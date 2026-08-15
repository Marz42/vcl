# Vincula 0.2.6 — Known issues / limitations

**Policy:** Accounting remains **approximate / Clash polling**. Short-lived connections may be missed between polls. Do not use for invoices.

## Product limitations

| Topic | Notes |
| --- | --- |
| Approximate accounting | Clash API polling; not byte-perfect |
| Department attribution | **Current** `users.json` department only — no historical department timeline |
| Host normalization | Lowercase + strip trailing `.` only; no full IDNA |
| IP-only destinations | Shown as `[IP only] <ip>`; no reverse DNS |
| Cross-midnight | Daily rollups use UTC date of `closed_at` (unchanged from 0.2.4) |
| Live connections | `vcl connections` requires active `vincula-accountd`; SQLite is not shown as live |
| Retention | Defaults raw 90 / daily 730; `vcl accounting retention` is read-only |

## Evidence gaps

| Gap | Notes |
| --- | --- |
| Live 0.2.5→0.2.6 migration on RC host | **PASS**（Debian 13；含 reboot + forced rollback；见 `docs/evidence/0.2.4-0.2.6-live/`） |
| Reboot / full OS matrix | Inherits 0.2.4/0.2.5 gaps |
| Reliable Accounting | Explicitly out of scope for 0.2.6 |

## Related docs

- [`release-readiness-0.2.6.md`](release-readiness-0.2.6.md)
- [`accounting-reliability.md`](accounting-reliability.md)
- [`known-issues-0.2.5.md`](known-issues-0.2.5.md)
