# Fleet operator guide (0.3.0)

Workstation **Fleet Users & Audit** controller. It registers nodes, provisions
the same logical user on many nodes, incrementally syncs audit into a local
`fleet.db`, retires nodes after a final sync, and records physical instances
(`node instances`). **`node replace`** is physical instance replacement onto a
**runtime-only** new host (see below). Transport is
**system OpenSSH**. It does not listen on a port, does not run as root, and
does not use `/etc/vincula`.

SPEC `vcl fleet <sub>` **≡** this binary: `vcl-fleet <sub>`. The node helper
`vcl` / `vincula` has **no** `fleet` subcommand.

Backup format and fresh-node restore: [`backup.md`](backup.md).
Command-by-command flags: [`manual.md`](manual.md).
Full identity contract (including `--user-id` and intended replace semantics):
[`identity.md`](identity.md).
Gate: [`release-readiness-0.3.1.md`](release-readiness-0.3.1.md) ·
[`known-issues-0.3.1.md`](known-issues-0.3.1.md)
(0.3.0 freeze record: [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md)).
Live two-VPS replace (not yet run): [`live-replace-checklist.md`](live-replace-checklist.md).

## Prerequisites

| | |
| --- | --- |
| Python | **3.10+** on PATH (`py -3` / `python` on Windows, `python3` on Unix) |
| SSH | **system OpenSSH client** (`ssh.exe` / `scp.exe` / `ssh-keyscan.exe` on Windows; `ssh` / `scp` / `ssh-keyscan` on Linux/macOS) |
| Node | 0.3.0 (or later) with `vcl identity --json`, `vcl user * --json`, `vcl audit export --after N --jsonl`, `vcl backup create --json`, and `vcl restore` reachable as the SSH user (default `root`) |
| Not bundled | CPython, OpenSSH, paramiko, pip packages, `age` |

Vincula does not ship a management HTTP API. The only workstation → node
channel is SSH. `scp` of **backup archives** (`.tar` / `.tar.age`) and
reissue CSV is allowed. Do **not** routinely `scp` live `accounting.db`.

## Paths

