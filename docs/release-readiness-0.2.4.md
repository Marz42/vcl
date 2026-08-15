# Vincula 0.2.4 Release Readiness Report

**Date:** 2026-08-14  
**Tree version:** 0.2.4  
**Automated suite:** `bash tests/test.sh` → **All 207 tests passed** (WSL2)  
**Live spot-check:** Debian 13 amd64 (2026-08-15) — main path PASS; full matrix incomplete  
**Release recommendation:** **READY WITH DOCUMENTED LIMITATIONS**

Open gaps: [`known-issues-0.2.4.md`](known-issues-0.2.4.md). RC procedure: [`rc-test-manual-0.2.4.md`](rc-test-manual-0.2.4.md).

This report answers Gate R01–R25 and F01–F15. Status values are only PASS / FAIL / PARTIAL / UNKNOWN. Untested live-host items are UNKNOWN — not speculative PASS.

---

## 1. Changed files

| Area | Files |
| --- | --- |
| Installer | `vincula.sh` |
| Helper | `bin/vincula` |
| Shared | `lib/vincula-common.sh` |
| Accountd | `lib/vincula-accountd.py`, `lib/vincula-accountd.service`, `lib/vincula-event.schema.json` |
| Packaging | `release.lock`, `vincula.sh.sha256`, `vincula-bootstrap.sh`, `scripts/gen-release-lock.sh` |
| Docs | `CHANGELOG.md`, `README.md`, `docs/accounting-reliability.md`, `docs/release-readiness-0.2.4.md` |
| Tests | `tests/test.sh` |

## 2. P0 fixes

| ID | Fix |
| --- | --- |
| P0-1 | `enable_accountd_service` hard-fails via `wait_for_accountd_healthy`; Clash API must accept secret and reject empty/wrong secret; only then `INSTALL_COMMITTED=1` |
| P0-2 | `preflight_clean_install` dies if `VAR_LIB_VINCULA` / `accounting.db` / `events.jsonl` exist |
| P0-3 | Migration stops accountd; backs up accounting artifacts + SQLite + `SERVICE_STATE`; `rollback_migration` restores them |
| P0-4 | `verify_existing_install` prints `[Proxy Plane]` / `[Accounting Plane]` and dies on any FAIL |

## 3. Schema changes

- SQLite `meta.schema_version = 2`
- `connections` / `daily_usage` canonical key = `user_id` (+ optional `user_tag`)
- Explicit `migrate_schema` 0/1 → 2 (tag→user_id via `users.json`, fail-closed)
- Corrupt / unreadable DB → `SystemExit` (no wipe-to-empty)

## 4. Packaging changes

- `release.lock` SHA-256 of first-party files; verified before sourcing `vincula-common.sh`
- `vincula-bootstrap.sh`: archive SHA → extract → per-file `release.lock` → exec `vincula.sh`
- README: no single-file install path

## 5. Migration changes

- Supported sources: `0.1.0–0.1.5`, `0.2.0–0.2.3` → `0.2.4`
- Assign permanent `node_id` UUID when missing/`local`
- Credential UUID SoT = `users.json` only (`state.json` has no `owner.uuid`)

## 6. Accounting correctness model

- Backend: **Clash API polling** (optional JSONL preferred when present)
- Day boundary: **UTC** (`closed_at` date for daily rollup)
- First sight of a connection: **baseline, zero delta**
- Counter decrease: **new generation**, no negative delta
- Destination: lowercase + strip trailing `.`; no rDNS; IP-only allowed (`destination_host` NULL)
- Product claim: **approximate polling accounting** — Reliable Accounting **not** done

## 7. Known limitations

1. Short connections between poll intervals may be missed.
2. Fresh-install OS matrix (Debian 12/13, Ubuntu 22.04/24.04, arm64) **not executed** in this environment.
3. End-to-end migration on live nodes (`0.1.5`/`0.2.x` → `0.2.4` + forced rollback) **not executed**.
4. Several F0x items need a real systemd + sing-box host → marked UNKNOWN.
5. `vincula-event.schema.json` is install-time JSON validated + documentation; **not** runtime-enforced on every event.
6. Accountd runs as **root** (required for `0600` settings/DB); unit hardened but not unprivileged.

