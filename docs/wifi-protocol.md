# Wi-Fi path (badge access point, TCP 8080)

Source: decompiled app, no hardware. [C] = confirmed from code, [I] = inferred, [U] = unknown. Companion docs: PROTOCOL.md (BLE), models.md (per model), streaming-plan.md (fps and bandwidth), first-session-checklist.md (capture steps).

## 1. Which devices use it
- [C] The home screen reads the stored product record (`DEVICE_SELECT_DATA`). If its `deviceType` is `BT`, `keyDeviceType` becomes 1 (BLE path). Any other value (the server value is `WiFi`) sets `keyDeviceType = 2` and the home tiles change (the fifth tile opens the live camera screen instead of the scrolling text screen).
- [C] The `deviceType` value comes from the server product list, not from the APK. No product in the APK is hard-wired to Wi-Fi.
- [U] Which of NIKKO, NANO, NIJI (or older products) the server marks `WiFi`. Third-party reports show Nano and Niji on BLE nn20, and no source states that Nikko (Pulse) uses Wi-Fi. A Pulse that shows a Wi-Fi access point named like `E-Badge...` in its settings would be the evidence. The first-session checklist asks for that scan.
- [C] Wi-Fi products use 360 x 360 images (BLE products 368 x 368 in the same code path).

## 2. Joining the badge access point
- [C] The access point SSID is chosen by substring: the Wi-Fi list screen shows scan results whose SSID contains the stored signal name (`keySignalName`, from the product record). The constant `DEVICE_WIFI_NAME = "E-Badge"` is used by `WifiTransferManager.isWifiConnected` to test that the phone is on the badge network (SSID contains `E-Badge`).
- [C] Security: if the scan result capabilities show no WPA/WEP the app connects with an empty password (open network). Otherwise it prompts the user for a password and stores it per SSID. No default password exists in the APK. [U] whether the badge AP is open or protected.
- [C] Android 10 and later: `requestNetwork` with a Wi-Fi network specifier (SSID and passphrase), without internet capability. On `onAvailable` the process is bound to that network (`bindProcessToNetwork`) so sockets use the badge Wi-Fi even though it has no internet, then the control socket is opened. Older Android: legacy `WifiConfiguration` and `enableNetwork`.
- [C] The app waits up to 5 seconds (1 s polls) for the phone to have a Wi-Fi SSID and an IP before opening sockets.
- [C] Address: default `192.168.8.1:8080`. If the phone's IPv4 /24 differs from the stored device address, the app replaces the device address by the DHCP gateway of the Wi-Fi network. So the badge is the gateway and DHCP server of its own network.
- Desktop equivalent [I]: join the SSID with the OS tools, then run rebeambox with `--transport wifi` (optionally `--host`). Linux: `nmcli device wifi connect <SSID> [password <pw>]`; macOS: `networksetup -setairportnetwork en0 <SSID> [pw]`; Windows: `netsh wlan connect name=<profile>`. The badge network has no internet, the OS may warn and fall back to another network; keep the badge network as the route for 192.168.8.0/24.

## 3. Sockets
Two kinds of TCP connection, both to the same address and port [C for addresses; I that the device accepts both on one port because the code uses 8080 for both]:
- Control socket (class `manager/s`): plain `Socket(host, port)`, no timeout set, raw 2-byte command words out, raw bytes in. A background loop polls `available()` every 10 ms in the camera screen.
- Upload socket (class `manager/w`): `Socket` bound to the Wi-Fi network, connect timeout 10 s, SO_TIMEOUT 60 s, keep-alive, TCP_NODELAY, 64 KiB send and receive buffers. Used only to POST container files.

There is no handshake or authentication on either: [C] nothing is sent on connect; the first bytes are a command word. [I] the device may require the control query (0x0069) before an upload because the app always sends it first.

