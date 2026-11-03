# 0.5.5 closeout — implementation in progress

Baseline `08af383`; approved contract: [SPEC](../../specs/V0.5.5_Closeout.md).
This is not an acceptance, frozen candidate, CI result or merge authorization
before H05. Historical evidence remains tied to its original inputs.

| Batch / gate | State |
| --- | --- |
| G0 contract and scope | APPROVED USER / recorded |
| A access and secret protection | IMPLEMENTED; commit `6326869`, targeted Windows/Linux PASS; later integration fixes included in D |
| B accounting, timestamps and migration | IMPLEMENTED; commit `3387bd5`, targeted Windows/Linux PASS |
| C cache, backups and failure boundaries | IMPLEMENTED; commit `5a7ee1f`, targeted Windows/Linux PASS |
| D checks, tools, docs and versions | IMPLEMENTED; final regression in progress |
| Full local/platform/artifact checks | IN PROGRESS; initial failures retained separately |
| Final required remote CI | PENDING |
| RC fixed inputs and digests | PENDING |
| Seven-node Live + ten-node simulated two-hour matrix | PENDING LIVE / PENDING OFFLINE |
| New RC continuous 24h integrated soak | PENDING LIVE |
| H05-01..08 human judgment/signature | PENDING HUMAN / NOT SIGNED |
| Mainline merge | BLOCKED ON H05; not performed |

Maintain a separate failure/recheck record. Never replace historical failure or
unperformed live acceptance with an offline/CI PASS.

R-02 now follows the user-approved independent-retention contract, superseding
the old raw-rebuild limitation. Other low-priority work is assigned to
[0.6/0.7](../../plans/0.6-0.7_Deferred_From_0.5.5.md). Migration, safe input and
capacity guidance: [runbook](../../operations/0.5.5-closeout-runbook.md).

New simulated scheduler runner: `scripts/soak-0.5.5-simulated.py`. Its real-clock
default is two hours/ten nodes. Short runs are explicitly smoke-only and never
close either the two-hour matrix or live proxy/inspect/H05 gates.
