# reBeamBox: design and test handoff report

Audience: another AI (or engineer) who will improve this project. This file is self-contained; deeper detail lives in the linked docs. Date of writing: 2026-10-11. Repository: THAI-passport/reBeamBox (public, branch main).

Evidence labels used everywhere: [C] Confirmed from decompiled app code or native disassembly, [I] Inferred (reasoned, not shown directly), [W] reported by third parties on real hardware (not verified by us), [U] Unknown. Nothing in this project has been tested on a real badge.

## 1. Goal and scope
- Goal: an open-source replacement client for the Beambox+ companion Android app (`com.guangshen.beambox`, version 1.0.14, versionCode 24) so a computer can push images, GIFs, short videos, text/name tags and live frames to Beambox round e-badges.
- Primary target: Beambox e-Badge Pulse, which the product owner identifies as the NIKKO model. Also supports the NANO and NIJI models through profiles.
- Method: static analysis only (jadx, apktool, capstone/pyelftools, unicorn emulation of one native library), then a Python client tested against software badges. No app code or assets are copied into the repo; the APK and decompiled tree are git-ignored.
- Principles: no ads, no analytics, no vendor backend calls (enforced by `tests/test_no_vendor_calls.py`), no emoji in code, docs or UI of the client. The original app's promotional surfaces are described in `docs/ads-removal.md`.
- Out of scope so far: phone app, GUI, firmware work, anything requiring hardware.

## 2. Product line
| Model | Marketing | Notes |
|---|---|---|
| NIKKO | Beambox e-Badge Pulse, flagship | standard display, four wearing styles; retail data 3 s video |
| NANO | Lite, essential | location finding, long standby, pin or keychain |
| NIJI | specialist | 1.53 inch touch display, GIF, bigger battery, colour; app trims video to 5 s |
Facts: the string "Pulse" does not occur in the APK; product identity comes from a server product list (`api/app/badge/select-badge`, records with deviceName, signalName, deviceType `BT` or `WiFi`). The only model-specific code is the NIJI video trimmer window (5 s vs 10 s) [C]. [W] reports say NN-family units (Niji, Nano) expose only the nn20 service 0x01F0, advertise as `E-badge` on the pairing screen (a Nano on USB power as `Nikko-badge(BLE)`), use a Jieli BR28-class SoC, and display a still only when sent as a one-frame animation container (type 5), not as raw JPEG type 6. See `docs/models.md`, `docs/pulse.md`.

## 3. The three transports
The app chooses by device name and product record [C]: names containing NEO or B-Device go to BadgeSdk; other names matching the stored product signal name go to nn20; products with `deviceType = WiFi` use the Wi-Fi socket. For the NN family the best current belief is nn20 over BLE [I for Nikko, W for Niji and Nano]. The client picks BLE transport by GATT service discovery, not by name.

### 3.1 nn20 BLE (service 0x01F0) [C layouts, W for hardware match]
- GATT: service 0x01F0, write 0x01F1 (write without response), notify 0x01F2. MTU 512 requested (fallback 23). No pairing/bonding call in the app.
- Frame app to badge (big endian): `F1 | type | N u16 | remaining u16 | L u16 | data | checksum`, checksum = (0 - sum of preceding bytes) & 0xFF, frame length L+9. Single-packet commands use N=0.
- Type codes: 5 animation, 6 album/still, 13 JSON settings (only seen: `{"animation_type":n}` sent bare before an animation); 1, 2, 3, 4, 7 are defined but unused in analysed code.
- Envelope for types 5 and 6: ASCII `{"type":T,"data":` + container bytes + `}`, chunked into P = min(446, max(23, MTU) - 12) data bytes (446 at MTU 512), at most 65535 packets.
- Replies on 0x01F2: `A0 | type | 2 unused | L (one byte) | UTF-8 JSON | checksum`, L at most 255, may be split over notifications. JSON: acknowledgements containing `GetPacketSuccess` or `GetPacketFail`, and a status record pushed by the badge (fields allspace, brand, devname, freespace in KB, size string like "368,368", time_mode, type). The status is pushed, not requested [I from the absence of a request].
- Pacing and ACK: `time_mode` 1 selects the no-response loop mode (20 ms between packets, no waiting for ACK); otherwise ACK mode: batches of 4 (adaptive 4, 2, 1), at least 50 ms interval, retry waits 500/1000/2000 ms, 3 retries. After the last packet wait `min(((N+999)//1000)*800+800, 3000)` ms. Minimum 300 ms between uploads. Free-space check: refuse if payload + 64 KiB exceeds freespace when known.
- Media containers (little endian) [C layout]:
  - IMB still (type 6): 36-byte header `49 4D 42 00 | 4 | jpegLen+32 | fmt 11, 0, 0 | width u16 | height u16 | offset 36 | jpegLen | 0 | 0` then JPEG. Width/height written as 368 only for 368, else 360.
  - Animation container (type 5): magic 0x12345678, address-list length N*16+24 (BLE) or N*16+32 (Wi-Fi), N, interval ms, 12-byte label `output/<ms>ms`, total length minus 1, frame table (12-byte name `frame_00001.` + u32 offset), frame records with a 32-byte header (own offset, next offset, 11, 0, 0, width, height, data offset, JPEG length, 0, 0) then JPEG. Last frame points to the first.
