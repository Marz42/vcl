# 0.5.0 Observation Foundation — DoD SUMMARY

**Stamp:** CTRL `0.5.0` / NODE payload `0.5.0` · Minimum Node `0.3.1`  
**Gate (offline):** `bash tests/test.sh` + `bash scripts/build-release.sh` + `bash scripts/build-controller.sh`  
**Spec:** [`../../specs/V0.5.0_Spec.md`](../../specs/V0.5.0_Spec.md) · Master [`../../specs/VCL_0.5-0.7_Master_SPEC.md`](../../specs/VCL_0.5-0.7_Master_SPEC.md)

> **G0：** 本文件为模板。编码与 Live 完成前 AC 均为 **PENDING**。

| AC | Result | Evidence |
| --- | --- | --- |
| **AC-5.0-01** | **PENDING** | schema + fixtures: [`../../../schemas/`](../../../schemas/) |
| **AC-5.0-02** | **PENDING** | Node `capabilities` / `telemetry snapshot` |
| **AC-5.0-03** | **PENDING** | Controller + Node 0.3.1/0.3.2 → UNSUPPORTED |
| **AC-5.0-04** | **PENDING** | Controller + Node 0.5.0 negotiation |
| **AC-5.0-05** | **PENDING** | observe/admin route + AUTH_FAILED |
| **AC-5.0-06** | **PENDING** | malformed / oversize fixtures |
| **AC-5.0-07** | **PENDING** | secret redaction tests |
| **AC-5.0-08** | **PENDING** | telemetry read-only regression |
| **AC-5.0-09** | **PENDING** | listener audit |
| **AC-5.0-10** | **PENDING LIVE** | Live L1–L5 + 1000× soak |
| **AC-5.0-11** | **PENDING** | accountd de-root or SECURITY blocker |
| **AC-5.0-12** | **PENDING** | docs / CHANGELOG / matrix |
| **AC-5.0-13** | **PENDING LIVE** | `node upgrade` 0.3.x → 0.5.0；断流 ≤3s |
| **AC-5.0-14** | **PENDING** | typed upgrade；journal 无 secret |

## Live Matrix

| ID | Scenario | Status |
| --- | --- | --- |
| **L1** | Fresh Node 0.5.0 telemetry | **PENDING LIVE** |
| **L2** | Upgrade 0.3.x → 0.5.0 identity preserved | **PENDING LIVE** |
| **L3** | Observer credential reads observation | **PENDING LIVE** |
| **L4** | Broken observer → AUTH_FAILED | **PENDING LIVE** |
| **L5** | Controller offline; proxy continues | **PENDING LIVE** |

Detail: [`LIVE.md`](LIVE.md). Do not paste secrets into evidence.

## Stamp (planned)

- Controller: `VCL_FLEET_VERSION = "0.5.0"`.
- Node: `VINCULA_VERSION = "0.5.0"`.
- Minimum Node: `0.3.1`.

## Related

- Tests: [`TESTS.md`](TESTS.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Compatibility: [`COMPATIBILITY.md`](COMPATIBILITY.md)
