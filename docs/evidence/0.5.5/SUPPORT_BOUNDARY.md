# 0.5.5 support-boundary revision — 2026-11-08

**OFFLINE GATES PASS / PENDING LIVE / PENDING HUMAN.**

This revision is based on `56a1626` plus the explicitly hashed working-tree
inputs in `SUPPORT_BOUNDARY_SOURCE_INPUTS.json`, frozen at source commit
`465106440688ab73823cbe4871139c834488d4ae`. It is not the already frozen
`653f7dd` candidate. Linux local tests/build, CI run `42531836471` (seven required
jobs) and the ten-node 2h synthetic matrix have passed. Live/H05 remain pending;
do not start the final 24h soak or claim live behavior from this offline result.

## Contract and implementation

- Minimum supported Node: 0.5.5. This Controller validates only the paired Node
  0.5.5 runtime; future releases are not automatically promised compatibility.
- Capability discovery retains actual version/capabilities/raw response but
  returns UNSUPPORTED / NODE_VERSION_UNSUPPORTED outside that exact version.
  Prereleases are never normalized into stable releases. Malformed protocol
  versions remain ERROR; authentication errors retain their meaning.
- Telemetry/monitoring, Inspect and enhanced Verify honor this negotiation.
  Unsupported observation is UNKNOWN, not an unreachable Node or proof of a
  working proxy. No unsupported-node telemetry/inspect/verify snapshot is fetched.
- Explicit identity, upgrade, recovery and historical-data tools remain for
  operator-directed ingress. This is a supported-runtime contract, not a new
  universal SSH command firewall. No broad transport interception is added.
- Existing typed upgrade allowlist is an ingress allowlist only. In particular,
  fresh050's real 0.5.0 -> 0.5.5 path remains PLANNED, 0.3.1-rc2 remains REFUSED,
  and same-version SKIPPED is not migration or recovery evidence.
- Seven formal live Nodes run 0.5.5. Only actual required ingress/recovery paths
  are tested; two arbitrary historical versions are no longer required.
- Traffic Policy v0.1 is deferred to 0.6.x, without implementation in this RC.

## Verification performed here

