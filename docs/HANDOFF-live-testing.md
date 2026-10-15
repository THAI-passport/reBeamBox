# Live Testing Handoff Guide (reBeamBox)

**Audience:** An autonomous AI coding agent (or engineer) picking up the live testing session on the real hardware.  
**Repository:** `THAI-passport/reBeamBox`  
**Active Working Branch:** `docs/grok-improvements`  
**Date:** 2026-10-15 (UTC+7 / Asia/Saigon)  
**Primary Guide:** [docs/live-test-phases.md](file:///Users/puredent/Desktop/reBeamBox/docs/live-test-phases.md)  
**Rules & Constraints:** [AGENTS.md](file:///Users/puredent/Desktop/reBeamBox/AGENTS.md)

---

## 1. Executive Summary & Hardware Milestone

We have successfully completed **Batch A: Phase 0 (Preflight)** and **Phase 1 (Read-Only Recon)** against the physical hardware.

### Confirmed Hardware Ground Truth `[H]`
- **Target Device:** `beambox e-Badge Pulse` (identified on box as Pulse / NIKKO profile).
- **Host Address (macOS CoreBluetooth UUID):** `3F81ED53-xxxx` (full value only in the local shell variable `BADGE`, never in a committed file).
- **Advertised Service:** `0000af30-0000-1000-8000-00805f9b34fb`.
- **GATT Transport:** **`nn20`** (Service `000001f0-0000-1000-8000-00805f9b34fb`).
  - Write Characteristic (`0x01F1`): Handle 65 (`write-without-response`).
  - Notify Characteristic (`0x01F2`): Handle 67 (`notify`).
- **Negotiated MTU:** **512** bytes (yielding 446 payload data bytes per BLE packet).
- **Status JSON (pushed unprompted on 0x01F2):**
  ```json
  {
    "size": "368,368",
    "freespace": 13876,
    "time_mode": 1,
    "allspace": 32000,
    "brand": "...",
    "devname": "beambox e-Badge Pulse",
    "type": 0
  }
  ```
- **Disputes Settled:**
  1. **Picture Size:** Confirmed **368x368** natively reported by badge (settles dispute in [docs/FACTS.md](file:///Users/puredent/Desktop/reBeamBox/docs/FACTS.md)).
  2. **Storage:** ~13.87 MB free out of 32 MB total (`freespace: 13876` KB).
  3. **Pacing:** `time_mode: 1` selects no-ACK mode default.
- **Flash Writes Used So Far:** **0** (verified via `rebeambox uploads`).

---

## 2. Environment & Toolchain

- **OS:** macOS 26.5.2 (Darwin 25F84, x86_64).
- **Python:** 3.13.5 in virtual environment `.venv`.
- **Installed Packages:**
  - `rebeambox 0.1.0` (editable)
  - `bleak 3.0.2`
  - `Pillow 12.3.0`
  - `pytest 9.1.1`
- **Media Pre-Generated:** Located in [live/media/](file:///Users/puredent/Desktop/reBeamBox/live/media) (`photo.jpg`, `gradient_label.png`, `gradient.png`, `party.gif`, `clip2.mp4`..`clip10.mp4`).
- **Local Logs Directory:** `live/` (already added to `.git/info/exclude`).

### Verification Commands
```bash
# Activate virtualenv (or invoke directly from .venv/bin/)
source .venv/bin/activate

# Check test suite (expect 364 passed, 3 skipped, 1 deselected)
.venv/bin/pytest -q tests

# Check repo rules and fixtures
.venv/bin/python tools/check_repo_rules.py
.venv/bin/python tools/make_fixtures.py --check

# Check safe-write counter (must show 0)
.venv/bin/rebeambox uploads
```

---

## 3. Peripheral & BLE Connection Quirks

1. **Only One Central at a Time (Rule 8):**
   - The user has an Android phone with the vendor companion app. If Bluetooth is on or the app is open on their phone, the phone will grab the connection immediately and the badge will stop advertising.
   - Always ask the owner to force-stop the vendor app or toggle phone Bluetooth off before running test commands.
2. **Sleep / Advertising Timeout:**
   - When disconnected, the badge sleeps after a few tens of seconds.
   - If `BleakDeviceNotFoundError: Device with address 3F81ED53... was not found` occurs, ask the owner to press the button on the badge to wake it to the pairing screen.
   - When running CLI commands, pass `--timeout 15` so the BLE scanner has adequate time to catch an advertisement packet.
3. **Beware False Targets:**
   - In earlier scans, a smartwatch replica named `Watch Ultra` (`5301DFC1-xxxx`, Bluetrum AB56xx running HryFine protocol) was active nearby.
   - Always target the specific UUID via `--address "$BADGE"` (set it locally from `live/p1/probe-pulse.txt`).

---

## 4. Next Phase Instructions

You are at the boundary between **Batch A** and **Batch B**.

### Option 1: Complete Phase 2 (Vendor App Reference Capture)
If the user wants to provide the ground truth capture first:
1. Owner enables Bluetooth HCI snoop log on Android phone.
2. Owner sends `photo.jpg` and `party.gif` from the official Beambox companion app to the badge.
3. Owner pulls the capture file to `live/p2/ref-<model>-<date>.btsnoop`.
4. Run replay analysis:
   ```bash
   .venv/bin/python tools/replay_pcap.py live/p2/ref-*.btsnoop --out live/p2/extracted/ 2>&1 | tee live/p2/replay.txt
   ```
5. Record first 5 frames, written handles (`0x01F1`), and sequence results.

### Option 2: Proceed Directly to Batch B (Phase 3: First Write)
If skipping Phase 2, begin **Phase 3 (First Write: One Still)**:
- **Goal:** One image rendered on the badge from `rebeambox`.
- **Write Budget:** Max 3 attempts (safe-write policy active, default 30s interval).
- **Execution Step:**
  ```bash
  # Start packet logging if desired, then send first test image:
  time .venv/bin/rebeambox send-image live/media/gradient_label.png \
      --model nikko \
      --address "$BADGE" \
      2>&1 | tee live/p3/send-image.txt
  ```
- **Owner Screen Confirmation Gate (Rule 6):**
  - Do NOT assume exit code 0 or an ACK means success.
  - Ask the user to visually inspect the badge screen and answer:
    1. *Is the image shown?*
    2. *Is the orientation correct (red arrow pointing UP)?*
    3. *Are corner labels TL/TR/BL/BR cropped or visible?*
    4. *Is it smooth or garbled?*
  - Request a photo if possible.
- **Check Uploads Counter:**
  ```bash
  .venv/bin/rebeambox uploads
  ```

---

## 5. Roadmap for Subsequent Phases

Refer to [docs/live-test-phases.md](file:///Users/puredent/Desktop/reBeamBox/docs/live-test-phases.md) for full phase details:

| Phase | Description | Max Writes | Critical Notes |
|---|---|---|---|
| **P4** | Still encoding & geometry | 5 | Compare `--nn20-still gif` (type 5) vs `--nn20-still album` (type 6). Verify `--size 368` vs `360`. Verify identical send is skipped by delta rule. |
| **P5** | GIF, text, video limit | 5 | `send-gif live/media/party.gif`, `send-text "Test"`. Binary search for video length (5s $\rightarrow$ 10s or 3s). |
| **P6** | BLE throughput | 3 | Calculate KB/s from P3–P5 timings first. Run 3 back-to-back GIF sends with `--no-delta --min-interval-s 10`. |
| **P7** | Wi-Fi live streaming | 1 + stream | Only if an `E-Badge*` SSID exists. Verify internet route isn't broken. Test persistence after reboot to confirm camera mode does not wear flash. |
| **P8** | Wrap-up | 0 | Compile `live/SUMMARY.md` with recommended code and doc changes. |

---

## 6. Logging & Safety Discipline

1. **Problem Log:**
   - Any anomaly, tool issue, or protocol surprise must be appended to [docs/problem_solution.md](file:///Users/puredent/Desktop/reBeamBox/docs/problem_solution.md).
   - Last entry is **81**. Next entry MUST be numbered **82**.
2. **Steps Log:**
   - Append every step and decision with Asia/Saigon (UTC+7) timestamps to [docs/steps.md](file:///Users/puredent/Desktop/reBeamBox/docs/steps.md).
3. **Safe-Write Caps:**
   - Never use `--force` or `--no-safe-write` on physical hardware.
   - Hard daily limit is 50 writes per badge. The revised plan uses at most 18 total writes.
4. **Data Redaction:**
   - Mask the last 3 bytes of Bluetooth MACs (`3F81ED53-xxxx`) in all committed files and user responses.
   - Never commit captures or `.btsnoop` files into git (directory `live/` is git-excluded).