## 4. Control words (big-endian, 2 bytes) [C]
| Word | Direction | Meaning | Evidence |
|---|---|---|---|
| 0x0069 | phone to badge | Query/start upload: ask for storage | sent before every upload (stills, GIF, video) |
| reply | badge to phone | ASCII text `SD:<n>KB` then two code bytes; app strips the last 2 bytes, takes digits after `SD:` as free KB. Hex containing `006A` is treated as upload start OK | VideoGif message handler |
| 0x006B | badge to phone | Upload start failed (toast shown, socket closed) | handler |
| 0x005F | phone to badge | End of session after upload; the app closes the control socket right after | SingleAdd cleanup |
| 0x0079 | phone to badge | Enter live camera mode | camera start button |
| 0x007B | badge to phone | Camera mode is on (frame sending starts) | camera reader |
| 0x007A | badge to phone | Shutter event: badge button pressed, the phone takes a photo | camera reader |
| 0x007D | phone to badge | Photo saved acknowledgement | after saving the photo |
| 0x007F | phone to badge | Stop live camera mode, always followed by 0x0000 | stop task |
| 0x007F | badge to phone | Badge left camera mode: phone stops sending, closes, leaves the badge Wi-Fi | camera reader |
| 0x0000 | phone to badge | Frame terminator and stop terminator | frame sender |
Any other reply is ignored by the camera screen. [U] The reply to 0x0079 when the badge is busy, and other error words.

## 5. Live camera mode [C]
Sequence:
1. Open the control socket (the screen also opens the upload socket in the background, it is unused for frames).
2. Send `00 79`; wait for `00 7B` (the app times out after 5 s and shows an error).
3. For every camera frame that passes the throttle send `[len_hi][len_lo][JPEG bytes][00 00]`, as three separate writes in the app (length, bytes, end marker). The length is the JPEG size as an unsigned 16-bit big-endian number.
4. On `00 7A` from the badge the phone captures a full resolution photo (quality 90) to its gallery and sends `00 7D`.
5. To stop: wait 200 ms, send `00 7F` then `00 00`; or the badge sends `00 7F` and the phone closes everything.

Frame format [C]:
- Camera analysis target 480 x 480 (back camera, keep-latest backpressure). Crop the centred square, scale to 360 x 360.
- Normal path: NV21 to JPEG, quality 10 (Android `YuvImage.compressToJpeg`). Beauty switch on: bitmap path with a small brightness and red-channel tweak and quality 10 after scaling.
- The app logs a warning above 30720 bytes and still sends. [I] 30 KB is the badge frame buffer; larger frames are probably dropped or corrupt, stay under it.
- Frame rate limit: [C] a frame is skipped if less than 300 ms passed since the last sent frame, so at most 3.3 fps; the screen shows the measured FPS.
- [U] Whether the badge applies a circular mask, rotation or colour correction. The app sends upright square images.

### 5.1 Length prefix versus stop words (the 127-byte ambiguity) [C for what the app sends, I for the firmware]
- [C] The app has no type byte. Every camera frame is three writes: a 2-byte big-endian length, the JPEG, and `00 00`. The stop request is the same shape: `00 7F` (a "length" of 127) followed by `00 00`, with no body. Other control words (`00 69`, `00 5F`, `00 79`, `00 7D`) are also two bytes with a zero high byte. The app has no guard for small frames and the socket read loop polls every 10 ms for replies.
- [C] Every control word has a zero high byte, so it equals a frame length below 256. A 360 x 360 JPEG at quality 10 is never that small, so the app never produces a collision in practice.
- [I] The firmware therefore most likely treats a first byte of 0x00 at a frame boundary as a command word and anything else as the high byte of a frame length. The alternative (it reads `len` bytes after any prefix) is contradicted by the stop request, which sends no body. The exact firmware rule cannot be read from the APK; hardware test H5 should send a frame with length 127 only if a reset is acceptable.
- Client rule: `wifi.pad_jpeg` pads any frame below 256 bytes with a JPEG comment segment, so no length prefix has a zero high byte; frames above 30720 bytes are dropped. Tests: `tests/test_sw_wifi_edges.py`.

