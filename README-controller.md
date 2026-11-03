# Vincula controller (`vcl-fleet`)

当前收口候选：Node/Controller **0.5.5**，accounting/fleet-cache **schema 5**；迁移、容量策略与验收状态见 [0.5.5 runbook](docs/operations/0.5.5-closeout-runbook.md)。 历史段落仍绑定原版本，不代表新候选已验收。
Workstation Fleet Users & Audit CLI. **No root, no systemd, no `/etc/vincula`.**
This zip is a user-local tool: it has no installer and no node `release.lock`.
Integrity: `controller.lock` (per-member SHA-256) inside the zip, plus an
independent sidecar `vincula-controller-<version>.zip.sha256`. Verify with
`sha256sum -c` on the sidecar, then `sha256sum -c controller.lock` after unzip.

Runtime siblings next to `lib/vincula-fleet.py` include `vincula-audit.py`,
`vincula-backup.py`, `vincula-audit-archive.py`, `workspace.py`, `access.py`,
`trust.py`, `provision.py`, `legacy_seed.py`, and `vincula-ui/` (Local Audit UI).

**Development candidate (0.5.5):** Controller and embedded Node payload
are both `0.5.5` (minimum Node remains `0.3.1`). Includes the SSH credential manager
v2: deterministic Agent-fingerprint and Identity-File modes, machine-local public-key
selectors, `CREDENTIAL_MIGRATION_REQUIRED`, and `access migrate`. Connections use
`-F <null config>`, an explicit `-i`, and `IdentitiesOnly=yes`; OpenSSH no longer
walks default/config identities. `~/.ssh/config` is intentionally ignored for VCL
connections (ProxyJump/ProxyCommand/custom Host aliases do not apply).

Includes read-only Inspect, machine-local inspection cache, explicit SHA-based
baseline acceptance, seven Drift findings and baseline Timeline events.
`inspect [NODE] --json` and `GET /api/inspect` read local caches. The UI displays
observation, baseline and comparison summaries.

`monitor --json` uses `monitor/v3`; `health` and `GET /api/monitor` remain `monitor/v1`.
`findings` and `timeline` use v2; frozen v1 schemas remain packaged.
`verify --extended [--name NODE] --json` uses observe credentials and eight explicit
checks. Data Plane stays UNKNOWN unless `--probe-profiles` explicitly runs a
private dedicated proxy probe and the post-probe identity still matches.
Invalid or contradictory probe results remain UNKNOWN. A failed post-probe
identity check discards the earlier snapshot and reports AUTH_FAILED, TIMEOUT
or ERROR; checks from a replaced instance are not shown as current evidence.
Legacy `verify --json` is unchanged for upgrade/restore consumers.

Typed upgrade supports 0.3.1/0.3.2/0.5.0/0.5.1/0.5.2/0.5.3 → 0.5.5.
Seventeen public schemas ship under `schemas/` with `controller.lock`.
Accounting and fleet-cache schema 5 use verified staged migrations. Independent
daily history survives raw pruning. `cache status --json` reports the local
8 GiB cap, 80% warning and 512 MiB free-space floor; over-limit imports stop
without deleting history. Node secrets use descriptors/private inputs, and Agent
selector publication isolates refs and failed rebindings.

The candidate is unreleased; Live, the new RC 24h soak and H05 remain pending.
The approved scale is seven real mixed nodes plus ten simulated nodes for two
hours. Current results and restrictions are in `docs/evidence/0.5.5/SUMMARY.md`.
Development stops before 0.6.x until H05 is signed PASS.



Requires **Python 3.10+** and the **system OpenSSH client**. Vincula does not
bundle CPython or `ssh`.

Full operator guide (repo): `docs/user-guide.md`. Architecture and contracts:
`docs/technical-guide.md`. Spec: `docs/specs/V0.5.4_SSH_Credential_Management.md`. Evidence:
`docs/evidence/0.5.4/CREDENTIALS.md`. Findings: `docs/operations/findings-runbook.md`.
Inspect / baseline / Drift / Verify: `docs/operations/inspect-runbook.md`.
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
