# Vincula 0.3.1-rc2 Release Readiness

**Tree version:** `0.3.1-rc2` (living tree).  
**Date:** 2026-08-20  
**Focus:** Living-tree gate toward stable `v0.3.2`; **B18** Schema 4 installer health; B17 restore/sync; **B14 live replace PASS**; **B15 UI**; Schema 4 / Export Protocol v2. **Feature freeze after B18.**  
**Companion:** [`known-issues-0.3.1.md`](known-issues-0.3.1.md) · Operator: [`backup.md`](backup.md) · [`fleet.md`](fleet.md) · Live replace runbook: [`live-replace-checklist.md`](live-replace-checklist.md) · Spec: [`specs/V0.2.7-V0.3.1_spec.md`](specs/V0.2.7-V0.3.1_spec.md) §7 / §9.3 / §9.4 / §10.

This is the **living-tree gate** for `0.3.1-rc2` (**`0.3.1-rc1` superseded** — see B18). It is **not** a continuation or rewrite of the 0.3.0 freeze record. Frozen-tag evidence stays in [`legacy/release-readiness-0.3.0.md`](legacy/release-readiness-0.3.0.md) / [`legacy/known-issues-0.3.0.md`](legacy/known-issues-0.3.0.md) (read-only). Older gates: [`legacy/`](legacy/).

## Release recommendation

**NOT READY** (B14 live evidence **PASS**; B15 UI **implemented**; Schema 4 / Protocol v2 on tree; **B18 Schema 4 health mismatch closed**; live upgrade + live re-sync after Schema 4 still open)

**B14** (two-VPS secretless replace + AC-3.0-11 + real `age` + Win11 `vcl-fleet.cmd`) is **PASS** — see [`evidence/0.3.1-live/SUMMARY.md`](evidence/0.3.1-live/SUMMARY.md). Fixture-green replace alone is still not sufficient; this live log is.

Known P0 on this tree: **0** (including prior live sync AUTOINCREMENT / open-row freeze, closed by Schema 4 + Protocol v2 in fixtures). Remaining NOT READY: live **`0.3.0 → 0.3.1-rc2` upgrade** evidence, deferred **P1-05** branch protection, and at least one live Fleet re-sync after Schema 4 + `--reseed`. **B15** Local Audit UI (`vcl-fleet ui`) is on the tree with AC-3.1 fixture coverage; it does **not** by itself make the release READY FOR RC.

## B18 — rc1 postmortem / Schema 4 health (PASS)

**Root cause:** `0.3.1-rc1` shipped `SCHEMA_VERSION = 4` in `vincula-accountd.py`, but `wait_for_accountd_healthy` in `vincula.sh` still required `meta.schema_version == "3"`. Fresh install created a healthy schema-4 DB, failed the health gate, and refused to commit install.

**Fix:** Installer health expects schema **4** (commit `a991774` on the rc1 line; carried into rc2). Schema **3** remains only as migration input (`migrate_schema_3_to_4`) and historical fixtures — not as a runtime health expectation.

**Regression:** `tests/test.sh` asserts installer/`SCHEMA_VERSION`/audit agree on 4 and that runtime paths do not expect accounting schema 3.

**Gate note:** **`0.3.1-rc1` is superseded** for fresh install. Prefer `0.3.1-rc2` artifacts.

## B19 — Scope freeze (`0.3.1-rc2`)

**Feature freeze** starts at tag `v0.3.1-rc2`. Living verification (B20+) must use **one immutable** node/controller artifact pair built from that tag.

Allowed after freeze:
- P0/P1 defect fixes
- release-blocker fixes
- tests / live evidence
- documentation consistency
- release-engineering (locks, digests, packaging)

Not allowed without a **new RC** (`0.3.1-rc3`+):
- new UI / Fleet features
- REALITY/SNI tuning
- large refactors
- new protocols / schemas
- other planned 0.4 work

Policy: **do not mutate** the `v0.3.1-rc2` tag or overwrite published `vincula-node-0.3.1-rc2.*` / `vincula-controller-0.3.1-rc2.*` digests. Fixes ship as a new RC (or stable `0.3.2` only after all live gates PASS).

## Closed on this living tree

