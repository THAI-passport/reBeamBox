# Hardware prediction, flaws, and streaming design

Companion documents: docs/PROTOCOL.md (protocol spec), docs/streaming-plan.md (phased implementation plan). Tags: [C] Confirmed from code, [I] Inferred, [S] Speculative. Nothing here was measured on a real badge.

## 1. Live streaming from a phone: design

### 1.1 What the stock protocol gives us
- [C] BadgeSdk path (likely the Beambox+): stills are JPEG files, animations are MJPEG AVI files (frame spacing down to 30 ms, optional 16 kHz mono PCM audio), pushed as whole files through the Jieli RCSP large-file transfer into the badge's file system (libjl_fatfs is shipped). Transfer is pulled by the badge (offset and size requests) and CRC16 protected.
- [C] nn20 path: whole JPEG or frame-container uploaded as one enveloped stream over 0x01F1 with write-without-response, ACK batching.
- [C] No code requests a faster connection interval or the 2M PHY in the vendor code. The Jieli SDK exposes a preferred-PHY option but the app does not set it.
- [C] There is no streaming or "show this frame now" command anywhere. Display is always "store a file, then the badge plays it".

### 1.2 Throughput math
BLE payload rates (rule-of-thumb, Android phone, write without response, data length extension to 251 bytes):

| Setting | Realistic payload | Notes |
|---------|-------------------|-------|
| Stock nn20 ACK mode | 446 B per packet, 50 ms floor, batch of 4 plus ACK round trip: about 7 to 9 kB/s | Computed from code constants (2.6 of PROTOCOL.md) |
| Stock nn20 no-ACK mode | 446 B per 20 ms = about 22 kB/s | Upper bound of the code, not the radio |
| Tuned BLE 1M PHY, 7.5 ms interval, DLE | 60 to 100 kB/s | Depends on how many packets per connection event the badge controller allows |
| Tuned BLE 2M PHY | 100 to 170 kB/s | Needs BLE 5 on both ends [S that the badge has it] |
| Wi-Fi SoftAP or Direct (if the badge has Wi-Fi) | 500 kB/s to several MB/s | [C] only the sibling nn20 product has Wi-Fi code (192.168.8.1:8080); the BadgeSdk contains none |

Frame size budget for a 360x360 round panel (368 canvas):
- JPEG q90 photo: about 30 to 50 kB. q50: 10 to 16 kB. q35 at 240x240 source upscaled by the badge: about 4 to 6 kB. Round crop means about 21 percent of pixels are never shown, so the corners can be filled flat to save bytes (JPEG compresses flat areas almost for free) [I].
- Frame rate = throughput / frame size. At 20 kB/s: 1 to 2 fps. At 60 kB/s with 12 kB frames: 5 fps. At 120 kB/s with 6 kB frames: about 20 fps. Over Wi-Fi 20 to 30 fps is easy.
- Practical target on BLE: 8 to 12 fps at reduced quality (q40 to q55, 12 kB or less) with 2M PHY. 15 fps needs about 6 kB frames or delta coding. On the stock firmware, "streaming" is more realistically 2 to 4 fps stills or short clip batches.

### 1.3 Transport options (ranked)
1. **BLE, tuned link** (works on every unit): request connection priority HIGH (about 11.25 ms; 7.5 ms on newer Android), request MTU 512, rely on DLE (251), request 2M PHY (`setPreferredPhy`), use write without response with a credit window sized to the controller buffer (4 to 8 outstanding), and measure by echoing nothing: use the badge's ACK notifications as credits where available. The nn20 ACK frames (`GetPacketSuccess`) can serve as a credit system [C exists].
2. **Wi-Fi SoftAP / Wi-Fi Direct**: only if the badge hardware has Wi-Fi [S for BadgeSdk devices; C for the nn20 sibling]. A badge SoC that has audio and video decoders and a PCM audio path may have Wi-Fi, but the BadgeSdk has no Wi-Fi code, so assume no.
3. **Pseudo-streaming via clips**: pack K frames into a small MJPEG AVI (K = 6 to 15) and upload clips back to back; the badge plays one clip while the next uploads (needs two file slots or fast replace). Latency 1 to 3 s, fps limited by the clip time, but uses only supported commands [I, depends on whether the badge keeps playing the old file while a new one arrives].

