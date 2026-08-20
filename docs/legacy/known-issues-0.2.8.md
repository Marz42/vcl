# Vincula 0.2.8 — Known issues / limitations

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices.

**Release recommendation:** **READY WITH DOCUMENTED LIMITATIONS** — offline fixture coverage for Fleet Foundation is green; there is no Windows 11 live `vcl-fleet.cmd` run and no live SSH against real VPS nodes. 0.2.8 does **not** use the D20 24h soak gate. See [`release-readiness-0.2.8.md`](release-readiness-0.2.8.md).

## Product limitations

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect. Unchanged from 0.2.7 |
| Incremental sync / fleet users | **Not in 0.2.8.** `vcl-fleet user *`, `--user-id`, incremental audit sync, `vcl audit export --after event_id`, `CURSOR_EXPIRED` belong in **0.2.9** |
| Original AC-2.8-08 / AC-2.8-09 | Original English SPEC cursor-consistency ACs are **deferred to 0.2.9**. Revised SPEC covers 08 as mock SSH (registry/status/verify/host-key) and 09 as registry persistence. Mock is not sync |
| No `fleet.db` cache | Controller persists `fleet.json` (+ optional `last-status.json`). No users / dimensions / daily usage / audit-cursor cache |
| Controller is a local tool | No installer, no systemd, no `/etc/vincula`, **no `release.lock` chain**. Integrity is the zip you unpacked |
| Windows workstation | Needs **Python 3.10+** on PATH and **system OpenSSH Client** (`ssh.exe` / `scp.exe` / `ssh-keyscan.exe`). Neither is bundled |
| Clock skew thresholds | Frozen: WARN `>30s`, FAIL `>300s` check `audit-clock-health`. Not tunable in 0.2.8 |
| Three fixtures ≠ three VPS | AC-2.8-01 CI evidence is lax / tokyo / sg mock nodes, not three public VPS |
| No public management port | Workstation → node is SSH only. Controller does not listen |
| `state.json` schema 2 irreversible | No automatic schema 2→1. Rollback is restore of the `backup_existing_install` backup + the 0.2.7 installer |
| Accounting schema stays 3 | No DDL in 0.2.8. Historical `connections.instance_id` NULL rows stay NULL |
| Node helper has no `fleet` | `vcl fleet` is not a node subcommand; use `vcl-fleet` on the workstation |
| Routine `scp accounting.db` | Forbidden. Remote read is `ssh … vcl identity\|status\|verify --json` |
| `replace-node` / backup | 0.3.0. 0.2.8 only reserves “same `node_id`, new `instance_id`” semantics |

## Evidence gaps

| Gap | Notes |
| --- | --- |
| Windows 11 live `vcl-fleet.cmd` | **Not run.** Zip layout and stdlib/OpenSSH contract are unit-tested. Live OpenSSH Client + `py -3` on Win11 is operator evidence |
| Live SSH against real VPS | **Not run.** CI uses `tests/fixtures/fake-ssh`. Operator should verify `vcl-fleet node add` / `status` / `verify` against at least one real node before production use |
| Live 0.2.7 → 0.2.8 upgrade | Allowlist + mint + schema 1→2 unit tests PASS. No live RC-host upgrade run for 0.2.8 |
| Live 24h soak | **Not a 0.2.8 gate** (D20 binds 0.2.7 only). Inherited 0.2.7 soak gap remains for accounting durability |
| Reboot / full OS matrix | Inherits 0.2.4–0.2.7 gaps |
| Reliable Accounting | Explicitly out of scope |

## Resolved in 0.2.8

| Issue | Notes |
| --- | --- |
| `instance_id` untracked | Fresh install and 0.2.7→0.2.8 mint a UUID into `state.json`; new accounting INSERT rows stamp it; never copied from `node_id` |
| No fleet registry | `vcl-fleet` user-local `fleet.json`; add / list / show / set host / enable / disable |
| No remote health split | `vcl-fleet status` classifies SSH vs proxy vs accounting (STALE vs FAIL) |
| Host-key globally disabled | Controller never ships `StrictHostKeyChecking=no` or `UserKnownHostsFile=/dev/null` |
| Single Linux tarball name | Dual artifact: `vincula-node-*.tar.gz` and `vincula-controller-*.zip` |

## Related docs

- [`release-readiness-0.2.8.md`](release-readiness-0.2.8.md)
- [`fleet.md`](../fleet.md)
- [`identity.md`](../identity.md)
- [`accounting-reliability.md`](../accounting-reliability.md)
- [`known-issues-0.2.7.md`](known-issues-0.2.7.md)