| ID | Contract | Status |
| --- | --- | --- |
| **B20** | CI matrix (ubuntu + Debian 12/13) + node/controller artifacts + black-box zip | **PASS** (local equivalent; GitHub Actions on push) |
| **B19** | Version sources + allowlist unified at `0.3.1-rc2`; immutable tag + freeze policy | **PASS** (tag `v0.3.1-rc2`) |
| **B18** | Installer / verify / audit runtime health tracks accounting schema **4**; no residual “expect schema 3” on health paths | **PASS** |
| **B14** | Live secretless replace on two VPS + AC-3.0-11 + Win11 `vcl-fleet.cmd` + real `age` | **PASS (2026-08-18).** Evidence: [`evidence/0.3.1-live/`](evidence/0.3.1-live/). Runbook: [`live-replace-checklist.md`](live-replace-checklist.md). |
| **B15** | Localhost Audit UI (`vcl-fleet ui`): Overview / Audit / Health; loopback-only; read-only + SSH refresh/sync; CLI recipes for mutations | **Implemented.** Fixture AC-3.1 in `tests/test-fleet.sh`. |
| **P1-01 / P1-02** | Restore is a single final commit. systemd + accountd fail-close before VERSION. Unique public JSON. Fleet mutations require remote `rc=0` and JSON `ok:true`. Rollback that cannot restore service state is `rollback_partial`. | **CLOSED** (B17) |
| **P1-03** | Audit sync fail-close: export meta/rows must carry matching `node_id` (and `instance_id` when expected). Unlabeled rows fail the batch; cursor unchanged. `--reseed` is the only stamp path (`vcl audit export --stamp-identity`). | **CLOSED** (B17) |
| **P1-04** | Installer allowlist includes `0.3.0`, `0.3.1-dev`, `0.3.1-rc1` (excludes `0.3.0-dev` / `0.3.1-rc2`). Fixture keep tests cover identity, credentials, Reality, accounting, dual-service. | **CLOSED** (fixture). Live upgrade still open (below). |
| **P2-01** | Version-boundary rollback restores `.runtime-only` from safety / journal. | **CLOSED** (B17) |
| **P2-02** | CI actions pinned to full commit SHA; unused top-level `actions: write` removed; Dependabot for GitHub Actions. | **CLOSED** (B17) |
| **P2-03** | This file + [`known-issues-0.3.1.md`](known-issues-0.3.1.md); README gate links and `<version>` artifacts; CHANGELOG B17. | **CLOSED** (B17) |
| **Schema 4 / Protocol v2** | `export_seq` cursor; closed-only export; Fleet UPSERT + `CURSOR_*` / `--reseed` | **On tree** (fixture-green). Live re-sync still open (below). |

Earlier living-tree batches (B0–B13, B16) remain in force: replace uses real `vcl restore` argv, controller zip ships audit/backup, mutex, CURSOR_AHEAD, streaming backup, bootstrap pin, GitHub Actions merge gate. See the 0.3.0 freeze record in [`legacy/`](legacy/) for freeze-era AC matrices; do not treat those addenda as 0.3.1 evidence.

## Still open (blocks READY FOR RC)

| ID | Why it blocks READY FOR RC |
| --- | --- |
| **Live 0.3.0 → 0.3.1-rc2 upgrade** | Allowlist + keep tests are fixture-only. No RC-host upgrade run this round. After upgrade: accounting migrates 3→4 on open; run `vcl-fleet sync --reseed NAME` once per node (Protocol mismatch), then normal sync. |
| **Schema 4 live re-sync** | Fixture green for `export_seq` / UPSERT / CURSOR_* . Live two-node re-sync after Schema 4 still required before READY FOR RC. |
| **P1-05 branch protection** | GitHub `main` protection deferred (operator pause). Workflow exists; settings not enforced. |

## Restore contract (B17)

Public `vcl restore --json` emits **one** object, and only after VERSION is committed:

1. Python `apply_restore` stages files with VERSION pending (stdout captured; not public).
2. Shell: `daemon-reload`; `enable --now` **both** `sing-box.service` and `vincula-accountd.service`; `is-enabled` / `is-active` for both; `wait_healthy`.
3. `commit-version` last.
4. Any failure: rollback, no VERSION, unique `{"ok":false,...}`, non-zero exit.

Controller mutate SSH (`restore`, `backup create`, `user add` / `rotate` / `enable` / `disable`) requires remote **exit 0** and JSON `ok is True`. Reads keep “255 = SSH fail, else JSON”.

## Audit sync contract (B17)

Normal `vcl-fleet sync` refuses unlabeled or mismatched identity; cursor does not advance. Remediation is `vcl-fleet sync --reseed NAME`, which asks the node for `--stamp-identity` (fills **missing** row identity only; does not write `accounting.db`).

## Upgrade contract (B17)

`vincula.sh` migrates `0.1.0–0.1.5`, `0.2.0–0.3.0`, **`0.3.1-dev`**, and **`0.3.1-rc1`** to `0.3.1-rc2`. Spec §9.4 treats `0.3.0 → 0.3.1` as a same-architecture milestone: no remint of `node_id` / `instance_id`, no credential UUID rotation, Reality keys unchanged; accounting migrates schema 3→4 on open.

## Verification this round

- `bash tests/test.sh` — **1280** passed on WSL host (includes B18 schema-health regressions + fleet); **1279** passed in Debian 12 / Debian 13 / Ubuntu containers (writable tree copy; build tests need write)
- `bash tests/test-fleet.sh` — **521** passed standalone (includes AC-3.1 UI subset)
- `bash -n` + `python3 -m py_compile` on first-party node/controller files
- `bash scripts/gen-release-lock.sh` + `vincula.sh.sha256` match tagged tree
- **B19:** annotated tag `v0.3.1-rc2` @ `63755b5`; freeze policy above
- **B20:** local matrix + artifact black-box PASS; GitHub Actions [32329621883](https://github.com/Marz42/vcl/actions/runs/32329621883) **success** (all jobs)
