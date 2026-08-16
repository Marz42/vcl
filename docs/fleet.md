# Fleet operator guide (0.2.9)

Workstation **Fleet Users & Audit** controller. It registers nodes, provisions
the same logical user on many nodes, incrementally syncs audit into a local
`fleet.db`, and retires nodes after a final sync. Transport is **system
OpenSSH**. It does not listen on a port, does not run as root, and does not
use `/etc/vincula`.

SPEC `vcl fleet <sub>` **≡** this binary: `vcl-fleet <sub>`. The node helper
`vcl` / `vincula` has **no** `fleet` subcommand.

Full identity contract (including `--user-id`): [`identity.md`](identity.md).
Gate: [`release-readiness-0.2.9.md`](release-readiness-0.2.9.md) ·
[`known-issues-0.2.9.md`](known-issues-0.2.9.md).

## Prerequisites

| | |
| --- | --- |
| Python | **3.10+** on PATH (`py -3` / `python` on Windows, `python3` on Unix) |
| SSH | **system OpenSSH client** (`ssh.exe` / `scp.exe` / `ssh-keyscan.exe` on Windows; `ssh` / `scp` / `ssh-keyscan` on Linux/macOS) |
| Node | 0.2.9 (or later) with `vcl identity --json`, `vcl user * --json`, and `vcl audit export --after N --jsonl` reachable as the SSH user (default `root`) |
| Not bundled | CPython, OpenSSH, paramiko, pip packages |

Vincula does not ship a management HTTP API. The only workstation → node
channel is SSH.

## Paths

