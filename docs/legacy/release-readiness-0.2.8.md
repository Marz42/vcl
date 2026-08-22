# Vincula 0.2.8 Release Readiness

> **(0.2.x 历史文档，命令名 vcl 已迁移为 vcl-fleet)**

**Tree version:** 0.2.8  
**Date:** 2026-08-16  
**Focus:** Fleet Foundation (`instance_id` mint, `vcl-fleet` registry/SSH/status/verify, dual artifact, D14 host-key, clock skew)  
**Companion:** [`known-issues-0.2.8.md`](known-issues-0.2.8.md) · Spec: [`specs/V0.2.7-V0.3.1_spec.md`](../specs/V0.2.7-V0.3.1_spec.md) §5 / §10 / §11 / D10 / D13 / D14 / 修正 C.

## Release recommendation

**READY WITH DOCUMENTED LIMITATIONS**

Offline / fixture evidence for AC-2.8-01…13 is green. Known P0/P1 at freeze: **0**. Dual artifacts are reproducible. Node `release.lock` has 8 first-party files; the controller zip has **no** lock chain (user-local tool).

Per spec §11, documented product limits are acceptable when they are intentional and do not break this milestone’s contract. D20’s 24h soak binds **0.2.7 only** — 0.2.8 must not be held to `READY FOR RC` on soak.

This tree is **not** `READY FOR RC` and **not** `NOT READY FOR RC`:

| Missing live evidence | Why it is a limitation, not a P0 |
| --- | --- |
| Windows 11 `vcl-fleet.cmd` on a real workstation | First-class packaging is tested (zip members, `.cmd` launcher). Live OpenSSH Client + Python 3.10+ is operator verification |
| Live SSH against a real VPS | AC-2.8-01 CI bar is **3 mock fixtures**, not 3 public VPS. Operator should still run `node add` / `status` / `verify` on a real node before production |

Raise to `READY FOR RC` only after a Win11 live `vcl-fleet.cmd` run **and** at least one live SSH operator verification. Do not treat mock SSH as live evidence.

## Scope delivered

| Item | Status |
| --- | --- |
| Product version `0.2.8` (no `-dev`) | PASS — constants + tests |
| Upgrade allowlist includes `0.2.7`, excludes `0.2.8` | PASS (unit) |
| `state.json` schema 2 + `instance_id` mint (never copy `node_id`) | PASS (unit) |
| Accounting schema stays **3**; historical `instance_id` NULL; new INSERT from SoT | PASS (unit) |
| `vcl identity --json` / `status --json` / `verify --json` | PASS (unit + fake-ssh) |
| `vcl-fleet` registry CLI + user-local `fleet.json` | PASS (unit) |
| OpenSSH transport, injectable ssh, D14 host-key | PASS (negative + positive fixture tests) |
| `vcl-fleet status` / `verify` + clock 30 / 300 | PASS (lax / tokyo / sg + skew injection) |
| Dual artifact `vincula-node-*.tar.gz` + `vincula-controller-*.zip` | PASS (packaging tests) |
| No incremental sync / fleet user / `fleet.db` | PASS (CLI + docs; explicit non-goal) |
| Windows 11 live `vcl-fleet.cmd` | **MISSING** (limitation) |
| Live SSH against real VPS | **MISSING** (limitation; not the CI bar) |

## Acceptance criteria (AC-2.8-01…13)

Evidence is **fixture-based** unless noted. Soak / live VPS items are not marked PASS from unit tests. Original English SPEC AC-2.8-08/09 (incremental sync / cursor) were **overridden** by the revised spec; the original meanings are 0.2.9 and must not be marked PASS via mock.

