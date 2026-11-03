# Deferred field work — user decision, 2026-11-03

Status: **DEFERRED USER / PENDING LIVE / PENDING HUMAN**. The user reported that
the formal Controller/Workspace is currently unavailable and asked to skip this
part, record the work and resume later. No current Node was contacted, upgraded,
restarted or fault-injected. No H05 decision or main merge was performed.

Resume owner: the user/operator supplies the actual Controller environment and
portable Workspace path. No credential needs to be pasted into chat. The code
owner prepares the exact action/evidence/recovery sheet; the user confirms the
named production window and makes the final H05 judgment.

| Order | Follow-up | Required completion evidence |
| --- | --- | --- |
| 1 | Locate formal Controller, Workspace and machine-local bindings/cache; confirm seven actual targets and OS/version/roles | Redacted inventory, independent identity/capability checks and read-only fingerprints; preserve prerelease version strings |
| 2 | Verify frozen package SHA/epoch; take and validate consistent backups; rehearse schema-5 conversion on a separate copy | IDs/generations/export sequences/cursors preserved, UTC/day totals reconciled, legacy range and deleted-history uncertainty explicit, enough migration/journal space |
| 3 | Select recoverable canary and exact maintenance window | Concrete target, affected service/action, impact, backup paths/readback, stop criteria and recovery commands approved before any production mutation |
| 4 | Canary then staged upgrade; two supported source-version upgrade/rollback proofs | Real client profile/identity/accounting preservation, actual permissions, successful restore and measured new-connection unavailability upper bound <=3s |
| 5 | H05-02..07 permissions, Agent keys, observer, accountd, proxy/accounting separation, SSH/Controller outage, Finding and Drift/Inspect | Separate before/fault/recovery records, actual proxy probes and effective Inspect data, zero unintended writes on observation-only paths |
| 6 | Seven real nodes plus the independently recorded ten-node synthetic matrix; continuous >=24h integrated new RC soak | Fixed inputs, real UTC/monotonic window, real proxy, Inspect/Drift, cache growth/stop/recovery and raw log hashes; no duration stitching |
| 7 | One-page H05-01..08 review and explicit human PASS | Acceptor/time/signature, scale deviation, known limits, all required evidence and deferred backlog |
| 8 | Final PR #13 title/body, undraft and merge-commit checks | Final head/base/seven CI checks, preserved history, main CI/version/docs confirmation; no tag/release |

Old A/B/C evidence remains useful only within its original scope. The
[impact review](HISTORICAL_EVIDENCE_IMPACT.md) explains what needs a new run.
Failure evidence is retained; a repaired run is a separate recheck. After cutover
has new writes, preserve the new database before reverting to an older snapshot;
that revert cannot be called lossless.
