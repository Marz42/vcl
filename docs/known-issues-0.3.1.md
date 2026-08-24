# Vincula 0.3.1 — Known issues / limitations

**Tree:** `0.3.1` (stable).  
**Release recommendation:** **READY** — Known P0: **0**. Known P1 release blockers: **0**.

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices. Fleet stats are derived from synced connection `started_at` UTC days and are **not** byte-identical with node `vcl stats`.

Companion: [`release-readiness-0.3.1.md`](release-readiness-0.3.1.md) · Evidence: [`evidence/0.3.1-final/SUMMARY.md`](evidence/0.3.1-final/SUMMARY.md) · Legacy freeze records: [`legacy/`](legacy/).

---

## Classification

### P0

**None.**

### P1 release blockers

**None.**

| Former ID | Resolution |
| --- | --- |
| P1-05 branch protection | **CLOSED (B26)** — `main` requires PR + CI checks; force-push/delete disabled |
| P1-06 live `0.3.0 → 0.3.1` upgrade | **WAIVED** — operator accepted **B22** live `0.3.1-rc1 → 0.3.1-rc2` as surrogate; fixtures cover `0.3.0` allowlist + keep tests. True schema **3→4** on a live `0.3.0` host was not run |

### P2

**None open** that block this release.

### Documented limitations (product)

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect; not for invoices |
| Short-lived connections | May be missed between polls |
| Fleet stats vs node `vcl stats` | Fleet `daily_usage` rebuilt from synced `audit_events` (UTC day of `started_at`); not byte-identical |
| Controller dependencies | Needs **Python 3.10+** and **system OpenSSH** on the workstation; neither bundled |
| UI localhost-only | `vcl-fleet ui` binds loopback only; no identity mutations; **reseed is CLI-only** |
| `--reseed` semantics | Wipes that node’s local `audit_events` + `daily_usage` in `fleet.db`; resets `cursor_kind=export_seq`; does **not** erase `instance_history` or node `accounting.db` |
| Secretless restore / reissue | Replace rotates credentials; old URI must fail on new IP; new URI from reissue CSV |
| `age` | Secretless backups never call age; `--include-secrets` requires distro `age` on PATH |
| PARTIAL mutations | Exit 2 + per-node status; no distributed rollback guarantee |
| D20 soak | Binds **0.2.7 only**; not a 0.3.1 gate |

### Deferred ops (non-blocking)

| Item | Notes |
| --- | --- |
| **B24** replace regression smoke on rc2/0.3.1 packaging | **Deferred** — [`evidence/0.3.1-rc2/B24-replace-deferred.md`](evidence/0.3.1-rc2/B24-replace-deferred.md). Full **B14** live replace already **PASS**. Resume when a spare runtime-only VPS is available |

---

## Live evidence closed this line

| Gate | Status |
| --- | --- |
| B14 live replace (+ AC-3.0-11, age, Win11) | **PASS** — [`evidence/0.3.1-live/`](evidence/0.3.1-live/) |
| B15 Local Audit UI | **Implemented** (AC-3.1 fixtures) |
| B18 accounting-db/v4 installer health | **PASS** |
| B19–B20 freeze + CI + artifacts | **PASS** |
| B21 fresh install | **PASS** — [`evidence/0.3.1-rc2/B21-fresh-install.md`](evidence/0.3.1-rc2/B21-fresh-install.md) |
| B22 upgrade (rc1→rc2 surrogate) | **PASS** — [`evidence/0.3.1-rc2/B22-upgrade-rc1.md`](evidence/0.3.1-rc2/B22-upgrade-rc1.md) |
| B23 accounting-db/v4 Fleet re-sync | **PASS** — [`evidence/0.3.1-rc2/B23-fleet-resync.md`](evidence/0.3.1-rc2/B23-fleet-resync.md) |
| B24 replace smoke | **Deferred** (see above) |
| B25 docs consistency | **PASS** (this freeze) |
| B26 branch protection | **PASS** |
| B27 final artifact black-box | See [`evidence/0.3.1-final/SUMMARY.md`](evidence/0.3.1-final/SUMMARY.md) (**PASS**; CI digests) |
| B28 tag `v0.3.1` | **PASS** (immutable tag + GitHub Release) |

## Related

- [`release-readiness-0.3.1.md`](release-readiness-0.3.1.md)
- [`fleet.md`](fleet.md) · [`backup.md`](backup.md) · [`manual.md`](manual.md) · [`identity.md`](identity.md)
- [`legacy/`](legacy/) (read-only historical gates)
