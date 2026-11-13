# 0.5.5 Live Preflight & Inventory Checklist (Read-Only Preparation)

- **Target Acceptance RC:** Runtime `21aba22157994d70bfcf2c17c1ec4ff38b9e9880` (frozen in [RC_FREEZE_21ABA22.md](RC_FREEZE_21ABA22.md))
- **Controller Package:** [vincula-controller-0.5.5.zip](review-artifacts/vincula-controller-0.5.5.zip) (`784ca4d0ef6e8181d683ab6f8ee998e216038cbf789c257c7dd50936394c7892`)
- **Embedded Node Payload:** `vincula-node-0.5.5.tar.gz` (`7b7a1b60d5dfa228291b3b99ac2dd87afd97c22d22d86f9d7732c86157b63c4b`)
- **Phase Policy:** **NO PRODUCTION MUTATIONS IN THIS PHASE.** All live endpoints, current node versions, credentials, and maintenance windows marked `[TO VERIFY IN T01]` or `[PENDING USER CONFIRMATION]` must be confirmed read-only before running any upgrade or service restart.

---

## 1. Controller & Workspace Inventory

### 1.1 Environment Check on Current Windows Session (Observed 2026-11-13)

- Local Windows Vincula directories (`%APPDATA%\vincula`, `%LOCALAPPDATA%\vincula`, `%USERPROFILE%\.config\vincula`, `%USERPROFILE%\.local\state\vincula`): **Not present (`False` on all 4 checks).**
- `wsl.exe -l -v` from current Windows session: **`Wsl/E_ACCESSDENIED`** (cannot inspect WSL distributions from this session).

### 1.2 Historical Production Controller Context (from `fleet-recovery-status.md`, `SUPPORT_BOUNDARY.md`, `2026-11-01-sync-mptcp.md`)

- **Host environment:** Kali WSL2 (`marz` user)
- **`VCL_FLEET_HOME`:** `/home/marz/vincula-fleet-live`
- **`VCL_FLEET_LOCAL_STATE`:** `/home/marz/.local/state/vincula`
- **`XDG_CONFIG_HOME`:** `/home/marz/.config`
- **`fleet_id`:** `1633b697-100f-44ba-bc67-acd28456d576` (historical revision `17`; historical `fleet.db` ~`3.3 GB` as of 2026-11-01)

### 1.3 Controller Preflight Requirements (`[PENDING USER CONFIRMATION]` / `[TO VERIFY IN T01]`)

1. **Operator confirmation needed:** Which workstation/terminal (Kali WSL `marz` session vs Windows host) will run the `0.5.5` Controller for live operations?
2. **Isolation:** Do **not** upgrade or overwrite an active workspace directory in-place without first backing up `fleet.db`, `observation.db`, `fleet.json`, and machine-local `credential-bindings.json` / `cache-policy.json` (see Section 4). Verify `vcl-fleet version` reports `0.5.5` from unpacked `vincula-controller-0.5.5.zip` (`784ca4d0...`).
3. **Read-only baseline check (T01):** Run inside the designated Controller environment:
   - `vcl-fleet cache status --json` (must remain read-only; inspect `fleet.db` size vs `8 GiB` cap / `80%` warning and free disk margin `>= 3 * db_size + 512 MiB` before v5 migration).
   - `vcl-fleet node list --json` (confirm all 7 nodes, exact current versions, hostnames/ports, and `admin_credential_ref` / `observe_credential_ref`).
   - `vcl-fleet status --json` (read-only).

---

## 2. Seven Target Nodes Inventory & Technical Constraints

Historical records (`fleet-recovery-status.md`, `fleet-recovery-20261008.json`, `2026-10-26-fleet-inspection.md`, `2026-10-26-hot-beam-1-inspection.md`, `2026-10-26-urgentfury-disconnect.md`, `2026-11-01-sync-mptcp.md`) list 7 production nodes. Exact current IP/version/SSH state must be re-confirmed in **T01 read-only discovery**:

