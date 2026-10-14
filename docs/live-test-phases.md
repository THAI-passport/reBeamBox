# Live test phases (real badge)

Task brief for the agent running the first live tests on a real badge. Phases run in batches (below); after each batch, stop, send the reports to the owner and wait. Later phases may be rewritten from the results. Never start the next batch on your own.

Read first: [AGENTS.md](../AGENTS.md) (binding rules, safety with real badges), [FACTS.md](FACTS.md) (disputed values), [first-session-checklist.md](first-session-checklist.md), [hardware-test-v1.md](hardware-test-v1.md) (H1 to H7), [safe-write.md](safe-write.md), [PROTOCOL.md](PROTOCOL.md), [wifi-protocol.md](wifi-protocol.md), [problem_solution.md](problem_solution.md), [steps.md](steps.md).

## Branch

Run from `docs/grok-improvements` only after it contains `origin/main`, `origin/feat/steps-log` and `origin/integration/2026-10-12` (check: `git merge-base --is-ancestor origin/main HEAD && echo ok`, same for the other two). Those carry the `--model` size fix (problem 58), the daily write cap (59), the fail-closed ledger and OTA block (77) and the capture scrubber. Record `git log -1 --oneline` in every report.

## Rules for the agent

1. **One batch per run.** Inside a batch, continue only if the gate passes; on a stop condition, stop and report.
2. **No code changes** in `rebeambox/` during a run. Record, do not fix.
3. **Logs, per AGENTS.md:**
   - Every step and decision: append to [steps.md](steps.md) (step + rationale).
   - Every problem, even small: new entry in [problem_solution.md](problem_solution.md) numbered **last existing number + 1** (check with `grep "^## [0-9]" docs/problem_solution.md | tail -1`; never reuse a number). Phase field: `Live P<n>`.
4. **Redact before writing to disk**, not only in reports (the repo is public). Bluetooth addresses: last 3 bytes as `XX`. No Wi-Fi passwords, serials or phone numbers in any file under the repo. Raw captures stay in `live/` (git-excluded); anything derived from a capture goes through `python tools/scrub_capture.py <in> -o <out> --mask <serial>` before it lands in `docs/`, `reports/` or `fixtures/`. `probe --qualify` redacts by default; never pass `--no-redact`.
5. **Write budget.** Every image, GIF, video or text send is a flash write. The guard (30 s minimum interval, delta skip, hard cap 50 per 24 h, warning at 40) stays on. Never use `--force`, `--no-safe-write` or `--max-per-day`. The only allowed guard flags are the ones a phase names. Check `rebeambox uploads` at the start and end of each phase.
6. **Owner confirms the screen.** A clean exit or an ACK does not prove the picture rendered. For every write the pass condition needs the owner's answer to: shown? oriented? cropped? garbled? Ask, wait for the answer, record it with a photo.
7. **Time every transfer** (`time ...`) and keep the console log: throughput comes from the P3 to P5 sends, not from extra writes.
8. **One central at a time.** Force stop the vendor app and disconnect nRF Connect before rebeambox talks to the badge.
9. **Do not guess.** Separate Observed from Inferred. Unexpected reply: stop, record, do not retry in a loop.
10. Results go in `live/p<n>/` (in `.git/info/exclude`). Log every command with `2>&1 | tee live/p<n>/<step>.txt`.

## Skills

| Skill | When | Why |
| :--- | :--- | :--- |
| `repo-builder` | Start of each run | Picks up AGENTS.md rules, real commands and the current last problem number instead of trusting this file. |
| `run` | P1 to P6 | Drive the real CLI and confirm behaviour on the device, not only in tests. |
| `grilling` (owner side, optional) | Between batches | Stress-test the next batch against the results before running it. |

If a skill is unavailable, do the steps by hand and say so in the report.

## Batches

| Batch | Phases | Gate inside the batch | Writes (max) |
| :--- | :--- | :--- | :--- |
| A | P0, P1, P2 | P0 green; P1 finds the badge and a transport | 2 (vendor app, P2) |
| B | P3, P4, P5 | P3 shown (owner); P4 one still mode works; P5 stops at the first freeze | 3 + 5 + 5 = 13 |
| C | P6, P7, P8 | P6 no 2 failures in a row; P7 only with an SSID and a second network | 3 + 1 = 4 |

Total rebeambox writes at most 18, well under the 40/day warning. Run batch B and C on different days if B used its full budget plus retries.

