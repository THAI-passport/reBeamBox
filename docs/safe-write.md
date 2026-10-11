# Safe-write policy

Why: the badge keeps every sent picture or animation in on-board flash. Third-party teardowns report a 16 MiB SPI NOR part, a FAT16 gallery and 4 KiB page programming ([recon-web.md](recon-web.md), label W), and the endurance of such flash is finite (typically tens of thousands of erase cycles per block in datasheets, [I]; the badge's wear levelling is Unknown). Repeating an upload of the same image, or looping a script that re-sends every second, burns write cycles for no visible change. The client therefore guards every real upload. Live Wi-Fi camera frames are not flash writes as far as the app code shows (a RAM display path, [I]) and are not gated.

What it does (module `rebeambox/safewrite.py`):
- Local upload counter, per badge and in total, saved in `uploads.json` under `~/.local/state/rebeambox` (or `$XDG_STATE_HOME/rebeambox`, `$REBEAMBOX_STATE_DIR`, `--state-dir`). The badge is identified by a SHA-256 prefix of its address (or `--badge-id`, or the Wi-Fi host); the address itself is not stored. Nothing is sent anywhere.
- Delta skipping: the SHA-256 of the exact payload (the container or AVI that would be written) is stored after a successful upload. If the next upload to the same badge produces the same bytes, nothing is written to the badge and the command exits 0 with "skipped".
- Minimum interval between writes to one badge (default 30 s). A write that comes sooner is refused with exit code 2.
- Hard daily cap: at most 50 writes to one badge in a rolling 24 hours (`--max-per-day N`, 0 turns the cap off). The 51st is refused with exit code 2 before anything is written; a refused write is not counted, and `--force` overrides the cap.
- Warnings, not refusals: more than 40 writes in 24 hours, or more than 10,000 writes to one badge in total (thresholds configurable, 0 turns a warning off).
- The counter is advanced only after the upload finished without error, so a failed attempt is not counted. The check runs after connecting (the payload depends on the size the badge reports) and before the first data frame, so a skipped upload writes nothing to the badge's flash.
- `--dry-run` never reads or writes the counter.

Flags (all send commands): `--min-interval-s N`, `--max-per-day N`, `--warn-per-day N`, `--warn-total N`, `--force` (ignore interval, daily cap and unchanged-image skip), `--no-delta` (keep the interval but resend identical images), `--no-safe-write` (policy and counting off), `--badge-id NAME`, `--state-dir DIR`. Command `rebeambox uploads` prints the counters; `rebeambox uploads --reset` clears them.

Limits and notes:
- The counter only knows about writes made by this client; the vendor app and other tools are invisible to it.
- A different encoding of the same picture (another quality or a different model profile) is a different payload and is written.
- The hash covers the payload, not the badge's stored state: if the badge was reset or its storage cleared, use `--force`.
- Counting is per machine. Two computers talking to one badge keep separate counters.
- Hardware tests H8 and H9 in [hardware-recon-checklist.md](hardware-recon-checklist.md) measure free space and rewrite behaviour and may justify different default thresholds. Until then the defaults are conservative guesses, not endurance data.

Tests: `tests/test_safewrite.py` (counter persistence, hashing instead of addresses, skip, interval, warnings, bounded history, corrupt state file, client wiring for nn20, BadgeSdk and Wi-Fi, CLI flags and exit codes).
