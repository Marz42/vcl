# 0.5.5 upgrade preparation repair — implementation handoff

Status: IMPLEMENTED LOCALLY / PENDING LINUX / NOT FROZEN / LIVE BLOCKED.

## Scope

The 2026-11-09 fresh050 attempt timed out before payload/checkpoint/migration.
Remote backup continued after SSH exited. Proxy failures coincided with backup;
resource contention is a hypothesis, not an isolated causal measurement.

This incremental patch targets the 202-file support-boundary source snapshot
reported committed as 4651064 (docs-only child 86f292b is also suitable).
It preserves the former frozen evidence and artifacts. Do not apply the old
support-boundary handoff again. No production commands have been run here.

## Changes

- Upload and verify payload before preparation. The staged helper resolves its
  sibling backup library first, including when installed old code exists.
- Linux-only upgrade_prepare.py starts a detached, deadline-bounded worker.
  A private persistent operation record binds node/instance/source version and
  payload digest. A flock inherited by child commands prevents concurrent
  preparation. Lost RUNNING workers become UNKNOWN; unresolved records block
  new starts. No automatic resume of migration or repeated start after SSH loss.
- Default preparation deadline 900 seconds; VCL_UPGRADE_PREPARE_SECONDS accepts
  30..7200. Controller polls over short SSH calls. Remote deadline terminates
  only the owned child process group; local SSH loss is not cancellation.
- Worker runs nice +15 and attempts ionice idle class, recording the outcome.
  Both backup and checkpoint run under this policy. SQLite backup yields after
  batches of 256 pages (5 ms), with 50 ms BUSY retry sleep.
- Creation self-verifies tar bytes by streaming, keeping bounded text members
  in memory and checking DB hashes without re-extracting the DB. Existing restore
  verification behavior is retained. Staging shares the destination filesystem;
  publication fsyncs and renames rather than copying the whole tar again.
- Backup JSON records stage timings. Preparation errors return structured JSON
  with operation ID, remote state, migrate_started=false and retry_allowed=false.
  Unknown/failed preparations retain the remote stage and diagnostic files.
- Node build and release-lock generation include the new runner.

## Recovery boundary

Preparation records are under /var/lib/vincula/upgrade-operations/<UUID>/.
Directories/logs are private; checkpoint contains secrets. Do not commit them.
A retained stage contains lib/upgrade_prepare.py; query it with:

    python3 <retained-unpack>/lib/upgrade_prepare.py status <operation-id>

Status queries do not migrate. UNKNOWN requires operator investigation of the
record and live processes. Never delete a RUNNING record to bypass the lock.
This patch intentionally does not implement automatic UNKNOWN reconciliation,
reuse a previous snapshot for a new apply, or provide a general job service.
No manual cancel CLI is provided; the worker enforces its configured deadline.

The prepared snapshot predates subsequent accounting writes. Rollback is not
lossless. Lower priority cannot promise <=3s outage on a high-steal VPS.

## Validation performed here

- New Python suite: 6 PASS, 2 Linux-only tests SKIP (flock/process groups).
- Existing support-boundary suite: 7 PASS.
- Four embedded upgrade/post-check/rollback Python tests from test-fleet.sh:
  all PASS, executed directly with Python; this is not a full Bash suite run.
- Full Python suite using writable workspace TEMP: 211 discovered, 195 PASS,
  15 SKIP, 1 ERROR: local HTTP test cannot open socket (WinError 10013).
- First full run using Windows sandbox TEMP: 12 errors including rename denied;
  retained separately. Retest with workspace TEMP removed 11 path errors.
- Backup verify emits existing TemporaryDirectory ResourceWarning; not hidden.
- Python compilation and git diff --check checked separately.

## Required Linux validation (isolated worktree only)

1. Confirm baseline hashes in BASE_INPUTS.json; git apply --check repair.patch,
   then apply it. No production Workspace, bindings, keys or VPS access needed.
2. Run python3 -m unittest discover -s tests -p 'test_upgrade_prepare.py' -v.
   Both Linux-only tests MUST execute. The worker test uses temporary state and
   fake Bash helper commands; it does not touch /etc/vincula or system services.
3. Run all Python and Bash suites, user/root coverage as before. WSL root is
   accepted; do not add passwordless sudo merely to match invocation spelling.
4. Add/run integration evidence for real detached start/status, SSH reply loss,
   concurrent starts, supervisor loss, deadline with surviving shell children,
   disk-full/corrupt archives, old installed helper shadowing, and concurrent
   SQLite writes. The current unit tests do not replace this evidence.
5. Benchmark roughly 400 MB accounting data under 2-vCPU CPU/IO limits, recording
   stage durations and foreground latency. Compare against the prior code; no
   production backup repetition for benchmarking.
6. Build Node/Controller at the recorded epoch, verify locks/artifacts and repeat
   builds. Old expected artifact hashes MUST NOT be reused for the changed code.
7. CI and renewed matrix follow only after failures are resolved. Do not freeze
   or deploy until Linux tests and resource evidence have been reviewed.

No root Linux/Bash/build/CI/real SSH validation is claimed by this handoff.
