# 0.5.5 closeout — PR #15 staged-helper fix / pending Linux RC rebuild & CI

**2026-11-14 current entry (PR #15):** Prior frozen RC `21aba22` aborted cleanly at
Batch 0 `fresh050` canary (`phase=checkpoint`, `PREPARATION_FAILED`,
`migrate_started=false`: staged `bin/vincula` `load_vincula_common()` sourced old
installed `/usr/local/lib/vincula/vincula-common.sh` ahead of staged `0.5.5`
`lib/vincula-common.sh`, missing `python_private`). PR #15 now includes the
minimal `bin/vincula` staged-library & embedded `upgrade-rollback-common.sh` fix,
unified `_resolve_lib_py()`, updated `release.lock`, and 2 regression tests in
`tests/test_checkpoint_integrity.py` (no generalized stress tests). Controller
`fleet.db` is already cleanly at `schema 5`; **new RC artifacts (`build-release.sh`
/ `build-controller.sh` with `SOURCE_DATE_EPOCH` pinned to the fix commit) await
Linux build + CI verification before re-running Batch 0.** Prior `21aba22` record:
[RC_FREEZE_21ABA22.md](RC_FREEZE_21ABA22.md). Acceptance entry:
[HUMAN_ACCEPTANCE.md](HUMAN_ACCEPTANCE.md) · [LIVE_FOLLOWUP.md](LIVE_FOLLOWUP.md) ·
[LIVE_PREFLIGHT_CHECKLIST.md](LIVE_PREFLIGHT_CHECKLIST.md).

**2026-11-09 support-boundary freeze (consolidated from PR #13):** support-boundary
revision frozen at source commit `4651064…`; Linux local tests/build, CI run
`42531836471` (seven required jobs) and the ten-node 2h synthetic matrix passed.
See [candidate freeze](SUPPORT_BOUNDARY_CANDIDATE_FREEZE.md) and
[revision status](SUPPORT_BOUNDARY.md). Live/H05 remain PENDING; the frozen
inputs, artifacts and PASS results below are historical and do not cover later
revisions. User-reported canary preparation is also recorded there.

Baseline `08af383`; approved contract: [SPEC](../../specs/V0.5.5_Closeout.md).
Runtime source `7bef780`; fixed validation inputs `653f7dd`; Node/Controller 0.5.5.
The [candidate](CANDIDATE_FREEZE.md) is frozen locally and has passed required
code CI. Field work is DEFERRED USER (2026-11-03), H05 remains unsigned, and main
is unchanged. Historical evidence remains tied to its original inputs.

| Batch / gate | State |
| --- | --- |
| G0 contract and scope | APPROVED USER / recorded |
| A access and secret protection | IMPLEMENTED; commit `6326869`, targeted Windows/Linux PASS; later integration fixes included in D |
| B accounting, timestamps and migration | IMPLEMENTED; commit `3387bd5`, targeted Windows/Linux PASS |
| C cache, backups and failure boundaries | IMPLEMENTED; commit `5a7ee1f`, targeted Windows/Linux PASS |
| D checks, tools, docs and versions | IMPLEMENTED; regression and CI passed; follow-up storage/backup/CI fixes included |
| Full local/platform/artifact checks | PASS OFFLINE: Windows/root Linux 196 Python tests; root Bash 1,966, ordinary-user Bash 1,968; 18 contracts/five cache-only surfaces; [verification](VERIFICATION.md) records skips and retained failures |
| Required remote code CI | PASS: [#129](https://github.com/Marz42/vcl/actions/runs/41595858638), all seven jobs; [snapshot](REMOTE_CI_CODE.json) |
| RC fixed inputs and digests | FROZEN: 201 inputs; Node `38336240…`, Controller `14312b21…`, epoch 1793689859; reproducible rebuild PASS |
| Support-boundary revision (2026-11-09) | OFFLINE GATES PASS: Linux local 203/203 Python user+root, 1,969 Bash user / 1,967 Bash root; Node `38336240…`, Controller `e2daaaf…`; CI #42531836471 seven jobs; ten-node 2h synthetic PASS; Live/H05 PENDING; [freeze](SUPPORT_BOUNDARY_CANDIDATE_FREEZE.md) |
| Upgrade-preparation & review-4 (2026-11-13, PR #15) | OFFLINE GATES PASS (historical unfrozen record): runtime `21aba22`; Python 228/10/0, Bash 1,970 user / 1,968 root; Node `7b7a1b60…`, Controller `784ca4d0…` (epoch `1794384920`); CI [#43353200757](https://github.com/Marz42/vcl/actions/runs/43353200757) (`04dd901`) seven jobs; [review-4](REVIEW4_FIXES.md) |
| Acceptance RC freeze (`21aba22`, 2026-11-13, PR #15) | SUPERSEDED AT BATCH 0 (`2026-11-14`): `fresh050` canary stopped at `phase=checkpoint` (`PREPARATION_FAILED`, `migrate_started=false`) due to `load_vincula_common()` preferring installed `0.5.0` lib over staged `0.5.5`; Node `7b7a1b60…` / Controller `784ca4d0…` retired; [RC freeze / abort](RC_FREEZE_21ABA22.md) |
| Staged-helper fix candidate (2026-11-14, PR #15) | PREPARING NEW RC: `bin/vincula` `load_vincula_common()` + `_resolve_lib_py()` + `upgrade-rollback-common.sh` + `release.lock` (`e9c7a1a9…`) + regression tests; Controller `fleet.db` already migrated to `schema 5`; awaiting Linux `build-release.sh` / `build-controller.sh` verification + CI before re-running Batch 0; [live preflight](LIVE_PREFLIGHT_CHECKLIST.md) |
| Seven-node Live + ten-node simulated two-hour matrix | DEFERRED USER / PENDING LIVE; synthetic dimension PASS OFFLINE: ten nodes, 7,200.016s, 2,400 samples, zero errors |
| New RC continuous 24h integrated soak | DEFERRED USER / PENDING LIVE |
| H05-01..08 human judgment/signature | PENDING HUMAN / NOT SIGNED |
| Mainline merge | BLOCKED ON H05; not performed |

Maintain a separate failure/recheck record. Never replace historical failure or
unperformed live acceptance with an offline/CI PASS.

R-02 now follows the user-approved independent-retention contract, superseding
the old raw-rebuild limitation. Other low-priority work is assigned to
[0.6/0.7](../../plans/0.6-0.7_Deferred_From_0.5.5.md). Migration, safe input and
capacity guidance: [runbook](../../operations/0.5.5-closeout-runbook.md).
Issue-by-issue implementation ownership and verification mapping:
[execution checklist](../../plans/0.5.5_Closeout_Execution.md). The user reported
the Controller/Workspace is unavailable and asked to skip field work for now;
the exact [resume checklist](LIVE_FOLLOWUP.md) preserves canary, backup/recovery,
real-client, 24h/H05 and merge gates.

New simulated scheduler runner: `scripts/soak-0.5.5-simulated.py`. Its real-clock
default is two hours/ten nodes. Short runs are explicitly smoke-only and never
close either the two-hour matrix or live proxy/inspect/H05 gates.
The completed [two-hour report](SIMULATED_MATRIX_2H.json) retains its actual
source `37f45dc`; all 17 observation/fixture/runner inputs match `653f7dd` exactly.
Storage/backup/packaging changes are outside that narrow synthetic proof scope.
