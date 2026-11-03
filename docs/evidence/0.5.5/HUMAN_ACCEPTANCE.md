# H05 — 0.5.5 candidate

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
| H05-01 facts and scale | independent CLI/UI/inventory, real proxy, seven real nodes, ten-node simulated 2h | PENDING LIVE; synthetic ten-node 7,200s PASS OFFLINE, 17 input hashes match |
| H05-02 credentials and permissions | actual Windows/Linux SSH/SCP, >10 Agent keys, migration/selector isolation, observer deny/revoke, accountd de-root | PENDING LIVE |
| H05-03 proxy/accounting separation | selected sing-box/accountd fault and recovery with continuing real client traffic | PENDING LIVE |
| H05-04 SSH/Controller outage | selected SSH block/restore, Controller off >=5m; state transitions and real traffic | PENDING LIVE |
| H05-05 Findings/Timeline | real anomaly/normal comparison, service disruption, gap/corrupt evidence mapping | PENDING LIVE |
| H05-06 Drift/read-only | inspect-capable Node, accepted baseline, listener/config/unit change and recovery; hashes/mtime/restarts and real proxy comparison | PENDING LIVE |
| H05-07 upgrade compatibility | two supported sources, canary migration/rollback, identity/profile/accounting preservation, <=3s measured new-connection bound | PENDING LIVE |
| H05-08 integrated closeout | fixed new RC >=24h, capacity/retention/corruption boundaries, manuals, risk/deferred-work review | PENDING LIVE / PENDING HUMAN |

Candidate source commit/digests: [fixed candidate record](CANDIDATE_FREEZE.md),
source `653f7dd`, Node `38336240…`, Controller `14312b21…`, epoch `1793689859`.
Do not substitute the old 26h33m record for the new candidate's missing dimensions.
Before mutation, prepare actual targets/window, backups, readback and recovery
steps for user review. Stop on failure; retain raw failures and a separate recheck.

Human acceptor: **not supplied**. UTC date: **not supplied**.
Conclusion/signature: **not signed**. Main merge remains unperformed until PASS.
