# Accounting reliability (V0.2.7-dev)

Vincula does **not** ship a patched sing-box binary. Accounting is built on:

1. Stock sing-box **1.13.18** Clash API (`experimental.clash_api` bound to `127.0.0.1` only)
2. Per-user `acct/<tag>` direct outbounds + `auth_user` route rules

Clash API poll is the **only** production collector in 0.2.7. There is no file-backed ingest path.

## Status: Approximate — Reliable Accounting is NOT done

| Claim | V0.2.7-dev reality |
| --- | --- |
| Exact per-flow billing | **No** — Clash API polling can miss short-lived connections |
| Lifecycle-complete closed events from stock sing-box | **No** — not available as a stable stream in 1.13.18 |
| Operational User × Destination visibility | **Yes** — approximate |
| File-backed JSONL ingest | **No** — deleted (A2). A leftover `/var/lib/vincula/events.jsonl` is dirty install state (preflight / uninstall / rollback), not a collector |

Do not treat poll-derived numbers as byte-perfect metering. Product retention defaults remain **raw 90 days** / **daily 90 days** (UTC day boundaries for rollups).

## Clash API polling

| Approach | What it sees | Gaps |
| --- | --- | --- |
| Clash API `/connections` poll | Live connections and byte counters; outbound tag `acct/<tag>` maps to `user_id` | Connections that start and finish between polls can be missed entirely |
| Official lifecycle / “connection closed” events in 1.13.18 | Not exposed as a stable, complete closed-connection stream suitable for billing | Polling remains approximate |

**Poll baseline:** first sight of a connection stores Clash counters as baseline with zero accounted delta; a counter decrease starts a new generation; only positive deltas accumulate. This avoids double-counting absolute counters across polls. After accountd restart, a still-live Clash id keeps already-accounted SQLite bytes and re-baselines on the current counters (downtime increment is abandoned).

## Operator notes

- Clash API must remain on `127.0.0.1` (never `0.0.0.0`)
- `destination_host` is normalized (lowercase, strip trailing dot); Vincula does not invent hostnames via reverse DNS
- Accounting rows key on `user_id` (from `users.json`); `user_tag` is display
- Retention: `accounting_raw_retention_days`, `accounting_daily_retention_days` in `/etc/vincula/config.toml`
- Daily rollup uses the UTC date of `closed_at` (else `started_at`)
- `vcl accounting status` reports Clash poll only; it does not claim a preferred JSONL ingest
