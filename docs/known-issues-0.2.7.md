# Vincula 0.2.7 — Known issues / limitations

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices.

**Release recommendation:** **READY WITH DOCUMENTED LIMITATIONS** — no live 24h soak has been run, so AC-2.7-09 is missing and this tree must not be called `READY FOR RC`. See [`release-readiness-0.2.7.md`](release-readiness-0.2.7.md).

## Product limitations

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect |
| Schema 3 irreversible | `connections` PK is `event_id AUTOINCREMENT`. There is no automatic schema 3→2 downgrade. Rollback is restore of the `backup_existing_install` backup taken before migrate |
| `instance_id` | Every row is NULL in 0.2.7. Minting is 0.2.8 (D5). Do not copy `node_id` into this column |
| No JSONL ingest | Production collector is Clash poll only (A2). A leftover `/var/lib/vincula/events.jsonl` is dirty install state, not a collector |
| `vcl audit` formats | table (default) and `--json` only. No `--csv` in 0.2.7 |
| Single-node | No fleet, no SSH controller, no incremental audit cursor |
| Department attribution | **Current** `users.json` department only — no historical department timeline |
| Host normalization | Lowercase + strip trailing `.` only; no full IDNA |
| IP-only destinations | Shown as `[IP only] <ip>`; no reverse DNS |
| Cross-midnight | Daily rollups use UTC date of `closed_at` (unchanged) |
| Live connections | `vcl connections` requires active `vincula-accountd`; SQLite is not shown as live |
| Retention | Defaults raw 90 / daily 90; expired deletes are batched at 2000 rows/table/tick |

## Evidence gaps

| Gap | Notes |
| --- | --- |
| Live 24h soak (AC-2.7-09) | **Not run.** Protocol is `scripts/soak-0.2.7.sh` (LIVE-ONLY). Unit tests and accelerated clocks do not satisfy this gate |
| Reboot dual-plane restore (AC-2.7-08) | Covered only by the soak T+6h step. No live 0.2.7 reboot evidence yet |
| Live 0.2.6→0.2.7 migration | Allowlist + schema 2→3 unit tests PASS. No live RC-host upgrade run for 0.2.7 |
| Reboot / full OS matrix | Inherits 0.2.4/0.2.5/0.2.6 gaps |
| Reliable Accounting | Explicitly out of scope for 0.2.7 |

## Resolved in 0.2.7

| Issue | Notes |
| --- | --- |
| Accountd restart zeroed accounted bytes | First sight of a still-live Clash id now keeps SQLite totals and re-baselines on current counters (AC-2.7-01 / AC-2.7-02) |
| JSONL restart replay | File ingest path deleted (A2). Restart cannot replay a collector that no longer exists (AC-2.7-12) |

## Related docs

- [`release-readiness-0.2.7.md`](release-readiness-0.2.7.md)
- [`accounting-reliability.md`](accounting-reliability.md)
- [`known-issues-0.2.6.md`](known-issues-0.2.6.md)
