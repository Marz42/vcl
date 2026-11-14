# 0.5.5 support-boundary candidate freeze — 2026-11-09

**FROZEN / OFFLINE GATES PASS / PENDING LIVE / PENDING HUMAN.**

This record freezes the support-boundary revision only. It does not overwrite or
re-label the original 0.5.5 candidate records; see [original candidate](CANDIDATE_FREEZE.md).
The evidence-only commit that adds this record is a docs-only child of the source
commit and is not a new source or CI head.

| Input | Fixed value |
| --- | --- |
| Source commit | `465106440688ab73823cbe4871139c834488d4ae` |
| Parent | `56a1626` plus `vcl-0.5.5-support-boundary.patch` |
| Source inputs | [SUPPORT_BOUNDARY_SOURCE_INPUTS.json](SUPPORT_BOUNDARY_SOURCE_INPUTS.json), 202/202 LF-normalized matches |
| `SOURCE_DATE_EPOCH` | `1793689859` |
| Node archive | `dist/vincula-node-0.5.5.tar.gz` |
| Node SHA256 | `383362401f0574c44649e5071b81f31ab03f03f54588ee6456e62e4627524671` |
| Controller archive | `dist/vincula-controller-0.5.5.zip` |
| Controller SHA256 | `e2daaafacd9732161a4eb02df9b681bed72e61f599db82e3d0f43957bb31cc60` |
| Artifact check | `PASS OFFLINE` — schemas 18, cache-only surfaces 5, `node_cli=PASS` |
| Deterministic rebuild | PASS — both archives byte-identical to first build |
| Required CI | run [42531836471](https://github.com/Marz42/vcl/actions/runs/42531836471), head `4651064`, seven jobs PASS |
| Ten-node 2h synthetic matrix | PASS OFFLINE — [report](SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.json), 2026-11-09 07:28:44–09:28:44 CST, 7,200.0056 s, 2,401 samples, 0 observation errors |

## Evidence binding

- CI run `42531836471` is bound to **source commit** `4651064`; it is not the CI
  of the later evidence-only commit.
- Original CI #129 and the original candidate digests remain historical and do
  not cover this revision.
- Original candidate records remain unchanged: [CANDIDATE_FREEZE.md](CANDIDATE_FREEZE.md),
  [SOURCE_INPUTS.json](SOURCE_INPUTS.json), [REMOTE_CI_CODE.json](REMOTE_CI_CODE.json).
- Execution identity deviation **accepted**: the `marz` `sudo -n` prerequisite
  was unavailable, so root suites ran via WSL root (`wsl -u root`). Root coverage
  passed; no rerun or passwordless-sudo configuration is required.
- Local test/build detail: [SUPPORT_BOUNDARY.md](SUPPORT_BOUNDARY.md). Synthetic
  original-file SHA256 and input verification: [manifest](SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H_MANIFEST.json).
- The synthetic report's 17 inputs match source commit `4651064`; the 202 source
  inputs are unchanged by this docs-only evidence commit.

## Still pending

- fresh050 and Controller backup validation, then the upgrade window.
- Real proxy, Inspect/Drift and other Live scenarios.
- New continuous 24h RC soak.
- H05-01..08 human review/signature.
- PR #13 remains a draft; no merge, tag or release.
