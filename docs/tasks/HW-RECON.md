# Hardware recon tasks (HW-0 to HW-17)

Needs a physical badge. Read `README.md` first (rules, who does what, assumption policy, result template) and `docs/safe-write.md`. Test definitions H1 to H9 map as: H1 = HW-2, H2 = HW-5, H3 = HW-14, H4 = HW-9, H5 = HW-12, H6 = HW-13, H7 = HW-10, H8 = HW-7, H9 = HW-8 (the H-numbers come from `docs/hardware-test-v1.md`).

Executor key: `HUMAN+AI` = a person runs commands on a machine with Bluetooth (cloud sandboxes cannot), the AI prepares the run sheet, interprets pasted output and updates docs. `HUMAN` = only a person, only with the owner's written approval. An AI that has no human available prepares HW-0 and stops (README).

Order for day 1: HW-0, HW-2, HW-4, HW-5, HW-6, HW-7, HW-8, then HW-9 to HW-11 as time allows, plus HW-3/HW-12 or HW-13/HW-14 if the discovery results call for them. HW-1 can come first or last (see its note). HW-15 and HW-16 are free and safe, do them while the badge charges. HW-17 is a separate, later decision.

Conventions in the commands below: `ADDR` is the badge address (Linux/Windows MAC address, macOS UUID); keep it in a shell variable and never write it into a committed file. `MODEL` is `nikko`, `nano` or `niji` (assumption A1). `$` lines are commands. After every send wait at least 35 s before the next one (minimum interval 30 s); after each write photograph the badge.

---
## HW-0. Run sheet, approvals, write budget
Executor: AI (preparation) then HUMAN confirms.
1. Ask the owner (or read the request) for: model on the box, whether the vendor phone app may be used for a capture (approval for HW-1), whether opening the badge is allowed (HW-17, default no), machine and OS with Bluetooth, whether ffmpeg is installed. If nobody answers, apply `ASSUMPTIONS.md` (A1, A10) and skip HW-1 and HW-17.
2. Prepare the machine: `python tools/make_test_media.py --out testmedia`; `pip install -e ".[test]"`; `python -m pytest -q` green; `rebeambox --version`.
3. Charge the badge above 50 percent. Put the vendor phone app away (close it, toggle the phone Bluetooth off).
4. Fix the write budget for the day. The guard allows 50 writes per rolling 24 h per badge; the plan stays at or below 25 to leave margin for retries (a failed attempt is not counted by the guard but may still have touched flash):
| Task | Writes | Notes |
|---|---|---|
| HW-5 | 2 | type 5, type 6 |
| HW-6 | 3 | sizes 360, 368, square |
| HW-7 | 3 | noise, noise again, gradient |
| HW-9 | 5 | animation timing |
| HW-10 | 6 | clips 2, 3, 4, 5, 8, 10 s; stop at first failure |
| HW-11 | 1 | text |
| HW-14 | 2 | only if BadgeSdk transport |
| Total | up to 22 | `rebeambox uploads` shows the counter at any time |
5. Write a run sheet: a plain text file `docs/tasks/results/run-sheet-<date>.md` listing, in order, the exact commands of the tasks you will run with `ADDR` and `MODEL` as variables, a column for the human to tick, and a place to paste outputs. Do not put the real address in it.
Pass: run sheet written; approvals recorded in the result file.

## HW-1. Reference capture with the vendor app
Executor: HUMAN+AI. Needs owner approval (live vendor-app session, assumption A10). Android phone with the vendor app, Developer options.
Why: the vendor app is the ground truth for what a working session looks like; it settles transport, framing and pacing disputes.
Best done after HW-2 (so you know what to look for) but before any of your own writes, because the badge may behave differently once you have written to it. Either order is acceptable if recorded.
1. On the phone: Developer options, enable Bluetooth HCI snoop log; toggle Bluetooth off and on to start a fresh log.
2. Put the badge on its pairing screen. In the vendor app select the model, connect, send exactly one still image and one short animation. Write down wall-clock times and what the badge showed.
3. Retrieve the log: `adb pull /sdcard/btsnoop_hci.log` (path varies; on Android 12+ use `adb bugreport` and look under `FS/data/misc/bluetooth/logs/`; Samsung: `*#9900#`). Save as `ref-<model>-<date>.btsnoop` OUTSIDE the repository (captures contain addresses).
4. Decode: `python tools/replay_pcap.py ref-<model>-<date>.btsnoop --out /tmp/ref` (also reads `.pcap`/`.pcapng`). Read the summary: transport used, control frames, checksum or sequence errors, the payload file it extracted.
5. Compare with `docs/PROTOCOL.md`: frame headers, counts, checksums, status JSON, pacing (inter-packet gap, ACK batch size), MTU. Every difference is a finding. Tag confirmed items `[H]`.
Pass: capture decoded and compared. Fail: no capture produced (adb, HCI log not enabled) - record and continue; the other tasks do not depend on it.
Record: result file with the comparison table; sanitised excerpts only.

