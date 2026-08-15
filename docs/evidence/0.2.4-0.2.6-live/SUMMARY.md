# Vincula live upgrade 0.2.4 → 0.2.6

- Host: hot-beam-1.localdomain (`104.194.90.172`)
- Date: 2026-08-15 UTC
- OS: Debian GNU/Linux 13 (trixie) amd64
- Python: 3.13.5
- Operator: automated `scripts/rc-live-upgrade-driver.sh`
- Artifacts: git tags `v0.2.4` / `v0.2.5` / `v0.2.6` via `scripts/rc-build-artifacts.sh`

**Overall: PASS** (all phases)

| Check | Result | Notes |
| --- | --- | --- |
| 00-preflight-clean | PASS | host ready |
| 01-install-024 | PASS | VERSION=0.2.4 services+verify |
| 02-clash-triad | PASS | localhost auth ok |
| 02-user-add | PASS | rc24alice |
| 02-baseline-024 | PASS | status/check/link |
| 03-remove-refused | PASS | exit=2 |
| 03-migrate-025 | PASS | identity+user suite |
| 04-stats-approx-label | PASS | present |
| 04-stats-stale-warn | PASS | warned |
| 04-connections-unavailable | PASS | failed closed |
| 04-migrate-026 | PASS | stats suite |
| 05-reboot | PASS | dual-plane ok |
| 06-accountd-py-ok | PASS | compiled |
| 06-backup-present | PASS | SERVICE_STATE found |
| 06-rollback | PASS | VERSION restored to 0.2.5 |
| 07-reinstall-026 | PASS | clean 0.2.6 ok |

Identity continuity (owner UUID / Reality / node_id / clash secret) preserved across 0.2.4→0.2.5 and 0.2.5→0.2.6 (see compare.txt under phase dirs). Forced rollback with broken `vincula-accountd.py` restored VERSION=0.2.5.

VPS full logs: `/root/vcl-rc-evidence/upgrade-246/`. Local mirror: `remote-copy/` (credential CSVs redacted from git).
