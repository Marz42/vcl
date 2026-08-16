# Backup, restore, and replace (0.3.0)

Node **identity / audit archives** and physical-instance replacement.
Gate: [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md) ·
[`known-issues-0.3.0.md`](known-issues-0.3.0.md).
Fleet replace: [`fleet.md`](fleet.md). Identity: [`identity.md`](identity.md).

`require_root`. `vcl backup *` also `require_install`. The node helper has
**no** `fleet` subcommand.

## Two backup kinds

| Mode | Command | Encryption | Contents |
| --- | --- | --- | --- |
| **A. Identity/Audit (default, secretless)** | `vcl backup create` | **None.** age is not required | Identity + audit + accounting. **No** live secrets |
| **B. Full DR (explicit)** | `vcl backup create --include-secrets --age-recipient FILE` | **Mandatory age** | A in full, plus Reality private key, active VLESS uuid, Clash secret |

`--include-secrets` is **not** an extra secrets bundle. Reality private key
already lives in `state.json`; VLESS uuid in `users.json`; Clash secret in
`config.toml`. The flag means: pack those three files **verbatim**, then
force whole-archive age. Secret-bearing backups are **never** written as
plaintext tar.

Default restore and `vcl-fleet node replace` are **secretless**. Do **not**
reuse live keys on a replacement VPS unless you explicitly choose mode B
(disk died, VPS not compromised).

## CLI

```text
vcl backup create [--include-secrets] [--output FILE] [--age-recipient FILE] [--json]
vcl backup verify FILE [--age-identity FILE] [--json]
vcl restore FILE [--include-secrets] [--age-identity FILE] [--reissue-output FILE] [--server HOST] [--json]
```

Human create: `Backup written to PATH`. Secret-bearing create also prints
stderr `WARNING: … contains authentication credentials`.

`--replace-node` is **not** a node CLI flag. `vcl help` does not document it.
If passed: `Restore is fresh-node only; --replace-node is not supported.`

There is no `vcl snapshot export` alias (`vcl backup create` is the snapshot).

## Archive layout (backup schema 1)

POSIX ustar. No absolute paths, no `..`. Archive file mode **0600**.
Directory `/var/backups/vincula` is **0700** (`BACKUP_ROOT`).

```text
manifest.json
state.json
users.json
config.toml
accounting.db
VERSION
```

Default names:

```text
secretless : /var/backups/vincula/node-<node_id>-<YYYYMMDDTHHMMSSZ>.tar
secrets    : /var/backups/vincula/node-<node_id>-<YYYYMMDDTHHMMSSZ>.tar.age
```

`--output FILE` overrides the path. Secrets mode: if `--output` does not end
in `.age`, the implementation appends `.tar.age` (a `.tar` suffix becomes
`.tar.age`).

`accounting.db` is snapshotted only with Python `sqlite3.Connection.backup()`
(read-only URI on the source). Live accountd / WAL is allowed. Do **not**
`cp` or routinely `scp` the live database. If the source DB is missing, that
member is omitted (`included_components` without `accounting.db`; verify
WARNs; AC-3.0-09 does not apply to that archive).

`VERSION` is the source node’s product line. Restore uses it for
compatibility checks; it does **not** overwrite the running helper version.

Unknown `manifest.schema_version` → verify/restore refuse.
`BACKUP_SCHEMA_VERSIONS_READ = (1,)`.

### `manifest.json`

```json
{
  "schema_version": 1,
  "vincula_version": "0.3.0",
  "created_at": "2026-08-16T06:00:00Z",
  "source_node_id": "<uuid>",
  "source_instance_id": "<uuid>",
  "included_components": [
    "state.json",
    "users.json",
    "config.toml",
    "accounting.db",
    "VERSION"
  ],
  "secret_bearing": false,
  "encryption": "none",
  "files": [
    {"path": "state.json", "sha256": "<hex>"},
    {"path": "users.json", "sha256": "<hex>"},
    {"path": "config.toml", "sha256": "<hex>"},
    {"path": "accounting.db", "sha256": "<hex>"},
    {"path": "VERSION", "sha256": "<hex>"}
  ]
}
```

| Field | Rule |
| --- | --- |
| `schema_version` | Backup **format** version, always `1`. Not `state.json` schema |
| `vincula_version` | Source product version (`VINCULA_VERSION`) |
| `created_at` | RFC3339 UTC, `Z` |
| `secret_bearing` | secretless=`false`; `--include-secrets`=`true` |
| `encryption` | `"none"` \| `"age"`. Invariant: `secret_bearing==true` ⇔ `encryption=="age"` ⇔ outer file `.tar.age` |
| `files[].sha256` | SHA-256 of the member bytes (lowercase hex). **Excludes** `manifest.json` itself |
| `source_instance_id` | Source physical instance (history). Restore **does not** write it back as the new SoT |

