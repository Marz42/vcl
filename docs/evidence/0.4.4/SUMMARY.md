# 0.4.4 Local Audit UI v2 (D53) — DoD SUMMARY

**Stamp:** CTRL `0.4.4` / NODE `0.3.1` · **Gate:** offline `bash tests/test.sh` + `bash tests/test-fleet.sh`  
**Spec:** [`../../specs/V0.4.4_ui_v2.md`](../../specs/V0.4.4_ui_v2.md)

| AC | Result | Evidence |
| --- | --- | --- |
| **4.4-01** | **PASS** | `api_sync` → `run_sync_full_payload`; `operation=sync_full`; concurrent sync lock |
| **4.4-02** | **PASS** | PARTIAL / non-zero → `ok=false` + toast `PARTIAL/FAIL`; no SUCCESS paint |
| **4.4-03** | **PASS** | `/api/recipes` adopt/provision/register/workspace/archive/user-link; `node-add` legacy |
| **4.4-04** | **PASS** | Empty Overview/Health copy → adopt/provision; static grep in `test-fleet.sh` |
| **4.4-05** | **PASS** | Overview/Health `workspace` strip: `fleet_id` + conflict codes |
| **4.4-06** | **PASS** | recipes/meta JSON grep: no `vless://`, `private_key`, `clash_secret` |
| **4.4-07** | **PASS** | AC-3.1 UI fixture block green (inherits B15 regression) |

## Notes

- Controller-only; Node `0.3.1` unchanged.
- D57 observe≠admin and `node add` deprecation warnings remain **0.5+**.
- LIVE optional (no new LIVE AC required for UI v2).

## Test counts

Offline gate: **`bash tests/test.sh` 1736 PASS** (0 not ok).

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.4.4"`.
- Node: `VINCULA_VERSION="0.3.1"` unchanged.
