# 0.5.0 — COMPATIBILITY evidence

## Matrix

| Controller | Node | `capabilities/v1` | `telemetry/v1` | 0.4 management | Method | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5.0 | 0.5.0 | PASS | PASS | PASS | fixture (`obsnode`) | **PASS (fixture)** |
| 0.5.0 | 0.3.2 | UNSUPPORTED | UNSUPPORTED | PASS | fixture (`lax`) | **PASS (fixture)** |
| 0.5.0 | 0.3.1 | UNSUPPORTED | UNSUPPORTED | PASS | fixture (`lax`) | **PASS (fixture)** |
| 0.4.5 | 0.5.0 | — | — | PARTIAL | not tested | **PENDING** |

Mixed fleet block `mix050` in `tests/test-fleet.sh`:

- `lax` (0.3.x identity): `capabilities` → UNSUPPORTED; `probe` → not ERROR
- `obsnode` (0.5.0): `capabilities` → OK

## UNSUPPORTED semantics

When Node lacks `vcl capabilities`:

- Controller observation commands MUST NOT report node **ERROR** solely for missing capability.
- Display **`UNSUPPORTED`** with explanation.
- Existing `probe` / `sync` / user management MUST continue to work for 0.3.x nodes.

Verified in `obs050` + `mix050` blocks.

## Upgrade path

| From | To | Identity | URI | Accounting | Outage budget |
| --- | --- | --- | --- | --- | --- |
| 0.3.1 | 0.5.0 | preserve | preserve | preserve | ≤3s (Live L2) |
| 0.3.2 | 0.5.0 | preserve | preserve | preserve | ≤3s (Live L2) |

Controller entry: `vcl-fleet node upgrade plan|apply NODE`.

Offline evidence: `obs050` upgrade apply happy path + migrate fail inject in test-fleet.
Live evidence: Live Matrix **L2** in [`LIVE.md`](LIVE.md) — historical **PASS LIVE** (2026-08-31); re-verification after rollback hardening remains **PENDING**.

## Artifact pins

Candidate build from `98423ed` with fixed `SOURCE_DATE_EPOCH=1790260874`; Node payload SHA is unchanged by the Controller clock fix. Re-pin if packaged source changes.

| Artifact | Version | SHA256 |
| --- | --- | --- |
| `vincula-controller-0.5.0.zip` | Controller 0.5.0 | `0adc8179a6260ddecd024b2f4ee219871f17ca7443415f6c344a392f65b641cd` |
| `vincula-node-0.5.0.tar.gz` | Node 0.5.0 | `23ebd558f39204fc21e7fdef92c58d1b8403b8953c8fc343b233bcd88f97330a` |

Minimum compatible Node for Controller 0.5.0: **0.3.1**.
