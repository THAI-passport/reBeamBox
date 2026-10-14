# Quickstart (read this first, then only your own task)

The pack is long on purpose, so you do not have to read it all. Pick your situation, do the listed tasks in order, and open only those sections.

| Your situation | Do this, in order | Stop when |
|---|---|---|
| AI agent in a cloud sandbox, no badge, no human | S0, S7, S8, S9, S10, S11 (and S1 to S6 only if the analysis tree is already present or can be rebuilt) | Run sheet for the human is written (HW-0) and STATUS.md is current |
| AI agent, `analysis/decompiled` exists | S0, S2, S5, S6, S8, S9, S11 | Every claim you touched has a recorded outcome |
| AI agent, no `analysis/` and the question is already answered in PROTOCOL.md, FACTS.md, SOP, or the problem log | Do not rebuild. Answer from the docs and say which section | - |
| AI agent, no `analysis/` and a claim tagged `[I]`/`[U]` needs the code | S0, then S1 (`--dry-run` first), then S2 | You have `[C]` or a precise "not settled" for each claim |
| Person with a badge and a laptop | HW-0, HW-2, HW-4, HW-5, HW-6, HW-7, HW-8, then HW-9 to HW-11 | Write budget used up (HW-0) or any stop condition hit |
| Person, badge shows a Wi-Fi network | add HW-3, HW-12 | - |
| Person, badge is a NIJI | add HW-13 | - |
| Person, scan shows service 0xAE00 | add HW-14 | - |
| Owner approved opening one unit | HW-15 to HW-17, in order | Any step answers the question |

## Ten rules to keep in your head
1. Do not rebuild or decompile to "explore". Read `docs/PROTOCOL.md`, `docs/FACTS.md`, `docs/SOP.md` and `docs/problem_solution.md` first (grep them).
2. Never write to the badge outside a listed task. Read-only first. 30 s between writes. Stop at the budget in HW-0.
3. Never claim a hardware result you did not receive as pasted output.
4. One retry after a power cycle, then record and move on.
5. Tag every finding `[C] [V] [H] [W] [I] [U]`.
6. Make assumptions from `ASSUMPTIONS.md`; log new ones. Do not ask what a default can settle.
7. After a decompile pass: record what you learned in `PROTOCOL.md`, disputed values in `FACTS.md`, procedure and tool details in `SOP.md`, problems in `problem_solution.md`, in the same commit.
8. Never commit vendor files, dumps, captures with addresses, or test counts in docs.
9. Run `python tools/check_repo_rules.py` and `python -m pytest -q` before you commit.
10. If a step here is wrong or missing, fix this pack and add an Open item in `fixes.md`: the next agent depends on it.
