# Live replace evidence (0.3.1)

**Result: PASS** on two public VPS, 2026-08-18.

| Role | Host | OS |
| --- | --- | --- |
| OLD → retired | `104.194.90.172` | Debian 13 amd64 |
| NEW (active) | `179.255.104.167` | Ubuntu 26.04 amd64 |
| Unix controller | WSL2 on Win11 | `vcl-fleet` (tree was `0.3.1-dev` @ `1137423` at run time) |
| Win11 controller | same workstation | `bin\vcl-fleet.cmd` + system OpenSSH |

Artifacts at run time: `dist/vincula-node-0.3.1-dev.tar.gz` + `dist/vincula-controller-0.3.1-dev.zip`. Living tree is now **`0.3.1`**; B14 status remains **PASS**.

Operator runbook: [`../../live-replace-checklist.md`](../../live-replace-checklist.md).  
See [`SUMMARY.md`](SUMMARY.md). Full host logs may live under `/root/vcl-rc-evidence/0.3.1-live/` (not mirrored).  
Do **not** commit VLESS URIs, reissue CSV, age identity files, or SSH private keys.
