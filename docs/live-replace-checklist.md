# B14 live replace operator checklist (0.3.1-dev)

**Status: NOT RUN.** This is the operator runbook for live VPS evidence.
Filling [`docs/evidence/0.3.1-live/`](evidence/0.3.1-live/) is what can raise
the freeze-record recommendation from **NOT READY** toward **READY FOR RC**.
Fixture-green `node replace` (B10) is **not** that evidence.

B14 (this pass) and B15 (localhost UI) are **deferred**. Do not mark AC-3.0-11
PASS, and do not call the tree `READY FOR RC`, until the evidence directory
is filled from a real two-VPS run.

Gate: [`release-readiness-0.3.0.md`](release-readiness-0.3.0.md) ·
limitations: [`known-issues-0.3.0.md`](known-issues-0.3.0.md) ·
operator: [`fleet.md`](fleet.md) · [`backup.md`](backup.md).

## What this pass proves

On **two public VPS** plus a workstation controller, with **real** `age`
and (in the same evidence pass) a **Win11** `vcl-fleet.cmd`:

1. Secretless backup on the old node, copied to the controller, verifies.
2. The new VPS is **runtime-only** (no `/etc/vincula/VERSION`).
3. `vcl-fleet node replace NAME --host NEW_HOST --host-key SHA256:…` completes
   the real restore contract (`vcl restore FILE --reissue-output FILE --server HOST --json`).
4. **AC-3.0-11:** the old client URI (old uuid, aimed at **new IP:443**) fails;
   the new URI succeeds. Then stop the old instance.
5. Real `age` `--include-secrets` create → verify round-trip (not `tests/fixtures/fake-age`).
6. Post-replace `vcl-fleet sync` is either a clean continuation or
   `CURSOR_AHEAD` with `--reseed` guidance (not a silent empty OK).

Node restore has **no** `--replace-node` flag. The controller must not send it.
A fully bootstrapped NEW_HOST (VERSION present) must fail replace without
rewriting `fleet.json`.

## Prerequisites

| Role | Requirement |
| --- | --- |
| **Old VPS** | Existing 0.3.0 or 0.3.1-dev install. Real users and some traffic (so accounting/audit is not an empty lab). SSH as the fleet user (default `root`). Dual plane up: `sing-box.service` + `vincula-accountd.service`. |
| **New VPS** | Fresh Debian 12/13 or Ubuntu 22.04/24.04/26.04, amd64 or arm64. **No** prior Vincula install (`test ! -f /etc/vincula/VERSION`). Public IPv4 (or DNS) reachable on TCP 443 after restore. |
| **Controller workstation** | Linux or macOS for the replace SSH path; Python 3.10+; system OpenSSH (`ssh` / `scp` / `ssh-keyscan`). Unpacked `dist/vincula-controller-*.zip` **or** a git checkout of this `0.3.1-dev` tree. |
| **Win11 workstation** | Same zip. Python 3.10+ on PATH. OpenSSH Client optional feature. `bin\vcl-fleet.cmd`. Same `$FLEET_HOME` / `%APPDATA%\vincula` fleet as the Unix controller **or** a documented second init against the same nodes. |
| **age** | Distro `age` on the node used for step 7 (`command -v age`; **not** `tests/fixtures/fake-age`, **not** `$VCL_AGE_BIN` pointed at the fixture). |
| **Artifacts** | Built from this `0.3.1-dev` tree: `bash scripts/build-release.sh` and `bash scripts/build-controller.sh`. Do **not** regenerate `release.lock` unless first-party node files changed. |
| **Fleet registry** | Old VPS already `vcl-fleet node add NAME --host OLD --host-key SHA256:…`. `vcl-fleet status` SSH/PROXY/ACCOUNTING OK (accounting may be STALE; FAIL is not a starting point). |

Suggested names in the log: `OLD_HOST`, `NEW_HOST`, `NAME` (registry name).
Do **not** commit VLESS URIs, reissue CSV rows, age identity files, or SSH
private keys. Redact them in the evidence files.

## Evidence layout

Save every step under [`docs/evidence/0.3.1-live/`](evidence/0.3.1-live/)
(same pattern as [`docs/evidence/0.2.4-0.2.6-live/`](evidence/0.2.4-0.2.6-live/)):

