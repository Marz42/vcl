# Vincula 0.3.1 Release Readiness

**Tree version:** `0.3.1` (stable).  
**Date:** 2026-08-20  
**Companion:** [`known-issues-0.3.1.md`](known-issues-0.3.1.md) · Evidence: [`evidence/0.3.1-final/SUMMARY.md`](evidence/0.3.1-final/SUMMARY.md) · Spec: [`specs/V0.2.7-V0.3.1_spec.md`](specs/V0.2.7-V0.3.1_spec.md)

Frozen-tag / historical gates: [`legacy/`](legacy/) (read-only). RC evidence retained under [`evidence/0.3.1-rc2/`](evidence/0.3.1-rc2/) and [`evidence/0.3.1-live/`](evidence/0.3.1-live/).

## Release recommendation

```text
Release recommendation: READY
Known P0: 0
Known P1 release blockers: 0
```

**Waivers (documented, non-blocking):**

- True live **`0.3.0 → 0.3.1`** upgrade not run; **B22** `0.3.1-rc1 → 0.3.1-rc2` accepted as surrogate (fixtures cover 0.3.0 allowlist).
- **B24** rc2 replace regression smoke **deferred**; full **B14** live replace remains **PASS**.

## Gate matrix (B18–B28)

| ID | Result |
| --- | --- |
| B18 Schema 4 installer health | **PASS** |
| B19 rc2 scope freeze / tag | **PASS** (`v0.3.1-rc2`) |
| B20 CI + artifact build | **PASS** |
| B21 fresh install live | **PASS** |
| B22 live upgrade (rc1→rc2 surrogate) | **PASS** |
| B23 Schema 4 Fleet re-sync | **PASS** |
| B24 replace regression smoke | **DEFERRED** (Known Issue) |
| B25 documentation consistency | **PASS** |
| B26 branch protection | **PASS** |
| B27 final artifact black-box | **PASS** — [`evidence/0.3.1-final/`](evidence/0.3.1-final/) (CI digests frozen) |
| B28 tag `v0.3.1` + GitHub Release | **PASS** — tag + assets match SUMMARY digests |

## Earlier living-tree closures

B14 live replace **PASS**. B15 UI **implemented**. B17 restore/sync fail-close **CLOSED**. Schema 4 / Export Protocol v2 **on tree**. Known P0: **0**.

## Upgrade contract

`vincula.sh` migrates `0.1.0–0.1.5`, `0.2.0–0.3.0`, `0.3.1-dev`, `0.3.1-rc1`, and `0.3.1-rc2` → **`0.3.1`**. Same-architecture: no remint of `node_id` / `instance_id`; no credential/Reality rotation; accounting schema **3→4** on open when upgrading from pre-Schema-4.

## Operator docs

[`manual.md`](manual.md) · [`fleet.md`](fleet.md) · [`backup.md`](backup.md) · [`identity.md`](identity.md) · [`live-replace-checklist.md`](live-replace-checklist.md)

## Post-release policy

Tag `v0.3.1` and published digests are **immutable**. Defects → `0.3.2` hotfix or `0.4.x` development — do not move this tag or replace release assets.