- Model default: stills are sent as a one-frame type 5 container (interval 3000 ms), per [W]; `--nn20-still album` selects IMB type 6. Both remain unverified on a Nikko.

### 3.2 BadgeSdk with Jieli RCSP (names NEO, B-Device) [C]
- Advertising: manufacturer data (AD 0xFF) of at least 10 bytes: tag 0xB3 = badge, shape 0x6D circle or 0x6C square, 6-byte id, u16 project number. Only 0xB3 accepted by the SDK scanner.
- Control service `C2E6FD00-E966-1000-8000-BEF9C223DF6A`: notify FD01 and FD03, write FD02. Writes chunked to MTU-6, 5 ms apart. After connect wait 1550 ms then bind.
- Control frame: `9E | checksum (byte sum of bytes 2..end) | flags (bit1 always set on commands, bit2 if payload+6 > 20, bits3..6 sequence 0..15) | cmd | length u16 little endian | payload`. Commands: 0x60 bind (reply 0x61), 0x02 time, 0x16 language, 0xC6 info (reply 0xC7), 0xDA picture size (reply 0xDB, 12 big-endian u16 values), 0xDC file type (0x0C for badge media) acknowledged by 0xFF generic response, 0x29 battery request (reply 0x27, two bytes status and level), 0x81 camera enter(0)/exit(2) and badge-to-app camera events (1 and 3 shutter, 2 exit), 0x87 file transport switch. Incoming frames with flag bit1 are acknowledged with 0xFF `[cmd, 0]`.
- File transfer: second GATT connection to the same address, Jieli RCSP service 0xAE00 (write 0xAE01, notify 0xAE02). RCSP frame: `FE DC BA | flag (bit7 command, bit6 wants response) | opcode | length u16 big endian | body | EF`; command body starts with sn, response body with status then sn; opcode 0x01 inserts an inner opcode. Large-file sequence: GetTargetInfo 0x03 (MTU in LTV type 13, CRC support in type 21) then NotifyPrepareEnv 0x21, DeviceExtendParam 0x27, StartLargeFile 0x1B (size, CRC16-XMODEM of file, temp name `%08x.tmp` from Java hashCode), then the badge pulls data with 0x1D requests (size, offset) and the app answers with Data frames (each with optional CRC16); GetName 0x20 may be requested; badge ends with StopLargeFile 0x1C (reason 0 success), Cancel 0x1E. Silence of 20 s aborts.
- Media on this path: still = plain JPEG q90 at the badge-reported size; animation or video = MJPEG AVI built with ffmpeg (`-c:v mjpeg -q:v 5`, 3 s cap in the client). Not the IMB or 0x12345678 containers.
- Authentication (Jieli RCSP auth, `libjl_auth.so`) [C, verified by emulation]: raw writes on 0xAE01 and notifications on 0xAE02. Reset frame `FE DC BA C0 06 00 02 00 01 EF`; app challenge `00|R[16]`; badge answers `01|E1(R)`; app answers `02 70 61 73 73`; badge sends its own challenge `00|Rdev`, app replies `01|E1(Rdev)`; badge sends `02 70 61 73 73`. E1 is the Bluetooth legacy-authentication function on SAFER+ with standard tables: T = Ar(K,R); M[i] = (T[i] xor R[i]) + A[i mod 6]; K~ = K with fixed per-byte sub/xor offsets; OUT = Ar'(K~, M), all 16 bytes. Default key `06775f87918dd423005df1d8cf0c142b`, fixed address `112233332211`, never changed by the app. Python reference `rebeambox/jl_auth.py`; vectors from emulating the real library (unicorn, `tools/emulate_jl_auth.py`).
- [W] contradicts using this path on NN-family units (they show only 0x01F0). It may serve older or other products. Whether a Pulse exposes it is [U].

