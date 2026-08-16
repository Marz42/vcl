# Vincula 0.3.0 Release Readiness

**Tree version:** 0.3.0 (freeze record). Living tree after Batch B0 is `0.3.1-dev`.  
**Date:** 2026-08-16 (freeze)  
**Addendum:** 2026-08-16 — P2-04 honesty; recommendation **NOT READY**.  
**Addendum:** 2026-08-16 — B2 / P0-01a: `node replace` fail-closed.  
**Addendum:** 2026-08-16 — B3 / P0-02: controller zip ships audit + backup modules.  
**Addendum:** 2026-08-16 — B6 / P1-06: operation-level flock mutex on node and controller.  
**Addendum:** 2026-08-16 — B7 / P1-04: `CURSOR_AHEAD` + strict sync batch validation.  
**Addendum:** 2026-08-16 — B8 / P1-02: restore is a single atomic transaction.  
**Addendum:** 2026-08-16 — B9 / P1-03: upgrade preflight captures service state before any mutation.  
**Addendum:** 2026-08-16 — B10 / P0-01b: `node replace` on the real restore contract.  
**Addendum:** 2026-08-17 — B11 / P2-01: uninstall leaves no `__pycache__`.  
**Addendum:** 2026-08-17 — B12 / P2-02: streaming backup verify and size caps.  
**Addendum:** 2026-08-17 — B13 / P2-03: controller sha256 manifest and fail-closed bootstrap pin.  
**Focus:** Backup / Replace / Restore (secretless default backup, age `--include-secrets`, `vcl restore` fresh-node, reissue CSV, `vcl-fleet node replace` vs `node set`, `fleet.db` schema 2 `instance_history`)  
**Companion:** [`known-issues-0.3.0.md`](known-issues-0.3.0.md) · Operator: [`backup.md`](backup.md) · [`fleet.md`](fleet.md) · Spec: [`specs/V0.2.7-V0.3.1_spec.md`](specs/V0.2.7-V0.3.1_spec.md) §7 / §9.3 / §10 / §11 / §13 / D17 / INV-02 / INV-05 / INV-06.

Product freeze dropped `-dev` in Batch 17-freeze. This file remains the 0.3.0 freeze record plus the contract-audit addendum. It is **not** a 0.3.1-dev gate document.

## Release recommendation

**NOT READY**

(Spec bucket: `NOT READY FOR RC`.) Supersedes freeze-era **READY WITH DOCUMENTED LIMITATIONS**. That grade treated P0-01 / P0-02 as documented limitations. An external contract audit classified both as **P0 blockers** (contract mismatch, not missing live evidence). **B3 closed P0-02** and **B10 closed P0-01** on the living tree. Remaining NOT READY is P1/P2 work plus live VPS evidence (B14), not the replace argv mismatch. Details: addendum below and [`known-issues-0.3.0.md`](known-issues-0.3.0.md).

## Addendum (2026-08-16) — external contract audit (P2-04)

The freeze docs claimed **Known P0/P1 at freeze: 0** and mapped fixture-green replace plus a four-member controller zip onto `READY WITH DOCUMENTED LIMITATIONS`. The Vincula 0.3.0 external-audit remediation plan (verified against this tree; plan file is outside the repository; this honesty batch is **B1**) found two **contract-level** P0s:

| ID | Contract failure | Why this is not a limitation |
| --- | --- | --- |
| **P0-01** | `vcl-fleet node replace` emits `vcl restore … --replace-node … --output`. Real `bin/vincula` `cmd_restore` dies on `--replace-node`, requires `--reissue-output`, and refuses an existing `VERSION`. `tests/fixtures/fake-ssh` implements the controller protocol, not the node CLI. Operator docs require an already-bootstrapped NEW_HOST. | A live VPS would **fail by contract**. “No live replace” was filed as a limitation; the protocol mismatch is a P0. |
| **P0-02** | `scripts/build-controller.sh` packs four members; the zip omits `lib/vincula-audit.py` and `lib/vincula-backup.py`. `load_audit_module` / `load_backup_module` die if those files are absent. Tests **pass** `controller zip omits node-side vincula-backup.py`. | A zip-only workstation cannot local-verify replace or run `audit`. Member-list packaging is not an accepted product limit; it is a broken artifact contract. |

