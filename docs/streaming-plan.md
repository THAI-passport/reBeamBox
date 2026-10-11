# Phone-to-badge live streaming: implementation plan

Related documents: docs/PROTOCOL.md (what the stock protocol does), docs/hardware-prediction.md (hardware guess, flaws, throughput math). This file is the phased plan and does not repeat the analysis.

## Goal and definitions
Show a live feed (screen, camera, canvas or video) from the phone on the 360x360 round badge at the best achievable fps with bounded latency, ideally 8 to 12 fps over BLE and 20+ fps if Wi-Fi exists. "Stock firmware streaming" means using only the commands the original app uses.

## Assumptions to verify (each becomes a test)
1. The Beambox+ uses the BadgeSdk path (name NEO or B-Device, control service C2E6FD00 plus Jieli RCSP). Verify by scanning and reading the name and 0xFF advertising bytes (type 0xB3, shape 0x6D).
2. Jieli RCSP authentication can be reimplemented (libjl_auth.so). Verify by disassembly and a live handshake.
3. The badge supports DLE, 2M PHY and short connection intervals. Verify with PHY and interval callbacks and a throughput test.
4. The badge can accept a new file while showing the previous one, and can replace a file of the same name without a long pause.
5. The nn20 path's ACK frames can be used as credits (only if the badge is an nn20-family device).
6. Whether any Wi-Fi interface exists on the badge (look at the advertised services, the info reply function bytes, and whether a SoftAP appears).

## Phone app architecture
- Layers: capture (screen, camera, canvas) -> frame scheduler -> encoder -> packetiser -> link driver -> badge.
- Frame scheduler: latest-frame-wins single slot; target fps computed from measured throughput; drops stale frames.
- Encoder: JPEG with adaptive quality (q30 to q80) and optional downscale (240, 288, 360); corner masking to flat colour; reusing buffers; hardware JPEG where available. Alternative encoder: MJPEG AVI muxer for clip mode (write the small RIFF structure directly, no ffmpeg).
- Packetiser: pluggable (nn20 frames with the envelope; RCSP large file; custom future format). Spec in PROTOCOL.md.
- Link driver: BLE (bleak on desktop for development, Android BLE for the phone app), with metrics hooks (bytes per second, retries, ACK latency, connection parameters).
- UI: icons only (Lucide), no emoji.
- Tooling in this repo: Python reference client first (bleak, Pillow), then phone app (Kotlin or Flutter) reusing the verified protocol vectors in scripts/spec_vectors.py.

## Phases and milestones

### Phase 0: Evidence and capture (no new code)
- Obtain a badge (or borrow one), enable Android HCI snoop log, perform one still upload and one animation upload with the stock app, extract with Wireshark.
- Milestone: pcap showing the real GATT services, MTU, connection interval, PHY, and the exact bytes of one upload; confirm or correct PROTOCOL.md sections 2 and 3.
- Exit: decision which path (2 or 3) the target badge speaks.

### Phase 1: Stock-protocol still image client (reference, desktop)
- Implement scan, connect, upload JPEG for the chosen path using bleak and Pillow; unit tests against the byte vectors in PROTOCOL.md.
- Milestone: a still image appears on the badge; checksum, chunking and pacing match the vectors.
- Risk: Jieli auth is not yet recovered; fallback is to replay the stock app on a rooted device or implement auth after disassembly (see Phase 1b).
- Phase 1b: reverse libjl_auth (11 KB native, small) with Ghidra, or port the open Jieli algorithm; test against the badge.

### Phase 2: Animation and clip pipeline
- Build MJPEG AVI (path 3) or the 0x12345678 container (path 2) in pure Python; verify playback on the badge.
- Milestone: 3-second clip at 8 fps plays; measure upload time.

### Phase 3: Link tuning and benchmark harness
- Add connection priority high, MTU 512, DLE, 2M PHY requests; measure sustained write-without-response throughput with the stock file transfer and with synthetic data.
- Benchmarks: bytes per second at 1M versus 2M PHY, at 7.5 versus 15 versus 30 ms intervals, with 1, 4, 8 outstanding packets; packet loss and retry rate; battery drain per minute; phone CPU. Record in docs/benchmarks.md.
- Milestone: documented best settings and a measured payload rate.

### Phase 4: Stock-firmware pseudo-streaming
- Strategy A (single file overwrite): upload one JPEG repeatedly; measure per-swap latency and flicker.
- Strategy B (clip ring): upload short AVI clips (6 to 15 frames) back to back, two names alternating; measure gap between clips.
- Strategy C (nn20 only): stream type 6 frames repeatedly; use the no-ACK mode at 20 ms and measure fps.
- Milestone: sustained loop with fps, latency and flash-wear estimate; choose the best strategy.

### Phase 5: Adaptive encoder and phone app
- Closed-loop quality control, frame dropping, resolution scaling, corner masking; phone UI (device list, connect, preview, fps and latency display).
- Milestone: live screen mirror at the best measured fps with under 500 ms latency on stock firmware.