### 3.3 Wi-Fi TCP (192.168.8.1:8080) [C], `docs/wifi-protocol.md`
- Which models: those whose server product record has `deviceType = WiFi`; [U] which of NIKKO, NANO, NIJI that is.
- Joining: the badge is an access point and DHCP gateway; SSID contains the product signal name (default `E-Badge`); open or password protected is [U] (app prompts if the scan shows security). Android 10+ uses a network specifier and binds the process to that network.
- Control words (2 bytes, big endian): 0x0069 query storage (reply ASCII `SD:<n>KB` plus 2 code bytes; 0x006B means refused), 0x005F end session, 0x0079 start camera (reply 0x007B), 0x007D photo saved, 0x007F stop (also sent by the badge when it leaves camera mode), 0x007A badge shutter button event, 0x0000 terminator.
- Live camera: frames sent as `[len u16 big endian][JPEG][00 00]`, JPEG 360x360 quality 10, at most 30720 bytes (the app only logs a warning above; our client drops such frames), at most one frame per 300 ms (3.3 fps). Stop: `00 7F 00 00`.
- Upload: a second TCP connection receives a handwritten HTTP request: `POST /upload HTTP/1.1`, Host, `X-Filename: NN.bin`, `Content-Type: application/octet-stream`, `Content-Length`, `Connection: keep-alive`, body in 6144-byte chunks with 1 to 3 ms sleeps, reply containing 200, 204 or OK (no reply counts as success). Payload is the IMB (stills) or 0x12345678 container (Wi-Fi variant N*16+32). An unused OkHttp uploader targets `http://192.168.8.1/upload` (port 80) with Content-Range resume, the first alternative if 8080 fails.
- Bandwidth: Wi-Fi proven 3 fps by the app; estimates in `docs/streaming-plan.md`.

## 4. Badge-originated data, touch
[C] Touch coordinates are never reported on any path; the app has no parser for them. nn20 status JSON has only the seven fields above; BadgeSdk consumes only 0x61, 0xC7, 0xDB, 0xFF, 0x27 (battery) and 0x81 (camera shutter events); Wi-Fi has only the control words. Battery exists only on BadgeSdk. [U] whether the badge sends undocumented notifications (H6 checks this on a Niji).

## 5. Unknowns that need hardware or captures
1. Pulse (Nikko) advertised name and GATT services, hence its transport.
2. Whether a Nikko shows a still sent as type 5 container, type 6 IMB, or both; accepted picture size 360 vs 368.
3. Whether the BadgeSdk path exists on any current model; whether auth is required and the default key accepted.
4. Whether nn20 ACK and pacing are enforced or only for reliability; real BLE throughput and MTU/PHY.
5. Which models have the Wi-Fi access point, its security, whether the badge accepts both sockets on port 8080, real fps limit, how the firmware tells a length prefix of 127 from the stop word 0x007F (the protocol has no type byte).
6. Real video length limit (retail 3 s; NIJI app window 5 s; code 10 s otherwise), flash space behaviour, duplicate file names.
7. Bind reply offsets for protocol 26 and above (jadx merged branches).
8. Niji touch notifications, if any.