| Node Alias | Historical Version / TZ | `lib/node_upgrade.py` `UPGRADE_ALLOWLIST` -> `0.5.5`? | Known Historical / Technical Constraints | Live State (`[TO VERIFY IN T01]`) |
| --- | --- | --- | --- | --- |
| `fresh050` | `0.5.0` (`+08:00`) | **Yes** (`0.5.0` supported) | Explicit **canary candidate** in `LIVE_FOLLOWUP.md` / `SUPPORT_BOUNDARY.md` | Host/IP, disk, `sing-box`, `vincula-accountd`, backup space |
| `eagleclaw` | `0.5.0` (`-07:00`) | **Yes** (`0.5.0` supported) | Standard `0.5.0 -> 0.5.5` upgrade + schema v5 migration + `vincula-accountd` de-root | Host/IP, disk, `sing-box`, `vincula-accountd`, backup space |
| `neptunespear` | `0.5.0` (`-07:00`) | **Yes** (`0.5.0` supported) | Standard `0.5.0 -> 0.5.5` upgrade + schema v5 migration + `vincula-accountd` de-root | Host/IP, disk, `sing-box`, `vincula-accountd`, backup space |
| `hot-beam-1` | `0.3.1` (`+00:00`) | **Yes** (`0.3.1` supported) | Historical endpoint `104.194.90.172:22` (Debian 13). Note `2026-10-26` inspection showed `/var/log/journal` at `1.7G` on `19G` `/` (`22%` used) and `admin_credential_ref` `-` in temp ws | Current IP/port, credential ref, `/var/backups/vincula` free space |
| `urgentfury` | `0.3.2` (`+00:00`) | **Yes** (`0.3.2` supported) | Historical endpoint `69.63.198.51:22`, port `20687` blocked domestically (`2026-10-26`/`2026-11-01`); historically accessed via `ssh -J root@104.194.90.172`. Note Controller `ssh` transport uses `-F /dev/null` (ignores `~/.ssh/config` `ProxyJump`) | Confirm direct SSH vs jump-host reachability from Controller host & active proxy port |
| `epicfury` | `0.3.1-rc2` (`-07:00`) | **NO (REFUSED by design)** | Prerelease `0.3.1-rc2` is **not** in `UPGRADE_ALLOWLIST`; `node upgrade plan/apply` fails closed. Per `0.5.5-closeout-runbook.md`, do **not** rewrite prerelease version strings; requires explicit one-time ingress / `backup + restore` or fresh install path | Confirm exact current version (`vcl version`) & ingress plan |
| `upperhand` | `0.3.1-rc2` (`-07:00`) | **NO (REFUSED by design)** | Prerelease `0.3.1-rc2` is **not** in `UPGRADE_ALLOWLIST`; same operator-directed one-time ingress / `backup + restore` or fresh install requirement as `epicfury` | Confirm exact current version (`vcl version`) & ingress plan |

---

## 3. Canary Selection & Rollout Batching (`[PENDING USER CONFIRMATION]`)

- **Proposed Canary Node:** **`fresh050`** (`0.5.0`, `+08:00`) — already supported by `UPGRADE_ALLOWLIST`, represents the `0.5.0 -> 0.5.5` production upgrade + schema v5 + `vincula-accountd` de-root path, and was designated as canary in [LIVE_FOLLOWUP.md](LIVE_FOLLOWUP.md).
- **Proposed Rollout Sequence (only after T01/T02 & canary pass):**
  1. **Batch 0 (Canary + Rollback Drill):** `fresh050` — preflight backup, `node upgrade plan`, `node upgrade apply` (timed `<=3s` new-connection unavailability probe), checkpoint rollback verification (`--verify-only` + controlled rollback rehearsal / restore-forward as approved by user), observer least-privilege & revocation check.
  2. **Batch 1 (Standard `0.5.0` nodes):** `eagleclaw`, `neptunespear`.
  3. **Batch 2 (Legacy release nodes `0.3.1` / `0.3.2`):** `hot-beam-1`, `urgentfury` (only after confirming `urgentfury` SSH transport reachability without relying on `~/.ssh/config`).
  4. **Batch 3 (Non-allowlisted prerelease `0.3.1-rc2` one-time ingress):** `epicfury`, `upperhand` via user-approved explicit ingress/restore path (never by forging `/etc/vincula/VERSION`).
  5. **Continuous 24h Soak + H05:** All 7 real `0.5.5` nodes + `>=10` simulated nodes (2h matrix deviation already verified at `17/17`), dedicated real proxy probes, fault/recovery drills, H05-01..08 human signoff.

