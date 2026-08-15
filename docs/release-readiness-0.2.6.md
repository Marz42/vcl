# Vincula 0.2.6 Release Readiness

**Tree version:** 0.2.6  
**Focus:** Accounting UX (query / export / health visibility)  
**Companion:** [`known-issues-0.2.6.md`](known-issues-0.2.6.md) · Spec: [`specs/V0.2.5-V0.2.6_dev_spec.md`](specs/V0.2.5-V0.2.6_dev_spec.md) Part II.

## Scope

| Item | Status |
| --- | --- |
| Single query model `lib/vincula-stats.py` | PASS (unit) |
| CLI: today/yesterday/days/month/user/department/host/top | PASS (unit + helper docs) |
| JSON/CSV export (raw integer bytes) | PASS (unit) |
| Current department attribution | PASS (unit) |
| IP-only hosts labeled, not dropped | PASS (unit) |
| Metadata: mode / collector / freshness / coverage | PASS (unit) |
| `vcl connections` UNAVAILABLE when accountd inactive | PASS (code) |
| Retention read-only CLI | PASS (code) |
| Migration allowlist includes `0.2.5` | PASS (unit) |
| No schema_version bump | PASS (query-only) |

## Gates

| Gate | Result |
| --- | --- |
| Offline unit suite (`tests/test.sh`) | **247 PASS** (WSL) |
| Packaging (`gen-release-lock` + `build-release`) | Includes `vincula-stats.py` |
| Live 0.2.5→0.2.6 migration | **PASS** (Debian 13 live chain + rollback) |
| Approximate accounting declaration | Required in all report surfaces |

## Release recommendation

**READY WITH DOCUMENTED LIMITATIONS** — stats/analytics UX for approximate polling data; not Reliable/Billing-grade accounting.

After tag `v0.2.6`, prefer P0/P1 fixes for stats correctness; larger accounting reliability work remains future scope.
