# 0.5.5 closeout — PR #15 (`f05fab8`) H05 ACCEPTED (`PASS` by Marz) / merging to `main`

**2026-11-19 current entry (PR #15):** Following the earlier `21aba22` Batch 0 abort and iterative fixes (`7627f45` -> `330cdea` -> `80e6f2d` -> `f05fab8`), all 7 live nodes reached `0.5.5` / schema 5 (`<= 1.10s` `:443` cutover unavailability), T05–T08 passed with restricted `vincula-observer` active, and RC `f05fab8977039ba3e69b951ea059e1377f1e40b4` (`SOURCE_DATE_EPOCH=1794899643`, CI Run [`#151`](https://github.com/Marz42/vcl/actions/runs/44037742663) 7/7 `success`) completed an unbroken `24h00m38s` live soak across 6/7 reachable nodes (`urgentfury` disabled by operator decision due to ISP upstream IPv4 block) plus a matching 10-node 2h synthetic matrix (`PASS OFFLINE`, `7,200.0118s`). **Marz** confirmed explicit human `PASS` (`2026-11-19T09:55Z`), authorizing `review/0.5.5-upgrade-preparation -> main` merge (without tag/release). Prior `21aba22` / Batch 0–4 record:
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
| Live rollout, T01–T08 & observer hardening (`330cdea` -> `80e6f2d`, PR #15) | LIVE PASS: All 7 real nodes (`fresh050`, `eagleclaw`, `hot-beam-1`, `epicfury`, `upperhand`, `neptunespear`, `urgentfury`) cut over to `0.5.5` / schema 5 (`<= 1.10s` `:443` outage); `80e6f2d` (`EPOCH=1794736944`, CI #149/#150) hardened `vincula-observer` & verified T05–T08 + 12h `7/7` soak |
| Final RC `f05fab8` & CI (`2026-11-17`, PR #15) | PASS: `f05fab8977039ba3e69b951ea059e1377f1e40b4` (`EPOCH=1794899643`, Controller `df2b038a…`, Node `71b61c3d…` matching `80e6f2d` `release.lock` 20/20); CI [#44037742663](https://github.com/Marz42/vcl/actions/runs/44037742663) 7/7 jobs `success`; excludes ephemeral UDP (`>= 32768`) sockets from listener drift projection |
| Ten-node 2h synthetic matrix (`f05fab8`) | PASS OFFLINE: 10 simulated nodes, `7,200.0118s`, `PASS OFFLINE`, `two_hour_matrix=true`, `observation_errors=0`, bound to `f05fab8` (`abf23566…`) |
| Continuous 24h integrated soak (`f05fab8`, 6/7 reachable nodes) | LIVE PASS (6/7 scope): `vcl-h05-t09p3-20261118T0829Z` (`2026-11-18T08:29:22Z -> 2026-11-19T08:30:00Z`, `24h00m38s`, 289 rounds, `1,734/1,734 HEALTHY`, `1,440/1,440 :443 ok`, `288/288 drift MATCH`, `144/144 DB quick_check=ok`, `295/295` hashed paths); `urgentfury` excluded (`enabled=false`) by operator decision due to ISP upstream IPv4 block |
| H05-01..08 human judgment/signature | **ACCEPTED (`PASS` by Marz, `2026-11-19T09:55Z`)**: recorded in [HUMAN_ACCEPTANCE.md](HUMAN_ACCEPTANCE.md) |
| Mainline merge | **APPROVED / MERGING PR #15 -> `main`** (closing/superseding PR #13; no tag/release) |

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
