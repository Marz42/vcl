# Vincula 0.2.9 Release Readiness

**Tree version:** 0.2.9  
**Date:** 2026-08-16  
**Focus:** Fleet Users & Audit (`--user-id`, PARTIAL multi-node provision, `audit export --after` / `CURSOR_EXPIRED`, `vcl-fleet sync` / `fleet.db`, fleet audit/stats with node tags, `node retire`, `fleet.json` schema 2)  
**Companion:** [`known-issues-0.2.9.md`](known-issues-0.2.9.md) · Operator: [`fleet.md`](../fleet.md) · Spec: [`specs/V0.2.7-V0.3.1_spec.md`](../specs/V0.2.7-V0.3.1_spec.md) §6 / §9 / §10 / §11 / D9 / D15 / D16.

## Release recommendation

**READY WITH DOCUMENTED LIMITATIONS**

Offline / **fake-ssh multi-node fixture** evidence for AC-2.9-01…12 is green. Known P0/P1 at this docs gate: **0**. Dual artifacts remain reproducible. Node `release.lock` has 8 first-party files; the controller zip has **no** lock chain and still four members (`README-controller.md`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd`, `lib/vincula-fleet.py`). `fleet.db` logic lives inside `vincula-fleet.py` (no extra zip file).

Per spec §11, documented product limits are acceptable when they are intentional and do not break this milestone’s contract. D20’s 24h soak binds **0.2.7 only** — 0.2.9 must not be held to `READY FOR RC` on soak.

This tree is **not** `READY FOR RC` and **not** `NOT READY FOR RC`:

| Missing live evidence | Why it is a limitation, not a P0 |
| --- | --- |
| Windows 11 `vcl-fleet.cmd` on a real workstation | First-class packaging is tested (zip members, `.cmd` launcher). Live OpenSSH Client + Python 3.10+ + user/sync is operator verification |
| Live SSH against real VPS (multi-node provision / sync / retire) | AC-2.9-01 CI bar is **lax + tokyo fixtures**, not two public VPS. Operator should still run `user add` / `sync` / `node retire` on real nodes before production |

Fixture suite all-green → `READY WITH DOCUMENTED LIMITATIONS`. Raise to `READY FOR RC` only after a Win11 live `vcl-fleet.cmd` run **and** at least one live multi-node SSH operator verification (`user add` + `sync`). Do not treat mock SSH as live evidence.

## Scope delivered

| Item | Status |
| --- | --- |
| Product version `0.2.9` (no `-dev`) | PASS — constants + tests |
| Upgrade allowlist includes `0.2.8`, excludes `0.2.9` / `0.2.9-dev` | PASS (unit) |
| `state.json` schema stays **2**; no remint of `instance_id` | PASS (unit) |
| `users.json` schema stays **2**; `--user-id` is CLI, not a schema bump | PASS (unit) |
| Accounting schema stays **3**; export is read-only | PASS (unit) |
| Node `vcl user * --json` + `--user-id` (0.2.1–0.2.4) | PASS (unit) |
| `vcl audit export --after --jsonl` + `CURSOR_EXPIRED` exit 3 | PASS (unit) |
| `vcl-fleet user *` + PARTIAL exit 2 + credential CSV 0600 | PASS (fake-ssh lax/tokyo) |
| `vcl-fleet sync` idempotent + durable cursor + `--reseed` | PASS (fake-ssh + new process) |
| `vcl-fleet audit` / `stats` keep node attribution | PASS (fake-ssh) |
| `fleet.json` schema 2 + `node retire` (sync before retired) | PASS (fake-ssh) |
| `fleet.db` schema 1 | PASS (unit) |
| No management API port | PASS (static grep) |
| Windows 11 live `vcl-fleet.cmd` | **MISSING** (limitation) |
| Live SSH against real VPS | **MISSING** (limitation; not the CI bar) |

## Acceptance criteria (AC-2.9-01…12)

Evidence strategy = **fake-ssh multi-node fixtures** (`tests/fixtures/fake-ssh`, aliases lax=`203.0.113.10`, tokyo=`203.0.113.11`). Unit tests must **not** be marked as live VPS. Soak / live VPS items are not marked PASS from fixtures.

| ID | Criterion | Status | Code evidence | Test evidence | Remaining risk | Release blocking |
| --- | --- | --- | --- | --- | --- | --- |
| AC-2.9-01 | Same logical user on two nodes: one `user_id`, different per-node credential UUIDs | **PASS** (fixture) | `lib/vincula-fleet.py` `cmd_user_add`: one global UUID, SSH `vcl user add TAG --user-id` per node | `tests/test-fleet.sh`: `AC-2.9-01 user add alice --nodes lax,tokyo exits 0`; `AC-2.9-01 same user_id two nodes different credential UUID`. Not two VPS | Live SSH / NAT / real sing-box restart untested | YES (fixture) |
| AC-2.9-02 | Rotate credential on one node does not change the other node | **PASS** (fixture) | `cmd_user_rotate` requires `--node`; SSH only that host | `AC-2.9-02 rotate one node does not change the other node's credential` | Live rotate + client reconnect untested | YES (fixture) |
| AC-2.9-03 | Disable on one node is not fleet-wide disable; `--node` required | **PASS** (fixture) | disable without `--node` dies `refusing fleet-wide disable; pass --node` | `AC-2.9-03 disable one node does not disable the user on other nodes`; missing `--node` non-zero | Live disable + last-enabled invariant on a real node untested | YES (fixture) |
| AC-2.9-04 | Fleet audit merges by stable `user_id`; each row tagged with node | **PASS** (fixture) | `cmd_audit` queries `audit_events` with node name from registry; empty `node_id` excluded | `AC-2.9-04 audit user alice human output includes lax and tokyo`; `AC-2.9-04 audit merges Alice across lax+tokyo by user_id`; unlabeled `node_id` not counted | Tag→`user_id` conflict across live nodes would fail closed (exit 1) | YES (fixture) |
| AC-2.9-05 | Fleet stats keep node attribution | **PASS** (fixture) | `stats` reads `daily_usage` only; detail `(user_id, node)`; `--json` totals still `by_node` | `AC-2.9-05 stats user alice preserves node attribution`; `stats top users keeps (user_id, node) rows`; `stats top hosts keeps per-node host rows` | Not byte-identical with node `vcl stats` (documented) | YES (fixture) |
| AC-2.9-06 | Any node FAILED → PARTIAL, per-node status, `--user-id` remediation; never report full success; no rollback promise | **PASS** (fixture) | `plan_state` / `remediation_user_add`; `cmd_user_add` returns 2 if `state != SUCCESS` | `AC-2.9-06` with `VCL_FAKE_FAIL_USER_ADD=tokyo`: exit 2, `PARTIAL`, tokyo `FAILED`, remediation `--user-id`, overall not `SUCCESS`; bob exists on lax only | Live SSH timeout / mid-restart failure modes beyond fake inject | YES (fixture) |
| AC-2.9-07 | Credential CSV is node-specific URI; file mode 0600 | **PASS** (fixture) | header `user,node,credential_id,vless_uri`; `os.chmod` 0600; stderr credential WARNING | `AC-2.9-07 credential CSV header`; `AC-2.9-07 credential CSV is node-specific (lax/tokyo hosts)`; import/export `mode 0600` | Operator mishandling of 0600 files after copy | YES (fixture) |
| AC-2.9-08 | Retire runs final sync **before** marking `retired` (original AC-2.8-08 sync semantics) | **PASS** (fixture) | `cmd_node_retire`: identity + `sync_one_node`; `CURSOR_EXPIRED` / sync fail → die, registry stays active; then snapshot; then `status=retired` | Failed export path: retire refused, still active. Success: `AC-2.9-08 final sync committed cursor=8 before status=retired; last enabled user kept` | Unreachable production node cannot be retired (intentional). `VCL_FLEET_RETIRE_SKIP_SYNC` is test-only | YES (fixture) |
| AC-2.9-09 | After retire, historical audit remains queryable; controller restart keeps cursor (original AC-2.8-09) | **PASS** (fixture) | retire does not DELETE `fleet.db` rows; cursor on disk; audit/stats not filtered by retired | `AC-2.9-09 historical audit still queryable after retire`; new-process sync COUNT unchanged; `sync` no longer touches retired lax | Live operator deleting `fleet.db` by hand | YES (fixture) |
| AC-2.9-10 | No public Vincula management port | **PASS** (static) | Controller has no `socket.bind` / `HTTPServer` / listen; SSH only. New user/sync code is in the same `vincula-fleet.py` already grepped | `tests/test-fleet.sh`: `AC-2.8-02 / AC-2.9-10 controller has no bind`; `AC-2.8-02 / AC-2.9-10 controller has no listen/http.server`; D14 greps on `lib/vincula-fleet.py`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd` | None for this AC (static) | YES |
| AC-2.9-11 | Node `--user-id`; ordinary add still generates UUID; controller injects one global id | **PASS** (unit + fixture) | `users_registry_mutate add` 6th arg; `cmd_user_add --user-id`; fleet generates or reuses `--user-id` | `tests/test.sh`: generated carol UUID; dave explicit `user_id`; duplicate eve rejected; invalid `not-a-uuid` rejected. Fleet AC-2.9-01 shared UUID | Malformed operator `--user-id` is fail-closed | YES |
| AC-2.9-12 | `audit export --after` + idempotent sync; expired cursor → `CURSOR_EXPIRED` + earliest + `--reseed` | **PASS** (unit + fixture) | `vincula-audit.py` `export_after`; fleet `cmd_sync` / `--reseed`; no hole import | `tests/test.sh` `--after 0` / contiguous / `CURSOR_EXPIRED` empty stdout. `tests/test-fleet.sh`: COUNT=5 then new process still 5; gap → `CURSOR_EXPIRED` COUNT stays 5; `--reseed lax` remaining window | Live retention vs cursor timing; reseed discards local cache (documented, not 0.3.0 backup) | YES (fixture) |

## Migration path (0.2.8 → 0.2.9)

| Step | Detail |
| --- | --- |
| Supported sources | `0.1.0`–`0.1.5` and `0.2.0`–`0.2.8` → **0.2.9** |
| Same version | Verify both planes; do not rotate credentials; do not remint `instance_id` |
| `state.json` | schema **stays 2**. Preserve `node_id` and `instance_id` |
| Accounting schema | **Stays 3.** No DDL. `vcl audit export` is read-only |
| `users.json` | schema **stays 2**. Existing `user_id` kept. `--user-id` is CLI only |
| `config.toml` | Still mirrors `node_id` only; **no** `instance_id` |
| Identity | Reality keys, user UUIDs, `user_id`, `node_id`, `instance_id` kept. D18 does **not** re-migrate daily=730 from 0.2.8 |
| `fleet.json` | schema **1 → 2** on next save. Missing `status`: `enabled=true` → `active`, else `disabled` |
| `fleet.db` | **New** on the workstation (`$FLEET_HOME/fleet.db` schema 1). Created on first `sync` / open |
| Allowlist | Includes `0.2.8`. Does **not** include `0.2.9` or `0.2.9-dev` |
| Node lock | Still 8 first-party files; fleet not included |
| Controller zip | Still four members; no installer, no `release.lock` |

## Rollback

There is **no** automatic `fleet.json` schema 2→1 downgrade. Node-side schemas were not bumped (state 2, users 2, accounting 3), so there is no node DDL to reverse for this milestone.

**Nodes:** restore the `backup_existing_install` backup taken before migrate (core + accounting artifacts + SQLite `.backup` + `SERVICE_STATE`) **and** the matching **0.2.8** installer. Restoring a 0.2.9 tree’s files onto 0.2.8 is the supported rollback path only via that backup, not via a schema downgrade.

**Workstation:** the controller has no lock chain and no installer. Replace the unpacked zip with the 0.2.8 zip. Schema-2 `fleet.json` and `fleet.db` are **not** understood by 0.2.8 — restore a pre-upgrade copy of `$FLEET_HOME`, or delete `fleet.db` and keep `fleet.json` only if you accept losing the local audit cache (0.2.8 has no `fleet.db`). Leaving schema-2 `fleet.json` in place for a 0.2.8 binary is unsupported. That does not roll back nodes.

## Decisions frozen in this release

| Decision | Value |
| --- | --- |
| Fleet-global identity | Inject the same `user_id` at provision time (D16); never merge on `display_name` |
| PARTIAL | Any FAILED (including all failed) → exit 2; no rollback guarantee |
| Accounting schema | **3** (unchanged); export is read-only `event_id > after` |
| `CURSOR_EXPIRED` | `after>0` and `MIN(event_id) > after+1` (or empty DB with `after>0`). `after=0` is never expired |
| `--reseed` | Remaining window only; **not** 0.3.0 snapshot |
| Fleet stats | Derived from synced connections, UTC day of `started_at`, tagged with `node_id` |
| Retire | Final sync → snapshot dir → best-effort disable (keep last enabled) → `retired`; no uninstall; no history erase |
| `fleet.json` | schema **2** (`status`) |
| `fleet.db` | schema **1** |
| Controller stack | Python 3.10+ stdlib + system OpenSSH; no paramiko; no root; no listen port |
| Host-key | Default `known_hosts`; never `StrictHostKeyChecking=no` / `UserKnownHostsFile=/dev/null` |
| Clock | WARN 30s / FAIL 300s / `audit-clock-health` |
| Node lock | 8 first-party files; **fleet files not included** |
| Controller lock | **None** — user-local zip, no installer integrity chain |
| AC-2.9-01 CI bar | lax + tokyo **fixtures**, not 2 VPS |
| Soak | D20 does **not** apply to 0.2.9 |

## Explicit non-goals (0.2.9)

backup/restore, age, Python SQLite Backup API, `vcl snapshot export`, `replace-node`, UI, routine `scp accounting.db`, billing-grade accounting, node `vcl fleet` subcommand, silent `display_name` merge, distributed rollback **guarantee**, blocking 90-day retention for cursors, retire auto-uninstall / erase `fleet.db`.

## Policy after freeze

After tag `v0.2.9`, prefer P0/P1 fixes only. Backup/restore and `replace-node` belong in 0.3.0+. A Win11 live controller run plus live multi-node SSH operator verification (`user add` + `sync`) is required before raising this recommendation to `READY FOR RC`.

## Completion report (SPEC §19)

Filled at freeze `0.2.9` (Batch 12-freeze). Historical 0.2.8/0.2.7 docs and `docs/specs/` were not rewritten.

### 1. Changed files

**Milestone (0.2.8 → 0.2.9):** `vincula.sh`, `bin/vincula`, `lib/vincula-common.sh`, `lib/vincula-audit.py`, `lib/vincula-fleet.py`, `lib/vincula-accountd.service`, `tests/test.sh`, `tests/test-fleet.sh`, `tests/fixtures/fake-ssh`, identity fixtures (`identity-sample.json`, `nodes/{lax,tokyo,copied}/identity.json`, `lax/identity-reinstall.json`), `README.md`, `README-controller.md`, `CHANGELOG.md`, `docs/fleet.md`, `docs/identity.md`, `docs/known-issues-0.2.9.md`, `docs/release-readiness-0.2.9.md`, `release.lock`, `vincula.sh.sha256`.

**Freeze-only (drop `-dev` + lock regen):** the product stamps above plus `vincula-bootstrap.sh` comment URLs (`0.2.8` → `0.2.9` tarball examples), `docs/accounting-reliability.md` title (collector unchanged through 0.2.9), and regenerated `release.lock` / `vincula.sh.sha256`. Fleet files remain **out** of the node lock.

Node first-party lock members stay **8**: `vincula.sh`, `vincula-bootstrap.sh`, `bin/vincula`, `lib/vincula-common.sh`, `lib/vincula-accountd.py`, `lib/vincula-stats.py`, `lib/vincula-audit.py`, `lib/vincula-accountd.service`. No `vincula-fleet.py`.

### 2. Schema changes

| Format | 0.2.8 | 0.2.9 | Notes |
| --- | --- | --- | --- |
| Product `VINCULA_VERSION` / `VCL_FLEET_VERSION` | `0.2.8` | **`0.2.9`** | Freeze dropped `-dev` only |
| `state.json.schema_version` | 2 | **2** | No remint of `instance_id` |
| `users.json.schema_version` | 2 | **2** | `--user-id` is CLI, not a schema bump |
| accounting `meta.schema_version` | 3 | **3** | No DDL; export is read-only |
| `fleet.json.schema_version` | 1 | **2** | Adds `status` (`active` \| `disabled` \| `retired`) |
| `fleet.db` `meta.schema_version` | — | **1** | New workstation cache |

### 3. CLI changes

**Node:** `vcl user add --user-id UUID --json`; `vcl user list|show|rotate|enable|disable --json` (contracts 0.2.1–0.2.4); human `list` adds `USER_ID`; `vcl audit export --after EVENT_ID --jsonl` (meta on stderr; `CURSOR_EXPIRED` exit 3).

**Controller:** `vcl-fleet user add|list|show|enable|disable|rotate|import|export`; `vcl-fleet sync [--node NAME] [--reseed NAME]`; `vcl-fleet audit user`; `vcl-fleet stats …`; `vcl-fleet node retire NAME`. PARTIAL → exit **2**. No node `vcl fleet` subcommand.

### 4. Migration path

Supported sources: `0.1.0`–`0.1.5` and `0.2.0`–`0.2.8` → **0.2.9**. Allowlist includes `0.2.8`, excludes `0.2.9` / `0.2.9-dev`. Same-version re-run verifies both planes and does not rotate credentials or remint `instance_id`. D18 does **not** re-migrate daily=730 from 0.2.8. Workstation: `fleet.json` 1→2 on next save; `fleet.db` created on first open/sync.

### 5. Rollback path

No automatic `fleet.json` 2→1. Node schemas were not bumped. Nodes: restore `backup_existing_install` **and** the matching **0.2.8** installer. Workstation: replace the zip with the 0.2.8 controller; restore pre-upgrade `$FLEET_HOME` or drop `fleet.db` (0.2.8 has none). Schema-2 `fleet.json` is unsupported on a 0.2.8 binary.

### 6. Security impact

No new listen port (`socket.bind` / `HTTPServer` absent — AC-2.9-10). Credential CSV mode **0600** + stderr WARNING. D14 unchanged: no `StrictHostKeyChecking=no`, no `UserKnownHostsFile=/dev/null`, no paramiko, OpenSSH argv lists only. Controller remains non-root, no systemd, no `/etc/vincula`. Node `release.lock` still 8 files; controller zip still has **no** lock.

### 7. Tests executed

Freeze verification: `bash -n` on all first-party bash (installer, helper, common, scripts, `tests/test.sh`, `tests/test-fleet.sh`); `python3 -m py_compile` on `lib/*.py`, `bin/vcl-fleet`, `tests/fixtures/fake-ssh`; `bash tests/test.sh` (sources fleet); `bash tests/test-fleet.sh` (standalone); `bash scripts/gen-release-lock.sh`.

| Suite | Count | Result |
| --- | --- | --- |
| `bash tests/test.sh` (sources `tests/test-fleet.sh`) | **837** | green |
| `bash tests/test-fleet.sh` (standalone) | **334** | green |

P0/P1 at freeze: **0**. No live Win11 / live VPS / live 0.2.8→0.2.9 upgrade run.

### 8. Failure-injection results

| Inject | Result |
| --- | --- |
| `VCL_FAKE_FAIL_USER_ADD=tokyo` (`user add bob`) | exit 2, `state=PARTIAL`, tokyo `FAILED`, remediation `--user-id`; overall not `SUCCESS`; no rollback of lax |
| Export fail during `node retire` | retire refused; registry stays `active` |
| Cursor gap (`after` behind MIN) | node `CURSOR_EXPIRED` exit 3, stdout empty, no hole import; COUNT unchanged |
| `--reseed NAME` after expire | remaining window imported; cursor advanced |
| Sync interrupted / re-run (new Python process) | `COUNT(*)` and cursor unchanged (idempotent) |
| jsonl row missing `node_id` | dropped + WARN; not inserted |
| Disable without `--node` | non-zero; `refusing fleet-wide disable` |

### 9. Acceptance criteria matrix

AC-2.9-01…12: all **PASS** on fake-ssh fixtures / static grep as tabulated above. None marked PASS from live VPS or soak. Original English SPEC AC-2.8-08/09 (incremental sync / durable cursor) are **implemented** here as AC-2.9-08/09/12.

### 10. Known limitations

See [`known-issues-0.2.9.md`](known-issues-0.2.9.md). Headline: no Win11 live `vcl-fleet.cmd`; no live multi-node VPS; fleet stats not byte-identical with node `vcl stats`; retire cannot disable the last enabled user; `--reseed` is not a 0.3.0 snapshot; D20 soak is not a 0.2.9 gate; PARTIAL has no distributed rollback guarantee.

### 11. Version / schema bump explanation

Product bump `0.2.8` → `0.2.9-dev` happened at the start of the milestone (Batch 8-version). Freeze only removes `-dev`. Accounting / users / state schemas are **not** tied to the product stamp (§9.5). `fleet.json` 1→2 and new `fleet.db` schema 1 are the only persistence bumps.

### 12. Release recommendation

**READY WITH DOCUMENTED LIMITATIONS**

CI fake-ssh all-green, P0/P1=0, no Win11 live `vcl-fleet.cmd` and no live SSH user add/sync. Raise to `READY FOR RC` only after those two live checks. Not `NOT READY FOR RC`: documented limits do not break the 0.2.9 contract.

### Extra (plan §7)

13. **Confirmed:** incremental sync + `fleet.db` cursor (original AC-2.8-08/09 semantics) landed as AC-2.9-08/09/12.
14. **PARTIAL negative:** tokyo FAIL → exit 2, not full success (AC-2.9-06).
15. **CURSOR_EXPIRED + `--reseed`:** node exit 3 + empty stdout; fleet does not import holes; reseed pulls remaining window (AC-2.9-12).
16. **Dual artifacts:** node `release.lock` still **8** files (fleet not included); controller zip still four members and **no** lock; `fleet.db` logic lives in `vincula-fleet.py`.
