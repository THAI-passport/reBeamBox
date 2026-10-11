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

## Update: native code pass 3 (capstone and pyelftools, 2026-10)
Goal: find frame size, packet size or storage limits in native code. Result: none of the native libraries enforces a badge frame limit; all badge limits are Java side (30720 byte Wi-Fi JPEG, 6144 byte Wi-Fi chunk, RCSP MTU from the device, nn20 P = min(446, mtu - 12)).
- libjl_fatfs.so [C]: ChaN FatFs (f_mkfs, f_open, f_write ...) over a "remote" block device whose read and write go through Bluetooth (`BluetoothIoOperation`, `read_data_from_remote`, `write_data_to_remote`), plus a `DiskOp` transaction layer (`insertFile`, `replaceFile`, `deleteFile`, `doUpdateBegin/End`). Constants from disassembly: sector size 512 (`disk_initialize` sets 0x200), sector count = `SZ_RAMDISK` >> 9 with `SZ_RAMDISK` set from Java at init, `format_fat_fs` calls `f_mkfs` with option 9, allocation unit 0x1000 (4096 bytes), 0x80, and a 0x4000 byte work buffer. Used by the Jieli watch-face and resource tooling (`FatFileSystem`, `PackResFormat`, `WatchManager`), not by the badge picture path. [I] Evidence that Jieli devices keep resources in a small FAT volume; it does not show how the badge stores pictures.
- libjl_pack_format.so [C]: resource pack format helper for the same watch tooling (C++ with STL, 422 exports mostly runtime); not called by the badge flows.
- libjl_enc.so [C]: `Java_com_jieli_bt_decryption_HashDecryption_decryptData`, AES tables (Rijndael key schedule `rijndael_eK`, `key_mask`, `btcon_hash`): decrypts a Jieli device hash; not part of the picture path.
- libjl_ota_auth.so [C]: `function_E1test` (same E1 as libjl_auth), `function_E21`, `function_xiaomi`, `CRC16`, `cd03_crc_encode`, `parse_fw_info`, `Java_..._nativeFilterFile`: firmware (OTA) file parsing and the OTA auth variants. Not needed for pictures.
- libcbuf.so [C]: circular buffer (`cbuf_init`, `cbuf_write`, `cbuf_read`, `cbuf_prewrite` ...), 15 exports, used by the audio and OTA code; no limits of interest.
- libjl_opus, libjl_speex: audio transcoding (OGG Opus, Speex) for Jieli voice features; not used by the picture path.
- FFmpeg kit [C]: `libavutil` embeds the configure line: FFmpeg n6.0 built by ffmpeg-kit (arm64, NDK 27, `--enable-small`, `--enable-libopenh264`, `--disable-programs`, no GPL, no zlib, no mediacodec). The `mjpeg` encoder and `avi` muxer are present in libavcodec and libavformat, matching the AVI builder command in PROTOCOL.md 3.6.1. The client's system ffmpeg may be newer; the MJPEG bitstream (`-q:v 5`, yuvj420p) should be equivalent, which is [I].
- libpl_droidsonroids_gif: GIF decoding for previews on the phone; no badge relevance.
- Not analysed: libijkffmpeg, libijkplayer, libijksdl, librtmp-jni, libst_opus, libst_speex, libmmkv, libandroidx.graphics.path, libimage_processing_util_jni (player, streaming and Android libraries without protocol code).

Related Jieli RCSP command ids present in `Command.java` [C ids, payloads not analysed]: START_FILE_BROWSE 12, STOP_FILE_BROWSE 13, FILE_BROWSE_DELETE 31, DELETE_FILE_BY_NAME 35, FORMAT_DEVICE 34, READ_FILE_FROM_DEVICE 36, SMALL_FILE_TRANSFER 40, SEARCH_DEVICE 25, GET_DEV_MD5 212, SET_DEVICE_STORAGE 216, REBOOT_DEVICE 231, NOTIFY_FILE_STRUCTURE_CHANGE 242. See PROTOCOL.md 3.7.2.
