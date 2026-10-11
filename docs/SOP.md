# SOP: Reverse engineering an Android app and its BLE protocol

Reusable procedure, written from the reBeamBox work on com.guangshen.beambox. Phases marked TODO are to be filled in as they are completed.

Ground rules
- Static analysis only. Never install or run the target APK.
- Do not commit the APK, split APKs, or decompiled app code to a public repo. Commit only notes, hashes, URLs, scripts, and original code.
- No emoji in docs or in the client app. Use icons (Lucide) in any UI.
- Record every external action (download, push) so it can be reproduced.

## 1. Repository setup
1. Create the repo (here: reBeamBox) and push it. With the GitHub CLI: `gh auth status`, then `gh repo create <name> --public --source . --push`.
2. Standard layout: `analysis/` (notes, SOURCES.md), `analysis/apk/` (ignored), `analysis/decompiled/` (ignored), `docs/`, `scripts/`, `tests/`.
3. Set a repo-local git identity if none exists (`git config user.name`, `git config user.email`). Commits fail with "Author identity unknown" otherwise. Reuse the identity from earlier commits (`git log -1 --format='%an <%ae>'`).
4. Add to `.gitignore` before downloading anything: `analysis/apk/`, `analysis/decompiled/`, `.venv/`, `__pycache__/`, `node_modules/`.

## 2. Tool setup without sudo
Script: `scripts/setup-tools.sh` (idempotent, installs into `~/tools`).

| Tool | How | Verify |
|------|-----|--------|
| JDK 17 | Temurin tarball from the Adoptium API into `~/tools/jdk` | `java -version` |
| jadx | Release zip from GitHub (skylot/jadx) into `~/tools/jadx` | `jadx --version` |
| apktool | Release jar from GitHub (iBotPeaches/Apktool) plus a wrapper script that calls `~/tools/jdk/bin/java -jar` | `apktool --version` |
| Python venv | `python3 -m venv .venv`, then `pip install bleak pillow pytest` | `.venv/bin/pip list` |
| tshark | Needs root via apt; see pitfalls | `tshark --version` |

Steps
1. Check what exists: `which java jadx apktool aapt tshark python3 unzip curl`, `id -u`, `sudo -n true`.
2. Run `./scripts/setup-tools.sh`.
3. PATH is added to `~/.bashrc` (JAVA_HOME, jadx/bin, apktool). In a non-login shell, `source ~/.bashrc` or export the same line.
4. Verify every tool with its version flag and record versions in the report.

Versions used: JDK 17.0.20.1, jadx 1.5.6, apktool 3.0.3, bleak 3.0.2, pillow 12.3.0, pytest 9.1.1.

## 3. Sourcing the APK
1. Search the package name to find current version and reference hashes. Listing sites (AppBrain, Chinese mirrors) are useful for version and size cross-checks only, not as download sources.
2. Download only from a reputable mirror (APKPure, APKMirror, Uptodown) or an official site.
3. APKPure direct link pattern: `https://d.apkpure.com/b/APK/<package>?version=latest`. It answers with a 302 to a tokenised URL on data.winudf.com. Use `curl -sIL -A "Mozilla/5.0"` first to read size and filename, then `curl -sL -A "Mozilla/5.0" -o <file>`.
4. Large downloads can exceed the shell timeout and get backgrounded. Wait on the job and read its output file.
5. Compare size with the redirect's `full_size` parameter and note the version (it may be newer than listing sites).

## 4. XAPK handling
- An XAPK is a zip: base APK, split APKs (config.arm64_v8a, language, density), `manifest.json`, `icon.png`.
- `unzip -l file.xapk` to list, `unzip -p file.xapk manifest.json` for package, version name/code, min and target SDK, and permissions.
- Extract only the base APK for analysis: `unzip -oq file.xapk <package>.apk -d <tmp>`.
- Native libraries live in the arm64 split. Extract it only if native code needs analysis.

