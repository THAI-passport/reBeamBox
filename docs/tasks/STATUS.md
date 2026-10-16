# Task status

States: `todo`, `doing`, `done`, `blocked: needs human`, `blocked: needs hardware`, `blocked: needs approval`, `skipped: not applicable`.
Update the row when the state changes; link the result file.

## Software (AI alone)
| Task | Title | State | Owner | Result |
|---|---|---|---|---|
| S0 | Baseline: environment, tests, rules | done | AI | suite green, 2 skips (2026-10-12) |
| S1 | Rebuild or obtain the analysis tree | done | AI | results/S1-2026-10-12.md (tree and hashes verified, no rebuild) |
| S2 | Audit the unconfirmed claims in PROTOCOL.md | done | AI | results/S2-2026-10-12.md (22 claims, 4 contradicted and fixed) |
| S3 | Static inventory of the vendor server API | done | AI | results/S3-2026-10-12.md |
| S4 | Static inventory of the firmware update path | done | AI | results/S4-2026-10-12.md |
| S5 | Inventory of everything the badge can send to the app | done | AI | results/S5-2026-10-12.md |
| S6 | Scan filter and model detection audit | done | AI | results/S6-2026-10-12.md (watch tag fixed) |
| S7 | Test media and payload size table | done | AI | results/S7-2026-10-12.md |
| S8 | Simulator assumption register | done | AI | results/S8-2026-10-12.md |
| S9 | First-contact readiness check | done | AI | probe --qualify sims nn20 and badge, replay_pcap and dry runs exit 0 (2026-10-12) |
| S10 | Documentation consistency pass | done | AI | rules ok, drift checked (2026-10-12) |
| S11 | Wrap-up | done | AI | 2026-10-12 |

## Hardware (needs a badge; see HW-RECON.md)
| Task | Title | State | Owner | Result |
|---|---|---|---|---|
| HW-0 | Run sheet, approvals, write budget | done | User + AI | docs/live-test-phases.md (18-write budget approved) |
| HW-1 | Reference capture with the vendor app | todo | | |
| HW-2 | Scan and qualify (H1) | done | AI + User | live/p1/first-contact-20261015-002059.md (PASS: nn20, MTU 512, size 368x368) |
| HW-3 | Wi-Fi presence survey | todo | | |
| HW-4 | Dry runs | done | AI | live/p0/ (dry runs written, payloads verified) |
| HW-5 | Still container test (H2) | todo | | |
| HW-6 | Picture size and shape | todo | | |
| HW-7 | Free space and rewrite behaviour (H8) | todo | | |
| HW-8 | Power-cycle persistence (H9) | todo | | |
| HW-9 | Throughput over BLE (H4) | todo | | |
| HW-10 | Animation and video limits (H7) | todo | | |
| HW-11 | Text and name tags | todo | | |
| HW-12 | Wi-Fi path (H5), only if an access point exists | todo | | |
| HW-13 | Touch notifications (H6), NIJI only | todo | | |
| HW-14 | BadgeSdk auth (H3), only if 0xAE00 is present | todo | | |
| HW-15 | Non-destructive physical survey | todo | | |
| HW-16 | USB enumeration (observe only) | todo | | |
| HW-17 | Destructive teardown and read-only dump (owner approval) | todo | | |
