# Software recon tasks (S0 to S11)

No hardware, no Bluetooth, no live vendor contact. An AI agent can do all of these alone. Read `README.md` first (rules, assumption policy, result template). Work in order unless a task says it is independent. After each task: write the result file, update `STATUS.md`, commit.

Paths: run everything from the repository root. `analysis/` is git-ignored and may be empty on a fresh clone (task S1 fills it).

---
## S0. Baseline: environment, tests, rules
Goal: prove the checkout works before you change anything, so later failures are yours or not yours.
1. `python3 --version` (need 3.10 to 3.12; 3.13 usually works). `git status --short` should be clean; if not, note it and do not touch files you did not create.
2. Create the venv and install: `python3 -m venv .venv && . .venv/bin/activate` (Windows: `.venv\Scripts\activate`), then `pip install -e ".[test]"`. Or run `python scripts/setup_tools.py --no-venv` only if you also need Java tools (S1).
3. `python -m pytest -q`. Expected: all pass, a few skips (native auth library, Thai font, maybe ffmpeg). If anything fails on a clean checkout, record the exact failure in `docs/problem_solution.md` and in `fixes.md` and continue; do not "fix" unrelated failures inside this task.
4. `python tools/check_repo_rules.py` (expect `repo rules: ok`) and `python tools/make_fixtures.py --check` (expect `fixtures up to date`).
5. `ffmpeg -version` (needed only for GIF/video tests). Missing ffmpeg is fine; note it.
Pass: steps 3 and 4 clean. Record versions of Python, pytest, Pillow, bleak.

## S1. Rebuild or obtain the analysis tree
Goal: have `analysis/decompiled/sources` (jadx output) for the pinned app so S2 to S6 can grep it.
1. Check first: `ls analysis/decompiled/sources 2>/dev/null | head`. If it exists and `analysis/BUILD-INFO.txt` shows `package=com.guangshen.beambox` and `version=1.0.14`, mark S1 done.
2. Otherwise plan: `python scripts/rebuild_analysis.py --dry-run`. It prints what it would do and checks nothing on the network.
3. Tools: `python scripts/setup_tools.py --no-venv` installs JDK 17, jadx 1.5.6, apktool into `~/tools` (no admin rights). If a download host is blocked (typical in a cloud sandbox), see the decision table below.
4. Run: `python scripts/rebuild_analysis.py`. Use `--max-heap 3g` if the machine has little RAM. It downloads the XAPK, verifies SHA-256 against `analysis/sources.env`, extracts, runs jadx (exit 3 from jadx is normal: some methods fail), writes `analysis/BUILD-INFO.txt`.
5. Verify: `ls analysis/decompiled/sources | head`; expect about 10,000 `.java` files under many obfuscated one-letter packages and `com/example/nn20`.
Decision table:
| Situation | Do this |
|---|---|
| Download host blocked (apkpure, adoptium, github) | Mark S1 `blocked: needs human`. Tell the owner the hosts to allow, or ask for the XAPK file and use `--local-file PATH`. Continue with tasks that do not need the tree: S0, S7, S8 (partly), S9, S10. Do not guess code contents without the tree. |
| Hash mismatch (exit 3) | Stop S1. Do not use `--accept-new-hash`. The vendor probably published a new version (`?version=latest`). Record both hashes and the date, tell the owner, and mark S2 to S6 `blocked: needs approval`. |
| Tool version mismatch (exit 4) | Run `scripts/setup_tools.py`; or `--force` and write the actual versions in the result file. |
| jadx killed | `--max-heap 2g`, close other programs, rerun. |
| Disk full | Delete `analysis/work/jadx-simple` or caches; the decompiled tree is about 1 GB. |
Never commit anything under `analysis/` except `SOURCES.md` and `sources.env`.