| File | What to put there |
| --- | --- |
| `README.md` | Hosts, date, OS, overall PASS/FAIL, pointer to `SUMMARY.md` |
| `SUMMARY.md` | Per-step table: host, version, command, exit code, key output lines, result |

Full SSH transcripts may live on the VPS (`/root/vcl-rc-evidence/0.3.1-live/`)
and need not be mirrored in git. The in-repo files must still record enough
to audit the gate (commands, exit codes, identity rotation, handshake
PASS/FAIL **without** pasting secrets).

Per-step record (copy into `SUMMARY.md`):

```text
step:     (1)–(9) / Win11 / age
host:     OLD | NEW | controller | win11
version:  `vcl version` and/or `vcl-fleet version`
command:  exact argv
exit:     N
key lines:
result:   PASS | FAIL | SKIP
```

## Step-by-step

Placeholders: `NAME`, `OLD_HOST`, `NEW_HOST`, `NEW_HOST_KEY`.

### (1) Build artifacts (workstation, 0.3.1-dev tree)

```bash
git -C ~/projects/vcl describe --always --dirty
python3 bin/vcl-fleet version
# expect: vcl-fleet 0.3.1-dev

bash scripts/build-release.sh
bash scripts/build-controller.sh
ls -l dist/vincula-node-0.3.1-dev.tar.gz \
      dist/vincula-node-0.3.1-dev.tar.gz.sha256 \
      dist/vincula-controller-0.3.1-dev.zip \
      dist/vincula-controller-0.3.1-dev.zip.sha256
sha256sum -c dist/vincula-controller-0.3.1-dev.zip.sha256
```

Record product stamps and the two sidecar checksums. Copy the **node**
tarball (and its `.sha256`) to the new VPS. Unzip the **controller** zip on
the workstation you will use for replace (Unix and, later, Win11).

### (2) Secretless backup on the old node → scp to controller

On **OLD**:

```bash
vcl version
sudo vcl backup create --json
# expect: ok=true, secret_bearing=false, encryption=none, path=/var/backups/vincula/node-<node_id>-<UTC>.tar
```

On the **controller**:

```bash
mkdir -p "$FLEET_HOME/backups"
# FLEET_HOME is ${XDG_CONFIG_HOME:-~/.config}/vincula unless VCL_FLEET_HOME is set
scp root@OLD_HOST:/var/backups/vincula/node-*.tar "$FLEET_HOME/backups/"
chmod 0600 "$FLEET_HOME/backups/"node-*.tar
```

This is operator evidence that live `vcl backup create` works. Step (5)
`node replace` creates **another** secretless backup itself. Do **not** use
`--from-backup` for the happy path (that skip is only when the old host is
dead, and it can drop the audit tail).

### (3) `vcl backup verify`

Verify the archive **before** replace. Prefer the node helper on OLD (same
binary that wrote the tar):

```bash
# on OLD
sudo vcl backup verify /var/backups/vincula/node-<node_id>-<UTC>.tar --json
# expect: ok=true, secret_bearing=false
```

Step (5) `node replace` verifies again on the workstation by loading
`lib/vincula-backup.py` next to `vincula-fleet.py` (controller zip includes
that sibling). Record `ok`, `source_node_id`, `source_instance_id`. A
checksum mismatch is FAIL; do not proceed to replace.

### (4) Runtime-only install on NEW VPS

Copy `dist/vincula-node-0.3.1-dev.tar.gz` to NEW. Verify the pin, extract,
install **runtime only**:

```bash
# on NEW — pin required in production
sha256sum -c vincula-node-0.3.1-dev.tar.gz.sha256
tar -tzf vincula-node-0.3.1-dev.tar.gz | head
# extract so vincula.sh, bin/, lib/, release.lock are together, then:

sudo bash vincula.sh --runtime-only
# equivalent: sudo VCL_RUNTIME_ONLY=1 bash vincula.sh
# or bootstrap + flag (production pin required):
# sudo env RELEASE_URL='https://…/vincula-node-0.3.1-dev.tar.gz' \
#   RELEASE_SHA256='…' bash vincula-bootstrap.sh --runtime-only
```

**Must be true** before replace:

```bash
test -x /usr/local/bin/vcl; echo "vcl_exit=$?"
test ! -f /etc/vincula/VERSION; echo "no_version_exit=$?"   # 0 = file absent = good
test -f /etc/vincula/.runtime-only; echo "marker_exit=$?"
vcl version   # helper is installed; identity is not finished
```