---

## 4. Backup & Recovery Paths (Exact Verified Locations)

### 4.1 Controller / Workstation Paths

- **Workspace & fleet metadata:** `$VCL_FLEET_HOME/fleet.json` (or `vcl-fleet workspace export` verified snapshot before any Controller action).
- **Machine-local SQLite databases (outside portable workspace):**
  - `$VCL_FLEET_LOCAL_STATE/fleet.db` (plus `-wal`/`-shm` — stop active sync/writer or hold fleet lock and use consistent SQLite online backup before upgrade/v5 conversion).
  - `$VCL_FLEET_LOCAL_STATE/observation.db` (next to `fleet.db`).
- **Machine-local bindings & policy (outside git & portable workspace):**
  - `$XDG_CONFIG_HOME/vincula/controllers/<fleet_id>/credential-bindings.json` and selectors.
  - `$XDG_CONFIG_HOME/vincula/controllers/<fleet_id>/cache-policy.json`.
- **Converter pre-v5 safety snapshot:** `*.pre-v5-*.db` created next to the DB; reserve `>= 3 * db_size + 512 MiB` free disk.
- **Private probe profiles (if configured):** Local private file `0600` (Linux) / user-only ACL (Windows) **outside** portable Workspace.

### 4.2 Target Node Paths (`bin/vincula`, `lib/upgrade_prepare.py`)

- **Canonical config & identity state (`STATE_DIR`):** `/etc/vincula` (`config.toml`, `state.json`, `users.json`, `VERSION`, `manifest`, etc.).
- **Runtime & accounting DB (`VAR_LIB_VINCULA`):** `/var/lib/vincula` (`accounting.db`, WAL files, `upgrade-operations/` state).
- **Daemon runtime config:** `/etc/vincula-accountd/runtime.json`.
- **Node backups & upgrade checkpoints (`BACKUP_ROOT`):** `/var/backups/vincula` (`0700` root):
  - Pre-change Node backup: `/var/backups/vincula/node-<node_id>-<UTC>.tar` (`0600`), verified read-back before mutation.
  - Upgrade checkpoint directory: `/var/backups/vincula/upgrade-checkpoint-<UTC>.XXXXXX` containing `.vincula-upgrade-checkpoint`, `.vincula-upgrade-checkpoint.manifest.json`, and embedded `upgrade-rollback-helper`.
  - Pre-restore safety directory: `/var/backups/vincula/pre-restore-<UTC>`.
- **Mandatory recovery rule (from `0.5.5-closeout-runbook.md` & `lib/node_upgrade.py`):**
  - Before any rollback after schema v5 activation / new writes, preserve the new `schema-5` database; checkpoint rollback is validated via `--verify-only` manifest check before touching services/live files, and post-write rollback is not lossless for intermediate new writes.

---

## 5. Probing & Verification Methods

1. **Read-only Fleet / Cache baseline (zero SSH / zero Node writes):**
   - `vcl-fleet cache status --json`
   - `vcl-fleet health --json`
