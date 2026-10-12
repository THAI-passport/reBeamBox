# Fixes

Things that need fixing and things already fixed. Add to Open when you find something; move it to Fixed with what was wrong and what changed. Same commit as the change.

## Open
- Hardware: nothing is confirmed on a real badge. Run `rebeambox probe --qualify --model nikko`, then follow `docs/first-session-checklist.md`. Every `[I]`/`[S]` claim in `docs/PROTOCOL.md` waits on this.
- `scripts/setup-tools.sh` pins jadx and apktool versions but downloads no checksums and still fetches the "latest" JDK 17; add SHA-256 checks for all three.
- `scripts/rebuild-analysis.sh` download path (network) is not covered by tests; only the `--local-file` path is.
- `docs/PROTOCOL.md` still uses `[C]/[I]/[S]`; tag mapping is documented, but the sections could be migrated to the repo-wide scheme incrementally.
- tshark is not available without root (problem_solution.md entry 2); capture analysis relies on `tools/replay_pcap.py`.

## Fixed
- Analysis files could not be rebuilt away from the original machine by script: added `scripts/rebuild-analysis.sh` and `analysis/sources.env` (hash-verified, idempotent, `--dry-run`, `--force`, `--recover`), jadx and apktool pinned in setup-tools.
- README stated a hard-coded test count (250) that contradicted the no-counts rule in docs/SOP.md 13.5 and had drifted; replaced with a pointer to CI.
- `docs/haiku5.5-is-garbage.md` renamed to `docs/review-critique-2026-10.md` with a neutral title; README links updated.
- No AGENTS.md existed; added AGENTS.md and CLAUDE.md.