| | |
| --- | --- |
| `VCL_FLEET_HOME` | If set, this directory (required in tests) |
| Windows | `%APPDATA%\vincula\` (usually `C:\Users\<user>\AppData\Roaming\vincula`) |
| Linux / macOS | `${XDG_CONFIG_HOME:-~/.config}/vincula/` |
| Registry | `$FLEET_HOME/fleet.json` (schema **2**; **does not store** `instance_id` or passwords) |
| Audit cache | `$FLEET_HOME/fleet.db` (schema **1**; controller-local, not node SoT) |
| Last probe | `$FLEET_HOME/last-status.json` (health summary, not source of truth) |
| Retired snapshot | `$FLEET_HOME/retired/<name>/` (identity / cursor / last-status; not a 0.3.0 backup) |
| Host keys | user default `known_hosts` (`%USERPROFILE%\.ssh\known_hosts` / `~/.ssh/known_hosts`) |

`fleet.json` schema 1 is read and rewritten as schema 2 (`status` =
`active` \| `disabled` \| `retired`). There is **no** automatic schema 2→1.

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
| `vcl-fleet node list` | `NAME NODE_ID SSH_HOST USER ENABLED STATUS` |
| `vcl-fleet node show NAME` | One record |
| `vcl-fleet node set NAME --host NEW_HOST` | Change `ssh_host` only; **`node_id` stays** |
| `vcl-fleet node disable NAME` / `enable NAME` | Flip `active` ↔ `disabled`. Retired nodes cannot be enabled |
| `vcl-fleet node retire NAME` | Final sync, snapshot, mark `retired` (history kept) |
| `vcl-fleet user add TAG --nodes a,b` | Same `user_id`, per-node credentials. PARTIAL → exit **2** |
| `vcl-fleet user list` / `show TAG` | Aggregate by `user_id` (SSH failure → PARTIAL, exit 2) |
| `vcl-fleet user enable\|disable\|rotate TAG --node N` | Single-node mutation; **`--node` required** |
| `vcl-fleet user import FILE` | CSV `tag,display_name,department,nodes`; validate all rows before SSH |
| `vcl-fleet user export [--credentials] --output FILE` | Merged CSV; credentials require `--output`, mode **0600** |
| `vcl-fleet sync [--node NAME] [--reseed NAME]` | Incremental `audit export --after`; cursor in `fleet.db` |
| `vcl-fleet audit user TAG --from RFC3339 --to RFC3339` | Synced connections, tagged with **node** |
| `vcl-fleet stats user\|top users\|top hosts\|node NAME --days N` | `daily_usage` with **node** attribution |
| `vcl-fleet status` | Probe table (see below) |
| `vcl-fleet verify` | Aggregate identity / health / clock |
| `vcl-fleet version` | `vcl-fleet 0.2.9` |
| `vcl-fleet help` | Help |

`node add` flags: `--user`, `--port`, `--host-key SHA256:...`, `--offline --node-id UUID`.
`--instance-id` is accepted and **ignored** (not stored).

Not in 0.2.9: backup/restore, `vcl snapshot export`, UI, `replace-node`.

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
→ write fleet.json (name, node_id, ssh_host, ssh_user, ssh_port, enabled, status)
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

## User provisioning

The controller generates **one** fleet-global `user_id` (or accepts
`--user-id UUID` for PARTIAL remediation) and SSHes
`vcl user add TAG --user-id UUID --json` to each target. Tag is UX only.
Do **not** match users by `display_name`. Each node mints its own
`credential_id` and VLESS URI.

```bash
python3 bin/vcl-fleet user add alice --nodes lax,tokyo --display-name Alice --department Eng
python3 bin/vcl-fleet user add alice --nodes tokyo --user-id <GLOBAL>   # remediation
python3 bin/vcl-fleet user list
python3 bin/vcl-fleet user show alice
python3 bin/vcl-fleet user rotate alice --node lax
python3 bin/vcl-fleet user disable alice --node lax
```

`--node N` ≡ `--nodes N`. `enable` / `disable` / `rotate` **require** `--node`
(AC-2.9-03: no fleet-wide disable). Missing `--node` exits non-zero with
`refusing fleet-wide disable; pass --node`.

### PARTIAL (exit 2)

```text
all SUCCESS          → state=SUCCESS, exit 0
any FAILED (incl. all failed) → state=PARTIAL, exit 2
```

PARTIAL prints per-node SUCCESS|FAILED plus a copy-paste remediation line
that **reuses the same `--user-id`**. Successful nodes also emit credential
CSV (`user,node,credential_id,vless_uri`). Distributed rollback is **not**
promised, not performed, and not in `--help`.

Controller idempotency (the node CLI itself is not idempotent):

| Remote state | Controller |
| --- | --- |
| tag missing | SSH `user add --user-id` |
| tag exists, same `user_id` | that node **SUCCESS** (already provisioned) |
| tag exists, different `user_id` | that node **FAILED** (identity conflict) |
| another tag holds the same `user_id` | that node **FAILED** |

`user list` / `show` SSH a live `vcl user list --json`. Unreachable nodes
are `UNREACHABLE`; the aggregate is PARTIAL (exit 2), not a fake complete
list. Same tag with different `user_id` across nodes is a conflict (exit 1).

### Credential CSV (mode 0600)

`--output FILE` on add / import / rotate / `user export --credentials` writes
mode **0600**. stderr always includes
`WARNING: … contains authentication credentials.`

```text
user,node,credential_id,vless_uri
alice,lax,<uuid>,vless://…@203.0.113.10:443…
alice,tokyo,<uuid>,vless://…@203.0.113.11:443…
```

### Import

CSV header **must** be `tag,display_name,department,nodes`. `nodes` is
`lax` or `lax,tokyo` (quotes allowed). Validation collects every error, then
exits **1 with no SSH**: unknown / retired node, duplicate tag in the file,
empty nodes, invalid tag. `--dry-run` prints the plan only.

Any row/node FAILED during apply → overall PARTIAL (already-successful nodes
are not rolled back).

## Incremental sync

```bash
python3 bin/vcl-fleet sync
python3 bin/vcl-fleet sync --node lax
python3 bin/vcl-fleet sync --reseed lax
```

Default scope: `status==active` nodes. Retired nodes are skipped (and
`--node` on a retired name is refused). Per node:

```text
identity --json (registry node_id must match; instance_id change → WARN, still sync)
→ read sync_cursor (missing → after=0)
→ SSH vcl audit export --after CUR --jsonl
→ import INSERT OR IGNORE in one transaction; rebuild that node's daily_usage
→ advance cursor only after COMMIT
```

Rows without `node_id` are dropped (WARN) and never merged into stats/audit.
`instance_id` NULL historical rows may import when `node_id` is present.

### `CURSOR_EXPIRED` (remote exit 3)

When `after > 0` and the node's remaining window has a gap (`MIN(event_id) >
after+1`, or empty DB), the node reports `CURSOR_EXPIRED`. The controller
does **not** import a hole: cursor `status=expired`, overall exit **2**,
remediation `vcl-fleet sync --reseed NAME`. `--reseed NAME` deletes that
node's local `audit_events` + `daily_usage`, resets `last_event_id=0`, then
pulls `--after 0` (the remaining window). Reseed is **not** a 0.3.0
consistent SQLite snapshot.

Cursor lives on disk in `fleet.db`. A new controller process reading the
same file continues from the last committed `event_id` (original AC-2.8-09
cursor semantics, landed here). Re-running sync is idempotent
(`COUNT(*)` and cursor stay put).

## Fleet audit / stats

Queries read **`fleet.db`**, not live node SQLite. Sync first.

```bash
python3 bin/vcl-fleet audit user alice --from 2026-08-10T00:00:00Z --to 2026-08-16T00:00:00Z
python3 bin/vcl-fleet stats user alice --days 30
python3 bin/vcl-fleet stats top users --days 7
python3 bin/vcl-fleet stats top hosts --days 7
python3 bin/vcl-fleet stats node lax --days 30
```

- `audit`: RFC3339 interval-overlap, same predicate as node `vcl audit`.
  Columns include **node** (registry name). `--json` adds
  `node_id,instance_id,user_id,event_id`.
- `stats`: **only** `daily_usage`, UTC day of connection `started_at`.
  Detail rows keep `(user_id, node)`. Combined totals exist only in
  `--json` `totals.by_node`.
- Empty `node_id` rows are never merged.
- Retired nodes stay queryable (history is not erased).
- Fleet stats are **not** byte-identical with node `vcl stats` (Clash is
  already approximate; cross-midnight connections have no per-day delta).

## Node retirement

Production path **has no `--offline`**. Order is mandatory; **final sync
must succeed before** `status=retired`:

```text
1. NAME already retired → refuse
2. If enabled: SSH identity; registry node_id must match
3. vcl-fleet sync --node NAME. CURSOR_EXPIRED → stop; print --reseed; do not mark retired
4. Write $FLEET_HOME/retired/<name>/ (0700 / files 0600):
     identity.json  cursor.json  last-status.json  README.txt
