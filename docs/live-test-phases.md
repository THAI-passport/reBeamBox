# Live test phases (real badge)

Task brief for the agent running the first live tests on a real badge. The phases are written all at once, but they run **one at a time**: after each phase, stop, send the phase report to the owner, and wait. The owner and the planning model may rewrite later phases based on what you found. Never start the next phase on your own.

Related docs (read before Phase 0): [first-session-checklist.md](first-session-checklist.md), [hardware-test-v1.md](hardware-test-v1.md) (tests H1 to H7), [safe-write.md](safe-write.md), [PROTOCOL.md](PROTOCOL.md), [models.md](models.md), [wifi-protocol.md](wifi-protocol.md), [problem_solution.md](problem_solution.md).

## Batch mode (3 checkpoints instead of 9)

Phases can be grouped into batches. Run a whole batch, then report once with one report block per phase. Inside a batch, continue to the next phase only if the gate passes; otherwise stop the batch and report.

| Batch | Phases | Gate to continue inside the batch | Why grouped |
| :--- | :--- | :--- | :--- |
| A | P0, P1, P2, plus P8 step 1 (touch, NIJI only) | P0 tests green; P2 transport identified | No rebeambox writes, nothing to tune between them |
| B | P3, P4, P5 | P3 shows the picture; in P4 at least one still mode works; in P5 stop at the first freeze | All writes on the one transport P2 chose; failures follow the stop rules already in each phase |
| C | P6, P7, P8 wrap-up | P6 no 2 failures in a row; P7 only if an SSID was seen | Speed and Wi-Fi measurements; wrap-up needs all results |

Not concurrent: the badge accepts one central at a time, so the vendor app, nRF Connect and rebeambox never run at the same moment. P1 (vendor app) and P0 (computer only) can run side by side. Running all phases in one go is not recommended: if P3 fails, P4 to P7 just burn flash writes on a broken path.

## Rules for the agent

1. **One phase per run.** Finish the phase, fill its report, stop. If a stop condition triggers, stop right there and report what you have.
2. **Do not change code** in `rebeambox/` during a phase. If something looks wrong, record it; fixes are made between phases after review. The one exception is a scratch copy where a phase says so.
3. **Log every problem** in [problem_solution.md](problem_solution.md) as a new numbered entry at the bottom (next number after the last one), in the existing format: date, phase (`Live P<n>`), problem, cause (or "unknown"), solution or `Status: Unsolved` with what was tried. Small problems count too (a missing tool, a permission prompt, a flag that did not exist).
4. **Record everything.** Every command with `2>&1 | tee live/p<n>/<step>.txt`. A failure with a log beats a success without one. Photo or short video of the badge after every write.
5. **Write budget.** Each image, GIF, video or text send is a flash write. Stay inside the budget for each phase. Do not use `--force` or `--no-safe-write` unless the phase says so. Check the counter with `rebeambox uploads` at the start and end of every phase.
6. **Redact** the last 3 bytes of Bluetooth addresses, Wi-Fi passwords and serial numbers in anything you send back.
7. **Do not guess.** If the output does not match what this brief expects, write down what you saw, not what you think it means. Mark claims as Observed or Inferred.
8. **One central at a time.** Close the vendor app (force stop) whenever rebeambox talks to the badge, and the other way round.

## Skills to use

| Skill | When | Why |
| :--- | :--- | :--- |
| `repo-builder` | Start of Phase 0 | Orient in the repo: find the real install, test and run commands and conventions instead of guessing them. |
| `run` | Phases 2 to 7, when driving the CLI | Run the app and confirm behaviour in the real program, not only in tests. |
| `grilling` (optional, owner side) | Between phases | Stress-test the plan for the next phase against the results before rewriting it. |

If a skill is not available to you, do the same steps manually and note it in the report.

## Directory layout for results

```
live/
  p0/ ... p8/          one folder per phase, all logs, captures, photos
  media/               the test media (Phase 0 creates it)
```
Add `live/` to your local ignore (`.git/info/exclude`), never commit captures.

---

## Phase 0. Preflight (no badge contact)

- **Goal:** a working toolchain and known-good test media before the badge is touched.
- **Rationale:** if tests or tools fail now, any later badge failure is ambiguous. Costs nothing, saves hours.
- **Write budget:** 0.
- **Steps:**
  1. Use `repo-builder` to orient. `git pull`, `git log -1 --oneline` (record the commit).
  2. `python -m venv .venv && source .venv/bin/activate && pip install -e .[test]`.
  3. `python -m pytest -q tests` (expect about 303 passed, 2 skipped). Record exact counts.
  4. `rebeambox --version`, `python -c "import bleak; print(bleak.__version__)"`, `ffmpeg -version | head -1`, OS version, Bluetooth adapter (macOS: `system_profiler SPBluetoothDataType | head -30`).
  5. Simulator dry run of the whole flow: `rebeambox probe --qualify --simulate nn20` and `--simulate badge`.
  6. Build `live/media/`: `photo.jpg` (any), `gradient.png` (360x360, labelled `TOP-LEFT` corner and a red arrow pointing up), `party.gif` (about 20 frames), `clip2.mp4 clip3.mp4 clip4.mp4 clip5.mp4 clip8.mp4 clip10.mp4` (generate with ffmpeg `testsrc2` showing a timer, e.g. `ffmpeg -f lavfi -i testsrc2=size=368x368:rate=15 -t 8 live/media/clip8.mp4`).
  7. Dry runs of every send type with `--dry-run live/p0/dry-<kind>.txt` for `--transport nn20`, `badge`, `wifi`. Record payload sizes.
  8. `rebeambox uploads` (expect empty).
