# Fleet operator guide (0.2.8)

Workstation **Fleet Foundation** controller. It registers nodes, then runs
read-only remote `vcl identity|status|verify --json` over **system OpenSSH**.
It does not listen on a port, does not run as root, and does not use
`/etc/vincula`.

SPEC `vcl fleet <sub>` **≡** this binary: `vcl-fleet <sub>`. The node helper
`vcl` / `vincula` has **no** `fleet` subcommand.

Full identity contract: [`identity.md`](identity.md).

## Prerequisites

| | |
| --- | --- |
| Python | **3.10+** on PATH (`py -3` / `python` on Windows, `python3` on Unix) |
| SSH | **system OpenSSH client** (`ssh.exe` / `scp.exe` / `ssh-keyscan.exe` on Windows; `ssh` / `scp` / `ssh-keyscan` on Linux/macOS) |
| Node | 0.2.8 (or later) with `vcl identity --json` reachable as the SSH user (default `root`) |
| Not bundled | CPython, OpenSSH, paramiko, pip packages |

Vincula does not ship a management HTTP API. The only workstation → node
channel is SSH.

## Paths

| | |
| --- | --- |
| `VCL_FLEET_HOME` | If set, this directory (required in tests) |
| Windows | `%APPDATA%\vincula\` (usually `C:\Users\<user>\AppData\Roaming\vincula`) |
| Linux / macOS | `${XDG_CONFIG_HOME:-~/.config}/vincula/` |
| Registry | `$FLEET_HOME/fleet.json` (schema 1; **does not store** `instance_id` or passwords) |
| Last probe | `$FLEET_HOME/last-status.json` (health summary, not source of truth) |
| Host keys | user default `known_hosts` (`%USERPROFILE%\.ssh\known_hosts` / `~/.ssh/known_hosts`) |

## Windows 11

1. Install **Python 3.10+** (enable “Add python.exe to PATH”).
2. Install **OpenSSH Client**: Settings → Apps → Optional features.
3. Unzip `vincula-controller-<version>.zip`.
4. From the unzipped folder:

```bat
py -3 bin\vcl-fleet.cmd version
bin\vcl-fleet.cmd help
bin\vcl-fleet.cmd init
```

`bin\vcl-fleet.cmd` locates `lib\vincula-fleet.py` beside `bin\` or one level up.

## Linux / macOS

Python 3.10+ and OpenSSH on PATH:

```bash
python3 bin/vcl-fleet version
python3 bin/vcl-fleet init
```

(Repo checkout also has `bin/vcl-fleet` with a `python3` shebang.)

## CLI

| Command | Purpose |
| --- | --- |
| `vcl-fleet init` | Create empty `fleet.json` (refuses to overwrite a non-empty registry) |
| `vcl-fleet node add NAME --host HOST` | SSH `vcl identity --json` and register |
| `vcl-fleet node list` | `NAME NODE_ID SSH_HOST USER ENABLED` |
| `vcl-fleet node show NAME` | One record |
| `vcl-fleet node set NAME --host NEW_HOST` | Change `ssh_host` only; **`node_id` stays** |
| `vcl-fleet node disable NAME` / `enable NAME` | Flip `enabled` |
| `vcl-fleet status` | Probe table (see below) |
| `vcl-fleet verify` | Aggregate identity / health / clock |
| `vcl-fleet version` | `vcl-fleet 0.2.8` |
| `vcl-fleet help` | Help |

`node add` flags: `--user`, `--port`, `--host-key SHA256:...`, `--offline --node-id UUID`.
`--instance-id` is accepted and **ignored** (not stored).

Not in 0.2.8: `sync`, `user`, `stats`, `audit`, `ui`, `node replace`, `node retire`.

## First node add (`--host-key`)

Non-interactive add (CI, scripts, no TTY) **requires** `--host-key SHA256:...`.
On a TTY, OpenSSH may prompt to confirm the host key.

```bat
bin\vcl-fleet.cmd node add lax --host 203.0.113.10 --host-key SHA256:BASE64FINGERPRINT
```

```bash
python3 bin/vcl-fleet node add lax --host root@203.0.113.10 --host-key SHA256:BASE64FINGERPRINT
```

Flow:

```text
resolve SSH target
→ if --host-key: ssh-keyscan candidates only; match fingerprint; append to user known_hosts
→ ssh with StrictHostKeyChecking=yes (strengthened, never disabled)
→ remote: vcl identity --json
→ refuse duplicate node_id / duplicate name
→ write fleet.json (name, node_id, ssh_host, ssh_user, ssh_port, enabled)
```

`ssh-keyscan` is **candidate acquisition**, not verification. A mismatch fails
and writes nothing.

Offline register (mock / unreachable host, still listed):

```bash
python3 bin/vcl-fleet node add sg --host 203.0.113.12 --offline --node-id <uuid>
```

Changing a node's IP later: `node set` does **not** rewrite `known_hosts`.
Pin again with `--host-key` or edit OpenSSH `known_hosts` yourself.

### Host-key policy (D14)

Default: OpenSSH user `known_hosts`. The controller never passes:

- `StrictHostKeyChecking=no`
- `UserKnownHostsFile=/dev/null`

and never points `UserKnownHostsFile` at an empty file.

## `status` / `verify`

`vcl-fleet status` columns:

```text
NAME      NODE_ID     INSTANCE     SSH      PROXY      ACCOUNTING
lax       <uuid>      <uuid>       OK       OK         OK
tokyo     <uuid>      <uuid>       OK       OK         STALE
sg        <uuid>      <uuid>       FAIL     UNKNOWN    UNKNOWN
```

| Probe | Meaning |
| --- | --- |
| SSH `FAIL`, PROXY/ACCOUNTING `UNKNOWN`, INSTANCE `-` | SSH unreachable (connection refused, host-key failure, timeout) |
| SSH `OK`, PROXY `FAIL` | SSH worked; remote proxy unhealthy |
| SSH `OK`, ACCOUNTING `STALE` | Heartbeat stale (not an SSH failure; status exit 0 if nothing else FAILs) |
| SSH `OK`, ACCOUNTING `FAIL` | Accounting unhealthy, not merely stale |
| all `OK` | Identity + proxy + accounting healthy |

Disabled nodes are omitted unless `--all` (then `DISABLED`). Exit 1 if any
enabled node is SSH/PROXY/ACCOUNTING `FAIL`. `--json` is schema 1.

`vcl-fleet verify` adds version, registry `node_id` match, and clock skew.
A new `instance_id` with the same `node_id` (reinstall) prints
`WARN: instance changed, node_id stable` and does **not** rewrite registry
`node_id`. `--json` includes `warnings` / `checks`.

Clock (visible constants in `lib/vincula-fleet.py`):

```text
CLOCK_SKEW_WARN_SECONDS = 30
CLOCK_SKEW_FAIL_SECONDS = 300
CLOCK_SKEW_FAIL_CHECK = "audit-clock-health"
```

Controller UTC vs remote `utc_now`: drift **> 30s** → WARN (verify may still
PASS); **> 300s** (5 minutes) → FAIL check `audit-clock-health`. Missing
`utc_now` is also that FAIL.

## Remote read-only

Daily operator model:

```text
ssh root@<host> vcl identity --json
ssh root@<host> vcl status --json
ssh root@<host> vcl verify --json
```

Do **not** routinely `scp /var/lib/vincula/accounting.db`. Live SQLite copy is
not a consistent snapshot (0.3.0).

## Tests / mock SSH

```bash
export VCL_FLEET_HOME=/tmp/fleet-home
export VCL_FLEET_SSH=/path/to/tests/fixtures/fake-ssh
export VCL_FLEET_SSH_KEYSCAN=/path/to/tests/fixtures/fake-ssh-keyscan
```

CI uses three fixtures: lax (healthy), tokyo (accounting STALE), sg (SSH FAIL).

## Explicitly not in 0.2.8

incremental audit sync / `fleet.db` / `vcl-fleet user *` / fleet stats / fleet
audit / UI / `replace-node` / backup.

## AC-2.8 matrix (01–10)

| ID | Criterion | Evidence |
| --- | --- | --- |
| AC-2.8-01 | ≥3 nodes registered and listed | `tests/test-fleet.sh` fixtures lax / tokyo / sg; `node list` exactly 3 |
| AC-2.8-02 | No public Vincula management port | Controller has no `socket.bind` / `HTTPServer` / `0.0.0.0`; SSH only. `assert_failure` grep in `tests/test-fleet.sh` |
| AC-2.8-03 | Status distinguishes SSH failure vs remote failure | Table: lax OK/OK/OK, tokyo OK/OK/STALE, sg FAIL/UNKNOWN/UNKNOWN |
| AC-2.8-04 | Stable UUID `node_id` (not recast) | Registry UUIDs; `ac_28_identity`; node mint tests in `tests/test.sh` |
| AC-2.8-05 | Reinstall may mint new `instance_id`; never copy `node_id` | `identity-reinstall.json` same name/`node_id`, different `instance_id`; verify WARN; `fleet.json` unchanged; Phase 4 mint tests |
| AC-2.8-06 | Changing `ssh_host` does not change `node_id` | `vcl-fleet node set`; `ac_28_identity` |
| AC-2.8-07 | Duplicate `node_id` registration refused | Offline and live `node add` of an already-registered `node_id` |
| AC-2.8-08 | Mock SSH covers registry / status / verify / host-key (not incremental sync) | `tests/fixtures/fake-ssh` + `tests/test-fleet.sh` |
| AC-2.8-09 | Controller restart does not lose registry | New process `node list` still shows `sg` |
| AC-2.8-10 | Host-key checking not globally disabled | No `StrictHostKeyChecking=no` / `UserKnownHostsFile=/dev/null` in shipped `lib/vincula-fleet.py`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd`; non-TTY add needs `--host-key` |