5. Best-effort disable remote users except the last enabled (node invariant)
6. fleet.json status=retired, enabled=false (atomic write)
7. WARN: last user credentials remain on the node; historical fleet.db rows were not erased;
   optional: sudo vcl uninstall on the node
```

`node enable` on a retired name dies:
`retired node cannot be enabled; replacement is 0.3.0`.
status / verify / sync default to `active` only; `--all` shows RETIRED
placeholders (`SSH=-`, no SSH). Unreachable nodes cannot be retired
(no final sync). Do **not** auto-uninstall. Do **not** delete `fleet.db`
rows for that `node_id`.

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

Disabled and retired nodes are omitted unless `--all` (then `DISABLED` /
`RETIRED`, retired `SSH=-`). Exit 1 if any enabled node is
SSH/PROXY/ACCOUNTING `FAIL`. `--json` is schema 1.

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

## Remote commands

Operator / controller argv after `--`:

```text
ssh root@<host> vcl identity --json
ssh root@<host> vcl status --json
ssh root@<host> vcl verify --json
ssh root@<host> vcl user add TAG --user-id UUID [--display-name N] [--department D] --json
ssh root@<host> vcl user list --json
ssh root@<host> vcl user show TAG --json
ssh root@<host> vcl user enable|disable|rotate TAG --json
ssh root@<host> vcl audit export --after EVENT_ID --jsonl
```

Do **not** routinely `scp /var/lib/vincula/accounting.db`. Live SQLite copy is
not a consistent snapshot (0.3.0). User add/rotate uses mutation timeout 60s
(sing-box restart); read-only probes stay 20s.

## Tests / mock SSH

```bash
export VCL_FLEET_HOME=/tmp/fleet-home
export VCL_FLEET_SSH=/path/to/tests/fixtures/fake-ssh
export VCL_FLEET_SSH_KEYSCAN=/path/to/tests/fixtures/fake-ssh-keyscan
export VCL_FAKE_STATE_DIR=/tmp/fake-state
```

CI uses three fixtures: lax (healthy), tokyo (accounting STALE), sg (SSH FAIL).
AC-2.9-01 “two nodes” = **lax + tokyo fixtures**, not two public VPS.

## Explicitly not in 0.2.9

backup/restore, age, Python SQLite Backup API, `vcl snapshot export`,
`replace-node`, UI, routine `scp accounting.db`, billing-grade accounting,
node `vcl fleet` subcommand, distributed rollback **guarantee**, blocking 90-day
retention for cursors, retire auto-uninstall / erase `fleet.db`.

## AC-2.9 matrix (01–12)

Evidence is **fake-ssh multi-node fixtures**. Mock is not live VPS. Full
Status / Code / Test / Remaining risk table:
[`release-readiness-0.2.9.md`](release-readiness-0.2.9.md).

| ID | Criterion | Fixture evidence pointer |
| --- | --- | --- |
| AC-2.9-01 | Same user, two nodes: one `user_id`, different credential UUIDs | `tests/test-fleet.sh` `AC-2.9-01 user add alice --nodes lax,tokyo` |
| AC-2.9-02 | Rotate one node does not change the other credential | `AC-2.9-02 rotate one node does not change the other node's credential` |
| AC-2.9-03 | Disable one node ≠ disable on every node; `--node` required | `AC-2.9-03 disable one node does not disable the user on other nodes` |
| AC-2.9-04 | Fleet audit merges by `user_id`, rows tagged with node | `AC-2.9-04 audit merges Alice across lax+tokyo by user_id` |
| AC-2.9-05 | Fleet stats keep node attribution | `AC-2.9-05 stats user alice preserves node attribution` |
| AC-2.9-06 | Partial failure → PARTIAL + per-node status + `--user-id` remediation; no rollback promise | `AC-2.9-06` tokyo FAIL inject, exit 2, not overall SUCCESS |
| AC-2.9-07 | Credential CSV is node-specific URI, mode 0600 | `AC-2.9-07 credential CSV is node-specific`; import/export `mode 0600` |
| AC-2.9-08 | Retire final-syncs **before** marking `retired` | `AC-2.9-08 final sync committed cursor=8 before status=retired` |
| AC-2.9-09 | After retire, history still queryable; cursor survives new process | `AC-2.9-09 historical audit still queryable after retire`; sync restart COUNT unchanged |
| AC-2.9-10 | No management API port | Static grep: no `socket.bind` / `HTTPServer` in `lib/vincula-fleet.py`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd` |
| AC-2.9-11 | Node `--user-id`; plain add still generates; controller injects | `tests/test.sh` explicit / generated / duplicate `user_id`; fleet add shares one UUID |
| AC-2.9-12 | `audit export --after` + idempotent sync; gap → `CURSOR_EXPIRED` + `--reseed` | `tests/test.sh` export/CURSOR_EXPIRED; `tests/test-fleet.sh` reseed / hole not imported |