**Known P0 at this gate: 2** (P0-01, P0-02). ~~Known P0/P1 at this docs gate: **0**.~~ That freeze sentence is **struck**. Do not restore it while these P0s remain. This addendum does not enumerate the audit’s P1/P2 items; it only stops calling them “zero P0/P1”.

The AC matrix, completion report, and test counts below are **unchanged** and are evidence **as of the 0.3.0 freeze**. Read AC-3.0-05…10 **PASS (fixture)** as fake-ssh / fake-scp results, not as “controller restore argv ⊆ real `vcl restore`”. Product remediations are later batches (B2+). Closing P0 in this addendum is not claimed.

## Addendum (2026-08-16) — B2 / P0-01a fail-closed

Living tree (`0.3.1-dev`): `vcl-fleet node replace` **fail-closes** (exit 2, stderr **NOT IMPLEMENTED against real vcl**). It does not rewrite `fleet.json` / `fleet.db`. Help, `docs/fleet.md`, and README no longer teach the fake restore argv. `node instances` remains available. The function body is kept for B10.

| ID | Living-tree status (B2) | Notes |
| --- | --- | --- |
| AC-3.0-05…10 / AC-3.0-12 **fleet replace** | **FAIL-CLOSED** (not a fixture PASS) | CLI never reaches fake-ssh restore. Node-side `vcl restore` ACs in `tests/test.sh` are unchanged |
| AC-3.0-11 fleet fixture PARTIAL | **withdrawn** from living-tree replace tests | Re-enable with B10 + B14 live handshake |
| `node instances` | still PASS | Independent of replace |

P0-01 remains open until B10. This batch only stops production misuse and false operator docs.

Living-tree test counts after B2: `bash tests/test.sh` **983**; standalone `bash tests/test-fleet.sh` **390**. The drop vs freeze 1006+413 is the withdrawn fake-ssh replace happy path / injection assertions, replaced by fail-closed + `node instances` coverage.

## Addendum (2026-08-16) — B3 / P0-02 controller zip runtime modules