| Check | Result |
| --- | --- |
| Targeted version/negotiation/ingress tests | 7 tests PASS on Windows Python 3.11 |
| Full Windows suite before the final additional Inspect/Verify test | 202 discovered: 188 passed, 13 platform skips, 1 environment error |
| Full-suite environment error | `test_http_inspect_get_remains_local_and_accept_requires_fresh_telemetry_identity`: loopback HTTP request rejected with WinError 10013; retained in `tmp/support-boundary-windows.log` |
| Windows-side WSL execution (preparer, historical) | NOT USED: Wsl/E_ACCESSDENIED; accepted Linux WSL2 execution recorded below |
| Windows-side Git Bash execution (preparer, historical) | NOT USED: NtCreateDirectoryObject permission error 0xC0000022; Linux Bash coverage recorded below |
| Linux Python user | PASS: 203 tests, 10 skipped, 0 failures (`python-user.log`) |
| Linux Python root | PASS: 203 tests, 0 skipped, 0 failures (`python-root.log`) |
| Linux Bash user | PASS: 1,969 tests, 0 failures (`bash-user.log`) |
| Linux Bash root | PASS: 1,967 tests, 0 failures (`bash-root.log`) |
| Linux/root execution identity | ACCEPTED DEVIATION: `marz` `sudo -n` needs a password; root suites ran via WSL root (`wsl -u root`). Root coverage passed; the human owner accepted this execution mode; no rerun required. |
| Standard packages | PASS: Node `38336240…`, Controller `e2daaaf…` (`first-build.sha256`) |
| Isolated artifact check | PASS OFFLINE: schemas 18, cache-only surfaces 5, `node_cli=PASS` |
| Internal locks and sidecars | PASS: both sidecars, `release.lock`, `controller.lock` |
| Deterministic rebuild | PASS: both archives byte-identical to first build |
| Remote required CI | PASS: run [42531836471](https://github.com/Marz42/vcl/actions/runs/42531836471), seven required jobs, head `4651064`; old CI #129 does not cover this revision |
| Synthetic ten-node 2h matrix | PASS OFFLINE: [report](SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.json), 2026-11-09 07:28:44–09:28:44 CST, 7,200.0056s, 10 nodes, 2,401 samples, 0 observation errors |
| Live/H05 | PENDING: no Node contacted by this code revision |

## Linux local validation — 2026-11-08/09

Isolated worktree: `/home/marz/vcl-055-boundary.CcgaundJ` (parent `56a1626`;
patch applied, not the frozen `653f7dd` candidate). Kali WSL2, Python 3.13.12,
Git 2.51.0. Source inputs: 202/202 LF-normalized digests match
`SUPPORT_BOUNDARY_SOURCE_INPUTS.json`. `git diff --check` passed.

Test results: Python user 203 tests (10 skipped), Python root 203 tests (0
skipped), Bash user 1,969 passed, Bash root 1,967 passed; zero failures/errors in
all four. Root Python emitted one `ResourceWarning` (unclosed sqlite connection)
but the suite was OK.

Execution identity deviation (accepted): `sudo -n` as `marz` requires a password,
so the root suites were run in a WSL root shell (`wsl -u root`), where
`sudo -n env ...` succeeded. Root coverage passed. The human owner accepted this
execution mode; no rerun or passwordless-sudo configuration is required.

First Node build recheck: the privileged Bash suite left `dist/` owned by root,
so the first ordinary-user `build-release.sh` failed with `Permission denied`.
The generated `dist/` was removed as root and rebuilt as `marz` with
`SOURCE_DATE_EPOCH=1793689859`; the recheck passed. The original failure log was
overwritten by the recheck; the preserved note is
`tmp/support-boundary/node-build.failure.log`. Root-test artifacts built without
the fixed epoch (Node `76d75bbc…`) were discarded and are not evidence.

Artifacts and deterministic rebuild:

| Artifact | SHA256 |
| --- | --- |
| `vincula-node-0.5.5.tar.gz` | `383362401f0574c44649e5071b81f31ab03f03f54588ee6456e62e4627524671` |
| `vincula-controller-0.5.5.zip` | `e2daaafacd9732161a4eb02df9b681bed72e61f599db82e3d0f43957bb31cc60` |

The Node digest matches the expected unchanged Node. The Controller digest
differs from the original `14312b21216bb4863a68c50ad9a443ac44786052c04b7648811cf4ca21ec233b`.
Sidecars and internal `release.lock`/`controller.lock` checks passed. The isolated
checker returned `{"state": "PASS OFFLINE", "version": "0.5.5", "schemas": 18,
"cache_only_surfaces": 5, "node_cli": "PASS"}`. A second build with the same
epoch produced byte-identical archives.

Remote required CI (`42531836471`) and the ten-node 2h synthetic matrix have
since passed. Still pending: the new continuous 24h RC soak, Live/H05, and the
fresh050/Controller backup validation and upgrade window. No Node was contacted
and the formal Workspace was not used for this offline validation.

The additional test checks old-node Inspect/Verify perform zero remote calls.
The distributed-artifact checker now also verifies the support floor and paired
version, and exercises current/old/prerelease/future capability responses.
The Bash suite now contains an end-to-end old-version capability/telemetry case.
These added artifact/Bash assertions still need their normal Linux execution.

## Completing the freeze on a permitted Linux executor

1. Transfer/apply the complete revision, including new tests and these records.
   Verify every LF-normalized source digest in SUPPORT_BOUNDARY_SOURCE_INPUTS.json
   before testing. Do not build `653f7dd` again as the revised candidate.
2. Run the normal Linux/root Python and Bash suites and the required CI platform
   matrix, including Windows loopback and Python 3.10. Retain failures/rechecks.
3. Use the standard build scripts at fixed `SOURCE_DATE_EPOCH=1793689859`.
   Keeping this deterministic epoch is intentional: Node sources are unchanged;
   the new Controller archive must have a new digest. Do not hand-edit dist.
4. Run the isolated artifact checker, verify internal locks and sidecars, and
   rebuild with the same epoch to prove both archives are byte-identical.
5. Generate a new source-input/artifact manifest and candidate record, binding
   the actual source commit, new Controller SHA, Node SHA, logs and CI head.
   Recheck the 2h synthetic proof's relevant hashes; changed Observation inputs
   invalidate automatic reuse of the previous hash match. Run a new matrix.
6. Only after those checks pass mark this revision FROZEN / PENDING LIVE. Start
   live acceptance and the new continuous 24h run on those exact bytes.

The offline gates above are complete; the new [candidate freeze record](SUPPORT_BOUNDARY_CANDIDATE_FREEZE.md)
binds the source commit, CI, artifacts and synthetic report. Live/H05 and the
continuous 24h soak remain pending.

Historical files CANDIDATE_FREEZE.md, SOURCE_INPUTS.json and REMOTE_CI_CODE.json
continue to identify the original candidate. Their values are not overwritten.

## Operator-reported preparation (not new-RC live acceptance)

On 2026-11-08 the operator reported original-package SHA reproduction, fresh050
observe capabilities/telemetry and identity checks, Agent admin binding,
administrator SSH, VNC root login, and an Android HTTPS proxy check at 21:56
Asia/Shanghai. Node remains 0.5.0. Workspace revision is 17. No backup, migration,
new-RC upgrade, measured <=3s outage or new-RC soak has been reported.
After installing this Controller revision, old-node capabilities/telemetry will
intentionally return UNSUPPORTED; prior successful old-node reads remain bound
to the original Controller candidate.
