# Product line: NIKKO, NANO, NIJI

Tags: [C] confirmed from the decompiled app (Beambox+ 1.0.14), [W] reported by a third party or vendor page (not verified by us), [I] inferred, [U] unknown. Sources for [W] are listed in section 6.

## 1. Summary table
| | NIKKO (Pulse) | NANO (Lite) | NIJI |
|---|---|---|---|
| Vendor positioning [W] | Flagship, standard display, four wearing styles (pin, magnet, lanyard, stand) | Essential, lightest, longest standby, pin or keychain, location finding | Specialist, 1.53 inch touch display, GIF, large battery, colour |
| Screen [W] | 1.8 or 1.83 inch round IPS, 360x360 advertised | round, 360x360 advertised (size not found) | 1.53 inch round IPS plus touch, 360x360 |
| Framebuffer / encoded size | 368x368 expected [I] | 368x368 frames in stock flash [W] | status JSON reports "368,368" [W] |
| BLE service seen | not reported [U] | 0x01F0 only, no 0xAE00 [W] | 0x01F0 only (01F1 write-no-resp, 01F2 notify) [W] |
| Transport used | nn20 (BLE) [I] | nn20 (BLE) [W] | nn20 (BLE) [W] |
| SoC [W] | Jieli BR28 / AC701N family (FCC internal photos, Nikko board YH-GS2501-V0.2) | Jieli BR28 / AC701N, 16 MiB flash, board YH-GS-NANO-V0.2 | Jieli BR28 ("BR28 UDISK" over USB) |
| Battery [W] | 450-500 mAh class, up to 12 h | 500 mAh | 500 mAh 3.8 V, 5-10 h daily use, 30+ days standby, 8 MB storage, 19 g |
| Video cap in app trimmer [C] | 10 s window (code); retail says 3 s | 10 s window (code) | 5 s window (code) |

## 2. What the app code says about models [C]
- The app has no model table. The words NIKKO, NANO and NIJI appear in exactly four places: the layout `item_banner.xml` (placeholder text "NIKKO BADGE" on the home banner card), `item_device_card.xml` (placeholder text "NANO" in the device card template, overwritten at runtime by the server record), `strings.xml` `find_string_tag_7` = "NIKKO" (a community filter tag), and one comparison in `IosStyleVideoTrimmerView.setSliderType` (see 4). `m2/g.java`, `a0/j.java` and the `wg` package contain no model names.
- Hard-coded BLE names: only `NEO` (`KeyConstant.keyBleName`) and `B-Device`. NEO is also used cosmetically: if the stored signal name equals NEO the home screen uses a different doodle card background (`w7/p0`).

## 3. Selected-device flow [C]
1. The home fragment (`w7/j`) downloads the badge product list from the server (`api/app/badge/select-badge`). Each `DeviceItem` has deviceName, signalName, deviceType (`BT` or `WiFi`), image URL, badgeId.
2. On selection (`w7/i`) the app stores the whole item (`DEVICE_SELECT_DATA`), `keySignalName` (BLE or Wi-Fi SSID prefix to look for) and `keySelectDeviceName` (display name).
3. Pet products (POLLY, NEMO, the Chinese pet badge) branch to pet screens. Everything else continues with: `deviceType == "BT"` sets `keyDeviceType2 = 1` and later `keyDeviceType = 1`; `"WiFi"` sets `keyDeviceType2 = 2` and `keyDeviceType = 2` (`w7/p0`).
4. `keyDeviceType` then drives behaviour: 1 means the BLE path (368 px images, Bluetooth permission prompts, BLE connection checks via `j8.c.F()`), 2 means the Wi-Fi path (360 px images, the app first reconnects to the badge access point named after `CONNECT_WIFI_NAME`).
5. For BLE, `j8.c.E()` checks the connected BLE name with `BluetoothDeviceNameMatcher`: matching names use the BadgeSdk (Jieli) manager, otherwise the nn20 manager.
- [U] Which of NIKKO, NANO, NIJI the server marks `BT` or `WiFi` is not in the APK. Third-party hardware reports (section 6) show Nano and Niji working over BLE nn20, and the vendor describes Beambox as "Bluetooth plus Wi-Fi high-speed transfer", so Wi-Fi is probably the newer Neo tier [I].

## 4. Model-specific code paths [C]
- Only one: video trimming window. `IosStyleVideoTrimmerView.setSliderType` sets a maximum window of 5000 ms when `keySelectDeviceName` upper-cased equals `NIJI`, else 10000 ms. `UnifiedSliderView` and `UnifiedSliderView2` use 10000 ms for `keyDeviceType == 1` and 5000 ms for the Wi-Fi type. The trimmer may allow up to twice the window when the clip is longer.
- No model-specific constants for resolution, transport, GIF or touch exist in the code. GIF and video flows are the same for all models. There is no code for touch input, location finding or Find My. The strings "Shake" and "Touch" belong to the pet products.
- Conclusion: the app treats the three models identically apart from the NIJI video window. Feature differences on the vendor page (touch, location, battery, wearing styles) are hardware and firmware features outside the phone protocol we can see [I].

