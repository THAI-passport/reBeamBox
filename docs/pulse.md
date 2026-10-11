# Beambox e-Badge Pulse (= NIKKO): what the decompiled app says

Update: the product owner identifies Pulse as the NIKKO model of the NN family (flagship, standard display, four wearing styles). See docs/models.md for the model comparison, transport per model and third-party hardware reports. Statements below that say the Pulse transport is probably BadgeSdk are superseded: NN-family units reported by third parties use the nn20 service 0x01F0, so the client defaults to nn20 for stills as a one-frame type 5 container.


Scope: static reading of Beambox+ 1.0.14 (package com.guangshen.beambox). Tags: [C] confirmed from code, [I] inferred, [U] unknown.

## 1. Pulse-specific data in the app
- [C] The string "Pulse" does not occur in the app's code or resources (the only hit is an unrelated pull-to-refresh footer class). There is no product table, product id, SKU, or model name for "Pulse" in the APK.
- [C] Product identity comes from the server. The home screen downloads a product list (endpoint `api/app/badge/select-badge`, plus `api/app/badge/instruction/list` for how-to pages). Each record has a display name, a "signal name" (the BLE name prefix to look for), a transport type `BT` or `WiFi`, and an image. The chosen record is stored (`keySignalName`, `keySelectDeviceName`). Pet products named POLLY and NEMO and a Chinese pet badge take extra pet screens; everything else goes to the generic badge flow.
- [I] So the Pulse is most likely one record in that server list. Its BLE name prefix is therefore not knowable offline. Our client accepts it with `--name <prefix>` (for example `--name Pulse`), in addition to NEO and B-Device.
- [C] Hard-coded names the app also accepts without the server: "NEO" and "B-Device" (substring, case and punctuation ignored). Names containing "BLE" are hidden from the scan list.
- [C] Shapes and device tags in advertising data (BadgeSdk): tag 0xB3 = badge, shape 0x6C square or 0x6D circle. The Pulse being a round badge corresponds to 0x6D [I].

## 2. Resolution
- [C] BadgeSdk path: the badge reports its picture size (0xC7 and 0xDB); the app uses it. No per-model table. The client does the same and falls back to 360x360.
- [C] nn20 path: the app builds 368x368 JPEGs (quality 90) for still and animation containers; some code paths hard-code 360x360 and a 240x240 sticker canvas; the IMB header only supports 368 or 360.
- [I] 360x360 circular area is the working assumption for a round badge; the client's default.

## 3. Feature support the app shows
- Stills: gallery picker and crop, JPG and PNG (Glide/Bitmap), flattened to RGB, scaled to the square. [C]
- GIF: frames extracted, re-encoded, sent as MJPEG AVI (BadgeSdk) or the 0x12345678 container (nn20). [C]
- Video: ffmpeg frame extraction, same AVI path. Audio is optional PCM 16 kHz mono in the AVI builder. [C] No duration cap was found in the code; the 3 s limit for the Pulse is product information, so the client enforces 3 s by default (`--max-seconds`). [U for hardware limit]
- Text and name tags: the app has doodle and sticker editors (DoodleCanvasActivity, sticker libraries) that render text and stickers onto a bitmap, then send that bitmap as a normal still. [C] There is no separate "text" protocol command; our `send-text` renders locally and sends a still. [I]
- Camera mode: CameraStreamActivity captures frames, crops to a centered square, scales to 360x360, converts to NV12 (194400 bytes = 360x360x1.5) or JPEG at quality 10, and pushes them over a Wi-Fi TCP socket to the badge access point (192.168.8.1:8080). The badge announces camera events with short status words (007B opened, 007F closed, 007A shutter). [C] This is the only live-video path in the app and it is Wi-Fi, not BLE. Relevant to docs/streaming-plan.md.
- Badge-to-badge transfer and a hardware Bluetooth button: operation strings say press the Bluetooth button once to enable APP transfer, long press 2.5 s to send to another badge. [C strings]

## 4. How the client handles the Pulse
- Scan: NEO, B-Device, advertising tag 0xB3, plus `--name`.
- Connect, then choose transport by service discovery: control service C2E6FD00 or Jieli 0xAE00 means the BadgeSdk path; 0x01F0 means nn20.
- Still: JPEG at the badge-reported size, circular mask with black corners (`--square` disables).
- GIF and video: capped at 3 s, MJPEG AVI (BadgeSdk) or container (nn20).
- Everything is untested on hardware; see README.
