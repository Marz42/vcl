# Vincula controller (`vcl-fleet`)

Workstation Fleet Users & Audit CLI. **No root, no systemd, no `/etc/vincula`.**
This zip is a user-local tool: it has no installer and no node `release.lock`.
Integrity: `controller.lock` (per-member SHA-256) inside the zip, plus an
independent sidecar `vincula-controller-<version>.zip.sha256`. Verify with
`sha256sum -c` on the sidecar, then `sha256sum -c controller.lock` after unzip.

Runtime siblings next to `lib/vincula-fleet.py` include `vincula-audit.py`,
`vincula-backup.py`, `vincula-audit-archive.py`, `workspace.py`, `access.py`,
`trust.py`, `provision.py`, `legacy_seed.py`, and `vincula-ui/` (Local Audit UI).

**Development candidate (0.5.2):** Controller and embedded Node payload are `0.5.2`
(minimum Node remains `0.3.1`). Adds cache-only `findings` and `timeline`, Node/User
anomalies, independent audit diagnostics and bounded user traffic samples.
`monitor --json` uses `monitor/v2`; `health --json` and the read-only monitoring API
retain `monitor/v1`. All public JSON schemas ship under `schemas/` and are covered
by `controller.lock`. Older Nodes retain capability-based observation support;
unavailable diagnostics show UNKNOWN. Typed upgrade supports Node
0.3.1/0.3.2/0.5.0/0.5.1 → 0.5.2. Human Gate and real VPS/24h soak checks are
pending and recorded as deferred; this candidate remains unreleased.

**0.5.3 work in progress:** Node `inspect/v1` and the internal identity-bound
observe fetch are included in this development tree and its packages. Controller
inspect/cache/baseline/Drift and enhanced Verify remain unimplemented. Runtime
stamps stay 0.5.2 until the full version is complete; 0.5.2 evidence does not
validate these additions. See `docs/evidence/0.5.3/SUMMARY.md`.

Requires **Python 3.10+** and the **system OpenSSH client**. Vincula does not
bundle CPython or `ssh`.

Full operator guide (repo): `docs/user-guide.md`. Architecture and contracts:
`docs/technical-guide.md`. Spec: `docs/specs/V0.5.2_Spec.md`. Evidence:
`docs/evidence/0.5.2/SUMMARY.md`. Findings: `docs/operations/findings-runbook.md`.
Monitoring and dedicated probe setup: `docs/operations/monitoring-runbook.md`.

## Windows 11

1. Install Python 3.10+ (enable “Add python.exe to PATH”).
2. Install **OpenSSH Client** (Settings → Apps → Optional features).
3. Unzip `vincula-controller-<version>.zip`.
4. From the unzipped folder:

```bat
py -3 bin\vcl-fleet.cmd version
bin\vcl-fleet.cmd help
bin\vcl-fleet.cmd init
bin\vcl-fleet.cmd access bind admin --identity-file %USERPROFILE%\.ssh\id_ed25519
bin\vcl-fleet.cmd node provision NAME --host HOST --host-key SHA256:… --server HOST
bin\vcl-fleet.cmd sync --full
bin\vcl-fleet.cmd status
bin\vcl-fleet.cmd probe
bin\vcl-fleet.cmd ui
```

`bin\vcl-fleet.cmd` locates `lib\vincula-fleet.py` beside `bin\` or one level up.

**Paths:** portable workspace = `VCL_FLEET_HOME` / `--workspace` /
`%APPDATA%\vincula\` (`workspace.json`, `fleet.json`, `trust/`, `history/`).
Machine-local bindings under `%APPDATA%\vincula\controllers\<fleet_id>\`.
Cache `fleet.db` (fleet-cache/v4) and UI runtime under
`%LOCALAPPDATA%\vincula\<fleet_id>\` (override `VCL_FLEET_LOCAL_STATE`).

## Linux / macOS

```bash
python3 bin/vcl-fleet version
python3 bin/vcl-fleet init
python3 bin/vcl-fleet access bind admin --identity-file ~/.ssh/id_ed25519
python3 bin/vcl-fleet sync --full
python3 bin/vcl-fleet status
python3 bin/vcl-fleet probe
python3 bin/vcl-fleet ui
```

Portable root: `${XDG_CONFIG_HOME:-~/.config}/vincula/`. STATE cache:
`${XDG_STATE_HOME:-~/.local/state}/vincula/<fleet_id>/`.

## Notes

- `status` is **cache-only** (no SSH). Live health: `probe`.
- `ui` is **localhost-only** (default `http://127.0.0.1:8765`). Non-loopback
  binds are refused. Mutations stay on the CLI; Command Builder copies only.
- `node set` = endpoint rebind (credentials stay). `node replace` = physical
  replacement onto a **runtime-only** host (`vincula.sh --runtime-only`, then
  remote `vcl restore --reissue-output`). See repo
  `docs/operations/node-replace-runbook.md`.
- There is **no** `--replace-node` flag on node `vcl restore`.