### 1.4 Frame codec choices
- **JPEG per frame** (stock, always decodable): choose resolution, quality and chroma subsampling 4:2:0; crop corners to flat colour; strip metadata and use fixed Huffman tables (optimised tables are about 5 to 10 percent smaller).
- **MJPEG AVI clips** (stock for BadgeSdk): the badge already decodes this at up to 33 fps [C by the 30 ms floor]. Keep index (idx1) small; keyframes only, since MJPEG has no delta frames.
- **Delta or partial updates**: not supported by any command found [C]. Only possible with a modified firmware; options if firmware could be changed: tile-based JPEG (e.g., 8 tiles of 8 rows) or XOR-delta with run-length coding in RGB565, giving 3 to 10x savings for UI-like content [S].
- **Raw RGB565**: 360x360x2 = 259 kB per frame, impossible over BLE. Not used by the app [C].
- Audio: stock AVI path supports PCM 16 kHz mono (32 kB/s), which alone would use half of a 60 kB/s link; skip audio for streaming.

### 1.5 Buffering, flow control, latency budget
- Phone side: capture or render at the target fps, drop frames rather than queue (keep at most one pending frame), adapt JPEG quality with a controller driven by measured throughput (target frame time = frame bytes / measured rate).
- Link: a sliding window of N outstanding packets (N from 4 to 8), resend only on a missing ACK, no retransmit of stale frames (a newer frame supersedes).
- Latency budget at 8 fps, 12 kB frames, 80 kB/s: encode 15 ms, queue 0 to 100 ms, air time 150 ms, badge decode plus panel refresh (SPI/QSPI to a 360x360 panel, around 20 to 40 ms), total 200 to 350 ms glass to glass. On stock file-based firmware, add file close, parse and open time, estimated 200 to 1000 ms per swap [S].
- Power: radio at 7.5 ms interval and 2M PHY draws several mA continuously; a small badge battery (unknown, likely 100 to 200 mAh) gives 1 to 3 h of streaming [S].
- Flash wear: pushing frames as files writes hundreds of kB per second into NAND or NOR flash. Use one fixed file name rewritten in place or a RAM path if available [I, wear is a real risk].

## 2. Flaws in the current app and protocol design (grounded)

1. [C] **Whole-file upload only**: both paths require the complete JPEG, container or AVI before display; the nn20 envelope even ends with a closing brace sent in the last packet; no partial display or resume.
2. [C] **ACK batching with timid back-off**: batch of 4, falling to 2 and 1 after errors, 50 ms interval floor, 500 then 1000 ms retry waits, the third failure aborts the whole upload (S2 2026-10-12). Effective rate about 7 to 9 kB/s, so a 40 kB photo takes 4 to 6 s.
3. [C] **Fixed pacing instead of link-aware credit**: 10 to 20 ms timers are used regardless of connection interval, MTU or PHY; no requestConnectionPriority, no PHY request in vendor code.
4. [C] **No streaming mode or direct-draw command**; the only "mode" values are file types and animation_type.
5. [C] **JPEG-only**; no raw, indexed, delta or partial formats; the animation container repeats a full JPEG for every frame; AVI path adds a heavy ffmpeg dependency (about 20 MB of native FFmpeg libraries in the arm64 split).
6. [C] **Weak integrity on the nn20 path**: 8-bit two's complement checksum, no CRC, status carried as JSON text matched by substring (`GetPacketSuccess`), single-byte reply length (255 byte cap), two unused header bytes in replies.
7. [C] **Three incompatible transports** (nn20 BLE, BadgeSdk with two GATT connections, Wi-Fi socket) selected by device-name substring; "NEO" / "B-Device" name matching is brittle.
8. [C] **BadgeSdk uses two GATT links to the same device** (control service and Jieli RCSP) with a hard-coded 1550 ms wait before bind; the control writes use write-with-response and sleep 5 ms inside the GATT callback thread.
9. [C] **Resolution inconsistency**: 360 constants and 368 hard-coded scaling coexist; the badge reports its own size on the BadgeSdk path but the nn20 path does not ask.
10. [C] **End-of-transfer guard up to 3 s** and a 300 ms minimum gap between uploads add latency and make quick sequences impossible.
11. [C] **Free-space check uses an arbitrary 1 MiB margin (not 64 KiB, S2 2026-10-12)** and is skipped if the badge never reported space.
12. [C] **Flash writes for every update** (file-based) with no in-RAM display path, which hurts wear and speed.
13. [I] The status JSON on the nn20 path appears push-only (no explicit query found), so the app can start without knowing free space.
14. [C] The device id sent in bind is a hash of device model strings, not a random installation id; weak as an identity.

