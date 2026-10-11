# Hardware test plan v1

Needs a real badge. Run after the software tests (software-test-v1.md) and use together with first-session-checklist.md (capture and reporting steps). Fill the results template at the end for each badge. Model names: NIKKO (Pulse), NANO, NIJI. Pass criteria are written so a result is unambiguous; anything else is a fail and must be reported with logs.

## Required tools
- Computer with Bluetooth LE, Python env from README, `rebeambox` installed, ffmpeg for video tests.
- Android phone with the vendor app (reference behaviour), Developer options HCI snoop log; nRF Connect for Mobile; PCAPdroid (Wi-Fi reference capture).
- Wireshark; Linux `btmon` or macOS PacketLogger; `tcpdump` for the badge access point.
- Phone or camera with 60 fps video (to count displayed frames), stopwatch, a fully charged badge, a test image and GIF, an 8 s video, a 12 s video.
- Test media: `photo.jpg` (any), `party.gif` (about 20 frames), `clip8.mp4` (8 s), a gradient image with a labelled top-left corner (to see rotation and crop).

## H1. Scan, advertised name and services
- Steps: badge on its pairing screen; `rebeambox scan --all --timeout 15 | tee scan-all.txt`; `rebeambox scan --model <model>`; `rebeambox probe <ADDRESS> --json gatt.json`; compare with nRF Connect.
- Shortcut: `rebeambox probe --qualify --model <model>` writes `reports/first-contact-<timestamp>.md` with these fields filled in (read-only handshake; PASS means transport identified and the badge answered, PARTIAL means identified but silent, FAIL means not found or no known service).
- Pass: the badge appears in `scan --model <model>` (names expected `E-badge`, `Nikko-badge(BLE)`, `NEO...`, `B-Device...`); the service list identifies the transport: 0x01F0 (nn20) or the 0x9E control service plus RCSP (BadgeSdk). Record the exact name, service UUIDs, manufacturer data (tag 0xB3 expected for BadgeSdk badges) and MTU.
- Fail: not found with `--all` (adapter, pairing screen, power); found only without a model filter (add the name to `profiles`); neither service present.
- Also record: any SSID containing `E-Badge` on the phone Wi-Fi list (decides H5).

## H2. Type 5 versus type 6 still image
- Purpose: confirm which still encoding displays (code says type 6 album, third-party reports say type 5 container for Niji and Nano).
- Steps (nn20 badges): `rebeambox send-image photo.jpg --model <model> --transport nn20 --address <ADDRESS>` (type 5, default), power-cycle the badge, then the same with `--nn20-still album` (type 6). Use the labelled gradient image. Photograph each result. For BadgeSdk badges this test is replaced by the AVI/JPEG path: `--transport badge`.
- Pass: the picture appears, correctly oriented, circle or square as expected, no black screen, within 30 s. Record which type works, which fails (black, garbled, nothing), the picture size reported in the status JSON (`size`) and whether `--size 360` or `368` changes the crop.
- Fail: both blank (check checksum bytes in the capture against the vendor app capture, frame count, ack mode via `time_mode`).
- Decision after the test: set `still_mode` in `rebeambox/models.py` for that model to the working one and update docs/models.md, PROTOCOL.md section 7.

## H3. With and without auth (BadgeSdk path)
- Purpose: confirm the Jieli auth is needed and correct.
- Steps: (a) normal send `rebeambox send-image photo.jpg --transport badge --address <ADDRESS>` and watch the log for the auth exchange (challenge, encrypted reply, `pass`). (b) negative control: capture the vendor app doing the same and compare the 17-byte frames structure (the bytes differ because challenges are random; compare lengths and opcodes). (c) with a deliberately wrong key if you can edit `jl_auth.DEFAULT_KEY` locally in a scratch copy: expect the badge not to answer `pass` and to drop the link. Only on a spare badge.
- Pass: (a) auth reaches `pass` and the transfer completes; (c) a wrong key fails. For nn20 badges record that no auth frames occur (expected, nn20 has none in the app).
- Fail: auth rejected with the right key (verify against `tests/test_sw_auth_fuzz.py` and the capture; the library vectors may not match the badge firmware revision).

