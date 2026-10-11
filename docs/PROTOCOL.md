# Beambox BLE protocol (DRAFT, first pass)

Source: static reading of com.guangshen.beambox 1.0.14. Notes only, no app code. Everything marked UNVERIFIED is inferred and untested against hardware.

## GATT
The app bundles several BLE stacks. Only the first is the badge protocol; the others come from bundled SDKs.

| Role | UUID (16-bit alias, base 0000xxxx-0000-1000-8000-00805F9B34FB) | Notes |
|------|------|------|
| Primary service | 0x01F0 | Looked up by the app after service discovery |
| Write characteristic | 0x01F1 | App to badge; write type 1 (WRITE_NO_RESPONSE) |
| Notify/read characteristic | 0x01F2 | Badge to app; notifications enabled through CCCD 0x2902 (ENABLE_NOTIFICATION) |
| Alternate service (UNVERIFIED use) | 0x03C4 with 0x03C5 (write) and 0x03C6 (read) | Constants defined, same layout; probably a second hardware variant |
| Bundled Jieli OTA stack (not the image path) | 0xAE00, 0xAE01 write, 0xAE02 notify | Jieli SDK, likely firmware update |
| Other bundled stacks | 0xFFFF / 0xFF01 / 0xFF02; 0x1812 (HID), 0xFD00 | Third-party SDK code, not traced |

Scan filter: device name match, normalised to upper case alphanumerics, containing "NEO" or "B-Device" (UNVERIFIED whether real badge names differ).

## Connection sequence
1. Connect GATT, then request MTU 512. If refused, continue with MTU 23.
2. Discover services, find 0x01F0, then 0x01F1 and 0x01F2.
3. Enable notifications on 0x01F2 by writing ENABLE_NOTIFICATION to its 0x2902 descriptor.
4. The app tracks the badge's free space (reported in JSON from the badge) and refuses uploads that do not fit (payload plus about 64 KiB margin).

## Frame format (app to badge)
All multi-byte fields big endian.

| Offset | Size | Field |
|--------|------|-------|
| 0 | 1 | Head 0xF1 (device to app uses 0xA0) |
| 1 | 1 | Type |
| 2 | 2 | Total packet count |
| 4 | 2 | Current subpage, counting down: (total - 1 - index), so the first packet carries total-1 and the last carries 0 |
| 6 | 2 | Data length of this packet |
| 8 | n | Data |
| 8+n | 1 | Checksum: two's complement of the byte sum of all preceding bytes, i.e. (0 - sum) & 0xFF |

Small commands use the same layout with total = 0 and subpage = 0 (no split) and a UTF-8 JSON body.

Type codes: 1 activate query, 2 OTA package, 3 boot animation, 4 watch face, 5 GIF animation, 6 album, 7 get version, 13 set brightness (JSON body).

## Chunking
- Payload per packet = min(446, MTU - 12), minimum 1. With MTU 512 this is 446 bytes, giving a 455-byte frame. Max 65535 packets.
- The data stream being chunked is an ASCII envelope of the form {"type":<n>,"data": then the raw media bytes then }. It is split across packets as one byte stream.

## Flow control
- Writes use write-without-response (type 1).
- ACK mode: batches of 4 packets (default), inter-packet interval 10 ms default (may adapt to 20, 40, 80 ms after failures), batch timeout about 2.5 s plus interval times batch size. Minimum 300 ms gap between separate transfers.
- Badge replies on 0x01F2 are frames with head 0xA0 carrying JSON; the strings GetPacketSuccess and GetPacketFail appear and drive ACK or resend. Exact reply layout UNVERIFIED.
- Retry: up to 3 ACK retries per logical packet, then the upload fails.
- Notification fragments are reassembled in a buffer and parsed repeatedly until no full frame remains.

## Media payload
- Native resolution 360x360 (368x368 also supported in the converter).
- Still image: JPEG, quality 90, wrapped in a 36-byte little-endian header: signature "IMB\0", then int 4, int (jpeg length + 32), byte format 11, byte 0, short 0, short width, short height, int data offset 36, int jpeg length, two zero ints, then the JPEG.
- Animation: frames are JPEG (quality 90, minimum frame interval 30 ms). A container is built from per-frame entries: header with magic 0x12345678 (little endian), address-table size, frame count, a 100 ms interval field, a 12-byte name field, then a table of 16-byte entries named frame_NNNNN, then each frame preceded by 32 bytes of header. The app also contains an AVI (MJPEG) builder; which of the two is used on BLE is UNVERIFIED.

## Key classes (names are obfuscated in places)
- com.example.nn20.bleutils.BleProtocolConstant: UUIDs, head bytes, type codes, 446 limit.
- com.example.nn20.bleutils.BleTransportSizing: payload size from MTU.
- com.example.nn20.bleutils.BluetoothScanUtil, utils.BluetoothDeviceNameMatcher, utils.KeyConstant: scan and name filter, target size 360.
- com.example.nn20.manager.k: BluetoothGattCallback (MTU, service discovery, notifications, write callback).
- com.example.nn20.manager.m: BleManager. Packetising, checksum, ACK/retry, pacing, command send (brightness).
- com.example.nn20.utils.BinConverter: JPEG to IMB header, multi-frame container.
- com.example.nn20.utils.BadgeMediaFileBuilder, GifFrameExtractor2, VideoFrameExtractor, AnimatedGifEncoder, NeuQuant, LZWEncoder: media preparation.

## Unknown / next
- Which type code carries a still image versus an animation (5 versus 6).
- Exact notification reply layout and fields (freespace, allspace, devname, time_mode, brand, size, type appear in the JSON).
- Whether the 0x03C4 service is a different hardware revision.
- Whether any pairing or authentication handshake is required (none seen yet).
- Final frame container details for GIF over BLE; multi-image upload path.
- Whether the badge accepts raw single-frame writes without the ACK batching.