### Secretless strip (disk schemas unchanged)

Archived files still declare their on-disk schemas (`state.json` 2,
`users.json` 2). Strip is archive rendering only.

| File | Kept | Removed |
| --- | --- | --- |
| `state.json` | `schema_version`, `project_version`, `sing_box_version`, `architecture`, `installed_at`, `node.node_id` / `instance_id` / `node_name` / `server` / `listen` / `port` / Reality handshake, SNI, **public** key, `short_id`, entire `service_account` | **`node.reality_private_key`** — key absent, not `""` / `null` |
| `users.json` | per user `user_id`, `tag`, `display_name`, `department`, `enabled`, `created_at`; each credential `credential_id`, `node_id`, `status`, `created_at`, `revoked_at` | **`credentials[].uuid`** (including historical revoked rows) |
| `config.toml` | versions, `node_id`, `node_name`, `server` / `listen` / `port`, Reality handshake/SNI, Clash API port, retention, billing cycle | **`clash_api_secret = "…"`** — line absent |

`--include-secrets`: copy those three files verbatim (private key, uuids,
Clash secret present).

## age (recipient file, not a passphrase)

Optional dependency. Secretless create **never** invokes age.

```text
encrypt:  $VCL_AGE_BIN -e -R RECIPIENT_FILE  < archive.tar  > archive.tar.age
decrypt:  $VCL_AGE_BIN -d -i IDENTITY_FILE   < archive.tar.age > archive.tar
```

| Item | Contract |
| --- | --- |
| Recipient | One or more `age1…` public keys (`age -R`). CLI: `--age-recipient FILE` |
| Identity | `AGE-SECRET-KEY-1…` (`age -i`). CLI: `--age-identity FILE` |
| Binary | `$VCL_AGE_BIN` if set, else `age` on PATH |
| Passphrase | **Not implemented** (`age -p` / `VCL_AGE_PASSPHRASE`). Generate a key once with `age-keygen` |

Whole tar is encrypted, not per-file. Verify of `.age` **must decrypt**
(`--age-identity`). 0.3.0 does not ship `age`; install the distro package
when you need mode B.

### Exact errors (stderr `ERROR: ` + these lines)

```text
ERROR: Secret-bearing backup requires age.
ERROR: Secret-bearing backup requires --age-recipient FILE.
ERROR: Encrypted backup verify requires --age-identity FILE.
```

Missing binary and missing recipient are **two** errors. Tests assert the
D17 age-missing line.

### Operator workflow (mode B)

```bash
age-keygen -o /root/vincula-age-identity.txt
# public line (age1…) → recipient file; keep the identity offline

sudo vcl backup create --include-secrets \
  --age-recipient /root/vincula-age-recipient.txt

sudo vcl backup verify /var/backups/vincula/node-….tar.age \
  --age-identity /root/vincula-age-identity.txt
```

## `vcl backup verify`

Always run verify before restore. Restore itself verifies **before any
mutation**. Failure leaves the source FILE untouched.

Order:

```text
1. If FILE ends with .age → decrypt to a temp tar (age + identity required)
2. tar members must include manifest.json
3. Parse manifest; schema_version ∈ {1}
4. secret_bearing, encryption, and outer extension agree
5. each files[].path exists; sha256 matches
6. included_components matches members (except manifest.json)
7. secretless: no reality_private_key / credentials[].uuid / clash_api_secret
8. secrets: those three must be present (users: at least one active uuid if users is non-empty)
```

`--json` failure: `{"schema_version":1,"ok":false,"error":"…"}` and non-zero
exit. `error`: `checksum_mismatch` | `missing_manifest` |
`unsupported_schema` | `secret_bearing_unencrypted` | `age_required` |
`age_identity_required` | `invalid_archive` | `failed`.

## Restore (fresh node)

`vcl restore FILE` **refuses an existing install**. If
`$STATE_DIR/VERSION` exists:

```text
ERROR: Refusing to overwrite an existing Vincula install.
```

Target: 0.3.0 helper (`vcl`, `vincula-backup.py`) on PATH as root, **no**
VERSION yet. A completed `vincula.sh` install writes VERSION and therefore
cannot be the restore target. `--replace-node` does not override that.

`--include-secrets` is valid only when `secret_bearing==true`. Secretless
archive + that flag → refuse. `.tar.age` without `--age-identity` → refuse.

`--server HOST` overrides the target `server` (fleet replace passes the new
public host). Omitted: keep the target’s current `server` / `listen` /
`port`. Backup `server` is source metadata only.

### What is kept vs rotated

