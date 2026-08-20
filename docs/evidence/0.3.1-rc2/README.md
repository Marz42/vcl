# B19 / B20 evidence — 0.3.1-rc2

**Tag:** `v0.3.1-rc2` → commit `63755b5f774efd13abf58a83851783cac7c525c8`  
**Date:** 2026-08-20

## B19

- Product stamps: `vincula` / `vcl-fleet` / README / manual / readiness / known-issues = `0.3.1-rc2`
- Allowlist: `0.3.0`, `0.3.1-dev`, `0.3.1-rc1` → `0.3.1-rc2`
- Freeze policy recorded in [`../../release-readiness-0.3.1.md`](../../release-readiness-0.3.1.md) (B19 section)
- UI HTTP `version_string` tracks `VCL_FLEET_VERSION`

## B20 artifacts

| Artifact | SHA256 |
| --- | --- |
| `vincula-node-0.3.1-rc2.tar.gz` | `ce80645029aefe075097156e1f2929ca1ac0e0370224d0d48bc68e5c84c93d92` |
| `vincula-controller-0.3.1-rc2.zip` | `4ac88c4b03e52f309942e31ac1dd7eed982b4e6139f2a9340851f500a727415f` |

Local verification: `release.lock` / `controller.lock` / sidecar digests OK; black-box controller `version`/`help`/`init`/module load OK.

## Local CI equivalents (2026-08-20)

| Job | Result |
| --- | --- |
| unit (WSL host) | PASS — 1280 |
| unit (ubuntu:latest container, writable copy) | PASS — 1279 |
| unit (debian:12 container, writable copy) | PASS — 1279 |
| unit (debian:13 container, writable copy) | PASS — 1279 |
| concurrency fixtures present | PASS (grep gates) |
| failure-injection fixtures present | PASS (grep gates) |
| artifact build + black-box | PASS |

GitHub Actions evidence: run after push of `main` + `v0.3.1-rc2`.