---

## 8. Release Readiness Report R01–R25

### R01 — Clash API exposure

Status: PARTIAL

Conclusion: Generated configs bind Clash API to `127.0.0.1:<port>` only; unit tests forbid `0.0.0.0`. Live `ss -ltnp` on an installed node was not captured here.

Code evidence: `lib/vincula-common.sh` (~682) `external_controller: 127.0.0.1:{port}`; tests assert localhost and reject `0.0.0.0`.

Test evidence: `tests/test.sh` ok “accounting config binds clash_api to 127.0.0.1”, “must not bind … 0.0.0.0”.

Remaining risk: Mis-edited live config outside installer would not be re-checked until `vcl verify`.

Release blocking: NO (documented; live ss UNKNOWN)

---

### R02 — Clash API authentication

Status: PARTIAL

Conclusion: Secret is written to settings + sing-box config; health gate requires Bearer success and empty/wrong Bearer failure when secret is set.

Code evidence: `vincula.sh` `clash_api_reachable_with_secret` (~1832); `wait_for_accountd_healthy` (~1886–1901) rejects `""` and `wrong-${secret}`.

Test evidence: Unit coverage of secret in rendered config; live curl triad on running Clash API not executed in this workspace.

Remaining risk: Live auth triad still needs one systemd host.

Release blocking: NO

---

### R03 — user attribution

Status: PARTIAL

Conclusion: Registry tag → `acct/<tag>` outbound/route → Clash chains → `resolve_user_id` → SQLite `user_id` is implemented end-to-end in code/tests. Live four-layer capture on traffic not run.

Code evidence: `render_sing_box_config_accounting` in common; `lib/vincula-accountd.py` `load_tag_to_user_id` / `resolve_user_id` (~152–174); ingest test writes `user_id`.

Test evidence: ok “ingested connection row has user_id”, multi-user `acct/alice` + `acct/owner`.

Remaining risk: Live Clash chain shape drift across sing-box versions.

Release blocking: NO

---

### R04 — accounting identity key

Status: PASS

Conclusion: Canonical identity is **`user_id`**. UUID is credential material only.

Code evidence: schema columns `user_id TEXT NOT NULL` (~65, ~85); `SCHEMA_VERSION = 2` (~49).

Test evidence: ok “meta.schema_version is 2”, “ingested connection row has user_id”.

Remaining risk: None material for RC decision.

Release blocking: NO

---

### R05 — UUID rotation continuity

Status: PARTIAL

Conclusion: Rotate updates credential UUID in `users.json` while preserving `user_id`; history keyed by `user_id` continues. Live Alice A→B traffic continuity not measured on a node.

Code evidence: `users_registry_mutate rotate` keeps `user_id`; accounting resolves by tag→`user_id`.

Test evidence: registry mutate covered in earlier identity tests; no live rotate+traffic matrix.

Remaining risk: Operator must not delete `user_id` rows.

Release blocking: NO

---

### R06 — revoked credential

Status: PARTIAL

Conclusion: Disable/rotate removes old UUID from generated inbound users. Historical SQLite rows retained. Live “old client fails to connect” not executed here.

Code evidence: user disable/rotate regenerates config from registry; uninstall/stats read DB independently of inbound UUID.

Test evidence: registry/config generation tests; no live client reconnect.

Remaining risk: Requires live REALITY client check.

Release blocking: NO

---

### R07 — Python compatibility

Status: PARTIAL

Conclusion: Accountd avoids `tomllib`, `datetime.UTC`, `match`, PEP604 unions in runtime annotations beyond `from __future__ import annotations` + `typing.Optional`. Targets 3.10+. Verified `py_compile` on WSL **Python 3.13.12**, not a native 3.10 interpreter in this run.

Code evidence: module docstring “Targets Python 3.10+”; `timezone.utc`; simple TOML parser.

Test evidence: `python3 -m py_compile lib/vincula-accountd.py` OK; AST scan clean for match/tomllib/UTC.

Remaining risk: Confirm once on Ubuntu 22.04 python3.10.

Release blocking: NO

