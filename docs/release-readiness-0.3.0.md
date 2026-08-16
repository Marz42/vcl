# Vincula 0.3.0 Release Readiness

**Tree version:** 0.3.0-dev  
**Date:** 2026-08-16  
**Focus:** Backup / Replace / Restore (secretless default backup, age `--include-secrets`, `vcl restore` fresh-node, reissue CSV, `vcl-fleet node replace` vs `node set`, `fleet.db` schema 2 `instance_history`)  
**Companion:** [`known-issues-0.3.0.md`](known-issues-0.3.0.md) · Operator: [`backup.md`](backup.md) · [`fleet.md`](fleet.md) · Spec: [`specs/V0.2.7-V0.3.1_spec.md`](specs/V0.2.7-V0.3.1_spec.md) §7 / §9.3 / §10 / §11 / §13 / D17 / INV-02 / INV-05 / INV-06.

Product freeze (drop `-dev`) is Batch 17-freeze, not this docs gate.

## Release recommendation

**READY WITH DOCUMENTED LIMITATIONS**

Offline / **fixture** evidence for AC-3.0-01…10 and AC-3.0-12 is green. AC-3.0-11 is **PARTIAL / LIVE-only** and is **not** marked PASS from unit tests. Known P0/P1 at this docs gate: **0**. Dual artifacts remain reproducible. Node `release.lock` has **9** first-party files (includes `lib/vincula-backup.py`); the controller zip has **no** lock chain and still **four** members (`README-controller.md`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd`, `lib/vincula-fleet.py`).

Per spec §11, documented product limits are acceptable when they are intentional and do not break this milestone’s contract. D20’s 24h soak binds **0.2.7 only** — 0.3.0 must not be held to `READY FOR RC` on soak.

This tree is **not** `READY FOR RC` and **not** `NOT READY FOR RC`:

| Missing live evidence | Why it is a limitation, not a P0 |
| --- | --- |
| Windows 11 `vcl-fleet.cmd` on a real workstation | First-class packaging is tested (zip members, `.cmd` launcher). Live OpenSSH Client + Python 3.10+ is operator verification |
| Live secretless replace on a real VPS | AC-3.0 replace CI bar is **lax → lax2 fixtures**, not two public VPS |
| Live `age` on a real node | CI uses `tests/fixtures/fake-age`. Distro `age` + recipient/identity is operator evidence |
| AC-3.0-11 live VLESS handshake | Fixture proves old uuid ∉ inbound set (**PARTIAL**). Old URI to the **new** IP must fail on a real sing-box before this AC can PASS |

Fixture suite all-green → `READY WITH DOCUMENTED LIMITATIONS`. Raise to `READY FOR RC` only after **one live VPS secretless replace** **and** old URI failure on the new IP (AC-3.0-11) **and** a real `age` `--include-secrets` round-trip on a real node. Do not treat fake-ssh / fake-age as live evidence.

## Scope delivered

| Item | Status |
| --- | --- |
| Product version `0.3.0-dev` (freeze drops `-dev`) | PASS — constants + tests |
| Upgrade allowlist includes `0.2.9`, excludes `0.3.0` / `0.3.0-dev` | PASS (unit) |
| `state.json` schema stays **2**; strip only in the archive | PASS (unit) |
| `users.json` schema stays **2** | PASS (unit) |
| Accounting schema stays **3**; snapshot is `Connection.backup()` | PASS (unit) |
| `fleet.json` schema stays **2** (no `instance_id`) | PASS (unit) |
| `fleet.db` schema **2** + `instance_history` + 1→2 migrate | PASS (unit) |
| Backup schema **1**; secretless default; age `--include-secrets` | PASS (unit + fake-age) |
| `vcl restore` fresh-node + reissue CSV + safety rollback | PASS (unit) |
| `vcl-fleet node replace` / `node instances`; `node set` = rebind | PASS (fake-ssh + fake-scp) |
| Replace does not auto-reseed; cursor `last_event_id` kept | PASS (fake-ssh) |
| No management API port | PASS (static grep) |
| AC-3.0-11 live handshake | **MISSING** (LIVE-only; fixture PARTIAL) |
| Live VPS replace / live age / Win11 live controller | **MISSING** (limitation) |

## Acceptance criteria (AC-3.0-01…12)

Evidence strategy = **node unit tests** (`tests/test.sh`) plus **fake-ssh / fake-scp / fake-age fixtures** (`tests/test-fleet.sh`). Unit tests must **not** be marked as live VPS. Soak / live VPS items are not marked PASS from fixtures. AC-3.0-11 must stay **PARTIAL/UNKNOWN** until a live handshake.

| ID | Criterion | Status | Code evidence | Test evidence | Remaining risk | Release blocking |
| --- | --- | --- | --- | --- | --- | --- |
| AC-3.0-01 | Default backup contains identity / audit / accounting needed to replace | **PASS** (fixture) | `lib/vincula-backup.py` `create_backup` / `strip_*` / `snapshot_sqlite`; tar members + manifest | `tests/test.sh` `AC-3.0-01 fixture PASS: default backup includes identity and accounting` | Live disk-full / permission on `/var/backups/vincula` untested | YES (fixture) |
| AC-3.0-02 | Default backup is secretless; no encryption required | **PASS** (fixture) | Strip removes `reality_private_key`, `credentials[].uuid`, `clash_api_secret`; `secret_bearing=false` `encryption=none`; no age call | `AC-3.0-02 fixture PASS: default backup is secretless without encryption` | Operator accidentally using `--include-secrets` | YES (fixture) |
| AC-3.0-03 | Secret-bearing backup uses age; missing age → exact `'Secret-bearing backup requires age.'` | **PASS** (fixture) | `AGE_MISSING_MSG`; `AGE_RECIPIENT_MSG`; no plaintext secret tar | `AC-3.0-03 fixture PASS: missing age dies with exact ERROR and writes no tar`; fake-age round-trip | Real `age` binary / recipient file mistakes. Passphrase mode not implemented (intentional) | YES (fixture) |
| AC-3.0-04 | Verify detects a damaged archive | **PASS** (fixture) | `verify_archive` checksum / manifest / schema / secret-bearing-unencrypted | `AC-3.0-04 fixture PASS: verify detects bit-flip checksum mismatch`; missing manifest; schema 99 | Operator skipping verify (restore still verifies first) | YES (fixture) |
| AC-3.0-05 | Replace keeps `node_id` | **PASS** (fixture) | Restore plan asserts staged `node_id==source`; fleet replace checks identity vs registry | `AC-3.0-05 fixture PASS: restore keeps backup node_id`; `AC-3.0-05/06/07/10 replace keeps node_id…` | Live bootstrap VERSION vs fresh-node restore argv (see limitations) | YES (fixture) |
| AC-3.0-06 | Replace mints a new `instance_id` (not a copy of `node_id`) | **PASS** (fixture) | `mint_instance_id`; staged `instance_id≠node_id` and ≠ source | `AC-3.0-06 fixture PASS: restore mints new instance_id`; fleet history two rows | Accidental `instance_id = node_id` is fail-closed | YES (fixture) |
| AC-3.0-07 | Safe replace rotates Reality and user credentials | **PASS** (fixture) | Safe plan new Reality + new active uuid; old uuid absent from staged users | `AC-3.0-07 fixture PASS: safe restore rotates Reality and credentials`; fleet reissue CSV | Secrets-mode restore reuses keys (not the replace default) | YES (fixture) |
| AC-3.0-08 | `user_id` unchanged | **PASS** (fixture) | Plan copies user metadata / `user_id` | `AC-3.0-08 fixture PASS: restore keeps user_id` | None for this AC beyond live operator error | YES (fixture) |
| AC-3.0-09 | After replace, historical accounting/audit remains queryable | **PASS** (fixture) | Accounting snapshot restored; `event_id` kept; fleet cursor `last_event_id` kept; no auto reseed | `AC-3.0-09 fixture PASS: restore keeps accounting event_id history`; `AC-3.0-09 replace sync keeps old instance rows and cursor`; reseed keeps `instance_history` | `--from-backup` without final sync may leave a cursor hole (`CURSOR_EXPIRED` → `--reseed`) | YES (fixture) |
| AC-3.0-10 | Reissue CSV is correct | **PASS** (fixture) | Header `user,node,old_credential_id,new_credential_id,vless_uri`; 0600; only previously-active users | `AC-3.0-10 fixture PASS: reissue CSV maps old to new credential_id` | Operator mishandling 0600 files after copy | YES (fixture) |
| AC-3.0-11 | After revoke, old credential links fail | **PARTIAL / UNKNOWN** (LIVE-only) | Staged `users.json` / generated inbound `users[].uuid` omit the old uuid (code contract only) | `AC-3.0-11 fixture PARTIAL (LIVE-ONLY): old uuid absent from inbound set` — **not PASS**. Live: old URI → new IP:443 fails; new URI succeeds; stop old VPS | Fixture cannot prove a handshake rejection. Old VPS still up ⇒ old IP still accepts old uuid | **No** for `READY WITH DOCUMENTED LIMITATIONS`. Live PASS required to raise `READY FOR RC` |
| AC-3.0-12 | Failed restore does not silently destroy target or source | **PASS** (fixture) | verify-before-mutate; `pre-restore-*` safety; `VCL_RESTORE_FAIL_AFTER` test hook; fleet replace failure does not rewrite `ssh_host` | `AC-3.0-12 fixture PASS: failed restore does not mutate source or target`; mid-restore safety rollback; fleet restore/verify/backup/scp fail inject | Distributed rollback of a **committed** new-VPS restore is not promised (print `node set` back to old host) | YES (fixture) |

## Migration path (0.2.9 → 0.3.0)

| Step | Detail |
| --- | --- |
| Supported sources | `0.1.0`–`0.1.5` and `0.2.0`–`0.2.9` → **0.3.0** |
| Same version | Verify both planes; do not rotate credentials; do not remint `instance_id` |
| `state.json` | schema **stays 2**. Preserve `node_id` and `instance_id`. No Reality rotation on upgrade |
| Accounting schema | **Stays 3.** No DDL |
| `users.json` | schema **stays 2**. Existing `user_id` / credentials kept |
| `config.toml` | Still mirrors `node_id` only; **no** `instance_id` |
| Identity | Reality keys, user UUIDs, `user_id`, `node_id`, `instance_id` kept on **upgrade**. Rotation happens only on restore / `node replace` |
| D18 | `730` from 0.2.9 is **preserved** (case still only ≤0.2.6) |
| `fleet.json` | schema **stays 2** |
| `fleet.db` | schema **1 → 2** on next open (`instance_history` + backfill from `sync_cursor`) |
| Backup | **New** contract (schema 1). 0.2.9 had no product backup |
| Allowlist | Includes `0.2.9`. Does **not** include `0.3.0` or `0.3.0-dev` |
| Node lock | **9** first-party files (`lib/vincula-backup.py` added) |
| Controller zip | Still four members; no installer, no `release.lock` |

## Rollback

There is **no** automatic `fleet.db` schema 2→1 downgrade. Node-side schemas were not bumped (state 2, users 2, accounting 3), so there is no node DDL to reverse for this milestone.

**Nodes:** restore the `backup_existing_install` backup taken before migrate (core + accounting artifacts + SQLite `.backup` + `SERVICE_STATE`) **and** the matching **0.2.9** installer. Restoring a 0.3.0 tree’s files onto 0.2.9 is the supported rollback path only via that backup, not via a schema downgrade. A 0.3.0 backup archive (`vcl backup create`) is **not** the 0.2.9 rollback vehicle.

**Workstation:** the controller has no lock chain and no installer. Replace the unpacked zip with the 0.2.9 zip. Schema-2 `fleet.db` is **not** understood by 0.2.9 — restore a pre-upgrade copy of `$FLEET_HOME`. Leaving schema-2 `fleet.db` in place for a 0.2.9 binary is unsupported. That does not roll back nodes.

## Decisions frozen in this release

| Decision | Value |
| --- | --- |
| Default backup | Secretless identity/audit archive; age not required |
| `--include-secrets` | Verbatim canonical files + mandatory whole-archive age; never plaintext |
| age | Recipient file (`-R` / `-i`). No passphrase in 0.3.0 |
| Node restore | Fresh-node only; existing VERSION refused; no `--replace-node` flag |
| Replace vs rebind | `node replace` rotates; `node set` rebinds |
| `instance_history` SoT | `fleet.db` schema 2; **not** `fleet.json` |
| Cursor after replace | Update `instance_id`; keep `last_event_id`; **no** auto `--reseed` |
| Accounting snapshot | Python `Connection.backup()` only |
| Host-key | Default `known_hosts`; never `StrictHostKeyChecking=no` / `UserKnownHostsFile=/dev/null`; replace requires `--host-key` |
| Node lock | **9** first-party files |
| Controller lock | **None** — user-local zip, no installer integrity chain |
| AC-3.0-11 | LIVE-only; fixture PARTIAL is not PASS |
| Soak | D20 does **not** apply to 0.3.0 |
| MINOR bump | 0.2.9 → 0.3.0 because of the backup/restore contract (§9.3), not a state/users/accounting schema bump |

## Explicit non-goals (0.3.0)

localhost UI (0.3.1), age passphrase, `vcl snapshot export`, routine `scp accounting.db`, billing-grade accounting, node `vcl fleet` subcommand, silent `display_name` merge, distributed rollback **guarantee**, blocking 90-day retention for cursors, retire/replace auto-uninstall / erase `fleet.db`, replace `--include-secrets`, restore without a VERSION check.

## Policy after this docs gate

Freeze (`0.3.0-dev` → `0.3.0`) is the next batch. After tag `v0.3.0`, prefer P0/P1 fixes only. A live VPS secretless replace, live `age` on a real node, and AC-3.0-11 live handshake are required before raising this recommendation to `READY FOR RC`. UI belongs in 0.3.1.
