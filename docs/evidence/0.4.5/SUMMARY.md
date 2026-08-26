# 0.4.5 Integration & Hardening + Legacy Seed — DoD SUMMARY

**Stamp:** CTRL `0.4.5` / NODE payload `0.3.2` · Minimum Node `0.3.1`
**Gate (offline):** `bash tests/test.sh` + `bash scripts/build-release.sh` + `bash scripts/build-controller.sh`
**Spec:** [`../../specs/V0.4.5_Spec.md`](../../specs/V0.4.5_Spec.md) · rev1 [`../../specs/vcl-spec-v0.4-v0.5-rev1.md`](../../specs/vcl-spec-v0.4-v0.5-rev1.md)

| AC | Result | Evidence |
| --- | --- | --- |
| **4.5-01** | **PASS LIVE** | Live Matrix A–H PASS (operator 2026-08-26); Matrix H handbook [`LIVE.md`](LIVE.md) |
| **4.5-02** | **PASS LIVE** | Replace Live Gate (Matrix G) |
| **4.5-03** | **PASS LIVE** | No new public management listener; Clash API loopback ([`LIVE.md`](LIVE.md)) |
| **4.5-04** | **PASS LIVE** | Matrix H — legacy seed; old client connects unchanged ([`LIVE.md`](LIVE.md)) |
| **4.5-05** | **PASS (offline) / PASS LIVE** | Fail-close offline + LIVE clean-host / seed path ([`LIVE.md`](LIVE.md)) |
| **4.5-06** | **PASS LIVE** | Owner + legacy both usable; UUID/Reality preserved; second fleet-home adopt OK ([`LIVE.md`](LIVE.md)) |
| **4.5-07** | **PASS (offline)** | CTRL `0.4.5` / payload pin `0.3.2`; min Node `0.3.1`; artifacts embed `vincula-node-0.3.2` only; 0.3.1→0.3.2 shaped migrate fixture |
| **4.5-08** | **PASS (offline)** | Closes 0.4.4 PARTIAL (AC-4.3-05): Node Instance History + recent usage; User destinations = host/bytes/connections (no network); shared CLI+UI operation journal |
| **4.5-09** | **PASS (offline) / PENDING review** | Offline gate green; Live Matrix A–H recorded; human review remains |

## Live Matrix A–H

| Matrix | Scenario | Status |
| --- | --- | --- |
| **A** | 0.3.1 legacy → Workspace migration | **PASS LIVE** |
| **B** | Office WSL → sync / sync --full → UI | **PASS LIVE** |
| **C** | Workspace copy → second WSL → access bind → sync → UI | **PASS LIVE** |
| **D** | Audit archive export → second machine restore → historical query | **PASS LIVE** |
| **E** | Fresh VPS provision (Node 0.3.2 pin) | **PASS LIVE** |
| **F** | Existing 0.3.1 node adopt | **PASS LIVE** |
| **G** | Physical instance Replace Live Gate | **PASS LIVE** |
| **H** | Legacy single-user seed | **PASS LIVE** — [`LIVE.md`](LIVE.md) (2026-08-26) |

Do not paste IPs / URIs / UUIDs / Reality keys / Clash secrets into this file.

## LIVE gate (Matrix H detail)

| Field | Value |
| --- | --- |
| Date | 2026-08-26 |
| Outcome | Legacy seed provision + verify/sync + dual-user + second `FLEET_HOME` adopt |
| Privilege | root |
| Not recorded | IP, VLESS URI, UUID, Reality private key, Clash secret |

Operator notes (no secrets): empty/missing URI `sid`; listen port from URI (preflight checks same port); leftover non-VCL sing-box removed; Reality SNI HTTP 503 accepted; legacy secret temps under early `$TMP_DIR`.

## Offline gate (review-fix + LIVE follow-ups)

- Offline tests: legacy unit + listen_port preflight (free / busy / 443-busy-ignored) passed after this harden.
- Artifact SHAs (one retained build record after listen_port / TMP_DIR harden):
  - `dist/vincula-node-0.3.2.tar.gz` — `577bcb73834fb4be5f0854a2e84e5ace28c7f64461701d9fbf12162758912336`
  - `dist/vincula-controller-0.4.5.zip` — `fea4e1a6ff922c6e579cc9d5b8b874075c32f7e6be61cdc3b23234734efb48c5`
- AC-4.5-08 closes [`../0.4.4/SUMMARY.md`](../0.4.4/SUMMARY.md) PARTIAL.

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.4.5"`.
- Node: `VINCULA_VERSION="0.3.2"` (payload pin); Minimum Node `0.3.1`.
- D45 namespaces unchanged: accounting-db/v4 · fleet-registry/v2 · fleet-cache/v4 · workspace/v1 · audit-archive/v1.
