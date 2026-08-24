# Vincula 0.2.9 — Known issues / limitations

> **(0.2.x 历史文档，命令名 vcl 已迁移为 vcl-fleet)**

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices. Fleet stats are derived from synced connection `started_at` UTC days and are **not** byte-identical with node `vcl stats`.

**Release recommendation:** **READY WITH DOCUMENTED LIMITATIONS** — fake-ssh multi-node fixture coverage for Fleet Users & Audit is green; there is no Windows 11 live `vcl-fleet.cmd` run and no live SSH against real VPS nodes (provision / sync / retire). 0.2.9 does **not** use the D20 24h soak gate. See [`release-readiness-0.2.9.md`](release-readiness-0.2.9.md).

Known P0/P1 at freeze: **0**.

## Product limitations

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect. Unchanged from 0.2.7/0.2.8 |
| Fleet stats vs node `vcl stats` | Fleet `daily_usage` is rebuilt from synced `audit_events` using UTC day of `started_at`. Cross-midnight connections have no per-day delta. Do not expect byte-level agreement with `vcl stats` |
| No Win11 live controller | Zip layout and stdlib/OpenSSH contract are unit-tested. Live OpenSSH Client + `py -3` on Win11 is operator evidence |
| No live multi-node VPS | AC-2.9-01 CI “two nodes” = lax + tokyo **fixtures**, not two public VPS. Operator should verify `user add` / `sync` / `retire` on real SSH before production |
| Retire cannot disable the last enabled user | Node invariant: refuse disable of the last enabled user. Retire best-effort-disables the rest and WARNs that owner/last credentials remain on the node |
| `--reseed` is not a 0.3.0 snapshot | Reseed wipes that node’s local `audit_events` + `daily_usage`, resets cursor to 0, and pulls the remaining `--after 0` window. Consistent SQLite backup is **0.3.0** |
| D20 soak is not a 0.2.9 gate | 24h soak binds **0.2.7 only**. Inherited accounting-durability gap remains |
| PARTIAL has no distributed rollback | Exit 2 + per-node status + `--user-id` remediation. Successful nodes are not undone |
| Controller is a local tool | No installer, no systemd, no `/etc/vincula`, **no `release.lock` chain**. Integrity is the zip you unpacked |
| Windows workstation | Needs **Python 3.10+** on PATH and **system OpenSSH Client**. Neither is bundled |
| Clock skew thresholds | Frozen: WARN `>30s`, FAIL `>300s` check `audit-clock-health`. Not tunable in 0.2.9 |
| No public management port | Workstation → node is SSH only. Controller does not listen |
| `fleet.json` schema 2 irreversible | No automatic schema 2→1. Rollback is restore of node `backup_existing_install` + the 0.2.8 installer; workstation `fleet.db` / schema-2 `fleet.json` are not understood by 0.2.8 |
| Accounting / users / state schemas unchanged | Accounting stays 3; `users.json` stays 2; `state.json` stays 2. No remint of `instance_id` |
| Node helper has no `fleet` | `vcl fleet` is not a node subcommand; use `vcl-fleet` on the workstation |
| Routine `scp accounting.db` | Forbidden. Sync uses `vcl audit export --after --jsonl` over SSH |
| `replace-node` / backup / UI | **0.3.0+**. 0.2.9 retire does not uninstall or erase history |

## Evidence gaps

| Gap | Notes |
| --- | --- |
| Windows 11 live `vcl-fleet.cmd` | **Not run.** Packaging tests cover zip members and `.cmd` launcher. Live user add / sync on Win11 is operator evidence |
| Live SSH against real VPS | **Not run.** CI uses `tests/fixtures/fake-ssh`. Operator should verify `vcl-fleet user add` / `sync` / `node retire` against at least two real nodes before production use |
| Live 0.2.8 → 0.2.9 upgrade | Allowlist + schema-unchanged unit tests PASS. No live RC-host upgrade run for 0.2.9 |
| Live 24h soak | **Not a 0.2.9 gate** (D20 binds 0.2.7 only). Inherited 0.2.7 soak gap remains for accounting durability |
| Reboot / full OS matrix | Inherits 0.2.4–0.2.8 gaps |
| Reliable Accounting | Explicitly out of scope |

## Resolved in 0.2.9

| Issue | Notes |
| --- | --- |
| No fleet-global `user_id` injection | Node `--user-id`; controller generates one UUID and SSHes it to each target |
| No multi-node provisioning | `vcl-fleet user add --nodes`; PARTIAL exit 2; credential CSV 0600 |
| Original AC-2.8-08/09 deferred | Incremental sync + durable `fleet.db` cursor landed as AC-2.9-08/09/12 |
| No `vcl audit export --after` | Node jsonl + `CURSOR_EXPIRED` (exit 3); controller `sync` / `--reseed` |
| No fleet audit/stats | `vcl-fleet audit` / `stats` merge by `user_id` and keep **node** labels |
| No node retirement | `node retire`: final sync, snapshot dir, mark `retired`, history kept |
| `fleet.json` schema 1 only | Schema 2 adds `status` (`active` \| `disabled` \| `retired`) |

## Related docs

- [`release-readiness-0.2.9.md`](release-readiness-0.2.9.md)
- [`fleet.md`](../fleet.md)
- [`identity.md`](../identity.md)
- [`accounting-reliability.md`](../accounting-reliability.md)
- [`known-issues-0.2.8.md`](known-issues-0.2.8.md)
