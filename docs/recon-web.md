# Web reconnaissance (2026-10)

Public sources only: no vendor backend was contacted, no firmware was downloaded, nothing was bought. Labels: **C** confirmed by our own code reading, **I** inferred by us, **W** a claim made by a third-party source that we have not verified on hardware (the source is named; a W claim from one source is weak evidence). Dates are 2026 unless stated.

Related documents: [models](models.md), [hardware-recon-checklist](hardware-recon-checklist.md), [hardware-test-v1](hardware-test-v1.md), [PROTOCOL](PROTOCOL.md), [safe-write policy](safe-write.md), [compatibility matrix](compatibility-matrix.md).

## 1. Sources

| Id | Source | What it gave |
|----|--------|--------------|
| S1 | fccid.io page for `2BR3T-BAGDE0` (FCC.gov mirror) | grantee, exhibits list, rule parts, power |
| S2 | Zenn series by Saqoosha, "Building Custom Firmware for a Round Electronic Badge" parts 1 to 7 (zenn.dev/saqoosha, 2026-08), NANO unit | chip, flash, panel, firmware layout, stock BLE path |
| S3 | lilting.ch, "Beambox Niji Badge over BLE without the app" (2026-07-03), NIJI unit | box specs, GATT table, frame and container layout, type 5 versus 6 |
| S4 | Lazada Thailand listing "beambox e-Badge Pulse" (THB 1,290, 17 ratings) | Thai retail listing |
| S5 | beambox.my Nikko page, DROIX Global Nikko product page, beambox.site Nikko page | Nikko specification |
| S6 | github.com/jumpingmushroom/e87_badge, hybridherbst/web-bluetooth-e87, Manaiakalani/auracast, a gist for "JieLi AC7076A E-Badge (E01)" | open-source clients for related Jieli badges |

## 2. FCC filings: 2BR3T-BAGDE0 and 2BR3T-BADGE0

- [W, S1] Only `2BR3T-BAGDE0` exists on fccid.io (the product code spells "Bagde"; equipment class "E-Bagde"). The spelling `2BR3T-BADGE0` returned 404 on the same site, so it is a mis-spelling of the same ID in our sources; both strings stay in the checklist so a reader can try either. Grantee code 2BR3T, applicant Avatronics Corporation Limited, Shenzhen (Nanshan District), granted 2025-09-28 by a TCB (KL-Certification GmbH), test lab Guangdong Asia Hongke Test Technology.
- [W, S1] Band 2402 to 2480 MHz only, rule part 15C, peak conducted output 0.0005 W (0.5 mW). No Wi-Fi band is listed, which is evidence that the certified unit has Bluetooth only [I]; a unit with a Wi-Fi access point would need a 2.4 GHz Wi-Fi entry (15C DTS or 15E) in the same filing.
- [W, S1] Exhibits listed: user manual, external and internal photos, label location, test setup photos, Bluetooth test report and RF appendix, antenna specification, RF exposure, a "Declaration Letter of Model Difference". Block diagram, schematic, operational description and parts list are listed as confidential (metadata only), so there is no public BOM. The model-difference letter and internal photos PDFs were not downloaded by us.
- [W, S2] The internal photos show a gold "JL" QFN chip; the photographed board is the Nikko revision (`YH-GS2501-V0.2`) while the author's Nano was `YH-GS-NANO-V0.2` dated 2025-12-22. The model family shares one radio design.
- [W, S2] The technical-conformity number `219-259667` (Thailand-style label) lists Nano-Badge, Nikko-Badge, Niji-Badge and Neo-Badge under one holder. "Neo" explains the `NEO` name filter in the app [I].

## 3. Hardware facts reported by teardowns

