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
- Solution: Output is usable (10,755 files). For the failed methods, read the smali with apktool, or re-run jadx on that class with `--show-bad-code` or `--comments-level debug`. Not yet done for the animation builder. Update: `BadgeMediaFileBuilder.a` was recovered from apktool smali (it builds an MJPEG AVI with an ffmpeg command line, see PROTOCOL.md 3.6). Status: Solved for the methods that mattered; the other failed methods were not needed and remain undecompiled.

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
- Solution: Pending. Next step: read `manager/k.java` (`onCharacteristicChanged`) and follow the call that consumes the accumulated buffer in `manager/m.java`, then confirm the 0xA0 reply layout. Update: solved. The parser was in `manager/k.java` (`b()`), reply frame layout documented in PROTOCOL.md 2.5. Status: Solved.

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
- Solution: Status: Unsolved. Open items, also listed in docs/PROTOCOL.md: type code for still image versus GIF (5 versus 6); layout of the badge's reply notifications; whether service 0x03C4 is another hardware revision; whether any pairing or auth handshake exists; exact GIF container over BLE and the AVI builder's role; whether the ACK batching is mandatory. Update after the second pass: resolved items are in PROTOCOL.md (type codes, reply layout, ACK flow, containers, checksums, handshake, name filters, 0x03C4 unused). Still open: Jieli auth algorithm, some reply fields, which path the real badge uses; these need a capture or more disassembly.

## 14. Wrong assumption: one BLE protocol
- Date: 2026-10-11
- Phase: Trace protocol
- Problem: The first pass assumed the 0x01F0 service was the badge protocol. Reading the upload callers showed the app has three transports and the BadgeSdk path uses entirely different framing (control service C2E6FD00 plus Jieli RCSP) and a different media format (AVI, not the IMB container).
- Cause: The first grep for UUIDs hit the nn20 constants class first; the BadgeSdk lives in another package (com.zijun.badgesdk) and uses obfuscated helper classes (te, re, se, qe, f8).
- Solution: Followed the connect handler (o7/t6.java) to see which path each device name takes, then documented both paths in PROTOCOL.md. Status: Solved. Lesson recorded in the SOP: always trace from the UI click to the transport before trusting the first UUID hit.

## 15. Shell commands interrupted by new instructions
- Date: 2026-10-11
- Phase: Trace protocol
- Problem: Two multi-grep commands were interrupted ("Shell command was interrupted by the user") when new requirements arrived, losing their output.
- Cause: Steering messages arrived while a command ran.
- Solution: Re-ran the commands with `timeout` and smaller scope. Status: Solved.

## 16. Broad recursive greps are slow on the full tree
- Date: 2026-10-11
- Phase: Trace protocol
- Problem: `grep -r` across the whole 10,000-file tree sometimes took long enough to risk the shell limit.
- Cause: Large decompiled tree including androidx and Google libraries.
- Solution: Restrict to vendor packages (com/example, com/zijun, te, re, se, qe, f8, o7, p7), use `timeout`, and filter with `-l` first. Status: Solved.

## 17. No objdump for aarch64 and no Ghidra
- Date: 2026-10-11
- Phase: Native analysis
- Problem: The box objdump is x86 only, so libjl_crc.so could not be disassembled directly.
- Cause: No cross binutils installed and no sudo.
- Solution: Installed `capstone` and `pyelftools` into the venv and disassembled the 72-byte CRC function; it is CRC-16/XMODEM (verified check value 0x31C3). Status: Solved for libjl_crc. Unsolved for libjl_auth (11 KB, auth cipher): not disassembled yet.

## 18. Jieli RCSP authentication algorithm not recovered
- Date: 2026-10-11
- Phase: Trace protocol
- Problem: The BadgeSdk file transfer needs the Jieli RCSP link, which authenticates through native code in libjl_auth.so.
- Cause: The cipher is native and was not disassembled in this pass; the Java side only shows the challenge flow.
- Solution: Status: Solved (2026-10-11, second pass). Disassembled with capstone, found E1 on SAFER+, wrote rebeambox/jl_auth.py and verified it against the real native code emulated with unicorn (see entries 21-23).

## 19. Which transport the real badge uses is undecided
- Date: 2026-10-11
- Phase: Trace protocol
- Problem: Both the nn20 (0x01F0) and BadgeSdk (NEO / B-Device) paths exist; static analysis cannot show which one a Beambox+ unit speaks.
- Cause: Selection depends on the advertised name at runtime.
- Solution: Status: Unsolved. Evidence favours the BadgeSdk path. Needs a scan of a real unit or an HCI capture (streaming-plan.md phase 0).

## 20. SOP section 11 accidentally deleted by a splice
- Date: 2026-10-11
- Phase: Documentation
- Problem: When filling SOP section 10 earlier, the replacement text spliced from section 9 up to "## 12", which silently removed the old section 11 placeholder. A later edit that looked for section 11 failed with "substring not found" and left some files committed before the SOP.
- Cause: Slice boundaries in a Python edit script spanned two sections.
- Solution: Re-inserted section 11 with the real tracing method and re-committed. Lesson: splice between adjacent headers only, and verify headings with grep afterwards. Status: Solved.

