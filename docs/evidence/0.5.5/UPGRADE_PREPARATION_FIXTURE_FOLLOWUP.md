# Upgrade preparation fixture follow-up

Scope: tests only. Apply AFTER the original repair ZIP whose SHA256 is
 e7086374fddca22c7544466864281616b4ffe30985ad37f0ab508abf8e9c695c.
No production Python, helper, build inputs, or frozen artifacts changed here.

Changes:
- fake-ssh handles staged upgrade_prepare.py start/status across invocations.
  It reuses the backup and checkpoint handlers, persists terminal results,
  acknowledges RUNNING on start, and avoids rerunning an existing operation.
  This simulates the protocol, not actual Linux process supervision.
- Fix release.lock counts (20), batched SQLite source check, staged runner checks.
- Update admin-only apply fixture to reach preparation and assert its failure
  phase, rather than testing the removed installed-helper call.
- Require the migrate-fail fixture to contain the actual migrate failure detail;
  an ERROR from preparation no longer counts as a passing migration test.
- SSH argv evidence checks the staged runner command rather than a backup command
  now executed internally by the remote worker.
- Add cross-process fake-SSH test: start/status, repeat-start idempotency,
  successful checkpoint creation, backup failure preventing checkpoint, and
  unchanged source VERSION. Uses 900-second argument with a 10-second subprocess
  safety bound; no production node or SSH executable is used.

Local verification:
- New fake-SSH test PASS (success and failure subcases).
- Five embedded apply/post-check/rollback Python scenarios PASS.
- Prior repair suite: 6 PASS, 2 Linux-only SKIP on Windows.
- git diff --check PASS.
- Full user/root Bash suites NOT RUN in this Windows session.

Linux continuation:
Use a clean isolated worktree at 4651064 or 86f292b. Apply the original repair
then this follow-up; do not layer over the temporary assertion edits from the
previous experiment. Check the included BASE_INPUTS.json before applying.
Do not set VCL_UPGRADE_PREPARE_SECONDS=30: run at its default 900 seconds.
Run the new test_fake_upgrade_prepare.py and full user/root Bash suites. Retain
actual return codes, all logs, and counts. In particular verify migrate-fail
reaches migration, happy-path reaches SUCCESS, and no timeout loop occurs.

User-reported Linux validation of the ORIGINAL repair (not independently run):
211 Python user tests OK with 10 skips; root 211 OK with no skips; new suite 8/8.
400 MB restricted-IO benchmark: new backup 20.39s at 50 MB/s and 84.37s at 10 MB/s.
These are measured backup durations, not backup+checkpoint deadline proof.
The proposed 170-250s live estimate is not an acceptance result. Foreground
sleep latency is not an end-to-end proxy availability test. Live remains BLOCKED.

Additional existing gate: real detached-worker failure injection and the combined
backup+checkpoint resource budget must be validated before freezing a new RC.
No retry of fresh050 is authorized by this test-only follow-up.
