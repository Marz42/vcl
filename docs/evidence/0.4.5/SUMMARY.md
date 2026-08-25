# 0.4.5 Integration & Hardening + Legacy Seed — DoD SUMMARY

**Stamp:** CTRL `0.4.5` / NODE payload `0.3.2` · Minimum Node `0.3.1`
**Gate (offline):** `bash tests/test.sh` + `bash scripts/build-release.sh` + `bash scripts/build-controller.sh`
**Spec:** [`../../specs/V0.4.5_Spec.md`](../../specs/V0.4.5_Spec.md) · rev1 [`../../specs/vcl-spec-v0.4-v0.5-rev1.md`](../../specs/vcl-spec-v0.4-v0.5-rev1.md)

| AC | Result | Evidence |
| --- | --- | --- |
| **4.5-01** | **PENDING LIVE** | Live Matrix A–G (see below) |
| **4.5-02** | **PENDING LIVE** | Replace Live Gate (Matrix G) |
| **4.5-03** | **PENDING LIVE** | No new public management listener (LIVE matrix notes) |
| **4.5-04** | **PENDING LIVE** | Matrix H — legacy seed; old client connects unchanged ([`LIVE.md`](LIVE.md)) |
| **4.5-05** | **PASS (offline) / PENDING LIVE** | Fail-close wrong key/URI/mode/symlink/incomplete flags; unit coverage in `tests/test-fleet.sh` |
| **4.5-06** | **PENDING LIVE** | Owner + legacy both usable; UUID/Reality preserved (Matrix H) |
| **4.5-07** | **PASS (offline)** | CTRL `0.4.5` / payload pin `0.3.2`; min Node `0.3.1`; artifacts embed `vincula-node-0.3.2` only |
| **4.5-08** | **PASS (offline)** | Closes 0.4.4 PARTIAL (AC-4.3-05): Node Instance History + recent usage; User destinations; shared CLI+UI operation journal |
| **4.5-09** | **PASS (offline) / PENDING LIVE+review** | Offline tests **1750** passed; digests OK; docs updated; LIVE + human review remain |

## Live Matrix A–H

| Matrix | Scenario | Status |
| --- | --- | --- |
| **A** | 0.3.1 legacy → Workspace migration | **PENDING LIVE** |
| **B** | Office WSL → sync / sync --full → UI | **PENDING LIVE** |
| **C** | Workspace copy → second WSL → access bind → sync → UI | **PENDING LIVE** |
| **D** | Audit archive export → second machine restore → historical query | **PENDING LIVE** |
| **E** | Fresh VPS provision (Node 0.3.2 pin) | **PENDING LIVE** |
| **F** | Existing 0.3.1 node adopt | **PENDING LIVE** |
| **G** | Physical instance Replace Live Gate | **PENDING LIVE** |
| **H** | Legacy single-user seed | **PENDING LIVE** — handbook [`LIVE.md`](LIVE.md) |

Do not mark PASS without operator evidence. No IPs / URIs / UUIDs / Reality keys / Clash secrets in this file.

## Offline gate (2026-08-25)

- Offline tests: **1750** passed (`bash tests/test.sh`, includes `test-fleet.sh`)
- `git diff --check` on first-party code paths: clean (docs may show CRLF warnings on Windows checkouts)
- Artifacts:
  - `dist/vincula-node-0.3.2.tar.gz` — `bb7d01fa4dd9476471db5298c9d7ffc482b7ae59ae8422c56bb3a49325c01997`
  - `dist/vincula-controller-0.4.5.zip` — `384d8312ea9615edc29f7e1467165bb1cbff952b2c06036beeeb71580a23cffa`
  - Sidecar digests match files; `payload-manifest.json` has `controller_version=0.4.5`, `node_payload_version=0.3.2`; no `0.3.1` payload pin in controller zip
- AC-4.5-08 closes [`../0.4.4/SUMMARY.md`](../0.4.4/SUMMARY.md) PARTIAL (Node Detail / User destinations / CLI ops history).

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.4.5"`.
- Node: `VINCULA_VERSION="0.3.2"` (payload pin); Minimum Node `0.3.1`.
- D45 namespaces unchanged: accounting-db/v4 · fleet-registry/v2 · fleet-cache/v4 · workspace/v1 · audit-archive/v1.
