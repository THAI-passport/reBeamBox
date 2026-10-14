# Fixes

Things that need fixing and things already fixed. Add to Open when you find something; move it to Fixed with what was wrong and what changed. Same commit as the change.

## Open
- Close the reconciliation table in `docs/beambox-reverse-reference.md` row by row (code or hardware evidence), then fold anything still true into PROTOCOL.md/FACTS.md.
- No versioned mirror of the pinned XAPK is recorded as `URL2` in `analysis/sources.env`; the `latest` link will stop matching after the next vendor release. Add one when the owner has a stable copy.
- Recon task pack (`docs/tasks/`) is untried by a second agent; the first agent to use it should record where it tripped here.
- Hardware: nothing is confirmed on a real badge. Run `rebeambox probe --qualify --model nikko`, then follow `docs/first-session-checklist.md`. Every `[I]`/`[S]` claim in `docs/PROTOCOL.md` waits on this.
- `scripts/setup_tools.py` pins jadx and apktool versions and verifies SHA-256 only when `JADX_SHA256`/`APKTOOL_SHA256` are set (it prints the computed hashes); the JDK is the latest 17. Pin real hashes once a machine with github access has downloaded them.
- Windows and macOS are untested locally: CI covers them, the JDK bundle layout is unit tested, a real jadx run there has not happened.
- Cloud sessions: `d.apkpure.com`, `data.winudf.com`, `api.adoptium.net` and github release hosts are blocked unless the environment allows them (use `--local-file` otherwise).
- `?version=latest` in `analysis/sources.env` fails the hash check after the vendor publishes a new release; keep the exact XAPK privately or record a versioned URL.
- `docs/PROTOCOL.md` still uses `[C]/[I]/[S]`; tag mapping is documented, but the sections could be migrated to the repo-wide scheme incrementally.
- tshark is not available without root (problem_solution.md entry 2); capture analysis relies on `tools/replay_pcap.py`.

## Fixed
- Ported from reWatch (2026-10-14): the RCSP builder could build Jieli OTA frames although OTA runs on this same 0xAE00 link (opcode 0xE5 per the Jieli OTA SDK docs); a damaged upload ledger was renamed to `.bad` and counting restarted at zero, silently resetting the daily cap; there was no capture scrubber. Changed: `rcsp.pack` and both links refuse opcodes 0xE0-0xEF (top level and inner), the ledger fails closed until `uploads --reset`, `tools/scrub_capture.py` added; tests `test_ota_block.py`, `test_scrub_capture.py`, and `test_safewrite.py` now pins the fail-closed rule.
- Hash mismatch after a vendor update now says which version the downloaded XAPK is; `URL2` to `URL4` are tried in order (problem 67). Task pack commands are test-checked and a QUICKSTART exists (problem 68). Rebuild-only-when-necessary and record-after-every-pass rules added to AGENTS.md and SOP 9.2 (problem 69).
- The hardware checklist could not be run as written (the H8 rewrite test hit the identical-payload skip, free space was never printed, no passive notification logger, no test media, wrong FCC spelling, no write budget): added `docs/tasks/` (S0 to S11, HW-0 to HW-17, assumptions, status), `tools/make_test_media.py`, `tools/notify_log.py`, and a `badge status:` log line from the nn20 session.
- Rebuild and setup were bash-only (`sha256sum`, `declare -A`, linux-x64 JDK URL), so they failed on macOS (bash 3.2) and Windows: rewrote them in Python 3 standard library (`rebuild_analysis.py`, `setup_tools.py`), kept the .sh files as wrappers, added OS/arch detection, the macOS JDK bundle layout, a zsh PATH line, `apktool.bat`, and tests.
- jadx was OOM-killed on small machines and the cap lived only in the problem log: `--max-heap`/`JADX_HEAP`, default 3g under 8 GiB RAM, and an OOM kill now says so. `--url` overrides the download URL.
- Analysis files could not be rebuilt away from the original machine by script: added `scripts/rebuild-analysis.sh` and `analysis/sources.env` (hash-verified, idempotent, `--dry-run`, `--force`, `--recover`), jadx and apktool pinned in setup-tools.
- README stated a hard-coded test count (250) that contradicted the no-counts rule in docs/SOP.md 13.5 and had drifted; replaced with a pointer to CI.
- `docs/haiku5.5-is-garbage.md` renamed to `docs/review-critique-2026-10.md` with a neutral title; README links updated.
- No AGENTS.md existed; added AGENTS.md and CLAUDE.md.