## H4. Measure fps over BLE
- Purpose: real throughput for the streaming plan.
- Steps: send the 8 s test video as animation clips and stills in a loop. For each transport and ack mode (`time_mode` from the status JSON): `time rebeambox send-gif party.gif --model <model> --address <ADDRESS>` five times; payload size is in the `.payload` file from `--dry-run`. Compute bytes per second = payload bytes / seconds. Estimate still fps = 1 / (seconds per still). Note the MTU printed and the packet interval.
- Pass criteria (from the plan in streaming-plan.md): record numbers; a result within 50 percent of the predicted bound (nn20 no-ack about 22 KB/s, ack about 9 KB/s, BadgeSdk 10 to 30 KB/s) confirms the model. No pass/fail on speed itself, fail only on dropped transfers or disconnects (repeat 5 times, report the number of failures).
- Record: transfer time, bytes, retries, any GetPacketFail.

## H5. Measure fps over Wi-Fi (only if a Wi-Fi access point exists)
- Steps: join the badge SSID (docs/wifi-protocol.md section 2); `nmap -Pn -p 80,8080 192.168.8.1`; `rebeambox send-image photo.jpg --transport wifi`; then `rebeambox stream clip8.mp4 --fps 2`, `--fps 3`; to go faster edit `MIN_FRAME_INTERVAL` in `rebeambox/wifi.py` (0.3 s) to 0.2, 0.125, 0.1 and repeat. Film the badge at 60 fps and count distinct frames per second.
- Pass: upload returns an HTTP 200/204/OK or no response and the picture shows; stream shows camera mode on (reply 0x007B) and frames follow; at 3 fps the picture is smooth. Record the highest fps without visible stutter or disconnect, bytes per frame, and what happens to a 30721-byte frame (the client drops it; test once by lowering the quality ceiling).
- Fail: no connection (wrong IP, password), no 0x007B reply (the model has no Wi-Fi camera mode: record the reply bytes).
- Capture: tcpdump of the session, plus the vendor app's session through PCAPdroid for comparison of control words and HTTP header.

## H6. Niji touch notifications
- Purpose: PROTOCOL.md section 8 says the app never consumes touch events; check whether the badge sends any.
- Steps (NIJI only): connect with nRF Connect, enable notifications on every notifiable characteristic (nn20 0x01F2 and any others from `probe`); tap, swipe and long-press the screen 10 times each; export the log. Repeat with `rebeambox` connected (nn20 session open) and with the vendor app connected, using the HCI snoop log.
- Pass: either no notifications while touching (expected; record "no touch events") or notifications correlated with touches: record raw hex, timestamps, which gesture, whether coordinates or only gesture codes, and whether JSON or binary.
- Fail: the badge disconnects on touch (record).
- If events exist: add them to PROTOCOL.md section 8 as Confirmed (hardware) and open an issue for a parser.

## H7. Real video length limit
- Purpose: retail data says 3 s for NIKKO, the app trimmer allows 10 s and 5 s for NIJI.
- Steps: send 2 s, 3 s, 4 s, 5 s, 8 s and 10 s clips (`rebeambox send-video clipN.mp4 --max-seconds N --fps 15 --address <ADDRESS>`; the client caps at the model default, so pass `--max-seconds` explicitly). After each, note whether the transfer completes, whether the badge plays it all, loops, or truncates, the file size, and free space before and after (`freespace` in the status JSON).
- Pass: the longest clip that plays completely and the shortest that fails are recorded; update `video_max_s` in `rebeambox/models.py` and docs/models.md.
- Fail: the badge freezes or reboots (power-cycle, record clip length and size, stop increasing).

## Results template (one per model and test)
```
test id (H1..H7):            model:          date:
badge firmware / app version:
command(s) run:
log file(s) / captures attached:
measured values (name, services, bytes, seconds, fps):
PASS / FAIL / PARTIAL:
observations (display, sound, reboot, disconnect):
code or doc change needed:
```
Report in the repository issue "First session: <model> <date>" (see first-session-checklist.md section 8) and append problems to problem_solution.md.

## Related

- [Hardware recon checklist](hardware-recon-checklist.md) (H8/H9 wear and physical dump path)