---

### R08 — accountd runtime user

Status: PASS

Conclusion: Runs as **root**. Required because installer creates `/etc/vincula/config.toml` and `/var/lib/vincula/accounting.db` as root `0600` / dir `0700`, and daemon must read settings secret + write DB.

Code evidence: `lib/vincula-accountd.service` `User=root` / `Group=root` (L11–12).

Test evidence: unit file present in tree; static review.

Remaining risk: Broader privilege surface than a dedicated user — mitigated by hardening (R09).

Release blocking: NO

---

### R09 — accountd systemd hardening

Status: PARTIAL

Conclusion: Unit sets `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=true`, `ReadWritePaths=/var/lib/vincula`, empty `CapabilityBoundingSet`, `LockPersonality`, `RestrictSUIDSGID`. `systemd-analyze security` score not captured on a live unit load.

Code evidence: `lib/vincula-accountd.service` L17–23; installer `validate_accounting_artifacts` runs `systemd-analyze verify` when available (~1827–1828).

Test evidence: file content review; live `systemd-analyze security` UNKNOWN.

Remaining risk: Residual attack surface as root.

Release blocking: NO

---

### R10 — SQLite transaction model

Status: PASS

Conclusion: WAL, busy_timeout=5000, foreign_keys=ON enabled; tick path uses explicit `conn.commit()` after mutations.

Code evidence: `open_db` PRAGMAs (~308–311); `AccountDaemon._tick` commit (~807).

Test evidence: ingest/open_db paths in tests succeed under WAL.

Remaining risk: None material.

Release blocking: NO

---

### R11 — duplicate counting after collector crash

Status: PASS

Conclusion: In-memory baselines reset on process restart; first re-sight of same Clash counters is baseline (zero new delta), then only positive deltas accumulate — prior absolute counters are not re-added.

Code evidence: `apply_poll_delta` first-sight baseline (~583–596); tests assert 1000→0 accounted then +500.

Test evidence: `tests/test.sh` “event parse + rollup + stale close + poll baseline”; synthetic restart probe.

Remaining risk: JSONL path uses absolute event bytes (different ingest model).

Release blocking: NO

---

### R12 — active connection baseline after restart

Status: PASS

Conclusion: First sight after restart stores Clash counters as baseline with zero accounted delta; existing multi-GB counters are not treated as new traffic.

Code evidence: same as R11 (~583–596).

Test evidence: baseline assert in test 202.

Remaining risk: None material.

Release blocking: NO

---

### R13 — sing-box restart / counter reset

Status: PASS

Conclusion: Counter decrease starts a new generation (reset baseline, delta=0); no negative writes.

Code evidence: `apply_poll_delta` (~603–608).

Test evidence: covered by poll baseline logic + synthetic decrease case in gate probes.

Remaining risk: Brief gap while sing-box restarts may miss short flows (approximate model).

Release blocking: NO

---

### R14 — short connection coverage

Status: PASS

Conclusion: Backend is **polling** (default 5s). Short connections can be missed. Docs explicitly state approximate — not Reliable Accounting.

Code evidence: module docstring L3–9; `docs/accounting-reliability.md`; README/CHANGELOG.

Test evidence: documentation presence test; no micro-timing live measure (would still be approximate).

Remaining risk: Inherent to polling.

Release blocking: NO

---

### R15 — day boundary

Status: PASS

Conclusion: UTC calendar day.

Code evidence: `utc_today` / docstring L14–15; stats help “UTC days”.

Test evidence: code review + stats labeling.

Remaining risk: Operators expecting local TZ must convert.

Release blocking: NO

---

### R16 — connection crossing midnight

Status: PASS

Conclusion: Daily rollup uses **UTC date of `closed_at`** (entire connection counted on close day). Raw row retains full interval.

Code evidence: docstring L14–15; `rollup_daily_usage` uses closed_at date.

Test evidence: rollup unit path; no live 23:59 traffic capture.

Remaining risk: Long-lived sessions closing after midnight attribute all bytes to day 2 by design.

Release blocking: NO

---

### R17 — IP-only traffic

Status: PASS

