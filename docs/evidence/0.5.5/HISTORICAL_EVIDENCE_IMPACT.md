# Earlier A/B/C evidence and the 0.5.5 candidate

Earlier measurements keep their original candidate, dates, failures and scope.
They remain supplementary evidence; they do not sign H05 for 0.5.5.

| Earlier evidence | What remains useful | Changes requiring new evidence |
| --- | --- | --- |
| [A: isolated Controller](../0.5.3/PHASE_A_CONTROLLER.md), `e024d12` / 0.5.3 | Real export-v2 pagination, million-row backlog, committed-page recovery, output/time budgets, original authentication failures and production fingerprints | New content-addressed selectors and explicit observe refs; schema-5 UTC conversion and legacy isolation; initialization lock budget, capacity floor/page limit and archive import. Repeat on a verified cache copy, not the production cache. Old throughput is not a 0.5.5 performance measurement. |
| [B: seven mixed real nodes](../0.5.3/PHASE_B_FLEET.md), 10h45m | Original mixed-version topology, unsupported-capability behavior, measured samples and read-only side-effect comparisons. The later correction of the collector stop-time artifact remains valid. | Recheck actual identities, explicit admin/observe bindings, >10 Agent-key selection on Windows/Linux, capability negotiation, cache migration and independent UTC totals. The old two authentication blind spots are not closed by a new offline test. |
| [C: burst and continuous observation](../0.5.3/SOAK.md), 26h33m | The actual 1,000-read burst, old service/RSS/FD measurements, old continuous duration and reported recovery remain historical facts. | New credentials, accounting, schema and capacity boundaries require a new continuous >=24h RC window. Old proxy probes were absent and Inspect had no data; the new window must contain real client proxy results and effective Inspect/Drift evidence. Never add separate windows to manufacture continuous duration. |

The approved scale is seven real nodes plus >=10 simulated nodes for two actual
hours. A synthetic scheduler exercise can close only the simulated dimension;
it does not prove real SSH/SCP, proxy, observer/accountd permissions, migration
on a real Node, or <=3s upgrade/rollback interruption.

The synthetic run started from `37f45dc`. Its report retains that source commit
and hashes of the observation modules, fixture factory and runner. Later storage,
UTC-reader and packaging fixes are outside those inputs. Reuse for the final
candidate requires exact equality of every recorded input hash, recorded with
the completed report; it is not a new whole-candidate live soak.
