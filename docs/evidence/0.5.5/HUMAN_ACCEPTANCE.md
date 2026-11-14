# H05 — 0.5.5 candidate

**2026-11-14 current PR #15 status:** Prior `21aba22` frozen RC (`Node 7b7a1b60…`,
`Controller 784ca4d0…`) stopped cleanly at Batch 0 `fresh050` canary checkpoint
(`load_vincula_common()` loaded installed `0.5.0` common ahead of staged `0.5.5`,
`migrate_started=false`; [RC_FREEZE_21ABA22.md](RC_FREEZE_21ABA22.md)). PR #15
now applies the `bin/vincula` staged-library & embedded `upgrade-rollback-common.sh`
fix, updated `release.lock`, and regression tests in `tests/test_checkpoint_integrity.py`.
New RC artifacts built from this fix commit (`SOURCE_DATE_EPOCH` pinned to commit
timestamp) await Linux `build-release.sh` / `build-controller.sh` verification +
CI before re-running Batch 0. Live preflight & weekend schedule:
[LIVE_PREFLIGHT_CHECKLIST.md](LIVE_PREFLIGHT_CHECKLIST.md) · [LIVE_FOLLOWUP.md](LIVE_FOLLOWUP.md) ·
[SUMMARY.md](SUMMARY.md).

2026-11-08 scope revision supersedes the earlier deferral/mixed-version and
two-source requirements below: preparation resumed, minimum supported Node
0.5.5, seven real 0.5.5 Nodes, only actual required one-time ingress/recovery
paths. H05-07 covers that cutover and unsupported-version handling rather than
maintaining old Nodes. Traffic Policy is deferred to 0.6.x. All live results
remain pending. The historical digests below identify earlier candidates, not
the current PR #15 review-4 build.

**PENDING HUMAN / NOT SIGNED.** No Live actions have been executed for this
candidate by this implementation run. Technical/CI results are separate in
[SUMMARY](SUMMARY.md). Authority: [H05 checklist](../../plans/VCL_0.5-0.7_Human_Acceptance.md).

2026-11-03 user decision: the formal Controller/Workspace is currently
unavailable; skip field work for now and retain it as a follow-up. See
[field follow-up](LIVE_FOLLOWUP.md). This defers execution, not the H05 PASS
requirement before main merge.

Approved scale deviation: seven real mixed-version nodes plus at least ten
simulated nodes for two actual hours, replacing the old ten-real-node default.
This does not waive real proxy, inspect/drift, permissions or new RC 24h soak.

| Case | Required evidence | Actual result / operator / time |
| --- | --- | --- |
| H05-01 facts and scale | independent CLI/UI/inventory, real proxy, seven real nodes, ten-node simulated 2h | PENDING LIVE; support-boundary synthetic 10-node 7,200.0056s (2,401 samples, 0 errors) PASS OFFLINE, 17/17 input hashes match `4651064` & `21aba22` |
| H05-02 credentials and permissions | actual Windows/Linux SSH/SCP, >10 Agent keys, migration/selector isolation, observer deny/revoke, accountd de-root | PENDING LIVE |
| H05-03 proxy/accounting separation | selected sing-box/accountd fault and recovery with continuing real client traffic | PENDING LIVE |
| H05-04 SSH/Controller outage | selected SSH block/restore, Controller off >=5m; state transitions and real traffic | PENDING LIVE |
| H05-05 Findings/Timeline | real anomaly/normal comparison, service disruption, gap/corrupt evidence mapping | PENDING LIVE |
| H05-06 Drift/read-only | inspect-capable Node, accepted baseline, listener/config/unit change and recovery; hashes/mtime/restarts and real proxy comparison | PENDING LIVE |
| H05-07 upgrade compatibility | two supported sources, canary migration/rollback, identity/profile/accounting preservation, <=3s measured new-connection bound | PENDING LIVE |
| H05-08 integrated closeout | fixed new RC >=24h, capacity/retention/corruption boundaries, manuals, risk/deferred-work review | PENDING LIVE / PENDING HUMAN |

Current PR #15 fix candidate: `bin/vincula` staged-library & rollback-common fix
with updated `release.lock` (awaiting Linux rebuild verification & CI;
`SOURCE_DATE_EPOCH` pinned to the fix commit timestamp).
Historical / superseded records (do not substitute for the rebuilt RC):
[21aba22 RC freeze / canary abort](RC_FREEZE_21ABA22.md) (`21aba22`, Node
`7b7a1b60…`, Controller `784ca4d0…`, epoch `1794384920`),
[support-boundary freeze](SUPPORT_BOUNDARY_CANDIDATE_FREEZE.md) (`4651064`, Node
`38336240…`, Controller `e2daaaf…`, epoch `1793689859`) and
[original candidate record](CANDIDATE_FREEZE.md) (`653f7dd`, Node `38336240…`,
Controller `14312b21…`, epoch `1793689859`).
Do not substitute the old 26h33m record for the new candidate's missing dimensions.
Before mutation, prepare actual targets/window, backups, readback and recovery
steps for user review. Stop on failure; retain raw failures and a separate recheck.

Human acceptor: **not supplied**. UTC date: **not supplied**.
Conclusion/signature: **not signed**. Main merge remains unperformed until PASS.
