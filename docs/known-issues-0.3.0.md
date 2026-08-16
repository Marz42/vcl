# Vincula 0.3.0 — Known issues / limitations

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices. Fleet stats are derived from synced connection `started_at` UTC days and are **not** byte-identical with node `vcl stats`.

**Release recommendation:** **NOT READY** — 2026-08-16 contract audit (P2-04 / remediation batch B1) reclassified P0-01 and P0-02 from “documented limitations” to **P0 blockers**. Freeze-era **READY WITH DOCUMENTED LIMITATIONS** is superseded. Living-tree code remediations closed those P0s (B3 / B10) and the remaining P1/P2 + REQ-CI items. **B14 live evidence is deferred** (runbook [`live-replace-checklist.md`](live-replace-checklist.md); [`evidence/0.3.1-live/`](evidence/0.3.1-live/) is NOT RUN). Live-evidence gaps (Win11 `vcl-fleet.cmd`, live VPS replace, real `age`, AC-3.0-11 LIVE-only) remain the RC gate, not a contract mismatch. 0.3.0 does **not** use the D20 24h soak gate. See [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md).

~~Known P0/P1 at freeze: **0**.~~ **Correction (2026-08-16):** freeze filed the replace argv mismatch and the four-member zip as limitations, then claimed zero P0/P1. Those two items are contract failures. **B3 (2026-08-16):** P0-02 is closed on the living tree (`0.3.1-dev`) — the controller zip ships `lib/vincula-audit.py` and `lib/vincula-backup.py`. **B10 (2026-08-16):** P0-01 is closed on the living tree — `node replace` uses the real restore argv on a runtime-only host. **Known P0: 0**. This page does not re-assert Known P1 = 0; remaining audit P1/P2 items were closed in later living-tree batches (see Resolved in 0.3.1-dev). **B14 (2026-08-17):** live secretless replace on two VPS is still a READY FOR RC evidence gap (deferred). Runbook: [`live-replace-checklist.md`](live-replace-checklist.md).

## P0 blockers (post-audit 2026-08-16)

Not product limitations. Fixture green does not close them. P0-02 is closed on the living tree (B3); P0-01 is closed on the living tree (B10).

| ID | Issue | Notes |
| --- | --- | --- |
| **P0-01** | `vcl-fleet node replace` vs real node CLI | **CLOSED (B10).** Controller restore argv is `vcl restore FILE --reissue-output FILE --server HOST --json`. NEW_HOST must be runtime-only (`vincula.sh --runtime-only`, no VERSION). fake-ssh matches the real flags (rejects `--replace-node`; VERSION present fails). Controller-vs-real-bin contract test parses the generated argv with `bin/vincula`. Live VPS handshake remains B14. |
| **P0-02** | Controller zip missing runtime modules | **CLOSED (B3).** Zip members now include `lib/vincula-audit.py` and `lib/vincula-backup.py` beside `lib/vincula-fleet.py`. `load_audit_module` / `load_backup_module` resolve those siblings from the controller’s own `lib/` (zip unpack or repo). Black-box: unzip with no repo `lib/` on `sys.path`, then `version` / `init` / `audit` / `stats` plus `node replace` (unknown-node after init). The freeze-era test `controller zip omits node-side vincula-backup.py` is deleted. |