- **Pass:** tests green, both simulations PASS, all dry runs produce files.
- **Stop if:** any test fails or a simulation fails. Report and wait.
- **Report:** fill the report block (end of this file) plus a table of tool versions and payload sizes.

## Phase 1. Vendor app reference capture (ground truth)

- **Goal:** a btsnoop capture of the vendor app sending one still and one animation.
- **Rationale:** every later byte comparison needs this. If our client fails, this capture tells us whether our bytes or our assumptions are wrong. Done before rebeambox so the badge is in a known factory-like state.
- **Write budget:** 2 (vendor app writes).
- **Steps:**
  1. Charge the badge above 50 percent. Record model printed on the box, the model selected in the app, app version, badge firmware version if shown.
  2. Android: Developer options, enable Bluetooth HCI snoop log, toggle Bluetooth off and on.
  3. In the vendor app: connect, send `photo.jpg`, wait for the badge to show it, then send `party.gif`. Note the wall-clock time of each action and what the badge showed.
  4. Pull the log (first-session-checklist.md step 1.3). Save as `live/p1/ref-<model>-<date>.btsnoop`.
  5. `python tools/replay_pcap.py live/p1/ref-*.btsnoop --out live/p1/extracted/ 2>&1 | tee live/p1/replay.txt`.
  6. Check the phone Wi-Fi list for an SSID containing `E-Badge`; record it (decides Phase 7).
- **Pass:** capture contains ATT writes to the badge; replay tool extracts frames.
- **Stop if:** no capture can be pulled (record phone model and Android version, try the bugreport path, then stop).
- **Report:** advertised name seen by the app, which service handle was written (0x01F1 or RCSP), first 5 frames in hex, replay CRC and sequence results, Wi-Fi SSID yes/no.

## Phase 2. Passive recon (read-only)

- **Goal:** name, services, MTU, transport decision, read-only handshake.
- **Rationale:** zero writes, so zero risk to flash, and it decides which transport every later phase uses.
- **Write budget:** 0.
- **Steps (H1):**
  1. Vendor app force stopped. Badge on its pairing screen.
  2. `rebeambox scan --all --timeout 15`, then `rebeambox scan --model <model> --timeout 15`.
  3. `rebeambox probe <ADDRESS> --json live/p2/gatt.json`.
  4. `rebeambox probe --qualify --model <model> --report-dir live/p2`.
  5. Optional cross-check: nRF Connect, export XML of the GATT table.
- **Pass:** qualify says PASS, transport identified (nn20 or badge).
- **Stop if:** badge not found with `--all`, or neither 0x01F0 nor the 0x9E/RCSP service exists. Do not write anything.
- **Report:** the first-contact report file, transport decision, MTU, manufacturer data, whether the model filter found it (if not, which name it used).

## Phase 3. First write: one still

- **Goal:** one picture on the badge from rebeambox.
- **Rationale:** smallest possible write that proves the full path (connect, framing, checksum, ack). Only one transport, the one Phase 2 chose, so a failure points at one code path.
- **Write budget:** up to 3.
- **Steps:**
  1. Start an HCI capture on the computer (macOS PacketLogger, Linux `sudo btmon -w live/p3/rb.btsnoop`).
  2. `rebeambox send-image live/media/gradient.png --model <model> --address <ADDRESS>` (auto transport).
  3. If it fails: power-cycle, retry once with the transport forced (`--transport nn20` or `badge`).
  4. If still failing: stop. Do not try other encodings, that is Phase 4.
  5. `rebeambox uploads`.
- **Pass:** gradient visible, correctly oriented, within 30 s.
- **Stop if:** badge reboots, freezes, or two attempts fail.
- **Report:** photo, time to finish, console output, orientation and crop, whether circle or square, capture file, diff of our first 5 frames vs Phase 1 frames (lengths and opcodes).

## Phase 4. Still encoding and geometry matrix