Living tree (`0.3.1-dev`): `scripts/build-controller.sh` packs **six** files (`README-controller.md`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd`, `lib/vincula-fleet.py`, `lib/vincula-audit.py`, `lib/vincula-backup.py`). `load_audit_module` / `load_backup_module` resolve siblings in the controller’s own `lib/` (zip unpack or repo), not cwd / `PYTHONPATH`. The freeze-era assertion `controller zip omits node-side vincula-backup.py` is deleted. Black-box: unzip `dist/vincula-controller-*.zip` with no repo `lib/` on `sys.path`, then `version` / `init` / `audit` / `stats` plus `node replace` fail-closed.

P0-02 is **closed**. Known P0 on the living tree: **1** (P0-01). Controller zip still has **no** `release.lock` (P2-03). Freeze-era “four members” text below is historical.

Living-tree test counts after B3: `bash tests/test.sh` **998**; standalone `bash tests/test-fleet.sh` **393**.

## Addendum (2026-08-16) — B6 / P1-06 operation-level mutex

Living tree (`0.3.1-dev`): node CLI and installer take an exclusive `flock` on `/run/lock/vincula.lock` (fallback `/var/lock/vincula.lock`; tests use `$VCL_LOCK_FILE`). The lock covers user add/set/disable/enable/rotate/import, `vcl restore`, and other `users.json` writers for the full read–stage–validate–commit–restart window. Timeout 30s (`$VCL_LOCK_TIMEOUT`) → exit 4, stderr `busy: another vincula operation in progress`. Released on EXIT (trap) and when the fd closes.

Controller: exclusive `fcntl.flock` on `$FLEET_HOME/.lock` for `node add/set/disable/enable/retire/replace`, `sync` (including cursor / `fleet.db` writes), and `save_registry`. Registry and `fleet.db` share that one lock. Timeout `$VCL_FLEET_LOCK_TIMEOUT` (default 30s) → exit 4 with the same busy text.

Concurrent `user add` / `node add` either serialize (both records present) or the waiter exits busy; no last-writer-wins lost update.

Living-tree test counts after B6: `bash tests/test.sh` **1051**; standalone `bash tests/test-fleet.sh` **415**.

## Addendum (2026-08-16) — B7 / P1-04 CURSOR_AHEAD and strict sync validation

Living tree (`0.3.1-dev`): node `vcl audit export --after` returns **CURSOR_AHEAD** (exit **3**, `meta.error=CURSOR_AHEAD`, empty stdout, `next_cursor` unchanged) when `after > 0` and `after > MAX(event_id)`. Distinct from **CURSOR_EXPIRED** (`MIN(event_id) > after+1` or empty DB). Controller distinguishes by `meta.error`, not return code alone.

`sync_one_node` validates remote meta against delivered JSONL before import: `after` matches our cursor, `count==len(rows)`, `next_cursor` is last `event_id` (or unchanged if empty), JSONL `event_id` values are contiguous, first row is `after+1` when `after>0`, and meta/row `node_id` matches identity. Any mismatch → **ERROR**, no import, cursor not advanced. Cursor advances to the remote `next_cursor` only after the full batch is validated and imported in one transaction. `CURSOR_AHEAD` prints `--reseed` (stale cursor vs a restored older DB, including `--from-backup`). Replace remains fail-closed (B2); this batch does not re-enable it.

Living-tree test counts after B7: `bash tests/test.sh` **1066**; standalone `bash tests/test-fleet.sh` **430**.

## Addendum (2026-08-16) — B8 / P1-02 restore is a true transaction

Living tree (`0.3.1-dev`): `apply_restore` stages canonical files, `accounting.db`, generated config, and the reissue CSV, then writes `VERSION` last (the dest commit marker). All of those plus the pre-restore sing-box / accountd enabled+active snapshot share one try/rollback. CLI health/render failure calls the same rollback (config.json, CSV, VERSION, service state); it does **not** `systemctl restart sing-box` on a mixed tree. `VCL_RESTORE_FAIL_AFTER=canonical|csv|config|health|version` (and ENOSPC on CSV / EACCES on VERSION) leave the target fully recoverable; a second restore without the hook succeeds.

Living-tree test counts after B8: `bash tests/test.sh` **1076**; standalone `bash tests/test-fleet.sh` **430**.

## Addendum (2026-08-16) — B9 / P1-03 upgrade captures service state before mutation

Living tree (`0.3.1-dev`): `migrate_existing_install` runs file/schema/disk/REALITY/`sing-box check` preflight with no service side effects, then captures sing-box + accountd enabled/active into `SERVICE_STATE` and sets `MIGRATION_STARTED=1` **before** backup or any `systemctl` stop/start. Accounting is snapshotted with Python `sqlite3.Connection.backup()` from the **source-tree** `lib/vincula-backup.py` (accountd stays up). Accountd is stopped only for the file-swap window. `rollback_migration` applies the snapshot exactly (no “unit exists → restart”). `VCL_MIGRATE_FAIL_AFTER=preflight|armed|backup|health-wait|accountd-stop|health|accountd` restores the pretest enabled/active bits.

Living-tree test counts after B9: `bash tests/test.sh` **1091**; standalone `bash tests/test-fleet.sh` **430**.

## Addendum (2026-08-16) — B10 / P0-01b real restore contract

Living tree (`0.3.1-dev`): `vcl-fleet node replace` is callable. Restore argv is `vcl restore FILE --reissue-output FILE --server HOST --json` (no `--replace-node`, no restore `--output`). NEW_HOST must be **runtime-only** (`vincula.sh --runtime-only` or `VCL_RUNTIME_ONLY=1`): sing-box, systemd units, helper, Python libs; **no** `/etc/vincula/VERSION` and no generated identity. Preflight: `test -x /usr/local/bin/vcl` and `test ! -f /etc/vincula/VERSION`. A bootstrapped host (VERSION present) fails without rewriting `fleet.json`. fake-ssh matches the real flags. A contract test feeds the controller argv to real `bin/vincula` `cmd_restore`. Live two-VPS handshake remains B14.

P0-01 is **closed** on the living tree. Known P0: **0**. AC-3.0-05…10 fleet replace are **PASS (fixture)** on the real contract. AC-3.0-11 remains PARTIAL / LIVE-only.

Living-tree test counts after B10: `bash tests/test.sh` **1142**; standalone `bash tests/test-fleet.sh` **474**.

## Addendum (2026-08-17) — B11 / P2-01 no pycache residue

Living tree (`0.3.1-dev`): `validate_accounting_artifacts` syntax-checks staged Python with `compile(source, filename, "exec")` (`python3 -B`); it does **not** call `python3 -m py_compile`, so install validation does not create `$LIB_DIR/__pycache__`. Runtime imports may still write bytecode; `cmd_uninstall`, `rollback_install`, and `rollback_migration` remove product-owned `$LIB_DIR/__pycache__` with `rm -rf --one-file-system` before `rmdir`. After uninstall of listed lib files + pycache, `$LIB_DIR` is gone.

P2-01 is **closed** on the living tree.

Living-tree test counts after B11: `bash tests/test.sh` **1154**; standalone `bash tests/test-fleet.sh` **474**.

## Addendum (2026-08-17) — B12 / P2-02 streaming backup verify and size caps

Living tree (`0.3.1-dev`): `verify_archive` / `_read_tar_members` reject a member whose `TarInfo.size` exceeds `MAX_MEMBER_BYTES` (1 GiB) or a total that exceeds `MAX_ARCHIVE_BYTES` (2 GiB) **before** `extractfile`. Remaining members are copied in `IO_CHUNK_BYTES` (1 MiB) chunks. JSON/text stay in memory under `MAX_TEXT_MEMBER_BYTES` (16 MiB). `accounting.db` is extracted to a tempfile and hashed with `sha256_file`; `write_tar` uses `TarFile.addfile` from a file handle; `atomic_replace` is a chunked copy + `os.replace`. SQLite snapshot was already the Backup API (not `read_bytes`).

P2-02 is **closed** on the living tree.

Living-tree test counts after B12: `bash tests/test.sh` **1167**; standalone `bash tests/test-fleet.sh` **474**.

## Addendum (2026-08-17) — B13 / P2-03 controller sha256 and bootstrap pin

Living tree (`0.3.1-dev`): `scripts/build-controller.sh` writes `controller.lock` (member list + sha256 per file) inside the zip and an independent sidecar `dist/vincula-controller-<ver>.zip.sha256`. The build verifies both (`sha256sum --check` on the sidecar and on the unpacked lock). `vincula-bootstrap.sh` production mode **requires** `RELEASE_SHA256` or a non-empty `EMBEDDED_RELEASE_SHA256`; missing pin is fail-closed. With a pin, the archive must match the pin **and** the shipped `${RELEASE_URL}.sha256`. Fetching the sibling digest from the same URL only detects transport corruption, not origin replacement of both files. `--allow-insecure-sibling-digest` is non-production only.

P2-03 is **closed** on the living tree.

Living-tree test counts after B13: `bash tests/test.sh` **1184**; standalone `bash tests/test-fleet.sh` **476**.

### Freeze-era recommendation (historical)

The following block is the Batch 17-freeze text, retained for the record. It is **not** the current recommendation.

**READY WITH DOCUMENTED LIMITATIONS** *(freeze-era; superseded by the addendum)*

Offline / **fixture** evidence for AC-3.0-01…10 and AC-3.0-12 is green. AC-3.0-11 is **PARTIAL / LIVE-only** and is **not** marked PASS from unit tests. ~~Known P0/P1 at this docs gate: **0**.~~ *(struck; post-audit Known P0 = 2.)* Dual artifacts remain reproducible. Node `release.lock` has **9** first-party files (includes `lib/vincula-backup.py`); the controller zip has **no** lock chain and still **four** members (`README-controller.md`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd`, `lib/vincula-fleet.py`).