## S2. Audit the unconfirmed claims in PROTOCOL.md
Goal: turn as many `[I]` and `[S]` statements as possible into `[C]`, or into a precise "cannot be settled in software" with the hardware test that settles it.
Needs S1.
1. List candidates: `grep -nE "\[(I|S)\]|Inferred|Speculative" docs/PROTOCOL.md docs/wifi-protocol.md docs/models.md docs/pulse.md`. Make a table: id, file:line, claim, current tag.
2. Do at most 25 claims per pass, highest value first: anything that changes bytes on the wire (lengths, checksums, opcodes, timing constants), then transport selection, then limits.
3. For each claim, find the code. Starting points (names may have moved; confirm with grep): `com/example/nn20` (BleProtocolConstant, BadgeMediaFileBuilder, BinConverter), package `com/zijun/badgesdk`, the connect click handler (`o7/t6.java`), the device manager `j8/c.java`. Method: grep a literal from the claim (a constant, a string, an opcode) in `analysis/decompiled/sources`, read the whole method with wide lines, follow callers.
4. Decide: Confirmed (change tag to `[C]`, add `source: <class.method>`); Contradicted (fix the sentence, fix code and tests if they depend on it, add a problem log entry); Not settled (leave the tag, add the hardware task id that would settle it).
5. If the decompiler failed on the method (stub with "JADX WARN" or a type-inference error), use `bash scripts/recover-failed-methods.sh` (needs bash) or read smali: `apktool d -s -f --no-res -o analysis/work/smali analysis/work/com.guangshen.beambox.apk`. Record behaviour only, never paste code into docs.
6. If a claim is contradicted and code depends on it: change the code in a separate commit with a test, run the full test suite.
Output: `results/S2-<date>.md` with the table (claim, old tag, new tag, source, action). Pass: every claim examined has a recorded outcome.

## S3. Static inventory of the vendor server API
Goal: know what the app asks its server, especially which products are `BT` versus `WiFi` (open item U in models.md). Static only: do not call any endpoint (assumption A10).
1. Find the base URL constants and endpoints: `grep -rnE "api/app/|https?://" analysis/decompiled/sources --include=*.java | grep -viE "schemas.android|w3.org|apache.org|google|github|xml" | head -200`. Narrow to app packages after the first pass (greps over the whole tree are slow; wrap in `timeout 120`).
2. For the badge list endpoint (`api/app/badge/select-badge`), find the response model (fields `deviceName`, `signalName`, `deviceType`, `badgeId`, image URL). Record field names and types from the model class, not from guesses.
3. List every endpoint that touches devices, firmware or media upload: path, HTTP method, request fields, response fields.
4. Record in `results/S3-<date>.md`. No tokens, no keys, no signed URLs; if you find a hard-coded secret, record only that one exists and where (class name), not its value, and tell the owner.
Pass: endpoint table plus a sentence stating whether any model name or product record is hard-coded (expected: no).

## S4. Static inventory of the firmware update path
Goal: understand how the app updates badge firmware so that a later hardware session knows what an OTA looks like. Static only; do not download firmware, do not call the update endpoint.
1. Find OTA classes: `grep -rliE "ota|upgrade|firmware" analysis/decompiled/sources --include=*.java | head -50`, plus the Jieli OTA SDK package (`com/jieli`) and `libjl_ota_auth.so` (see `docs/binaries.md`).
2. Record: how the app learns a new version exists (endpoint from S3), what file type it downloads (extension, header magic if visible), how it is sent to the badge (which characteristic or transport), what authentication step is used (libjl_ota_auth), and any size or version checks.
3. Mark clearly in the result: "NOT TO BE USED FOR WRITING". The client must never contain an OTA path (README rule 4).
Pass: a one-page description with tags `[C]` or `[I]`, plus the list of unknowns.

## S5. Inventory of everything the badge can send to the app
Goal: settle "does the badge send touch or other events" in software, and produce a negative-result list.
1. Enumerate receive paths: `onCharacteristicChanged` implementations in the vendor packages (nn20 manager, BadgeSdk manager, Wi-Fi poll loop). For each, list every message type or opcode the parser handles and what the app does with it.
2. Cross-check against `docs/PROTOCOL.md` section 8 (touch). Add any message type missing from the spec.
3. State the negative result precisely: "No code path parses touch coordinates: searched X, Y, Z" with the list of classes read.
Pass: table of inbound message types with source, plus the negative-result paragraph. Hardware test HW-13 verifies it later.

## S6. Scan filter and model detection audit
Goal: make sure the client finds every badge the app would find, and no more by accident.
1. In the app, find the scan filter and name matcher (`BluetoothDeviceNameMatcher`, `ScanFilter`, constants `NEO`, `B-Device`, the BLE suffix rule). Record the exact rules.
2. Compare with `rebeambox/scan.py` and `rebeambox/models.py` (`COMMON_NAMES`, per-model names). List differences.
3. For each difference decide: client is broader on purpose (fine, say why), or client misses a case (fix with a test in `tests/test_scan.py`).
4. Remember (problem log 32 and models.md section 5): the badge advertises as `E-badge` only on its pairing screen; the app's own filter would hide `Nikko-badge(BLE)`.
Pass: differences table; any fix has a test; full suite green.

