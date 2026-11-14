# 0.5.5 Acceptance RC Freeze (`21aba22`) — SUPERSEDED (2026-11-14 Batch 0 Abort)

> [!WARNING]
> **SUPERSEDED BY PR #15 BATCH 0 FIXES (2026-11-14):**
> - **Attempt 1 (`21aba22` / `7b7a1b60…`):** Aborted cleanly in `phase=checkpoint` (`PREPARATION_FAILED`, `migrate_started=false`, `retry_allowed=false`): staged `bin/vincula` `load_vincula_common()` preferred installed `0.5.0` `/usr/local/lib/vincula/vincula-common.sh` ahead of `<staged>/lib/vincula-common.sh`, causing `python_private: command not found`. Fixed in `7627f45` (sibling library preference, embedded `upgrade-rollback-common.sh`, unified `_resolve_lib_py()`, updated `release.lock` & `tests/test_checkpoint_integrity.py`); Controller `fleet.db` remained cleanly migrated at schema 5 (`quick_check=ok`, `3.80 GB`).
> - **Attempt 2 (`7627f45`):** Checkpoint succeeded cleanly, then `install` failed after `75.7s` at `wait_for_accountd_healthy()` (`15s` cap too short for `609 MB` `accounting.db` schema-4→5 `staged_migrate`), and `rollback_migration()` left `/var/lib/vincula` owned by `vincula-accountd:vincula-accountd 0700` while holding `sing-box` down during the `609 MB` DB copy (`4.06s` probe outage). Fixed in follow-up commit (`vincula.sh`, `bin/vincula`, `lib/vincula-accountd.py`, `lib/storage_v5.py`, `lib/node_upgrade.py`, `lib/vincula-fleet.py`, `release.lock`, and regression tests).

- **Frozen At:** 2026-11-13 (Superseded 2026-11-14)
- **Status:** `HISTORICAL / SUPERSEDED AT CANARY CHECKPOINT`
- **PR / Branch:** PR #15 (`review/0.5.5-upgrade-preparation`)
- **Runtime Source Commit:** `21aba22157994d70bfcf2c17c1ec4ff38b9e9880` (`21aba22`)
- **Evidence / Freeze Policy:** Historical freeze & failure records are preserved verbatim; new RC builds from PR #15 HEAD with `SOURCE_DATE_EPOCH` pinned to the fix commit timestamp (`git log -1 --pretty=%ct`) and must be verified on Linux (`build-release.sh` / `build-controller.sh`) + CI before re-running Batch 0.

## 1. Remaining Code Diff Review (`4651064..21aba22`)

Reviewed all 13 non-docs files changed between `4651064` and `21aba22` (`0` P0/P1/P2 defects found):

- **Runtime & build (7 files):**
  - `lib/upgrade_prepare.py` (lines 1–648): `CLONE_NEWPID`/`CLONE_NEWNS` lifecycle isolation, `PR_SET_PDEATHSIG` cleanup, monotonic `VCL_PREPARE_DEADLINE_MONO`, deadline-guard `ENOSPC` resilience, `read_status()` post-lock convergence, and pinned-fd backup verification.
  - `lib/node_upgrade.py` (lines 1–572): typed `UPGRADE_ALLOWLIST` (`0.3.1`, `0.3.2`, `0.5.0`, `0.5.1`, `0.5.2`, `0.5.3` -> `0.5.5`, excluding prereleases such as `0.3.1-rc2`), `preserve_stage` fail-closed handling, and `_attempt_post_upgrade_rollback` preflight via `--verify-only` before live service stop/mutation.
  - `bin/vincula` (`resolve_backup_py()`, `cmd_upgrade_checkpoint` manifest written last, `cmd_upgrade_rollback --verify-only` preflight).
  - `lib/vincula-backup.py`: WAL-only `snapshot_sqlite()` pinned read transaction, `_verify_archive_stream` / `verify_archive_fd`, `_check_archive_unchanged()` size/mtime validation, `_stream_created_tar`.
  - `scripts/build-release.sh`, `scripts/gen-release-lock.sh`, `release.lock`.