2. **Restricted Observer & Least-Privilege Verification:**
   - Dedicated Ed25519 observer key installed via `sudo vcl observer install-key --file <pub>`; bound in Controller via `vcl-fleet node set <NODE> --observe-identity-file <priv> --observe-ssh-user vincula-observer`.
   - Verify `vcl-fleet capabilities <NODE> --json` and `vcl-fleet telemetry <NODE> --json`.
   - Negative auth checks on the node: verify PTY, port forwarding, `sudo`, arbitrary commands, and key removal/revocation fail closed, and no wildcard `AuthorizedKeysCommand`/CA bypasses forced command.
   - Verify `ps`/unit user shows `vincula-accountd` unprivileged user and `/etc/vincula/config.toml` + Reality private key remain `root`-private.
3. **Real VLESS+REALITY End-to-End Proxy Probe:**
   - Dedicated `vcl-probe-*` test user (never copy ordinary user UUIDs), private `probe-profiles/v1` JSON (`0600` / user ACL), pinned compatible local `sing-box` + SOCKS5 `curl`:
   - `vcl-fleet monitor <NODE> --once --timeout 10 --probe-profiles <private-path>/probe-profiles.json --probe-sing-box <verified-path>/sing-box --json`
   - Confirm `2xx`/`3xx` HTTPS success over `127.0.0.1` ephemeral SOCKS listener, verify `connect_ms` and confirm `sing-box` + `vincula-accountd` accounting separation.
4. **Precise `<= 3s` New-Connection Unavailability Measurement (Canary & Upgrades):**
   - Do **not** infer from 30s polling intervals. Run a dedicated high-cadence TCP/REALITY-handshake or local probe harness across the `sing-box` restart/upgrade cutover window (timestamps in UTC with sub-second precision) to directly measure consecutive failed-dial duration against the `<= 3s` acceptance bar.
5. **Audit / Accounting & Sync Consistency:**
   - Run `vcl-fleet sync --json` (and `sync --full` on canary), `vcl verify --json` on node, confirm UTC 6-fractional-digit timestamps, `history-coverage/v1`, and zero unintended restarts or Node writes on read-only checks.

---

## 6. Maintenance Window & Stop Criteria (`[PENDING USER CONFIRMATION]`)

### 6.1 Maintenance Window Table (Fill Before Execution)

| Phase | Target | Proposed Window (UTC / CST) | Operator | Rollback Target / Backup Verified? | Status |
| --- | --- | --- | --- | --- | --- |
| T01/T02 Read-only Discovery | Controller + 7 Nodes | `[PENDING USER CONFIRMATION]` | `[USER]` | Read-only (no mutation) | Ready to run once Controller path confirmed |
| Canary Upgrade + Rollback Drill | `fresh050` (or user choice) | `[PENDING USER CONFIRMATION]` | `[USER]` | Node tar + Checkpoint verified before apply | Blocked awaiting window |
| Staged Fleet Rollout | Remaining 4 allowlisted + 2 rc2 ingress | `[PENDING USER CONFIRMATION]` | `[USER]` | Per-node tar + checkpoint verified | Blocked awaiting Canary PASS |
| Integrated 24h Soak + Fault Drills | 7 real `0.5.5` nodes (`+ >=10` sim 2h done) | `[PENDING USER CONFIRMATION]` | `[USER]` | Per-node tar + Controller backup | Blocked awaiting rollout |

### 6.2 Immediate Stop / Abort Criteria

Halt rollout immediately (do not advance to the next batch) if any of the following occurs:

1. Read-only preflight shows `CACHE_LIMIT_REACHED`, `DISK_SPACE_LOW`, insufficient migration reserve (`< 3 * db_size + 512 MiB`), or missing/unverified node backup.
2. Any `node upgrade plan` refuses (e.g., dirty runtime, version mismatch, non-allowlisted prerelease) — inspect root cause before touching node.
3. Canary `<= 3s` new-connection unavailability probe exceeds `3s`, `vcl verify` fails, ordinary/test proxy probe fails post-upgrade, or checkpoint `--verify-only` / rollback fails.
4. `vincula-observer` negative test permits PTY/forward/escalation, or `vincula-accountd` fails to drop privileges.
5. Unexpected service crash, `systemd` restart loop, or accounting DB integrity/cursor regression during the 24h soak.