## 6. Client architecture (`rebeambox`, version 0.1.0)
Layering: pure byte builders and parsers first, then media, then async sessions against an abstract link, then CLI. Only `link.BleakLink` and `wifi.TcpChannel` touch real I/O.
| Module | Role |
|---|---|
| `control.py` | BadgeSdk 0x9E frames, bind, time, info, picture size, file type, reply parsers |
| `rcsp.py` | Jieli RCSP framing, CRC16-XMODEM, large-file payloads, LTV and storage parsers |
| `jl_auth.py` | E1 on SAFER+, challenge helpers, default key |
| `nn20.py` | nn20 frames, replies, IMB and 0x12345678 containers, guard time |
| `media.py` | Pillow stills (centre crop, circular mask, transparency on black), GIF and video frame loading, text and name tag rendering, ffmpeg MJPEG AVI builder with the documented command, caps |
| `models.py` | profiles for nikko, nano, niji: name filters, video cap (3 s, niji 5 s), size 368, still mode |
| `scan.py` | name filter (skip names containing BLE unless a configured name matches; defaults NEO, B-Device, E-badge), advertisement parser, bleak scan, `probe` GATT dump |
| `link.py` | `Link` abstraction, `BleakLink`, `RecordingLink` (dry run) |
| `session.py` | `RcspSession`, `BadgeSession`, `Nn20Session` (auth, bind, transfers, retries, pacing) |
| `client.py` | `Job`, `detect_transport` (service discovery), `send`, `wifi_payload`, `send_wifi` |
| `wifi.py` | control words, POST builder, camera frame, `WifiSession` (send_file, stream), `TcpChannel`, `SimChannel` |
| `sim.py` | software badges: `SimBadgeSdk`, `SimNn20`, `SimWifiBadge` implementing the badge side from the spec |
| `cli.py` | commands below |
- CLI: `rebeambox scan [--all] [--model]`, `probe <address> [--json]`, `send-image`, `send-gif`, `send-video`, `send-text` (with `--subtitle`, colours, `--font`), `stream <video-or-gif> [--fps]` (Wi-Fi live frames). Common flags: `--address`, `--name` (repeatable), `--size`, `--square`, `--model nikko|nano|niji`, `--transport badge|nn20|wifi`, `--nn20-still gif|album`, `--wifi-still imb|gif`, `--host`, `--port`, `--max-seconds`, `--quality`, `--quiet`, `--dry-run FILE`.
- Dry run: no Bluetooth or network; talks to a software badge and writes every write (W) and reply (N) to FILE plus the exact payload to `FILE.payload`. BLE format: `W <short uuid> <length> <hex bytes>`; Wi-Fi format: `W|N <ctrl|upload> <length> <hex, long writes truncated to 64 bytes>`.
- `--model`: adds model names to the scan filter, sets default size 368 for BLE (ignored for Wi-Fi unless `--size` is given), video cap and still mode.
- Product questions that code cannot answer are flags (names, size, still mode, transport) so first hardware contact needs no code change.

## 7. Software test suite
- Status: the user reports 148 tests passed (pytest run on this repository after the software test plan was added; native auth fuzz, Thai font and ffmpeg tests skip when their prerequisites are missing, and the slow marker is deselected by default). The assistant that wrote the last 59 tests did not run them; the report of 148 passed is the first execution.
- Coverage (details and per-test locations in `docs/software-test-v1.md`):
  - Older files: frame serialization and checksums (`test_control.py`, `test_rcsp.py`, `test_nn20.py`), auth vectors from the emulator (`test_jl_auth.py`), media (`test_media.py`), scan filter (`test_scan.py`), models (`test_models.py`), sessions against software badges including retries and no-ACK mode (`test_session_sim.py`), CLI dry runs (`test_cli_dryrun.py`), Wi-Fi sessions including a real loopback TCP server (`test_wifi.py`), no vendor calls (`test_no_vendor_calls.py`).
  - `test_sw_containers.py`: IMB and animation container round trips with an independent parser, checksum edge cases (empty, maximum, corrupted), property-style random round trips.
  - `test_sw_auth_fuzz.py`: native emulator vs Python on random challenges, keys, addresses (20 by default, 500 with `-m slow`), plus pure-Python properties.
  - `test_sw_wifi_edges.py`: 30720 byte limit and dropping, embedded stop words, segmentation, stop between frames, the 127-byte ambiguity, shutter handling.
  - `test_sw_media_scan_transport.py`: non-square, transparent and palette images, uneven GIF delays, model caps, video trimming, scan matrix per model (names containing BLE), transport auto-selection from mock GATT services, Thai rendering.
  - `test_sw_snapshot.py`: hex-locked nn20 frames, IMB header, animation container and Wi-Fi POST header from a fixed embedded JPEG; CLI dry run self-consistency and determinism.
- Limits: software badges are written from the same spec as the client, so they prove consistency, not truth. Nothing here proves behaviour on a badge.

## 8. Hardware test plan (not yet run)
`docs/hardware-test-v1.md`, with the capture steps in `docs/first-session-checklist.md`. Tests: H1 scan, advertised name and services (decides transport); H2 type 5 vs type 6 still display; H3 with and without auth (BadgeSdk) and absence of auth on nn20; H4 BLE throughput and fps; H5 Wi-Fi fps and stutter threshold (only if an access point exists); H6 Niji touch notifications; H7 real video length limit. Each has steps, tools, pass or fail criteria; a results template ends the document. Results go to a repository issue titled `First session: <model> <date>` and to `docs/problem_solution.md`.

