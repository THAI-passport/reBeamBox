# Software test plan v1 (no hardware)

Status: written, not yet run in CI at the time of writing (the run is awaiting approval). All tests live in `tests/test_sw_*.py` and reuse the existing software badges (`rebeambox/sim.py`: `SimBadgeSdk`, `SimNn20`, `SimWifiBadge`) and helpers. Hardware counterpart: hardware-test-v1.md. Earlier tests (frame serialization, session flows, CLI dry run, models) stay in the other `tests/test_*.py` files.

Run:
```
.venv/bin/python -m pytest -q tests/test_sw_containers.py tests/test_sw_auth_fuzz.py tests/test_sw_wifi_edges.py tests/test_sw_media_scan_transport.py tests/test_sw_snapshot.py
.venv/bin/python -m pytest -q -m slow tests/test_sw_auth_fuzz.py     # larger auth fuzz (default 500, REBEAMBOX_FUZZ_SLOW_N)
```
`pyproject.toml` deselects the `slow` marker by default (`addopts = -m 'not slow'`). Environment switches: `REBEAMBOX_FUZZ_N` (default 20), `JL_AUTH_SO` (path of libjl_auth.so), `REBEAMBOX_THAI_FONT`.

Skips by design: native auth fuzz (needs unicorn, pyelftools and the library under `analysis/work/so/...`, not in the repo), Thai rendering (needs a Thai font), video tests (need ffmpeg).

## 1. Round trip of IMB and animation containers
- Purpose: the builders and an independent parser written in the test agree on every field.
- Inputs: random JPEG-like byte strings; sizes 360, 368, 240 for IMB; 1, 2, 5, 17 frames, BLE and Wi-Fi variants for animations.
- Expected: IMB constants (4, size+32, format 11, offset 36, length) and size mapping (368 stays, anything else becomes 360); animation magic 0x12345678, frame count, interval, address-list length N*16+24 (BLE) or N*16+32 (Wi-Fi), total length field = length-1, frame names `frame_00001.`, offsets, last frame points to the first, JPEG bytes identical, label `output/<ms>ms`.
- Location: `tests/test_sw_containers.py`: `test_imb_round_trip`, `test_animation_container_round_trip`, `test_animation_container_label_and_interval_field`.

## 2. Checksum edge cases
- Purpose: boundaries of every checksum and length field, and rejection of corrupted frames.
- Inputs: empty data; maximum lengths (nn20 65535 packets via MTU 23, control payload 65535, reply text 255); one byte over each limit; flipped checksum bytes; corrupted frame followed by a good frame; CRC-16/XMODEM check value; truncated RCSP frames.
- Expected: empty checksum 0 and sum+checksum = 0 mod 256; maximum frames round trip; one over the limit raises (`ValueError`, `struct.error`); corrupted frames are rejected and the parser resynchronises on the next good frame; CRC of "123456789" is 0x31C3 and works incrementally; incomplete RCSP frames wait.
- Location: `tests/test_sw_containers.py`: `test_nn20_checksum_edges`, `test_nn20_empty_payload_frame`, `test_nn20_max_packet_count_boundary`, `test_nn20_max_data_per_packet_is_446`, `test_nn20_reply_length_limits_and_bad_checksum`, `test_control_checksum_empty_and_max_payload`, `test_control_known_bad_checksum_rejected`, `test_crc16_xmodem_known_values`, `test_rcsp_incomplete_frames_wait`.

## 3. Auth fuzzing: native emulator versus Python
- Purpose: the Python E1/SAFER+ port equals the real `libjl_auth.so` for arbitrary challenges, keys and addresses, not only the four stored vectors.
- Inputs: seeded random 16-byte challenges; every fourth case uses the default key and fixed address, the others random keys and addresses; default 20 cases, emulator reloaded every 25 cases (its allocator never frees). Large run behind the `slow` marker.
- Expected: byte-identical 16-byte outputs. Pure Python checks that always run: determinism, avalanche (one flipped challenge bit changes at least 16 of 128 output bits), `encrypt_challenge` equals `0x01 + E1`, wrong length rejected, key and address both change the answer.
- Location: `tests/test_sw_auth_fuzz.py`: `test_native_vs_python_random_challenges`, `test_native_vs_python_random_challenges_large` (slow), `test_python_e1_shape_and_determinism`, `test_python_e1_avalanche_on_challenge_bit_flip`, `test_encrypt_challenge_matches_e1_for_random_challenges`, `test_key_and_address_change_the_answer`. Emulator: `tools/emulate_jl_auth.py`.

## 4. Wi-Fi framing edge cases
- Purpose: the live-frame and control-word framing behaves at its limits against the software Wi-Fi badge.
- Inputs: frame of exactly 30720 bytes and 30721 bytes; 65535 and 65536 bytes; frames that contain the stop word 0x007F, the end word 0x0000 and the query word 0x0069 in their payload; frames written in 7-byte TCP segments; a stop word between two length-prefixed frames; a 127-byte frame; a shutter event during streaming.
- Expected: exactly 30720 accepted, 30721 dropped and counted (`WifiSession.dropped`), nothing over 16 bits builds; embedded words do not split frames; segmentation does not matter; stop ends camera mode and later bytes are not frames; the 127-byte frame is ambiguous and the simulator treats it as stop (documented, problem 37); shutter is answered with 0x007D and counted; `jpeg_under` never exceeds 30720 and raises `MediaError` when impossible.
- Location: `tests/test_sw_wifi_edges.py` (ten functions), code in `rebeambox/wifi.py` and `rebeambox/sim.py`.