| | |
| --- | --- |
| `VCL_FLEET_HOME` | If set, this directory (required in tests) |
| Windows | `%APPDATA%\vincula\` (usually `C:\Users\<user>\AppData\Roaming\vincula`) |
| Linux / macOS | `${XDG_CONFIG_HOME:-~/.config}/vincula/` |
| Registry | `$FLEET_HOME/fleet.json` (schema **2**; **does not store** `instance_id` or passwords) |
| Audit cache + instance history | `$FLEET_HOME/fleet.db` (schema **3**; controller-local, not node SoT) |
| Last probe | `$FLEET_HOME/last-status.json` (health summary, not source of truth) |
| Retired snapshot | `$FLEET_HOME/retired/<name>/` (identity / cursor / last-status; not a 0.3.0 backup) |
| Replace backups | `$FLEET_HOME/backups/` (**0700**; pulled secretless `.tar`, files **0600**) |
| Reissue CSV | `$FLEET_HOME/reissue-<name>-<UTC>.csv` (**0600**) unless `--output` |
| Host keys | user default `known_hosts` (`%USERPROFILE%\.ssh\known_hosts` / `~/.ssh/known_hosts`) |

`fleet.json` schema 1 is read and rewritten as schema 2 (`status` =
`active` \| `disabled` \| `retired`). There is **no** automatic schema 2→1.

`fleet.db` schema **1 → 2** adds `instance_history` (explicit migrate +
backfill from `sync_cursor`). Schema **2 → 3** adds `audit_events.export_seq`,
`sync_cursor.last_export_seq`, and `sync_cursor.cursor_kind` (legacy cursors
stay `event_id` until `--reseed`). There is no automatic downgrade. A
schema-2 `fleet.db` is not understood by a 0.2.9 controller without migrate.

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

`node replace` locally verifies the archive by loading
`lib/vincula-backup.py` next to `vincula-fleet.py`. The controller zip ships
`lib/vincula-audit.py` and `lib/vincula-backup.py` beside `vincula-fleet.py`
(P0-02 / B3). The zip also ships `controller.lock` (member list + sha256) and a
sidecar `vincula-controller-<ver>.zip.sha256` (P2-03 / B13). Verify with
`sha256sum -c`. See [`known-issues-0.3.0.md`](known-issues-0.3.0.md).

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
| `vcl-fleet node set NAME --host NEW_HOST` | **Endpoint rebind.** Change `ssh_host` only; **`node_id` stays**; credentials stay |
| `vcl-fleet node replace NAME --host NEW_HOST --host-key SHA256:…` | Physical replace onto a **runtime-only** NEW_HOST (secretless backup → `vcl restore --reissue-output`) |
| `vcl-fleet node instances NAME` | `instance_history` table for that logical node |
| `vcl-fleet node disable NAME` / `enable NAME` | Flip `active` ↔ `disabled`. Retired nodes cannot be enabled |
| `vcl-fleet node retire NAME` | Final sync, snapshot, mark `retired` (history kept). Not a replace |
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
| `vcl-fleet ui [--host 127.0.0.1] [--port 8765]` | Localhost-only read-only Local Audit UI (Overview / Audit / Health) |
| `vcl-fleet version` | `vcl-fleet 0.3.1-dev` |
| `vcl-fleet help` | Help |

`node add` flags: `--user`, `--port`, `--host-key SHA256:...`, `--identity-file PATH`, `--offline --node-id UUID`.
`--instance-id` is accepted and **ignored** (not stored).
`--identity-file` is a **local** private-key path (not the key bytes). SSH/SCP then pass `-i PATH -o IdentitiesOnly=yes`. Unset keeps the OpenSSH default (agent / default keys). There is no password-SSH fallback; use the cloud console / serial, or a non-root account with sudo.

`node set` flags: `--host` (rebind), `--user`, `--port`, `--identity-file PATH`, `--clear-identity-file`. At least one of `--host` / `--identity-file` / `--clear-identity-file` is required.

`node replace` flags: `--host` (required), `--host-key SHA256:…` (required),
`--output` (local reissue CSV dest), `--from-backup FILE`, `--identity-file PATH`, `--json`. Remote
restore argv is `vcl restore FILE --reissue-output FILE --server HOST --json`.
NEW_HOST must already have runtime (`sudo bash vincula.sh --runtime-only`)
and **must not** have `$STATE_DIR/VERSION`. A fully bootstrapped host is
refused.

Not in 0.3.0: age passphrase, `vcl snapshot export`. Localhost UI is **0.3.1** (`vcl-fleet ui`).

## Local Audit UI (0.3.1 / B15)

```bash
python3 bin/vcl-fleet ui
# Windows: bin\vcl-fleet.cmd ui
```

Listens on **`http://127.0.0.1:8765`** by default (`--host` / `--port`). Only
loopback binds (`127.0.0.1`, `::1`); `0.0.0.0` / public listens are refused
(AC-3.1-01). Stopping the UI process does **not** affect VPS nodes
(AC-3.1-09).

**Pages:** Overview / Audit / Health. Users and Nodes are **read-only
drill-downs**, not admin editors. There are **no** UI identity mutations
(add/rotate/retire/replace/restore/import) and **no UI reseed** (CLI
`vcl-fleet sync --reseed NAME` only). Recipes panel copies commands.
`/api/*` requires loopback `Host` + process UI token; POST requires JSON
`Content-Type` and, **when Origin is present**, a matching loopback Origin
(missing Origin is allowed for same-machine tools). Default views never show Reality keys,
Clash secret, or VLESS URI.

**Data:** `$FLEET_HOME` cache (`fleet.json`, `fleet.db`, `last-status.json`,
optional `users-cache.json`). Buttons **Refresh status** / **Verify** /
**Sync** call the same controller paths as the CLI (SSH-backed cache
writes). GET audit is local cache only (no implicit SSH). Audit uses the
same interval-overlap query layer as `vcl-fleet audit user`, with a 31-day
window cap and a 500-row default page. The HTTP server caps concurrent
workers (503 when busy) and applies a per-request socket timeout.
Accounting is labeled **approximate**.