## 5. Validation (before any analysis)
1. Integrity: `unzip -t file.xapk` and `unzip -t base.apk` must report no errors.
2. Identity: `apktool d -f -o out base.apk`, then confirm `package=` in `AndroidManifest.xml` and `versionName`/`versionCode` in `apktool.yml`. For a quicker check without resources, `apktool d -s -f --no-res`.
3. Review permissions in the manifest for anything out of character. Note it, do not panic: CALL_PHONE was odd but explainable for a badge companion app.
4. Signature: no v1 files in META-INF means v2/v3 signing. Not verified here. Where available, `apksigner verify --print-certs` is the next step.
5. If anything fails to validate or looks suspicious, stop and report.
6. Clean up temp directories afterwards. Do not delete a directory that is your current working directory (the shell then refuses further commands); `cd` out first.

## 6. Hashing and provenance
1. `sha256sum` the downloaded file and the inner base APK.
2. Write `analysis/SOURCES.md`: package, version, source name, URL, file name, size in bytes, both hashes, and a note that the archive is ignored.
3. Commit SOURCES.md and the setup script; never the archive.
4. Confirm nothing sensitive is tracked: `git ls-files | grep -ci xapk` should print 0.

## 7. What not to commit
- The APK, XAPK, split APKs, extracted dex, resources, or native libraries.
- Anything under `analysis/decompiled/`.
- Third-party app assets (images, strings) and any tokens from download URLs.
- Credentials of any kind.
Commit instead: notes in the repo's own words, the protocol spec, original client code, tests, scripts.

## 8. Pitfalls encountered
Full running log with causes and status: docs/problem_solution.md. Append to it whenever anything goes wrong.

- Relative path bug: in `setup-tools.sh`, `cd "$(dirname "$0")/.."` ran after an earlier `cd ~/tools`, so a relative `$0` no longer resolved. Fix: compute `ROOT="$(cd "$(dirname "$0")/.." && pwd)"` at the top before any `cd`, and use `cd "$ROOT"` later.
- tshark needs root: apt cannot run without sudo, so tshark is not installed. The script prints a notice instead of failing. Options: ask for sudo, build Wireshark from source in user space, or parse pcaps with Python (scapy or pyshark needs tshark, so prefer reading btsnoop logs directly).
- Missing git identity makes `git commit` fail even after `git add`; the staged state is kept, so just set the identity and commit again.
- Deleting the current working directory breaks the shell tool. Use `working_directory` set to a stable path.
- `java` not found in a fresh shell until PATH is exported.
- Listing sites show conflicting versions and sizes (1.0.13 vs 1.0.14, 57/77 MB). Trust the mirror's own metadata and the manifest inside the file.

## 9. Phase: decompile with jadx
Commands (run from the repo root, JAVA_HOME and PATH set per section 2):
```
unzip -oq analysis/apk/<file>.xapk <package>.apk -d analysis/work
nohup bash -c 'S=$(date +%s); jadx -j 4 -d analysis/decompiled analysis/work/<package>.apk > analysis/jadx.log 2>&1; echo "exit=$? seconds=$(( $(date +%s)-S ))" > analysis/jadx.done' >/dev/null 2>&1 &
```
- Add `analysis/work/` to .gitignore as well. The jadx log and .done file are kept local (analysis/ logs are not needed in git).
- Result for v1.0.14: 8 cores, 45 seconds, `-j 4`. 8,246 classes processed, 10,755 .java files written, exit code 3 with "finished with errors, count: 63". Exit 3 only means some methods failed to decompile (jadx prints a stub with a type-inference error); the output is still usable. Inspect those methods in smali (apktool) if needed. Example: the animation file builder failed in jadx.
- Progress output uses carriage returns; read the log with `tr '\r' '\n' < analysis/jadx.log | grep -v progress:`.
- Code is R8-obfuscated (single letter packages such as a/, o7/, p7/), but the vendor package com.example.nn20 keeps many names. Resources decoded to analysis/decompiled/resources (use that AndroidManifest.xml, which is readable).
- Companion docs: docs/app-behaviour.md (screens, flows, permissions) and docs/binaries.md (APK, splits, native libraries). Write both from the manifest, jadx tree, and `unzip -l` of each split.