## 9. Flaws of the original design and streaming notes
Full list with evidence in `docs/hardware-prediction.md` section 2. Main points: whole-file upload only (no partial display or resume); timid ACK batching (about 7 to 9 KB/s); fixed pacing instead of link-aware flow control; no streaming or direct-draw command; JPEG only, a full JPEG per animation frame; weak 8-bit checksum and substring-matched JSON status; three incompatible transports selected by name substring; two GATT links on the BadgeSdk path with a fixed 1550 ms wait; 360 vs 368 size inconsistency; up to 3 s end-of-transfer guard and 300 ms minimum gap; flash write for every update.
Streaming (details `docs/streaming-plan.md`, `docs/hardware-prediction.md` section 1): the only live path in the app is the Wi-Fi camera stream (3 fps cap, 30 KB frames). Estimated bounds: Wi-Fi up to about 100 KB/s at the app limit (try 5 to 10 fps with 8 to 12 KB frames, untested); BLE nn20 no-ACK about 22 KB/s (1.5 to 2 fps for 12 KB frames), ACK mode about 9 KB/s, BadgeSdk 10 to 30 KB/s. Plan: use `rebeambox stream` on Wi-Fi models; on BLE-only models use pre-rendered 3 to 5 s animations or stills under 1 fps; phases and fallbacks (custom firmware only with recovery) are in the plan. Touch-driven features cannot be built from the documented protocol (section 4).
Ideas for improvement: a real-device transport probe command that auto-runs H1 to H2 and writes the report template; configurable pacing and MTU flags; asyncio-based Wi-Fi fps benchmark; hypothesis-based property tests; a minimal GUI after hardware validation.

## 10. Repository layout and key docs
```
rebeambox/            client package (see section 6)
tests/                software tests (test_*.py older, test_sw_*.py plan v1)
docs/                 all documentation (below)
scripts/              setup-tools.sh (tool install without sudo), spec_vectors.py (hex vectors)
tools/                emulate_jl_auth.py (unicorn, needs the .so which is not in the repo)
analysis/             SOURCES.md (APK provenance and hashes); apk/, decompiled/, work/ are git-ignored
ui/                   Node package manifest and node_modules only; not part of the Python client
pyproject.toml        package metadata, pytest options (slow marker deselected by default)
```
| Doc | Content |
|---|---|
| `README.md` | install, quick start, model and Wi-Fi sections, status |
| `docs/PROTOCOL.md` | byte-exact BLE protocols with evidence labels, auth, corrections from third-party reports, notification inventory |
| `docs/wifi-protocol.md` | Wi-Fi path |
| `docs/models.md`, `docs/pulse.md` | per-model analysis; Pulse equals NIKKO |
| `docs/software-test-v1.md`, `docs/hardware-test-v1.md`, `docs/first-session-checklist.md` | test plans and first session procedure |
| `docs/streaming-plan.md`, `docs/hardware-prediction.md` | streaming plan, bandwidth table, flaws, hardware prediction |
| `docs/SOP.md` | reverse-engineering procedure and tooling rationale (section 15) |
| `docs/problem_solution.md` | dated log of every problem (39 entries) |
| `docs/app-behaviour.md`, `docs/binaries.md`, `docs/ads-removal.md` | app screens and flows, shipped binaries, promotional surfaces |

## 11. Install and run
```
git clone https://github.com/THAI-passport/reBeamBox.git && cd reBeamBox
python3 -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .[dev]                                # bleak, Pillow, pytest, unicorn, pyelftools, capstone
# ffmpeg only for GIF/video: apt install ffmpeg | brew install ffmpeg | winget install ffmpeg
python -m pytest -q                                  # whole suite, no hardware
python -m pytest -q -m slow tests/test_sw_auth_fuzz.py   # larger auth fuzz
rebeambox send-image photo.jpg --model nikko --dry-run frames.txt --transport nn20   # no Bluetooth
rebeambox scan --all --timeout 15        # first contact with a badge, see docs/first-session-checklist.md
```
Environment switches for tests: `JL_AUTH_SO` (path to libjl_auth.so for the native fuzz; default `analysis/work/so/lib/arm64-v8a/libjl_auth.so`), `REBEAMBOX_FUZZ_N`, `REBEAMBOX_FUZZ_SLOW_N`, `REBEAMBOX_THAI_FONT`. Rebuilding the analysis tree (jadx, apktool, APK download) is scripted in `scripts/setup-tools.sh` and described in `docs/SOP.md`; the APK is not redistributed.
