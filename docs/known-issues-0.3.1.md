# Vincula 0.3.1-dev — Known issues / limitations

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices. Fleet stats are derived from synced connection `started_at` UTC days and are **not** byte-identical with node `vcl stats`.

**Release recommendation:** **NOT READY** — living-tree gate for `0.3.1-dev`. B17 closed restore/sync fail-close; **B14 live two-VPS replace is PASS** ([`evidence/0.3.1-live/SUMMARY.md`](evidence/0.3.1-live/SUMMARY.md)). Remaining blockers: **B15** UI and live **`0.3.0 → 0.3.1-dev` upgrade**. This page is **not** an addendum to the 0.3.0 freeze record. Historical freeze text: [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md) · [`known-issues-0.3.0.md`](known-issues-0.3.0.md).

Known P0: **0**. Remaining blockers are evidence gaps (B15 / live upgrade), not B14 or B17 contracts.

## Product limitations

Inherited from 0.3.0 unless noted.

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect |
| Fleet stats vs node `vcl stats` | Fleet `daily_usage` is rebuilt from synced `audit_events` using UTC day of `started_at` |
| Win11 live controller | **PASS (B14 2026-08-18):** `vcl-fleet.cmd version/status/verify` on Win11 + system OpenSSH |
| Live VPS replace | **PASS (B14):** two public VPS secretless replace; see evidence SUMMARY |
| AC-3.0-11 | **PASS (B14):** old URI→new IP failed; new URI succeeded |
| `age` is a system package | Secretless backups never call age. `--include-secrets` requires `age` on PATH |
| `--from-backup` may drop the sync tail | Escape hatch when the old host is dead. Next sync with a kept cursor past restored `MAX(event_id)` is `CURSOR_AHEAD`. Remedy is `--reseed` |
| Unlabeled audit rows | Normal sync **fails the batch** (cursor unchanged). Stamp missing identity only via `vcl-fleet sync --reseed NAME` / node `--stamp-identity`. Query still ignores historical unlabeled rows already in `fleet.db` |
| Node restore is fresh-node / runtime-only | Existing `$STATE_DIR/VERSION` → refuse. `--replace-node` is not a node flag |
| `fleet.db` schema 2 irreversible | No automatic 2→1 |
| `--reseed` still wipes the local audit cache | Deletes that node’s `audit_events` + `daily_usage`, cursor=0. Does not erase `instance_history` |
| D20 soak is not a 0.3.1 gate | 24h soak binds **0.2.7 only** |
| PARTIAL has no distributed rollback | Exit 2 + per-node status + `--user-id` remediation |
| Controller is a local tool | No installer, no systemd. Zip has `controller.lock` + sidecar `.zip.sha256` |
| Windows workstation | Needs **Python 3.10+** and **system OpenSSH Client**. Neither is bundled |
| UI | **0.3.1** Phase B (B15). Not started |

## Evidence gaps

| Gap | Notes |
| --- | --- |
| Windows 11 live `vcl-fleet.cmd` | **PASS (B14)** |
| Live SSH against real VPS | **PASS (B14)** (replace/status/verify) |
| Live secretless `node replace` | **PASS (B14).** Evidence [`evidence/0.3.1-live/`](evidence/0.3.1-live/) |
| Live `age` on a real node | **PASS (B14):** distro `age` 1.2.1 `--include-secrets` create+verify |
| AC-3.0-11 live handshake | **PASS (B14)** |
| Live `0.3.0 → 0.3.1-dev` upgrade | Allowlist + keep tests PASS in fixtures. No RC-host upgrade this round |
| Live 24h soak | **Not a 0.3.1 gate** |

## Closed on this living tree (B17)

| Issue | Notes |
| --- | --- |
| Restore JSON / systemd ignore-errors before VERSION | Shell is the only public JSON emitter. Both units must enable/active + health before `commit-version`. Unique `ok:false` on failure |
| Fleet mutate treated non-zero remote exit as SSH OK | Mutate path requires `returncode == 0` and JSON `ok is True` |
| Rollback swallowed systemctl failures | `rollback_partial` when files/services cannot be fully restored |
| Sync skipped unlabeled rows and still advanced cursor | Whole batch fails; cursor unchanged. `--reseed` stamps missing identity only |
| Upgrade allowlist stopped at 0.2.9 | `0.3.0` is allowed; `0.3.0-dev` / `0.3.1-dev` are not |
| Version-boundary rollback dropped `.runtime-only` | Safety copy + journal `had_runtime_only`; marker restored with VERSION rollback |
| CI used mutable action tags + unused `actions: write` | Full SHA pins; Dependabot; `actions: write` only on the artifact job |

Earlier closures (P0 replace argv, controller zip modules, mutex, CURSOR_AHEAD, streaming backup, bootstrap pin, GitHub Actions workflow) remain closed; see [`known-issues-0.3.0.md`](known-issues-0.3.0.md) “Resolved in 0.3.1-dev” for B0–B16.

## Deferred

| Item | Notes |
| --- | --- |
| B14 live two-VPS replace + AC-3.0-11 | **PASS (2026-08-18)** — [`evidence/0.3.1-live/SUMMARY.md`](evidence/0.3.1-live/SUMMARY.md) |
| B15 localhost UI | Phase B. Not started |

## Related docs

- [`release-readiness-0.3.1.md`](release-readiness-0.3.1.md)
- [`live-replace-checklist.md`](live-replace-checklist.md)
- [`backup.md`](backup.md)
- [`fleet.md`](fleet.md)
- [`identity.md`](identity.md)
- [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md) (freeze record; read-only)
- [`known-issues-0.3.0.md`](known-issues-0.3.0.md) (freeze record; read-only)