Conclusion: `destination_host` may be NULL; `destination_ip` stored; no rDNS.

Code evidence: `normalize_destination_host` returns None; schema allows NULL host; stale-open test uses `destination_host: None`.

Test evidence: test 202 stale row with NULL host.

Remaining risk: None material.

Release blocking: NO

---

### R18 — destination normalization

Status: PASS

Conclusion: lowercase + strip trailing dots. No IDNA conversion beyond that.

Code evidence: `normalize_destination_host` (~107–114).

Test evidence: ok “destination host normalized lowercase strip dot”.

Remaining risk: IDN variants may not collapse.

Release blocking: NO

---

### R19 — disk full

Status: UNKNOWN

Conclusion: Not fault-injected on a full filesystem. Code surfaces SQLite errors via exceptions / warnings on poll failure; no silent success path identified, but behavior under ENOSPC unproven.

Code evidence: poll failures logged; DB open failures exit.

Test evidence: none for disk-full.

Remaining risk: Release limitation — needs F12 on real host.

Release blocking: NO (documented UNKNOWN)

---

### R20 — DB corruption

Status: PASS

Conclusion: Fail-closed: corrupt file raises `SystemExit` after integrity/open errors; does not wipe into empty schema.

Code evidence: `open_db` (~303–330).

Test evidence: gate probe F13 PASS (`file is not a database` → SystemExit).

Remaining risk: Operator must restore from migration backup / off-box backup.

Release blocking: NO

---

### R21 — retention locking

Status: PARTIAL

Conclusion: Retention runs inside the same tick transaction after rollup, then single `commit`. No long multi-connection lock beyond that tick. Concurrent writer contention not load-tested.

Code evidence: `_tick` (~804–807); `apply_retention` (~672).

Test evidence: code review only.

Remaining risk: Large DB prune duration under load UNKNOWN.

Release blocking: NO

---

### R22 — DB schema version

Status: PASS

Conclusion: Explicit integer `meta.schema_version`; `migrate_schema` N→2; failure exits; not “CREATE IF NOT EXISTS forever”.

Code evidence: `SCHEMA_VERSION = 2`; `migrate_schema` (~197–291).

Test evidence: ok “meta.schema_version is 2”.

Remaining risk: Future N→N+1 must stay explicit.

Release blocking: NO

---

### R23 — uninstall DB semantics

Status: PASS

Conclusion: Uninstall removes accounting DB/events; confirm text states historical accounting data permanently removed.

Code evidence: `bin/vincula` (~704); removal list includes `ACCOUNTING_DB_FILE` / `EVENTS_JSONL_FILE`.

Test evidence: ok “helper uninstall mentions historical accounting data”.

Remaining risk: None material.

Release blocking: NO

---

### R24 — stale stats behavior

Status: PASS

Conclusion: `vcl stats` / `vcl connections` call `warn_if_accounting_stale`: inactive accountd or `last_success_at` >5m prints WARNING that data is not live.

Code evidence: `bin/vincula` `warn_if_accounting_stale` (~1431); callers (~1471, ~1560).

Test evidence: ok “stats/connections warn on stale accounting”.

Remaining risk: Warning is stderr; scripts parsing stdout must still treat rows as historical.

Release blocking: NO

---

### R25 — event schema enforcement

Status: PARTIAL

Conclusion: `vincula-event.schema.json` is validated as JSON at install (`python3 -m json.tool`) and shipped for documentation/contracts. Runtime ingest uses hand parsers, **not** a JSON Schema validator library.

Code evidence: `validate_accounting_artifacts` (~1825–1826); no `jsonschema` usage in accountd.

Test evidence: schema file present; parse tests use hand parser.

Remaining risk: Invalid events may be skipped/logged rather than schema-rejected.

Release blocking: NO

---

## 9. Fault Injection Report F01–F15