## 5. Media conversion
- Purpose: pictures and clips are normalised to the badge geometry whatever the input.
- Inputs: tall (300x500) and wide (600x200) images with coloured halves; transparent and half-transparent RGBA PNG; palette PNG with transparency; GIF with uneven delays (50, 200, 100 ms), with very short delays, and with 100 frames; an 8-second ffmpeg test video.
- Expected: centre crop to a square (colours of the central part), circular mask blanks corners for any aspect, transparency flattened on black (half alpha white becomes about 128 grey, also after JPEG), uneven delays give the mean interval (117 ms), short delays are clamped to 30 ms, GIF and video are cut to the model cap (NIKKO and NANO 3 s, NIJI 5 s), video output is an AVI.
- Location: `tests/test_sw_media_scan_transport.py`: `test_tall_image_is_center_cropped`, `test_wide_image_is_center_cropped`, `test_circular_mask_blanks_corners_for_any_aspect`, `test_transparent_png_is_flattened_on_black`, `test_palette_png_with_transparency`, `test_uneven_gif_durations_average_to_one_interval`, `test_gif_very_short_delays_are_clamped`, `test_long_gif_is_capped_to_the_model_limit` (3 models), `test_video_longer_than_model_cap_is_trimmed` (2 models, needs ffmpeg), `test_video_to_avi_is_an_avi`.

## 6. Scan filter matrix per model
- Purpose: which advertised names are accepted with no model and with `--model nikko|nano|niji`, especially names containing BLE (the app skips them unless a configured name matches).
- Inputs: 14 names (`NEO-0001`, `NEO-0001(BLE)`, `B-Device 7`, `E-badge`, `E-badge(BLE)`, `Nikko-badge(BLE)`, `Nikko-badge`, `Nano-01`, `NIJI_touch`, `niji(BLE)`, an unrelated name, empty, blanks, None) times four profiles.
- Expected: table `MATRIX` in the test file; notably `Nikko-badge(BLE)` matches only with `--model nikko`, and `E-badge(BLE)` matches only when a model is given because every profile carries `E-badge`. Case and punctuation do not matter; a configured `--name` beats the BLE exclusion.
- Location: `tests/test_sw_media_scan_transport.py`: `test_scan_filter_matrix` (14 cases), `test_scan_filter_is_case_and_punctuation_insensitive`, `test_scan_extra_name_beats_ble_exclusion_only_when_configured`.

## 7. Transport auto-selection from mock GATT services
- Purpose: service discovery picks nn20, BadgeSdk or an error.
- Inputs: mock links exposing the control service, 0xAE00, 0x01F0, both, none, only unrelated services; the real software badges through `RecordingLink`.
- Expected: control or AE00 gives `badge`; 0x01F0 alone gives `nn20`; both gives `badge`; nothing known raises `ProtocolError`.
- Location: `tests/test_sw_media_scan_transport.py`: `test_transport_from_mock_services`, `test_transport_badge_wins_when_both_present`, `test_transport_unknown_services_is_an_error`, `test_transport_with_software_badges`.

## 8. Thai text rendering
- Purpose: Thai name tags render inside the circle with a font that has Thai glyphs, and never crash without one.
- Inputs: two different Thai strings with subtitles; font from `REBEAMBOX_THAI_FONT` or common Noto Sans Thai, Loma, Garuda, Thonburi, Tahoma paths.
- Expected: 360x360 image, black corners, text inside the safe area, the two renders differ (missing glyphs would draw identical boxes). Skipped when no Thai font exists. A missing font path falls back without an exception.
- Location: `tests/test_sw_media_scan_transport.py`: `test_thai_text_renders_inside_circle_with_known_font`, `test_thai_text_without_font_does_not_crash`.

## 9. Dry-run snapshot of a known image (hex lock)
- Purpose: any accidental change of bytes on the wire fails a test.
- Inputs: a fixed 16x16 gradient JPEG embedded as base64 (independent of the installed JPEG encoder); a deterministic PNG for the CLI test.
- Expected locked values: nn20 frames of the one-frame animation: 2 frames (455 and 320 bytes), first 40 bytes `f1050002000101be7b2274797065223a352c2264617461223a785634122800000001000000b80b00`, SHA-256 of all frames `67aa2a4b...7a4a`; IMB header `494d4200 04000000 b3020000 0b000000 68016801 24000000 93020000 00000000 00000000`, SHA-256 `56281b5e...8f55`; animation container SHA-256 `0cf46d39...c61b`; Wi-Fi POST header text with Content-Length 695. The CLI dry run of a known image has valid checksums, its reassembled envelope equals `{"type":5,"data":<payload file>}`, and two runs give identical files.
- Location: `tests/test_sw_snapshot.py` (seven functions).

## 10. Property based: random valid frames round trip
- Purpose: any valid frame produced by a builder is parsed back exactly, whatever the chunking.
- Inputs: seeded `random` (no extra dependency; hypothesis is not installed) with 100 to 200 cases each: control frames with random command, sequence and payload fed in random chunk sizes; streams of 30 frames; nn20 frames for random type, payload and MTU; nn20 reply streams; RCSP frames with random opcode, direction, sequence and payload followed by trailing bytes.
- Expected: the parsed fields equal the inputs, no bytes lost or invented, remaining buffer correct.
- Location: `tests/test_sw_containers.py`: `test_property_control_frames_round_trip_any_chunking`, `test_property_control_stream_of_many_frames`, `test_property_nn20_frames_reassemble`, `test_property_nn20_reply_stream`, `test_property_rcsp_pack_unpack`.

## Counts
59 test functions in 5 new files, about 83 test cases by default (parametrized) plus 1 slow test. Total with older files is higher.

## Changes made to code for these tests
- `WifiSession.stream` now drops frames above 30720 bytes (the original app only logs a warning) and counts them in `dropped`.
- `pyproject.toml`: `slow` marker registered and deselected by default.
