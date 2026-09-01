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
Live evidence: Live Matrix **L2** in [`LIVE.md`](LIVE.md) — **PASS LIVE** (2026-08-31).

## Artifact pins

Deterministic build (`SOURCE_DATE_EPOCH` from git HEAD). Re-pin after the release commit if tree/epoch changes.

| Artifact | Version | SHA256 |
| --- | --- | --- |
| `vincula-controller-0.5.0.zip` | Controller 0.5.0 | `143b394024bca188ec801c398026f81b46be155eecececbc4d60de539eefccd4` |
| `vincula-node-0.5.0.tar.gz` | Node 0.5.0 | `52557a013df57a888a0c84fd48c56ea7a82a08118c73ee07321c628bbc717204` |

Minimum compatible Node for Controller 0.5.0: **0.3.1**.