## HW-2. Scan and qualify (H1)
Executor: HUMAN+AI. Writes: 0.
1. Badge on its pairing screen (QR code and "scan to download"). If the vendor instructions say to press the Bluetooth button once, do it.
2. `$ rebeambox scan --all --timeout 15 | tee scan-all.txt` then `$ rebeambox scan --model MODEL --timeout 15`. Expect a device named `E-badge` or `Nikko-badge(BLE)` (or `NEO...`, `B-Device...`). If nothing: see the troubleshooting table in `README.md`; try `--name <prefix>`; try once more after toggling the badge off and on. Not found after that: mark BLOCKED, record scan output, stop the hardware track.
3. Read-only qualification: `$ rebeambox probe --qualify --model MODEL --timeout 15 --wait 5`. It scans, connects, reads GATT, negotiates MTU, decides the transport, listens for the status JSON, writes `reports/first-contact-<timestamp>.md` (addresses masked, git-ignored).
4. Full GATT dump for the record: `$ rebeambox probe ADDR --json gatt-MODEL.json` (keep outside git or redact).
5. Read the report. Record: advertised name, services, MTU, transport decision, status JSON fields (`size`, `freespace`, `allspace`, `time_mode`, `type`, `devname`, `brand`).
Interpretation:
| Observation | Meaning | Next |
|---|---|---|
| Service 0x01F0 with 0x01F1 and 0x01F2 | nn20 (assumption A2 holds) | Continue with `--transport nn20` implied |
| Services C2E6FD00... and 0xAE00 | BadgeSdk (Jieli RCSP) | Use `--transport badge`; plan HW-14; update A2 |
| Both families | Record both; try nn20 first | Note which answers |
| Neither | Unknown stack | Stop writes; run HW-3 and HW-1; record everything |
| Status JSON received | Note `freespace` as F0 (KB) | Used by HW-7 |
| No status JSON | Report says it may need a write to wake it | Not a failure; read status after the first write (log line `badge status:`) |
| MTU 23 | Platform did not negotiate | Record OS and adapter; throughput will be low (HW-9) |
Update: run `python tools/aggregate_reports.py` (updates `docs/compatibility-matrix.md`), `docs/FACTS.md` section 3 (transport) with `[H]`, `docs/models.md` section 7 open items.
Pass: transport identified and the badge answered. Partial: identified, silent. Fail: not found or no known service.

## HW-3. Wi-Fi presence survey
Executor: HUMAN+AI. Writes: 0. Independent of BLE results.
1. With the badge on (pairing screen and also its normal screen), list Wi-Fi networks on a phone or computer. Look for an SSID containing `E-Badge` or `Nikko`.
2. If none: record "no access point" (assumption A3 holds, consistent with the Bluetooth-only FCC filing [W]) and mark HW-12 `skipped: not applicable`.
3. If found: note open or protected. Do not guess passwords. Join if open or if the vendor documentation gives one. Then `$ ip addr` / `$ ip route` (Linux), `ifconfig` / `netstat -rn` (macOS), `ipconfig` (Windows): expect 192.168.8.x with gateway 192.168.8.1. `$ curl -sI --max-time 5 http://192.168.8.1:8080/` and `nmap -Pn -p 80,8080 192.168.8.1` once.
Pass: yes/no answer with evidence.