## Product limitations

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect. Unchanged from 0.2.7–0.2.9 |
| Fleet stats vs node `vcl stats` | Fleet `daily_usage` is rebuilt from synced `audit_events` using UTC day of `started_at`. Cross-midnight connections have no per-day delta |
| No Win11 live controller | Zip layout and stdlib/OpenSSH contract are unit-tested. Live OpenSSH Client + `py -3` on Win11 is operator evidence |
| No live VPS replace | AC-3.0 replace CI = lax → lax2 **fixtures** on the real restore contract (runtime-only NEW_HOST). Live secretless replace + old URI on the new IP is still required before `READY FOR RC` (B14 deferred). Runbook: [`live-replace-checklist.md`](live-replace-checklist.md). Evidence dir: [`evidence/0.3.1-live/`](evidence/0.3.1-live/) (**NOT RUN**). |
| AC-3.0-11 is LIVE-only | “Old credential links fail” needs a real VLESS handshake against the new sing-box. Fixtures only prove the old uuid is absent from inbound `users` (**PARTIAL**). Unit tests must **not** report PASS |
| `age` is a system package | Secretless backups never call age. `--include-secrets` requires `age` (or `$VCL_AGE_BIN`) on PATH. 0.3.0 does not bundle it and does not implement passphrase mode |
| `--from-backup` may drop the sync tail | Escape hatch when the old host is dead. Skips final sync. WARN in stderr. Next sync with a kept cursor past restored `MAX(event_id)` is `CURSOR_AHEAD` (or `CURSOR_EXPIRED` for a retention hole). Remedy is `--reseed`, not another restore |
| Old VPS still up | After safe restore, old uuid + old IP may still work until the old machine is stopped. Cut-over is operational, not a distributed revoke |
| Node restore is fresh-node only | Existing `$STATE_DIR/VERSION` → `Refusing to overwrite an existing Vincula install.` `--replace-node` is **not** a node CLI flag. Fleet replace prepares a runtime-only host instead. |
| `fleet.db` schema 2 irreversible | No automatic 2→1. A 0.2.9 controller will not open schema 2. Rollback the workstation `$FLEET_HOME` copy taken before upgrade |
| `--reseed` still wipes the local audit cache | Deletes that node’s `audit_events` + `daily_usage`, cursor=0. Does **not** erase `instance_history`. Not a substitute for `vcl backup create` |
| D20 soak is not a 0.3.0 gate | 24h soak binds **0.2.7 only** |
| PARTIAL has no distributed rollback | Exit 2 + per-node status + `--user-id` remediation. Unchanged from 0.2.9 |
| Controller is a local tool | No installer, no systemd, no `/etc/vincula`. Not a node `release.lock`. Living tree: `controller.lock` inside the zip + sidecar `vincula-controller-<ver>.zip.sha256` (P2-03 / B13) |
| Windows workstation | Needs **Python 3.10+** on PATH and **system OpenSSH Client**. Neither is bundled |
| Clock skew thresholds | Frozen: WARN `>30s`, FAIL `>300s` check `audit-clock-health`. Not tunable |
| No public management port | Workstation → node is SSH only. Controller does not listen |
| Node helper has no `fleet` | `vcl fleet` is not a node subcommand; use `vcl-fleet` |
| Routine `scp accounting.db` | Forbidden. Sync uses `vcl audit export --after --jsonl`. `scp` of backup archives and reissue CSV is allowed |
| UI | **0.3.1**. Not in 0.3.0 |

## Evidence gaps

| Gap | Notes |
| --- | --- |
| Windows 11 live `vcl-fleet.cmd` | **Not run.** Packaging tests cover zip members and `.cmd` launcher. Same B14 pass: [`live-replace-checklist.md`](live-replace-checklist.md) |
| Live SSH against real VPS | **Not run.** CI uses `tests/fixtures/fake-ssh` / `fake-scp` |
| Live secretless `node replace` | **Not run on two public VPS** (B14 deferred). Living-tree fixture replace (lax → lax2, runtime-only, real `--reissue-output`) is a contract pass, not live PASS. Runbook: [`live-replace-checklist.md`](live-replace-checklist.md) |
| Live `age` on a real node | **Not run.** CI uses `tests/fixtures/fake-age`. Distro `age` + recipient/identity files are operator evidence (same B14 pass) |
| AC-3.0-11 live handshake | **Not run.** Old URI to the **new** IP:443 must fail; new URI must succeed; then stop the old VPS |
| Live 0.2.9 → 0.3.0 upgrade | Allowlist + schema-unchanged unit tests PASS. No live RC-host upgrade run for 0.3.0 |
| Live 24h soak | **Not a 0.3.0 gate** (D20 binds 0.2.7 only) |
| Reboot / full OS matrix | Inherits 0.2.4–0.2.9 gaps |
| Reliable Accounting | Explicitly out of scope |

## Resolved in 0.3.0

| Issue | Notes |
| --- | --- |
| No backup format | Backup schema 1; secretless default; Python SQLite Backup API |
| No age contract | `--include-secrets` + recipient file; D17 exact missing-age line |
| No `vcl restore` | Fresh-node restore; safety directory; reissue CSV; INV-05 rollback |
| No physical replace | `vcl-fleet node replace` vs `node set` rebind; `node instances`. **Post-audit / B10:** replace is callable on a runtime-only host. Live VPS evidence is still B14 |
| No instance history | `fleet.db` schema 2 `instance_history`; not stored in `fleet.json` |
| `--reseed` was the only “snapshot” | Consistent node backup is `vcl backup create`; reseed remains a cache wipe |

## Resolved in 0.3.1-dev (living tree)