## 5. Transport per model, and what changed in the client
- Real-hardware reports contradict the earlier assumption that the NN family speaks Jieli RCSP over 0xAE00. A Nano and a Niji expose only service 0x01F0 [W]. So the nn20 path is the primary path for NIKKO, NANO and NIJI [I for Nikko], and the BadgeSdk path (C2E6FD00 plus 0xAE00) is the fallback for other Beambox+ era products.
- Stills must be sent as type 5 with the 0x12345678 container (one frame), not as type 6 with the IMB header: type 6 is accepted and stored but displays black on a Niji [W]. The client now sends stills as a one-frame type 5 container (interval 3000 ms, like the reporter) by default, and keeps `--nn20-still album` for the app's documented type 6 path.
- The badge only advertises while its pairing screen (QR code, "Scan to download") is shown; the advertised name is `E-badge` in pairing mode [W]. A third-party report also saw `Nikko-badge(BLE)` on a Nano powered over USB, which the app's own filter would hide because of the BLE suffix [W]. The client accepts `E-badge`, and `--model` adds the model name and bypasses the BLE-suffix rule.
- Status JSON pushed on 0x01F2 (from a Niji) [W]: `{"type":13,"allspace":16384,"freespace":5592,"devname":"","size":"368,368","time_mode":1,"brand":0}`. `size` is a string "W,H"; allspace and freespace are KB. The client now reads `size`.
- Reported packet size 496 data bytes works on a Niji [W]; the app constant is 446 [C]; the client keeps 446.
- Wi-Fi path: selected by the server product `deviceType = WiFi`, never by model name. Full analysis in docs/wifi-protocol.md; the client implements it (`--transport wifi`, `stream`). Which of the three models (if any) the server marks WiFi is [U].

## 6. Web recon (all [W])
- Spec page https://beambox.my/index.php?option=com_sppagebuilder&view=page&id=94 : taglines and feature bullets as in the table (NIKKO: four wearing styles, standard display; NANO: location support, longest standby, pin or keychain; NIJI: 1.53 inch touch, GIF, high capacity battery, up to 12 hours).
- https://beambox.my/index.php/niji and https://www.sac-corp.jp/product/niji-e-badge/ : Niji 1.53 inch IPS plus touch, 360x360, 350 cd/m2, Bluetooth 5.4, 3.8 V 500 mAh, JPG/GIF/PNG, 8 MB storage, 48.6 mm diameter, 9.6 mm thick, 19 g, buttons plus touch.
- https://www.beambox.site/products/beambox-nikko-e-badge : Nikko 1.83 inch IPS, photos, GIFs and videos from the app, magnetic, pin and lanyard.
- https://www.geekpark.net/news/359356 (teardown-style article): 360x360 at 285 PPI, 350 cd/m2, Bluetooth 5.4, 8-16 MB flash, gyroscope and IMU, 57-58 mm and 25-50 g for the family, Neo to add Wi-Fi. Treat as marketing-derived.
- https://lilting.ch/en/articles/beambox-niji-badge-ble-without-app : hands-on Niji over bleak: name `E-badge`, service 01F0, status JSON, packet format identical to our nn20 spec (F1 head, big endian counts, two's complement checksum), type 6 black screen, type 5 container works, framebuffer 368x368, USB charge only, button behaviour (second button: pairing screen; double press: share to another badge).
- https://zenn.dev/saqoosha/articles/beambox-nano-badge-1-bricked (series of 7): Nano label (Nano-Badge, Avatronics Corporation Limited, 5 V 0.5 A, 500 mAh), family listed under one conformity number (Nano, Nikko, Niji, Neo), FCC ID 2BR3T-BAGDE0, Jieli BR28 (AC701N), 16 MiB flash, watch-type firmware, frames in flash use the same 32-byte frame header and 16-byte directory entries as our container spec (header says 360, JPEG data is 368), pairing advertises `E-badge` and only service 0x01F0 (no 0xAE00), USB gadget is a dummy disk. The series ends with a bricked panel; do not flash firmware.
- https://fccid.io/2BR3T-BAGDE0 : "E-Bagde", Avatronics Corporation Limited, Bluetooth LE 2402-2480 MHz, grant 2025-09-28, internal photos available (Jieli QFN).
- No FCC filing or teardown for a product literally named "Pulse" matched this brand (other "Pulse" filings are unrelated). A marketplace listing calls a Niji product "Beambox E Badge Pulse"-adjacent, so "Pulse" is a retail or regional name [I]; per the project owner Pulse = NIKKO.

## 7. Open items
- Nikko and Nano on-air names beyond `E-badge` and `Nikko-badge(BLE)`: [U], scan a real unit with `rebeambox scan --all`.
- Whether Nikko exposes 0xAE00 as well: [U].
- Maximum video length and allowed AVI parameters on the nn20 path: the app builds a frame container, not an AVI, for animations. Videos are sent as frame sequences there; AVI (MJPEG) is the BadgeSdk path only [C]. The client's nn20 `send-gif` and `send-video` follow this.