- **Goal:** confirm which still mode and size are right for this model (H2, and H3 if BadgeSdk).
- **Rationale:** the code default (type 5 container) comes from third-party reports; the app code uses type 6 album. Only hardware settles it. Size 360 vs 368 decides the crop.
- **Write budget:** up to 6, at least 30 s apart (the safe-write default enforces this, do not override).
- **Steps:**
  1. nn20: `--nn20-still gif` (type 5) and `--nn20-still album` (type 6), power-cycle between them.
  2. With the working mode: `--size 360`, `--size 368`, `--square`.
  3. BadgeSdk only: watch the log for the auth exchange (challenge, reply, `pass`). Skip the wrong-key test unless the owner says the badge is a spare.
  4. Send the same image twice in a row without changes: expect the second send to be skipped by the delta rule (no write). Record.
- **Pass:** one mode shows the image correctly; the delta skip works.
- **Report:** a table mode x size -> result (ok, black, cropped, garbled, nothing), photos, recommended `still_mode` and size for `rebeambox/models.py` (do not edit it).

## Phase 5. Animation, video, text, length limit

- **Goal:** GIF, video and text work, and the real video length limit (H7).
- **Rationale:** separate from stills because they use another container and larger payloads; the length limit is disputed (3 s retail vs 10 s app trimmer vs 5 s Niji).
- **Write budget:** up to 10.
- **Steps:**
  1. `send-gif live/media/party.gif`; `send-text "Test" --model <model>`.
  2. Videos in increasing length: 2, 3, 4, 5, 8, 10 s with `send-video clipN.mp4 --max-seconds N --fps 15`. Before and after each, record `freespace` from the status output if printed.
  3. Film each playback, count the timer seconds shown before it loops.
- **Pass:** longest fully played clip and shortest failing one identified.
- **Stop if:** freeze or reboot. Power-cycle, record clip length and size, do not go longer.
- **Report:** table clip length -> transfer ok, seconds played, loop yes/no, bytes, transfer time; text readability; recommended `video_max_s`.

## Phase 6. BLE throughput and reliability

- **Goal:** real transfer speed and failure rate (H4).
- **Rationale:** the streaming plan depends on these numbers; repetition exposes intermittent drops a single send hides.
- **Write budget:** up to 10. Note: back-to-back sends need `--min-interval-s 5` (allowed here only). Do not use `--force`.
- **Steps:**
  1. `time rebeambox send-gif live/media/party.gif --model <model> --address <ADDRESS> --min-interval-s 5 --no-delta` five times.
  2. Repeat five times with `--packet-interval-ms 10` only if all first five succeeded.
  3. Compute bytes per second from the dry-run payload size.
- **Pass:** no disconnects. Speed is recorded, not judged (prediction: nn20 no-ack about 22 KB/s, ack about 9 KB/s, BadgeSdk 10 to 30 KB/s).
- **Stop if:** 2 failures in a row.
- **Report:** per run: seconds, bytes, KB/s, retries, any GetPacketFail, ack mode, MTU.

## Phase 7. Wi-Fi (only if Phase 1 or 2 found an E-Badge SSID)

- **Goal:** Wi-Fi upload and camera-mode streaming fps (H5).
- **Rationale:** Wi-Fi camera mode is the only live (non-flash) path, which matters for streaming without wear.
- **Write budget:** 2 still uploads; streaming frames are not counted as flash writes if camera mode is confirmed.
- **Steps:** follow hardware-test-v1.md H5: join SSID, `nmap -Pn -p 80,8080 192.168.8.1`, `tcpdump` capture, `send-image --transport wifi`, `stream clip8.mp4 --fps 2`, then `--fps 3`. Do not edit `MIN_FRAME_INTERVAL` in this phase.
- **Pass:** image shows; stream gets the 0x007B reply; 3 fps smooth.
- **Report:** password needed y/n, IP lease, open ports, reply bytes, fps where stutter begins, capture file. If skipped, say "skipped: no SSID".

## Phase 8. Touch events (NIJI only) and wrap-up

- **Goal:** check for touch notifications (H6), then a final summary.
- **Rationale:** cheap, read-only, and closes the last open protocol question. Wrap-up turns findings into concrete change requests.
- **Write budget:** 0.
- **Steps:**
  1. NIJI only: nRF Connect, enable all notifications, tap, swipe, long-press 10 times each, export log. Other models: skip, write "skipped".
  2. `rebeambox uploads` final count.
  3. Write `live/SUMMARY.md`: per phase one line PASS/FAIL/PARTIAL/SKIPPED, the list of suggested code and doc changes (file, current value, proposed value, evidence), and the list of problem_solution.md entries added.

---

## Report block (send this after every phase)

```
LIVE TEST REPORT, Phase <n>: <name>
date / time zone:            repo commit:
model (box / app):           firmware / app version:
computer OS, Python, bleak:  adapter:
writes used / budget:        uploads counter before -> after:

RESULT: PASS | PARTIAL | FAIL | STOPPED (which stop condition)

commands run (in order, with log file name):
observed (facts only):
inferred (your interpretation, labelled):
measured values (table if more than 3):
photos / captures (file names):
problem_solution.md entries added (numbers):
questions for the owner before the next phase:
```
