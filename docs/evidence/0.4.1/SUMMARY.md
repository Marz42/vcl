# 0.4.1 Portable Workspace — DoD SUMMARY

**Milestone:** v0.4.1  
**Stamp:** CTRL `0.4.1` / NODE `0.3.1`  
**Date:** 2026-08-21  
**Gate:** offline (`bash tests/test.sh` + `bash tests/test-fleet.sh`)

| AC / DoD | Result | Evidence |
| --- | --- | --- |
| **M01** ids/endpoints consistent after migrate | **PASS** | offline T42 (`tests/test-fleet.sh` AC-4.0-M01) |
| **M02** migrate does not touch remote | **PASS** | offline T42 (`VCL_FLEET_SSH=/bin/false`) |
| **M03** fail-inject preserves legacy | **PASS** | offline T42 (fail-after migrate registry) |
| **M04** verify / sync / status / audit / stats / ui | **PASS** | offline T42 (status=cache) |
| **M05** dual WSL cross-machine | **SKIP / REQUIRES-LIVE** | runbook [`../0.4.1-m05/`](../0.4.1-m05/); SUMMARY `NOT RUN` |
| **M06** dry-run history gaps / no SSH | **PASS** | offline T42 |
| **S01** CHANGELOG status breaking + probe / `--live` | **PASS** | offline T42 + `CHANGELOG.md` |
| **S02** CAS + three-state conflict | **PASS** | offline T42 (ROLLBACK / DIVERGED / INCONSISTENT / CAS_REJECTED) |
| **4.1-02** bare `status` zero SSH | **PASS** | offline T42 / B7 D58 |
| **fleet_id + independent fleet.db** | **PASS** | offline T43 (M05 structural; same `fleet_id`, distinct DBs) |
| **D45** namespaced schema errors | **PASS** | 0.4.0 greps still green (`unsupported fleet-cache/registry schema:`; no bare `fleet.json schema_version`) |

## Version decoupling

- Controller only: `lib/vincula-fleet.py` `VCL_FLEET_VERSION = "0.4.1"` → artifact `vincula-controller-0.4.1.zip`.
- Node stays `vincula.sh` `VINCULA_VERSION="0.3.1"` (fixtures / upgrade allowlist untouched).

## Out of scope (→0.4.2+)

- `sync --full` body; `local-state/<fleet_id>/`; UI Sync→`--full`; adopt/provision; UI v2 / D53.
