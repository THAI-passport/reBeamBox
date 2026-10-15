# Steps log (reBeamBox)

Chronological record of every step taken and every decision with its rationale.
Times are Asia/Saigon (UTC+7). Append as work proceeds; do not rewrite history.
Required by AGENTS.md.

Backfilled briefly from docs/SOP.md, docs/problem_solution.md and git history (2026-10-13).
Earlier day-to-day detail lives in those logs; new work appends here.

---

## 2026-10 (early) — repo and analysis baseline

- **Decision:** Keep vendor APK out of git; record hashes and rebuild via `scripts/rebuild_analysis.py` / `analysis/SOURCES.md`.
  - **Rationale:** Ground rule against committing binaries; cloud agents must reproduce the tree.
- **Step:** Decompile Hiwear / BeamBox companion with jadx; locate BLE UUIDs and upload pipeline; build local client with safe-write guards.
  - **Rationale:** Interoperability client; flash-wear and brick risk require guards before any send-often feature (see problem_solution entries on daily cap, ACK abort, free-space margin).

## 2026-10-11..12 — protocol hardening and docs

- **Step:** Confirm numeric constants in smali when jadx substitutes library names (guard multiplier 300 not 800; free-space margin 1 MiB; ACK abort on 3rd failure; watch tag 0xB9). Record in PROTOCOL/FACTS/SOP/problem_solution 73–76.
  - **Rationale:** Jadx constant substitution repeatedly misled built-ahead code; smali is authoritative for literals.
- **Decision:** FACTS.md is the only home for disputed values; other docs link there. Daily write cap default 50.
  - **Rationale:** Docs drift (entry 57) and hard-coded test counts caused contradictory sizes; centralise.
- **Step:** Task-pack / rebuild-policy / pin-by-SHA work merged via integration branches; promote reusable tricks into reWork skills where applicable.
  - **Rationale:** Weaker agents need executable checklists; avoid repeating rebuilds when docs already answer.

## 2026-10-13 — steps log introduced

- **Decision:** Add `docs/steps.md` and require append-on-every-step in AGENTS.md (with reWatch and reWork).
  - **Rationale:** Owner instruction. Problem/SOP logs capture pitfalls and procedure; the decision trail (why a pin, why a branch, why a constant) was not required in one place.

## 2026-10-14 — live test suite preparation (Batch A / Phase 0 Preflight)

- **Step:** Merged `origin/main` (containing PR #1: Jieli OTA block by RCSP opcode, fail-closed upload ledger, capture scrubber, safe-write daily cap, scan watch tag 0xB9, and free space margin fixes) and `origin/feat/steps-log` into `docs/grok-improvements`.
  - **Rationale:** The working branch `docs/grok-improvements` had `docs/live-test-phases.md` but lacked recent safety critical fixes and `docs/steps.md`. Merging combined all safety mechanisms, test harnesses, and documentation cleanly without conflicts.
- **Step:** Prepared local `.venv` (Python 3.13, bleak 3.0.2, Pillow 12.3.0, pytest 9.1.1), verified test suite (365 passed, 2 skipped, 1 deselected) and repo rules. Generated full synthetic media in `live/media/` and completed Phase 0 dry runs across all transports (nn20, badge, wifi).
  - **Rationale:** Satisfy Phase 0 preflight gates before any hardware contact.

## 2026-10-14 — live test brief revised after external review

- **Step:** Rewrote `docs/live-test-phases.md`: recon (P1) before vendor capture (P2), touch listen folded into recon, owner screen confirmation per write, budget 18 writes (P5 boundary search, P6 3 runs), Wi-Fi persistence check and second-network pre-check, on-disk redaction, last+1 problem numbering, steps.md logging. Logged problem 80.
  - **Rationale:** Review found the brief predated main's safety changes (daily cap, ledger, steps log) and spent flash writes where existing sends already give the data.

## 2026-10-14 — live test Batch A: Phase 1 Read-only recon

- **Step:** Executed passive scan (`rebeambox scan --all --timeout 15`) and probe qualification (`rebeambox probe <UUID> --qualify --report-dir live/p1`) against advertising device `Watch Ultra` (`5301DFC1-xxxx`).
  - **Rationale:** Execute Live P1 read-only recon before attempting writes or vendor captures.
  - **Finding:** Target connected and exposed MTU 256, battery 74% (handle 2), and GATT services (Battery 0x180F, Device Info 0x180A, 0xFF10, 0xFF12, Nordic UART Service 6E400001, 0xFF00; manufacturer data 0x314C: 4142d013d7cc1234). Transport identified as `none` because Beambox services (0x01F0 / 0xAE00) are absent. Stop condition triggered cleanly; 0 writes performed. Logged problem 81.
- **Step:** Executed passive scan and `rebeambox probe 3F81ED53-xxxx --qualify --timeout 15 --wait 6 --report-dir live/p1` against physical badge `beambox e-Badge Pulse` (`3F81ED53-xxxx`).
  - **Rationale:** First-contact qualification on the actual Beambox hardware.
  - **Result:** [H] PASS. Transport: `nn20` (service `000001f0`, write char `000001f1` handle 65, notify char `000001f2` handle 67). Negotiated MTU: 512 (446 data bytes/packet). Handshake status JSON successfully pushed on 0x01F2 and parsed: `size: 368,368`, `freespace: 13876` KB, `time_mode: 1`, keys (`allspace`, `brand`, `devname`, `freespace`, `size`, `time_mode`, `type`). 0 flash writes used.

## 2026-10-15 — handoff picked up, address masked

- **Step:** Replaced the full CoreBluetooth UUID in `docs/HANDOFF-live-testing.md` with the masked form and a local `$BADGE` variable.
  - **Rationale:** AGENTS.md forbids identifiers in committed files; the handoff itself said to mask it.
- **Step:** Read-only `scan --all --timeout 15` before P3: badge not advertising. P3 held until the owner wakes the badge and disconnects the phone app.
  - **Rationale:** Rule 8 (one central) and the handoff note that the badge sleeps when disconnected.
