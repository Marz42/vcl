# 0.5.5 live acceptance — PR #15 (`f05fab8`) T01–T09 complete / T10 review

Status: **LIVE T01–T09 EXECUTED ON PR #15 (`f05fab8`, `SOURCE_DATE_EPOCH=1794899643`, CI Run `#151` 7/7 `success`) / T10 AWAITING HUMAN PASS SIGN-OFF BY MARZ**.
Following the prior `21aba22` Batch 0 abort and iterative live fixes (`7627f45` -> `330cdea` -> `80e6f2d` -> `f05fab8`), all 7 live nodes reached `0.5.5` / schema 5 with `<= 1.10s` `:443` cutover unavailability, restricted `vincula-observer` & T05–T08 passed, and RC `f05fab8` completed an unbroken `24h00m38s` live soak (`vcl-h05-t09p3-20261118T0829Z`, 6/7 reachable nodes with `urgentfury` excluded by operator decision due to ISP upstream IPv4 block) plus matching 10-node 2h synthetic matrix (`abf23566…`, `7,200.0118s`, `PASS OFFLINE`). See [RC_FREEZE_21ABA22.md](RC_FREEZE_21ABA22.md) and [HUMAN_ACCEPTANCE.md](HUMAN_ACCEPTANCE.md).

## Current PR #15 candidate (2026-11-14, awaiting Linux build + CI)

- Fix scope: `bin/vincula` (`load_vincula_common()` staged-first order,
  `upgrade-rollback-common.sh` embedded in checkpoint, unified `_resolve_lib_py()`),
  updated `release.lock`, and 2 regression tests in
  `tests/test_checkpoint_integrity.py`.
- Reproducible build rule: on-site Linux `bash scripts/build-release.sh` and
  `bash scripts/build-controller.sh` must pin `SOURCE_DATE_EPOCH` to the fix
  commit's `%ct` timestamp so `dist/` digests match GitHub Actions `artifact`
  CI (`vincula-dist`) bit-for-bit regardless of any later docs commits.
- Prior retired artifacts (`21aba22`, `SOURCE_DATE_EPOCH=1794384920`): Node
  `7b7a1b60d5dfa228291b3b99ac2dd87afd97c22d22d86f9d7732c86157b63c4b`, Controller
  `784ca4d0ef6e8181d683ab6f8ee998e216038cbf789c257c7dd50936394c7892`
  ([review-artifacts/](review-artifacts/README.md) — **do not use for upgrades**).
