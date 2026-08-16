# Vincula 0.3.0 — Known issues / limitations

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices. Fleet stats are derived from synced connection `started_at` UTC days and are **not** byte-identical with node `vcl stats`.

**Release recommendation:** **NOT READY** — 2026-08-16 contract audit (P2-04 / remediation batch B1) reclassified P0-01 and P0-02 from “documented limitations” to **P0 blockers**. Freeze-era **READY WITH DOCUMENTED LIMITATIONS** is superseded. Live-evidence gaps (Win11 `vcl-fleet.cmd`, live VPS replace, real `age`, AC-3.0-11 LIVE-only) remain; they are not the reason for NOT READY. 0.3.0 does **not** use the D20 24h soak gate. See [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md).

~~Known P0/P1 at freeze: **0**.~~ **Correction (2026-08-16):** freeze filed the replace argv mismatch and the four-member zip as limitations, then claimed zero P0/P1. Those two items are contract failures. **B3 (2026-08-16):** P0-02 is closed on the living tree (`0.3.1-dev`) — the controller zip ships `lib/vincula-audit.py` and `lib/vincula-backup.py`. **Known P0: 1** (P0-01). This page does not re-assert Known P1 = 0; remaining audit P1/P2 items are tracked in the 0.3.0 external-audit remediation plan (outside this repository).

## P0 blockers (post-audit 2026-08-16)

Not product limitations. Fixture green does not close them. P0-02 is closed on the living tree (B3); P0-01 remains.

| ID | Issue | Notes |
| --- | --- | --- |
| **P0-01** | `vcl-fleet node replace` vs real node CLI | **B2 (P0-01a):** CLI fail-closed — exit 2, **NOT IMPLEMENTED against real vcl**; does not rewrite `fleet.json`. Help/docs no longer teach the fake restore argv. Unreachable body still contains `vcl restore … --replace-node NODE_ID --output FILE` pending B10. Real `vcl restore` rejects `--replace-node`, uses `--reissue-output`, and refuses an existing `$STATE_DIR/VERSION`. Fixture `fake-ssh` still implements the old controller protocol (not exercised by living-tree replace tests). **Contract mismatch, not a live-evidence gap.** |
| **P0-02** | Controller zip missing runtime modules | **CLOSED (B3).** Zip members now include `lib/vincula-audit.py` and `lib/vincula-backup.py` beside `lib/vincula-fleet.py`. `load_audit_module` / `load_backup_module` resolve those siblings from the controller’s own `lib/` (zip unpack or repo). Black-box: unzip with no repo `lib/` on `sys.path`, then `version` / `init` / `audit` / `stats` plus `node replace` fail-closed. The freeze-era test `controller zip omits node-side vincula-backup.py` is deleted. |