| Issue | Notes |
| --- | --- |
| P0-02 controller zip missing audit/backup | B3: zip ships `lib/vincula-audit.py` and `lib/vincula-backup.py`; black-box unpack runs `version` / `init` / `audit` / `stats`; `node replace` fail-closed still works from the zip |
| P1-01 SSH remote argv not POSIX-quoted | B4: `ssh_argv` sends one `shlex.join` string; `ssh_user`/`ssh_host` and `display_name`/`department` reject control characters; node CLI / CSV import match. Spaces in display names stay one remote arg |
| P1-05 Clash 200 + bad envelope treated as empty snapshot | B5: `/connections` body must be an object with `connections` a list of objects. `{}` / wrong types / oversized body are protocol errors (no close-all, no `last_success_at` refresh). Legal `{"connections":[]}` still closes stale. Non-int counters are skipped per connection |
| P1-06 no operation-level mutex (lost updates) | B6: node `flock` on `/run/lock/vincula.lock` (fallback `/var/lock/vincula.lock`) covers user mutations, restore, and `users.json` writers; controller `fcntl` on `$FLEET_HOME/.lock` covers registry mutations and sync/`fleet.db` cursor updates. Timeout 30s → exit 4 `busy: another vincula operation in progress`. flock is fd-based (released on process exit); not a PID file |
| P1-04 audit cursor silently dropped data | B7: node export `CURSOR_AHEAD` (exit 3) when `after > MAX(event_id)`; fleet sync validates meta/JSONL before import and does not advance a stale cursor. `--from-backup` / kept cursor vs an older restored DB fails closed with `--reseed` |
| P1-02 restore not a true transaction | B8: CSV, generated config, and VERSION share the apply_restore try/rollback with canonical files and accounting.db. Rollback also restores the pre-restore sing-box / accountd enabled+active snapshot. Health-check failure no longer restarts sing-box on a mixed tree |
| P1-03 upgrade preflight stopped accountd before backup, with no recovery | B9: read-only preflight (files, schema, disk, REALITY, `sing-box check`) runs before any service mutation. `SERVICE_STATE` is captured and `MIGRATION_STARTED` is armed before backup. SQLite snapshot uses source-tree `snapshot_sqlite` (Backup API); accountd is stopped only for the file-swap window. Rollback restores the exact pretest enabled/active bits |
| P2-01 uninstall left `__pycache__` | B11: install validation uses in-process `compile()` (no bytecode write). `cmd_uninstall` / `rollback_install` / `rollback_migration` delete `$LIB_DIR/__pycache__` before `rmdir`, so a complete uninstall leaves no product residue |
| P2-02 backup verify/copy held whole files in memory | B12: tar verify streams members in 1 MiB chunks; `info.size` over `MAX_MEMBER_BYTES` (1 GiB) or total over `MAX_ARCHIVE_BYTES` (2 GiB) is `invalid_archive` before `extractfile`. `atomic_replace` is a chunked copy. `accounting.db` stays on disk (Backup API + tempfile) |
| P2-03 incomplete release integrity chain | B13: controller zip writes `controller.lock` + sidecar `.zip.sha256`; `sha256sum -c` verifies. Production bootstrap refuses without `RELEASE_SHA256` (or embed); with a pin, archive must match pin **and** shipped `${URL}.sha256`. Sibling digest from the same URL is transport-only |
| REQ-CI no GitHub Actions workflow | B16: `.github/workflows/ci.yml` merge gate — unit (`ubuntu-latest` + Debian 12/13 containers), concurrency (B6 flock/busy), failure-injection (restore/upgrade/Clash fixtures in `test.sh`), artifact (build + black-box unzip + sha256). No secrets. Live `rc-live-upgrade-driver` stays manual |

## Deferred (living tree)

| Item | Notes |
| --- | --- |
| B14 live two-VPS replace + AC-3.0-11 | Operator checklist [`live-replace-checklist.md`](live-replace-checklist.md); evidence [`evidence/0.3.1-live/`](evidence/0.3.1-live/) is **NOT RUN**. Win11 `vcl-fleet.cmd` and real `age` are the same pass |
| B15 localhost UI | Phase B. Not started. Blocked on B14 policy |

## Related docs

- [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md)
- [`live-replace-checklist.md`](live-replace-checklist.md)
- [`backup.md`](backup.md)
- [`fleet.md`](fleet.md)
- [`identity.md`](identity.md)
- [`accounting-reliability.md`](accounting-reliability.md)
- [`known-issues-0.2.9.md`](known-issues-0.2.9.md)
