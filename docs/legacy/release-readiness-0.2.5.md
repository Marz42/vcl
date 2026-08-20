# Vincula 0.2.5 Release Readiness

**Tree version:** 0.2.5  
**Date:** 2026-08-15  
**Release recommendation:** **READY WITH DOCUMENTED LIMITATIONS** (User Provisioning API freeze candidate)

Companion: [`known-issues-0.2.5.md`](known-issues-0.2.5.md) · Spec: [`specs/V0.2.5-V0.2.6_dev_spec.md`](../specs/V0.2.5-V0.2.6_dev_spec.md) Part I.

## Scope delivered

| Area | Status |
| --- | --- |
| Identity contract (`user_id` / `tag` / credentials) | PASS (unit) |
| Unified mutation transaction | PASS (existing pipeline + set/import) |
| `vcl user add\|set\|disable\|enable\|rotate\|list\|show\|link` | PASS (CLI + offline tests) |
| `vcl user import` / dry-run / credential CSV | PASS (offline) |
| `vcl user export` / `--credentials` | PASS (offline) |
| `vcl user verify` | PASS (offline + 100-user) |
| `user remove` refused | PASS |
| Tag regex with `.` | PASS |
| Migration allowlist includes `0.2.4` | PASS (unit) |
| Package build `scripts/build-release.sh` → `dist/` | PASS |
| Automated tests | **236** PASS |

## DoD (spec §21) — lab status

| Item | Result |
| --- | --- |
| single-user CRUD lifecycle | PASS (code + offline) |
| bulk import / dry-run / transactional rollback on validate fail | PASS (offline) |
| credential CSV 0600 semantics | PASS (code path) |
| disable/enable/rotate | PASS |
| 100-user invariant + verify | PASS (offline in `tests/test.sh`) |
| accounting identity continuity | PASS by design (no user_id rebuild on migrate) |
| migration 0.2.4→0.2.5 | **PASS** — live Debian 13 upgrade chain 2026-08-15 |
| reboot / uninstall-reinstall | **PASS** on same host (see 0.2.4–0.2.6 live evidence) |

## Explicit non-goals (still out)

Reliable Accounting, billing, Web UI, fleet, tag rename, credential expiry, purge/delete, stats analytics (→ 0.2.6).

## Policy after freeze

After tag `v0.2.5`, **User Provisioning CLI/schema is frozen**. Only P0/P1 regression fixes in 0.2.5.x; new analytics land in 0.2.6+.