## HW-4. Dry runs
Executor: AI or HUMAN. Writes: 0. Proves the files you will send, and gives payload sizes for the budget.
```
$ rebeambox send-image testmedia/gradient_label.png --model MODEL --transport nn20 --dry-run dry-nn20.txt
$ rebeambox send-image testmedia/gradient_label.png --transport badge --dry-run dry-badge.txt
$ rebeambox send-image testmedia/noise.png --model MODEL --transport nn20 --dry-run dry-noise.txt
```
Keep `dry-*.txt` and `dry-*.txt.payload` for comparison with captures. Pass: exit 0 and payload files exist. Note the payload sizes (noise is the large one, used in HW-7).

## HW-5. Still container test (H2)
Executor: HUMAN+AI. Writes: 2. Needs HW-2 done (nn20 transport). Purpose: assumption A5 (type 5 shows, type 6 may show black).
1. `$ rebeambox send-image testmedia/gradient_label.png --model MODEL --nn20-still gif --address ADDR 2>&1 | tee hw5-type5.txt` (type 5, one-frame container; this is the default). Wait for it to finish. Photograph the screen. Note what shows.
2. Wait 35 s. `$ rebeambox send-image testmedia/gradient_label.png --model MODEL --nn20-still album --address ADDR 2>&1 | tee hw5-type6.txt` (type 6, IMB). Photograph.
3. Power-cycle only if the badge shows an error or hangs.
Interpretation:
| Type 5 | Type 6 | Meaning | Action |
|---|---|---|---|
| shows | black or nothing | A5 holds | none; tag FACTS/models `[H]` |
| shows | shows | both work | keep default 5; note type 6 works for this model |
| black | shows | A5 wrong for this model | set `still_mode` to `album` in `rebeambox/models.py` for MODEL, add a test, update `docs/models.md` section 5, `docs/PROTOCOL.md` |
| nothing | nothing | something else is wrong | go to HW-6 (size), compare with HW-1 capture; check `hw5-*.txt` for errors, status lines and `GetPacketFail` |
Record: photos (no addresses in view), the `badge status:` lines, elapsed time.

## HW-6. Picture size and shape
Executor: HUMAN+AI. Writes: 3. Purpose: settle 360 versus 368 and orientation (`docs/FACTS.md` section 2).
Use the image type that worked in HW-5 (default type 5). `gradient_label.png` has TL, TR, BL, BR labels at the corners and a cross in the centre.
```
$ rebeambox send-image testmedia/gradient_label.png --model MODEL --size 360 --address ADDR
(wait 35 s)  $ rebeambox send-image testmedia/gradient_label.png --model MODEL --size 368 --address ADDR
(wait 35 s)  $ rebeambox send-image testmedia/gradient_label.png --model MODEL --square --address ADDR
```
For each photograph the screen. Record: is TL at the top-left, is the picture mirrored or rotated, is the cross centred, where is the circle cut, any shifted or wrapped edge (a 1 or 2 pixel wrap indicates a wrong width), the size the badge reported in the status JSON.
Decision: if one size is clean and the other shifted, FACTS.md section 2 gets `[H]` for the clean one and the client default follows it; if rotated or mirrored, record and open a `fixes.md` item (do not invent a rotation flag without a second observation).

## HW-7. Free space and rewrite behaviour (H8)
Executor: HUMAN+AI. Writes: 3. Purpose: does a rewrite consume flash space (append or log style) or overwrite a slot? It decides the safe-write defaults (assumption A8).
Notes: the guard skips identical payloads; this test needs a deliberate rewrite, so the second send uses `--no-delta` (interval still enforced). Free space is read two ways: the `badge status:` log lines during a send, and a read-only `probe --qualify` afterwards (which reconnects and lists `freespace`). Units are KB as reported by the badge.
1. F0: `$ rebeambox probe --qualify --model MODEL --wait 5` and note `freespace` (run it twice; the two values should agree).
2. Write A: `$ rebeambox send-image testmedia/noise.png --model MODEL --address ADDR 2>&1 | tee hw7-a.txt`. The payload is about 83 KB (HW-4 shows the exact size). Then F1 via `probe --qualify`.
3. Wait 35 s. Write B (identical): `$ rebeambox send-image testmedia/noise.png --model MODEL --no-delta --address ADDR 2>&1 | tee hw7-b.txt`. Then F2.
4. Wait 35 s. Write C (different): `$ rebeambox send-image testmedia/gradient_label.png --model MODEL --address ADDR`. Then F3.
Interpretation (D1 = F0 - F1, D2 = F1 - F2, D3 = F2 - F3; compare with payload size P in KB):
| Result | Meaning | Action |
|---|---|---|
| D1 about P, D2 about 0, D3 about 0 or negative | One slot, overwritten | Wear per write is bounded to a slot; note it |
| D1 about P, D2 about P, D3 about +P/-P mix | Append or log allocation | Rewrites consume space and wear; keep the safe-write cap; document the number of rewrites until full |
| D1 about 0 | Free space is not updated live (RAM or lazy accounting) | Record; repeat F after power cycle (HW-8) |
| Values change in 4 KB steps | Page-granular accounting | Normal |
| F0 differs between two reads | Status is not stable; take the median | Record |
Update: `docs/safe-write.md` (limits and notes: replace the "Unknown" with the measured behaviour, tag `[H]`), `docs/FACTS.md`, `docs/problem_solution.md`.
Stop condition: if free space drops below 2 MB, stop writing and tell the owner; recovery is a vendor-app delete, not something to attempt from this client.

