# Problems and solutions log

Running log of every pitfall hit, solved or not. Append a new entry whenever anything goes wrong. Newest entries go at the bottom. Dates are 2026-10-11 unless stated (Asia/Saigon time).

Entry format: date, phase, problem, cause, solution (or Status: Unsolved plus what was tried).

---

## 1. Relative path bug in setup-tools.sh
- Date: 2026-10-11
- Phase: Tool setup
- Problem: First run installed the JDK, jadx and apktool, then failed with `cd: ./scripts/..: No such file or directory`, so the venv step never ran and no tool was on PATH.
- Cause: The script did `cd ~/tools` early, then later ran `cd "$(dirname "$0")/.."`. With a relative `$0` (`./scripts/setup-tools.sh`) that path no longer resolved from the new directory.
- Solution: Compute `ROOT="$(cd "$(dirname "$0")/.." && pwd)"` at the very top, before any `cd`, and use `cd "$ROOT"` later. Re-running is safe because the script is idempotent. Status: Solved.

## 2. tshark needs root
- Date: 2026-10-11
- Phase: Tool setup
- Problem: tshark (Wireshark CLI) could not be installed.
- Cause: It is only available through apt, and the box user has no sudo (`sudo -n true` fails, uid 1000).
- Solution: The script prints "tshark unavailable without root" instead of failing. Workarounds if packet captures are needed: ask for sudo, build Wireshark in user space, or parse btsnoop logs directly in Python. Not needed so far because analysis is static. Status: Unsolved (worked around, not installed).

## 3. Missing git identity
- Date: 2026-10-11
- Phase: Repo and provenance
- Problem: `git commit` failed with "Author identity unknown".
- Cause: No user.name or user.email configured on the box.
- Solution: Set a repo-local identity matching earlier commits (`git log -1 --format='%an <%ae>'`): `git config user.name ReverseBot` and `git config user.email bot@users.noreply.github.com`. Staged changes were kept, so just re-run the commit. Status: Solved.

## 4. Deleted current working directory
- Date: 2026-10-11
- Phase: APK validation
- Problem: After `rm -rf /tmp/ax` the shell refused further commands: "The shell's working directory no longer exists".
- Cause: The previous command had `cd`'d into the temp directory and then deleted it, and the shell session persists its cwd.
- Solution: Pass `working_directory` (for example /workspace) on the next call, and always `cd` out of a temp directory before deleting it. Status: Solved.

## 5. java and tools not on PATH in a fresh shell
- Date: 2026-10-11
- Phase: Tool setup
- Problem: `java`, `jadx` and `apktool` reported "command not found" right after installation.
- Cause: The PATH line was appended to ~/.bashrc, which a non-interactive shell does not source.
- Solution: Run `source ~/.bashrc` or export `JAVA_HOME=$HOME/tools/jdk` and `PATH=$JAVA_HOME/bin:$HOME/tools/jadx/bin:$HOME/tools/apktool:$PATH` in the same command. Documented in SOP section 2. Status: Solved.

## 6. Large download backgrounded by the shell timeout
- Date: 2026-10-11
- Phase: APK sourcing
- Problem: The 72 MiB APKPure download exceeded the 30 s foreground limit and was moved to the background with no output.
- Cause: Shell tool time limit.
- Solution: Wait on the job and read its output file. Verified size against the redirect's `full_size` parameter (75,266,587 bytes). Same applied to the jadx run, which was started with nohup and a log. Status: Solved.

## 7. Conflicting versions and sizes on listing sites
- Date: 2026-10-11
- Phase: APK sourcing
- Problem: Listing sites disagreed: version 1.0.13 versus 1.0.8 versus the mirror's 1.0.14, and sizes of 57 MB, 77.7 MB and 108.8 MB. One listed an MD5 that could not be matched to our file.
- Cause: Different sites cache old versions, count different artefacts (single APK versus XAPK), and some are low-quality mirrors.
- Solution: Treated listing sites as hints only. Downloaded from APKPure and trusted the file's own manifest (version 1.0.14, versionCode 24) and our own SHA-256. Recorded both in analysis/SOURCES.md. Status: Solved. Residual risk: no official hash to compare against and the signing certificate was not verified.

## 8. Download was an XAPK, not a plain APK
- Date: 2026-10-11
- Phase: APK sourcing
- Problem: The expected APK was a zip bundle (.xapk) with split APKs.
- Cause: APKPure serves split-APK apps as XAPK.
- Solution: Listed it with `unzip -l`, read manifest.json, extracted only the base APK for analysis and kept the arm64 split for the native library inventory. Status: Solved.

## 9. jadx exits with code 3 and 63 errors
- Date: 2026-10-11
- Phase: Decompile
- Problem: jadx finished with "finished with errors, count: 63" and exit code 3. Some methods, including the animation file builder (`BadgeMediaFileBuilder.a`), were emitted as stubs with a type-inference error ("Types fix failed").
- Cause: jadx cannot always recover types in heavily optimised (R8) bytecode. Exit 3 only signals per-method failures, not a failed run.
- Solution: Output is usable (10,755 files). For the failed methods, read the smali with apktool, or re-run jadx on that class with `--show-bad-code` or `--comments-level debug`. Not yet done for the animation builder. Status: Unsolved for the 63 methods (GIF container details still inferred from `BinConverter`).

## 10. jadx progress log is unreadable
- Date: 2026-10-11
- Phase: Decompile
- Problem: Reading the log showed one huge line and the "done" marker did not exist yet when checked, so the first check looked like a failure.
- Cause: jadx writes progress with carriage returns, and the run took 45 s while the first check happened mid-run.
- Solution: `tr '\r' '\n' < analysis/jadx.log | grep -v progress:` and wait for analysis/jadx.done before judging. Status: Solved.

## 11. Searching for the receive parser found nothing
- Date: 2026-10-11
- Phase: Trace protocol
- Problem: `grep` for the notification parser method signature (`boolean b()`) in the BLE manager returned nothing, so the badge's reply layout could not be read.
- Cause: Obfuscated names and decompiler formatting meant the guessed signature did not match. The work was also interrupted by a new request before a second search.
- Solution: Pending. Next step: read `manager/k.java` (`onCharacteristicChanged`) and follow the call that consumes the accumulated buffer in `manager/m.java`, then confirm the 0xA0 reply layout. Status: Unsolved.

## 12. Interrupted or slow git clones
- Date: 2026-10-11
- Phase: Tool setup
- Problem: Raised as a known risk for fetching tools or reference repos (skill installs from GitHub).
- Cause: Large repositories over a slow link can time out.
- Solution: Not observed during the commands in this log; tools were fetched as release archives (JDK tarball, jadx zip, apktool jar) rather than cloned, which avoided the issue. If it occurs: use `git clone --depth 1`, retry, or download the release archive. Status: Not encountered (prevented by design).

## 13. Unresolved unknowns blocking full protocol tracing
- Date: 2026-10-11
- Phase: Trace protocol
- Problem: Several protocol facts could not be established from the first static pass.
- Cause: Obfuscated code, failed decompiles, no hardware to observe live traffic, and no packet capture tools (see entry 2).
- Solution: Status: Unsolved. Open items, also listed in docs/PROTOCOL.md: type code for still image versus GIF (5 versus 6); layout of the badge's reply notifications; whether service 0x03C4 is another hardware revision; whether any pairing or auth handshake exists; exact GIF container over BLE and the AVI builder's role; whether the ACK batching is mandatory. Plan: finish static tracing (callers of the send function, smali for failed methods), then validate against hardware or a btsnoop capture.
