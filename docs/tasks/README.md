# Recon task pack (software and hardware)

Written for an AI agent or a person who has not seen this project before. Follow it literally. Where it is silent, make an assumption using the policy below, write it down, and keep going.

Context in one paragraph: reBeamBox is an open Python client for Beambox-style round e-badges (NIKKO = Pulse, NANO, NIJI) over BLE (and possibly Wi-Fi). It was written from static analysis of the vendor Android app. Nothing has been confirmed on a real badge yet. The two jobs are: (1) squeeze the remaining certainty out of the app code (software recon, no hardware), and (2) run a controlled first contact with a real badge (hardware recon). Evidence tags used everywhere: `[C]` confirmed in app code, `[V]` verified by emulation or test vector, `[H]` confirmed on a real badge, `[W]` third-party claim, `[I]` inferred, `[U]` unknown.

## Files in this pack
| File | Purpose |
|---|---|
| `SW-RECON.md` | Tasks S0 to S11. No hardware, no Bluetooth. An AI can do all of them in a normal sandbox. |
| `HW-RECON.md` | Tasks HW-0 to HW-17. Need a physical badge and a machine with Bluetooth. |
| `ASSUMPTIONS.md` | Pre-made assumptions (so you never stop to ask) and the log where you add yours. |
| `STATUS.md` | One table: task, state, owner, result file. Update it when a task changes state. |
| `results/` | One result file per finished task, named `<task>-<YYYY-MM-DD>[-<model>].md`. |

Older documents still valid as background: `docs/PROTOCOL.md`, `docs/FACTS.md`, `docs/models.md`, `docs/recon-web.md`, `docs/safe-write.md`, `docs/first-session-checklist.md`, `docs/hardware-test-v1.md` (H1 to H7 definitions), `docs/hardware-recon-checklist.md` (physical teardown background; its executable form is HW-15 to HW-17 here).

## Who can do what
| Task type | Who | Why |
|---|---|---|
| S0 to S11 | AI agent alone | Pure software. |
| HW tasks that say `Executor: HUMAN+AI` | A person with a badge runs the commands; the AI prepares a run sheet, reads the pasted output and updates the docs | A cloud sandbox has no Bluetooth adapter and cannot touch a badge. Do not claim you ran a hardware task unless a human gave you its output. |
| HW-15 to HW-17 physical | HUMAN only, with explicit written approval from the project owner | Battery, heat, soldering. The AI only prepares notes and analyses files the human supplies. |

If you are an AI and no human is present: finish all of S0 to S11, prepare the run sheets (HW-0), and stop. That is a complete, correct outcome. Do not invent hardware results.

## Hard rules (read before touching anything)
1. Static analysis only on the vendor app. Never install or run it yourself. A live capture of the vendor app on a phone is allowed only as task HW-1 and only after the owner approves that session.
2. Never commit the APK, XAPK, split APKs, decompiled output, native libraries, vendor assets, tokens, signed URLs, raw captures with personal data, full Bluetooth addresses, serial numbers or Wi-Fi passwords. `reports/` and `testmedia/` are git-ignored on purpose. Mask the last three bytes of any address.
3. Every write to a real badge goes through the safe-write guard (see `docs/safe-write.md`): 30 s minimum interval, identical payloads skipped, hard cap 50 per 24 h. Do not use `--no-safe-write` or `--force` unless a step says so. Each hardware task lists its write cost; the daily budget is in HW-0. Stop at the budget.
4. Never flash, erase or write to the badge's firmware or storage by any route other than the client's normal upload commands. No OTA, no Jieli UBOOT writes, no SPI writes. Reading only.
5. Do not retry a failing hardware step in a loop. One retry after a power cycle, then record and move on.
6. No emoji in any file. No hard-coded test counts in docs; say "run `pytest -q`".
7. Do not push to `main`. Use the branch you were given. Do not open a pull request unless asked.
8. If a step needs a person (hardware, login, approval, root) and nobody is available, mark it `blocked: needs human` in `STATUS.md` and continue with the next task.

