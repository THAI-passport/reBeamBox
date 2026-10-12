# Beambox reverse engineering reference (imported)

> Imported 2026-10-12 from an external write-up. Treat as `[W]` (third-party) except where PROTOCOL.md already confirms the same statement. Where it disagrees with `docs/PROTOCOL.md` or `docs/FACTS.md`, those win. The tags inside the document below are the author's, not ours.
>
> Reconciliation (check each against the code when the decompiled tree is available, then fix PROTOCOL.md/FACTS.md and delete the row):
>
> | Statement in this document | Repo position | Action |
> |---|---|---|
> | Minimum inter-upload delay of 300 ms `[C]` | 300 ms is the app's Wi-Fi camera frame spacing; BLE flash writes are guarded at 30 s minimum and 50 per day (`docs/safe-write.md`) | Keep the guard; do not cite 300 ms for BLE stills |
> | Firmware has no direct-draw framebuffer command `[C]` | The Wi-Fi camera mode looks like a RAM display path `[I]` (`docs/wifi-protocol.md`) | Leave `[I]`; settle with HW-12 |
> | Battery 150 to 300 mAh | Retail and teardown say 450 to 500 mAh `[W]` (`docs/models.md`) | FACTS.md section 6 owns it |
> | Panel "360x360 physical" | Nano reported as 454x454 AMOLED behind a 360 buffer `[W]`; owner says Pulse is 1.8 inch | FACTS.md sections 1 and 2 own it |
> | H9: non-persistence "proves an SRAM framebuffer bypass" | Overreach: a lost picture can also mean a reset slot or default image | Use the HW-8 interpretation table |
> | Flash "8 to 16 MB", 100,000 P/E cycles | 16 MiB reported `[W]`; endurance is a typical datasheet figure `[I]`, wear levelling unknown | FACTS.md section 4 |
> | "NIKKO defaults to 368" `[C]` | nn20 falls back to 368 only when the badge reports nothing; the badge-reported size wins | FACTS.md section 2 |
> | Type 5 for all stills | Matches our default (`--nn20-still gif`), based on a Niji report `[W]` | HW-5 settles per model |

---

# Beambox Reverse Engineering Technical Reference

Audience: Embedded engineers, security researchers, and autonomous software agents.
Repository Context: `reBeamBox` (clean-room client implementation).
Evidence Taxonomy: [C] Confirmed via decompilation/disassembly, [I] Inferred logic, [W] Third-party reported from hardware, [U] Unknown pending physical capture.

---

## 1. Executive Summary and Architecture Overview

The Beambox e-Badge series comprises wearable circular e-badges controlled via the Android companion application `com.guangshen.beambox` (version 1.0.14, versionCode 24). The hardware functions as an active digital display badge for still images, multi-frame animations, scrolling text, and short video clips.

### Product Matrix

| Model Identifier | Commercial Marketing | Physical Display | Confirmed Distinctions |
| :--- | :--- | :--- | :--- |
| **NIKKO** | Beambox e-Badge Pulse | 1.83-inch circular LCD [W] | Primary flagship; 3-second retail video duration cap; defaults to 368x368 canvas [C]. |
| **NANO** | Beambox Lite / Essential | Circular LCD | Compact pin/keychain enclosure; advertises as `Nikko-badge(BLE)` under USB power [W]. |
| **NIJI** | Specialist Model | 1.53-inch circular touch LCD | Larger internal cell; app forces a 5-second video trim window (vs. 10 s default) [C]. |

*Note on Product Identification:* The string "Pulse" does not exist in the Android client code [C]. Hardware models are identified via a remote server catalog (`api/app/badge/select-badge`) mapping `deviceName`, `signalName`, and `deviceType` (`BT` vs. `WiFi`) [C].

---

## 2. Hardware Architecture & Silicon Stack

### 2.1 Microcontroller and Storage Topology
* **Primary Processor:** JieLi (Zhuhai Jieli Technology) BR28 / AC701N family SoC [W]. Proprietary 32-bit Pi32 RISC architecture.
* **Non-Volatile Storage:** External SPI NOR Flash (typically 64 Mbit to 128 Mbit / 8 MB to 16 MB) [W].
* **Logic Levels & Power:** Logic rails and flash $V_{CC}$ commonly operate on a **1.8V rail** to minimize wearable power draw. A rechargeable lithium-polymer pouch cell (150–300 mAh) is adhered directly behind the display/PCB assembly.
* **Display Engine:** 360x360 physical panel resolution; software scales and packs images to a 368x368 coordinate boundary with circular alpha masking [C].

