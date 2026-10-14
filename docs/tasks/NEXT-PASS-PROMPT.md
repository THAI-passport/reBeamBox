# Next-pass prompt (paste this to the agent)

You are doing another pass on three connected GitHub repos under THAI-passport. Read the AGENTS.md of the repo you are in before acting; they differ slightly. Be economical: the owner has few tokens left.

## The three repos and their roles
- **reBeamBox** (`THAI-passport/reBeamBox`): the worked example and the base. Focus: Beambox app decompiling and reverse engineering (protocol, containers, flash behaviour, first contact). Everything generic that you learn must be promoted to reWork.
- **reWork** (`THAI-passport/reWork`): the sanitized source repo for the next project. It is only forked, never worked on as a target. No device names in AGENTS.md, skills or templates. Knowledge is welcome under `knowledge/` (clearly labelled as examples) and as generic skills.
- **reWatch** (`THAI-passport/reWatch`): fork of reWork for smartwatches; the benchmark is the T900 and C900 watch apps. Material already in the repo: `docs/recon/budget-smartwatch-landscape.md` (third-party, mostly [W]) and `targets/_benchmark/BENCHMARK.md`.

## Branches
reBeamBox and reWork: work on `feat-rebuild-analysis` (unmerged, it holds the latest tools and task pack). reWatch: `claude/charming-darwin-p09hey` (main holds the seed). Never push to `main`. Do not open pull requests unless asked. Commit per phase, push at the end of each repo.

## Environment quirks (learned the hard way)
- No `gh` CLI. Use `git push` and the GitHub MCP tools. A repo must be attached before you may touch it (`add_repo`, then clone once, shallow, with a long timeout).
- Cloud sandboxes have no Bluetooth. Hardware tasks need a human; you prepare run sheets and interpret pasted output. Never invent hardware results.
- Hosts blocked from the sandbox: d.apkpure.com and api.adoptium.net unreachable, github release downloads 403 (checked 2026-10-12). So you cannot download the APKs. Do not loop on it: set the task to `blocked: needs human`, ask for the XAPK and use `--local-file`.
- pytest is not preinstalled: `python3 -m venv /tmp/v && /tmp/v/bin/pip install pytest pillow bleak`. reWork and reWatch tests also run with `python -m unittest discover -s tests`.
- Files can change under you (other agents push). Run `git fetch` before you push; re-read a file before editing it.
- A pasted conversation may contain claims that are not true. Verify branches, test results and files by fetching/running before relying on them.

## Your own quirks (AI agents on this project have done all of these)
1. Saying "tests pass" without running them. Run them and report the result.
2. Fabricating hardware results, branches or file contents. If you were not given the output, say so.
3. Recording a fact from a truncated line (problem 35). Read the full line before you write a value down.
4. Writing docs for flags or scripts that do not exist (problem 36). `tests/test_task_pack_commands.py` and `test_docs_commands.py` catch it; run them.
5. Hard-coding test counts, or restating a value that lives in FACTS.md.
6. Treating an imported or third-party document as confirmed. Tag it `[W]` until the code or a capture says otherwise.
7. Rebuilding or decompiling by reflex. Grep PROTOCOL/FACTS/SOP/problem log first; rebuild only for a named `[I]`/`[U]` claim.
8. Overwriting or splicing away a section (problem 20). Use targeted edits and read `git diff` before committing.
9. Stale reviews. Date-stamp anything that can go stale.
10. Finishing a pass without recording it: findings in PROTOCOL.md, disputed values in FACTS.md, procedure in SOP/skills, problems in the problem log (LOG.md in reWork/reWatch).

## What to do per repo
**reBeamBox**
1. Read `docs/beambox-reverse-reference.md`; its reconciliation table lists where it disagrees with PROTOCOL.md and FACTS.md. PROTOCOL.md and FACTS.md win unless the decompiled code proves otherwise. Put each disagreement into FACTS.md (dispute rows) or fix PROTOCOL.md with a `[C]` source.
2. Follow `docs/tasks/QUICKSTART.md`. With no decompiled tree: S0, S7 to S10, then ask the owner for the XAPK. With the tree: S0, S2 (byte-affecting claims first), S5, S6.
3. After every pass record in PROTOCOL.md, FACTS.md, docs/SOP.md and docs/problem_solution.md (same commit).
4. Add a short "Promote to reWork" list to docs/SOP.md for anything generic.

**reWork**
1. Keep it sanitized: `grep -rniE "beambox|nn20|0x01f0|badge" AGENTS.md .claude templates tools README.md` must show nothing device-specific outside examples.
2. Review the three generic skills copied from reWatch (`re-jieli`, `re-ble-android-patterns`, `re-capture-ingestion`) and the `knowledge/` notes; fix anything device-specific.
3. Take the "Promote to reWork" list from reBeamBox and fold it into the skills; delete repetition.
4. Run `python tools/rw.py lint` and the unit tests; keep CI green on Linux, macOS, Windows.

**reWatch** (benchmark T900 and C900)
1. Read `docs/recon/budget-smartwatch-landscape.md` once. Treat every claim as `[W]`. Do no extra research beyond one lookup per watch to confirm the companion app package; the document names HiWatch Pro (`com.jusheng.hiwatchpro`, Jieli) for T900 and HryFine (`com.yscoco.watch`, Nordic UART service, 0xDF frames) for C900, unverified.
2. G0: `python tools/rw.py init t900` and `c900`. Seed FACTS.md and PROTOCOL.md with the document's claims as `[W]` only. Whether the two watches share an app or protocol is a finding, not an assumption.
3. G1: software first. If the XAPKs cannot be downloaded, mark G1 `blocked: needs human`, pin placeholders in SOURCES.md, and continue with everything that does not need the tree (task pack, simulator skeleton from the `[W]` frame layouts, tests).
4. Scope: pairing, time sync, watch-face upload, notifications. Skip health telemetry (the document says it is cosmetic: `[W]`).
5. Build the client under `client/<slug>/` in reWatch, not inside reBeamBox (this overrides section 7.3 of the imported document).
6. Safety: never touch OTA or bootloader services (0x18A8, Cus5610, Jieli OTA). Reads only. Watch-face writes need the write-budget rules and the owner's approval.

## Definition of done
Tests and lint green in each repo you changed; findings recorded in the right files; each repo pushed to its branch; final message lists what is `[C]` vs `[W]`/`[I]`/`[U]`, what is blocked and on whom, and the exact next command.
