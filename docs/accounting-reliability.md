# Accounting reliability (V0.2.4)

Vincula does **not** ship a patched sing-box binary. Accounting is built on:

1. Stock sing-box **1.13.18** Clash API (`experimental.clash_api` bound to `127.0.0.1` only)
2. Per-user `acct/<tag>` direct outbounds + `auth_user` route rules
3. Optional file-based closed-connection ingest via `/var/lib/vincula/events.jsonl`

## Status: Approximate — Reliable Accounting is NOT done

| Claim | V0.2.4 reality |
| --- | --- |
| Exact per-flow billing | **No** — Clash API polling can miss short-lived connections |
| Lifecycle-complete closed events from stock sing-box | **No** — not available as a stable stream in 1.13.18 |
| Operational User × Destination visibility | **Yes** — approximate |
| `events.jsonl` preferred ingest | **Yes** — when present; still requires out-of-tree producer for full coverage |

Do not treat poll-derived numbers as byte-perfect metering. Product retention defaults remain **raw 90 days** / **daily 90 days** (UTC day boundaries for rollups).

## Clash API polling vs lifecycle events

| Approach | What it sees | Gaps |
| --- | --- | --- |
| Clash API `/connections` poll | Live connections and byte counters; outbound tag `acct/<tag>` maps to `user_id` | Connections that start and finish between polls can be missed entirely |
| Official lifecycle / “connection closed” events in 1.13.18 | Not exposed as a stable, complete closed-connection stream suitable for billing | Polling remains approximate |
| Future minimal telemetry → `events.jsonl` | One `connection_closed` record per finished flow | Requires a small out-of-tree patch or companion; not in this repo |

**Poll baseline (V0.2.4):** first sight of a connection stores Clash counters as baseline with zero accounted delta; a counter decrease starts a new generation; only positive deltas accumulate. This avoids double-counting absolute counters across polls.

## Prefer `events.jsonl` when present

`vincula-accountd` watches `/var/lib/vincula/events.jsonl` (JSON Lines). Each line should match the Vincula event schema (see `lib/vincula-event.schema.json`), especially:

```json
{"event":"connection_closed","connection_id":"...","node_id":"<uuid>","user":"alice","destination_host":"example.com","destination_ip":"203.0.113.10","destination_port":443,"network":"tcp","upload_bytes":123,"download_bytes":456,"started_at":"...","closed_at":"..."}
```

When the events file exists, accountd **prefers** these records for closed connections and does not emit duplicate poll-close rows for the same poll cycle strategy.

## Future minimal telemetry patch (protocol-neutral)

A future patch to sing-box (or a thin sidecar with privileged visibility) should:

1. Observe connection close with final upload/download counters and authenticated user tag
2. **Append** one JSON object per line to `/var/lib/vincula/events.jsonl` (mode `0600`, directory owned by root)
3. **Not** change VLESS/REALITY protocol behavior, listen addresses, or public ports
4. Leave Clash API optional for live `vcl connections` diagnostics

No protocol MITM, no new public management ports, and no change to client-visible traffic.

## Operator notes

- Clash API must remain on `127.0.0.1` (never `0.0.0.0`)
- `destination_host` is normalized (lowercase, strip trailing dot); Vincula does not invent hostnames via reverse DNS
- Accounting rows key on `user_id` (from `users.json`); `user_tag` is display
- Retention: `accounting_raw_retention_days`, `accounting_daily_retention_days` in `/etc/vincula/config.toml`
- Daily rollup uses the UTC date of `closed_at` (else `started_at`)