Packaging: controller zip includes `lib/vincula-ui/server.py` and
`lib/vincula-ui/static/*` (listed in `controller.lock`).

操作员手测清单（Win11 / 浏览器 / AC-3.1 勾选）：见手册
[`docs/manual.md` § Local Audit UI 手动测试指南](manual.md#ui-manual-test)。

## Rebind vs replace

| | `node set` (rebind) | `node replace` (replace) |
| --- | --- | --- |
| When | Same VPS, new SSH IP/hostname (or user/port) | New physical machine for the **same** logical `node_id` |
| Credentials / Reality / Clash | **Kept** | **Rotated** (secretless restore) |
| `instance_id` | Unchanged | Newly minted; ≠ `node_id`; ≠ old instance |
| Backup / restore | None | Secretless `vcl backup create` → `vcl restore` on the new host |
| Host key | Does **not** auto-pin (0.2.9 behaviour) | **Must** `--host-key SHA256:…` |
| Registry | `ssh_host` (etc.) | `ssh_host` new; `status` stays `active`; **not** `retired` |
| `fleet.json` `instance_id` | Still not stored | Still not stored |
| `instance_history` | No extra row | Old instance `retired`; new row `active` |
| Sync cursor | Unchanged | `instance_id` updated; **`last_export_seq` kept**; no auto `--reseed` |

`retired` still means you **abandoned the logical `node_id`**. Replacing a
VPS is not retire. `node enable` on a retired name still dies:
`retired node cannot be enabled; replacement is 0.3.0`.

Replace **never** sends `--include-secrets`. Key reuse is node-side
`vcl restore --include-secrets` only ([`backup.md`](backup.md)).

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
→ write fleet.json (name, node_id, ssh_host, ssh_user, ssh_port, optional identity_file, enabled, status)
```

`ssh-keyscan` is **candidate acquisition**, not verification. A mismatch fails
and writes nothing.

Offline register (mock / unreachable host, still listed):

```bash
python3 bin/vcl-fleet node add sg --host 203.0.113.12 --offline --node-id <uuid>
```

Changing a node's IP later **on the same instance**: `node set` does **not**
rewrite `known_hosts`. Pin again with `--host-key` or edit OpenSSH
`known_hosts` yourself. A **new** VPS is `node replace` (must pin). Prepare
the new host with `sudo bash vincula.sh --runtime-only` first.

### Host-key policy (D14)

Default: OpenSSH user `known_hosts`. The controller never passes:

- `StrictHostKeyChecking=no`
- `UserKnownHostsFile=/dev/null`

and never points `UserKnownHostsFile` at an empty file.

## `node replace`

Physical instance replacement of the same logical `node_id`. NEW_HOST must
be **runtime-only**, not a finished bootstrap:

```bash
# on the new VPS (no VERSION, no identity)
sudo bash vincula.sh --runtime-only
# or: sudo VCL_RUNTIME_ONLY=1 bash vincula.sh
```

Then from the workstation:

```bash
python3 bin/vcl-fleet node replace lax --host 203.0.113.18 --host-key SHA256:...
python3 bin/vcl-fleet node instances lax
```

Living-tree **fixture** replace is a contract pass (B10). **Live** two-VPS
evidence is still missing (B14 deferred). Run
[`live-replace-checklist.md`](live-replace-checklist.md) on real hosts before
calling replace RC-ready. Do not treat fake-ssh as that pass.

Flow:

```text
final sync on OLD (unless --from-backup)
→ secretless vcl backup create
→ scp archive to NEW:/tmp/vincula-restore.tar
→ preflight: test -x /usr/local/bin/vcl && test ! -f /etc/vincula/VERSION
→ ssh: vcl restore FILE --reissue-output /tmp/reissue.csv --server NEW --json
→ identity + vcl verify --json
→ pull reissue CSV
→ registry ssh_host = NEW; instance_history: old retired, new active
→ keep sync cursor last_export_seq (CURSOR_AHEAD on next sync if the restored
  DB is behind; then --reseed)
```

A host that already has `$STATE_DIR/VERSION` is refused; `fleet.json` is not
rewritten. A host with no `vcl` binary is refused (`install with vincula.sh
--runtime-only`). The remote restore command uses `--reissue-output` (not a
restore `--output` flag).

`--reseed` wipes that node’s local `audit_events` + `daily_usage` and does
**not** delete `instance_history`.

## `node instances`

Answers: “which physical instance served `lax` in this period?”

```text
INSTANCE_ID STARTED RETIRED ENDPOINT SSH STATUS
```

`status` ∈ `active` \| `retired`. At most one `active` row per `node_id`.
`instance_id` is UUID and ≠ `node_id`. SoT is **`fleet.db`**, not
`fleet.json`.

Schema 1→2 backfill: each `sync_cursor` row with a non-empty `instance_id`
becomes one `active` history row (`started_at=last_sync_at` or now;
`ssh_host` from `fleet.json`). Active nodes with no cursor do not invent a
row.

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

Replace reissue CSV is a different header (`old_credential_id`,
`new_credential_id`); see [`backup.md`](backup.md).

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
   (`--reseed` also passes `--stamp-identity`; normal sync does not)
→ import INSERT OR IGNORE in one transaction; rebuild that node's daily_usage
→ advance cursor only after COMMIT
```

Every JSONL row and export meta must carry a `node_id` that matches identity.
Missing or mismatched identity **fails the whole batch**: no import, cursor
unchanged, overall exit **2**, remediation `vcl-fleet sync --reseed NAME`.
`--reseed` is the only stamp path: remote `vcl audit export --stamp-identity`
fills **missing** row `node_id` / `instance_id` (does not write `accounting.db`).
Already-labeled but mismatched rows still fail. Query still ignores unlabeled
rows already in `fleet.db`.

### `CURSOR_EXPIRED` (remote exit 3)

When `after > 0` and `after < pruned_max_export_seq` (Fleet missed durable
rows that retention already deleted), the node reports `CURSOR_EXPIRED`.
Sparse `event_id` holes alone are **not** expiry. The controller does **not**
import a hole: cursor `status=expired`, overall exit **2**, remediation
`vcl-fleet sync --reseed NAME`. `--reseed NAME` deletes that node's local
`audit_events` + `daily_usage`, resets `last_export_seq=0` with
`cursor_kind=export_seq`, then pulls `--after 0` (the remaining closed window)
with `--stamp-identity`. Reseed is **not** a backup; `instance_history` is
**not** erased. Unlabeled rows on a normal sync also point here; they do not
skip-and-advance.

### `CURSOR_AHEAD` (remote exit 3, distinct `meta.error`)

When `after > 0` and `after > audit_export_seq` (stale controller cursor vs a
restored older `accounting.db`, including `--from-backup`), the node reports
`CURSOR_AHEAD`. This is **not** `CURSOR_EXPIRED`. The controller does **not**
treat it as a successful empty sync: status=`error`, cursor unchanged, no
import, overall exit **2**, same `--reseed NAME` remediation.

### `CURSOR_PROTOCOL_MISMATCH` (controller-local)

`fleet.db` schema 3 keeps legacy `cursor_kind=event_id` cursors until the
operator reseeds. Sync refuses those nodes with
`CURSOR_PROTOCOL_MISMATCH: event_id → export_seq` and the same `--reseed`
remediation. Do not reinterpret `last_event_id` as `export_seq`.

Sync also fail-closes if remote meta lies: `protocol_version` ≠ 2,
`cursor_kind` ≠ `export_seq`, `count` ≠ JSONL rows, `next_cursor` ≠ last
`export_seq`, `export_seq` not strictly increasing / duplicates, or
`node_id` / meta `instance_id` mismatch with identity. Contiguous
`event_id` is **not** required. Cursor advances to the remote `next_cursor`
only after the full batch is validated and UPSERT-imported in one
transaction.

**Replace does not auto-reseed.** After a successful replace,
`last_export_seq` (and diagnostic `last_event_id`) are kept. Immediate
`sync --node NAME` continues `--after` that export_seq on the new instance.
If the restored DB's max is below that cursor, you get `CURSOR_AHEAD` and
`--reseed`. If retention already raised `pruned_max_export_seq` above the
cursor, you still `--reseed` — you do not restore again.

Cursor lives on disk in `fleet.db`. A new controller process reading the
same file continues from the last committed `export_seq`. Re-running sync is
idempotent (UPSERT; `COUNT(*)` and cursor stay put when the window is empty).

Durable export is **closed generations only**. Open connections stay on the
node (`vcl connections` / status); they are not Fleet audit rows until close
assigns `export_seq`.

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

Retire abandons the **logical** node. Keeping `node_id` on new hardware is
the intended `node replace`.

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
A new `instance_id` with the same `node_id` (reinstall / replace) prints
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
ssh root@<host> vcl backup create [--json]
ssh root@<host> vcl backup verify FILE [--json]
ssh root@<host> vcl restore FILE [--server HOST] [--reissue-output CSV] [--json]
```

Allowed `scp` (archives and CSV only):

```text
scp … root@OLD:/var/backups/vincula/node-*.tar  $FLEET_HOME/backups/
scp … $FLEET_HOME/backups/*.tar  root@NEW:/tmp/vincula-restore.tar
scp … root@NEW:/tmp/reissue.csv  $FLEET_HOME/reissue-*.csv
```

Do **not** routinely `scp /var/lib/vincula/accounting.db`. Live SQLite copy is
not a consistent snapshot. User add/rotate uses mutation timeout 60s
(sing-box restart); backup/restore 120s; read-only probes stay 20s.

## Tests / mock SSH

```bash
export VCL_FLEET_HOME=/tmp/fleet-home
export VCL_FLEET_SSH=/path/to/tests/fixtures/fake-ssh
export VCL_FLEET_SSH_KEYSCAN=/path/to/tests/fixtures/fake-ssh-keyscan
export VCL_FLEET_SCP=/path/to/tests/fixtures/fake-scp
export VCL_FAKE_STATE_DIR=/tmp/fake-state
```

CI uses fixtures: lax (healthy), tokyo (accounting STALE), sg (SSH FAIL),
lax2 (`203.0.113.18`, intended replace target). AC-2.9-01 “two nodes” =
**lax + tokyo fixtures**. Living-tree `node replace` is callable on the real
restore contract (runtime-only NEW_HOST, `--reissue-output`). lax → lax2 is
**PASS (fixture)** only. Live two-VPS evidence is B14
([`live-replace-checklist.md`](live-replace-checklist.md); **PASS 2026-08-18**).
Local Audit UI is B15 (`vcl-fleet ui`).

## Explicitly not in 0.3.0

age passphrase, `vcl snapshot export`, routine `scp accounting.db`,
billing-grade accounting, node `vcl fleet` subcommand, distributed rollback
**guarantee**, blocking 90-day retention for cursors, retire/replace
auto-uninstall / erase `fleet.db`, replace `--include-secrets`, automatic
`--reseed` after replace. Localhost UI shipped in **0.3.1** (`vcl-fleet ui`);
UI still does not mutate identity (CLI recipes only).

## AC-2.9 matrix (01–12)

Fleet Users & Audit evidence remains **fake-ssh multi-node fixtures**. Mock
is not live VPS. Full Status / Code / Test / Remaining risk table:
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
| AC-2.9-10 | No VPS management API port; UI (0.3.1) is workstation loopback-only in `lib/vincula-ui` | Static grep: no `socket.bind` / `HTTPServer` in `lib/vincula-fleet.py`, `bin/vcl-fleet`, `bin/vcl-fleet.cmd`; UI refuses non-loopback |
| AC-2.9-11 | Node `--user-id`; plain add still generates; controller injects | `tests/test.sh` explicit / generated / duplicate `user_id`; fleet add shares one UUID |
| AC-2.9-12 | `audit export --after` + idempotent sync; gap → `CURSOR_EXPIRED` + `--reseed`; `after>max` → `CURSOR_AHEAD` | `tests/test.sh` export/CURSOR_EXPIRED/CURSOR_AHEAD; `tests/test-fleet.sh` reseed / hole not imported / lying meta |

## AC-3.0 matrix (01–12)

Backup / restore / replace. Evidence is **fixtures** unless noted.
AC-3.0-11 is **LIVE-only** (must not be marked PASS from unit tests).
Full table: [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md).

| ID | Criterion | Fixture evidence pointer |
| --- | --- | --- |
| AC-3.0-01 | Default backup has identity / audit / accounting | `tests/test.sh` `AC-3.0-01 fixture PASS: default backup includes identity and accounting` |
| AC-3.0-02 | Default backup is secretless; no encryption required | `AC-3.0-02 fixture PASS: default backup is secretless without encryption` |
| AC-3.0-03 | Secret-bearing backup requires age; exact missing-age error | `AC-3.0-03 fixture PASS: missing age dies with exact ERROR and writes no tar` |
| AC-3.0-04 | Verify detects damage | `AC-3.0-04 fixture PASS: verify detects bit-flip checksum mismatch` |
| AC-3.0-05 | Replace keeps `node_id` | node restore + `AC-3.0-05/06/07/10 replace keeps node_id…` |
| AC-3.0-06 | Replace mints new `instance_id` ≠ `node_id` | same |
| AC-3.0-07 | Safe replace rotates Reality and credentials | same |
| AC-3.0-08 | `user_id` unchanged | `AC-3.0-08 fixture PASS: restore keeps user_id` |
| AC-3.0-09 | History accounting/audit still queryable | `AC-3.0-09 fixture PASS` + `AC-3.0-09 replace sync keeps old instance rows and cursor` |
| AC-3.0-10 | Reissue CSV correct | `AC-3.0-10 fixture PASS: reissue CSV maps old to new credential_id` |
| AC-3.0-11 | Old credential links fail after revoke | **PARTIAL / LIVE-only.** Fixture: inbound omits old uuid. Not PASS |
| AC-3.0-12 | Failed restore does not destroy target or source | `AC-3.0-12 fixture PASS`; fleet replace fail inject leaves old `ssh_host` |

## AC-3.1 matrix (01–11)

Local Audit UI (B15). Fixture + urllib against loopback stdlib server.

| ID | Criterion | Evidence pointer |
| --- | --- | --- |
| AC-3.1-01 | UI default / only loopback bind | `tests/test-fleet.sh` refuses `--host 0.0.0.0` |
| AC-3.1-02 | No VPS public management port | UI is workstation-local; nodes unchanged |
| AC-3.1-03 | Health / Overview visible | `/api/health`, `/api/overview` |
| AC-3.1-04 | Users/nodes read-only drill-down; no mutation | `/api/users`, `/api/nodes/:name`; POST mutate routes 405 |
| AC-3.1-05 | Audit by user/time/destination | `/api/audit?...`; destination substring in SQL before LIMIT |
| AC-3.1-06 | Accounting freshness / approximate badge | Overview warnings + `accounting_mode` |
| AC-3.1-07 | Default pages omit keys / Clash secret / URI dump | Static + JSON asserts |
| AC-3.1-08 | Same query layer as CLI | `query_fleet_audit` / `query_daily_grouped` |
| AC-3.1-09 | Closing UI does not affect nodes | Process-local HTTP only |
| AC-3.1-10 | Local cache + SSH refresh | `last-status.json` + POST `/api/refresh/*` / `/api/sync` |
| AC-3.1-11 | Three pages only; no identity-mutation APIs; reseed CLI-only; Host/token; Origin if present | `/api/meta`; POST reseed 400; Host 403; missing token 401 |
