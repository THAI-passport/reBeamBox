# Shipped binaries (XAPK for v1.0.14)

| File | Size (bytes) | Purpose |
|------|------|------|
| com.guangshen.beambox.apk (base) | 46,923,980 | Dex (classes.dex, classes2.dex), resources, manifest. Holds all BLE logic |
| config.arm64_v8a.apk | 26,552,816 | Native libraries for arm64-v8a only |
| config.en.apk | 106,905 | English strings |
| config.mdpi.apk | 241,749 | mdpi resources |
| icon.png, manifest.json | 1,438,553 / 1,822 | XAPK metadata |

The base APK contains no .so files; all native code is in the arm64 split (ABI arm64-v8a). Only the base APK was decompiled. BLE logic is Java/Kotlin, not native.

## Native libraries (lib/arm64-v8a)
| Library | Size | Purpose / relevance |
|------|------|------|
| libavcodec, libavformat, libavutil, libavfilter, libavdevice, libswscale, libswresample | 8.5 MB, 2.0 MB, 498 KB, 2.8 MB, 57 KB, 315 KB, 78 KB | FFmpeg, video decode and frame extraction. Image processing |
| libffmpegkit, libffmpegkit_abidetect | 472 KB, 31 KB | FFmpegKit JNI wrapper. Image processing |
| libijkffmpeg, libijkplayer, libijksdl | 6.6 MB, 546 KB, 363 KB | ijkplayer video preview |
| libpl_droidsonroids_gif | 42 KB | GIF decoding (frame extraction). Image processing |
| libimage_processing_util_jni | 29 KB | AndroidX image utilities |
| libandroidx.graphics.path | 10 KB | AndroidX graphics |
| libjl_auth, libjl_ota_auth, libjl_enc, libjl_crc, libjl_pack_format, libjl_fatfs | 12 KB, 15 KB, 15 KB, 5 KB, 282 KB, 346 KB | Jieli SDK: auth, OTA, crypto, CRC, packaging, FAT filesystem. OTA and watch-face tooling, not seen in the image path |
| libjl_opus, libjl_speex, libst_opus, libst_speex | 30 KB, 16 KB, 431 KB, 127 KB | Audio codecs (Jieli and other) |
| librtmp-jni | 92 KB | RTMP streaming |
| libmmkv | 718 KB | Key-value storage |
| libcbuf | 7.5 KB | Small buffer helper (unidentified) |
| libc++_shared | 1.8 MB | C++ runtime |

No native library implements the BLE image protocol as far as seen; checksum and framing are in Java. Jieli libraries (libjl_crc, libjl_pack_format) may matter for firmware or OTA and are not yet analysed.

## Update: findings per library (second pass)
- libjl_crc.so (5.4 KB): single function CRC16(buf, len, seed); nibble-table CRC-16/XMODEM (poly 0x1021, no reflection), table of 16 values at .rodata 0x5e0. Verified check value 0x31C3. Used for the Jieli file transfer CRC. Confirmed by disassembly with capstone.
- libjl_auth.so (11.5 KB) and libjl_ota_auth.so (15 KB): Jieli authentication ciphers for the RCSP link and OTA. Not disassembled yet; needed for the BadgeSdk path (see problem_solution.md entry 18).
- libjl_fatfs.so (346 KB) and libjl_pack_format.so (282 KB): FAT and package formatting used by the Jieli watch and file tooling; supports the theory that the badge stores media in a FAT volume.
- FFmpeg libraries and libffmpegkit: used to build the AVI (MJPEG) files for animations and to extract frames from videos. They do not handle BLE.
- No library implements the nn20 framing or checksum; those are Java.
- The base APK contains no native code; classes live in classes.dex and classes2.dex; the BadgeSdk is package com.zijun.badgesdk and its helper classes are obfuscated (te, re, se, qe, f8).