### 2.2 Storage Endurance & Flash Wear Hazards
1. **Direct-to-NOR Commits:** Every incoming BLE/Wi-Fi image payload is committed directly to external SPI NOR flash [C]. The vendor firmware does not expose an in-memory direct-draw framebuffer command [C].
2. **Endurance Ceilings:** Standard budget SPI NOR flash (Puya, BoyaMicro, XT25F) is rated for approximately $100,000$ Program/Erase (P/E) cycles per sector. High-frequency automated streaming over BLE will exhaust sector endurance rapidly.
3. **Client Mitigation Controls:**
   - Enforce mandatory client-side frame hashing (skip upload if image hash matches current display).
   - Enforce a minimum inter-upload delay of at least 300 ms [C] (recommended: 60+ seconds for automated widgets).
   - Track total write counts in client session state.

---

## 3. Communication Transports & Wire Protocols

The vendor companion app multiplexes across three distinct transport implementations based on device name heuristics and server records [C]:

```
[Advertised Name Scan]
       |
       +---> Contains "NEO" or "BDEVICE" -----> BadgeSdk (Jieli RCSP via dual GATT)
       |
       +---> Matches Product Signal Name -----> nn20 Protocol (Service 0x01F0)
       |
       +---> Server record deviceType=WiFi ---> Wi-Fi SoftAP Socket (192.168.8.1:8080)
```

### 3.1 nn20 BLE Transport (Service `0x01F0`)
Primary transport for NN-family hardware (NIKKO, NANO, NIJI) [W].
* **GATT Profile:** Service `0x01F0`, Write Characteristic `0x01F1` (`WRITE_NO_RESPONSE`), Notification Characteristic `0x01F2` (`NOTIFY`).
* **MTU:** App requests ATT MTU 512 (fallback to 23) [C].
* **Frame Header (Big Endian):**
  $$\text{Frame} = [\mathtt{0xF1}] \,|\, [\text{Type}] \,|\, [N_{u16}] \,|\, [\text{Remaining}_{u16}] \,|\, [L_{u16}] \,|\, [\text{Data}_L] \,|\, [\text{Checksum}]$$
  $$\text{Checksum} = (0 - \sum \text{preceding bytes}) \pmod{256}$$
* **Payload Types:**
  - `0x05`: Animation container (multi-frame GIF, carousel, video).
  - `0x06`: Album still image (IMB container).
  - `0x0D`: JSON command parameter (e.g., `{"animation_type": 1}`).
* **Payload Envelope:** Data for types 5 and 6 is enclosed in an ASCII envelope: `{"type": T, "data": <binary_container>}` [C].
* **Chunking Formula:** Packet data length $P = \min(446, \max(23, \text{ATT MTU}) - 12)$. Total packet size is $P + 9$ bytes, guaranteeing it fits within a single unfragmented ATT write [C].
* **Status Notification (`0x01F2`):** Frame starts with `0xA0`, length byte, UTF-8 JSON payload, and two's-complement checksum. Pushes `allspace`, `freespace` (KB), `time_mode`, `devname`, `brand`, `type`, and `size` [C].
* **Flow Control Modes:**
  - `time_mode = 1`: No-ACK loop mode. Writes pushed back-to-back at 20 ms intervals [C].
  - `time_mode = 0`: ACK mode. Packets transmitted in batches of 4 (adaptive 4, 2, 1) with minimum 50 ms spacing, waiting for `GetPacketSuccess` JSON notifications [C].

### 3.2 BadgeSdk / Jieli RCSP Transport
Legacy or alternate pin-badge path ("baji" tag `0xB3`, circular shape `0x6D`) [C].
* **GATT Profile:** Control Service `C2E6FD00-E966-1000-8000-BEF9C223DF6A` (Notify `FD01`/`FD03`, Write `FD02`). RCSP File Transport Service `0xAE00` (Write `0xAE01`, Notify `0xAE02`).
* **Authentication ($E_1$ on SAFER+):** Raw challenge-response on `0xAE01`/`0xAE02` using Bluetooth legacy authentication $E_1$ based on SAFER+ [C].
  - Default Key: `06775f87918dd423005df1d8cf0c142b` [C].
  - Default BD_ADDR: `112233332211` [C].
* **File Delivery:** RCSP binary framing (`FE DC BA ... EF`) pulling chunks via `LargeFileTransferOp` (`0x1D`). Transmits plain JPEG or MJPEG AVI (created via ffmpeg `-c:v mjpeg -q:v 5`), not custom containers [C].