## S7. Test media and payload size table
Goal: produce the media files the hardware plans need and know what each produces on the wire, so the write budget is accurate.
1. `python tools/make_test_media.py --out testmedia` (git-ignored). Videos need ffmpeg; without it use `--no-video` and note that H7 clips are missing.
2. For each file run a dry run per transport: `rebeambox send-image testmedia/noise.png --model nikko --transport nn20 --dry-run /tmp/d.txt` (the exact payload is `/tmp/d.txt.payload`). Record the payload size for nn20 type 5, nn20 album (`--nn20-still album`), BadgeSdk (`--transport badge`) and Wi-Fi (`--transport wifi`).
3. Reference sizes seen on one run (nn20 type 5, model nikko): noise.png about 83 KB, photo.jpg about 17 KB, red.png about 9 KB. Yours should be close; large deviations mean a code change worth a look.
4. Table in `results/S7-<date>.md`; paste into HW-RECON.md budget notes if different.
Pass: files exist, every dry run exits 0.

## S8. Simulator assumption register
Goal: list what `rebeambox/sim.py` assumes without app-code proof, so a hardware result can quickly show which assumption broke.
1. Read `rebeambox/sim.py` and `tests/test_sw_*.py`. For each behaviour the simulator implements (auth challenge, bind reply, status push content, ACK strings, time_mode semantics, free-space numbers, delays), mark whether `docs/PROTOCOL.md` backs it with `[C]` or it is a choice.
2. Write the list into `results/S8-<date>.md` as: behaviour, simulator location, backing tag, hardware task that would test it.
3. Where an invented number is hard-coded (for example free space), make it a named constant with a comment `# assumption, see docs/tasks/results/S8-...` (no behaviour change). Run the tests.
Pass: register complete; no test changed in meaning.

## S9. First-contact readiness check
Goal: prove the tools a human will run on the first session work end to end without hardware.
1. `rebeambox probe --qualify --simulate nn20 --report-dir /tmp/rep` and `--simulate badge`. Expect a report file in `/tmp/rep`. Open it; check it has: advertised name, services, MTU, transport decision, handshake result, status keys (size, freespace, time_mode), addresses masked.
2. `python tools/aggregate_reports.py` on a copy of the reports (do not leave simulated rows in `docs/compatibility-matrix.md`: run it with the repo's reports dir empty or check the diff and restore the file with `git checkout docs/compatibility-matrix.md`).
3. Dry runs for every send command (image, gif, video, text, stream synthetic) and for `--transport nn20|badge|wifi`; all must exit 0.
4. `python tools/replay_pcap.py fixtures/captures/nn20_animation_ack.btsnoop --out /tmp/x` decodes the synthetic capture; `malformed.btsnoop` must report errors without crashing.
5. Confirm the nn20 send log prints a `badge status:` line (size, freespace, allspace, time_mode). That line is how HW-7 reads free space.
Pass: all of the above succeed. Anything that fails is a bug: fix it (with a test) or log it in `fixes.md`.

## S10. Documentation consistency pass
1. Run `python tools/check_repo_rules.py`. Fix findings (emoji, analytics host names in code, non-local URLs in code).
2. Check for drift: `grep -rnE "[0-9]{3} (tests )?pass" docs README.md` (no test counts allowed), and values that must live only in `docs/FACTS.md` (screen size, picture size 360 versus 368, chip, limits): grep for them elsewhere and replace with a link.
3. Check relative links in the markdown files you touched.
4. Make sure `docs/tasks/STATUS.md` matches reality.
Pass: rules lint clean, no new drift.

## S11. Wrap-up
1. Update `STATUS.md`, append your assumptions to `ASSUMPTIONS.md`.
2. Update `docs/problem_solution.md` (new numbered entries) and `fixes.md`.
3. Run the full suite, the rules lint and the fixtures check once more. Commit with `docs:`/`fix:`/`feat:` prefixes; push to the branch you were given.
4. Final message to the owner, in this order: what is now `[C]` that was not, what was contradicted, what is blocked and on whom, the exact next command for the human (the first command of HW-2).
