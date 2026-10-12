# Hardware Reconnaissance and Flash Endurance Checklist

> Executable version: the step-by-step task pack in [tasks/README.md](tasks/README.md) (software tasks S0 to S11 in `tasks/SW-RECON.md`, hardware tasks HW-0 to HW-17 in `tasks/HW-RECON.md`) supersedes the procedures below for day-to-day work; this document stays as background for the teardown and flash-endurance reasoning. Known corrections: the only FCC spelling that exists is `2BR3T-BAGDE0`; a discrete SOIC flash may not exist (flash reported inside the SoC package); the H8 rewrite test needs `--no-delta`.

> Cross-reference (added 2026-10): public findings that overlap this checklist are collected in [recon-web.md](recon-web.md) (FCC filing contents, chip and flash reports from third-party teardowns, firmware layout). On fccid.io only `2BR3T-BAGDE0` exists; `2BR3T-BADGE0` returned 404, so treat it as a spelling variant. The filing lists a Bluetooth band only (no Wi-Fi) and keeps the block diagram, schematic and parts list confidential.

Audience: Embedded engineers and autonomous agents working with physical Beambox hardware.

Repository Context: reBeamBox (commit post-1b84ecd).

Target Models: NIKKO (Pulse, primary), NANO (Lite), NIJI.

Evidence Labels: [C] Confirmed from code/disassembly, [I] Inferred, [W] Third-party reported, [U] Unknown.

## 1. Purpose and Scope

This checklist defines the empirical verification process for physical Beambox e-badges. While the client codebase (`rebeambox`) passes full software simulation, physical validation is required to determine flash wear limits, exact transport bindings, and real-time streaming viability.

### What This Checklist Proves

- **Transport Identity:** Definitively identifies whether NIKKO/Pulse utilizes `0x01F0` (nn20), BadgeSdk/RCSP, or a Wi-Fi raw socket.
- **Flash Wear Characteristics:** Measures how the firmware allocates incoming frames (direct sector overwrite vs. append-only circular buffer vs. RAM buffering) to evaluate storage degradation risks.
- **Physical Hardware Stack:** Identifies the SoC model, flash part number, screen controller, and operating rail voltages.

### What This Checklist Will Not Prove

- Long-term silicon endurance over 100,000 cycles (must be evaluated against component datasheets).
- Proprietary JieLi closed-source bootloader internals beyond observable external behaviors.

### What This Unlocks: Decision Matrix

| Missing Hardware Fact | Measurement Method | Architecture Decision Enabled |
|---|---|---|
| Active BLE Transport | `probe --qualify` | Locks default client link stack (nn20 vs. rcsp). |
| Accepted Still Container | Test write Type 5 vs. Type 6 | Selects optimal image container format (no dummy frames). |
| Flash Endurance & Part | IC markings / JEDEC ID (`0x9F`) | Establishes safe client upload rate limits (P/E cycle budget). |
| RAM Framebuffer Presence | Memory status delta during Wi-Fi streaming | Determines whether live mobile screen mirroring is possible. |
| Native Panel Resolution | Status JSON vs. test pattern display | Sets definitive canvas crop bounds (360x360 vs. 368x368). |

## 2. Safety and Prerequisites

### Hardware and Tooling Requirements

- **Software Tools:** `rebeambox` CLI (latest `main`), Chromium browser (Web Bluetooth UI), Wireshark, Android device with Developer Options enabled.
- **Electronics Lab Equipment:** Digital Multimeter (DMM), variable lab power supply (optional), ESD-safe mat and wrist strap.
- **Disassembly Tools (Destructive Track):** Plastic guitar picks/spudgers, heat gun or thermal pad (controlled to 60C-70C), Isopropyl Alcohol (IPA > 99%).
- **ROM/Flash Tooling (Destructive Track):** CH341A USB programmer (or Raspberry Pi/ESP32 running `flashrom`), 1.8V bidirectional level shifter adapter, Pomona SOIC-8 test clip or WSON-8 probe needles.