---

## P0. Preflight (no badge contact). Writes: 0

- **Rationale:** a broken toolchain makes every later badge failure ambiguous.
- **Steps:** branch check (above); `python -m venv .venv && source .venv/bin/activate && pip install -e '.[test]'` (quotes needed in zsh, problem 78); `python -m pytest -q`; versions: `rebeambox --version`, `python -c "import importlib.metadata as m; print(m.version('bleak'))"` (problem 79), `ffmpeg -version | head -1`, OS, adapter; `rebeambox probe --qualify --simulate nn20` and `--simulate badge`; `python tools/make_test_media.py --out live/media`; dry runs of image, GIF, video and text for `--transport nn20`, `badge`, `wifi` into `live/p0/`, record payload sizes; `rebeambox uploads`.
- **Pass:** tests green (record counts in the report, not in docs), both simulations PASS, dry runs written.
- **Stop if:** any of those fail.

## P1. Read-only recon (+ touch listen). Writes: 0

- **Rationale:** zero risk to flash; proves the host Bluetooth stack sees the badge and decides the transport before any manual capture work. Runs before the vendor capture so a host-side problem is found first.
- **Steps (H1):** vendor app force stopped, badge on its pairing screen. `rebeambox scan --all --timeout 15`; `rebeambox scan --model <model> --timeout 15`; `rebeambox probe <ADDRESS> --json live/p1/gatt.json`; `rebeambox probe --qualify --model <model> --report-dir live/p1`. Record the status JSON fields the badge reports (`size`, `freespace`, `time_mode`) next to what `--model` would assume.
- **Touch (NIJI only, H6):** nRF Connect, enable every notifiable characteristic, tap, swipe, long-press 10 times each, export the log. Other models: "skipped".
- **Pass:** qualify PASS, transport identified (nn20 or badge).
- **Stop if:** not found with `--all`, or neither 0x01F0 nor the 0x9E/RCSP service. Write nothing.

## P2. Vendor app reference capture. Writes: 2 (vendor app)

- **Rationale:** ground truth bytes for every comparison later; if our client fails, this tells us whether bytes or assumptions are wrong.
- **Steps:** Android HCI snoop on, Bluetooth off and on; in the app send `photo.jpg`, wait for it to show, then a GIF; note wall-clock times and what the badge showed. Pull the log to `live/p2/ref-<model>-<date>.btsnoop` (first-session-checklist.md 1.3). `python tools/replay_pcap.py live/p2/ref-*.btsnoop --out live/p2/extracted/`. Check the phone Wi-Fi list for `E-Badge*`.
- **Pass:** capture has ATT writes to the badge; replay extracts frames.
- **Report:** handle written (0x01F1 or RCSP), first 5 frames as lengths and opcodes (scrubbed), CRC/sequence results, SSID yes/no.

## P3. First write: one still. Writes: max 3

- **Rationale:** smallest write that proves the full path, on the one transport P1 chose, so a failure points at one code path.
- **Steps:** start an HCI capture (macOS PacketLogger, Linux `sudo btmon -w live/p3/rb.btsnoop`). `time rebeambox send-image live/media/gradient_label.png --model <model> --address <ADDRESS>`. Owner confirms the screen. If it fails: power-cycle, retry once with `--transport nn20` or `badge` forced. Then stop.
- **Pass:** owner confirms the picture shown, oriented, within 30 s.
- **Stop if:** reboot, freeze, or two failures.
- **Report:** owner's answer + photo, seconds, bytes, our first 5 frames vs P2 frames (lengths, opcodes).

## P4. Still encoding and geometry. Writes: max 5

- **Rationale:** type 5 container (default, third-party reports) vs type 6 album (app code); 360 vs 368 decides the crop. Only the screen settles it.
- **Steps:** nn20: the default (type 5) was P3; send `--nn20-still album` (type 6) once. With the mode that worked, try the other size of 360/368 (P1 told you which one the badge reports; the default now follows the badge), then `--square` once if the circle crops the labels. Then send the last image again unchanged: expect the delta rule to skip it (no write); record. BadgeSdk badges: replace with the auth check from H3 (a), log challenge/reply/`pass`; no wrong-key test.
- **Pass:** owner confirms one mode and size render correctly; delta skip observed.
- **Report:** table mode x size -> owner's verdict (ok, black, cropped, garbled, nothing), seconds, bytes; recommendation for `still_mode` and size (do not edit code).

