# First session with a real badge

Goal: in one sitting, find out which transport the badge uses, whether the documented bytes work, and capture enough evidence to fix the client afterwards. Nothing here needs the vendor app except step 1 (capture). Related: PROTOCOL.md, models.md, wifi-protocol.md, problem_solution.md. Run the software tests first (software-test-v1.md), then use hardware-test-v1.md for the structured tests (H1 to H7) after this checklist.

Rules: write down every command you run and its output. A failure with a log is more useful than a success without one. Never share your Wi-Fi password or full Bluetooth addresses publicly; redact the last 3 bytes.

## 0. Before you start (10 min)
- Charge the badge above 50 percent. Know the model (NIKKO/Pulse, NANO, NIJI), firmware version shown in the vendor app if you have it, and the exact product name on the box.
- Computer: Python env from README, `pip install -e .[dev]`, Bluetooth adapter on, `python -m pytest -q tests` green.
- Phone with the vendor app (only for the reference capture in step 1). Enable Developer options, "Enable Bluetooth HCI snoop log" (Android), then toggle Bluetooth off and on.
- Optional: nRF Connect for Mobile (Nordic) on a phone, a second laptop or a Wi-Fi capable computer for the access point capture.

## 1. Reference capture with the vendor app first (15 min)
Do this once before using rebeambox, because it is the ground truth.
1. Restart the HCI snoop log (Bluetooth off, on).
2. In the vendor app: select the model, connect, send one still image, one GIF (or video), nothing else. Note the wall-clock time of each action and what the badge showed.
3. Pull the log: `adb pull /sdcard/btsnoop_hci.log` (path varies: `adb bugreport` and look under `FS/data/misc/bluetooth/logs/` on Android 12 and later; Samsung: dial `*#9900#`, copy dumpstate). Open in Wireshark with filter `btatt` (or `btl2cap`); save with a name like `ref-<model>-<date>.pcapng`.
4. If the badge has Wi-Fi (settings screen shows an access point, or the app asks to join `E-Badge...`): see step 6 for the Wi-Fi capture instead.

## 2. Scan and identify the badge (5 min)
Put the badge on its Bluetooth pairing screen. Press the badge Bluetooth button once if the vendor instructions say so.
```
rebeambox scan --all --timeout 15 | tee scan-all.txt
rebeambox scan --model nikko --timeout 15      # or nano / niji
rebeambox scan --name E-badge --name Nikko --timeout 15
```
Record: advertised names (expected: `E-badge`, `Nikko-badge(BLE)`, `NEO...`, `B-Device...`), RSSI, service UUIDs, manufacturer data. Also look at the phone Wi-Fi list for an SSID containing `E-Badge`; if present the model has the Wi-Fi path (docs/wifi-protocol.md).

Then dump the GATT table of the badge (also do it in nRF Connect and use its Export (XML) feature):
```
rebeambox probe <ADDRESS> --json gatt-<model>.json
```
Shortcut: `rebeambox probe --qualify --model <model>` does the scan, MTU, GATT, transport decision and a read-only handshake in one go and writes `reports/first-contact-<timestamp>.md` in the results template layout (attach it to the issue). To decode the vendor-app reference capture afterwards: `python tools/replay_pcap.py btsnoop_hci.log --out extracted/`. Software tests: docs/software-test-v1.md; hardware plan: docs/hardware-test-v1.md.
Decide the transport from the services:
- Service `000001F0-...` (0x01F0) with characteristics 0x01F1/0x01F2: nn20 path.
- A custom 0x9E control service plus Jieli RCSP (UUIDs in PROTOCOL.md 2 and 3.7): BadgeSdk path.
- Neither: record everything and stop; do not write anything.

## 3. Dry runs (2 min)
Prove the files you will send. Keep them, attach them to the report.
```
rebeambox send-image photo.jpg --model nikko --dry-run dry-nn20.txt --transport nn20
rebeambox send-image photo.jpg --dry-run dry-badge.txt --transport badge
rebeambox send-image photo.jpg --transport wifi --dry-run dry-wifi.txt     # only if step 2 showed a Wi-Fi AP
```

## 4. Live BLE sends, in this order (20 min)
Stop at the first one that works; if one fails record the exact output, power-cycle the badge, then try the next. Use `--address` once you know it. Each command sends a harmless still.
1. Auto transport, model profile (stills as one-frame type 5 container for nn20):
   `rebeambox send-image photo.jpg --model nikko --address <ADDRESS>`
