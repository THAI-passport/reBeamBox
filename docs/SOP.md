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

## 12. Phase: build the client
TODO. Planned: Python client with bleak and Pillow, scan and connect, image and GIF conversion to 360x360, chunked writes with flow control, CLI. Icons only (Lucide) in any UI, no emoji.

## 13. Phase: tests
TODO. Planned: pytest unit tests for packet serialization, checksum, chunking, and frame conversion; golden vectors derived from the spec; no hardware required.

## 14. Reporting checklist
- Update docs/problem_solution.md with any new problem
- Tools and versions
- APK source URL, file size, SHA-256, version name and code
- Validation results and any suspicious findings
- What was committed and pushed
- Issues and open questions
