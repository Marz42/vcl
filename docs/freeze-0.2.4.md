# Vincula 0.2.4 Freeze Record

**Freeze date:** 2026-08-15  
**Policy:** After this freeze, **0.2.4 only accepts P0/P1 regression fixes** (install/migrate/rollback/data correctness). No new features / stats / Reliable Accounting in 0.2.4.

**Gate recommendation:** `READY WITH DOCUMENTED LIMITATIONS` → freeze candidate with **V-MIG / V-RB / V-PY310 PASS** (see below). Remaining OS-matrix / F-inject gaps stay documented.

---

## Provenance of 0.2.3 baseline

No `v0.2.3` tag exists in this git history (repo initialized at 0.2.4). Freeze tests used a **0.2.3-shaped morph** of a live install:

1. Healthy 0.2.4 install
2. `scripts/freeze-morph-to-0.2.3.sh` → `VERSION=0.2.3`, inbound `"sniff": true`, `node_id=local`
3. Confirmed `sing-box 1.13.18 check` **FATAL** on that config (legacy inbound)
4. Migrate with 0.2.4 installer

Also provided: `scripts/build-reconstructed-0.2.3.sh` → `artifacts/vincula-0.2.3/` (reconstructed release tree with inbound sniff + soft-fail accountd + `node_id=local`).

---

## Gate results

### A — 0.2.3 → 0.2.4 migration (PASS)

| Check | Result |
| --- | --- |
| Host | Debian 13 amd64 (`104.194.90.172`) |
| Legacy pre-check | Warned + continued (P0) |
| Owner UUID preserved | PASS (`d012b784-…`) |
| Reality pk / short_id | PASS |
| `node_id` left `local` | PASS (new UUID assigned) |
| Config without inbound sniff | PASS (`action: sniff` present) |
| Dual services active + `vcl verify` | PASS |
| Evidence | `/root/vcl-rc-evidence/freeze/migrate-happy.log` on test host |

### B — Forced mid-migration failure → rollback (PASS)

| Check | Result |
| --- | --- |
| Injection | Broken `lib/vincula-accountd.py` in release tree (py_compile fail after `MIGRATION_STARTED`) |
| Non-zero exit | PASS |
| `VERSION` restored `0.2.3` | PASS |
| Broken accountd not left installed | PASS |
| Backup `SERVICE_STATE` present | PASS |
| UUID preserved across rollback + re-migrate | PASS |
| Evidence | `/root/vcl-rc-evidence/freeze/migrate-rollback.log` |

### C — Ubuntu 22.04 / Python 3.10 (PASS)

| Check | Result |
| --- | --- |
| Environment | Docker `ubuntu:22.04` |
| `python3 --version` | **3.10.12** |
| `python3 -m py_compile lib/vincula-accountd.py` | **PY310_COMPILE_OK** |
| Live accountd on Ubuntu 22.04 systemd | Not run in-container (no stable systemd image this session); Debian 13 live active after migration used as operational cross-check |

---

## P0 code landed for freeze

In [`vincula.sh`](../vincula.sh) `migrate_existing_install`:

- Prefer `owner_active_uuid_from_registry` for owner UUID
- If `sing-box check` fails with legacy inbound / 1.13 removed fields → **warn and continue**
- Skip pre-migration `wait_for_service` when legacy config cannot run on 1.13
- Regenerated config remains authoritative

---

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/build-reconstructed-0.2.3.sh` | Build `artifacts/vincula-0.2.3` |
| `scripts/freeze-morph-to-0.2.3.sh` | Morph live install to 0.2.3-shaped |
| `scripts/freeze-run-ubuntu2204.sh` | Full A/B/C runner for Ubuntu 22.04+systemd |
| `scripts/freeze-docker-entrypoint.sh` | Container entry helper |

---

## Post-freeze policy

Allowed in 0.2.4:

- P0/P1 regression: install fail-closed, migration/rollback, accounting identity, packaging hash, crashers

Not allowed in 0.2.4:

- New protocols, fleet, billing, Reliable Accounting, new stats surfaces, non-root redesign (→ 0.2.5+)