- Consolidated offline gates from PR #13: support-boundary CI
  [42531836471](https://github.com/Marz42/vcl/actions/runs/42531836471) and
  ten-node 2h synthetic matrix ([SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.md](SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.md);
  17/17 observation/fixture/runner inputs match `21aba22`/HEAD).
- Before T03/T04/T09 production mutation or 24h soak, explicitly freeze and
  verify the PR #15 `21aba22` candidate packages rather than installing the
  historical `4651064` or `653f7dd` archives.

## Support-boundary candidate frozen (2026-11-09, historical baseline consolidated from PR #13)

Source commit `465106440688ab73823cbe4871139c834488d4ae`; offline gates pass:
Linux local tests/build, CI run [42531836471](https://github.com/Marz42/vcl/actions/runs/42531836471)
(seven required jobs), and the ten-node 2h synthetic matrix. See
[candidate freeze](SUPPORT_BOUNDARY_CANDIDATE_FREEZE.md).

Still pending: fresh050/Controller backup validation, upgrade window, real
proxy/Inspect/Drift, continuous 24h RC soak, and H05. No Node was contacted by
the offline validation. The 2026-11-08 operator preparation remains historical.

## Current scope (user decision, 2026-11-08)

- Formal acceptance starts at Controller/Node 0.5.5; minimum supported Node is
  0.5.5. Older Nodes are not a maintained runtime compatibility matrix.
- Preserve actual old version strings in inventory. Where existing machines
  need migration, validate their actual one-time ingress path and recovery;
  do not require two arbitrary historical source versions. Recovery to an old
  checkpoint is emergency recovery, not renewed support for that version.
- Seven real Nodes run 0.5.5 for the formal matrix/soak, retaining OS/role
  diversity; at least ten simulated Nodes run for two hours. New RC continuous
  24h, real proxy, Inspect/Drift and H05 remain mandatory.
- Traffic Policy v0.1 / Policy Engine (Steam domain blocking, user bindings,
  hit audit) belongs to 0.6.x and is not a 0.5.5 acceptance gate.
- This is a revised acceptance contract, not proof of a runtime version gate.
  Before RC freeze, reconcile current support docs and code behavior for old
  Nodes (explicit unsupported/upgrade guidance). Retain historical manifests
  and CI records; rebuild/revalidate affected inputs before a new freeze.

Resume owner: the user/operator supplies the actual Controller environment and
portable Workspace path. No credential needs to be pasted into chat. The code
owner prepares the exact action/evidence/recovery sheet; the user confirms the
named production window and makes the final H05 judgment.

| Order | Follow-up | Required completion evidence |
| --- | --- | --- |
| 1 | Locate formal Controller, Workspace and machine-local bindings/cache; confirm seven actual targets and OS/version/roles | Redacted inventory, independent identity/capability checks and read-only fingerprints; preserve prerelease version strings |
| 2 | Verify frozen package SHA/epoch; take and validate consistent backups; rehearse schema-5 conversion on a separate copy | IDs/generations/export sequences/cursors preserved, UTC/day totals reconciled, legacy range and deleted-history uncertainty explicit, enough migration/journal space |
| 3 | Select recoverable canary and exact maintenance window | Concrete target, affected service/action, impact, backup paths/readback, stop criteria and recovery commands approved before any production mutation |
| 4 | Canary then staged cutover to 0.5.5; actual required migration and recovery paths only | Real client profile/identity/accounting preservation, actual permissions, successful restore and measured new-connection unavailability upper bound <=3s where upgrade occurs; same-version SKIPPED is not upgrade evidence |
| 5 | H05-02..07 permissions, Agent keys, observer, accountd, proxy/accounting separation, SSH/Controller outage, Finding and Drift/Inspect | Separate before/fault/recovery records, actual proxy probes and effective Inspect data, zero unintended writes on observation-only paths |
| 6 | Seven real 0.5.5 nodes plus a separately recorded ten-node synthetic matrix; continuous >=24h integrated new RC soak | Fixed inputs, real UTC/monotonic window, real proxy, Inspect/Drift, cache growth/stop/recovery and raw log hashes; no duration stitching; prior synthetic evidence reusable only with matching relevant inputs/scope |
| 7 | One-page H05-01..08 review and explicit human PASS | Acceptor/time/signature, scale deviation, known limits, all required evidence and deferred backlog |
| 8 | Final PR #15 title/body, undraft and merge-commit checks (closing/superseding draft PR #13) | Final head/base/seven CI checks, preserved history, main CI/version/docs confirmation; no tag/release |

Old A/B/C evidence remains useful only within its original scope. The
[impact review](HISTORICAL_EVIDENCE_IMPACT.md) explains what needs a new run.
Failure evidence is retained; a repaired run is a separate recheck. After cutover
has new writes, preserve the new database before reverting to an older snapshot;
that revert cannot be called lossless.

## Operator handoff — T01–T09 complete / T10 pending explicit verdict

T01–T09 have been executed and consolidated in [HUMAN_ACCEPTANCE.md](HUMAN_ACCEPTANCE.md); historical failures remain retained separately from rechecks. Final verdict and mainline merge remain explicitly gated on **Marz** (T10).

| ID | Operator action | Status / Outcome |
| --- | --- | --- |
| T01 | Identify actual Controller host, executable/version, Workspace path, seven target aliases and recoverable canary | **DONE** (7 real nodes + `fresh050` canary + Controller schema-5) |
| T02 | With supplied target-specific read-only commands, collect identity/capabilities, OS, services, storage and current proxy baseline | **DONE** (pre-cutover identities/versions/storage verified read-only) |
| T03 | After revised RC is frozen, verify packages and create/verify consistent backups; rehearse necessary schema migration on copies | **DONE** (`4af12bc`/`330cdea`/`80e6f2d`/`f05fab8` verified deterministic builds & backups including `neptunespear` `1.42 GB` DB) |
| T04 | In the agreed canary window, install/migrate to 0.5.5 and rehearse recovery; then stage remaining nodes | **DONE** (7/7 nodes at `0.5.5` / schema 5, `:443` cutover max gap `0.00s–1.10s <= 3s`, controlled & auto-rollbacks + re-upgrades verified) |
| T05 | Exercise admin/observe separation, Agent selectors, revocation and accountd identity | **DONE** (re-verified on `80e6f2d` with `observe_ssh_user=vincula-observer`, `/root/.ssh/authorized_keys` cleaned, `AUTH_FAILED` w/o fallback, `vincula-accountd` unprivileged) |
| T06 | Check sync, UTC/day totals, history coverage and cache capacity failure/recovery on isolated copies | **DONE** (`RAW_RECONSTRUCTED`, `UTC_CONNECTION_START`, isolated `/tmp` `CACHE_LIMIT_REACHED` & resume, bounded sync cursor advances) |
| T07 | In the canary window, separately inject sing-box/accountd and SSH/Controller outages | **DONE** (`accountd` stop / `sing-box` stop / 75s SSH block / 320s Controller offline recovery & bounded sync backfill) |
| T08 | Apply and revert controlled listener/unit/config drift, then verify observation-only behavior | **DONE** (baseline accept, 3 read-only rounds zero side-effects, unit drift detect & restore to `MATCH`, `f05fab8` `288/288` listener `MATCH`) |
| T09 | Keep 0.5.5 Nodes available for fixed-RC continuous 24h soak; run/revalidate separate ten-node 2h synthetic matrix | **DONE (6/7 scope)** (`f05fab8` `vcl-h05-t09p3-20261118T0829Z` `24h00m38s`, 289 rounds, `1,734/1,734 HEALTHY`, `1,440/1,440 :443 ok`, `288/288 drift MATCH`, `295/295` hashed paths; `urgentfury` disabled due to ISP IPv4 block; same-RC 10-node 2h synthetic `PASS OFFLINE` `7,200.0118s`) |
| T10 | Review H05-01..08 evidence, limits and remaining defects | **IN REVIEW — PENDING EXPLICIT PASS VERDICT BY MARZ** (no automatic PASS, merge, tag or release) |

PR #13's offline freeze and 2h synthetic evidence are consolidated into PR #15.
T01/T02 read-only discovery may proceed immediately; production cutover (T04)
and the final soak (T09) must use the frozen PR #15 (`21aba22`) RC and remain
blocked until Live/H05 completion.
