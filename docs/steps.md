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