## Product limitations

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect. Unchanged from 0.2.7–0.2.9 |
| Fleet stats vs node `vcl stats` | Fleet `daily_usage` is rebuilt from synced `audit_events` using UTC day of `started_at`. Cross-midnight connections have no per-day delta |
| No Win11 live controller | Zip layout and stdlib/OpenSSH contract are unit-tested. Live OpenSSH Client + `py -3` on Win11 is operator evidence |
| No live VPS replace | AC-3.0 replace CI = lax → lax2 **fixtures**, not two public VPS. Live secretless replace + old URI on the new IP is still required before `READY FOR RC`. **Additionally blocked by P0-01** (even a live run would fail the real CLI contract) |
| AC-3.0-11 is LIVE-only | “Old credential links fail” needs a real VLESS handshake against the new sing-box. Fixtures only prove the old uuid is absent from inbound `users` (**PARTIAL**). Unit tests must **not** report PASS |
| `age` is a system package | Secretless backups never call age. `--include-secrets` requires `age` (or `$VCL_AGE_BIN`) on PATH. 0.3.0 does not bundle it and does not implement passphrase mode |
| `--from-backup` may drop the sync tail | Escape hatch when the old host is dead. Skips final sync. WARN in stderr. Remaining hole is still `--reseed`, not another restore |
| Old VPS still up | After safe restore, old uuid + old IP may still work until the old machine is stopped. Cut-over is operational, not a distributed revoke |
| Node restore is fresh-node only | Existing `$STATE_DIR/VERSION` → `Refusing to overwrite an existing Vincula install.` `--replace-node` is **not** a node CLI flag. (Intentional node contract. The P0 is fleet replace contradicting it — see P0-01.) |
| `fleet.db` schema 2 irreversible | No automatic 2→1. A 0.2.9 controller will not open schema 2. Rollback the workstation `$FLEET_HOME` copy taken before upgrade |
| `--reseed` still wipes the local audit cache | Deletes that node’s `audit_events` + `daily_usage`, cursor=0. Does **not** erase `instance_history`. Not a substitute for `vcl backup create` |
| D20 soak is not a 0.3.0 gate | 24h soak binds **0.2.7 only** |
| PARTIAL has no distributed rollback | Exit 2 + per-node status + `--user-id` remediation. Unchanged from 0.2.9 |
| Controller is a local tool | No installer, no systemd, no `/etc/vincula`, **no `release.lock` chain** |
| Windows workstation | Needs **Python 3.10+** on PATH and **system OpenSSH Client**. Neither is bundled |
| Clock skew thresholds | Frozen: WARN `>30s`, FAIL `>300s` check `audit-clock-health`. Not tunable |
| No public management port | Workstation → node is SSH only. Controller does not listen |
| Node helper has no `fleet` | `vcl fleet` is not a node subcommand; use `vcl-fleet` |
| Routine `scp accounting.db` | Forbidden. Sync uses `vcl audit export --after --jsonl`. `scp` of backup archives and reissue CSV is allowed |
| UI | **0.3.1**. Not in 0.3.0 |

## Evidence gaps

| Gap | Notes |
| --- | --- |
| Windows 11 live `vcl-fleet.cmd` | **Not run.** Packaging tests cover zip members and `.cmd` launcher |
| Live SSH against real VPS | **Not run.** CI uses `tests/fixtures/fake-ssh` / `fake-scp` |
| Live secretless `node replace` | **Not run.** Living-tree CLI is fail-closed (P0-01a). Former fixture replace (lax → lax2) is **not** a contract pass |
| Live `age` on a real node | **Not run.** CI uses `tests/fixtures/fake-age`. Distro `age` + recipient/identity files are operator evidence |
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
| No physical replace | `vcl-fleet node replace` vs `node set` rebind; `node instances`. **Post-audit / B2:** CLI fail-closed (NOT IMPLEMENTED against real vcl); **P0-01** remains until B10 |
| No instance history | `fleet.db` schema 2 `instance_history`; not stored in `fleet.json` |
| `--reseed` was the only “snapshot” | Consistent node backup is `vcl backup create`; reseed remains a cache wipe |

## Resolved in 0.3.1-dev (living tree)

| Issue | Notes |
| --- | --- |
| P0-02 controller zip missing audit/backup | B3: zip ships `lib/vincula-audit.py` and `lib/vincula-backup.py`; black-box unpack runs `version` / `init` / `audit` / `stats`; `node replace` fail-closed still works from the zip |
| P1-01 SSH remote argv not POSIX-quoted | B4: `ssh_argv` sends one `shlex.join` string; `ssh_user`/`ssh_host` and `display_name`/`department` reject control characters; node CLI / CSV import match. Spaces in display names stay one remote arg |
| P1-05 Clash 200 + bad envelope treated as empty snapshot | B5: `/connections` body must be an object with `connections` a list of objects. `{}` / wrong types / oversized body are protocol errors (no close-all, no `last_success_at` refresh). Legal `{"connections":[]}` still closes stale. Non-int counters are skipped per connection |
| P1-06 no operation-level mutex (lost updates) | B6: node `flock` on `/run/lock/vincula.lock` (fallback `/var/lock/vincula.lock`) covers user mutations, restore, and `users.json` writers; controller `fcntl` on `$FLEET_HOME/.lock` covers registry mutations and sync/`fleet.db` cursor updates. Timeout 30s → exit 4 `busy: another vincula operation in progress`. flock is fd-based (released on process exit); not a PID file |

## Related docs

- [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md)
- [`backup.md`](backup.md)
- [`fleet.md`](fleet.md)
- [`identity.md`](identity.md)
- [`accounting-reliability.md`](accounting-reliability.md)
- [`known-issues-0.2.9.md`](known-issues-0.2.9.md)
