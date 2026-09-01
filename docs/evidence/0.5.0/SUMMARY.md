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
| **AC-5.0-05** | **PASS LIVE** | observe/admin route; AUTH_FAILED on revoked observe key — [`LIVE.md`](LIVE.md) L3/L4 |
| **AC-5.0-06** | **PASS (offline)** | malformed JSON, oversize capabilities/telemetry → ERROR fail-closed |
| **AC-5.0-07** | **PASS (offline)** | Secret scan on capabilities/telemetry/journal stdout |
| **AC-5.0-08** | **PASS (offline)** | Telemetry audit: no mutation of config/users/systemd restart count |
| **AC-5.0-09** | **PASS (offline)** | Listener audit: no new management port; Clash/UI loopback — [`SECURITY.md`](SECURITY.md) |
| **AC-5.0-10** | **PASS LIVE** (L1 skipped) | L2–L5 **PASS LIVE**; soak **PASS (offline)**; L1 needs fresh VPS — [`LIVE.md`](LIVE.md) |
| **AC-5.0-11** | **PASS (blocker)** | accountd de-root deferred; documented deviation — [`SECURITY.md`](SECURITY.md) |
| **AC-5.0-12** | **PASS (offline)** | CHANGELOG / README / technical-guide / evidence synced |
| **AC-5.0-13** | **PASS LIVE** | `node upgrade apply` 0.3.1→0.5.0; outage ~0s; identity preserved — [`LIVE.md`](LIVE.md) |
| **AC-5.0-14** | **PASS (offline)** | Typed upgrade plan/apply; journal `node_upgrade` without secrets |

## Live Matrix

| ID | Scenario | Status |
| --- | --- | --- |
| **L1** | Fresh Node 0.5.0 telemetry | **PENDING LIVE** (offline: obsnode fixture OK) |
| **L2** | Upgrade 0.3.x → 0.5.0 identity preserved | **PASS LIVE** (2026-08-31; outage ~0s; hotfixes applied on node) |
| **L3** | Observer credential reads observation | **PASS LIVE** (2026-08-31) |
| **L4** | Broken observer → AUTH_FAILED | **PASS LIVE** (2026-08-31) |
| **L5** | Controller offline; proxy continues | **PASS LIVE** (2026-09-01) |

Detail: [`LIVE.md`](LIVE.md). Do not paste secrets into evidence.

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.5.0"`.
- Node: `VINCULA_VERSION = "0.5.0"`.
- Minimum Node: `0.3.1`.

## Artifact SHAs (release build)

- `dist/vincula-node-0.5.0.tar.gz` — `59171c161cf96651f368ce8507f2424c68886f88191785625966f8d687c772d9`
- `dist/vincula-controller-0.5.0.zip` — `2abf035ad8572b52de9bfc5b87d4d3f7f36c5d3ad02e948924ef718aa14aa3ca`

## Related

- Tests: [`TESTS.md`](TESTS.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Compatibility: [`COMPATIBILITY.md`](COMPATIBILITY.md)