Per spec §11, documented product limits are acceptable when they are intentional and do not break this milestone’s contract. D20’s 24h soak binds **0.2.7 only** — 0.3.0 must not be held to `READY FOR RC` on soak.

Freeze-era table (live-evidence gaps only; **does not** cover P0-01 / P0-02):

| Missing live evidence | Why the freeze filed it as a limitation, not a P0 |
| --- | --- |
| Windows 11 `vcl-fleet.cmd` on a real workstation | First-class packaging is tested (zip members, `.cmd` launcher). Live OpenSSH Client + Python 3.10+ is operator verification |
| Live secretless replace on a real VPS | AC-3.0 replace CI bar is **lax → lax2 fixtures**, not two public VPS. **Post-audit:** even a live run would fail P0-01. |
| Live `age` on a real node | CI uses `tests/fixtures/fake-age`. Distro `age` + recipient/identity is operator evidence |
| AC-3.0-11 live VLESS handshake | Fixture proves old uuid ∉ inbound set (**PARTIAL**). Old URI to the **new** IP must fail on a real sing-box before this AC can PASS |

Freeze-era path: fixture suite all-green → `READY WITH DOCUMENTED LIMITATIONS`. Raise to `READY FOR RC` only after **one live VPS secretless replace** **and** old URI failure on the new IP (AC-3.0-11) **and** a real `age` `--include-secrets` round-trip on a real node. Do not treat fake-ssh / fake-age as live evidence. **Post-audit:** that path is blocked until P0-01 and P0-02 close; fixture green is not a contract pass.

