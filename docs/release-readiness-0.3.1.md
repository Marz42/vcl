# Vincula 0.3.1-dev Release Readiness

**Tree version:** `0.3.1-dev` (living tree).  
**Date:** 2026-08-17  
**Focus:** Restore / sync fail-close (B17): unique restore commit point, audit identity fail-close, `0.3.0` upgrade allowlist, runtime-only rollback, CI supply-chain pins.  
**Companion:** [`known-issues-0.3.1.md`](known-issues-0.3.1.md) · Operator: [`backup.md`](backup.md) · [`fleet.md`](fleet.md) · Live replace runbook: [`live-replace-checklist.md`](live-replace-checklist.md) · Spec: [`specs/V0.2.7-V0.3.1_spec.md`](specs/V0.2.7-V0.3.1_spec.md) §7 / §9.3 / §9.4 / §10.

This is the **living-tree gate** for `0.3.1-dev`. It is **not** a continuation or rewrite of the 0.3.0 freeze record. Frozen-tag evidence stays in [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md) / [`known-issues-0.3.0.md`](known-issues-0.3.0.md) (read-only).

## Release recommendation

**NOT READY**

Do **not** mark **READY FOR RC** until **B14** live two-VPS secretless replace (plus Win11 `vcl-fleet.cmd` and real `age` on the same pass) is complete. Fixture-green restore / replace / sync is not live PASS. B15 localhost UI stays deferred.

Known P0 on this tree: **0**. Remaining NOT READY is evidence (B14 / B15) plus a live `0.3.0 → 0.3.1-dev` upgrade gap, not an open restore/sync contract mismatch from B17.

## What B17 closed

| ID | Contract | Living-tree status |
| --- | --- | --- |
| **P1-01 / P1-02** | Restore is a single final commit. systemd + accountd fail-close before VERSION. Unique public JSON. Fleet mutations require remote `rc=0` and JSON `ok:true`. Rollback that cannot restore service state is `rollback_partial`. | **CLOSED** |
| **P1-03** | Audit sync fail-close: export meta/rows must carry matching `node_id` (and `instance_id` when expected). Unlabeled rows fail the batch; cursor unchanged. `--reseed` is the only stamp path (`vcl audit export --stamp-identity`). | **CLOSED** |
| **P1-04** | Installer allowlist includes `0.3.0` (excludes `0.3.0-dev` / `0.3.1-dev`). Fixture keep tests cover identity, credentials, Reality, accounting, dual-service. | **CLOSED** (fixture). Live `0.3.0 → 0.3.1-dev` upgrade is still an evidence gap. |
| **P2-01** | Version-boundary rollback restores `.runtime-only` from safety / journal. | **CLOSED** |
| **P2-02** | CI actions pinned to full commit SHA; unused top-level `actions: write` removed; Dependabot for GitHub Actions. | **CLOSED** |
| **P2-03** | This file + [`known-issues-0.3.1.md`](known-issues-0.3.1.md); README gate links and `<version>` artifacts; CHANGELOG B17. | **CLOSED** |

Earlier living-tree batches (B0–B13, B16) remain in force: replace uses real `vcl restore` argv, controller zip ships audit/backup, mutex, CURSOR_AHEAD, streaming backup, bootstrap pin, GitHub Actions merge gate. See the 0.3.0 freeze record for freeze-era AC matrices; do not treat those addenda as 0.3.1 evidence.

## Still open (not this batch)

| ID | Why it blocks READY FOR RC |
| --- | --- |
| **B14** | Live secretless replace on two VPS + AC-3.0-11 handshake + Win11 controller + real `age`. Evidence dir [`evidence/0.3.1-live/`](evidence/0.3.1-live/) is **NOT RUN**. Runbook: [`live-replace-checklist.md`](live-replace-checklist.md). |
| **B15** | Localhost Audit UI. Not started. Blocked on B14 policy. |
| **Live 0.3.0 → 0.3.1-dev upgrade** | Allowlist + keep tests are fixture-only. No RC-host upgrade run this round. |

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

`vincula.sh` migrates `0.1.0–0.1.5` and `0.2.0–0.3.0` to `0.3.1-dev`. Spec §9.4 treats `0.3.0 → 0.3.1` as a same-architecture milestone: no remint of `node_id` / `instance_id`, no credential UUID rotation, Reality keys unchanged, accounting schema/`event_id` unchanged.

## Verification this round

- `bash tests/test.sh` — **1231** passed
- `bash tests/test-fleet.sh` — **485** passed
- `bash -n` + `python3 -m py_compile` on first-party node/controller files
- `bash scripts/gen-release-lock.sh` after first-party edits

B14 was **not** executed. Recommendation stays **NOT READY**.
