# reBeamBox

Open-source Python client for Beambox-style round e-badges (Beambox e-Badge Pulse, Beambox+) over Bluetooth LE.
Sends JPG/PNG stills, GIFs, short videos (3 s default cap) and rendered text or name tags. No vendor account, no cloud, no ads, no telemetry.

STATUS: written from static analysis of the Android app. It has NOT been tested on real hardware. Byte layouts are documented and unit-tested against a software badge, but expect to debug on first contact (see docs/PROTOCOL.md section 6.4). Use `--dry-run` first.

## Install
Python 3.10+ is required. ffmpeg is needed only for GIF and video (stills and text do not need it).
```
python3 -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .                # installs bleak and Pillow, plus the `rebeambox` command
pip install -e .[dev]           # adds pytest etc.
# ffmpeg: apt install ffmpeg | brew install ffmpeg | winget install ffmpeg
```

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
`--model nikko|nano|niji` (Nikko is the Pulse). It adds the model name to the scan filter, sets the default size (368) and video cap (3 s, Niji 5 s) and picks the still encoding. All three speak the nn20 service 0x01F0 according to third-party reports, so stills go out as a one-frame animation container (type 5); `--nn20-still album` selects the app's type 6 path. Put the badge on its pairing screen first, it advertises as `E-badge` only then. Details: docs/models.md.

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
cd ui && python3 -m http.server 8000                             # Web Bluetooth harness, open http://localhost:8000 in Chrome
```
- `probe --qualify` writes nothing to the badge storage: nn20 badges are only listened to (status JSON on 0x01F2), BadgeSdk badges get the read-only info query 0xC6. The report follows the results template of docs/hardware-test-v1.md; Bluetooth addresses are masked unless `--no-redact`. Reports are git-ignored.
- Packet size follows the negotiated MTU: P = min(446, mtu - 12), ATT minimum 23. No-ACK streaming falls back to ACK batches (and a reconnect if the link dropped) when the badge reports a failed packet or a write errors.
- nn20 stills default to a one-frame type 5 container (interval 3000 ms); `--nn20-still album` sends type 6. Stills are cropped with a circular mask on black at the size the badge reports (360 or 368).
- Details: ui/README.md, tools/replay_pcap.py header, docs/hardware-test-v1.md.

## Tests
```
python -m pytest -q                  # no hardware (202 pass, 1 skip); see docs/software-test-v1.md (larger auth fuzz: -m slow)
```

## Docs
- docs/PROTOCOL.md: byte-exact protocol, with Confirmed/Inferred tags
- docs/wifi-protocol.md: Wi-Fi access point path, control words, live camera frames, upload
- docs/software-test-v1.md: the software test plan (what each test checks and where it lives)
- docs/hardware-test-v1.md: tests to run with a real badge, with pass/fail criteria and a results template
- docs/first-session-checklist.md: what to capture and report on the first real badge test
- docs/models.md: NIKKO, NANO, NIJI comparison, transport per model, web recon
- docs/pulse.md: Pulse-specific findings and how the client handles them
- docs/ads-removal.md: how the original app shows promotions, and that this client has none
- docs/SOP.md: reverse engineering procedure
- docs/app-behaviour.md, docs/binaries.md: app and binary notes
- docs/problem_solution.md: running log of problems and solutions
- docs/hardware-prediction.md, docs/streaming-plan.md: streaming design
- scripts/spec_vectors.py, tools/emulate_jl_auth.py: spec vector generator, native auth emulation (needs the library, not shipped)

Not affiliated with the badge vendor. The original app and its assets are not included or modified.

- [Hardware recon checklist](docs/hardware-recon-checklist.md)