All from S2 (Nano unit) unless noted; they are W until one of our units agrees.
- SoC: JieLi BR28 (AC701N), reported by a SCSI INQUIRY ("BR28", "UDISK") and cross-checked in the open `jl-uboot-tool` chip table. The author first guessed BR30/AC697N from the photo and was wrong, which is a reminder to read the part from the device.
- Flash: 16 MiB SPI NOR (JEDEC id 0x5E4018, Zbit ZB25VQ128 class) on SPI0 inside the package (the unpopulated SOP-8 pad `U4` has no ground continuity); the flash read back byte-identical to the factory image. Layout: boot and app code first, then resources, then a FAT16 gallery volume (`PIC1.BIN` and similar, cluster to flash address = 0x186000 + (cluster - 2) x 4096).
- USB: VID 0x4C4A, PID 0x4155, a mass-storage "BR28 UDISK" with no media while charging (S3 on Niji, S2 on Nano). Holding the button shows a USB icon and the badge enumerates as UDISK, then can be reset into "BR28 UBOOT1.00" (the Jieli download mode). Charging-only for users.
- Panel (Nano): a 454 x 454 round AMOLED, SH8601A controller, QSPI wiring with the factory firmware using single-line writes; the 360 x 360 frame buffer is the centre, corners fall outside the circle (radius 227, corner distance 254.6) [W, S2]. Frame header says 360 x 360 while the JPEG data is 368 x 368, matching our reported `size` of 368,368 [C for the JSON field; W for the explanation].
- Other badges: Nikko is a 1.83 inch IPS touch display, 360 x 360, 283 PPI, about 350 cd/m2, Bluetooth 5.4, 500 mAh, 16 MB storage, "up to 21 hours" on beambox.my and "16 hours at minimum brightness" on DROIX [W, S5]. Niji is 1.53 inch, 500 mAh, 360 x 360 advertised, DC 5 V 0.5 A [W, S3]. Nano reads 500 mAh, 5 V 0.5 A on the label [W, S2].
- Button behaviour (Niji, W, S3): a short press shows an app QR code and pairing screen, during which the badge advertises as `E-badge`; powered on without that screen it advertised no name and no service. A double press near another badge beams the current picture (peer to peer, not documented by us).

## 4. Stock firmware behaviour reported (Nano), and how it compares with our protocol

