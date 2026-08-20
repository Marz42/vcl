# B21 — Fresh install live acceptance (0.3.1-rc2)

**Result: PASS** (operator live run, 2026-08-20)

| Item | Value |
| --- | --- |
| Artifact | `vincula-node-0.3.1-rc2.tar.gz` |
| SHA256 | `ce80645029aefe075097156e1f2929ca1ac0e0370224d0d48bc68e5c84c93d92` |
| Path | Fresh VPS (no prior `/etc/vincula/VERSION`) |
| Provisioning | `vcl-fleet user add` (normal management path) |
| Reboot | PASS — both services restored; URI still worked |

## Checklist

| Gate | Result |
| --- | --- |
| Artifact SHA256 | PASS |
| Fresh install exit 0 / no rollback | PASS |
| `sing-box` + `vincula-accountd` enabled+active | PASS |
| `vcl version` = `0.3.1-rc2` | PASS |
| accounting schema = **4** | PASS |
| `vcl status` / `check` / `verify` / `accounting check` | PASS |
| Fleet user add + real client VLESS+REALITY+Vision | PASS |
| Public traffic + stats/audit (with `audit user TAG`) | PASS |
| Reboot smoke | PASS |

## Notes

- Node `vcl audit` requires `user TAG` or `--user-id` (not bare `--from`/`--to`).
- Fleet registration + sync exercised on the same workstation fleet that already had another node.

Tag for artifacts: `v0.3.1-rc2` @ `63755b5`.