## 3. Prediction of the real badge hardware and its firmware

Evidence summary: the BadgeSdk bundles the Jieli (Zhuhai Jieli Technology, "JL") BLE SDK stack and file system library, the badge advertises an AD structure typed "baji" with a circle tag, there is an AVI MJPEG plus PCM path, audio libraries (Opus, Speex) for the same vendor SDK, and a custom control service on top.

- **SoC family**: [I] Jieli. Evidence: com.jieli.* RCSP classes, 0xAE00/AE01/AE02 service, libjl_auth, libjl_crc, libjl_fatfs, libjl_pack_format, `FAT_FS_ROOT` constant, large-file transfer commands, OTA classes. [S] a smartwatch-class part such as the AC79xx or JL701x/AC70xx series, because the transfer code is the "watch face / big file" flow used by Jieli smartwatch SoCs. Those chips have a hardware JPEG decoder (MJPEG playback is a core feature) and on-chip BLE 5.x with 2M PHY; exact model unknown.
- **BLE chip**: [I] the same Jieli SoC (single-chip). [S] BLE 5.0 or 5.1 capable, so DLE and 2M PHY are likely available but unused by the app.
- **Display controller and panel**: [S] a round 1.28 inch IPS or AMOLED, 360x360, driven over SPI or QSPI by a controller such as a ST77916 / GC9B71 / similar. Evidence only: app resolution constants 360 and 368 and `BadgeShape.CIRCLE`. The 368 canvas suggests the panel or the decoder works in 16-pixel blocks (JPEG MCU alignment: 368 = 23 x 16) [I]; the panel crop to 360 is then done by the firmware.
- **Flash**: [I] SPI NOR or NAND flash with a FAT file system (jl_fatfs) holding media files; free space is reported in KB by the 0xC7 reply and the nn20 JSON (`allspace`, `freespace`). [S] 4 to 16 MB class.
- **Firmware update path**: [C] the app contains the Jieli OTA stack (jl_bt_ota, libjl_ota_auth, nn20 type 2 "OTA package"); [I] updates are Jieli `.ufw` style images pushed over RCSP after the same auth handshake.
- **Badge-side parser (nn20 path)**: [I] a small state machine: look for 0xF1, read type, packet counters, length, data, verify checksum, append data to a RAM or flash buffer; after the last counter hits 0, parse the JSON envelope, extract "type", and store the payload into a file (type 5 or 6). The reply side builds a 0xA0 frame with JSON text. The counters (total, remaining) and the 255-byte reply cap suggest a fixed buffer, 8-bit length in replies, and JSON handled with a tiny string search for "type" and "animation_type".
- **Badge-side behaviour (BadgeSdk path)**: [I] standard Jieli file receive into the FAT volume, then a media player service picks the newest file (JPEG shows as still, AVI plays in a loop); the control commands (0x60 bind, 0xC6 info, 0xDA sizes, 0xDC file type) are handled by a vendor task layered on the second GATT service. The 0xDC ACK before starting the file transfer suggests the badge switches its storage path or player state according to the file type 0x0C.
- **Second parts**: [S] a battery fuel gauge (battery command 0x29), a button for the remote camera shutter (command 0x81 pushed by the device), and no microphone or speaker use in the Beambox flow.

## 4. What to verify first
See docs/streaming-plan.md, phase 0. In short: capture a real upload (Android HCI snoop log, Wireshark) to pick path 2 or 3, confirm 2M PHY and DLE support with `setPreferredPhy` and a throughput test, and learn whether the badge can display a file while another is being written.
