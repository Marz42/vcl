# 0.3.1 final evidence SUMMARY

**Release recommendation:** READY  
**Known P0:** 0  
**Known P1 release blockers:** 0  
**Date:** 2026-08-20  

| Field | Content |
| --- | --- |
| Tree | `0.3.1` (stable stamp from `0.3.1-rc2`) |
| RC freeze tag | `v0.3.1-rc2` @ `63755b5` (immutable product freeze) |
| Stable tag | `v0.3.1` (after merge of release PR) |

## Artifacts (B27)

| Artifact | SHA256 |
| --- | --- |
| `vincula-node-0.3.1.tar.gz` | `b83c5769aefd7335484084b04f80c9d7f4bb723b9d7c5ac737f456a256c71256` |
| `vincula-controller-0.3.1.zip` | `166bc7a1db42dd537e92c13414dbbcb888b93b54a169403a9fa27c1bc9c9e6fb` |

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
| B27 node black-box | Clean `/tmp` (WSL) | node `0.3.1` | `b83c5769…71256` | **PASS** | [`release-artifacts/b27-unix-transcript.txt`](release-artifacts/b27-unix-transcript.txt) | — |
| B27 controller Unix | Clean `/tmp` (WSL) | controller `0.3.1` | `166bc7a1…9e6fb` | **PASS** | same transcript | — |
| B27 controller Windows | Win11 | controller `0.3.1` | `166bc7a1…9e6fb` | **PASS** | [`windows-controller/b27-windows-smoke.txt`](windows-controller/b27-windows-smoke.txt) | — |

Pointers under [`fresh-install/`](fresh-install/), [`upgrade/`](upgrade/), [`schema4-resync/`](schema4-resync/), [`replace/`](replace/) link to the RC/live records above.

## Post-release

Tag `v0.3.1` and published digests are immutable. Defects → `0.3.2` or `0.4.x`.
