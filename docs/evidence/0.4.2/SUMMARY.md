# 0.4.2 Local Cache & Archive — DoD SUMMARY
**Stamp:** CTRL `0.4.2` / NODE `0.3.1` · **Gate:** offline `bash tests/test.sh` + `bash tests/test-fleet.sh`
| AC | Result | Evidence |
| --- | --- | --- |
| **4.1-01** | **PASS** | B4/B8 offline zero SSH |
| **4.1-03** | **PASS** offline / **SKIP LIVE** | B5 fake-ssh; LIVE optional |
| **4.1-04** | **PASS** | B5 PARTIAL exit 2 |
| **4.1-05** | **PASS** | B7 restore cursor unchanged |
| **4.1-06** | **PASS** offline half / **SKIP LIVE** | B7 Workspace+archive+fresh db |
| **4.2-C01** | **PASS** | B4 true mode=ro |
| **4.2-C02** | **PASS** | B3 fleet-cache/v4 |
| **4.2-C03** | **PASS** | B1/B3 local-state + MISMATCH |
| **4.2-C04** | **PASS** | B5 --full additive / sync legacy |
| D58 status/--live/probe | **PASS** | regression unchanged |

## P1 fix batches (F1–F6 + P1 regression)

Offline `tests/test-fleet.sh` + `tests/test.sh` after P1-1..6 regression suite (`590083e`): **826** / **1594** PASS (0 not ok).

| Item | Result | Key asserts |
| --- | --- | --- |
| **P1-1** | **PASS** | `workspace_mutation` single entry; registry/trust/history/migrate/import bump rev/write_id/parent; external fork CAS detected |
| **P1-2** | **PASS** | cache rollback journal (`DELETE`); RO `mode=ro` + `query_only` (no immutable) |
| **P1-3** | **PASS** | cached status ← `node_snapshot`; probe live-only (SSH yes; no `last-status.json`); legacy last-status fallback |
| **P1-4** | **PASS** | archive canonical excludes `imported_at`; restore rebuilds `daily_usage`; `ARCHIVE_FLEET_MISMATCH` |
| **P1-5** | **PASS** | local tag→user_id; audit/stats/status/UI Local Read Plane (zero default SSH); conflict/unknown fail-closed |
| **P1-6** | **PASS** | machine-local → CONFIG/STATE; workspace root purely copyable (`workspace.json`/`fleet.json`/`trust/`/`history/`) |
| **P1-1..6r** | **PASS** | dedicated regression blocks lock each fix |

## F7 hardening (F7-1..F7-6 + T1–T5)

Offline gate after F7-1..F7-5 (`08173dc`) + F7-6 evidence: **`bash tests/test.sh` 1652 PASS** · **`bash tests/test-fleet.sh` 884 PASS** (0 not ok; baselines held).

| Item | Result | Key asserts |
| --- | --- | --- |
| **F7-1 / T2** | **PASS** | `sync --full` defers portable history past DB commit; audit-import inject → exit 2, DB rollback, `history/instances.jsonl` + digest unchanged; success flushes after commit |
| **F7-2 / T3** | **PASS** | import verify-in-staging then commit; corrupt/digest-mismatch FAIL; live SHA256 set unchanged; no auto re-sign |
| **F7-3 / T1** | **PASS** | Workspace active + `--identity-file` → machine-local binding; `fleet.json` refs only (no `identity_file`); verify/export PASS; registry save refuses identity_file |
| **F7-4 / T4** | **PASS** | cached status `ok` from health; SSH/PROXY/ACCOUNTING FAIL → `ok=false` exit≠0; healthy → `ok=true`; UNKNOWN/STALE contract unchanged |
| **F7-5 / T5** | **PASS** | stale digest → `workspace verify` FAIL + `workspace export` FAIL (no `.tgz`) |
| **F7-6** | **PASS** | this SUMMARY + CHANGELOG hardening notes; stamp unchanged |

## Local double-isolation acceptance

| Run | Result | Summary |
| --- | --- | --- |
| **Workspace A→B** | **PASS** | A export → B import → verify (`revision=3`) → bind → `sync --full` SUCCESS → status (cache, snapshot healthy) / audit / stats OK |
| **Archive A→B restore** | **PASS** | A `.vclaudit` export → B fresh restore: imported events + aggregated usage (stats queryable); cursor unchanged |

True dual-WSL LIVE remains optional / operator-run (same posture as AC-4.1-03/06).

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.4.2"` (no bump for P1/F7 fix batches).
- Node: `VINCULA_VERSION="0.3.1"` unchanged.