## Scope delivered

| Item | Status |
| --- | --- |
| Product version `0.3.0` (no `-dev`) | PASS — constants + tests |
| Upgrade allowlist includes `0.2.9`, excludes `0.3.0` / `0.3.0-dev` | PASS (unit) |
| `state.json` schema stays **2**; strip only in the archive | PASS (unit) |
| `users.json` schema stays **2** | PASS (unit) |
| Accounting schema stays **3**; snapshot is `Connection.backup()` | PASS (unit) |
| `fleet.json` schema stays **2** (no `instance_id`) | PASS (unit) |
| `fleet.db` schema **2** + `instance_history` + 1→2 migrate | PASS (unit) |
| Backup schema **1**; secretless default; age `--include-secrets` | PASS (unit + fake-age) |
| `vcl restore` fresh-node + reissue CSV + safety rollback | PASS (unit) |
| `vcl-fleet node replace` / `node instances`; `node set` = rebind | **FAIL-CLOSED** replace (B2); instances + rebind still PASS |
| Replace does not auto-reseed; cursor `last_event_id` kept | intended; replace CLI unreachable (B2) |
| No management API port | PASS (static grep) |
| AC-3.0-11 live handshake | **MISSING** (LIVE-only; fixture PARTIAL) |
| Live VPS replace / live age / Win11 live controller | **MISSING** (limitation) |

## Acceptance criteria (AC-3.0-01…12) — as of 0.3.0 freeze

Historical freeze matrix. **Not rewritten** in the 2026-08-16 P2-04 addendum. Fixture **PASS** on AC-3.0-05…10 is fake-ssh / fake-scp evidence only; it does not mean the controller restore argv is accepted by real `bin/vincula`.

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
| AC-3.0-09 | After replace, historical accounting/audit remains queryable | **PASS** (fixture) | Accounting snapshot restored; `event_id` kept; fleet cursor `last_event_id` kept; no auto reseed | `AC-3.0-09 fixture PASS: restore keeps accounting event_id history`; `AC-3.0-09 replace sync keeps old instance rows and cursor`; reseed keeps `instance_history` | `--from-backup` without final sync may leave a cursor ahead of restored `MAX(event_id)` (`CURSOR_AHEAD` → `--reseed`) or a retention hole (`CURSOR_EXPIRED` → `--reseed`). **B7:** neither case is silent OK | YES (fixture) |
| AC-3.0-10 | Reissue CSV is correct | **PASS** (fixture) | Header `user,node,old_credential_id,new_credential_id,vless_uri`; 0600; only previously-active users | `AC-3.0-10 fixture PASS: reissue CSV maps old to new credential_id` | Operator mishandling 0600 files after copy | YES (fixture) |
| AC-3.0-11 | After revoke, old credential links fail | **PARTIAL / UNKNOWN** (LIVE-only) | Staged `users.json` / generated inbound `users[].uuid` omit the old uuid (code contract only) | `AC-3.0-11 fixture PARTIAL (LIVE-ONLY): old uuid absent from inbound set` — **not PASS**. Live: old URI → new IP:443 fails; new URI succeeds; stop old VPS | Fixture cannot prove a handshake rejection. Old VPS still up ⇒ old IP still accepts old uuid | **No** for `READY WITH DOCUMENTED LIMITATIONS`. Live PASS required to raise `READY FOR RC` |
| AC-3.0-12 | Failed restore does not silently destroy target or source | **PASS** (fixture) | verify-before-mutate; `pre-restore-*` safety; `VCL_RESTORE_FAIL_AFTER` test hook (stage/canonical/csv/config/health/version); fleet replace failure does not rewrite `ssh_host` | `AC-3.0-12 fixture PASS: failed restore does not mutate source or target`; mid-restore safety rollback; **B8** csv/version/health injects roll back CSV, config, VERSION, and service state; fleet restore/verify/backup/scp fail inject | Distributed rollback of a **committed** new-VPS restore is not promised (print `node set` back to old host) | YES (fixture) |

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