### 5.2 Which models use Wi-Fi: resource and string hints [C strings, I verdict]
- [C] `home_string_35`: "enable your device's WiFi and connect to signal E-Badge-xxx" (the SSID prefix, also the default product signal name). `home_string_39`: "disconnect your device from WiFi before editing" (the badge access point has no internet, editing needs the phone off it). `toaster_tips_31`: "Please connect Bluetooth or WiFi first" (the app treats BLE and Wi-Fi as alternative connections). `toaster_tips_13` and `_16`: "WiFi upload failed" and "WiFi transferring". `legacy_layout_text_006` "WiFi upload".
- [C] `WiFiDeviceActivity` lists scan results whose SSID contains the stored signal name (`keySignalName`), then connects; it has no model names. Strings about 2.4 GHz only, Wi-Fi password and SSID entry (`pets_string_*`, `legacy_layout_text_038`) belong to unrelated flows and are not part of the badge protocol.
- [I] Nothing in the APK names a model as Wi-Fi. The only selector is the server `deviceType`. The `E-Badge` SSID prefix and the BLE name `E-badge` shown by Nano and Niji suggest the same product-name family, but that is not evidence of a Wi-Fi radio.

## 6. File upload (stills, GIF, video) [C unless marked]
1. Control: `00 69`, read reply, parse `SD:<n>KB` (free KB); the app compares it with the file size before building the payload.
2. Build a container file in memory: stills with the 36-byte IMB header (`BinConverter` method for single images, tag `single_wifi`), animations with the 0x12345678 container using the Wi-Fi variant (address list length N*16+32 rather than N*16+24; PROTOCOL.md 3.6). The app calls the animation builder with a frame interval of 44 ms for the single-image add path. The app also writes the file to its cache as `S`/`M`/`V`/`G` plus two digits and `.bin`.
3. Upload socket: send a handwritten HTTP request, exactly:
   `POST /upload HTTP/1.1`, `Host: <ip>`, `X-Filename: <two digits>.bin`, `Content-Type: application/octet-stream`, `Content-Length: <n>`, `Connection: keep-alive`, blank line. File name: two random digits plus `.bin` (a `.bin` suffix is added if missing).
4. Wait 10 ms, then send the body in 6144-byte chunks with a flush after each. Sleep after each chunk: 3 ms while more than 102400 bytes remain, 2 ms while more than 51200, else 1 ms. On a socket exception the app reconnects once and resends the header.
5. Read the response for up to 3 s. A reply containing `200`, `204` or starting `OK` is success. No reply is treated as success.
6. Control: `00 5F`, close the control socket.
- [C] An OkHttp based uploader (`HttpUploader`) also exists with `POST http://192.168.8.1/upload` (port 80, same `X-Filename` header, resume support: a `Content-Range: bytes <start>-<end>/<total>` header and a saved offset). It appears unused by the current screens [I]. If the TCP 8080 path fails, port 80 is the first alternative to try.
- [U] Maximum file size and what the badge does with a duplicate file name.
- Image formats: a still is a JPEG inside the IMB container, 360 x 360, circular crop done by the app. Animations are JPEG frames inside the container (see PROTOCOL.md 3.6), not AVI. The AVI path in the BLE BadgeSdk is a separate product line.

## 7. Models [I]
Only models whose server record has `deviceType = WiFi` take this path; see section 1. Model name specific code does not exist on the Wi-Fi path; the only model constant is the video trimmer window (Niji 5 s, others 10 s).

## 8. What rebeambox does
- `rebeambox send-image|send-gif|send-video|send-text --transport wifi [--host IP] [--port N] [--wifi-still imb|gif]`
- `rebeambox stream <video-or-gif> [--fps 2]` (live frames, clamped to 3.3 fps, each JPEG fitted under 30720 bytes; a frame above that is dropped and counted, unlike the app which only logs a warning).
- `--dry-run FILE` runs against a software badge (`SimWifiBadge`) and writes every write and reply plus the payload; no network.
- Tests: framing, header text, free-space parsing, refusal, no space, camera loop with a shutter event, loopback TCP server using the same software badge.
- Untested on hardware. Everything above not marked [C] is a hypothesis.