Replacement keeps logical identity and history; it rotates short-lived
secrets and the physical instance.

| Kept | Replaced |
| --- | --- |
| Backup `node_id` (not reminted) | `instance_id` = new UUID, ≠ `node_id` |
| Each user’s `user_id` / tag / metadata / enabled | Endpoint: **target** `server` / `listen` / `port` |
| accounting / audit history (`event_id` kept) | Reality keypair (safe mode: newly generated) |
| Historical `credentials[]` rows (`credential_id`, revoked) | Clash secret (safe mode: new) |
| Reality handshake / SNI from the backup | Active VLESS uuid (safe mode: new) |
| retention / billing cycle | `service_account` stays **target** uid/gid (not taken from the backup) |

### Safe mode (secretless, or no `--include-secrets`)

```text
1. verify FILE (mandatory)
2. refuse if VERSION exists
3. replacement plan (new instance_id; users whose credentials will rotate)
4. target safety backup: $BACKUP_ROOT/pre-restore-<UTC>/  marker type=restore-safety
5. stage canonical files (new instance_id, new Reality, new Clash, new active uuid;
   old active credentials → revoked, no uuid in secretless staging)
6. render sing-box config.json + owner.uri from staged users+state
7. validate (syntax, node_id≠instance_id, no empty private key)
8. stop accountd → atomic install staged files → start sing-box + accountd → health
9. failure → roll target back from pre-restore-*; never edit FILE; never touch the source node
10. success → reissue CSV 0600 to --reissue-output
    (default $BACKUP_ROOT/reissue-<UTC>.csv)
```

Reality keys: `sing-box generate reality-keypair` (same as a new install).

### Secrets mode (`--include-secrets` + age archive)

Still **mints a new `instance_id`**. Still applies the new endpoint.
**Reuses** backup Reality keys, Clash secret, and every `credentials[].uuid`
(including active). No new-uuid rows in the reissue CSV; stdout:

```text
secret-mode restore reused credentials; no reissue CSV
```

This is **not** the replacement default. `vcl-fleet node replace` is
secretless only. Use secrets restore only when the disk died and the VPS
was not untrusted.

### Reissue CSV (AC-3.0-10)

```csv
user,node,old_credential_id,new_credential_id,vless_uri
alice,lax,<old-uuid>,<new-uuid>,vless://...
```

- `user` = tag
- `node` = `node_name`
- One row per user whose credential was **active before restore**
- Historical revoked rows do not appear
- File **0600**; stderr credential WARNING
- URI uses the **new** uuid + **new** Reality public key + **new** server

Old uuids must not appear in the new node’s `config.json` inbound `users`.
If the old VPS is still up, old links may still work on the **old IP** —
cut-over is stop the old machine (AC-3.0-11 is LIVE-only).

## Fleet replace

Physical instance replacement is **`vcl-fleet node replace`**, not
`vcl-fleet node set` and not node `vcl restore --replace-node`.

| Command | Meaning |
| --- | --- |
| `vcl-fleet node set NAME --host X` | **Endpoint rebind.** Same physical instance; only `fleet.json` `ssh_host` (optional user/port). Credentials, `instance_id`, Reality **kept**. No backup/restore |
| `vcl-fleet node replace NAME --host NEW_HOST --host-key SHA256:…` | **Physical replace.** Secretless backup → restore on a new host → new `instance_id`, rotated keys, reissue CSV |

`--host-key` is required on replace (new VPS, new host key). Replace does
**not** mark the logical node `retired`. `status` stays `active`; only
`ssh_host` changes. Operator checklist: [`fleet.md`](fleet.md).

`scp` of `.tar` / `.tar.age` / reissue CSV is allowed. `scp` of live
`accounting.db` is still forbidden.

## DR checklist

1. **Routine:** `sudo vcl backup create` (secretless). Copy the `.tar` off-box. Mode **0600**.
2. **Optional full DR:** install `age`; `age-keygen`; `--include-secrets --age-recipient`. Never leave a plaintext secret tar.
3. **Verify before you need it:** `vcl backup verify FILE` (`.age` needs `--age-identity`).
4. **Fresh-node restore:** helper present, **no** `VERSION`. `sudo vcl restore FILE [--server HOST]`. Distribute the reissue CSV. Stop the old VPS.
5. **Secrets restore:** only when the box was not compromised. `--include-secrets --age-identity`. No CSV of new uuids.
6. **Fleet:** `node replace` for a new machine; `node set` only to rebind the same instance. `--from-backup FILE` if the old host is dead (sync tail may be lost).
7. **Do not** default to key reuse. **Do not** `scp` live `accounting.db`. **Do not** expect unit tests to prove old VLESS links fail (AC-3.0-11).