**Nodes:** restore the `backup_existing_install` backup taken before migrate (core + accounting artifacts + Python SQLite Backup API snapshot + `SERVICE_STATE`) **and** the matching **0.2.9** installer. Restoring a 0.3.0 tree’s files onto 0.2.9 is the supported rollback path only via that backup, not via a schema downgrade. A 0.3.0 backup archive (`vcl backup create`) is **not** the 0.2.9 rollback vehicle.

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

## Policy after freeze

After tag `v0.3.0`, prefer P0/P1 fixes only. The living tree is `0.3.1-dev` (Batch B0). A live VPS secretless replace, live `age` on a real node, and AC-3.0-11 live handshake remain required before `READY FOR RC`, **and** P0-01 must close first (P0-02 closed in B3; this freeze record stays **NOT READY** until P0-01 closes). UI belongs in 0.3.1 Phase B.

## Completion report (SPEC §19)

Filled at freeze `0.3.0` (Batch 17-freeze). Historical 0.2.9/0.2.8/0.2.7 docs and `docs/specs/` were not rewritten.

### 1. Changed files

**Milestone (0.2.9 → 0.3.0):** `vincula.sh`, `bin/vincula`, `lib/vincula-common.sh`, `lib/vincula-backup.py` (new), `lib/vincula-fleet.py`, `lib/vincula-accountd.service`, `scripts/build-release.sh`, `scripts/gen-release-lock.sh`, `tests/test.sh`, `tests/test-fleet.sh`, `tests/fixtures/fake-age` (new), `tests/fixtures/fake-scp` (new), `tests/fixtures/fake-ssh`, `tests/fixtures/fake-ssh-keyscan`, identity fixtures (`identity-sample.json`, `nodes/{lax,tokyo,copied,lax2}/identity.json`, `lax/identity-reinstall.json`, `lax2/{hostkey.pub,status.json,verify.json}`), `README.md`, `README-controller.md`, `CHANGELOG.md`, `docs/backup.md` (new), `docs/fleet.md`, `docs/identity.md`, `docs/known-issues-0.3.0.md` (new), `docs/release-readiness-0.3.0.md` (new), `release.lock`, `vincula.sh.sha256`.

**Freeze-only (drop `-dev` + lock regen):** the product stamps above plus `vincula-bootstrap.sh` comment URLs (`0.2.9` → `0.3.0` tarball examples), `docs/accounting-reliability.md` title (collector unchanged through 0.3.0), and regenerated `release.lock` / `vincula.sh.sha256`. Fleet files remain **out** of the node lock.

Node first-party lock members stay **9**: `vincula.sh`, `vincula-bootstrap.sh`, `bin/vincula`, `lib/vincula-common.sh`, `lib/vincula-accountd.py`, `lib/vincula-stats.py`, `lib/vincula-audit.py`, `lib/vincula-backup.py`, `lib/vincula-accountd.service`. No `vincula-fleet.py`.

### 2. Schema changes

| Format | 0.2.9 | 0.3.0 | Notes |
| --- | --- | --- | --- |
| Product `VINCULA_VERSION` / `VCL_FLEET_VERSION` | `0.2.9` | **`0.3.0`** | Freeze dropped `-dev` only |
| `state.json.schema_version` | 2 | **2** | Strip of `reality_private_key` is archive-only |
| `users.json.schema_version` | 2 | **2** | Strip of `credentials[].uuid` is archive-only |
| accounting `meta.schema_version` | 3 | **3** | No DDL; snapshot is `Connection.backup()` |
| `fleet.json.schema_version` | 2 | **2** | Still no `instance_id` |
| `fleet.db` `meta.schema_version` | 1 | **2** | `instance_history`; explicit 1→2 migrate |
| backup `schema_version` | — | **1** | New contract |

### 3. CLI changes

**Node:** `vcl backup create [--include-secrets] [--output FILE] [--age-recipient FILE] [--json]`; `vcl backup verify FILE [--age-identity FILE] [--json]`; `vcl restore FILE [--include-secrets] [--age-identity FILE] [--reissue-output FILE] [--server HOST] [--json]`. Restore is **fresh-node only** (existing `VERSION` refused with `Refusing to overwrite an existing Vincula install.`). `--replace-node` is not a supported node flag (explicit die). No node `vcl fleet` subcommand. No `vcl snapshot export` alias.