| ID | Criterion | Status | Evidence | Release blocking |
| --- | --- | --- | --- | --- |
| AC-2.8-01 | ≥3 nodes registered and listed | **PASS** (fixture) | `tests/test-fleet.sh`: lax / tokyo / sg; `AC-2.8-01 list has exactly 3 fixture nodes`. Not 3 VPS | YES (fixture) |
| AC-2.8-02 | No public Vincula management port | **PASS** | Static grep: no `socket.bind` / `HTTPServer` / `0.0.0.0` / `http.server` in controller. SSH only | YES |
| AC-2.8-03 | Status distinguishes SSH failure vs remote failure | **PASS** | lax OK/OK/OK; tokyo OK/OK/STALE; sg FAIL/UNKNOWN/UNKNOWN. `AC-2.8-03` named tests | YES |
| AC-2.8-04 | Stable UUID `node_id` (not recast) | **PASS** | Mint tests in `tests/test.sh`; `AC-2.8-04 node_id is a stable UUID in registry` | YES |
| AC-2.8-05 | Upgrade mint `instance_id`; never copy `node_id`; reinstall may mint new | **PASS** | `mint_or_preserve_instance_id`; schema 1→2; `identity-reinstall.json` WARN, registry `node_id` unchanged | YES |
| AC-2.8-06 | Changing `ssh_host` does not change `node_id` | **PASS** | `vcl-fleet node set`; `AC-2.8-06 ssh_host change does not alter node_id` | YES |
| AC-2.8-07 | Duplicate `node_id` registration refused | **PASS** | Offline + live `node add` of an already-registered `node_id` | YES |
| AC-2.8-08 | **Overridden:** mock SSH covers registry/status/verify/host-key. **Not** incremental sync | **PASS** (mock) | `tests/fixtures/fake-ssh` + host-key / status / verify tests. `vcl audit export --after event_id` **not implemented** | YES (mock, not sync) |
| AC-2.8-09 | **Overridden:** controller restart does not lose **registry**. **Not** sync cursor | **PASS** | `AC-2.8-09 registry survives a new process`. No `fleet.db` cursor | YES |
| AC-2.8-10 | Host-key checking not globally disabled | **PASS** | No `StrictHostKeyChecking=no` / `UserKnownHostsFile=/dev/null` in shipped controller; non-TTY add requires `--host-key`; mismatch refuses; badkey FAIL | YES |
| AC-2.8-11 | Dual artifact; Windows 11 first-class zip | **PASS** (packaging) / Win11 live **MISSING** | `scripts/build-release.sh` + `scripts/build-controller.sh`. Zip has `vcl-fleet.cmd` + `vincula-fleet.py`; no `vincula.sh` / no `release.lock`. Win11 live is a documented limitation | Packaging YES; missing Win11 live does not flip to NOT READY |
| AC-2.8-12 | Clock skew >30s WARN, >5min FAIL `audit-clock-health`; thresholds visible | **PASS** | Constants 30 / 300; `clock_skew_result` 0=OK 31=WARN 301=FAIL; `VCL_FAKE_CLOCK_SKEW_SECONDS=45` WARN exit 0; `=400` FAIL + `audit-clock-health`; `--help` names the check | YES |
| AC-2.8-13 | No full fleet audit cache, no incremental audit sync, no fleet user provisioning | **PASS** | CLI subcommands are init / node / status / verify / version / help only. Docs: not in 0.2.8 | YES |

## Migration path (0.2.7 → 0.2.8)

| Step | Detail |
| --- | --- |
| Supported sources | `0.1.0`–`0.1.5` and `0.2.0`–`0.2.7` → **0.2.8** |
| Same version | Verify both planes; do not rotate credentials; do not remint `instance_id` |
| `state.json` | schema 1 → **2**. Preserve `node_id`. Mint `instance_id` if missing / invalid / equal to `node_id` |
| Accounting schema | **Stays 3.** No DDL. Historical `connections.instance_id` NULL remains NULL. New INSERT / new generation writes current SoT `instance_id` |
| `config.toml` | Still mirrors `node_id` only; **no** `instance_id` |
| `users.json` | schema still 2 |
| Identity | Reality keys, user UUIDs, `user_id`, existing UUID `node_id` kept |
| Allowlist | Includes `0.2.7`. Does **not** include `0.2.8` or `0.2.8-dev` |

## Rollback

There is **no** automatic `state.json` schema 2→1 downgrade. Accounting schema was not bumped, so there is no 3→4 / 3→2 problem from this milestone.

Rollback = restore the `backup_existing_install` backup taken before migrate (core + accounting artifacts + SQLite `.backup` + `SERVICE_STATE`) **and** the matching **0.2.7** installer. Restoring a schema-2 `state.json` onto a 0.2.7 tree that expects schema 1 is unsupported.

The workstation controller has no lock chain and no installer: delete / replace the unpacked zip directory and user-local `fleet.json` as needed. That does not roll back nodes.

## Decisions frozen in this release

| Decision | Value |
| --- | --- |
| `instance_id` SoT | `state.json` `node.instance_id` only |
| Accounting schema | **3** (unchanged) |
| Controller entry | `vcl-fleet` / `vcl-fleet.cmd`; node has no `fleet` subcommand |
| Controller stack | Python 3.10+ stdlib + system OpenSSH; no paramiko; no root |
| Host-key | Default `known_hosts`; never `StrictHostKeyChecking=no` / `UserKnownHostsFile=/dev/null` |
| Clock | WARN 30s / FAIL 300s / `audit-clock-health` |
| Node lock | 8 first-party files; **fleet files not included** |
| Controller lock | **None** — user-local zip, no installer integrity chain |
| AC-2.8-01 CI bar | 3 mock fixtures, not 3 VPS |
| Soak | D20 does **not** apply to 0.2.8 |

## Explicit non-goals (0.2.8)

incremental audit sync, `vcl audit export --after event_id`, `CURSOR_EXPIRED`, full `fleet.db`, `vcl-fleet user *`, fleet stats/audit, UI, `replace-node`, backup/restore, routine `scp accounting.db`, billing-grade accounting, node `vcl fleet` subcommand.

## Policy after freeze

After tag `v0.2.8`, prefer P0/P1 fixes only. Incremental sync and fleet user provisioning belong in 0.2.9+. A Win11 live controller run plus live SSH operator verification is required before raising this recommendation to `READY FOR RC`.
