# reBeamBox

Open-source Python client for Beambox-style round e-badges (Beambox e-Badge Pulse, Beambox+) over Bluetooth LE.
Sends JPG/PNG stills, GIFs, short videos (3 s default cap) and rendered text or name tags. No vendor account, no cloud, no ads, no telemetry.

STATUS: written from static analysis of the Android app. It has NOT been tested on real hardware. Byte layouts are documented and unit-tested against a software badge, but expect to debug on first contact (see docs/PROTOCOL.md section 6.4). Use `--dry-run` first.

## Install
Python 3.10+ is required. Dependencies are split: core (bleak, Pillow) with `pip install -e .`, `[test]` adds pytest, `[emulation]` adds unicorn, capstone and pyelftools (needed only to re-derive auth test vectors from the native library; those tests skip when the extra or the library is missing). ffmpeg is needed only for GIF and video (stills and text do not need it).
```
python3 -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .                # installs bleak and Pillow, plus the `rebeambox` command
pip install -e .[test]          # adds pytest (core + test is all CI needs)
pip install -e .[emulation]      # optional: unicorn, capstone, pyelftools for the native-auth emulation and RE tools
# pip install -e .[dev] still works (alias of [test]); [full] = test + emulation
# ffmpeg: apt install ffmpeg | brew install ffmpeg | winget install ffmpeg
```

### Rebuilding the analysis files (research only)
The APK and the decompiled tree are never committed. To recreate them on another machine: `python scripts/setup_tools.py`, then `python scripts/rebuild_analysis.py` (the .sh files are wrappers; Linux, macOS, Windows; `--max-heap 3g` on small machines, `--url`/`--local-file` when the vendor mirror is unreachable). It reads `analysis/sources.env` (URL, SHA-256 of the XAPK, base APK and ABI split, tool pins), downloads, refuses to continue on a hash mismatch, extracts, runs jadx into `analysis/decompiled` and writes `analysis/BUILD-INFO.txt`. Options: `--dry-run`, `--force`, `--recover` (CFR recovery), `--local-file PATH` (skip the download), `--accept-new-hash` (print the new hash and continue; edits nothing). See docs/SOP.md section 9.1. The client itself does not need any of this.