**Controller:** `vcl-fleet node replace NAME --host HOST --host-key SHA256:… [--output FILE] [--from-backup FILE] [--json]`; `vcl-fleet node instances NAME [--json]`. `node set` remains endpoint rebind (credentials stay). Replace is secretless-only; requires `--host-key`. PARTIAL / `CURSOR_EXPIRED` / `--reseed` unchanged from 0.2.9.

### 4. Migration path

Supported sources: `0.1.0`–`0.1.5` and `0.2.0`–`0.2.9` → **0.3.0**. Allowlist includes `0.2.9`, excludes `0.3.0` / `0.3.0-dev`. Same-version re-run verifies both planes and does not rotate credentials or remint `instance_id`. D18 does **not** re-migrate daily=730 from 0.2.9. Workstation: `fleet.db` 1→2 on next open (`instance_history` + backfill from `sync_cursor`). Node state/users/accounting/`fleet.json` schemas unchanged. Rotation of Reality / uuid happens only on `vcl restore` / `vcl-fleet node replace`, not on upgrade.

### 5. Rollback path

No automatic `fleet.db` 2→1. Node schemas were not bumped. Nodes: restore `backup_existing_install` **and** the matching **0.2.9** installer. A 0.3.0 `vcl backup create` archive is **not** the 0.2.9 rollback vehicle. Workstation: replace the zip with the 0.2.9 controller; restore a pre-upgrade `$FLEET_HOME`. Schema-2 `fleet.db` is unsupported on a 0.2.9 binary.

### 6. Security impact

No new listen port (`socket.bind` / `HTTPServer` absent on backup.py, fake-age, fake-scp, fleet). Default backup is secretless; secret-bearing backups are whole-archive age (`-R` / `-i`), never plaintext tar. Archive / CSV / `.tar.age` mode **0600**; `$BACKUP_ROOT` and `$FLEET_HOME/backups/` **0700**. D14 unchanged: no `StrictHostKeyChecking=no`, no `UserKnownHostsFile=/dev/null`, no paramiko, OpenSSH argv lists only; replace requires `--host-key`. Controller remains non-root, no systemd, no `/etc/vincula`. Node `release.lock` **9** files; controller zip still has **no** lock.

### 7. Tests executed

Freeze verification: `bash -n` on all first-party bash (installer, helper, common, scripts, `tests/test.sh`, `tests/test-fleet.sh`); `python3 -m py_compile` on `lib/*.py`, `bin/vcl-fleet`, `tests/fixtures/fake-{age,scp,ssh,ssh-keyscan}`; `bash tests/test.sh` (sources fleet); `bash tests/test-fleet.sh` (standalone); `bash scripts/gen-release-lock.sh`.

| Suite | Count | Result |
| --- | --- | --- |
| `bash tests/test.sh` (sources `tests/test-fleet.sh`) | **1005** | green |
| `bash tests/test-fleet.sh` (standalone) | **413** | green |

~~P0/P1 at freeze: **0**.~~ **Correction (2026-08-16 addendum):** freeze claim struck. Post-audit Known P0: **2** (P0-01, P0-02). Test counts above are unchanged freeze evidence. No live Win11 / live VPS replace / live `age` / live 0.2.9→0.3.0 upgrade run.

### 8. Failure-injection results

| Inject | Result |
| --- | --- |
| Bit-flip tar member (manifest sha unchanged) | verify + restore non-zero; `error=checksum_mismatch`; dest unchanged |
| Tar without `manifest.json` | `missing_manifest`; dest unchanged |
| Existing `VERSION` + `vcl restore FILE` | exact overwrite refusal; dest bytes unchanged |
| `PATH` without age + `--include-secrets` | exact `ERROR: Secret-bearing backup requires age.`; no plaintext secret tar |
| `VCL_RESTORE_FAIL_AFTER=stage` (after stage, before install) | target equals pre-restore; source tar sha256 unchanged; `pre-restore-*` kept; second restore without hook succeeds |
| `VCL_RESTORE_FAIL_AFTER=canonical\|csv\|config\|health\|version` | full rollback: no VERSION (or VERSION removed), no leftover reissue CSV, generated config restored, sing-box/accountd enabled+active restored; re-restore succeeds (P1-02 / B8) |
| CSV `ENOSPC` / VERSION `EACCES` inject | same recoverable state as above |
| `VCL_RESTORE_FAIL_AFTER=health` | CLI rolls back target (canonical + config + CSV + services); source intact |
| `VCL_MIGRATE_FAIL_AFTER=preflight\|armed\|backup\|health-wait\|accountd-stop\|health\|accountd` | upgrade inject: accountd/sing-box enabled+active restored to pretest (P1-03 / B9) |
| `VCL_FAKE_FAIL_RESTORE` / backup-create fail / scp fail / verify-fail `--from-backup` | replace aborts; `fleet.json` `ssh_host` stays old; no new `instance_history` active |
| `--from-backup` whose `source_node_id` ≠ registry | refused; registry `node_id` / old host unchanged |
| Replace then cursor gap | `CURSOR_EXPIRED` + `--reseed` guidance; `--reseed` keeps `instance_history` |

