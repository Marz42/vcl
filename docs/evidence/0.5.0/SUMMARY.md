# 0.5.0 Observation Foundation — DoD SUMMARY

**Stamp:** CTRL `0.5.0` / NODE payload `0.5.0` · Minimum Node `0.3.1`  
**Gate (offline):** `bash tests/test.sh` + `bash scripts/build-release.sh` + `bash scripts/build-controller.sh`  
**Spec:** [`../../specs/V0.5.0_Spec.md`](../../specs/V0.5.0_Spec.md) · Master [`../../specs/VCL_0.5-0.7_Master_SPEC.md`](../../specs/VCL_0.5-0.7_Master_SPEC.md)

| AC | Result | Evidence |
| --- | --- | --- |
| **AC-5.0-01** | **PASS (offline)** | Schema fixtures + contract tests: [`TESTS.md`](TESTS.md) |
| **AC-5.0-02** | **PASS (offline)** | Node `capabilities` / `telemetry snapshot`; fake-ssh `obsnode` alias |
| **AC-5.0-03** | **PASS (fixture)** | Mixed fleet: lax 0.3.x → UNSUPPORTED; probe/sync still OK — [`COMPATIBILITY.md`](COMPATIBILITY.md) |
| **AC-5.0-04** | **PASS (fixture)** | obsnode 0.5.0 capabilities/telemetry negotiation OK |
| **AC-5.0-05** | **PASS (offline)** | observe/admin route; AUTH_FAILED on wrong observe key — `obs-auth` block in test-fleet |
| **AC-5.0-06** | **PASS (offline)** | malformed JSON, oversize capabilities/telemetry → ERROR fail-closed |
| **AC-5.0-07** | **PASS (offline)** | Secret scan on capabilities/telemetry/journal stdout |
| **AC-5.0-08** | **PASS (offline)** | Telemetry audit: no mutation of config/users/systemd restart count |
| **AC-5.0-09** | **PASS (offline)** | Listener audit: no new management port; Clash/UI loopback — [`SECURITY.md`](SECURITY.md) |
| **AC-5.0-10** | **PARTIAL** | Soak 1000× telemetry **PASS (offline)**; Live L1–L5 **PENDING LIVE** — [`LIVE.md`](LIVE.md) |
| **AC-5.0-11** | **PASS (blocker)** | accountd de-root deferred; documented deviation — [`SECURITY.md`](SECURITY.md) |
| **AC-5.0-12** | **PASS (offline)** | CHANGELOG / README / technical-guide / evidence synced |
| **AC-5.0-13** | **PASS (offline) / PENDING LIVE** | `node upgrade apply` fixture E2E + migrate fail; outage ≤3s needs Live L2 |
| **AC-5.0-14** | **PASS (offline)** | Typed upgrade plan/apply; journal `node_upgrade` without secrets |

## Live Matrix

| ID | Scenario | Status |
| --- | --- | --- |
| **L1** | Fresh Node 0.5.0 telemetry | **PENDING LIVE** (offline: obsnode fixture OK) |
| **L2** | Upgrade 0.3.x → 0.5.0 identity preserved | **PENDING LIVE** (offline: upgrade apply fixture OK) |
| **L3** | Observer credential reads observation | **PENDING LIVE** (offline: observe binding + admin mutation path) |
| **L4** | Broken observer → AUTH_FAILED | **PASS (offline equiv)** — obs-auth fixture; Live confirm on VPS |
| **L5** | Controller offline; proxy continues | **PENDING LIVE** |

Detail: [`LIVE.md`](LIVE.md). Do not paste secrets into evidence.

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.5.0"`.
- Node: `VINCULA_VERSION = "0.5.0"`.
- Minimum Node: `0.3.1`.

## Artifact SHAs (release build)

- `dist/vincula-node-0.5.0.tar.gz` — `365ab648c87aee2d6b56a049e9364d5838f1dcbf1c8e96f3cb9a072329b7e25c`
- `dist/vincula-controller-0.5.0.zip` — `e4256146257a8c7479f5d1f094ef4bcdbe69aee785ea7be25f51e2bce5dcc9bf`

## Related

- Tests: [`TESTS.md`](TESTS.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Compatibility: [`COMPATIBILITY.md`](COMPATIBILITY.md)
