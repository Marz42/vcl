# Vincula 0.2.7 Release Readiness

> **(0.2.x 历史文档，命令名 vcl 已迁移为 vcl-fleet)**

**Tree version:** 0.2.7  
**Date:** 2026-08-16  
**Focus:** Stability & Audit Foundation (schema 3, durable baseline, JSONL A2, batched retention, `vcl audit`, D3 checker)  
**Companion:** [`known-issues-0.2.7.md`](known-issues-0.2.7.md) · Spec: [`specs/V0.2.7-V0.3.1_spec.md`](../specs/V0.2.7-V0.3.1_spec.md) §4 / §10 / §11 / D20.

## Release recommendation

**READY WITH DOCUMENTED LIMITATIONS**

No live 24h soak has been run. **AC-2.7-09 is missing.** Per D20 this tree must not be reported as `READY FOR RC`. Offline unit coverage for AC-2.7-01…07 and 11–15 is green; AC-2.7-08 (reboot dual-plane) is soak T+6h and is also missing live evidence.

Known P0/P1 at freeze: **0**.

## Scope delivered

| Item | Status |
| --- | --- |
| Absorb 27 post-0.2.6 commits as 0.2.7 baseline (D1) | PASS — not shipped as a forked 0.2.6 |
| Accounting schema 3 (`event_id`, `generation`, `poll_baseline`, nullable `instance_id`) | PASS (unit) |
| Durable poll baseline + generation resets (D7/D8) | PASS (unit + failure injection) |
| JSONL production ingest removed (A2) | PASS (path absent) |
| Retention DELETE batch 2000 | PASS (unit) |
| raw 90 / daily 90 + D18 (730→90 only) | PASS (unit) |
| `vcl audit` RFC3339 interval-overlap | PASS (unit); no `--csv` |
| `vcl verify` Accounting Plane D3 + `vcl accounting check` alias | PASS (offline) |
| Upgrade allowlist includes `0.2.6` | PASS (unit) |
| Product version `0.2.7` (no `-dev`) | PASS (constants + tests) |
| Live 24h soak | **MISSING** (protocol only: `scripts/soak-0.2.7.sh`) |

## Acceptance criteria (AC-2.7-01…15)

Evidence mapping follows the v0.2.7 execution plan §4. Soak items are not marked PASS from unit tests.

| ID | Criterion | Status | Evidence | Release blocking |
| --- | --- | --- | --- | --- |
| AC-2.7-01 | Restart does not re-count already-accounted bytes | **PASS** | Tasks 12–14, 26, 40. Unit: restart bytes preserved / `restart empty known_open preserves generation bytes` | YES |
| AC-2.7-02 | Unknown live connection → baseline only | **PASS** | Tasks 12, 24. First sight of unseen Clash counters accounts 0 | YES |
| AC-2.7-03 | sing-box restart: no negative or absurd delta | **PASS** | Tasks 24, 39. Counter drop opens a new generation | YES |
| AC-2.7-04 | `current < previous` → new generation (no huge-threshold heuristic) | **PASS** | Tasks 24, 39. `counter reset opens new generation without negative delta` | YES |
| AC-2.7-05 | COMMIT failure reloads cache from DB | **PASS** | Tasks 25, 38. `commit failure reloads cache from DB` | YES |
| AC-2.7-06 | Retention batched at 2000; not gated on a fleet cursor | **PASS** | Tasks 27, 41. `retention deletes at most 2000 rows per call`; `RETENTION_DELETE_BATCH = 2000` | YES |
| AC-2.7-07 | `vcl audit` interval-overlap; stats stay day-grained | **PASS** | Tasks 31–34. Audit module + CLI; no `--csv` | YES |
| AC-2.7-08 | Reboot restores proxy + accounting planes | **UNKNOWN** | Task 43 soak T+6h. Not run. Protocol in `scripts/soak-0.2.7.sh` | Blocks `READY FOR RC` (live) |
| AC-2.7-09 | Live 24h soak, no cumulative replay drift | **MISSING** | Tasks 43, 47. No host / start / end / inject log. Unit tests do not satisfy D20 | Blocks `READY FOR RC` |
| AC-2.7-10 | 0.2.6 → 0.2.7 keeps users, credentials, UUID `node_id`, accounting history | **PARTIAL** | Tasks 3–4, 28. Allowlist + schema 2→3 byte-preserve unit tests PASS. No live 0.2.6→0.2.7 upgrade run | Live upgrade is operator evidence |
| AC-2.7-11 | Schema 3 complete; closed generation not overwritten | **PASS** | Tasks 19–24, 28–30. `schema 2 to 3 preserves accounted bytes`; `instance_id` stays NULL | YES |
| AC-2.7-12 | JSONL A2: restart cannot replay ingest | **PASS** | Tasks 15–18. Collector path deleted; leftover `events.jsonl` is dirty state | YES |
| AC-2.7-13 | `vcl verify` three planes + D3; `accounting check` same checker | **PASS** (offline) | Tasks 35–37. Live Clash Bearer triad remains operator | Clash live is operator |
| AC-2.7-14 | Version `0.2.7-dev` then freeze `0.2.7` | **PASS** | Tasks 1–4, 50. Tree is `0.2.7`; allowlist still has 0.2.6 and rejects 0.2.7 | YES |
| AC-2.7-15 | raw 90 / daily 90 + D18 730→90 tests | **PASS** | Tasks 5–7. Custom daily values preserved; only legacy 730 migrates | YES |

## Migration path

| Step | Detail |
| --- | --- |
| Supported sources | `0.1.0`–`0.1.5` and `0.2.0`–`0.2.6` → **0.2.7** |
| Same version | Verify both planes; do not rotate credentials |
| Accounting schema | 2 → 3 on first 0.2.7 migrate (`event_id`, `generation=0`, `instance_id` NULL, `poll_baseline` created empty for unknown counters) |
| D18 | If source is supported **and** `accounting_daily_retention_days=730`, rewrite to 90. Custom values (e.g. 365) are kept. Raw retention is preserved (default 90) |
| Identity | Reality keys, user UUIDs, `user_id`, existing UUID `node_id` kept |
| JSONL | Not migrated as a collector (A2). A leftover `events.jsonl` is dirty state |

## Rollback

There is **no** automatic schema 3→2 downgrade.

Rollback = restore the `backup_existing_install` backup taken before migrate (core + accounting artifacts + SQLite `.backup` + `SERVICE_STATE`). Restoring a schema-2 backup onto a 0.2.7 tree that expects schema 3 is unsupported; restore the matching 0.2.6 (or earlier) installer with that backup.

## Decisions frozen in this release

| Decision | Value |
| --- | --- |
| JSONL | **A2** — production ingest path removed |
| Retention DELETE batch | **2000** |
| Existing-row `generation` | **0** |
| Schema 3 | Irreversible |
| Soak | Protocol shipped; 24h live run **not** executed |

## Explicit non-goals (0.2.7)

`instance_id` mint, fleet / SSH controller, audit `--csv`, incremental `event_id` cursor, JSONL A1, automatic schema 3→2, billing-grade accounting.

## Policy after freeze

After tag `v0.2.7`, prefer P0/P1 fixes only. A live 24h soak PASS (AC-2.7-09) is required before raising this recommendation to `READY FOR RC`. Fleet / `instance_id` mint belong in 0.2.8+.