## 10. Phase: locate BLE UUIDs
Method used (all greps from analysis/decompiled/sources):
1. Find GATT users: `grep -rlE "BluetoothGattCallback|writeCharacteristic|requestMtu" --include=*.java .`. Many hits are bundled SDKs (here Jieli, com.jieli.*). Separate vendor code from SDK code by package.
2. List every UUID literal: `grep -rnE "UUID\.fromString\(" --include=*.java . | grep -vE "androidx|com/google|kotlin|okhttp3"`. Expect several stacks. Standard 0x2902 is the CCCD.
3. Identify the real one by following the vendor package: the class holding service constants (here BleProtocolConstant) and who references it (`grep -rl BleProtocolConstant`). The GATT callback shows discovery, notification enable, MTU request.
4. Read BluetoothGattCallback subclass for: requestMtu value, fallback MTU, getService and getCharacteristic order, descriptor write.
5. Find write type with `grep -n setWriteType`; value 1 is WRITE_NO_RESPONSE, 2 is default write with response.
6. Scan filters: look for ScanFilter, device name matchers and constants for names.
Findings for this app are in docs/PROTOCOL.md (service 0x01F0, write 0x01F1, notify 0x01F2).

## 11. Phase: trace the upload pipeline
Method used (what worked):
1. Start from the UI, not the first UUID hit. Find the click handler that connects (here o7/t6.java) and note how it chooses a transport. This revealed three transports.
2. Find the send entry points: grep for `.sendPhoto(`, `.sendFile(` and the manager's send method over vendor packages. Read the sender method fully (framing, chunk size, checksum).
3. Follow the pacing code: Handler.postAtTime and postDelayed calls, retry counters, timeouts, batch sizes. Record constants.
4. Read the receive path (`onCharacteristicChanged`) for the reply layout and the ACK matching strings.
5. Read the media builders (BinConverter, BadgeMediaFileBuilder); where jadx fails use `apktool d --no-res` and read the smali strings (it exposed the ffmpeg command line).
6. For native helpers, extract the .so from the split APK and disassemble with capstone and pyelftools (pip install into the venv). A 72-byte CRC function was enough to identify the algorithm; verify with the check value of "123456789".
7. Generate worked examples with a small script (scripts/spec_vectors.py) that implements only the documented formulas, and paste its output into docs/PROTOCOL.md.
8. Tag every statement Confirmed, Inferred or Speculative.
Outputs: docs/PROTOCOL.md, docs/app-behaviour.md, docs/binaries.md, and docs/hardware-prediction.md and docs/streaming-plan.md for design work.

### 11.1 Native-library recovery by emulation (worked for libjl_auth.so)
1. List symbols and sections with pyelftools; `.dynsym` names (function_E1test, function_E21) and the JNI strings in `.rodata` (class and method names) tell you the surface. `.rela.plt` order maps PLT stubs to libc imports (malloc, free, rand).
2. Disassemble `.text` with capstone to a file; read JNI_OnLoad to find the RegisterNatives table in `.data` (name, signature, function pointer), then each native.
3. Constants in `.data` and tables in `.rodata` are the secrets; compare tables against textbook ones (here SAFER+ exp, log and bias tables) before assuming custom crypto.
4. Do not trust a hand port: run the real function with unicorn (pip install unicorn). Map PT_LOAD segments at their vaddr, give TPIDR_EL0 a mapped page (stack canary), enable FP/SIMD via CPACR_EL1, hook the PLT stubs for malloc and free, set PC to the link register to return from a hook (not LR minus 4). Script: tools/emulate_jl_auth.py.
5. Port stage by stage (key schedule, block cipher, wrapper) and compare each stage with the emulator on random inputs; freeze the emulator outputs as test vectors (tests/test_jl_auth.py).
6. Do not commit the .so; commit only the emulation script and vectors.

### 11.2 Reading an SDK's command layer (worked for Jieli RCSP)
Read in this order: frame packer/parser (ParseHelper, BasePacketParse), command classes (opcode in the super constructor, param toData/parse), response handlers (cmdHandler classes switch on opcode), then the task that sequences them (TransferTask). Types in the base classes decide the "wants response" flag. Write pure-function builders (rebeambox/rcsp.py) and unit tests with frames derived by hand.