## HW-8. Power-cycle persistence (H9)
Executor: HUMAN+AI. Writes: 0 (uses the last write of HW-7).
1. Note what the badge shows now (the HW-7 gradient).
2. Power it fully off using the documented method on the box or the vendor instructions (do not open the case; if you do not know how, ask the owner and skip). Wait 10 s. Power on.
3. Observe whether the last picture appears and how long boot takes.
Interpretation: picture returns = non-volatile storage; default or blank = volatile or slot reset. Record `[H]` in `docs/FACTS.md`.

## HW-9. Throughput over BLE (H4)
Executor: HUMAN+AI. Writes: 5. Purpose: real bytes per second to confirm the streaming plan numbers (`docs/streaming-plan.md`).
1. Dry-run the animation to learn its payload: `$ rebeambox send-gif testmedia/party.gif --model MODEL --dry-run dry-gif.txt` -> payload size S bytes.
2. Five real sends, each at least 35 s apart, with `--no-delta` after the first so identical payloads are rewritten: `$ time rebeambox send-gif testmedia/party.gif --model MODEL --no-delta --address ADDR 2>&1 | tee hw9-N.txt`.
3. For each run record seconds T, throughput S/T, MTU, mode (`noack` or `ack` in the log, from `time_mode`), packet interval, retries, failures.
Pass criteria: no pass/fail on speed. Fail only on dropped transfers or disconnects; report failures out of 5. Compare with predicted bounds (nn20 no-ack about 22 KB/s, ack about 9 KB/s; `docs/streaming-plan.md`) and tag `[H]`. If it is far below, check the MTU first (23 means the platform did not negotiate).
If `GetPacketFail` appears: the client falls back to ACK batches automatically; record the line and the batch size. Do not change pacing constants without a capture (`--packet-interval-ms`, `--ack-batch-size` exist for experiments; log each experiment).

## HW-10. Animation and video limits (H7)
Executor: HUMAN+AI. Writes: up to 6. Needs ffmpeg and the clips from `make_test_media.py`.
For N in 2, 3, 4, 5, 8, 10 (stop at the first failure): `$ rebeambox send-video testmedia/clipN.mp4 --model MODEL --max-seconds N --fps 15 --address ADDR` (35 s apart). The client caps at the model default unless `--max-seconds` is given, hence the explicit flag.
Record per clip: transfer completed, badge plays all / loops / truncates, payload size, free space before and after, any freeze or reboot. If the client refuses with "not enough free space" that is a result (record F and payload).
Decision: the longest clip that plays fully sets `video_max_s` in `rebeambox/models.py`; update `docs/models.md`, FACTS.md (assumption A6).
Stop condition: a freeze, reboot or disconnect: power-cycle, record clip length and size, do not go longer.

## HW-11. Text and name tags
Executor: HUMAN+AI. Writes: 1.
`$ rebeambox send-text "Somchai" --subtitle "Bangkok" --bg "#102040" --font /path/to/NotoSansThai.ttf --model MODEL --address ADDR`. Use a Thai-capable font for Thai text (without it, glyphs are boxes). Record legibility at the real panel size and whether text sits inside the visible circle.