## Assumption policy (how to avoid asking questions)
- Prefer the pre-made assumptions in `ASSUMPTIONS.md`. If your situation is not covered, choose the option that is (a) reversible, (b) does the least writing to the badge, and (c) is easiest to falsify. Add a line to the log in `ASSUMPTIONS.md`: id, what you assumed, why, how a later test would prove it wrong, who is affected.
- Never stop for a question about something a search, a grep or a default can settle.
- Stop and ask only for: physical access, permission for a live session, a destructive step, a legal question, a credential, or a command that would exceed the write budget.
- A wrong assumption is acceptable if it is written down and cheap to reverse. An unrecorded assumption is a defect.

## Result file template (copy for each finished task)
```
# <task id>: <title>
date / time zone:           executor (name or agent):
model and firmware / app version (hardware tasks):
branch and commit:
commands run (exact, in order):
raw outputs (paths or pasted, redacted):
measured values:
result: PASS | FAIL | PARTIAL | BLOCKED
evidence tag for each finding: [C] [V] [H] [W] [I] [U]
assumptions made (ids from ASSUMPTIONS.md):
docs or code changed (paths):
new problems (also appended to docs/problem_solution.md):
next task suggested:
```

## Where things get recorded
| What | Where |
|---|---|
| Task result | `docs/tasks/results/<task>-<date>[-<model>].md` and a row in `STATUS.md` |
| A problem you hit | New numbered entry at the bottom of `docs/problem_solution.md` (date, phase, problem, cause, solution or Status: Unsolved) |
| Something that needs fixing | `fixes.md` under Open |
| A value sources disagree on | `docs/FACTS.md` only; other docs link to it |
| A byte-level claim confirmed or corrected | `docs/PROTOCOL.md`, with the tag changed and the source named |
| First-contact reports | `reports/first-contact-*.md` (git-ignored); then `python tools/aggregate_reports.py` updates `docs/compatibility-matrix.md` |

## Things that trip people up (from the problem log)
| Symptom | Cause | Fix |
|---|---|---|
| Badge not found by scan | It only advertises on its pairing screen (QR code); the vendor phone app may hold the connection (one central at a time) | Show the pairing screen, close the phone app, toggle phone Bluetooth off, retry with `scan --all` |
| `scan` prints a bare errno / no adapter | No BlueZ or no Bluetooth hardware (also true in every cloud sandbox) | Run on a machine with an adapter; Linux needs the `bluetooth` service |
| macOS shows UUIDs, not MAC addresses | CoreBluetooth hides addresses | Use the UUID that `scan` prints as `--address` |
| Windows: connection fails after pairing in OS settings | The badge uses application-level binding, not OS pairing | Remove the badge from Windows paired devices |
| Second identical send prints "skipped" | Delta skipping: same payload hash as the last upload | Intended. For tests that need a rewrite use `--no-delta` (and wait out the interval) |
| Send refused, exit code 2 | Minimum interval (30 s) or daily cap (50) | Wait; check `rebeambox uploads`; never raise the cap without owner approval |
| Picture black on NIJI/NANO | Type 6 (album/IMB) stills reported black; type 5 container works [W] | Default is type 5; `--nn20-still album` is the diagnostic |
| `--model` seems to change the size | It must not: size is what the badge reports, else nn20 368 / BadgeSdk 360 / Wi-Fi 360; only `--size` overrides (problem 58) | Report any deviation as a bug |
| Tests skip | Optional packages or native libs absent (unicorn, `libjl_auth.so`, ffmpeg, Thai font) | Expected. Do not "fix" by committing the library |
| jadx killed / stalls at about 75 percent | Out of memory on small machines | `--max-heap 3g` (default on small RAM) |
| `d.apkpure.com` unreachable | Cloud network policy | `--local-file`, or ask the owner to allow the host |
| Shell dies after `rm -rf` of a directory you were in | cwd deleted | `cd` out first |
| Docs fail the repo-rules lint | Emoji, analytics host name, or non-local URL in code | Run `python tools/check_repo_rules.py`; vendor hostnames are allowed in docs only |
| Test counts drift in docs | Hard-coded numbers | Never write counts |