### Safety Gates

- **Lithium Battery Warning:** The badge contains a pouch LiPo cell directly behind the electronics. Never use metal tweezers, scalpels, or excessive heat near the pouch. Disconnect or desolder the positive battery lead immediately upon opening the casing.
- **Voltage Rail Safety:** Wearable NOR flash commonly runs on 1.8V logic. Never attach a 3.3V/5V programmer without first measuring the flash chip's VCC with a multimeter while the device is on.

## 3. Non-Destructive Software Probes (Phase 1)

Execute these steps first. No disassembly or physical tools required.

```
[Phone / PC] <---- BLE / Wi-Fi ----> [Unopened Beambox Badge]
```

### Procedure 3.1: Automated Transport Qualification

Run the integrated qualification runner against the badge:

```bash
rebeambox probe --qualify --model nikko --wait 15
```

- **Step 1:** Review the generated report in `reports/first-contact-<timestamp>.md`.
- **Step 2:** Inspect the classified GATT services:
  - If Service `0x01F0` is present: Badge belongs to the nn20 transport family.
  - If Service `C2E6FD00...` and `0xAE00` are present: Badge uses BadgeSdk (Jieli RCSP).
- **Step 3:** Record negotiated MTU. Note whether it accepted 512 bytes or defaulted to a lower platform threshold (e.g., 23, 185, 247).

### Procedure 3.2: Wi-Fi Presence Survey

- **Step 1:** Scan for local Wi-Fi SSIDs using your host machine or phone.
- **Step 2:** Note any open or secured network matching `E-Badge*` or `Nikko*`.
- **Step 3:** If found, associate with the network and probe the standard gateway:

```bash
curl -I http://192.168.8.1:8080/
```

Note whether the socket opens or returns an HTTP handshake.

### Phase 1 Verification Template

| Parameter | Measured Value | Evidence Label |
|---|---|---|
| Advertised Device Name | ____________________ | [C] |
| BLE MAC Address (Masked) | AA:BB:CC:__:__:__ | [C] |
| Exposed GATT Services | ____________________ | [C] |
| Negotiated ATT MTU | ________ bytes | [C] |
| Initial Reported Status | freespace: _____ KB, allspace: _____ KB | [C] |
| Wi-Fi SSID Detected | Yes (____________) / No | [C] |

## 4. Controlled Write and Wear Tests (Phase 2)

Execute limited, counted writes to inspect flash allocation behaviors without exceeding safe write limits.

### Procedure 4.1: Still Image Container Test (H2)

Test whether the badge accepts standard IMB still containers (Type 6) or requires a 1-frame animation container (Type 5):

- Transmit a known 360x360 solid red image using the Type 5 container:

```bash
rebeambox send-image red.png --transport nn20 --nn20-still gif
```

- Inspect the screen. Note if displayed.
- Transmit a known 360x360 solid blue image using the Type 6 IMB container:

```bash
rebeambox send-image blue.png --transport nn20 --nn20-still album
```

- Inspect the screen. Note if displayed or ignored.

### Procedure 4.2: Flash Allocation and Rewrite Check (H8)

- Record `freespace` from the status notification payload.
- Upload a 50 KB image file.
- Read and record the updated `freespace` value.
- Immediately upload the exact same 50 KB image file a second time.
- Read and record the final `freespace` value:
  - **Outcome A (In-place overwrite):** `freespace` remains identical to step 3. Indicates a static slot or overwrite model.
  - **Outcome B (Append-only / Log allocation):** `freespace` drops by an additional ~50 KB. Indicates circular logging / wear leveling.

### Procedure 4.3: Power-Cycle Volatility Check (H9)

- Power cycle the badge (hold power toggle or disconnect battery).
- Check whether the last uploaded frame displays immediately upon boot.
- If the frame is lost, the badge relies on a temporary volatile buffer; if retained, it commits directly to non-volatile flash.

## 5. Non-Destructive Physical and RF Survey (Phase 3)

Perform external and non-destructive visual checks.

