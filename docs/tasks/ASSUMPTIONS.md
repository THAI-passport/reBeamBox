# Assumptions

Use these instead of asking. Each is reversible and has a test that would prove it wrong. If your situation is not covered, add a row to the log at the bottom (see `README.md` assumption policy).

## Pre-made assumptions
| Id | Assumption | Basis | How it is proven wrong | Effect if wrong |
|---|---|---|---|---|
| A1 | The badge under test is a NIKKO (Pulse) unless the owner says otherwise | Project owner: Pulse = NIKKO [USER] | Advertised name, box, vendor app shows another model | Use `--model nano` or `--model niji`; Niji-only tests (HW-13) apply |
| A2 | Transport is nn20 (service 0x01F0, write 0x01F1, notify 0x01F2) | Third-party reports for Nano and Niji [W]; code supports it [C] | `probe --qualify` shows 0xAE00 / C2E6FD00 instead | Use `--transport badge`; run HW-14 (auth) |
| A3 | The badge has no Wi-Fi access point | FCC filing lists Bluetooth band only [W] | An SSID containing `E-Badge` appears while the badge is on | Run HW-12 |
| A4 | Picture size is what the badge reports (status JSON `size`), else 368 on nn20 | `docs/FACTS.md` section 2 | Status shows 360,360 or a picture is cropped | The client already follows the report; update FACTS.md |
| A5 | Stills should be sent as type 5 (`--nn20-still gif`, default) | Niji report [W] | Type 5 shows nothing, type 6 shows the picture | Flip `still_mode` in `rebeambox/models.py` for that model |
| A6 | Video cap is 3 s for NIKKO and NANO, 5 s for NIJI | Retail data and app trimmer [W] and [C] | HW-10 plays longer clips | Update `video_max_s` in `rebeambox/models.py` and FACTS.md |
| A7 | The badge advertises only on its pairing screen, under the name `E-badge` or `Nikko-badge(BLE)` | Third-party reports [W] | Scan finds it in another state or under another name | Add the name with `--name`; record in models.md |
| A8 | Flash is a 16 MiB SPI NOR with finite endurance; wear levelling unknown | Teardown [W] | HW-7 shows free space behaviour; chip marking (HW-17) | Adjust safe-write defaults only with owner approval |
| A9 | The badge accepts one BLE central at a time | General BLE behaviour [I] | Two centrals connect | Drop the "close the phone app" instruction |
| A10 | A request to the vendor server is out of scope | Project rule | Owner explicitly approves | Record the approval in the result file |
| A11 | The software badges (`rebeambox/sim.py`) prove consistency only | Written from our own reading of the spec | A hardware result disagrees with them | Fix the simulator and the spec together, retag the claim |
| A12 | Python 3.10 to 3.12, Linux or macOS for development | `pyproject.toml`, AGENTS.md | CI failure on another version | Record in problem_solution.md |
| A13 | The APK used for static work is Beambox+ 1.0.14 (versionCode 24), hashes in `analysis/sources.env` | `analysis/SOURCES.md` | `rebuild_analysis.py` reports a hash mismatch | Never `--accept-new-hash` without telling the owner; a new version means re-running S1 and S2 |

## Log (append; newest last)
| Id | Date | By | Assumption | Why | How to falsify | Impact |
|---|---|---|---|---|---|---|
