# 0.3.1 final evidence SUMMARY

**Release recommendation:** READY  
**Known P0:** 0  
**Known P1 release blockers:** 0  
**Date:** 2026-08-20  

| Field | Content |
| --- | --- |
| Tree | `0.3.1` (stable stamp from `0.3.1-rc2`) |
| RC freeze tag | `v0.3.1-rc2` @ `63755b5` (immutable product freeze) |
| Release commit | `908fee9` (merge PR #3) + digest-freeze follow-up |
| Stable tag | `v0.3.1` |

## Artifacts (B27 / B28 freeze)

Published digests are from **GitHub Actions** `vincula-dist` on PR #3
([run 32341985689](https://github.com/Marz42/vcl/actions/runs/32341985689)),
not a local Windows/WSL rebuild (archive bit-identity can differ by tar metadata).

| Artifact | SHA256 |
| --- | --- |
| `vincula-node-0.3.1.tar.gz` | `9fdf68d5567fe5376bf531d58dd18c46792524c3cc95e7a69366607c031ecd59` |
| `vincula-controller-0.3.1.zip` | `053712194564f6551918f978ee7f0965c33db1b4eaabd81087f27ed962d70546` |

Sidecars: [`release-artifacts/`](release-artifacts/).

## Gate results

| Test | Environment | Artifact | SHA256 | Result | Evidence | Waiver |
| --- | --- | --- | --- | --- | --- | --- |
| B21 fresh install | Live VPS | node `0.3.1-rc2` | `ce806450…c93d92` | **PASS** | [`../0.3.1-rc2/B21-fresh-install.md`](../0.3.1-rc2/B21-fresh-install.md) | — |
| B22 live upgrade | Live VPS | rc1→rc2 | `ce806450…c93d92` | **PASS** | [`../0.3.1-rc2/B22-upgrade-rc1.md`](../0.3.1-rc2/B22-upgrade-rc1.md) | True `0.3.0→0.3.1` not run; rc1→rc2 surrogate accepted |
| B23 Schema 4 re-sync | Live Fleet | rc2 | (same) | **PASS** | [`../0.3.1-rc2/B23-fleet-resync.md`](../0.3.1-rc2/B23-fleet-resync.md) | — |
| B14 live replace | Dual VPS + Win11 | `0.3.1-dev` at run | (historical) | **PASS** | [`../0.3.1-live/SUMMARY.md`](../0.3.1-live/SUMMARY.md) | — |
| B24 replace smoke | — | — | — | **DEFERRED** | [`../0.3.1-rc2/B24-replace-deferred.md`](../0.3.1-rc2/B24-replace-deferred.md) | Non-blocking; B14 already PASS |
| B26 branch protection | GitHub `main` | — | — | **PASS** | [`../0.3.1-rc2/B26-branch-protection.md`](../0.3.1-rc2/B26-branch-protection.md) | — |
| B27 node black-box | Clean `/tmp` (WSL) + CI archive verify | node `0.3.1` | `9fdf68d5…ecd59` | **PASS** | [`release-artifacts/b27-unix-transcript.txt`](release-artifacts/b27-unix-transcript.txt) | Local WSL archive digests superseded by CI freeze |
| B27 controller Unix | Clean `/tmp` (WSL) | controller `0.3.1` | `05371219…70546` | **PASS** | same transcript | same |
| B27 controller Windows | Win11 | controller `0.3.1` | `05371219…70546` | **PASS** | [`windows-controller/b27-windows-smoke.txt`](windows-controller/b27-windows-smoke.txt) | Smoke used pre-CI local zip; re-verify with CI digest at upload |

Pointers under [`fresh-install/`](fresh-install/), [`upgrade/`](upgrade/), [`schema4-resync/`](schema4-resync/), [`replace/`](replace/) link to the RC/live records above.

## Post-release

Tag `v0.3.1` and published digests are immutable. Defects → `0.3.2` or `0.4.x`.