## 12. Phase: build the client
Done (v0.1, untested on hardware). Procedure that worked:
1. Layer the client like the protocol: pure byte builders and parsers first (control.py, nn20.py, rcsp.py, jl_auth.py), then media conversion (media.py), then async sessions written against an abstract Link (session.py, link.py), then the CLI. Only link.BleakLink touches Bluetooth.
2. Write the badge side as a simulator (sim.py) that implements the documented protocol, including auth and the device-pulled file transfer. Run the real session code against it. This finds client state-machine bugs without hardware and powers `--dry-run` (RecordingLink logs every write and notification in order).
3. Keep every uncertain value a named constant or option (device-name filters, picture size, animation type, MTU) so first hardware contact only needs flag changes.
4. Choose the transport by service discovery after connecting, not by name.
5. Product questions that code cannot answer (for example what BLE name the Pulse uses) become CLI options, and are recorded in docs/pulse.md.
6. Prove the client has no vendor calls with a test that greps the package for URLs and network modules (tests/test_no_vendor_calls.py), and document any promotional surfaces of the original in docs/ads-removal.md.
Modules: control (0x9E frames), rcsp and jl_auth (Jieli), nn20 (containers and framing), media (Pillow, ffmpeg using the documented AVI command), scan, link, session, sim, client, cli.

### 12.1 Per-model research
1. Grep the decompiled tree and resources for each model name (case-insensitive) and list every hit; here only layouts, one string and one trimmer branch matched. Absence of a model table means the product list is server-side.
2. Trace the stored selection keys (MMKV or SharedPreferences) from where they are written to every place they are read; this exposed the device type switch (BT versus WiFi) and the one NIJI branch.
3. Do web recon after the code pass: vendor spec pages, FCC filings (grantee, internal photos, chip), teardowns, and hands-on write-ups. Treat them as unverified, label them, and let hardware reports overrule code-only inferences (here: nn20 service only, type 5 container for stills).
4. Put every model difference into a profile object (models.py) so the CLI option only selects data.

## 12.2 Per-transport research: the Wi-Fi path
Procedure that worked, reusable for any secondary transport:
1. Start from the constants (IP, port, SSID substring) and grep every user of them; expect the real logic in obfuscated or misnamed classes (here the sender was a lambda dispatcher in an androidx package and a vendor OTA package, found by grepping for `getOutputStream` and `Socket`).
2. Find the single place bytes are written, then walk backwards to every caller: that yields the complete command list (2-byte words) without needing the reader code.
3. Read the reader (poll loop) for the reply words, and the UI handlers for what each means.
4. Quote request text literally from the string builder; jadx shows it, `cut` can hide the tail of long lines (use wide columns).
5. Frame rate and size limits live in the analyzer callback (a time check) and the encoder (quality, size warning), not in the transport.
6. Build the software badge with the same state machine (control words, HTTP, camera mode) and serve it both in process (dry run) and over a loopback TCP server in a test.
7. For input events: enumerate the incoming command parsers and listener interfaces, not text searches for names like touch; then state the negative result with the list.

## 12.3 Recovering methods the decompiler failed on
1. List the failures: grep the output for `JADX ERROR` and print the enclosing signature; classify each as library (androidx, kotlin coroutines, GMS, ZXing) or app (package of the app, or referencing it). On this APK 38 error markers were found; only one app method mattered (`BadgeMediaFileBuilder.a`); the rest were library code (compose, coroutines, QR encoder, media3).
2. Re-run with `jadx -m simple --show-bad-code`: region-maker overflows disappear (63 errors became 35) and the splash activity deep-link switch was recovered; type-inference failures stay.
3. For a type-inference failure read the smali (apktool) and, to confirm, convert the one dex with dex2jar and decompile the class with CFR (`--jarfilter`); CFR handles a register reused as long and double. Script: `scripts/recover-failed-methods.sh`. Both outputs stay in git-ignored `analysis/work`.
4. Only record behaviour, not code; find callers by grepping the call site to learn where each argument comes from.

## 13. Phase: tests
`.venv/bin/python -m pytest tests -q` (software test plan: docs/software-test-v1.md; hardware plan: docs/hardware-test-v1.md; no hardware, ffmpeg tests skip if ffmpeg is missing). Coverage: frame serialization and checksums (control, nn20, rcsp), auth vectors frozen from the native library emulation, container layouts, media conversion and the 3 s cap, session flows against the simulators (still, animation, no packet CRC, retry after a failed packet, free-space refusal, memory refusal), CLI dry run output, and the no-vendor-calls check. Pitfall: a test GIF made of near-identical frames is merged by Pillow on save; make frames visibly different.