- [W, S2] The firmware registers several GATT attribute tables and which one is live depends on runtime state: a table with services 0xAE00 and 0xAE30 (write-without-response 0xAE01, notify 0xAE02, handle 130) and the table the author's unit actually showed (`E-badge`, service 0x01F0, write 0x01F1 at handle 66). One of the author's units differed from the expected table. [I] This supports our client probing both transports instead of assuming one (`probe --qualify`).
- [W, S2] Stock firmware accepts a 0xF1 control frame (`F1 | opcode | length | payload | checksum`, two's complement) which opens a file by opcode (2 update `rby_upd.bin`, 4 background `rby_bp.bin`, 5 animation `rby_gif.bin`, 6 still `rby_pic.bin`), after which raw bytes are written to flash in 4096-byte units; replies are `{GetPacketSuccess}` or `{GetPacketFail}`. This agrees with our nn20 type codes (5 and 6, plus 2 for OTA); the exact header layout described there (zero counters then a length) differs from ours (total and remaining packet counters, then a length) and the two descriptions may be for two firmware paths (AE01 raw stream versus the 0x01F0 envelope). [U] which a given unit uses; hardware test H1 settles it.
- [W, S3] On a Niji, the frame is `F1 | type | total(2) | remaining(2) | length(2) | data | checksum`, data up to 496 bytes per frame, with the `{"type":T,"data":` header in the first packet and `}` in the last; the badge pushes `A0 | type | 00 00 | len | JSON | checksum` status (`type` 13, `allspace`, `freespace`, `devname`, `size` 368,368, `time_mode` 1, `brand` 0). [C] our code builds exactly this envelope; our status layout (section 6.2 of PROTOCOL.md) matches. Difference: we cap data at 446 per frame as the app does; S3 shows 496 working on a Niji. [I] 496 is probably safe where the MTU allows it (needs MTU of at least 508); to try in H4 as an optional faster mode, not a default.
- [W, S3] A raw JPEG sent as type 6 is stored (free space drops by the JPEG size) but displays black; wrapping it in the 0x12345678 container and sending as type 5 shows it first time. [C] This is the change we made in the client (default still is type 5, `--nn20-still album` for type 6). The container fields S3 lists (meta = frames x 16 + 24, name `output/<interval>ms`, frame sub-header 0x0B, width, height, offsets, next pointer to self for one frame) agree with PROTOCOL.md section 2.
- [W, S2] JPEG and "IMB" are decoded by hardware blocks (not firmware code); the firmware also contains a PNG decoder with zlib, which would allow sending PNG directly [I, untested and not used by the app; the app converts everything to JPEG].
- [W, S2] Connection parameters: the firmware clamps the MTU to 23 to 517 and requests a 7.5 to 15 ms connection interval at the start of a transfer, restoring a slower one at the end; with MTU 512 and write-without-response a 259,200 byte full frame needs about 517 packets. [I] Matches our P and the recommendation to request a fast interval; bleak does not expose that call, so BLE throughput depends on the OS.
- [W, S2] The factory firmware writes received data to FAT16 flash in 4096-byte pages and the author notes that writing every frame would wear it out. [I] This motivates the safe-write policy (`docs/safe-write.md`) and means any live-video mode over BLE should avoid the album path.
- [W, S2] The stock firmware, on this unit, did not run its app while USB was connected, so "plug in" and "BLE use" are exclusive for the Nano.

## 5. Models, retail and specifications

| Model | Source | Claims | Label |
|-------|--------|--------|-------|
| NIKKO | S5 | 1.83 inch IPS, 360 x 360, touch overlay, button, Bluetooth 5.4, 500 mAh, 16 MB, GIF/PNG/JPG and 3 s video, peer sharing, magnetic, pin, lanyard, stand | W |
| NANO | S2 | Round AMOLED 454 x 454 behind a 360 x 360 buffer, BR28, 16 MiB, 500 mAh, 5 V 0.5 A | W |
| NIJI | S3 | 1.53 inch, 360 x 360 advertised, 500 mAh, advertised name `E-badge`, three colours | W |
| Pulse | S4 | Thai Lazada listing, THB 1,290, title says Image / GIF / Video, review snippets mention LED-style display, touch control, Thai app | W, see below |

- The Lazada listing text for Pulse reads "1.28-inch LED display" in one aggregator summary, which conflicts with Nikko's 1.83 inch IPS. We treat the user's statement "Pulse = NIKKO (flagship)" as the working assumption [I]; the Pulse retail copy may be loose marketing language or a different panel size. Hardware test H1 should record the badge's `size` field and the physical diagonal. Not resolved.
- No Thai reseller page we could open gave a Bluetooth name for Pulse; the advertised names seen anywhere are `E-badge` (Niji, Nano, S2 and S3) and the app's `Nikko-badge(BLE)`.

## 6. Firmware update information

- No firmware download or update URL was found: the APK contains no firmware or OTA host strings (grep of sources and resources); `type 2` of the nn20 envelope is an "OTA package" (S3) and the Jieli SDK in the app carries the OTA library, so updates are delivered inside the app (server contents unknown). [I] A firmware dump from a unit (S2 shows full 16 MiB read and write over USB with the Jieli updater) is the realistic way to see firmware; this is the destructive-risk track in the hardware recon checklist.
- [W, S2] Jieli's vendor SDK for the BR28 family (soundbox and others) was reachable on a public GitLab host at the time of that article, and the toolchains are published by Jieli; the badge uses a "watch" variant that was not in the public list. We did not access these hosts. Licence terms of that SDK are unknown to us, so we neither use nor copy it.

## 7. Open-source projects for the same chip family

- jumpingmushroom/e87_badge (MIT, Python plus Home Assistant), hybridherbst/web-bluetooth-e87 (MIT, TypeScript) and Manaiakalani/auracast (MIT): clients for "E87 / L8" round LED badges (Jieli BR23 family, Zrun app). They use the Jieli RCSP framing (`FE ... EF` frames, 490-byte data frames, windows of 8 frames, CRC-16/XMODEM, a 368 x 368 JPEG of about 16 KB, AVI for animations) and the Jieli auth cipher ported from `libjl_auth.so` [W, S6]. This is the BadgeSdk-like family, not the nn20 0x01F0 envelope; it is closest to our `rebeambox.rcsp`. Useful for cross-checking RCSP framing and auth; the static key quoted there is a different value from the one in our implementation, so we did not import it (our vectors were produced by emulating the shipped library, PROTOCOL.md 3.7.1) [I: they describe a different product line and library build].
- A gist for a "JieLi AC7076A E-Badge (E01)" describes a single-handle RCSP-like protocol with open/write/commit opcodes [W, S6]; not compared in detail.
- `jl-uboot-tool` (Jieli download mode, memory read/write) and `jl-misctools` (firmware unpack) are used by S2; they are the relevant tools for the hardware-recon dump options.
- No existing project targets the nn20 0x01F0 envelope beyond S3's snippets; this repository's `rebeambox.nn20` is, as far as we found, the fuller description.

## 8. Effect on the plan

1. Hardware test H1 must record which attribute table appears (0x01F0 versus 0xAE00/0xAE30) and the advertised name; both transports stay supported.
2. H2: type 5 container first (already the default); type 6 as the control. H4: try 496-byte frames only if MTU is at least 508.
3. Safe-write policy and delta skipping are justified by the FAT16/NOR gallery and 4 KiB page writes (W): see `docs/safe-write.md`.
4. FCC filing has no Wi-Fi band: expect the Pulse/Nikko to be Bluetooth only unless a unit shows an `E-Badge-xxxx` access point. The Wi-Fi path remains Unknown per model.
5. Pulse versus Nikko panel size is unresolved; record the physical diagonal.