## 21. First Python port of the auth cipher produced wrong output
- Date: 2026-10-11
- Phase: Native analysis
- Problem: A SAFER+ plus E1 port written from the Bluetooth specification did not match the library.
- Cause: Two details: the Ar' variant folds the input into round 3 with the xor/add pattern of the round key (I had guessed per-position add/xor sets differently), checked by brute-forcing variants against the native Ar; and the native uses a fixed per-byte offset table for the second key.
- Solution: Compared stage by stage (key schedule, Ar, Ar', E1) against the emulated native code until all matched. Status: Solved.

## 22. Emulating the native function under unicorn
- Date: 2026-10-11
- Phase: Native analysis
- Problem: No objdump, Ghidra or device to run the .so; first emulation returned all zero output.
- Cause: The PLT hook for malloc set PC to the link register minus 4, re-executing the call forever until the instruction limit; NEON needed CPACR_EL1 enabled; the TLS canary slot needed a mapped TPIDR_EL0.
- Solution: Hook malloc and free PLT stubs, return to LR directly, enable FP/SIMD, map TLS. Status: Solved (tools/emulate_jl_auth.py).

## 23. awk strtonum not available
- Date: 2026-10-11
- Phase: Native analysis
- Problem: mawk lacks strtonum, so address-range filtering of the disassembly failed.
- Solution: Used a small Python filter. Status: Solved.

## 24. Earlier doc showed the RCSP file name as UTF-16 and 0xDB as ten values
- Date: 2026-10-11
- Phase: Spec review
- Problem: The first PROTOCOL.md draft marked the name encoding as inferred (UTF-16LE) and described 0xDB as ten u16; both were wrong.
- Cause: Written before TransferTask, LargeFileTransferGetNameCmd and the receive parser (se/b.java) were read in full.
- Solution: Reading them showed the StartLargeFileTransfer path is a plain ASCII temp name with NUL, UTF-16LE (prefixed with a backslash-U marker) is only used in the GetName reply for long names, and 0xDB carries twelve u16 values (ten mandatory). Spec and rebeambox/rcsp.py fixed. Status: Solved.

## 25. Bind reply layout partly uncertain
- Date: 2026-10-11
- Phase: Spec
- Problem: The 0x61 parser in se/b.java decompiled with merged branches (shared offset variable), so offsets for protocol >= 26 are only moderately certain.
- Cause: jadx variable merging in a very long method (2098 lines).
- Solution: Documented the table with a caveat; Status: Unsolved at byte level until a real reply is seen or the smali is read. The field is not needed to upload.

## 26. Transport for Beambox+ cannot be proven from the APK
- Date: 2026-10-11
- Phase: Spec
- Problem: Which BLE name the Beambox+ advertises is decided by a server-delivered product list (signal name field), plus hard-coded NEO and B-Device.
- Cause: No local product table in assets, resources or code.
- Solution: Documented the runtime selection rule so a client can follow it (name test, then service discovery). Status: Unsolved without a badge or a capture; no network calls to the vendor backend were made (code-only scope).

## 27. Slow broad grep over the decompiled tree
- Date: 2026-10-11
- Phase: Spec
- Problem: A recursive grep with a multi-name find hung a shell for 30 s.
- Solution: Narrow directories and use timeout. Status: Solved.

## 28. Simulated badge never completed the transfer
- Date: 2026-10-11
- Phase: Client
- Problem: First session-against-simulator run stalled with "no progress for 20 s".
- Cause: The simulator encoded the target-info CRC attribute with record length 6 instead of 5 (length counts the type byte), so the client parsed no CRC flag and sent frames without per-packet CRC that the simulator then rejected.
- Solution: Fixed the simulator record length. Lesson: record `len` includes the type byte; a mismatch silently shifts the parse. Status: Solved. The LTV length rule itself is still [I] for real hardware.

## 29. No Pulse data in the app
- Date: 2026-10-11
- Phase: Client
- Problem: Asked for Pulse-specific names, ids and shapes from the decompiled code.
- Cause: The app has no "Pulse" product table; products arrive from the server list at runtime.
- Solution: Documented in docs/pulse.md; added configurable name filter (--name). Status: Unsolved offline; needs a scan of a real Pulse or the product list response.

## 30. Pillow merged identical GIF frames in a test
- Date: 2026-10-11
- Phase: Tests
- Problem: Expected 30 frames at 100 ms, got interval 357 ms.
- Cause: Test frames repeated colours (byte overflow); Pillow drops duplicate consecutive frames and sums their delay.
- Solution: Use distinct frames. Status: Solved.

## 31. Scan on a machine without Bluetooth printed a bare errno
- Date: 2026-10-11
- Phase: Client
- Problem: `rebeambox scan` on the headless box printed "[Errno 2] No such file or directory".
- Cause: bleak/BlueZ D-Bus socket missing.
- Solution: CLI now prints a hint about a missing adapter or BlueZ. Status: Solved.

## 32. Earlier transport assumption contradicted by hardware reports
- Date: 2026-10-11
- Phase: Models
- Problem: Earlier docs and the client treated the BadgeSdk/Jieli RCSP path as the likely one for Beambox badges and still images as type 6 with an IMB header.
- Cause: Static analysis cannot show which service a given model exposes; server product list decides.
- Solution: Third-party reports on a Niji and a Nano show only service 0x01F0 and a black screen for type 6. Client now defaults still images to a one-frame type 5 container, accepts the name E-badge, and docs/PROTOCOL.md section 7 records the correction. Status: Solved in code, unverified by us on hardware.

## 33. Model names barely appear in the code
- Date: 2026-10-11
- Phase: Models
- Problem: Asked for per-model code paths in m2/g.java, a0/j.java and wg/*; those files hold no model names (wg does not exist in the jadx output).
- Cause: Product identity is server data; code keeps only placeholders and one NIJI comparison.
- Solution: Full-tree case-insensitive grep, then traced the stored keys; documented in docs/models.md. Status: Solved (negative result).

## 34. Wi-Fi sender hidden in unrelated packages
- Date: 2026-10-11
- Phase: Wi-Fi
- Problem: The Wi-Fi socket code (WifiTransferManager) had no write method, and the call sites showed only `getClass()` stubs.
- Cause: R8 moved the upload and command lambdas into a switch class in an androidx package (`processing/c`, `processing/i`) and a vendor OTA package.
- Solution: Grepped for `f6020d.write` and `new byte[]{0,` across the tree to find the writers, then read the dispatcher cases. Status: Solved.

## 35. Wrong claim about the HTTP uploader resume header
- Date: 2026-10-11
- Phase: Wi-Fi docs
- Problem: First draft of docs/wifi-protocol.md said the OkHttp uploader used an X-Offset-like header.
- Cause: Wrote it from the class shape before reading the request builder line (it was cut off by a narrow `cut`).
- Solution: Read the line at full width: it sends `Content-Range: bytes start-end/total`. Doc fixed. Lesson added to SOP 12.2 step 4.

## 36. First checklist draft contained impossible instructions
- Date: 2026-10-11
- Phase: first-session checklist
- Problem: The draft described capturing the vendor app on the badge AP with a second computer and a non-existent `--address-less` flag, and referred to CLI tuning flags that do not exist.
- Cause: Written quickly without checking `--help`.
- Solution: Replaced with PCAPdroid on the phone for the reference capture, tcpdump on the computer joined to the AP for rebeambox, and removed the invented flags. Added `rebeambox probe` for the GATT dump instead.

## 37. Camera frame length versus stop word in the software badge
- Date: 2026-10-11
- Phase: Wi-Fi simulator
- Problem: In camera mode the stream mixes 2-byte length prefixes and 2-byte command words (0x007F stop, 0x0000 end), so a frame length of 127 would look like a stop word.
- Cause: The protocol has no type byte.
- Solution: Sim treats 0x007F as stop (a real JPEG is never 127 bytes). Real badge behaviour is unknown [U]; noted here so a capture can check how the firmware disambiguates.

## 38. Writing tests without being allowed to run pytest
- Date: 2026-10-11
- Phase: software tests v1
- Problem: The new test files had to be written and committed without a pytest run, so assertion mistakes could not be found by execution.
- Cause: The run needs the user's approval.
- Solution: Compiled every file with `py_compile`, re-read each assertion against the module code, and executed only the locked golden values (fixture, hashes, header hex) as plain expressions to be sure the snapshot constants are right. Removed a timing race I noticed in my own first shutter test (sleep-based) by driving the shutter from the frame generator. Status: Unverified by pytest until the run is approved; any failure should be added here.

## 39. App only warns about oversize Wi-Fi frames, client now drops them
- Date: 2026-10-11
- Phase: software tests v1
- Problem: The test plan requires oversize Wi-Fi frames to be dropped, but the client logged a warning and sent them (copying the app).
- Cause: Followed the app literally; the 30720-byte limit is a likely badge buffer size, so sending more is risky.
- Solution: `WifiSession.stream` drops frames above 30720 bytes and counts them in `dropped`; documented in wifi-protocol.md and software-test-v1.md.



## 40. No-ACK fallback needs a restart point the protocol does not give
- Date: 2026-10-11
- Phase: first-contact tooling
- Problem: On a dropped packet in no-ACK mode the badge reply (GetPacketFail) does not say which packet failed, so resuming mid-stream is a guess.
- Cause: The reply text carries no index (code search, PROTOCOL.md section 8).
- Solution: Restart the stream from the first packet in ACK mode (also after a reconnect). The software badge treats a first packet as a new upload. Status: Inferred; hardware test H4 must confirm a real badge accepts a restart.

## 41. Silent badge after reconnect in the fallback test
- Date: 2026-10-11
- Phase: first-contact tooling
- Problem: A test with a simulated disconnect hung in ACK mode because the software badge still ran in time_mode 1 and never acknowledged.
- Cause: Fallback to ACK assumes the badge acknowledges; time_mode 1 may mean it does not.
- Solution: The test flips the simulated badge to ACK mode on reconnect; the client still raises after 3 unanswered batches instead of hanging. Real behaviour is unknown (H4).

## 42. Capture replay dropped frames with bad checksums
- Date: 2026-10-11
- Phase: first-contact tooling
- Problem: Without GATT discovery in a capture, writes were classified by checksum, so corrupted frames vanished instead of being reported.
- Cause: Heuristic required a valid checksum.
- Solution: classify nn20 writes by the consistent length field; checksum failures are counted per transfer. Also fixed the IMB decoder offsets (width and height at byte 16, JPEG length at 24).

## 43. Web Bluetooth cannot read the MTU
- Date: 2026-10-11
- Phase: web harness
- Problem: The browser API exposes no negotiated MTU, so P = min(446, mtu - 12) cannot be computed automatically.
- Cause: Platform limitation.
- Solution: MTU is an input (default 247) and is halved on a write error, up to three times. Hardware confirmation pending.


## 44. Replay tool accepted malformed captures silently
- Date: 2026-10-11
- Phase: fixtures
- Problem: A transfer with a bad checksum and a dropped packet was decoded as if complete, and the RCSP CRC16 detection used only the first chunk (a corrupted first chunk would flip detection).
- Cause: The decoder only counted packets and tested the first chunk.
- Solution: track the expected remaining counter (gaps), detect CRC16 presence from any valid chunk, report per-chunk CRC errors and sequence gaps as warnings, skip container decoding for incomplete transfers, never raise on corrupt containers. Covered by the malformed fixture.

## 45. Fixture determinism
- Date: 2026-10-11
- Phase: fixtures
- Problem: Generating test JPEGs with Pillow would change bytes between Pillow versions and break the committed fixtures.
- Cause: JPEG encoder output is not stable across versions.
- Solution: embed a fixed JPEG and derive frames by inserting a COM segment; timestamps are fixed; `make_fixtures.py --check` and a test compare committed files with a fresh generation.

## 46. Docs legitimately name vendor hosts
- Date: 2026-10-11
- Phase: CI lint
- Problem: A naive host-ban lint would flag the lint's own host list and its tests.
- Cause: The rule needs the strings it forbids.
- Solution: the lint script and its test are exempt from the host rules only (emoji still checked); code files additionally fail on any non-local URL. The repository currently contains no analytics host anywhere.


## 47. Push rejected: token lacks the workflow scope
- Date: 2026-10-11
- Phase: CI
- Problem: `git push` was refused: an OAuth App cannot create or update `.github/workflows/ci.yml` without the `workflow` scope.
- Cause: The stored GitHub credential has no `workflow` scope.
- Solution: Not worked around (no token handling). The unpushed local commits were rewritten so the workflow sits at `ci/ci.yml`, everything else was pushed. Status: Solved 2026-10-12: the token was given the `workflow` scope and the file was moved with `git mv ci/ci.yml .github/workflows/ci.yml`.


## 48. jadx type inference failure on the animation builder, three recovery attempts
- Date: 2026-10-11
- Phase: decompiler recovery
- Problem: `BadgeMediaFileBuilder.a` still fails after `--show-bad-code` and `-m simple`; `--deobf` cannot help a type failure.
- Cause: a Dalvik register is reused as both long and double (1000.0), which jadx type inference rejects.
- Solution: smali read (already done) plus dex2jar and CFR 0.152 on classes2.dex: CFR produced readable code identical in behaviour. Exact behaviour documented in PROTOCOL.md 3.6.1; simple mode reduced errors 63 to 35 and the remaining errors are library code (compose, coroutines, ZXing encoder, media3, GMS). Scripted in scripts/recover-failed-methods.sh.

## 49. Client AVI command differed from the app in fps formatting
- Date: 2026-10-11
- Phase: decompiler recovery
- Problem: the client used an integer fps (`-r 15`) and a fixed -t, the app uses `-r %.3f` from 1000/interval and duration = frames*interval/1000.
- Cause: the first reading of the builder summarised the command but not the number formatting.
- Solution: `avi_command` and `Job.badge_payload` follow the exact formulas; tests updated. Impact on a real badge is Unknown (likely none).

## 50. Wi-Fi camera 127-byte ambiguity: reasoning and mitigation
- Date: 2026-10-11
- Phase: Wi-Fi gaps
- Problem: How does the badge tell a 2-byte frame length from the stop word 0x007F (entry 37)?
- Cause: The app sends no type byte; stop is `00 7F 00 00`, the same shape as a frame with length 127. Firmware cannot be read from the APK.
- Solution: Code review shows all control words have a zero high byte (frame length below 256) and the app never sends such a small frame. Inferred rule: first byte 0x00 means command. Client now pads frames below 256 bytes with a JPEG comment segment (`wifi.pad_jpeg`). Status: firmware rule Unknown; resource strings give no model-to-Wi-Fi mapping (wifi-protocol.md 5.2).


## 51. Native libraries hold no badge limits
- Date: 2026-10-11
- Phase: native pass 3
- Problem: Looked for frame size, packet size or storage limits in libjl_fatfs, libjl_pack_format, libjl_enc, libjl_ota_auth, libcbuf and the FFmpeg kit.
- Cause: Those libraries serve watch-face tooling, OTA and audio; the badge picture limits are Java constants.
- Solution: Documented constants (FatFs sector 512, mkfs unit 4096, FFmpeg n6.0 with mjpeg and avi) in binaries.md; found unexplored RCSP storage commands (browse, delete, format) in the SDK and recorded their ids in PROTOCOL.md 3.7.2 as Unknown payloads.

## 52. FCC ID spelling and unreliable aggregator text
- Date: 2026-10-11
- Phase: web recon
- Problem: The checklist names `2BR3T-BADGE0` and `2BR3T-BAGDE0`; one returned 404. A search summary also quoted "1.28-inch LED display" for Pulse, conflicting with Nikko's 1.83 inch IPS.
- Cause: The grant itself spells the product code "BAGDE0" ("E-Bagde"); marketing copy on resale pages is loose.
- Solution: Verified on the registry page, kept both spellings noted, labelled retail claims W, flagged Pulse panel size as unresolved in docs/recon-web.md and asked H1 to record the physical diagonal. Third-party blog contents are W, not Confirmed.


## 53. Safe-write check needs the payload, which needs the connection
- Date: 2026-10-11
- Phase: safe-write policy
- Problem: Delta skipping needs the hash of the payload, but the payload depends on the picture size the badge reports, so it cannot be computed before connecting.
- Cause: Pictures are rendered at the size the badge advertises (368 versus 360).
- Solution: The gate runs inside `client.send` after the handshake and before the first data frame; a skipped upload writes nothing to flash (only the handshake traffic happened). The counter is advanced after success only. Documented in docs/safe-write.md.


## 54. Streaming benchmark quantised by the source frame grid
- Date: 2026-10-11
- Phase: streaming prototype
- Problem: A 3.3 fps target gave 2.5 fps from a 10 fps synthetic source.
- Cause: Frames exist only every 100 ms, so a 303 ms period waits for the 400 ms frame.
- Solution: Benchmark source runs at 30 fps (3.0 fps delivered at a 3.3 target, 3.36 at 5); noted in the benchmark text that targets between grid steps round down. Floating point comparison got a 1e-6 tolerance so an exact 300 ms spacing is not skipped.

## 55. BLE clips cannot be live and cannot bypass the write guard
- Date: 2026-10-11
- Phase: streaming prototype
- Problem: A BLE "stream" is a series of uploads, each a flash write; at the safe-write default only one clip per 30 s passes.
- Cause: nn20 and BadgeSdk have no live mode; the Wi-Fi camera mode is the only live path in the app.
- Solution: The BLE sink is explicitly a clip sink, shares the safe-write gate, counts policy drops, and the benchmark labels it a slideshow.


## 56. Optional native packages in the default install
- Date: 2026-10-11
- Phase: dependencies
- Problem: `.[dev]` pulled unicorn, capstone and pyelftools, which need wheels or a compiler and are used by only one test file and the RE tools; setup-tools.sh installed pytest without the package metadata.
- Cause: all extras were lumped together.
- Solution: extras split into test, emulation, full, with dev as an alias of test; setup script gained `--full`/`--emulation` and tolerates a failed emulation install; CI installs `.[test]`; `pytest-asyncio` was dropped because no test uses it. Verified in fresh venvs: core+test 303 passed, 2 skipped; full 304 passed, 1 skipped.

## 57. Docs drift: hard-coded test counts and conflicting screen and size values
- Date: 2026-10-12
- Phase: docs
- Problem: README, HANDOFF, SOP and the test plan carried test counts (148, 202, 250, 303, 304) that no longer matched, and screen size, picture size and video cap were restated in several files with different values.
- Cause: Each milestone appended a new number or value instead of replacing the old one.
- Solution: Counts removed (run `pytest -q` or read the Actions result). New `docs/FACTS.md` is the single source for screens, 360 versus 368, transports, chip, limits and safety defaults; README, models.md, pulse.md and HANDOFF link to it. Status: Solved.

## 58. --model overrode the picture size the badge reports
- Date: 2026-10-12
- Phase: client
- Problem: `--model nikko` set `--size` to 368, which then won over the size reported by the badge (for example 360), contradicting the README and the intended rule.
- Cause: `apply_model` copied the profile size into `args.size`, which the client treats as an explicit override. Found while checking docs for contradictions.
- Solution: `apply_model` leaves `args.size` alone; the client falls back to 368 only when the badge reports nothing. Test added in `tests/test_models.py`. Status: Solved.

## 59. Daily write cap
- Date: 2026-10-12
- Phase: safe-write
- Problem: Safe-write only warned about high daily counts, so a loop could still wear out flash.
- Cause: Policy was warnings plus a minimum interval only.
- Solution: Hard cap of 50 writes per badge per rolling 24 hours (`--max-per-day`, 0 disables, `--force` overrides), `CapReached` is a `Blocked` subclass so the CLI exits 2. The default warning threshold moved from 100 to 40 so the warning comes before the cap. Status: Solved.

## 60. Agent rules lived only in prose and a mislabelled review file
- Date: 2026-10-12
- Phase: documentation
- Problem: No AGENTS.md or fixes list existed, so agent rules (safe-write, no vendor artifacts, log upkeep) lived only in the SOP and README. A README test count had drifted again, and the critique of an external review sat in a file named `haiku5.5-is-garbage.md`.
- Cause: Rules were written as procedure, not as instructions an agent loads at session start.
- Solution: Added AGENTS.md, CLAUDE.md and fixes.md; removed the README test count; renamed the critique to `docs/review-critique-2026-10.md`; added a tag-mapping note to PROTOCOL.md. Status: Solved. Hardware testing is still open (see fixes.md).

## 61. Analysis files were not rebuildable by script
- Date: 2026-10-12
- Phase: reproducibility
- Problem: AGENTS.md required that analysis/ be rebuildable, but only prose steps existed, and setup-tools.sh fetched unpinned latest versions.
- Cause: The download, hash check, extraction and jadx run were done by hand once.
- Solution: Added `scripts/rebuild-analysis.sh` driven by `analysis/sources.env`; it refuses on a hash mismatch (`--accept-new-hash` prints the hash and edits nothing), is idempotent and has `--dry-run`, `--force`, `--recover`, `--local-file`. jadx and apktool are pinned. Status: Solved for the local path; the network download is untested in the suite.

## 62. A long jadx run was killed by the tool shell timeout
- Date: 2026-10-12
- Phase: reproducibility
- Problem: Running the rebuild script in the foreground got "Killed" (exit 137) after about 60 s and the script recorded a failed jadx run.
- Cause: Memory pressure on the shared box: jadx stalled at 75 percent and the process was killed (reproduced three times, also when detached). A run with `JAVA_OPTS=-Xmx3g` finished in about 45 s.
- Solution: Cap the heap with `JAVA_OPTS=-Xmx3g` when memory is tight and run detached (`setsid nohup ... &`). The script never treats a killed jadx as success (exit 137 is reported and the marker is not accepted). Status: Solved.

## 63. Version query failed silently under set -e
- Date: 2026-10-12
- Phase: reproducibility
- Problem: With a broken jadx on PATH the script exited 1 with no message.
- Cause: A failing command inside `$(... | head -1)` with pipefail ended the script before the pin check.
- Solution: Version lookups end with `|| true`, so the pin check reports the mismatch with exit 4. Status: Solved.

## 64. Rebuild and setup scripts were bash-only
- Date: 2026-10-12
- Phase: tooling
- Problem: `rebuild-analysis.sh` used `sha256sum` and `declare -A`; `setup-tools.sh` fetched linux/x64 only and edited only `~/.bashrc`. On macOS (bash 3.2, no `sha256sum`) and Windows they did not run, although AGENTS.md listed macOS as supported.
- Cause: bash chosen for convenience; GNU userland assumed.
- Solution: reimplemented both in Python 3 standard library (`scripts/rebuild_analysis.py`, `scripts/setup_tools.py`); the `.sh` files are wrappers. The 18 existing tests passed unchanged against the port before new ones were added (heap option, `--url`, setup URLs and the macOS JDK bundle layout). Also added `--max-heap` (default 3g under 8 GiB RAM) and `--url`. Status: Solved for Linux (tested here); macOS and Windows are covered by CI and unit tests only.

## 65. Cloud session cannot reach the download hosts
- Date: 2026-10-12
- Phase: tooling
- Problem: from a cloud container, `d.apkpure.com` and `api.adoptium.net` are unreachable and github release URLs return 403, so a rebuild stops at the download.
- Cause: the environment network policy allows package managers and a short list of hosts.
- Solution: add the hosts under Allowed domains in the environment settings, or pass `--local-file`. Status: needs the user.

## 66. Recon checklists could not be executed by a newcomer
- Date: 2026-10-12
- Phase: documentation and tooling
- Problem: `hardware-recon-checklist.md` mixed procedures, background and an external review; steps contradicted the tool behaviour (the H8 identical rewrite is skipped by the delta guard, the 30 s interval and 50 per day cap were not budgeted), the free space number was not printed anywhere, test media and a passive notification logger did not exist, the FCC ID spelling was wrong in one place, and nothing said who may do which step (a cloud sandbox has no Bluetooth).
- Cause: the checklist was written before the safe-write policy and the first-contact tooling.
- Solution: new task pack `docs/tasks/` with per-task executor, write cost, exact commands, interpretation tables, stop conditions and an assumption policy; `tools/make_test_media.py`, `tools/notify_log.py`; the nn20 session now logs every status JSON (`badge status:` line, `Nn20Session.status_log`). Status: Solved in documentation; untested by a second agent and by hardware.

## 67. Hash mismatch after a vendor release gave no clue why
- Date: 2026-10-12
- Phase: tooling
- Problem: `analysis/sources.env` pins the XAPK hash but downloads from a `?version=latest` link. After a new release the rebuild stops with only two hashes, and a newcomer cannot tell a corrupt download from a new version. A second known-good source could not be configured.
- Cause: one URL, no version information in the error.
- Solution: `scripts/rebuild_analysis.py` now prints the version the downloaded XAPK reports (manifest.json) against the pinned version, and tries `URL`, `URL2`, `URL3`, `URL4` in order until one matches the pinned hash. Tests in `tests/test_rebuild_analysis.py`. Status: Solved. Open: nobody has recorded a versioned mirror yet, so `URL2` is empty (see fixes.md).

## 68. Task pack mentioned flags that might not exist
- Date: 2026-10-12
- Phase: documentation
- Problem: a step-by-step pack is only as good as its commands; a renamed flag would silently break a hardware session.
- Cause: documentation and CLI evolve separately.
- Solution: `tests/test_task_pack_commands.py` checks every `rebeambox` subcommand and flag and every `python tools/...` / `scripts/...` path mentioned in `docs/tasks/`. It was checked by injecting a bogus flag (the test failed as expected). Also added `docs/tasks/QUICKSTART.md` because the full pack is long and weaker agents skim. Status: Solved.

## 69. A rebuild on a new instance repeated work the docs already held
- Date: 2026-10-12
- Phase: process
- Problem: a fresh agent's default is to rebuild and decompile, which costs a 72 MB download and a jadx run and often answers nothing new; and findings from a pass were not always written back, so the next pass repeated it.
- Cause: no rule said when to rebuild, and no rule said what to record afterwards.
- Solution: AGENTS.md "Rebuild only when necessary" (grep the docs, check for an existing tree, rebuild only for `[I]`/`[U]` claims, new versions or contradictions, `--dry-run` first, state the reason) and "After every decompile pass" (PROTOCOL, FACTS, SOP, problem log in the same commit); SOP 9.2. Status: Solved as process; relies on agents following it.

## 71. External reference documents disagree with the repo
- Date: 2026-10-12
- Phase: documentation
- Problem: an imported Beambox summary states several values with `[C]` that the repo holds as `[W]`/`[I]` or as different numbers (BLE minimum delay, battery size, panel size, what a non-persistent picture proves).
- Cause: external authors blend confirmed and reported facts under one tag scheme.
- Solution: the document is stored as `docs/beambox-reverse-reference.md` with a reconciliation table at the top; PROTOCOL.md and FACTS.md win; each row is closed when the decompiled code or a hardware result settles it. Also added `docs/tasks/NEXT-PASS-PROMPT.md` for the next agent pass. Status: Open until the rows are closed (see fixes.md).

## 70. Hash pinned, but only by a floating latest link
- Date: 2026-10-12
- Phase: reproducibility
- Problem: the only URL for the app is a floating "latest" link, so a vendor update changes the file while the pinned hash stays; a rebuild then fails, and `--accept-new-hash` could be used to move on without a record.
- Cause: the pin was a hash plus a floating URL; no rule asked for a versioned URL, an owner-controlled copy or a new entry per release.
- Solution: AGENTS.md pinning rule, `COPY_LOCATION` in sources.env, warnings from the rebuild script when all URLs float or the copy location is missing, clearer mismatch and accept messages, SOP 9.3, tests. The APKPure link is still floating; no versioned or mirrored URL is known yet, so the owner-controlled copy is the real pin. Status: Mitigated.

## 72. Simulator numbers looked like badge facts
- Date: 2026-10-12. Found during S8.
- Evidence: `rebeambox/sim.py` used bare literals for free space (20000 KB, 32000 KB total, 12000 KB over Wi-Fi). A reader could take them for measured values.
- Cause: the simulator was written before the assumption register existed.
- Solution: named constants with an assumption comment pointing at `docs/tasks/results/S8-2026-10-12.md`; no behaviour change, suite unchanged. The reference document's disputes moved to FACTS.md section 9. Status: Solved.

## 73. Documented guard time used the wrong multiplier
- Date: 2026-10-12. Found during S2.
- Evidence: PROTOCOL 2.6 and the client had `min(ceil(N/1000) * 800 + 800, 3000)` ms. The app's smali multiplies by 0x12c (300). The decompiled Java showed a library constant with the value 300 in that place, so the earlier reading took it for something else.
- Cause: a jadx constant substitution plus a doc line tagged [C] without a second look at the bytecode.
- Solution: `nn20.guard_time_ms` now uses 300 (test updated and extended), PROTOCOL, FACTS section 10, HANDOFF corrected, SOP 12.4 added. Effect: the client waits 500 ms less for small uploads. Status: Solved; the badge's own need for a guard is still [U] (HW-9).

## 74. Free-space margin and ACK retry count did not match the app
- Date: 2026-10-12. Found during S2.
- Evidence: the app refuses an upload when payload + 0x100000 (1 MiB) exceeds free space; the client and docs said 64 KiB. In ACK mode the app counts failures and aborts on the third, so only two retries happen (waits 500 and 1000 ms); docs and client allowed three retries with a 2000 ms wait.
- Cause: another substituted constant (the margin) and an off-by-one in reading increment-then-compare.
- Solution: `FREE_SPACE_MARGIN` and `ACK_ABORT_FAILURES` in `rebeambox/session.py`, two new tests, docs corrected (PROTOCOL, FACTS, HANDOFF, hardware-prediction). Status: Solved. The margin is a client safety choice that happens to match the app.

## 75. Watch device tag was wrong in the scan table
- Date: 2026-10-12. Found during S6.
- Evidence: the SDK's device-type enum has WATCH = 0xB9 (smali), the client and PROTOCOL 3.1 had 0xB5. The enum also lists phone case 0xB0, alarm clock 0xB1, speaker 0xB2, badge 0xB3.
- Cause: a transcription slip from an earlier pass, never cross-checked.
- Solution: `scan.DEVICE_TAGS` and PROTOCOL fixed, test pinning the table added. No effect on badge discovery (only 0xB3 is accepted). Status: Solved.

## 76. FACTS routing row contradicted PROTOCOL
- Date: 2026-10-12. Found during S6.
- Evidence: FACTS section 3 said the BadgeSdk path is chosen by the server product record; the app's code chooses it by the advertised name (NEO or B-Device after normalising), anything else goes to nn20 (PROTOCOL 1.1, re-read in S6).
- Cause: the FACTS row was written from the product-list analysis, not from the connect handler.
- Solution: row corrected and tagged with S6. Status: Solved.

## 77. OTA reachable through RCSP; damaged ledger reset the write cap
- Date: 2026-10-14. Found while porting lessons from reWatch.
- Evidence: Jieli's OTA SDK docs place firmware upgrade on 0xAE00 itself (device-pulled blocks, opcode 0xE5) [W]; `rcsp.pack` accepted any opcode. `safewrite.Store._load` renamed an unreadable `uploads.json` to `.bad` and returned a zero count, so the next write passed the daily cap.
- Cause: OTA was thought of as a separate service; the ledger chose availability over safety.
- Solution: opcode block 0xE0-0xEF in `rcsp.pack` and in BleakLink/RecordingLink (PROTOCOL 3.7.3); the ledger refuses writes, even with `--force`, until `rebeambox uploads --reset`. Tests added; the old test that pinned the reset behaviour now pins the new rule. Status: Solved in code; untested on hardware (no OTA frame is ever sent, so nothing to test there).

## 78. zsh glob error on pip install -e .[test]
- Date: 2026-10-14. Phase: Live P0.
- Evidence: Running `pip install -e .[test]` in zsh produces `zsh: no matches found: .[test]`.
- Cause: zsh interprets square brackets as pattern globbing instead of pip extra syntax.
- Solution: Quote the target as `'.[test]'` or `'rebeambox[test]'`. Status: Solved.

## 79. bleak.__version__ AttributeError in bleak >= 0.22 / 3.0
- Date: 2026-10-14. Phase: Live P0.
- Evidence: `python -c "import bleak; print(bleak.__version__)"` failed with `AttributeError: module 'bleak' has no attribute '__version__'`.
- Cause: Newer versions of bleak (installed: 3.0.2) do not expose `__version__` on the top-level package namespace.
- Solution: Query package version via `importlib.metadata.version('bleak')`. Status: Solved.


## 80. Live test brief written on a stale branch
- Date: 2026-10-14. Phase: Live planning.
- Evidence: `docs/live-test-phases.md` was first written on `docs/grok-improvements` after a `git pull` that only updated that branch; `origin/main` already held problems 57-77, the daily write cap, the `--model` size fix, `docs/steps.md` and AGENTS.md. The brief told agents to number problems from 57 and did not mention steps.md (found by an external review).
- Cause: the planner checked the current branch only, not how far it was behind `main`.
- Solution: branch merged with main, feat/steps-log and integration; brief rewritten: branch check, last+1 numbering, steps.md, on-disk redaction with `tools/scrub_capture.py`, recon before vendor capture, owner screen confirmation, write budget cut from 31 to 18 (boundary video search, throughput from existing sends), Wi-Fi persistence and second-network pre-check. Lesson: before planning, run `git fetch --all` and compare the branch with `origin/main`. Status: Solved.

## 81. Live P1 recon target lacks nn20 (0x01F0) and RCSP (0xAE00) services
- Date: 2026-10-14. Phase: Live P1.
- Evidence: `rebeambox probe 5301DFC1-xxxx --qualify` against `Watch Ultra` connected and read MTU (256) and battery (0x4A / 74%), but reported `FAIL: transport none`. Services present: Battery (0x180F), Device Info (0x180A), 0xFF10, 0xFF12, Nordic UART Service (6E400001-B5A3-F393-E0A9-E50E24DCCA9F), and 0xFF00. Manufacturer data: `0x314C: 4142d013d7cc1234`.
- Cause: The target device is a C900 / Watch Ultra smartwatch clone (Bluetrum AB56xx running the HryFine / Nordic UART protocol; see `budget_smartwatch.md`) rather than a Beambox-family e-badge (`nn20` or Jieli `BadgeSdk`).
- Solution: Phase 1 stop condition triggered as specified in `docs/live-test-phases.md` ("Stop if neither 0x01F0 nor the 0x9E/RCSP service. Write nothing"). Zero flash writes attempted. Status: Solved (safe-write and stop conditions honoured; protocol mismatch documented).

## 82. Bluetooth scan aborts (exit 134) when run from the Claude desktop app
- Date: 2026-10-15. Phase: Live P3 (pre-write check).
- Evidence: `rebeambox scan --all --timeout 10` exits 134 (SIGABRT) with no output when launched by the Claude desktop app's shell, with or without its sandbox. The same command worked from the IDE terminal used for P1.
- Cause: [I] macOS privacy (TCC) kills a process that touches CoreBluetooth when the responsible app has no Bluetooth permission.
- Solution: grant Bluetooth to the Claude app (System Settings, Privacy and Security, Bluetooth) and restart it, or run the live commands from a terminal that already has the permission. Status: Open until the owner chooses.

## 83. First write failed: "badge did not acknowledge packet 0"
- Date: 2026-10-15. Phase: Live P3.
- Evidence: `send-image --model nikko` on the Pulse printed no `badge status` line, chose ACK mode and aborted after about 10 s at packet 0. In P1 `probe --qualify` (which waits up to 3 s) received `time_mode: 1`. Upload counter stayed 0.
- Cause: `Nn20Session.start` waited 50 ms after enabling notify; the badge pushes its status later, so `time_mode` was unknown and the client waited for ACKs a no-ACK badge never sends.
- Solution: `STATUS_WAIT_S = 2.0` in `rebeambox/session.py`: wait up to 2 s for the status before sending, log when it does not come. Status: Fixed in code; hardware retry pending.

## 84. Upload completes but the Pulse shows its own logo, not the image
- Date: 2026-10-15. Phase: Live P3.
- Evidence: after the problem 83 fix, `send-image gradient_label.png --model nikko` (nn20, type 5 one-frame container, no-ACK, 368x368) finished in 3.65 s with exit 0 and counted 1 write. The owner reports the screen shows the Beambox logo, clean, not the test image. No `GetPacketSuccess`/`GetPacketFail` text was logged. The status in this session said `allspace=16384`, while the handoff recorded 32000.
- Cause: unknown. Candidates [I]: the type 5 container is not what this firmware displays for stills (app code uses type 6 album); the badge stored it but needs a separate play or select step; the stream was dropped silently in no-ACK mode.
- Solution: Status: Open. Next: one write with `--nn20-still album` (type 6). If that also shows the logo, stop writing and take a vendor app capture (P2) to compare.