### Procedure 5.1: Regulatory Filings Review

Before opening the chassis, inspect public FCC documentation for FCC ID `2BR3T-BADGE0` (also seen as `2BR3T-BAGDE0` in some listings; verify both):

- Download official Internal Photos, Schematics, and Parts List/BOM exhibits if unsealed.
- Cross-reference component placements before applying mechanical force.

### Procedure 5.2: External Enclosure Inspection

- Check for exposed casing screws (Torx/Phillips) vs. ultrasonic welds vs. adhesive bezels.
- Identify microphone/speaker pinhole locations and USB-C port pinouts (measure if CC pins have 5.1kOhm pulldowns).
- Inspect the kickstand and magnetic mounting ring for access seams.

## 6. Internal Hardware Inspection (Phase 4 - Destructive Track)

```
[Spudger / Heat] ---> [Pry Bezel] ---> [Disconnect LiPo] ---> [Inspect IC Markings]
```

### Procedure 6.1: Enclosure Disassembly

- Apply gentle heat (maximum 60C) to the perimeter bezel to soften adhesive.
- Insert a thin plastic guitar pick into the outer seam. Work around the circumference; do not use metal blades.
- Slowly lift the rear assembly. Stop immediately if resistance is felt. Watch for display ribbon cables or LiPo wiring.
- **Mandatory Step:** Desolder or unplug the battery ground connection before proceeding.

### Procedure 6.2: Component and Silicon Identification

Record markings directly from silicon packages using a macro lens or digital microscope:

| Component Role | Package Style | Marking / Text | Identified Part Number |
|---|---|---|---|
| Main SoC / MCU | QFN / BGA | ____________________ | JieLi BR28 / AC701N series [U] |
| SPI Flash (if discrete) | SOP-8 / DFN-8 | ____________________ | ____________________ |
| Display Driver (FPC) | COG / Ribbon | ____________________ | ST7789 / GC9A01 / CST816 [U] |
| Power Management (PMIC) | SOT-23 / QFN | ____________________ | ____________________ |
| Antenna Layout | PCB Trace / Ceramic | ____________________ | Inverted-F / Monopole [U] |

### Procedure 6.3: Voltage Rail Verification

- Reconnect a current-limited bench power supply set to 3.8V to the battery pads.
- Power on the board.
- Measure voltage with a DMM across:
  - Flash Pin 8 (VCC) to Pin 4 (GND): _______ V (Must confirm 1.8V vs. 3.3V).
  - Core logic rail: _______ V.
  - Display backlight anode: _______ V.

## 7. Firmware Acquisition and Dump (Phase 5 - Advanced)

Attempt acquisition methods from lowest to highest risk.

```
Method A (OTA Intercept) ---> Method B (Test Pads) ---> Method C (In-Circuit Clip) ---> Method D (Desolder)
   [Zero Risk]                   [Low Risk]                 [Medium Risk]                 [High Risk]
```

### Option A: OTA Package Capture (Zero Risk)

- Run the official vendor app on an Android device configured with HTTP proxy logging (mitmproxy/Burp Suite).
- Check if the app checks for firmware updates.
- If an OTA image is pulled, save the raw binary, hash it, and inspect the header structure.

### Option B: Debug Test Pad Interrogation (Low Risk)

- Locate unpopulated PCB test pads (often labeled DP, DM, PRG, TX, RX, GND).
- Connect a logic analyzer set to 24 MS/s during boot.
- Check for UART debug logging (test baud rates: 115200, 921600, 1000000, 2000000).
- If a single-wire JieLi debug protocol (PRG) is present, document pad positions.
- Note: JieLi BR28/AC701N-series chips use proprietary Pi32 cores and do not expose standard ARM SWD/JTAG.

### Option C: In-Circuit SPI Flash Dump (Medium Risk)

- **Prerequisite:** Battery must be fully disconnected.
- Verify flash operating voltage (VCC) from Phase 6.3.
  - If 1.8V: You must insert a 1.8V level shifter adapter between the programmer and the chip.
