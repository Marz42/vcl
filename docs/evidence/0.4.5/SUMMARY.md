# 0.4.5 Integration & Hardening + Legacy Seed — DoD SUMMARY

**Stamp:** CTRL `0.4.5` / NODE payload `0.3.2` · Minimum Node `0.3.1`
**Gate (offline):** `bash tests/test.sh` + `bash scripts/build-release.sh` + `bash scripts/build-controller.sh`
**Spec:** [`../../specs/V0.4.5_Spec.md`](../../specs/V0.4.5_Spec.md) · rev1 [`../../specs/vcl-spec-v0.4-v0.5-rev1.md`](../../specs/vcl-spec-v0.4-v0.5-rev1.md)

| AC | Result | Evidence |
| --- | --- | --- |
| **4.5-01** | **PENDING LIVE** | Live Matrix A–G (see below); **H PASS** |
| **4.5-02** | **PENDING LIVE** | Replace Live Gate (Matrix G) |
| **4.5-03** | **PASS LIVE (Matrix H)** | No new public management listener; Clash API loopback ([`LIVE.md`](LIVE.md)) |
| **4.5-04** | **PASS LIVE** | Matrix H — legacy seed; old client connects unchanged ([`LIVE.md`](LIVE.md)) |
| **4.5-05** | **PASS (offline) / PASS LIVE (Matrix H)** | Fail-close offline; LIVE clean-host / seed path exercised ([`LIVE.md`](LIVE.md)) |
| **4.5-06** | **PASS LIVE** | Owner + legacy both usable; UUID/Reality preserved; second fleet-home adopt OK ([`LIVE.md`](LIVE.md)) |
| **4.5-07** | **PASS (offline)** | CTRL `0.4.5` / payload pin `0.3.2`; min Node `0.3.1`; artifacts embed `vincula-node-0.3.2` only; 0.3.1→0.3.2 shaped migrate fixture |
| **4.5-08** | **PASS (offline)** | Closes 0.4.4 PARTIAL (AC-4.3-05): Node Instance History + recent usage; User destinations = host/bytes/connections (no network); shared CLI+UI operation journal (replace backup/restore sub-ops + `audit_archive_restore`; `--from-backup` SUCCESS only after verify) |
| **4.5-09** | **PASS (offline) / PENDING review** | Offline tests **1763** passed; Matrix H LIVE recorded; human review / remaining Matrix A–G remain |

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
| **H** | Legacy single-user seed | **PASS LIVE** — [`LIVE.md`](LIVE.md) (2026-08-26) |

Do not mark PASS without operator evidence. No IPs / URIs / UUIDs / Reality keys / Clash secrets in this file.

## LIVE gate (Matrix H)

| Field | Value |
| --- | --- |
| Date | 2026-08-26 |
| Outcome | Legacy seed provision + verify/sync + dual-user + second `FLEET_HOME` adopt |
| Privilege | root |
| Not recorded | IP, VLESS URI, UUID, Reality private key, Clash secret |

Operator notes (no secrets): empty/missing URI `sid` supported; listen port from URI; leftover non-VCL sing-box paths removed before install; Reality SNI HTTP 503 accepted by preflight/self-test.

## Offline gate (review-fix + LIVE follow-ups)

- Offline tests: **1763** passed (`bash tests/test.sh`, includes validate-seed argv / SUDO_UID / parser / from-backup journal / 0.3.1→0.3.2 fixture / empty-sid)
- Artifact SHAs below are a **retained record of one build**, not a reproducible proof of source→byte identity (zip/tar timestamps and packaging can differ across builds):
  - `dist/vincula-node-0.3.2.tar.gz` — `c24f2fe6792b479d52faa049add22387f48bd7d8d2ad8d526f4399b9911fa3ab`
  - `dist/vincula-controller-0.4.5.zip` — `3e7030e86e18a072bb4c033d90060271ae9e65e8afbb013fcdafb9df45cd9c76`
  - Sidecar digests match files; `payload-manifest.json` has `controller_version=0.4.5`, `node_payload_version=0.3.2`; no `0.3.1` payload pin in controller zip
- AC-4.5-08 closes [`../0.4.4/SUMMARY.md`](../0.4.4/SUMMARY.md) PARTIAL (Node Detail / User destinations host+bytes+conns / CLI ops history).

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.4.5"`.
- Node: `VINCULA_VERSION="0.3.2"` (payload pin); Minimum Node `0.3.1`.
- D45 namespaces unchanged: accounting-db/v4 · fleet-registry/v2 · fleet-cache/v4 · workspace/v1 · audit-archive/v1.
