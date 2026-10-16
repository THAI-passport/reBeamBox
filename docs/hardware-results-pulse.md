# Hardware results: Beambox e-Badge Pulse (2026-10-15/16)

First tests of reBeamBox on a real badge. One unit, one host (macOS, Python 3.13, bleak 3.0.2), 16 uploads in total. Details and evidence per finding: [problem_solution.md](problem_solution.md) entries 82 to 93; plan: [live-test-phases.md](live-test-phases.md).

## What works [H]

| Feature | Command | Result |
|---|---|---|
| Discovery | `rebeambox scan --model nikko`, `probe --qualify` | Advertises `beambox e-Badge Pulse`, service 0xAF30 in the advert, nn20 GATT (0x01F0/F1/F2), MTU 512 |
| Still image | `send-image photo.jpg --model nikko` | Shown at once, correct orientation, about 5 s end to end |
| Both still encodings | default (type 5) and `--nn20-still album` (type 6) | Both listed in the gallery |
| GIF | `send-gif party.gif --model nikko` | Plays, shown at once, about 15 s for 20 frames |
| Text | `send-text "Test" --model nikko` | Readable |
| Video | `send-video clip.mp4 --max-seconds 10` | A 10 s, 15 fps clip (3.5 MB) plays fully |
| BLE slideshow | `stream synthetic --transport nn20` | One clip uploaded and shown; choppy by design (each clip is a flash write) |

## Measured values

- Status JSON pushed by the badge about once a second after notify is enabled: `size "368,368"`, `allspace 16384` KB, `time_mode 1` (no-ACK).
- Throughput, no-ACK, 20 ms packet interval: about 19.7 KB/s (5 s clip 1.7 MB in 90 s, 10 s clip 3.5 MB in 177 s). The vendor app is about the same.
- Post-upload hold: the badge shows a new upload only if the host stays connected for 1 to 2 s after the last packet; default 2 s (`--post-upload-hold-s`).

## Behaviour to know

- The badge advertises only on its Bluetooth page, and turns Bluetooth off after each upload. Turn it on again before every send.
- Uploads are gallery items. Delete them on the badge itself (gallery menu). No delete command is known on the nn20 protocol, so the client cannot clear the badge.
- The retail "3 s video" limit does not apply to this unit.

## Not tested or open

- Wi-Fi path: this badge has no access point.
- NANO and NIJI models: not available.
- On macOS, the `claude` CLI cannot use Bluetooth (no app bundle, so no permission); commands were run through Terminal.app (problem 82). A normal terminal is fine.
- One duplicate still listed once; slight flicker in the top right of a GIF; after the tests the vendor Android app on one phone did not list the badge although the phone received its adverts (problem 93).
