# 0.4.4 Local Audit UI v2 (D53-rev1) — DoD SUMMARY

**Milestone:** Local Audit UI **v2 belongs to controller 0.4.4** (not deferred to 0.4.5+).
**Stamp:** CTRL `0.4.4` / NODE `0.3.1` · **Gate:** offline `bash tests/test.sh` + `bash tests/test-fleet.sh`
**Spec:** [`../../specs/V0.4.4_ui_v2.md`](../../specs/V0.4.4_ui_v2.md) · **Rev1 roadmap:** [`../../specs/vcl-spec-v0.4-v0.5-rev1.md`](../../specs/vcl-spec-v0.4-v0.5-rev1.md) §16
**Hand-test:** [`../../manual.md#ui-manual-test`](../../manual.md#ui-manual-test)

| AC | Result | Evidence |
| --- | --- | --- |
| **4.4-01** | **PASS** | `api_sync` → `run_sync_full_payload`; `operation=sync_full`; concurrent sync lock |
| **4.4-02** | **PASS** | PARTIAL exit 2 → `ok=false`, `operation=sync_full` (UI API + toast) |
| **4.4-03** | **PASS** | Recipes parse via `build_parser()`; archive restore positional `out.vclaudit`; workspace export positional `fleet.tgz` |
| **4.4-04** | **PASS** | Empty Nodes/Overview copy → adopt/provision; static grep |
| **4.4-05** | **PASS** | `read_only_workspace_surface` five states; malformed `workspace.json` → `WORKSPACE_INCONSISTENT` (not absent); GET never mkdir; UI migrate fail-closed (no `<workspace>/ui-runtime`) |
| **4.4-06** | **PASS** | recipes/meta JSON grep: no secrets; UI `has_active_credential` bool only; users-cache in `ui-runtime` (legacy Fleet Home migrated + deleted) |
| **4.4-07** | **PASS** | AC-3.1 UI fixture block green (six-page nav) |
| **4.4-08** | **PASS** | Probe live overlay; GET `/api/nodes` stays cache; no `last-status.json` write |
| **4.4-09** | **PASS** | GET `/api/operations` lists UI-triggered probe/sync with visible `time`; Probe/Verify/Sync share `confirmRemoteSsh` |
| **4.3-05** | **PARTIAL** | List pages cover day-to-day reads (Overview KPIs/trend; Nodes users/traffic/endpoint; Users dept/enabled/today/30d; Traffic filters+**filtered** trend; Audit IP/port/network). Gaps vs full §16 drawers: Node Detail does not yet render Instance History / recent usage tables; User Detail lacks destinations; Operations history is **UI-triggered only** (not CLI provision/adopt/replace/user.add/rotate/backup/restore) |
| **4.3-06** | **PASS** | Command Builder POST builds argv + `shlex.join` (spaces / quotes / `;` / backticks / `$()` safe); host / host_key / nodes validated |

## Notes

- Controller-only; Node `0.3.1` unchanged.
- Six pages: Overview / Nodes / Users / Traffic / Audit / Operations.
- D57 observe≠admin and `node add` deprecation warnings remain **0.5+**.
- Test gate isolates `HOME` / `XDG_CONFIG_HOME` under `TEST_TMP` through suite teardown.
- LIVE optional (no new LIVE AC required for UI v2).

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.4.4"`.
- Node: `VINCULA_VERSION="0.3.1"` unchanged.