2. Force nn20, container still (same as 1 without discovery): `rebeambox send-image photo.jpg --model nikko --transport nn20 --address <ADDRESS>`
3. nn20 album (type 6, IMB): `rebeambox send-image photo.jpg --model nikko --nn20-still album --address <ADDRESS>`. The Niji reportedly shows black with this, so it is a diagnostic.
4. Size variants if the picture is cropped or black: `--size 360`, then `--size 368`, then `--square` (no circular mask).
5. BadgeSdk path (names NEO or B-Device, or the 0x9E service present): `rebeambox send-image photo.jpg --transport badge --address <ADDRESS>`
6. Animation: `rebeambox send-gif party.gif --model nikko --address <ADDRESS>`, then `send-video clip.mp4 --max-seconds 3` (needs ffmpeg).
7. Text: `rebeambox send-text "Test" --model nikko --address <ADDRESS>`
8. Unreliable link: there are no tuning flags yet. Pacing and MTU constants live in `rebeambox/nn20.py` (guard time, data per packet) and `rebeambox/session.py`; if a send stalls, retry once, then record the log and the last notification and report it (do not guess new values without a capture).
Run each with `2>&1 | tee run-<n>.txt`. Take a photo or video of the badge after each send.

Linux: BlueZ must be running (`systemctl status bluetooth`) and your user able to use D-Bus Bluetooth. macOS: allow Bluetooth for the terminal. Windows: pair nothing; close other apps holding the badge (the phone app must be disconnected, a badge accepts one central).

## 5. Capture while testing (parallel)
- Linux HCI capture: `sudo btmon -w rebeambox-<model>-<date>.btsnoop` before running a send; open in Wireshark. Or `sudo hcidump -w file`.
- macOS: install Xcode "Additional Tools" PacketLogger, start capture. Windows: Wireshark with USBPcap on the Bluetooth adapter, or the Microsoft Bluetooth ETW tracing (`BluetoothTrace`).
- nRF Connect: connect, enable notifications on 0x01F2 (nn20) and RCSP notify characteristic, export the session log.
- Save the console output of rebeambox with timestamps (`ts` or `| while read l; do echo "$(date +%T) $l"; done`).

## 6. Wi-Fi badge capture (only if an SSID like E-Badge exists) (20 min)
1. Join the badge access point from the computer (nmcli, networksetup, netsh; see docs/wifi-protocol.md section 2). Record whether a password was needed, the DHCP lease (`ip addr`, `ip route`: expect 192.168.8.x and gateway 192.168.8.1).
2. Port scan, politely, once: `nmap -Pn -p 80,8080 192.168.8.1`.
3. Capture on the computer interface: `sudo tcpdump -i <wlan> -w badge-wifi.pcap host 192.168.8.1` while running rebeambox. For the vendor app reference capture use the phone app PCAPdroid (local VPN capture, no root) while the vendor app sends, then export the pcap; the vendor app traffic never needs a second computer.
4. Run `rebeambox send-image photo.jpg --transport wifi`, then `rebeambox stream clip.mp4 --fps 2`, then raise `--fps` to 3, 5 and 8 (the client clamps below 300 ms between frames only if you ask for more than 3.3 fps; to test faster, edit `MIN_FRAME_INTERVAL` in `rebeambox/wifi.py` and record where the picture stutters).
5. Compare with the reference capture: control words 00 69 / 00 5F / 00 79 / 00 7B / 00 7A / 00 7F, HTTP request header, response text.

## 7. What to record (copy the template)
```
reBeamBox first-session report
date / time zone:
model (box and app): NIKKO/Pulse | NANO | NIJI      firmware / app version:
computer OS, Python, bleak version, adapter chipset:
phone (reference capture): model, Android version

SCAN
 advertised name(s):
 service UUIDs:
 manufacturer data (hex, redact address):
 Wi-Fi SSID visible (name, open or protected):
 gatt-<model>.json attached: yes/no      nRF Connect export attached: yes/no

TRANSPORT DECISION: nn20 | badge | wifi | none      reason:

SENDS (one block per attempt)
 command:
 result: picture shown ok | black | cropped | garbled | nothing | error text
 time to finish (s):
 badge reaction (sound, light, reboot):
 log file:
 notes (MTU printed, ack mode, retries):

SIZE / SHAPE: picture size reported by badge (if any), visible area, circle or square, orientation (rotated?):
ANIMATION: frames shown, speed, loop, max length accepted:
TEXT: fits, readable, scrolling?:
WI-FI (if any): password needed, IP, ports open, upload response, fps where stutter began:
CAPTURES ATTACHED: ref-btsnoop, rebeambox-btsnoop, nRF export, pcap, photos
SURPRISES / ANYTHING ELSE:
```

## 8. Where to report
- Open an issue on the project repository (THAI-passport/reBeamBox) titled `First session: <model> <date>` and paste the template; attach files that do not contain secrets. Use the issue template `.github/ISSUE_TEMPLATE/first-session.md`.
- Append anything that went wrong to docs/problem_solution.md as a new numbered entry (date, phase, problem, cause, solution or Unsolved).
- If a byte-level assumption was wrong, fix docs/PROTOCOL.md and mark the claim Confirmed (hardware) or Corrected, and update the relevant test vector.
- Redaction: remove the last three bytes of Bluetooth addresses, Wi-Fi passwords, and any serial numbers from logs before uploading.