## Quick start
```
rebeambox scan                                   # list badges (NEO, B-Device, tag 0xB3, plus --name)
rebeambox scan --name Pulse --all                # show everything, mark matches
rebeambox send-image photo.jpg                   # 360x360 circular crop, or the size the badge reports
rebeambox send-image photo.png --square --size 368
rebeambox send-gif party.gif
rebeambox send-video clip.mp4 --fps 15           # first 3 s only (--max-seconds)
rebeambox send-text "Somchai" --subtitle "Bangkok" --bg "#102040" --font /path/to/NotoSansThai.ttf
rebeambox send-image photo.jpg --address AA:BB:CC:DD:EE:FF --name Pulse
python -m rebeambox ...                          # same as the command
```
Press the badge Bluetooth button once first (the app's instructions say this enables phone transfer). If your badge advertises a different name, add `--name <prefix>`.

## Models
`--model nikko|nano|niji` (Nikko is the Pulse). It adds the model name to the scan filter, sets the video cap and picks the still encoding (it never overrides the picture size the badge reports). All three speak the nn20 service 0x01F0 according to third-party reports, so stills go out as a one-frame animation container (type 5); `--nn20-still album` selects the app's type 6 path. Put the badge on its pairing screen first, it advertises as `E-badge` only then. Details: docs/models.md; screen sizes, 360 versus 368, chip and limits: docs/FACTS.md.

## Wi-Fi models and live frames
Products that the vendor server marks as Wi-Fi expose an access point (SSID contains `E-Badge`, gateway 192.168.8.1). Join it with your OS first, then:
```
rebeambox send-image photo.jpg --transport wifi            # POST /upload on TCP 8080, 360x360
rebeambox stream clip.mp4 --fps 2                          # live JPEG frames (at most 3.3 fps, 30 KB each)
rebeambox send-image photo.jpg --transport wifi --dry-run w.txt   # software badge, no network
rebeambox probe <ADDRESS> --json gatt.json                 # dump BLE services for a bug report
```
Details: docs/wifi-protocol.md. First hardware test: docs/first-session-checklist.md.

## Dry run (no Bluetooth)
```
rebeambox send-image photo.jpg --dry-run frames.txt
rebeambox send-image photo.jpg --dry-run frames_nn20.txt --transport nn20
rebeambox send-text "Hi" --dry-run t.txt --pic 240 240
```
`frames.txt` lists every GATT write (W) and simulated badge notification (N) with characteristic, length and hex; `frames.txt.payload` is the exact file (JPEG, AVI or nn20 container) that was sent. The simulated badge runs the real auth, bind, storage discovery and device-pulled transfer, so a dry run exercises the whole protocol code.

## Bluetooth permissions
- Linux: BlueZ 5.55+ and the `bluetooth` service. Run as a normal user in the `bluetooth` group (or grant `cap_net_raw` to Python for scanning). No location permission is needed.
- macOS: first run asks for Bluetooth access for your terminal app (System Settings, Privacy and Security, Bluetooth). Addresses are UUIDs, use `rebeambox scan` to find yours.
- Windows 10/11: turn Bluetooth on; no pairing is needed. If connection fails, remove the badge from Windows paired devices (the badge uses application-level binding, not OS pairing).

## How it works
Transport is chosen by service discovery: control service C2E6FD00 plus Jieli 0xAE00 (BadgeSdk path: bind, picture size, Jieli auth, RCSP large-file transfer), or service 0x01F0 (nn20 path: IMB still or animation container in framed packets with ACK pacing). See docs/PROTOCOL.md.

## First contact, pacing, web harness, capture replay
```
rebeambox probe --qualify --model nikko          # scan, MTU, GATT, transport, read-only handshake; writes reports/first-contact-<timestamp>.md
rebeambox probe --qualify --simulate nn20        # same against a software badge (no Bluetooth)
rebeambox send-image photo.jpg --packet-interval-ms 20 --ack-batch-size 4 --nn20-still gif
python tools/replay_pcap.py btsnoop_hci.log --out extracted/     # decode a capture of the vendor app (also .pcap, .pcapng)
python tools/scrub_capture.py summary.txt -o scrubbed.txt --mask <serial>   # mask addresses, tokens and named literals before committing
cd ui && python3 -m http.server 8000                             # Web Bluetooth harness, open http://localhost:8000 in Chrome
```
- `probe --qualify` writes nothing to the badge storage: nn20 badges are only listened to (status JSON on 0x01F2), BadgeSdk badges get the read-only info query 0xC6. The report follows the results template of docs/hardware-test-v1.md; Bluetooth addresses are masked unless `--no-redact`. Reports are git-ignored.
- Packet size follows the negotiated MTU: P = min(446, mtu - 12), ATT minimum 23. No-ACK streaming falls back to ACK batches (and a reconnect if the link dropped) when the badge reports a failed packet or a write errors.
- Safe-write policy: every real upload is counted per badge, an identical payload is skipped, writes closer than 30 s are refused, more than 50 writes in 24 hours per badge are refused (`--max-per-day`), and high counts warn (`--force`, `--no-delta`, `--min-interval-s`, `--warn-per-day`, `--warn-total`; `rebeambox uploads` shows the counter). See docs/safe-write.md.
- Streaming: `rebeambox stream synthetic|clip.gif|video.mp4 [--transport wifi|nn20|badge] --fps N --dry-run out.txt` runs crop, JPEG quality control, rate control and the Wi-Fi camera sink or BLE clips; see docs/streaming-plan.md (Prototype status) and docs/streaming-benchmarks.md.
- nn20 stills default to a one-frame type 5 container (interval 3000 ms); `--nn20-still album` sends type 6. Stills are cropped with a circular mask on black at the size the badge reports (360 or 368).
- Details: ui/README.md, tools/replay_pcap.py header, docs/hardware-test-v1.md.

## Fixtures, report aggregation, CI
```
python tools/make_fixtures.py [--check]           # synthetic btsnoop/pcapng captures in fixtures/captures (no vendor data)
python tools/replay_pcap.py fixtures/captures/malformed.btsnoop    # reports bad checksums, CRC16 errors, sequence gaps
python tools/aggregate_reports.py                 # reports/first-contact-*.md -> docs/compatibility-matrix.md (idempotent)
python tools/check_repo_rules.py                  # fails on emoji, analytics hosts, non-local URLs in code
```
- `fixtures/captures/MANIFEST.md` describes the three synthetic scenarios (fragmented nn20 animation with ACKs, full RCSP auth session, malformed capture). They are generated from this repository's own builders and are not recordings of any badge.
- `docs/compatibility-matrix.md` collects one row per first-contact report: device name, masked address, transport, MTU, accepted container (Type 5 or 6), verdict.
- GitHub Actions workflow (`.github/workflows/ci.yml`) runs on push and pull request to main with Python 3.10, 3.11 and 3.12: repo rules, fixture check, `pytest -q`, and the no-vendor-calls test again as an explicit step. Tests needing the native `libjl_auth.so` skip themselves in CI.
- Sequence diagrams (Mermaid) for nn20, BadgeSdk/RCSP and the Wi-Fi camera are inline in `docs/PROTOCOL.md`.

## Tests
```
python -m pytest -q                  # no hardware, CI runs the same; see docs/software-test-v1.md (larger auth fuzz: -m slow)
```

## Docs
- docs/PROTOCOL.md: byte-exact protocol, with Confirmed/Inferred tags
- docs/wifi-protocol.md: Wi-Fi access point path, control words, live camera frames, upload
- docs/software-test-v1.md: the software test plan (what each test checks and where it lives)
- docs/beambox-reverse-reference.md: imported external summary with a reconciliation table (PROTOCOL.md and FACTS.md win)
- docs/tasks/NEXT-PASS-PROMPT.md: prompt for the next agent pass over reBeamBox, reWork and reWatch
- docs/tasks/README.md: step-by-step recon task pack for agents and people (software S0 to S11, hardware HW-0 to HW-17, assumptions, status board)
- docs/hardware-test-v1.md: tests to run with a real badge, with pass/fail criteria and a results template
- docs/first-session-checklist.md: what to capture and report on the first real badge test
- docs/models.md: NIKKO, NANO, NIJI comparison, transport per model, web recon
- docs/FACTS.md: one fact sheet for screen sizes, picture size, transports, chip and limits
- docs/pulse.md: Pulse-specific findings and how the client handles them
- docs/ads-removal.md: how the original app shows promotions, and that this client has none
- AGENTS.md: rules for AI agents working in this repo (also read fixes.md and docs/problem_solution.md first)
- fixes.md: open and fixed issues
- docs/review-critique-2026-10.md: critique of an external review
- docs/SOP.md: reverse engineering procedure (a generalized, target-agnostic version lives in the reWork repo)
- docs/app-behaviour.md, docs/binaries.md: app and binary notes
- docs/problem_solution.md: running log of problems and solutions
- docs/hardware-prediction.md, docs/streaming-plan.md: streaming design
- scripts/spec_vectors.py, tools/emulate_jl_auth.py: spec vector generator, native auth emulation (needs the library, not shipped)

Not affiliated with the badge vendor. The original app and its assets are not included or modified.

- [Hardware recon checklist](docs/hardware-recon-checklist.md)
- [Streaming benchmarks (software badges)](docs/streaming-benchmarks.md)
- [Safe-write policy (flash protection, upload counter)](docs/safe-write.md)
- [Web reconnaissance (FCC, teardowns, retail, related projects)](docs/recon-web.md)
