# 0.5.5 closeout — offline candidate frozen

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
