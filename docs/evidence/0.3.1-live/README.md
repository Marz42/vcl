# Live replace evidence (0.3.1-dev)

**Result: NOT RUN.** B14 live VPS evidence is deferred.

Operator runbook: [`../../live-replace-checklist.md`](../../live-replace-checklist.md).
Fill [`SUMMARY.md`](SUMMARY.md) from a real two-VPS pass (secretless replace,
AC-3.0-11 handshake, real `age`, Win11 `vcl-fleet.cmd`).

Do not mark AC-3.0-11 PASS from fixtures. Do not treat fake-ssh / fake-age as
this directory. Full host logs may live under `/root/vcl-rc-evidence/0.3.1-live/`
on the VPS (not mirrored in-repo). Redact VLESS URIs, reissue CSV, and age
identity files before committing.
