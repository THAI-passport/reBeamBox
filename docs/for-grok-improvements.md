# reBeamBox: improvements worth doing (review for Grok)

Audience: Grok, or any reviewer with web access. This file is self-contained. It lists what to improve in the reBeamBox project, why, and what to check. Read the linked files in the repo for detail. Do not change code from this document alone. Propose changes as a pull request or as a written list, and say which claim you verified and which you could not.

Date of review: 2026-10-12. Branch: main at commit edf68f4 (the state reviewed).

## 1. State of the project (verified)

- Python client `rebeambox` v0.1.0 for Beambox round e-badges over BLE. Core code is about 3,100 lines in `rebeambox/`. Tests, tools and docs bring the total to about 6,900 lines of code plus 2,600 lines of docs.
- Tests: 303 passed, 2 skipped, 1 deselected (slow fuzz) in a fresh venv with `bleak`, `Pillow`, `pytest`. Command: `python -m pytest -q`.
- Repo rules lint (`tools/check_repo_rules.py`) passes. Fixture check (`tools/make_fixtures.py --check`) passes.
- Nothing in the project has run against a real badge. `rebeambox/sim.py` is a software badge written from the same spec as the client, so passing tests only show that the code agrees with itself. The project's own handoff document says this.
- CI is written in `ci/ci.yml` but not active. It is not in `.github/workflows/`.

## 2. Improvements, in priority order

### 2.1 Activate CI now (small, high value)
- The README says the push token lacks the `workflow` scope, so CI was staged in `ci/ci.yml`. The current `gh` token now lists `workflow` among its scopes.
- Action: move the file to `.github/workflows/ci.yml` and remove the "staged" note from the README.
- Check: the workflow runs repo rules, fixture check, `pytest -q`, and the no-vendor-calls test on Python 3.10, 3.11 and 3.12.

### 2.2 Freeze features until there is hardware evidence (high value)
- The last ten commits add features (safe-write policy, Wi-Fi/BLE streaming pipeline, first-contact tooling) that have only been tested against the software badge.
- Most open questions in `docs/HANDOFF-design-and-tests.md` section 5 can only be answered on a real badge. Examples: which transport the Pulse (NIKKO) uses, whether it accepts a still as an animation container or an IMB still, and the real MTU and throughput.
- Action: run a first real session with `rebeambox probe --qualify --model nikko` (dry-run first), following `docs/first-session-checklist.md` and `docs/hardware-test-v1.md`. Record results in `reports/` and let `tools/aggregate_reports.py` update `docs/compatibility-matrix.md`.
- Check: the streaming benchmarks in `docs/streaming-benchmarks.md` come from the software badge. Treat them as code benchmarks, not link measurements.

### 2.3 Fix documentation drift and reduce sprawl (medium value)
Facts that disagree between files:
- README says "250 pass, 1 skip". Current result is 303 passed, 2 skipped.
- Pulse screen size: 1.8 inch (stated by the project owner, recorded in `docs/models.md`), 1.83 inch (third-party reports in `docs/recon-web.md`), and 1.28 inch (a retail aggregator quoted in `docs/problem_solution.md`). These should be one fact with a clear evidence label until a badge is measured.
- Action: keep one fact sheet, have the README link to it, and remove hard-coded test counts from the README (or have CI print them).
- Sprawl: 23 documents in `docs/`, a 56-entry problem log, and a handoff written for "another AI". Consider merging overlapping files (for example the software test plan and the handoff) and keeping the problem log as the only changelog of problems.

### 2.4 Get a legal read before wider publishing (medium value, not a finding of wrongdoing)
- The public repository contains the default E1 authentication key and the algorithm for the BadgeSdk path. Both were recovered by static analysis and emulation of the vendor's native library (`rebeambox/jl_auth.py`, `docs/PROTOCOL.md` section 3.7.1).
- `analysis/SOURCES.md` lists where the vendor APK was obtained. The APK and decompiled trees are git-ignored, which is the right choice.
- Reverse engineering for interoperability is permitted in some jurisdictions (for example EU Software Directive Article 6, US DMCA section 1201(f)). Whether this project's work falls under such an exception depends on jurisdiction and facts. Reviewer task: list what a short legal review should check, and do not give legal advice as settled.

### 2.5 Safety on real hardware (medium value)
- The safe-write gate (`rebeambox/safewrite.py`, `docs/safe-write.md`) counts uploads per badge, skips identical payloads, refuses writes closer than 30 seconds apart, and warns on high counts. This is well designed.
- Suggestion: consider a hard daily cap by default, so a bad loop cannot wear the badge's flash. Consider an explicit confirmation before the first real write to a new badge address.
- Check: `--dry-run` is documented as the first step. Verify that `README.md` says so before any real write command.

### 2.6 Commit hygiene (low value)
- Commit messages follow a clear convention (`feat(...)`, `docs:`, `fix(...)`, `build:`).
- Some feature commits also contain large documentation changes. For example `7ac92f7` touches 11 files and about 978 lines. Separate code and docs commits make review easier.

## 3. What is already good (keep it)

- Layering: pure byte builders and parsers first, then media, then async sessions against an abstract link, then the CLI. Only `link.BleakLink` and `wifi.TcpChannel` touch real I/O.
- Evidence labels in the docs: [C] confirmed from code, [I] inferred, [W] reported by third parties, [U] unknown. Keep this practice.
- Repo rules enforced by tests: no emoji, no analytics or advertising hosts, no non-local URLs in client code. A test also checks that the client makes no vendor calls.
- Synthetic fixtures generated by the project's own builders, with a check that they are up to date.

## 4. What to ask Grok to do with this

1. Verify section 1 by running the tests in a clean virtual environment. Report the exact counts.
2. Check the drift claims in section 2.3 against the files and report any others.
3. Propose the exact diff for section 2.1 (moving the CI file) and confirm the workflow would pass on Python 3.10, 3.11 and 3.12. Do not run anything that touches real hardware.
4. Give a short, sourced list of questions for the legal review in section 2.4.
5. Suggest any improvement this review missed, labelled with its evidence level.

Do not contact the vendor, do not download the vendor app, and do not add credentials or keys to the repository.

---

Signed: Haiku 5.5 high
Date: 2026-10-12