- **Tests & fixtures (6 files):**
  - `tests/test_checkpoint_integrity.py` (5 test cases), `tests/test_fake_upgrade_prepare.py` (1 test case), `tests/test_upgrade_prepare.py` (18 test cases), `tests/test-fleet.sh`, `tests/test.sh`, `tests/fixtures/fake-ssh`.
- **Zero runtime delta after `21aba22`:** `git diff --name-status 21aba22..HEAD -- . ':!docs/' ':!README.md'` is empty (docs/evidence consolidation only).

## 2. Frozen Fixed-Epoch Artifacts (`SOURCE_DATE_EPOCH=1794384920`)

Reuses the verified deterministic artifacts stored in [review-artifacts/](review-artifacts/README.md) built from `21aba22`:

| Artifact | SHA256 | Integrity / Contract Check |
| --- | --- | --- |
| [vincula-node-0.5.5.tar.gz](review-artifacts/vincula-node-0.5.5.tar.gz) | `7b7a1b60d5dfa228291b3b99ac2dd87afd97c22d22d86f9d7732c86157b63c4b` | `release.lock` 20/20 match (`0` mismatches); matches `SHA256SUMS` and `BUILD_INPUTS.json` |
| [vincula-controller-0.5.5.zip](review-artifacts/vincula-controller-0.5.5.zip) | `784ca4d0ef6e8181d683ab6f8ee998e216038cbf789c257c7dd50936394c7892` | `controller.lock` 59/59 match against embedded & LF-normalized workspace files; embedded `payload/payload-manifest.json` matches Node tar `7b7a1b60...` |

- Standalone offline contract check (`python -B scripts/check-controller-artifact.py docs/evidence/0.5.5/review-artifacts/vincula-controller-0.5.5.zip`):
  - `{"state": "PASS OFFLINE", "version": "0.5.5", "schemas": 18, "cache_only_surfaces": 5, "node_cli": "NOT RUN"}` (`node_cli` verified in Linux CI `artifact` job).

## 3. Offline & CI Gate Summary

- **PR #13 Consolidated Evidence:** Cherry-picked `86f292b` (`42d1d54`). All 17 observation/fixture/runner inputs in [SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.md](SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.md) match `21aba22`/HEAD 17/17 with `0` mismatches.
- **Review-4 Test Baseline at `21aba22` ([REVIEW4_FIXES.md](REVIEW4_FIXES.md)):** Python `228/10/0`, Bash `1,970` user / `1,968` root. No additional generalized stress tests were executed.
- **GitHub Actions CI (`#139`, Run ID `43357668445` on consolidated HEAD `62975f9ab87e8bd794eccd65a5935f49b27b8ee2`):** `Success` across all 7 jobs:
  - `unit (windows-latest)`
  - `unit (ubuntu-latest)`
  - `unit (debian:12)`
  - `unit (debian:13)`
  - `concurrency`
  - `failure-injection`
  - `artifact` (+ `vincula-dist` artifact)
- *(Docs-only freeze commits after `62975f9` must keep `21aba22..HEAD` non-docs diff empty and re-pass CI before live execution.)*

## 4. Next Gates Required Before Merge / H05

Live execution preflight is documented in [LIVE_PREFLIGHT_CHECKLIST.md](LIVE_PREFLIGHT_CHECKLIST.md). **Do not mutate production nodes** until the operator confirms Controller/Workspace location, canary target, and maintenance windows:

1. **Read-only discovery (T01/T02)** & backup baseline (no node mutation).
2. **Single-node canary upgrade + recovery rehearsal** (`<=3s` new-connection outage measurement + checkpoint rollback verification).
3. **Staged fleet rollout** across remaining allowlisted nodes + operator-directed handling of `0.3.1-rc2` (`epicfury`, `upperhand`) and `urgentfury` SSH reachability.
4. **Continuous `>=24h` integrated soak** on the frozen `21aba22` RC (`7` real `0.5.5` nodes + `>=10` simulated nodes 2h deviation scope) + **H05-01..08 human signoff**.
