# Vincula live replace 0.3.1-dev

- Old host: _TBD_ (`OLD_HOST`)
- New host: _TBD_ (`NEW_HOST`)
- Date: _TBD_
- OS (old / new): _TBD_
- Controller: _TBD_ (Unix `vcl-fleet` / Win11 `vcl-fleet.cmd`)
- Tree: `0.3.1-dev` (`bash scripts/build-release.sh` + `bash scripts/build-controller.sh`)
- Operator: manual [`docs/live-replace-checklist.md`](../../live-replace-checklist.md)

**Overall: NOT RUN**

| Check | Result | Notes |
| --- | --- | --- |
| 01-build-artifacts | NOT RUN | `vcl-fleet version`, node tarball + controller zip + sidecars |
| 02-secretless-backup-scp | NOT RUN | old node `vcl backup create` → scp to `$FLEET_HOME/backups/` |
| 03-backup-verify | NOT RUN | `vcl backup verify` ok, `secret_bearing=false` |
| 04-runtime-only-new | NOT RUN | `vincula.sh --runtime-only`; **no** `/etc/vincula/VERSION` |
| 05-node-replace | NOT RUN | preflight, backup, scp, verify, restore `--reissue-output`, health, CSV, registry, old instance retired |
| 06-AC-3.0-11-old-uri | NOT RUN | old URI → new IP:443 **FAIL** (record client + error) |
| 06-AC-3.0-11-new-uri | NOT RUN | new URI **SUCCESS**; then stop old VPS |
| 07-real-age-roundtrip | NOT RUN | distro `age`, not `fake-age`; `--include-secrets` create + verify |
| 08-sync-after-replace | NOT RUN | clean continuation **or** `CURSOR_AHEAD` + `--reseed` guidance |
| 09-win11-vcl-fleet.cmd | NOT RUN | live `version` + `status`/`verify` on Win11 |

Record per step (host, `vcl version` / `vcl-fleet version`, command, exit code,
key output lines) in this file or in `/root/vcl-rc-evidence/0.3.1-live/` on the
VPS. Do not commit credentials.