`no_version_exit=0` (VERSION **absent**) is the gate. If VERSION exists, this
host is a finished bootstrap — replace will fail closed and you must not
“fix” it by deleting VERSION on a live identity. Wipe and start over, or use
another fresh VPS.

Pin the new host key on the controller:

```bash
ssh-keyscan -p 22 NEW_HOST 2>/dev/null | ssh-keygen -lf - -E sha256
# use the SHA256:… value as --host-key (unpadded)
```

### (5) Controller: `vcl-fleet node replace`

Watch the whole flow: final sync on OLD → secretless backup → scp to NEW →
local verify → preflight (`test -x /usr/local/bin/vcl` and
`test ! -f /etc/vincula/VERSION`) → remote
`vcl restore FILE --reissue-output /tmp/reissue.csv --server NEW_HOST --json`
→ identity + `vcl verify` → pull reissue CSV → registry `ssh_host=NEW` →
`instance_history` old retired / new active → old instance best-effort user
disable.

```bash
python3 bin/vcl-fleet version
python3 bin/vcl-fleet node replace NAME --host NEW_HOST --host-key SHA256:...
python3 bin/vcl-fleet node instances NAME
python3 bin/vcl-fleet verify
```

Expected human stdout (secrets redacted in the log):

```text
Replaced NAME (node_id=<uuid> still active).
old instance_id: <uuid>
new instance_id: <uuid>          # must differ; must not equal node_id
ssh_host: NEW_HOST
reissue_csv: …/reissue-NAME-<UTC>.csv
```

`--json` is allowed; record `ok=true`. Exit **0**. `node instances` shows
the old row `retired` and the new row `active`. Logical `NAME` stays
`active` (this is **not** `node retire`).

If restore committed but registry did not update, stderr tells you to
`vcl-fleet node set NAME --host OLD_HOST`. Treat that as FAIL for this
checklist; do not continue to AC-3.0-11 until registry points at NEW.

### (6) AC-3.0-11 — old URI fails on new IP; new URI works

Fixture tests only prove the old uuid is absent from inbound `users`.
**This step needs a real VLESS client** (sing-box / Clash / similar) on a
machine that is not the VPS.

1. **Before cut-over**, save the old client URI for one active user
   (`vcl user link TAG` on OLD, or the user’s existing client profile).
   It contains **old uuid + OLD_HOST:443**. Do not commit it.
2. After replace, open the reissue CSV (mode 0600). Use that user’s
   **new** `vless_uri` (new uuid + NEW_HOST:443).
3. **Attempt A (must FAIL):** take the **old** URI, rewrite only the host
   to `NEW_HOST` (keep old uuid / Reality public key / SNI). Connect to
   **NEW_HOST:443**. Record client, time, and the failure (auth / handshake
   / timeout). A TCP connect that then fails REALITY/VLESS is FAIL in the
   AC sense (good). A successful proxy session is a **checklist FAIL**.
4. **Attempt B (must succeed):** import the **new** URI as issued. Connect
   to NEW_HOST:443. Record success (`vcl` owner/user traffic, or a known
   site fetch through the proxy).
5. **Then** stop the old instance (`systemctl stop sing-box vincula-accountd`
   on OLD, or power off). Old uuid + **old** IP may still have worked until
   this step; that is operational cut-over, not a distributed revoke.

Record **both** attempts. AC-3.0-11 stays **PARTIAL / UNKNOWN** until this
log exists. Do not mark it PASS from unit tests.

### (7) Real `age` round-trip (`--include-secrets`)

On the **new** node (now a finished install) with distro `age`:

```bash
command -v age
age --version          # must not be tests/fixtures/fake-age
age-keygen -o /root/vincula-age-identity.txt
# copy the age1… public line into /root/vincula-age-recipient.txt

sudo vcl backup create --include-secrets \
  --age-recipient /root/vincula-age-recipient.txt
sudo vcl backup verify /var/backups/vincula/node-*.tar.age \
  --age-identity /root/vincula-age-identity.txt --json
# expect: ok=true, secret_bearing=true, encryption=age
```