## HW-12. Wi-Fi path (H5) - only if HW-3 found an access point
Executor: HUMAN+AI. Writes: stills count; live frames are not gated.
1. Join the SSID. 2. `$ rebeambox send-image testmedia/photo.jpg --transport wifi` (a still upload on TCP 8080). 3. `$ rebeambox stream testmedia/clip3.mp4 --fps 2`, then `--fps 3`. The client caps at about 3.3 fps (300 ms spacing, as the app does). To test faster, make a local uncommitted edit of `MIN_FRAME_INTERVAL` in `rebeambox/wifi.py`, film the badge at 60 fps and count distinct frames, then revert the edit (`git checkout rebeambox/wifi.py`).
4. Capture with `sudo tcpdump -i <wlan> -w badge-wifi.pcap host 192.168.8.1` (outside the repo) and compare with the vendor app's session (PCAPdroid on the phone) if HW-1 was approved: control words, HTTP header, reply text (`docs/wifi-protocol.md`).
Pass: upload shows the picture; stream shows frames. Record highest fps without stutter and any reply bytes. A frame over 30,720 bytes is dropped by the client by design.

## HW-13. Touch notifications (H6) - NIJI (and NIKKO if it has touch)
Executor: HUMAN+AI. Writes: 0.
1. `$ python tools/notify_log.py ADDR --seconds 90 --json touch.jsonl` (subscribes to every notifiable characteristic, passive).
2. While it runs: tap, double tap, swipe left/right/up/down, long press, 10 times each, noting the order and times. Also press the physical button(s) once each at the end.
3. Repeat once while the vendor app is connected instead (only if HW-1 was approved; use the HCI log).
Pass: either "no notifications while touching" (record that as the answer) or notifications correlated with gestures: raw hex, time, gesture, whether coordinates or codes, JSON or binary. If events exist: add them to `docs/PROTOCOL.md` section 8 as `[H]` and open a `fixes.md` item for a parser. If the badge disconnects on touch, record it.

## HW-14. BadgeSdk auth (H3) - only if HW-2 found 0xAE00 / C2E6FD00
Executor: HUMAN+AI. Writes: 2.
1. `$ rebeambox send-image testmedia/photo.jpg --transport badge --address ADDR 2>&1 | tee hw14.txt`. Watch for the auth exchange (challenge, encrypted reply, pass), bind, info query (picture size, memory), transfer.
2. If auth is rejected with the default key, do not brute-force. Record the exchange bytes (hex), compare lengths and opcodes with the vendor capture (HW-1), and check `tests/test_sw_auth_fuzz.py` and `docs/PROTOCOL.md` for what is assumed. The wrong-key negative control from `hardware-test-v1.md` H3 is allowed only on a spare badge and only with the owner's approval.
Pass: auth reaches pass and the file transfers. Update PROTOCOL.md section on auth with `[H]`.

## HW-15. Non-destructive physical survey
Executor: HUMAN. No writes, no opening.
1. FCC: `https://fccid.io/2BR3T-BAGDE0` is the only existing spelling (the string `2BR3T-BADGE0` returned 404, `docs/recon-web.md`). Download the internal photos and the label exhibit; note chip markings you can see (JL QFN) and the board code if visible (`YH-GS2501-V0.2` Nikko, `YH-GS-NANO-V0.2` Nano) [W].
2. Photograph the badge: front, back, label (blur the serial and QR), charging port, buttons. Note screws, ultrasonic welds or adhesive seams. Do not pry anything.
3. Measure nothing live. A DMM across the USB-C CC pins to GND (expect about 5.1 kOhm if it presents as a sink) is allowed with the badge unplugged and off.
Record in `results/HW-15-<date>.md`; add to `docs/recon-web.md` only third-party links, not photos of the unit with identifiers.

## HW-16. USB enumeration (observe only)
Executor: HUMAN. No writes.
Third-party reports say the badge enumerates as VID 4C4A PID 4155 "BR28 UDISK" (a mass-storage device with no media) while charging or in a USB mode, and that the stock app does not run over USB [W, `docs/recon-web.md` section 3].
1. Plug the badge into a computer with a known-good data cable. Linux: `$ lsusb -d 4c4a:4155` and `$ dmesg | tail -20`. macOS: `$ system_profiler SPUSBDataType`. Windows (PowerShell): `Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB*VID_4C4A*'`.
2. Record whether it enumerates, the strings, and what the badge screen shows. Unplug.
3. DO NOT mount, format, write to the device, run any Jieli tool, or press the button combination that enters a download mode. A third-party NANO was bricked while experimenting with firmware (`docs/recon-web.md`, source S2); we only observe.
Pass: enumeration recorded as `[H]` or "does not enumerate".

