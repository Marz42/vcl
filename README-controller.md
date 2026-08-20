# Vincula controller (`vcl-fleet`)

Workstation Fleet Users & Audit CLI. **No root, no systemd, no `/etc/vincula`.**
This zip is a user-local tool: it has no installer and no node `release.lock`.
Integrity: `controller.lock` (per-member SHA-256) inside the zip, plus an
independent sidecar `vincula-controller-<version>.zip.sha256`. Verify with
`sha256sum -c` on the sidecar, then `sha256sum -c controller.lock` after unzip.
Runtime siblings next to `lib/vincula-fleet.py` are `vincula-audit.py`,
`vincula-backup.py`, and `vincula-ui/` (Local Audit UI static + stdlib HTTP).
Required for `audit`, local backup verify, and `vcl-fleet ui`.

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

Config directory: `%APPDATA%\vincula\` (usually
`C:\Users\<user>\AppData\Roaming\vincula`). Override with `VCL_FLEET_HOME`.

SSH uses your user `known_hosts` (`%USERPROFILE%\.ssh\known_hosts`).

```bat
bin\vcl-fleet.cmd user add alice --nodes lax,tokyo --display-name Alice
bin\vcl-fleet.cmd sync
bin\vcl-fleet.cmd ui
bin\vcl-fleet.cmd node replace lax --host 203.0.113.18 --host-key SHA256:...
bin\vcl-fleet.cmd node instances lax
```

`ui` opens a **localhost-only** read-only Local Audit UI (default
`http://127.0.0.1:8765`). Non-loopback binds are refused. Mutations stay on
the CLI (recipes panel copies commands only).
## Linux / macOS

Python 3.10+ and OpenSSH (`ssh` on PATH):

```bash
python3 bin/vcl-fleet version
```

Config directory: `${XDG_CONFIG_HOME:-~/.config}/vincula/`.
Override with `VCL_FLEET_HOME`.

```bash
python3 bin/vcl-fleet user add alice --nodes lax,tokyo --display-name Alice
python3 bin/vcl-fleet sync
python3 bin/vcl-fleet ui
python3 bin/vcl-fleet node replace lax --host 203.0.113.18 --host-key SHA256:...
python3 bin/vcl-fleet node instances lax
```

Operator guide (PARTIAL, `CURSOR_EXPIRED`, retire, **replace vs rebind**):
see the repo `docs/fleet.md` and `docs/backup.md` (not shipped in this zip).

`node set` is endpoint rebind (credentials stay). `node replace` is
physical replacement onto a runtime-only host (`vincula.sh --runtime-only`,
then `vcl restore --reissue-output`). `node instances NAME` lists physical
instances over time. **B14 live replace PASS (2026-08-18)** —
`docs/live-replace-checklist.md` · `docs/evidence/0.3.1-live/SUMMARY.md`.
Gate: `docs/release-readiness-0.3.1.md` (remaining: live `0.3.0 → 0.3.1-rc1` upgrade).