Missing real `age`: `ERROR: Secret-bearing backup requires age.` — install
the distro package and retry. Do **not** point `$VCL_AGE_BIN` at the test
fixture. Do **not** commit identity/recipient files. Passphrase mode
(`age -p`) is not implemented.

### (8) Sync after replace

```bash
python3 bin/vcl-fleet sync --node NAME
echo "sync_exit=$?"
```

| Outcome | Meaning | What to record |
| --- | --- | --- |
| Exit 0, new rows or empty increment | Restored `MAX(event_id)` ≥ kept cursor; clean continuation | `last_event_id` before/after |
| Exit 2, `CURSOR_AHEAD` | Kept cursor is **ahead** of the restored DB (including `--from-backup` older snapshot). Controller must **not** import or advance. | stderr `--reseed NAME` guidance |
| Exit 2, `CURSOR_EXPIRED` | Retention hole; same `--reseed` guidance | do not restore again |

If `CURSOR_AHEAD` / `CURSOR_EXPIRED`:

```bash
python3 bin/vcl-fleet sync --reseed NAME
```

`--reseed` wipes that node’s local `audit_events` + `daily_usage` and does
**not** delete `instance_history`. A silent `ok` empty sync that leaves the
cursor past `MAX(event_id)` is a **FAIL** (that bug is closed in B7; this
step proves it on live data).

### (9) Evidence collection

Fill [`docs/evidence/0.3.1-live/README.md`](evidence/0.3.1-live/README.md)
and [`SUMMARY.md`](evidence/0.3.1-live/SUMMARY.md). Minimum fields per
step: host, `vcl version` / `vcl-fleet version`, command, exit code, key
output lines (redacted). Attach Win11 and real-age rows to the same pass.

## Win11 live `vcl-fleet.cmd` (same evidence pass)

On a real Windows 11 workstation, unzip `vincula-controller-0.3.1-dev.zip`:

```bat
py -3 bin\vcl-fleet.cmd version
bin\vcl-fleet.cmd help
bin\vcl-fleet.cmd status
bin\vcl-fleet.cmd verify
```

Record OS build, Python version, that `ssh.exe` is the system OpenSSH
Client, and at least `version` + one live SSH command (`status` or
`verify`) against the replaced node. Packaging tests are not this row.

## Acceptance — what flips the gate

Living-tree code remediations (B0–B13, B16) are **already** on this tree.
Known P0 on the living tree is **0**. This checklist does not re-open them.

The freeze-record recommendation stays **NOT READY** until live evidence
exists. Per the 发行门禁清单, **READY FOR RC** additionally requires the
rows below (fixture-only PASS is not enough). D20 24h soak still binds
**0.2.7 only** — do not block 0.3.1 RC on soak, and do not substitute soak
for live replace.

| Must-have evidence | This checklist |
| --- | --- |
| Live secretless replace | Steps (1)–(5): two real VPS; backup → restore → identity/verify; host, version, command, exit code recorded |
| AC-3.0-11 | Step (6): old URI → **new IP:443** fails; new URI succeeds; then stop old VPS. Fixture PARTIAL must not be marked PASS |
| Live `age --include-secrets` | Step (7): real `age` binary, not `tests/fixtures/fake-age` |
| Win11 live `vcl-fleet.cmd` | Same pass: real workstation, not zip-member tests |
| Bootstrap production pin | Already closed in B13 (code + unit). Optional live: bootstrap **without** `RELEASE_SHA256` dies; with pin, archive matches pin **and** shipped `.sha256` |
| Controller integrity | Already closed in B13/B16 (`controller.lock` + sidecar `.zip.sha256` in CI). Re-check in step (1) |
| P2-01 / P2-02 | Already closed on the living tree (B11/B12). Not re-run here |
| No open P0/P1 | known-issues living-tree Known P0 = **0**, consistent with code. Remaining RC gap is **this live log** |

Do **not** treat fake-ssh / fake-scp / fake-age as live evidence.
Do **not** document or send node restore `--replace-node`.
Do **not** install a finished bootstrap on NEW_HOST and then replace.

When `docs/evidence/0.3.1-live/SUMMARY.md` is overall **PASS**, update
[`release-readiness-0.3.0.md`](release-readiness-0.3.0.md) and
[`known-issues-0.3.0.md`](known-issues-0.3.0.md) in a later docs commit and
re-evaluate the recommendation. Until then: **NOT READY**.