### 3.3 Wi-Fi TCP SoftAP Transport
* **Network:** Badge operates as a Wi-Fi Access Point (SSID containing `E-Badge`, gateway `192.168.8.1`).
* **Control Port:** TCP port 8080 [C].
* **Live Camera Stream:** Binary frame streaming using 2-byte big-endian control words (`0x0079` start, `0x007B` active, `0x007F` stop). Frame payload: `[length_u16][JPEG 360x360 q10][00 00]`. Maximum frame size: 30,720 bytes; minimum pacing: 300 ms (capped at 3.3 fps) [C].
* **File Upload:** Secondary TCP socket handling HTTP `POST /upload` with custom header `X-Filename: NN.bin` delivering containers in 6,144-byte chunks [C].

---

## 4. Binary Media Containers

### 4.1 Type 6: IMB Still Container (36-Byte Header)
Little-endian binary format preceding the raw JPEG:
```
Offset 0x00: 49 4D 42 00 ("IMB\0")
Offset 0x04: 04 00 00 00 (Format version 4)
Offset 0x08: u32 (jpeg_len + 32)
Offset 0x0C: 0B 00 00 00 (Format flag 11 = JPEG)
Offset 0x10: u16 width (368 if 368, else 360)
Offset 0x12: u16 height (368 if 368, else 360)
Offset 0x14: 24 00 00 00 (Data offset 36)
Offset 0x18: u32 jpeg_len
Offset 0x1C: 00 00 00 00 00 00 00 00 (Reserved 8 bytes)
Offset 0x24: Raw JPEG stream...
```
*Field Finding [W]:* Multiple real NN-family badges ignore Type 6 IMB containers and display a black screen. **Always wrap static images in a 1-frame Type 5 animation container by default.**

### 4.2 Type 5: Animation Container (Magic `0x12345678`)
Little-endian multi-frame format:
```
Offset 0x00: 78 56 34 12 (Magic 0x12345678)
Offset 0x04: u32 address_list_len (N * 16 + 24 on BLE; N * 16 + 32 on Wi-Fi)
Offset 0x08: u32 frame_count (N)
Offset 0x0C: u32 interval_ms
Offset 0x10: 12-byte ASCII string ("output/<ms>ms", zero-padded)
Offset 0x1C: u32 total_file_length_minus_1
Offset 0x20: Frame table [N entries, 16 bytes each]:
             - 12-byte ASCII name ("frame_%05d.")
             - u32 absolute file offset to frame record
Offset ... : Frame records back-to-back:
             - u32 self_offset
             - u32 next_frame_offset (last frame points back to frame 0)
             - 0B 00 (Format 11 = JPEG)
             - 00 00 (Reserved)
             - u16 width, u16 height
             - u32 data_offset (self_offset + 32)
             - u32 jpeg_len
             - 00 00 00 00 00 00 00 00 (Reserved 8 bytes)
             - Raw JPEG bytes...
```

---

## 5. Reverse Engineering & Hardware Qualification Protocols

### 5.1 Non-Destructive First Contact (`rebeambox probe --qualify`)
Execute upon initial delivery before running large media writes:
1. Performs passive BLE advertisement scan.
2. Connects and enumerates all GATT services and characteristics.
3. Subscribes to `0x01F2` (nn20) or reads `0xC6` (BadgeSdk) passively without initiating transfers.
4. Outputs structured Markdown report to `reports/first-contact-<timestamp>.md`.

### 5.2 Flash Wear Qualification Tests (H8 & H9)
* **Test H8 (Allocation Geometry):** Query `freespace` via status JSON. Upload a 50 KB image. Note `freespace` delta. Re-upload the exact same 50 KB image.
  - If `freespace` is unchanged: Firmware overwrites fixed slots in place.
  - If `freespace` decreases by 50 KB: Firmware operates an append-only circular log (wear leveling active).
* **Test H9 (Buffer Volatility):** Upload test frame, disconnect battery power, reboot. Check if image persists on LCD. Non-persistence proves an SRAM framebuffer bypass exists.

### 5.3 Bench Safety Protocol (Physical Teardown)
* **LiPo Cell Isolation:** Do not use metal blades or tweezers along casing seams. Use plastic spudgers and 60°C thermal loosening. Disconnect battery ground wire immediately upon popping case.
* **Voltage Verification:** Wearable flash frequently runs on **1.8V**. Probe Pin 8 ($V_{CC}$) to Pin 4 (GND) with a multimeter. Connecting a 3.3V or 5.0V programmer directly will permanently damage the SoC SPI controller.
* **Bus Contention:** When clipping SPI flash in-circuit, tie the SoC reset pin to GND to prevent the JieLi MCU from waking, back-powering via clamping diodes, and asserting signals on MISO.