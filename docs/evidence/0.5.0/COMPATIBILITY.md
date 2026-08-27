# 0.5.0 — COMPATIBILITY evidence

> G0: planned matrix from SPEC §2.2. Mark **PASS** only after verified run (fixture or LIVE).

## Matrix

| Controller | Node | `capabilities/v1` | `telemetry/v1` | 0.4 management | Method | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5.0 | 0.5.0 | PASS | PASS | PASS | _TBD_ | **PENDING** |
| 0.5.0 | 0.3.2 | UNSUPPORTED | UNSUPPORTED | PASS | fixture | **PENDING** |
| 0.5.0 | 0.3.1 | UNSUPPORTED | UNSUPPORTED | PASS | fixture | **PENDING** |
| 0.4.5 | 0.5.0 | — | — | PARTIAL | _TBD_ | **PENDING** |

## UNSUPPORTED semantics

When Node lacks `vcl capabilities`:

- Controller observation commands MUST NOT report node **ERROR** solely for missing capability.
- Display **`UNSUPPORTED`** with explanation.
- Existing `probe` / `sync` / user management MUST continue to work for 0.3.x nodes.

## Upgrade path

| From | To | Identity | URI | Accounting | Outage budget |
| --- | --- | --- | --- | --- | --- |
| 0.3.1 | 0.5.0 | preserve | preserve | preserve | ≤3s (Live L2) |
| 0.3.2 | 0.5.0 | preserve | preserve | preserve | ≤3s (Live L2) |

Controller entry: `vcl-fleet node upgrade plan|apply NODE`.

Live evidence: Live Matrix **L2** in [`LIVE.md`](LIVE.md).

## Artifact pins (planned)

| Artifact | Version |
| --- | --- |
| `vincula-controller-0.5.0.zip` | Controller 0.5.0 |
| `vincula-node-0.5.0.tar.gz` | Node 0.5.0 payload |

Minimum compatible Node for Controller 0.5.0: **0.3.1**.
