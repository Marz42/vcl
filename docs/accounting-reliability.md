# Accounting reliability (V0.2.7 / V0.2.8)

Vincula does **not** ship a patched sing-box binary. Accounting is built on:

1. Stock sing-box **1.13.18** Clash API (`experimental.clash_api` bound to `127.0.0.1` only)
2. Per-user `acct/<tag>` direct outbounds + `auth_user` route rules

Clash API poll is the **only** production collector in 0.2.7 and 0.2.8. There is no file-backed ingest path.

## Status: Approximate — Reliable Accounting is NOT done

| Claim | V0.2.7 reality |
| --- | --- |
| Exact per-flow billing | **No** — Clash API polling can miss short-lived connections |
| Lifecycle-complete closed events from stock sing-box | **No** — not available as a stable stream in 1.13.18 |
| Operational User × Destination visibility | **Yes** — approximate |
| File-backed JSONL ingest | **No** — deleted (A2). A leftover `/var/lib/vincula/events.jsonl` is dirty install state (preflight / uninstall / rollback), not a collector |

Do not treat poll-derived numbers as byte-perfect metering. Product retention defaults are **raw 90 days** / **daily 90 days** (UTC day boundaries for rollups).

## Schema 3

SQLite `accounting.db` uses `meta.schema_version = 3`.

| Object | Role |
| --- | --- |
| `connections.event_id` | `INTEGER PRIMARY KEY AUTOINCREMENT` (deleted ids are not reused) |
| `connections.generation` | Session generation for a Clash `connection_id`. Migrated rows start at **0** |
| `UNIQUE (connection_id, generation)` | One open row per generation; a counter reset inserts a new generation |
| `connections.instance_id` | 0.2.8: new INSERT writes `state.json` SoT (`node.instance_id`). Historical 0.2.7 NULL rows stay NULL. Never copied from `node_id`. The DB is not the SoT |
| `poll_baseline` | Durable Clash counters + accounted totals for the open generation |
| `daily_usage` | Unchanged UTC-day rollup keyed by `(date, user_id, destination_host)` |

Schema 2→3 rewrite keeps existing accounted bytes, assigns `event_id`, sets `generation=0`, leaves `instance_id` NULL, and does **not** invent `poll_baseline` counters. The migrate is **irreversible**; rollback is restore of the pre-upgrade backup.

## Clash API polling

| Approach | What it sees | Gaps |
| --- | --- | --- |
| Clash API `/connections` poll | Live connections and byte counters; outbound tag `acct/<tag>` maps to `user_id` | Connections that start and finish between polls can be missed entirely |
| Official lifecycle / “connection closed” events in 1.13.18 | Not exposed as a stable, complete closed-connection stream suitable for billing | Polling remains approximate |

**poll_baseline / generation**

- Unknown connection (no open row, no baseline): store current Clash counters as baseline; accounted delta is 0.
- Same generation, counters increased: add only the positive delta; write `connections` and `poll_baseline` together.
- `current < previous`: close the current generation (keep already-accounted bytes), open `generation + 1` with accounted 0, replace baseline. Never apply a negative delta; no huge-threshold heuristic.
- Connection leaves the live set: close that generation and delete its `poll_baseline` row.
- Closed `(connection_id, generation)` rows are never updated by first sight.

**Restart**

- Cache is reloaded from `poll_baseline` JOIN open `connections` after `open_db`.
- A still-live Clash id keeps SQLite accounted bytes and re-baselines on the **current** Clash counters (downtime increment is abandoned = under-count, never replayed).
- Memory `known_open` is a cache: SQLite COMMIT succeeds first, then the cache is replaced (D7). COMMIT failure rolls back and reloads from DB.

## Retention (90 / 90)

- Defaults: `accounting_raw_retention_days = 90`, `accounting_daily_retention_days = 90`.
- D18: upgrading from a supported source (`≤ 0.2.6`) rewrites daily **730 → 90** only. Custom daily values are kept. Raw is preserved.
- Expired closed `connections` and old `daily_usage` rows are deleted in batches of **2000** per table per maintenance tick. Open rows are never deleted. Retention does not consult a fleet cursor.

## Operator notes

- Clash API must remain on `127.0.0.1` (never `0.0.0.0`)
- `destination_host` is normalized (lowercase, strip trailing dot); Vincula does not invent hostnames via reverse DNS
- Accounting rows key on `user_id` (from `users.json`); `user_tag` is display
- Retention knobs live in `/etc/vincula/config.toml`
- Daily rollup uses the UTC date of `closed_at` (else `started_at`)
- `vcl accounting status` reports Clash poll only; it does not claim a preferred JSONL ingest
- `vcl accounting check` runs the same Accounting Plane checker as `vcl verify` (schema 3, heartbeat, baseline/counter sanity, retention backlog)
- `vcl audit` is connection-level RFC3339 interval-overlap over schema 3; `vcl stats` remains UTC day granularity