### 9. Acceptance criteria matrix

AC-3.0-01…10 and AC-3.0-12: **PASS** on node unit / fake-ssh / fake-scp / fake-age as tabulated above. AC-3.0-11: **PARTIAL / UNKNOWN** (LIVE-only). Fixture proves old uuid ∉ inbound set — **not** marked PASS. None marked PASS from live VPS or soak.

### 10. Known limitations

See [`known-issues-0.3.0.md`](known-issues-0.3.0.md). Freeze-era headline (limitations only): no Win11 live `vcl-fleet.cmd`; no live VPS secretless replace; no real `age` on a node; AC-3.0-11 LIVE-only; `--from-backup` may drop the sync tail; old VPS still up ⇒ old IP still accepts old uuid; `fleet.db` 2 irreversible; D20 soak is not a 0.3.0 gate; reseed still wipes local audit cache but not `instance_history`. **Post-audit P0 blockers** (not limitations): P0-01 replace argv vs node CLI; P0-02 controller zip missing audit/backup modules.

### 11. Version / schema bump explanation

Product bump `0.2.9` → `0.3.0-dev` happened at the start of the milestone (Batch 13-version) because of the backup/restore contract (§9.3 MINOR), not a state/users/accounting schema bump. Freeze only removes `-dev`. Persistence bumps: backup schema **1** (new); `fleet.db` **1→2** (`instance_history`). `state.json` / `users.json` / accounting / `fleet.json` stay at 2 / 2 / 3 / 2.

### 12. Release recommendation

Freeze-era (Batch 17-freeze), **superseded** by the 2026-08-16 addendum. Current recommendation at the top of this file is **NOT READY**.

**READY WITH DOCUMENTED LIMITATIONS** *(historical freeze text)*

CI fixture all-green, ~~P0/P1=0~~ *(struck; post-audit Known P0 = 2)*, no live VPS secretless replace and no live AC-3.0-11 handshake. Raise to `READY FOR RC` only after **one live VPS secretless replace** **and** old URI failure on the new IP **and** a real `age` `--include-secrets` round-trip. Freeze claimed not `NOT READY FOR RC` on the grounds that documented limits do not break the 0.3.0 contract. **Post-audit:** P0-01 and P0-02 **do** break that contract; the current grade is **NOT READY**.

### Extra (plan §6)

13. **Backup schema 1:** `manifest.json` + `state.json` / `users.json` / `config.toml` / `accounting.db` / `VERSION`. Secretless strip: drop `node.reality_private_key`, `credentials[].uuid`, `clash_api_secret` (keys absent, not empty).
14. **age:** recipient file `-R` / identity `-i`. Exact `ERROR: Secret-bearing backup requires age.` (D17). No passphrase mode.
15. **fleet.db 1→2:** `instance_history` SoT is `fleet.db`, not `fleet.json`.
16. **CURSOR_EXPIRED:** replace updates `sync_cursor.instance_id`, keeps `last_event_id`, does **not** auto `--reseed`. History instance rows survive reseed.
17. **AC-3.0-11** must not be marked PASS from unit tests. Readiness LIVE strategy: old URI → new IP:443 fails; new URI succeeds; stop old VPS.
18. **Dual artifacts:** node `release.lock` **9** files (includes `lib/vincula-backup.py`; fleet **not** in lock). Controller zip still **four** members (`README-controller.md`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd`, `lib/vincula-fleet.py`) and **no** lock / installer. Local replace verify loads `vincula-backup.py` from the same `lib/` as `vincula-fleet.py` (repo layout); zip does not embed it.

**Confirmed non-goals:** localhost UI, age passphrase, `vcl snapshot export`.
