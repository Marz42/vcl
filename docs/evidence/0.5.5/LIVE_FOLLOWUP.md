# 0.5.5 live acceptance — resumed preparation, 2026-11-08

Status: **PREPARING / PENDING LIVE / PENDING HUMAN**. The user has resumed
acceptance preparation. The November 3 deferral is historical; Controller and
Workspace availability must now be checked. No current Node was contacted,
upgraded, restarted or fault-injected by this review. H05 remains unsigned.

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
| 8 | Final PR #13 title/body, undraft and merge-commit checks | Final head/base/seven CI checks, preserved history, main CI/version/docs confirmation; no tag/release |

Old A/B/C evidence remains useful only within its original scope. The
[impact review](HISTORICAL_EVIDENCE_IMPACT.md) explains what needs a new run.
Failure evidence is retained; a repaired run is a separate recheck. After cutover
has new writes, preserve the new database before reverting to an older snapshot;
that revert cannot be called lossless.

## Operator handoff — execute one item at a time

All rows are PENDING. Return redacted output, actual time and outcome; retain
failures separately from rechecks. Never return private keys, tokens, full client
URIs, raw credential files or secret-bearing backups.

| ID | Operator action | Return / pass criterion |
| --- | --- | --- |
| T01 | Identify actual Controller host, executable/version, Workspace path, seven target aliases and recoverable canary | OS/runtime, exact paths, known Node versions/roles, admin/observe credential mode, recovery-console availability; unknown values may remain unknown until read-only discovery |
| T02 | With supplied target-specific read-only commands, collect identity/capabilities, OS, services, storage and current proxy baseline | Actual versions and identities, service state, disk/DB sizes, redacted baseline; no installation or configuration changes |
| T03 | After revised RC is frozen, verify packages and create/verify consistent backups; rehearse necessary schema migration on copies | Digests, backup paths and verification results, retained identities/cursors/totals, reserve space; original DB unchanged by rehearsal |
| T04 | In the agreed canary window, install/migrate to 0.5.5 and rehearse recovery; then stage remaining nodes | Real client probes, identity/profile/accounting comparisons, downtime series and recovery evidence; stop rollout on failure |
| T05 | Exercise admin/observe separation, Agent selectors, revocation and accountd identity | Allowed reads succeed; denied actions fail without fallback; restore access and verify proxy service |
| T06 | Check sync, UTC/day totals, history coverage and cache capacity failure/recovery on isolated copies | Node/Fleet comparisons, refused-page cursor preservation, readable existing history; never deliberately fill production disks |
| T07 | In the canary window, separately inject sing-box/accountd and SSH/Controller outages | Before/fault/recovery timelines, continuous real probes, Findings recovery; Controller outage at least five minutes |
| T08 | Apply and revert controlled listener/unit/config drift, then verify observation-only behavior | Drift detected and restored to MATCH; effective Inspect evidence, hashes/mtime/restart counts, proxy continuity |
| T09 | Keep seven 0.5.5 Nodes available for fixed-RC continuous 24h soak; run/revalidate separate ten-node 2h synthetic matrix | Start/end times, immutable inputs, proxy/Inspect/cache evidence and raw log hashes; no splicing runs |
| T10 | Review H05-01..08 evidence, limits and remaining defects | Explicit human verdict and time; no automatic PASS, merge, tag or release |

The code owner handles local support-boundary closure, affected regression,
packaging/freeze and evidence review. T01/T02 may proceed while that work is
pending; production cutover and the final soak depend on the new frozen RC.
