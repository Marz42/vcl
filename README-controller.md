# Vincula controller (`vcl-fleet`)

Workstation Fleet Users & Audit CLI. **No root, no systemd, no `/etc/vincula`.**
This zip is a user-local tool: it has no installer and no node `release.lock`.
Integrity: `controller.lock` (per-member SHA-256) inside the zip, plus an
independent sidecar `vincula-controller-<version>.zip.sha256`. Verify with
`sha256sum -c` on the sidecar, then `sha256sum -c controller.lock` after unzip.
Runtime siblings next to `lib/vincula-fleet.py` are `vincula-audit.py`,
`vincula-backup.py`, `vincula-audit-archive.py`, `workspace.py`, `access.py`,
`trust.py`, and `vincula-ui/` (Local Audit UI static + stdlib HTTP).
Required for `audit` / archive, local backup verify, workspace, and `vcl-fleet ui`.

**Stamp (0.4.2 tree):** controller `VCL_FLEET_VERSION=0.4.2`; remote nodes remain
`VINCULA_VERSION=0.3.1` (node helper is still `vcl`). **0.4.3** is in progress
(docs first; stamp stays `0.4.2` until 0.4.3 closes).

Requires **Python 3.10+** and the **system OpenSSH client**. Vincula does not
bundle CPython or `ssh`.

## Windows 11

1. Install Python 3.10 or newer (enable “Add python.exe to PATH”).
2. Install **OpenSSH Client** (Settings → Apps → Optional features). Use the
   system `ssh.exe` / `scp.exe` / `ssh-keyscan.exe`.
3. Unzip `vincula-controller-<version>.zip`.
4. From the unzipped folder:

```bat
py -3 bin\vcl-fleet.cmd version
bin\vcl-fleet.cmd help
```

`bin\vcl-fleet.cmd` locates `lib\vincula-fleet.py` beside `bin\` or one level up.

**Paths (0.4.2):** portable workspace root = `VCL_FLEET_HOME` /
`--workspace` / `%APPDATA%\vincula\` — holds only `workspace.json`,
`fleet.json`, `trust/`, `history/`. Machine-local bindings + `controller.json`
live under `%APPDATA%\vincula\controllers\<fleet_id>\`. Cache `fleet.db`
(fleet-cache/v4) and UI runtime under `%LOCALAPPDATA%\vincula\<fleet_id>\`
(override `VCL_FLEET_LOCAL_STATE`). Legacy `machine-local/` is migrate-only.

SSH host keys: workspace `trust/known_hosts` when workspace is active
(`StrictHostKeyChecking=yes`).

```bat
bin\vcl-fleet.cmd workspace init
bin\vcl-fleet.cmd access bind admin --identity-file %USERPROFILE%\.ssh\id_ed25519
bin\vcl-fleet.cmd user add alice --nodes lax,tokyo --display-name Alice
bin\vcl-fleet.cmd sync --full
bin\vcl-fleet.cmd status
bin\vcl-fleet.cmd probe
bin\vcl-fleet.cmd ui
bin\vcl-fleet.cmd node replace lax --host 203.0.113.18 --host-key SHA256:...
bin\vcl-fleet.cmd node instances lax
```

`status` is **cache-only** (no SSH; health from `sync --full` →
`node_snapshot`). Live health: `probe` (`status --live` is a deprecated alias).
`ui` opens a **localhost-only** read-only Local Audit UI (default
`http://127.0.0.1:8765`). Non-loopback binds are refused. Mutations stay on
the CLI (recipes panel copies commands only).

## Linux / macOS

Python 3.10+ and OpenSSH (`ssh` on PATH):

```bash
python3 bin/vcl-fleet version
```

Portable root: `${XDG_CONFIG_HOME:-~/.config}/vincula/` (or `VCL_FLEET_HOME` /
`--workspace`). CONFIG bindings:
`${XDG_CONFIG_HOME:-~/.config}/vincula/controllers/<fleet_id>/`.
STATE cache: `${XDG_STATE_HOME:-~/.local/state}/vincula/<fleet_id>/`.

```bash
python3 bin/vcl-fleet workspace init
python3 bin/vcl-fleet access bind admin --identity-file ~/.ssh/id_ed25519
python3 bin/vcl-fleet user add alice --nodes lax,tokyo --display-name Alice
python3 bin/vcl-fleet sync --full
python3 bin/vcl-fleet status
python3 bin/vcl-fleet probe
python3 bin/vcl-fleet audit archive create --from … --to … --output out.vclaudit
python3 bin/vcl-fleet ui
python3 bin/vcl-fleet node replace lax --host 203.0.113.18 --host-key SHA256:...
python3 bin/vcl-fleet node instances lax
```

Operator guide (workspace, `sync --full`, PARTIAL, `CURSOR_EXPIRED`, retire,
**replace vs rebind**): see the repo `docs/fleet.md` and `docs/backup.md`
(not shipped in this zip). Schema names (D45): fleet-registry/v2,
fleet-cache/v4, workspace/v1, audit-archive/v1.

`node set` is endpoint rebind (credentials stay). `node replace` is
physical replacement onto a runtime-only host (`vincula.sh --runtime-only`,
then `vcl restore --reissue-output`). `node instances NAME` lists physical
instances over time. **B14 live replace PASS (2026-08-18)** —
`docs/live-replace-checklist.md` · `docs/evidence/0.3.1-live/SUMMARY.md`.
0.4.2 evidence: `docs/evidence/0.4.2/SUMMARY.md`.