## HW-17. Destructive teardown and read-only dump (owner approval required)
Executor: HUMAN only. Do not start without a written approval in the result file (who, when, which unit; it must be a unit the owner is willing to lose).
This is the executable summary of `docs/hardware-recon-checklist.md` sections 6 to 8, with corrections from the research since. Read that document first.
Corrections:
- The FCC ID that exists is `2BR3T-BAGDE0`.
- Third-party teardown (Nano): the flash is a 16 MiB SPI NOR inside the SoC package (the unpopulated SOP-8 pad has no ground continuity), so an external clip may have nothing to clip onto [W]. Identify before assuming a dump point exists.
- The SoC is a Jieli BR28 (AC701N class): no ARM SWD/JTAG; the debug interface is Jieli's own. UART output at 115200 and similar rates is worth listening for on test pads.
- Read-only means read-only. Never write, erase, flash, or use a Jieli UBOOT download mode. Never flash a modified image.
Steps (in order, stop at the first step that answers the question):
1. Plan from the FCC internal photos (HW-15). Decide whether opening is needed at all.
2. Safety: battery is a LiPo pouch; use plastic tools only, no heat above about 60 C, disconnect the battery before anything else, never short it.
3. Identify chips (SoC, flash, display driver, PMIC) with a macro photo; table as in the old checklist section 6.2.
4. Rails: with a current-limited supply on the battery pads, measure the flash VCC (expect 1.8 V on wearable NOR; a 3.3 V programmer on a 1.8 V part will damage it) and the core rail.
5. Only if a discrete flash exists and rails are 1.8 V: use a 1.8 V-capable programmer or level shifter, battery disconnected, take two reads (`flashrom -p ch341a_spi -r dumps/run1.bin`, again `run2.bin`) and require identical SHA-256 (`sha256sum` on Linux, `shasum -a 256` on macOS, `Get-FileHash` on Windows). Differing hashes mean bus contention: stop.
6. Firmware dumps are vendor material: store under `dumps/` (git-ignored), never commit, never upload. Commit only your notes (partition map, offsets, hashes of the dump, what you learned about the file system and the display init sequence).
7. Analysis of a dump (an AI can do this on a file the human provides): `binwalk -B`, `strings -a -n 8`, look for the FAT16 gallery volume and the frame header/directory layout described in `docs/recon-web.md` section 4, display init byte chains, and the command dispatch for BLE 0x01F1.
Record everything in `results/HW-17-<date>.md`. Anything surprising goes to `docs/problem_solution.md`.

---
## After hardware tasks: decision checklist
Update only what the evidence changes, with the tag `[H]` and the result file named as the source.
| Finding | Files to change |
|---|---|
| Transport confirmed | `docs/FACTS.md` section 3, `docs/models.md` sections 1 and 5, `docs/compatibility-matrix.md` (via `tools/aggregate_reports.py`), README models section |
| Still type | `rebeambox/models.py` `still_mode`, test in `tests/test_models.py`, `docs/models.md`, `docs/PROTOCOL.md` |
| Picture size / orientation | `docs/FACTS.md` section 2; code only if a default is wrong, with a test |
| Video cap | `rebeambox/models.py` `video_max_s`, `docs/models.md`, FACTS.md |
| Flash behaviour | `docs/safe-write.md` limits and notes, FACTS.md, and (owner approval) default thresholds in `rebeambox/safewrite.py` |
| A protocol byte was wrong | `docs/PROTOCOL.md` (tag `[H]`/Corrected), the builder, the test vector, the simulator |
| Anything went wrong | `docs/problem_solution.md` new entry, `fixes.md` |
When everything you planned is done: `STATUS.md` updated, `python tools/aggregate_reports.py` run, commit, push to the given branch, final message to the owner listing (a) what is now `[H]`, (b) what contradicted the code, (c) what is still unknown, (d) the next test to run.