### Phase 6: Beyond stock (only if Phase 4 is inadequate)
- Options: Wi-Fi transport if the hardware has it; custom firmware via the Jieli OTA path; tile and delta codec; direct-draw command.
- Each option needs its own safety review: flashing unknown firmware can brick the badge, so require a recovery path (USB, ISP) and a spare unit first.

## Test and benchmark plan
- Unit tests: frame builders, checksums, CRC16 XMODEM, container builders against the hex vectors; chunking at several MTUs; round-trip parse of reply frames.
- Simulator: a software "fake badge" that parses frames and ACKs, to test flow control and failure injection (drop, reorder, delay) without hardware.
- Hardware tests: still upload success rate over 50 attempts; throughput matrix (PHY, interval, window); long-run stability (30 minutes streaming); distance and interference tests; battery drain curve.
- Metrics logged per run: fps, bytes per frame, glass-to-glass latency (camera pointing at phone and badge with a timestamp overlay), retries, disconnects.

## Risks and fallbacks
| Risk | Impact | Fallback |
|------|--------|----------|
| Jieli auth cannot be reproduced | No transfer on path 3 | Reverse the native lib; or drive the stock transfer library from a small Android helper |
| Badge refuses fast intervals or 2M PHY | Throughput cap about 20 to 30 kB/s | Lower resolution and quality; clip mode; accept 2 to 4 fps |
| File-based display has long swap time | Streaming looks like a slideshow | Clip ring, longer clips, or treat as "near-live" with 1 to 3 s delay |
| Flash wear from continuous rewrite | Shortened badge life | Overwrite a single file, limit session length, warn the user |
| Stock firmware cannot stream at all | No live mode | Slideshow mode with background upload; Wi-Fi if available; custom firmware only with a recovery path |
| Device-name path ambiguity | Wrong protocol on a given unit | Detect by services after connect (0x01F0 versus C2E6FD00) instead of by name |
| Legal and warranty | Interoperability use only | Keep the repo free of app code and assets; document only the protocol |

## Fallbacks if the stock firmware cannot stream
1. Rapid still updates (1 to 2 fps) with small JPEGs.
2. Short looping clips refreshed every few seconds (near-live).
3. Pre-render animations on the phone and upload once, driving content changes (clock, weather, status) rather than video.
4. Wi-Fi SoftAP transport only for models that have it (nn20 sibling product: 192.168.8.1:8080).
5. Custom firmware as a last resort, after Phase 0 to 4 evidence and with a recovery plan.


## Appendix: realistic fps and bandwidth, Wi-Fi versus BLE (added with the Wi-Fi analysis)
Numbers marked [C] come from app constants, [I] are arithmetic estimates for planning, none are measured on hardware.

| Path | Constraint from code | Payload per frame | Upper bound | Realistic target |
|---|---|---|---|---|
| Wi-Fi live camera (TCP 8080, docs/wifi-protocol.md) | [C] frames at least 300 ms apart (3.3 fps); JPEG 360 x 360 at quality 10, warn above 30720 bytes | 6 to 30 KB | [I] 30 KB x 3.3 = 100 KB/s (0.8 Mbit/s), well below Wi-Fi capacity | 3 fps proven by the app; try 5 to 10 fps with 8 to 12 KB frames [I]; the limit is probably the badge JPEG decoder and display refresh [U] |
| Wi-Fi file upload (POST /upload) | [C] 6144-byte chunks, 1 to 3 ms sleep per chunk | 15 to 400 KB container | [I] 6144 / 3 ms = 2 MB/s | a 100 KB animation in about 0.1 to 0.5 s; faster than BLE by 50x or more |
| BLE nn20 no-ACK mode | [C] 20 ms between packets, about 446 data bytes per packet at MTU 512 | 10 to 15 KB JPEG | [I] 446 / 0.02 = 22 KB/s | 1.5 to 2 fps for 12 KB stills, 0.5 fps for 30 KB |
| BLE nn20 ACK mode | [C] interval at least 50 ms, batches of 4, wait for GetPacketSuccess | same | [I] about 9 KB/s | under 1 fps |
| BLE BadgeSdk (RCSP file transfer) | [C] MTU negotiation, device-pulled blocks, CRC | same | [I] 10 to 30 KB/s | under 1 fps |

Conclusions:
1. Live video is only realistic over Wi-Fi: the app has a live frame path there and no live path over BLE.
2. For a Wi-Fi model, implement phase 4 strategy as `rebeambox stream` first (already in the client): measure real badge fps by raising `--fps` from 2 to 10 and watching the 0x007A/0x007B/0x007F replies and visual stutter.
3. For BLE-only models (Nano, Niji by third-party reports) the best is a slideshow: pre-render an animation and upload it once (3 to 5 s clips), or push stills at under 1 fps.
4. Keep the Wi-Fi frame under 30720 bytes regardless of what the badge tolerates; the client enforces this by lowering JPEG quality.
5. Check whether a given badge has Wi-Fi at all before planning around it: see docs/first-session-checklist.md, step 2 (scan for an `E-Badge` access point).
