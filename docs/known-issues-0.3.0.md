# Vincula 0.3.0 — Known issues / limitations

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices. Fleet stats are derived from synced connection `started_at` UTC days and are **not** byte-identical with node `vcl stats`.

**Release recommendation:** **READY WITH DOCUMENTED LIMITATIONS** — fixture coverage for backup / restore / `node replace` is green; there is no Windows 11 live `vcl-fleet.cmd` run, no live VPS secretless replace, no real `age` on a production node, and AC-3.0-11 remains LIVE-only. 0.3.0 does **not** use the D20 24h soak gate. See [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md).

Known P0/P1 at freeze: **0**.

## Product limitations

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect. Unchanged from 0.2.7–0.2.9 |
| Fleet stats vs node `vcl stats` | Fleet `daily_usage` is rebuilt from synced `audit_events` using UTC day of `started_at`. Cross-midnight connections have no per-day delta |
| No Win11 live controller | Zip layout and stdlib/OpenSSH contract are unit-tested. Live OpenSSH Client + `py -3` on Win11 is operator evidence |
| No live VPS replace | AC-3.0 replace CI = lax → lax2 **fixtures**, not two public VPS. Live secretless replace + old URI on the new IP is still required before `READY FOR RC` |
| AC-3.0-11 is LIVE-only | “Old credential links fail” needs a real VLESS handshake against the new sing-box. Fixtures only prove the old uuid is absent from inbound `users` (**PARTIAL**). Unit tests must **not** report PASS |
| `age` is a system package | Secretless backups never call age. `--include-secrets` requires `age` (or `$VCL_AGE_BIN`) on PATH. 0.3.0 does not bundle it and does not implement passphrase mode |
| `--from-backup` may drop the sync tail | Escape hatch when the old host is dead. Skips final sync. WARN in stderr. Remaining hole is still `--reseed`, not another restore |
| Old VPS still up | After safe restore, old uuid + old IP may still work until the old machine is stopped. Cut-over is operational, not a distributed revoke |
| Node restore is fresh-node only | Existing `$STATE_DIR/VERSION` → `Refusing to overwrite an existing Vincula install.` `--replace-node` is **not** a node CLI flag |
| Fleet replace argv vs node CLI | `vcl-fleet node replace` SSHes `vcl restore … --replace-node NODE_ID`. Fixture `fake-ssh` accepts that flag. Real `vcl restore` rejects `--replace-node` and refuses VERSION. Live replace on a completed bootstrap is **untested** |
| Controller zip omits `vincula-backup.py` | Zip still four members. `node replace` local verify loads `lib/vincula-backup.py` beside `vincula-fleet.py` (repo checkout / node tarball). A zip-only unpack cannot load that module |
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
| Live secretless `node replace` | **Not run.** Fixture replace (lax → 203.0.113.18 / lax2) is green |
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
| No physical replace | `vcl-fleet node replace` vs `node set` rebind; `node instances` |
| No instance history | `fleet.db` schema 2 `instance_history`; not stored in `fleet.json` |
| `--reseed` was the only “snapshot” | Consistent node backup is `vcl backup create`; reseed remains a cache wipe |

## Related docs

- [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md)
- [`backup.md`](backup.md)
- [`fleet.md`](fleet.md)
- [`identity.md`](identity.md)
- [`accounting-reliability.md`](accounting-reliability.md)
- [`known-issues-0.2.9.md`](known-issues-0.2.9.md)
