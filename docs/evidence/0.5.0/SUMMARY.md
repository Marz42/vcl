# 0.5.0 Observation Foundation — DoD SUMMARY

**Stamp:** CTRL `0.5.0` / NODE payload `0.5.0` · Minimum Node `0.3.1`
**Gate (offline):** `bash tests/test.sh` + `bash scripts/build-release.sh` + `bash scripts/build-controller.sh` — code commit `82dc577`: 1863 tests PASS, both builds PASS (2026-09-25)
**Spec:** [`../../specs/V0.5.0_Spec.md`](../../specs/V0.5.0_Spec.md) · Master [`../../specs/VCL_0.5-0.7_Master_SPEC.md`](../../specs/VCL_0.5-0.7_Master_SPEC.md)

| AC | Result | Evidence |
| --- | --- | --- |
| **AC-5.0-01** | **PASS (offline)** | Schema fixtures + contract tests: [`TESTS.md`](TESTS.md) |
| **AC-5.0-02** | **PASS (offline)** | Node `capabilities` / `telemetry snapshot`; fake-ssh `obsnode` alias |
| **AC-5.0-03** | **PASS (fixture)** | Mixed fleet: lax 0.3.x → UNSUPPORTED; probe/sync still OK — [`COMPATIBILITY.md`](COMPATIBILITY.md) |
| **AC-5.0-04** | **PASS (fixture)** | obsnode 0.5.0 capabilities/telemetry negotiation OK |
| **AC-5.0-05** | **PASS LIVE** | observe/admin route; AUTH_FAILED on revoked observe key — [`LIVE.md`](LIVE.md) L3/L4; probe/verify observe route regression PASS offline at `6428960` |
| **AC-5.0-06** | **PASS (offline)** | malformed / oversize / nested schema / padded raw oversize fail-closed; telemetry node/instance identity mismatch rejected |
| **AC-5.0-07** | **PASS (offline)** | Secret scan on capabilities/telemetry/journal stdout |
| **AC-5.0-08** | **PASS (offline)** | Telemetry audit: no mutation of config/users/systemd restart count |
| **AC-5.0-09** | **PASS (offline)** | Listener audit: no new management port; Clash/UI loopback — [`SECURITY.md`](SECURITY.md) |
| **AC-5.0-10** | **PARTIAL** | L3–L5 **PASS LIVE**; L2 historical PASS, **re-verify PENDING** (rollback path hardened); soak 1000× historical OK, RSS/FD **PENDING**; L1 **PENDING LIVE** — [`LIVE.md`](LIVE.md) / [`SOAK.md`](SOAK.md) |
| **AC-5.0-11** | **PASS (blocker)** | accountd de-root deferred; documented deviation — [`SECURITY.md`](SECURITY.md) |
| **AC-5.0-12** | **PASS (offline)** | CHANGELOG / README / technical-guide / evidence synced |
| **AC-5.0-13** | **PASS LIVE** (historical); **re-verify PENDING** | 2026-08-31 apply OK; re-run after rollback stop/helper hardening — [`LIVE.md`](LIVE.md) L2 |
| **AC-5.0-14** | **PASS (offline)** | Typed upgrade plan/apply; journal `node_upgrade` without secrets |

## Live Matrix

| ID | Scenario | Status |
| --- | --- | --- |
| **L1** | Fresh Node 0.5.0 telemetry | **PENDING LIVE** (offline: obsnode fixture OK) |
| **L2** | Upgrade 0.3.x → 0.5.0 identity preserved | **PASS LIVE** (2026-08-31); **re-verify PENDING** after rollback hardening |
| **L3** | Observer credential reads observation | **PASS LIVE** (2026-08-31) |
| **L4** | Broken observer → AUTH_FAILED | **PASS LIVE** (2026-08-31) |
| **L5** | Controller offline; proxy continues | **PASS LIVE** (2026-09-01) |

Detail: [`LIVE.md`](LIVE.md). Do not paste secrets into evidence.

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.5.0"`.
- Node: `VINCULA_VERSION = "0.5.0"`.
- Minimum Node: `0.3.1`.

## Artifact SHAs (current candidate build)

From code commit `82dc577`, set `SOURCE_DATE_EPOCH=1790260874` (the fixed candidate epoch from `6428960`), then run `build-release.sh` + `build-controller.sh`. The same source and epoch produced the same SHA on Kali Linux and WSL Windows mounted filesystems. These are candidate pins until G4/G5 live gates pass; refresh them if packaged source changes.

| Artifact | SHA256 |
| --- | --- |
| `dist/vincula-node-0.5.0.tar.gz` | `23ebd558f39204fc21e7fdef92c58d1b8403b8953c8fc343b233bcd88f97330a` |
| `dist/vincula-controller-0.5.0.zip` | `a155c92f497d8c2a7a89a80d1f72a7b09819a6880f3532507721b0ab3e0aa078` |

The explicit epoch keeps these candidate digests reproducible after evidence-only commits. CI merge-ref epochs may differ; compare a release asset against the digest for the exact source tree and epoch used to build it.


## Related

- Tests: [`TESTS.md`](TESTS.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Compatibility: [`COMPATIBILITY.md`](COMPATIBILITY.md)
- Soak digest: [`SOAK.md`](SOAK.md)
