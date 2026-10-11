# Fact sheet: models, screens, sizes, transports, chip

This is the single place for values that sources disagree on. Other documents link here instead of restating them. When a value changes, change it here first.

Evidence labels: [C] confirmed from the decompiled app (Beambox+ 1.0.14), [W] third-party or vendor claim not verified by us, [I] inferred, [U] unknown, [USER] stated by the project owner. Source URLs for [W] items are in docs/models.md section 6 and docs/recon-web.md.

## 1. Screens

| Model | Panel size | Evidence | Notes |
|---|---|---|---|
| NIKKO (Pulse) | 1.8 inch | [USER] | Project owner's statement; treated as the working value |
| NIKKO (Pulse) | 1.83 inch round IPS | [W] | Third-party retail page and reviews; consistent with 1.8 inch |
| NIKKO (Pulse) | 1.28 inch | [W] | One retail copy; conflicts with the two rows above and is treated as probably a copy error |
| NANO (Lite) | round, size not found | [U] | 360x360 advertised [W] |
| NIJI | 1.53 inch round IPS plus touch | [W] | Vendor and distributor pages |

Resolution advertised for the whole family: 360x360 [W]. Nothing in the app states a panel diameter [C].

## 2. Picture size: 360 versus 368

| Context | Value | Evidence |
|---|---|---|
| Advertised panel resolution | 360x360 | [W] |
| nn20 BLE path, JPEG edge the app builds | 368 (quality 90); some paths hard-code 360 and a 240 sticker canvas | [C] |
| IMB header | width and height written only as 368 or 360 | [C] |
| nn20 status JSON `size` field, from a Niji | "368,368" | [W] |
| Wi-Fi camera mode | 360x360 JPEG, quality 10, at most 30720 bytes | [C] |
| BadgeSdk path | the badge reports its size (0xC7, 0xDB); the app uses it | [C] |
| Real accepted size on a Nikko | unknown | [U] (hardware test H2) |

Client rule: use the size the badge reports. Without a report, nn20 falls back to 368 and the BadgeSdk path to 360; the Wi-Fi path uses 360. `--size` overrides all of these. `--model` does not change the size.

## 3. Transports

| Model | Transport | Evidence |
|---|---|---|
| NIJI | nn20 BLE, service 0x01F0 only (write 0x01F1, notify 0x01F2); advertised name `E-badge` | [W] |
| NANO | nn20 BLE, service 0x01F0 only | [W] |
| NIKKO (Pulse) | nn20 BLE expected; advertised name `Nikko-badge(BLE)` reported | [I] and [W] |
| BadgeSdk / Jieli RCSP (C2E6FD00, 0xAE00, E1/SAFER+ auth) | used by the app for devices whose product record says BT and which expose 0xAE00 | [C] for app logic, no model confirmed to use it |
| Wi-Fi (badge access point, TCP 192.168.8.1:8080) | used by the app for product records of type WiFi | [C] for app logic, which model uses it is [U] |

The app has no model table; the choice comes from a server product list and runtime service discovery [C]. Full detail: docs/models.md, docs/PROTOCOL.md section 6, docs/wifi-protocol.md.

## 4. Chip and storage

| Item | Value | Evidence |
|---|---|---|
| SoC family | Jieli BR28 / AC701N | [W] (FCC internal photos, a Nano teardown, USB identifier "BR28 UDISK" on a Niji) |
| Flash | 16 MiB NOR, FAT16 gallery | [W] Nano teardown |
| Storage in status JSON | `allspace` 16384 KB from a Niji | [W] |
| Storage in Niji retail copy | 8 MB | [W], conflicts with the status JSON; the status JSON is the better evidence |
| FCC ID | spelled `2BR3T-BAGDE0` in the filing and `2BR3T-BADGE0` in some sources | [W], both are kept on purpose |
| Radio | Bluetooth LE 5.x; no Wi-Fi in any filing seen | [W] |

## 5. Video and animation limits

| Item | Value | Evidence |
|---|---|---|
| Retail claim for Pulse | video up to 3 s | [W] |
| App video trimmer window | 10 s, NIJI 5 s | [C] |
| Client default cap | 3 s for every model, NIJI 5 s (`--max-seconds` overrides) | design choice |
| Real limit on hardware | unknown | [U] (hardware test H7) |

## 6. Battery

Reports range from 450 to 500 mAh for Nikko and 500 mAh at 3.8 V for Niji [W]; runtime claims differ by seller. Not used by any code.

## 7. Client safety defaults

Minimum 30 s between writes, warning above 40 writes in 24 hours, hard cap 50 writes in 24 hours per badge, warning above 10000 writes in total. All configurable; see docs/safe-write.md.