## 13.1 First-contact tooling (before the first real badge)
Build tooling that makes the first hardware session cheap and loss-free: (1) a read-only qualification command that records advertisement, MTU, GATT, transport decision and the first reply into a report shaped like the results template (`probe --qualify`; test it against the software badges with `--simulate`); (2) pacing and packet size as flags derived from the negotiated MTU, with an automatic fallback so a first run does not stall; (3) an offline replay tool for a capture of the vendor app (`tools/replay_pcap.py`) so the reference traffic can be decoded with the same parsers as the client, which turns every capture into a regression test; (4) a dependency-free browser harness (`ui/`) as a second implementation, cross-checked byte for byte against the Python one in a test (Node, skipped if missing). Pitfalls: synthetic captures must include fragmented ACL packets and PDUs without discovery; do not require valid checksums when classifying, or corrupted frames disappear.

## 13.2 Fixtures, aggregation and CI
Once a parser exists, give it regression data before real captures arrive: generate small synthetic captures with the same builders the client uses (deterministic, committed with a manifest that says SYNTHETIC, plus a `--check` mode so drift fails CI), include a deliberately malformed one (bad checksum, bad CRC, dropped sequence number) and require the tool to report it instead of crashing. Aggregate field reports with an idempotent script that rewrites only a marked block of a document. Put the project rules (no emoji, no analytics hosts, no non-local URLs in code) in a lint script with its own tests and run it in CI next to the explicit no-vendor-calls test. CI pitfalls: a token without the `workflow` scope cannot push `.github/workflows/*` (stage the file elsewhere, then `gh auth refresh -s workflow` and `git mv` it); tests that need an extracted native library must skip when it is absent (it is not in the repository); verify by running the suite with the library hidden. Document protocols with sequence diagrams only from the code path that implements them and label inferred steps in the diagram text.

## 13.3 Safe-write policy and streaming prototype
1. Before adding any "send often" feature, find out what a send costs the device (here: a flash write, from third-party teardown reports labelled W) and add a guard first: per-device counter in a state file that stores a hash of the identifier, a hash of the last payload for skipping unchanged sends, a minimum interval, and warning thresholds; count only after success; keep dry runs out of the counter. Put the check where the payload is known (after the handshake) and before the first data frame. Test the guard with an injected clock.
2. Build a streaming pipeline as small replaceable stages (source, crop, encode, rate control, sink) with an injectable clock: a virtual clock makes a 20 s stream run in milliseconds and the tests deterministic. Model the link with named, labelled assumptions and print them next to any number derived from them; only hardware numbers may be called measured.
3. When a transport has no live mode, say so in code and in the benchmark: the BLE sink sends clips, goes through the write guard, and its numbers are labelled a slideshow.
4. Benchmarks are a script that regenerates a document (`tools/bench_stream.py --write`), so the document never drifts from the code.

## 13.4 Dependency split
Keep the runtime small and make heavy or native-build packages opt-in: core dependencies in `dependencies`, `[test]` for the test runner, `[emulation]` for packages that need wheels or compilers (unicorn, capstone, pyelftools), `[dev]` kept as an alias so old commands work, `[full]` for both. Every test that needs an optional package or a native artifact must `importorskip` it and skip with a reason. Prove the split by building a fresh venv with only core + test and running the whole suite (skips allowed), then repeat with everything; the setup script defaults to the small set and reports, never fails on, a failed emulation install. CI installs the small set.

## 14. Reporting checklist
- Update docs/problem_solution.md with any new problem
- Tools and versions
- APK source URL, file size, SHA-256, version name and code
- Validation results and any suspicious findings
- What was committed and pushed
- Issues and open questions

## 15. Thought process and tooling (why each tool, how probed, outcome, decision)
- CFR and dex2jar (added): why: jadx cannot type a method whose register is reused as long and double. Installed without sudo: CFR jar from Maven Central, dex2jar release zip from GitHub into `~/tools`, driven by `scripts/recover-failed-methods.sh`. Worked: CFR decompiled the animation builder cleanly and matched the smali. Failed: jadx `--show-bad-code` and `-m simple` do not fix type failures (simple mode does remove the region-maker overflows, 63 errors to 35). Decision: smali first, CFR to confirm, jadx simple mode for the rest; never trust one decompiler for a critical method.
- capstone and pyelftools, second use (native pass 3): list exports first (`.dynsym` with sizes), classify by name, then disassemble only functions that look like constants (disk init, ioctl, mkfs wrapper). Result: the extra libraries held no badge limits; recording a negative result is part of the work.
- WebSearch and WebFetch, recon: search the FCC grant first (the registry page names grantee, exhibits and bands), then teardown posts and open-source clients for the same chip; fetch the full article rather than relying on a summary snippet, label every claim W, and keep a table of conflicts (retail copy versus spec sheets) instead of resolving them silently.
Format per tool: why, how installed or probed, worked, failed, decision. Update this section whenever a tool choice changes. Related: problem_solution.md has the dated failures.