## P5. GIF, text, video length boundary. Writes: max 5

- **Rationale:** other container, bigger payloads; length limit disputed (FACTS.md: 3 s retail, 5 s NIJI trimmer, 10 s app default). Boundary search instead of a sweep to save writes.
- **Steps:** `send-gif live/media/party.gif`; `send-text "Test" --model <model>`. Video, each `--max-seconds N --fps 15`, owner counts the on-screen timer before it loops:
  1. 5 s. Plays fully: go to 3. Fails or truncates: send 3 s, stop.
  2. 10 s. Plays fully: limit at least 10, stop. Fails: send 8 s only if budget left.
- **Pass:** the longest clip that plays fully and the shortest that fails (or "at least 10 s").
- **Stop if:** freeze or reboot; power-cycle, record length and bytes, go no longer.
- **Report:** table length -> transfer ok, seconds played, loop, bytes, transfer seconds, `freespace` before/after.

## P6. BLE throughput check. Writes: max 3

- **Rationale:** P3 to P5 already give timings over several payload sizes. This adds only a short repeat to see drops on back-to-back sends.
- **Steps:** compute KB/s for every P3 to P5 transfer first (payload bytes from P0 dry runs / seconds). Then 3 runs of `time rebeambox send-gif live/media/party.gif --model <model> --address <ADDRESS> --no-delta --min-interval-s 10` (both flags are documented CLI options of the guard; the hard cap stays on). Different image each run is not needed: `--no-delta` sends the full payload.
- **Pass:** no disconnects. Speed recorded, not judged (prediction: nn20 no-ack ~22 KB/s, ack ~9 KB/s, BadgeSdk 10 to 30 KB/s).
- **Stop if:** 2 failures in a row.

## P7. Wi-Fi (only if an `E-Badge*` SSID was seen). Writes: max 1 + stream test

- **Rationale:** camera mode is the only possibly flash-free live path; that claim must be proven before any streaming loop.
- **Pre-check (stop if it fails):** joining the badge AP drops internet on that adapter. The agent must stay connected: use Ethernet or USB tethering for internet and Wi-Fi for the badge, or a second USB Wi-Fi adapter, or have the owner run P7 by hand from the commands below and paste the outputs. Confirm with `route get default` (macOS) / `ip route` (Linux) that the default route is not the badge.
- **Steps:** join the SSID (wifi-protocol.md 2), record whether a password was needed (do not write it down); `nmap -Pn -p 80,8080 192.168.8.1` once; `sudo tcpdump -i <wlan> -w live/p7/wifi.pcap host 192.168.8.1`.
  1. Persistence check: `rebeambox send-image live/media/gradient_label.png --transport wifi` (1 write). Owner confirms shown. Power-cycle: if the image is still there after reboot, uploads are persistent (flash).
  2. Camera mode: `rebeambox stream live/media/clip5.mp4 --fps 2 --max-seconds 5`. Expect the 0x007B reply. Then power-cycle: if the last streamed frame survives the reboot, camera mode writes to flash: **stop, do not run higher fps**, report.
  3. Only if frames do not survive: `--fps 3`, 10 s. Do not edit `MIN_FRAME_INTERVAL`.
- **Report:** password needed y/n, IP lease, open ports, reply bytes, persistence results for 1 and 2, fps where stutter begins.

## P8. Wrap-up. Writes: 0

- `rebeambox uploads` final count.
- `live/SUMMARY.md`: one line per phase PASS/FAIL/PARTIAL/SKIPPED; proposed code and doc changes (file, current value, proposed value, evidence tag `[H]` with the report that proves it); list of problem_solution.md entries and steps.md lines added.

---

## Report block (one per phase, sent at the end of each batch)

```
LIVE TEST REPORT, Phase <n>: <name>
date / time zone:            repo commit:
model (box / app / badge-reported):   firmware / app version:
computer OS, Python, bleak:  adapter:
writes used / budget:        uploads counter before -> after:

RESULT: PASS | PARTIAL | FAIL | STOPPED (which stop condition) | SKIPPED

commands run (in order, log file):
owner screen confirmations (per write):
observed (facts only):
inferred (labelled):
timings (bytes, seconds, KB/s):
files (photos, scrubbed captures):
problem_solution.md entries added:
steps.md lines added:
questions before the next batch:
```