- Attach an SOIC-8 clip or micro-grabbers to the flash pins.
- Run `flashrom` via CH341A:

```bash
flashrom -p ch341a_spi -r dump_run1.bin
flashrom -p ch341a_spi -r dump_run2.bin
```

- Compare file hashes:

```bash
sha256sum dump_run1.bin dump_run2.bin
```

  - **Requirement:** Hashes must match identically. If they differ, bus contention is occurring; hold the SoC reset line to GND or desolder the flash chip.

### Option D: Desolder and Socket Read (High Risk / Last Resort)

- Apply Kapton tape over surrounding passive components and the display connector.
- Use a hot-air rework station at 320C-340C with flux to lift the 8-pin flash package.
- Place into an external SOP-8/WSON-8 ZIF programmer socket and dump clean binary.
- Solder the chip back cleanly using fresh solder paste.

## 8. Firmware Analysis and Binary Inspection

Once a valid binary dump (`flash_dump.bin`) exists, extract storage parameters.

### Analysis Procedure

- **Identify Partition Table:**

```bash
binwalk -B flash_dump.bin
strings -a -n 8 flash_dump.bin | grep -E "app|boot|font|res|anim|fat|littlefs"
```

- **Determine File System Format:** Check whether the media region uses a recognized embedded filesystem (LittleFS, SPIFFS, FAT12/16) or a flat raw-offset image array.
- **Inspect Display Initialization:** Locate SPI initialization sequences (look for typical LCD setup byte chains: `0x11` Sleep Out, `0x29` Display On, `0x3A` Pixel Format).
- **Locate Undocumented Commands:** Search for command dispatch tables handling BLE `0x01F1` or Wi-Fi `:8080` to identify hidden direct-draw or RAM-only display primitives.

## 9. Hardware Mitigation Options (Design Reference)

| Strategy | Feasibility | Risk | Impact |
|---|---|---|---|
| Client-Side Upload Throttling | Ready (Implemented) | None | Enforces minimum interval between rewrites; prevents flash wear out. |
| Delta Checking | Ready (Implemented) | None | Client hashes current frame and skips uploads if identical to active badge face. |
| Higher-Endurance NOR Swap | Difficult (Requires Match) | High | Swapping chip requires identical JEDEC ID support in bootloader ROM and matching QE bits. |
| RAM Framebuffer Streaming | Dependent on Phase 8 findings | Medium | If RAM buffer write exists, custom software can stream live video without touching flash. |

## 10. Traceability: Mapping to Existing Test Suite

Map these reconnaissance procedures to the test cases in `docs/hardware-test-v1.md`:

- **H1 (Scan and Discovery):** Covered by Section 3.1 (`probe --qualify`).
- **H2 (Display Mode Verification):** Covered by Section 4.1 (Type 5 vs Type 6).
- **H3 (Authentication Interrogation):** Covered by Section 3.1 (Handshake inspection).
- **H4 (BLE Throughput and MTU):** Covered by Section 3.1 and Phase 2 write benchmarks.
- **H5 (Wi-Fi Socket and Frame Stream):** Covered by Section 3.2 (HTTP/TCP probe).
- **H8 (Flash Allocation and Free-Space Delta):** New test covering Section 4.2.
- **H9 (Non-Volatile Persistence Verification):** New test covering Section 4.3.

## Provenance

This document incorporates an external technical review of `HARDWARE-RECON-TASK.md`, including:

- Mandatory 1.8V rail measurement and level-shifter requirement before SPI clipping.
- Battery disconnect / reset-hold to avoid bus contention during in-circuit dumps.
- JieLi single-wire debug (PRG / USB_DP/DM) instead of assuming ARM SWD/JTAG.
- Plastic pry tools and IPA for LiPo pouch safety.
- FCC ID review (`2BR3T-BADGE0` / `2BR3T-BAGDE0`) before opening a unit.
- Formal H8 and H9 wear tests based on `freespace` deltas and power-cycle persistence.