General rule used throughout: probe a tool with a version command or a ten-second smoke test before relying on it, record the result, and prefer tools installable in user space (the box has no sudo). When a tool fails, look for a smaller tool that does the same job rather than fighting the environment.

### gh (GitHub CLI)
- Why: create the public repo and push every milestone without manual steps.
- Probe: `gh auth status` before anything else; repo created with `gh repo create <name> --public --source . --push`.
- Worked: authenticated on the box, repo THAI-passport/reBeamBox, push after every milestone.
- Failed: first commit failed for a missing git identity (problem log); fixed with a repo-local identity, not a global one.
- Decision: commit and push per milestone so work is never only local; keep the APK and decompiled tree out via .gitignore.

### APKPure (and listing sites)
- Why: need the real APK; the box cannot use Google Play. APKPure, APKMirror, Uptodown are the reputable mirrors; official site if one exists.
- Probe: direct link pattern `https://d.apkpure.com/b/APK/<package>?version=latest` with curl following the redirect; compared sizes and versions with listing pages.
- Worked: 75 MB download, inner base APK validated by `unzip -t` and apktool reading the manifest (package name, versionCode 24).
- Failed: download passed the 30 s foreground limit (use a background job and wait); the file was an XAPK (a zip of split APKs); listing sites disagreed on version and size.
- Decision: trust the file's own manifest over listing text, record URL, size and SHA-256 in analysis/SOURCES.md, never run the APK, never commit it.