| ID | Expected | Actual | Status |
| --- | --- | --- | --- |
| F01 accountd Python syntax error | `py_compile` / enable fails → install die before commit | Static validate calls `py_compile`; hard-fail path present. Live broken-file install not run. | PARTIAL |
| F02 accountd unit invalid | `systemd-analyze verify` fails → die | Code path present when `systemd-analyze` exists. Live bad unit not injected. | PARTIAL |
| F03 accountd cannot start | enable/start or health fail → die, no commit | `enable_accountd_service` + `wait_for_accountd_healthy \|\| die`; tests assert no soft `log_warn`. Live stop-injection not run. | PARTIAL |
| F04 Clash API unavailable | health fail → die | Health requires Clash GET success. Live stop clash not run. | PARTIAL |
| F05 Clash API wrong secret | health fail | Explicit wrong/empty secret rejection in health. Live curl not run. | PARTIAL |
| F06 existing accounting.db before fresh install | preflight die | Code checks DB/events/var-lib; unit tests assert presence. | PASS (code+unit) |
| F07 migration after DB creation | backup DB + migrate schema | Backup uses sqlite `.backup`/cp; schema migrate on start. Live migrate not run. | PARTIAL |
| F08 DB migration failure | fail-closed, no commit / rollback | Unmapped tag→user_id raises SystemExit. Live migrate fail not run. | PARTIAL |
| F09 SIGTERM during migration | rollback via EXIT trap | `on_exit` calls `rollback_migration` if uncommitted. Live SIGTERM not run. | UNKNOWN |
| F10 accountd crash during traffic | no double-count after restart | R11/R12 logic + unit baseline. Live crash not run. | PARTIAL |
| F11 sing-box restart during traffic | no negative/bogus delta | R13 counter-decrease logic. Live restart not run. | PARTIAL |
| F12 disk full / SQLite write failure | error, no silent success | Not injected. | UNKNOWN |
| F13 corrupted SQLite DB | refuse start, no wipe | Probe: SystemExit on garbage file. | PASS |
| F14 user rotate during active connection | history by user_id continues; new UUID in config | Debian 13: rotate kept `user_id`, old UUID rejected | PASS (spot) |
| F15 disabled user attempts reconnect | connect fails; history kept | Debian 13: removed from inbound; history queryable; re-enable OK | PASS (spot) |

---

## 10. Test matrix results

| Matrix | Result |
| --- | --- |
| Unit / static (`bash tests/test.sh`) | **207/207 PASS** (WSL2) |
| `bash -n` installer/helper | PASS |
| `python3 -m py_compile lib/vincula-accountd.py` | PASS |
| `scripts/gen-release-lock.sh` | PASS |
| Fresh install Debian 13 amd64 | **PASS** (2026-08-15 spot-check; post sniff + user-mutation fixes) |
| Fresh install Debian 12 / Ubuntu 22.04 / 24.04 / arm64 | **UNKNOWN** |
| Migration `0.1.5`/`0.2.0`/`0.2.2`/`0.2.3` → `0.2.4` + forced rollback | **UNKNOWN** |
| Live REALITY client + accounting (owner) on Debian 13 | **PASS** (spot-check) |
| user add / rotate / disable on Debian 13 | **PASS** (after helper fix) |
| Reboot dual-plane | **UNKNOWN** |
| Full F01–F15 | **PARTIAL** (see known-issues) |

---

## 11. Remaining P1/P2

见 [`known-issues-0.2.4.md`](known-issues-0.2.4.md)。摘要：

- P0/RC：补 migration + forced rollback；至少再一台 Ubuntu 22.04
- P1：剩余故障注入、reboot、bootstrap 篡改、Python 3.10 实机
- P2：非 root accountd、runtime JSON Schema、Reliable Accounting

---

## 12. Release recommendation

**READY WITH DOCUMENTED LIMITATIONS**

Justification:

- P0 生命周期与数据模型修复已在树内；单元测试 207 PASS。
- Debian 13 实机主路径与用户生命周期 spot-check PASS。
- Accounting 仍为 **approximate**（产品限制）。
- OS 矩阵 / migration rollback / 完整 F 注入等仍有 UNKNOWN → **不得** `READY FOR RC`。

Before promoting to RC: follow [`rc-test-manual-0.2.4.md`](rc-test-manual-0.2.4.md), close items in [`known-issues-0.2.4.md`](known-issues-0.2.4.md), re-score UNKNOWN → PASS/FAIL, then update this document’s recommendation.
