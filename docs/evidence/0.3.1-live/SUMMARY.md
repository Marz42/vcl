# Vincula live replace 0.3.1-dev

- Old host: `104.194.90.172` (Debian 13 amd64) — registry name `hotbeam`
- New host: `179.255.104.167` (Ubuntu 26.04 amd64)
- Date: 2026-08-18
- Controller: WSL2 `python3 bin/vcl-fleet` + Win11 `bin\vcl-fleet.cmd`
- Tree: `0.3.1-dev` (`1137423`)
- Operator: automated against operator-provided VPS

**node_id** (stable): `ec51fd29-796e-42e3-966d-e1e3dd92ff6d`  
**old instance_id**: `c0102fcb-567c-456f-8703-843e5416c095` (retired)  
**new instance_id**: `db1dcbe1-ebc2-499f-9a70-ec2ab4e6e4bf` (active)

**Overall: PASS**

| Check | Result | Notes |
| --- | --- | --- |
| 01-build-artifacts | PASS | `vcl-fleet 0.3.1-dev`; node tarball + controller zip + sidecars verified |
| 02-secretless-backup-scp | PASS | `vcl backup create --json` ok=`true` secret_bearing=`false`; scp to `$FLEET_HOME/backups/` mode 0600 |
| 03-backup-verify | PASS | `vcl backup verify` ok=`true` on OLD |
| 04-runtime-only-new | PASS | `vincula.sh --runtime-only`; `vcl_exit=0` `no_version_exit=0` `marker_exit=0` |
| 05-node-replace | PASS | `node replace hotbeam --host 179.255.104.167 --host-key SHA256:…` exit 0; reissue CSV 0600; old retired / new active; `vcl-fleet verify` SSH/PROXY/ACCOUNTING OK |
| 06-AC-3.0-11-old-uri | PASS | old `b14alice` URI host-rewritten to NEW:443 via sing-box client; curl socks exit **97** (SOCKS fail) — auth/handshake fail as required |
| 06-AC-3.0-11-new-uri | PASS | reissue `b14alice` URI; curl via socks exit **0**, `cdn-cgi/trace` OK; then OLD `systemctl stop` → inactive |
| 07-real-age-roundtrip | PASS | distro `/usr/bin/age` 1.2.1; `--include-secrets` create+verify ok=`true` encryption=`age` secret_bearing=`true` |
| 08-sync-after-replace | PASS | `vcl-fleet sync --node hotbeam` exit 0; status ok |
| 09-win11-vcl-fleet.cmd | PASS | Win11 NT 10.0.26200; Python 3.12.9; OpenSSH_for_Windows_9.5p2; `vcl-fleet.cmd version/status/verify` OK against NEW |

Per-step host transcripts kept off-repo under operator `/tmp/vcl-b14-evidence` (redact before any copy). Credentials not committed.