### Java, jadx, apktool
- Why: jadx gives readable Java quickly for protocol tracing; apktool gives smali and resources when jadx fails.
- Probe: user-space JRE, jadx release zip in ~/tools, apktool jar; `--version` on each, PATH via ~/.bashrc (new shells did not inherit PATH at first, so export explicitly in scripts).
- Worked: jadx produced about 10,755 files in the background (log with carriage returns, read with `tr '\r' '\n'`).
- Failed: exit code 3 with 63 methods not decompiled, including the animation file builder; names are obfuscated by R8 so greps for plain names often fail.
- Decision: use jadx for survey, apktool smali for failed methods (the builder's ffmpeg command string was only visible in smali), and navigate obfuscation by following constants, string literals and stored keys instead of class names.

### Search strategy on a big tree (ripgrep and grep)
- Why: finding the BLE stack, constants and writers across 10k files.
- Worked: grep for UUID strings, `getOutputStream`, `Socket`, `new byte[]{0,`, `@SerializedName`; trace each stored key (MMKV keys) to every reader and writer.
- Failed: whole-tree recursive grep sometimes neared the shell time limit; names of models barely occur in code.
- Decision: wrap in `timeout`, narrow to likely packages after the first hit, and treat product identity as server data.

### bleak, Pillow, ffmpeg, pytest (client stack)
- Why: bleak is the cross-platform Python BLE library (asyncio, Linux BlueZ, macOS, Windows); Pillow for stills, circular mask, text and GIF frames; ffmpeg because the documented animation builder shells out to it with an MJPEG AVI command; pytest for fast tests with no hardware.
- Probe: installed into a venv; imported each; `ffmpeg -version` check at runtime with a clear error and tests that skip when absent.
- Worked: only `link.BleakLink` touches Bluetooth, everything else is pure and testable.
- Failed: scan on a machine without BlueZ raised a bare errno (now a clear message); Pillow merged identical GIF frames in a test (use distinct frames).
- Decision: keep Bluetooth behind an abstract Link, keep every uncertain number a named constant or CLI flag.

### objdump, radare2, Ghidra, capstone, pyelftools
- Why: the Jieli authentication lives in `libjl_auth.so` (aarch64) and a CRC in `libjl_crc.so`; the file transfer cannot start without them.
- Probe: `objdump` on the box is x86 only; Ghidra and radare2 were not available without sudo and a large install, so they were not used.
- Worked: capstone plus pyelftools in the venv disassembled both libraries (the CRC is a 72-byte function; the auth is E1 on SAFER+).
- Failed: no aarch64 objdump (problem log 17).
- Decision: a pip-installable disassembler is enough for small libraries; only reach for Ghidra when the function is too large to read.

### unicorn (CPU emulation of libjl_auth)
- Why: a hand port of a cipher is easy to get subtly wrong and there is no device to run the library on; emulating the real function gives ground truth vectors.
- Probe: map the library PT_LOAD segments, set up stack, TPIDR_EL0 page (stack canary), enable FP/SIMD, hook the PLT stubs for malloc and free, call the exported function with chosen inputs.
- Worked: random-input comparison stage by stage against the Python port until all stages matched; vectors now in tests/test_jl_auth.py.
- Failed: first run returned all zeros (hook returned to lr-4 instead of lr; FP/SIMD disabled).
- Decision: always verify a port against the real code on random inputs, and commit the vectors (not the library).

### Software badges (sim.py) and dry-run
- Why: no hardware, so the only way to find client state-machine bugs is a second implementation of the badge side written from the spec.
- Probe: write the simulator from the documented bytes, run the real session code against it, then expose the same pairing as `--dry-run`.
- Worked: found a wrong LTV length in the simulator that stalled a transfer; the Wi-Fi badge also serves a real loopback TCP socket in a test.
- Failed: a simulator shares the author's misreadings, so it proves consistency, not truth.
- Decision: label everything untested on hardware, and use the first-session checklist to replace assumptions with captures.

### Web reconnaissance
- Why: the APK does not contain product identity (server data) and cannot say which service a given model exposes.
- Probe: product pages, vendor spec page, teardown-style articles, FCC listings, forum and repository reports of the same hardware; WebSearch then WebFetch, with curl as fallback for blocked pages.
- Worked: third-party reports of Niji and Nano showing only service 0x01F0, the black screen for type 6, the `E-badge` advertised name, Jieli BR28 class chip.
- Failed: results are second-hand and sometimes marketing; no direct Pulse capture found.
- Decision: tag web facts Inferred, change client defaults only when a report is specific and consistent with the code (stills as type 5), and keep the old behaviour behind a flag.

### Wi-Fi analysis path
- Why: a second transport (TCP 8080, live camera) existed only as constants; it matters for live streaming.
- Probe: grep constants, find the single writer, enumerate callers for the command list, read the reader loop for replies, read the camera analyzer for limits (see 12.2).
- Worked: full control-word table, frame format, 300 ms spacing, upload request text, all from code; software Wi-Fi badge and `stream` command.
- Failed: the sender was hidden in misnamed obfuscated classes; the first doc draft misstated a header read through a truncated line (problem 35).
- Decision: Wi-Fi is selected by server product type, so the client takes `--transport wifi`; whether any given model has Wi-Fi is left to the first session.

### Test planning (software tests before hardware)
- Why: with no badge, the most valuable tests are the ones that would catch a wrong byte on the wire or a parser that loses data.
- How: wrote the plan first (docs/software-test-v1.md: purpose, inputs, expected, location), then the tests; wrote the hardware plan (docs/hardware-test-v1.md) from the same unknowns so each software assumption has a hardware check.
- Techniques that fit this kind of project: independent parsers in the test (round trip against the builder), boundary values at every length field, snapshot hashes over fixed inputs (embed a fixed JPEG instead of encoding one so the lock survives library upgrades), seeded random loops as property tests when hypothesis is not installed, ground-truth emulation for crypto behind a slow marker, and skip-by-design for tests that need external files, fonts or ffmpeg.
- Decision: a test that documents a known ambiguity (the 127-byte frame) is kept and named after the problem log entry.

### Reuse notes for another app
1. Order: manifest and permissions, then UUID or port constants, then the single write path, then reply parsing, then containers and checksums, then auth, then client, then simulator, then hardware.
2. Mark every claim Confirmed, Inferred or Unknown the moment you write it; fix claims by reading the full source line, not a truncated one.
3. Keep a problem log from the first minute; most entries became SOP steps.
