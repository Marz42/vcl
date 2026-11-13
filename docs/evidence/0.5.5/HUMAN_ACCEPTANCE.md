# H05 — 0.5.5 candidate

**2026-11-13 current PR #15 candidate & entry:** PR #15
(`review/0.5.5-upgrade-preparation`) consolidates PR #13's final
support-boundary evidence (`86f292b`, zero runtime delta since `21aba22`),
completes remaining `4651064..21aba22` code diff review (0 defects, no extra
generalized stress tests), and freezes runtime commit
`21aba22157994d70bfcf2c17c1ec4ff38b9e9880` as the **FROZEN acceptance RC**
(Node `7b7a1b60d5dfa228291b3b99ac2dd87afd97c22d22d86f9d7732c86157b63c4b`,
Controller `784ca4d0ef6e8181d683ab6f8ee998e216038cbf789c257c7dd50936394c7892`,
`SOURCE_DATE_EPOCH=1794384920`; [RC_FREEZE_21ABA22.md](RC_FREEZE_21ABA22.md),
[REVIEW4_FIXES.md](REVIEW4_FIXES.md), [review-artifacts/](review-artifacts/README.md)).
Support-boundary offline freeze (`4651064`, CI `42531836471`,
[SUPPORT_BOUNDARY_CANDIDATE_FREEZE.md](SUPPORT_BOUNDARY_CANDIDATE_FREEZE.md))
and the 10-node 2h synthetic matrix ([SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.md](SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.md))
are included; its 17 observation/fixture/runner inputs match `21aba22`/HEAD
17/17 with 0 mismatches. Read-only live inventory is in
[LIVE_PREFLIGHT_CHECKLIST.md](LIVE_PREFLIGHT_CHECKLIST.md). Use
[current operator sequence](LIVE_FOLLOWUP.md) and [SUMMARY.md](SUMMARY.md).

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

Current PR #15 frozen acceptance RC: runtime `21aba22`, Node `7b7a1b60…`,
Controller `784ca4d0…`, epoch `1794384920` ([RC_FREEZE_21ABA22.md](RC_FREEZE_21ABA22.md),
[REVIEW4_FIXES.md](REVIEW4_FIXES.md)).
Historical candidate records (do not substitute for `21aba22`):
[support-boundary freeze](SUPPORT_BOUNDARY_CANDIDATE_FREEZE.md) (`4651064`, Node
`38336240…`, Controller `e2daaaf…`, epoch `1793689859`) and
[original candidate record](CANDIDATE_FREEZE.md) (`653f7dd`, Node `38336240…`,
Controller `14312b21…`, epoch `1793689859`).
Do not substitute the old 26h33m record for the new candidate's missing dimensions.
Before mutation, prepare actual targets/window, backups, readback and recovery
steps for user review. Stop on failure; retain raw failures and a separate recheck.

Human acceptor: **not supplied**. UTC date: **not supplied**.
Conclusion/signature: **not signed**. Main merge remains unperformed until PASS.
