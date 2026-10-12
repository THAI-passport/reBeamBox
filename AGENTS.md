# AGENTS.md

Instructions for AI agents working in this repository (reBeamBox: an open Python client for Beambox-style BLE and Wi-Fi e-badges, written from static analysis, not yet tested on hardware). The generalized, target-agnostic version of this workflow lives in the reWork repo.

## Read first
- `docs/problem_solution.md`: every problem hit so far, with cause and fix or an explicit open status. Read it before starting work.
- `fixes.md`: what needs fixing and what was fixed.
- `docs/FACTS.md`: the single place for values sources disagree on (screen size, picture size, transports, chip, limits). Link to it; do not restate those values elsewhere.
- `docs/PROTOCOL.md`: the byte-exact spec. If the code and the spec disagree, one of them is wrong; find out which and fix it in the same commit.

## Logs you maintain
- Problem log: append to `docs/problem_solution.md` whenever you hit a problem or find a solution: what happened, the evidence, the cause, the fix, or "open" with what is needed. Same commit as the related change when practical.
- Fixes list: add anything that needs fixing under Open in `fixes.md`; when fixed, move it to Fixed with what was wrong and what changed. Same commit as the change.

## Evidence discipline
- Tag claims: `[C]` confirmed in the app code, `[V]` verified by emulation or test vector, `[H]` confirmed on a real badge, `[W]` third-party report, `[I]` inferred, `[U]` unknown. PROTOCOL.md's `[S]` (speculative) maps to `[U]`.
- The software badge (`sim.py`) is written from our own reading of the spec. Passing tests against it prove consistency, not truth. Never label anything `[H]` without a capture or a first-contact report.
- Do not write test counts in docs. Say "run `pytest -q`" or point at CI.

## Safety with real badges
- Contact with a real badge needs the user's go-ahead for each session. Start read-only: `rebeambox probe --qualify`. Writes come one at a time after that.
- Every real upload goes through the safe-write guard (counter, delta skip, minimum interval, hard daily cap of 50 per badge). Never bypass it in code or in a test run against hardware, and do not raise the cap without an explicit instruction and a flash-wear reason.
- Never add firmware-flashing or OTA paths.
- If the badge answers unexpectedly, stop and record it; do not retry in a loop.

## Platform support
- Supported for now: Linux (Debian/Ubuntu, including headless) and macOS for development and tests; Windows 10/11 is documented for use but not maintained per change. Keep code portable (`pathlib`/`os.path`, no shell-only syntax in Python).
- When you add a dependency, extra, script, or setup step, update `README.md`, `pyproject.toml`, and `scripts/setup-tools.sh`.
- If a platform lacks something the work needs (no Bluetooth adapter, no BlueZ, no ffmpeg, no root), tell the user which platform, what is missing, and the options. Do not silently skip it. Record it under Open in `fixes.md`.
- Say which platforms you actually ran a change on and which are untested.

## Reverse-engineering rules
- Static analysis comes first: read the app, decompile it, disassemble and emulate native code. Do not install or run the vendor app on your own machine unless the user approves a live test.
- Live testing is allowed when the user approves it for that session: a real badge, a phone running the vendor app for an HCI snoop or Wireshark capture, or a live site or service the user owns or may test. Say what you will touch and for how long, start read-only, stop at the first throttle, auth challenge or unexpected reply, and record the result in `docs/problem_solution.md`. Never enter credentials or bypass protections.
- Never commit the APK, XAPK, split APKs, decompiled output, native libraries, vendor assets, raw captures that contain personal data, tokens, or signed URLs. Commit notes in our own words, hashes, source URLs, scripts, original code, tests, and sanitized or synthetic fixtures.
- Work that happens away from the machine holding the analysis files must be reproducible: `analysis/SOURCES.md` and `analysis/sources.env` record where the app came from and its hashes, and `scripts/rebuild-analysis.sh` rebuilds `analysis/` (download, verify hash, extract, decompile; `--dry-run` first, never use `--accept-new-hash` without telling the user; see docs/SOP.md section 9.1). If the files cannot be rebuilt, say so and ask the user for them; do not guess.
- The client makes no vendor calls: no analytics hosts, no non-local URLs in code. `python tools/check_repo_rules.py` and `tests/test_no_vendor_calls.py` enforce it. This applies to the finished client, not to research.
- Procedure for new targets or new research passes: `docs/SOP.md`.

## UI and docs style
- No emoji in docs, code, or the web UI. Use icon components (for example Lucide) in any UI.
- Plain, specific prose. Date-stamp observations that can go stale (CI state, versions).

## Build workflow
- Keep every uncertain value a named constant or CLI flag so first hardware contact needs flag changes, not rewrites.
- Layering: pure byte builders and parsers, then media, then async sessions over the abstract `Link`, then the CLI. Only `link.BleakLink` touches Bluetooth.
- Before committing: `python tools/check_repo_rules.py`, `python tools/make_fixtures.py --check`, `python -m pytest -q`. Tests needing optional packages or native libraries must `importorskip` with a reason.
- Work in coherent phases; commit after each one with a short imperative message (`feat(scope): ...`, `fix(scope): ...`, `docs: ...`). Never push to `main` directly; use the designated work branch and do not open a pull request unless asked.
- Docs that describe behaviour change in the same commit as the code.
- Stop and ask when a step needs the user: providing hardware, approving a real write, installs needing root, or any decision about the legal notes.
- Never commit personal data: Bluetooth addresses (mask them), serial numbers, account ids, home Wi-Fi names. `reports/` is git-ignored for that reason.
