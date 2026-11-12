# 0.5.5 preparation lifecycle, SQLite snapshot and archive handoff fixes

Base: `4651064` plus the previously reviewed repair/follow-up fixture patches.
This change is the follow-up to the FAIL evidence in
`dist/validation-055/real-worker-budget/` and does **not** alter the frozen
release artifacts.

## 1. Worker/supervisor lifetime

`start` still creates `prepare.lock` and `status.json`, but it now launches a
supervisor process. The supervisor:

1. creates a private mount + PID namespace;
2. forks the worker as PID 1 of that namespace;
3. holds a duplicate of the operation lock for the entire operation;
4. enforces the single deadline from the original `start` call.

Every helper and helper descendant is in the same PID namespace. Linux
guarantees that when namespace init exits, the kernel kills the remaining tasks
in that namespace before init can be reaped. This is the cleanup mechanism for
a worker `SIGKILL`; it is not a user-space watchdog that can itself be lost.

Responsibilities:

| event | timer/cleanup/status owner |
| --- | --- |
| worker killed | supervisor observes `waitpid`, writes `FAILED/WORKER_LOST`, then releases its lock fd |
| deadline | supervisor sends `SIGTERM` to namespace init, waits up to 5 s, sends `SIGKILL`; kernel clears the namespace |
| supervisor killed | worker has `PR_SET_PDEATHSIG(SIGUSR1)`; its handler writes `FAILED/WORKER_LOST` before exiting; kernel then clears the namespace |
| supervisor and worker both lost | `read_status` acquires the lock (proving all lock-fd holders are gone) and rewrites `RUNNING` to `FAILED/WORKER_LOST` |
| helper ignores TERM | worker exits; kernel clears every task in the namespace, including the helper |

The supervisor does not report success on behalf of the worker. A terminal
`SUCCEEDED` is written only by the worker after checkpoint; a missing worker
record becomes `FAILED/WORKER_LOST`. The lock is closed only after `waitpid`
returns, and the worker's namespace teardown is complete before that point.

`start` probes `CLONE_NEWPID` before writing `RUNNING`. If the kernel or
capability set does not allow it, the operation is written as
`FAILED/LIFECYCLE_UNAVAILABLE`; there is no silent fallback to the old
detached-process model. This requires root (or `CAP_SYS_ADMIN` in the initial
user namespace) on Linux. No systemd dependency was introduced.

## 2. SQLite snapshot starvation

`sqlite3.Connection.backup()` does not hold a read transaction between steps.
When the live writer commits between steps, the backup restarts from the
beginning. The old progress callback slept 5 ms per step, enlarging that
window, but removing the sleep alone does not fix the restart loop.

`snapshot_sqlite()` now:

* opens the source read-only and starts one explicit read transaction
  (`BEGIN` plus a `sqlite_master` read) so the whole copy sees one WAL snapshot;
* removes the per-progress-callback sleep;
* keeps `sleep=0.05` only for SQLite BUSY handling;
* rejects an expired `VCL_PREPARE_DEADLINE_MONO` from the progress callback,
  preserving an explicit, bounded failure.

The transaction is rolled back on error and committed after the copy. A
non-WAL source is explicitly refused (`unsupported journal_mode ...; accounting
snapshot requires WAL`): the pinned read transaction would otherwise hold a
SHARED lock and block/fail writers for the whole copy. Only the WAL accounting
DB is supported.

## 3. Backup handoff verification

After the backup helper returns JSON and before checkpoint starts, the worker:

1. requires an absolute path whose resolved parent is `BACKUP_ROOT`;
2. opens it with `O_RDONLY|O_CLOEXEC|O_NOFOLLOW` and requires a regular file,
   owner `euid`, and no group/other permission bits;
3. verifies through the **same descriptor** using the payload's own
   `lib/vincula-backup.py` (`verify_archive_fd`), not the helper's JSON;
4. checks the manifest's `source_node_id`/`source_instance_id`/version against
   the operation binding, rejects secret-bearing/encrypted archives, and
   records `archive_sha256`, size, device, inode and `mtime_ns`;
5. keeps the descriptor open through checkpoint and re-checks that the path
   still names the verified inode and that its size/mtime did not change.

Verification is a one-pass stream over the archive. It checks tar structure,
manifest schema, member names, size caps, per-member SHA-256, JSON/TOML
decodability, and secretless structure without extracting `accounting.db` to a
temporary file. A verification failure writes `backup.verify.json`, sets
`FAILED` with `backup_verification`, and does not start checkpoint or set
`migrate_started`.

This is a point-in-time handoff check. It does not lock the pathname for future
consumers: after the worker drops the descriptor, a later process can replace
the path. The Controller (or any consumer) must re-open and verify the archive
it actually consumes; the recorded digest/inode is the value to compare.

## Compatibility / limits

* Linux only; root or `CAP_SYS_ADMIN` is now required for `start`.
* A process in uninterruptible sleep (D state) cannot be killed until it wakes;
  the lock remains held during that interval.
* A stopped supervisor (`SIGSTOP`) cannot enforce its deadline; the record is
  not reported as success, but it can remain `RUNNING` until the supervisor is
  continued or killed.
* A later real-block-device run (loop ext4 + cgroup v2) enforced
  `cpu.max=200%` and `io.max=10 MiB/s` for reads and writes. A process-level
  write throttle remains only as supplemental evidence.
* The supervisor `SIGSTOP` case is a measured deadline gap: while stopped it
  cannot enforce the deadline. On `SIGCONT` it converges; this is not counted
  as a pass.
* No production node was contacted, no apply/migrate/rollback was performed.


## Review-round additions

* `cmd_upgrade_checkpoint` now writes an integrity manifest last. Every
  checkpoint member (regular file hash/size/mode or symlink target, including
  the completion marker) is covered.
* `cmd_upgrade_rollback` verifies that manifest before the service stop gate
  and before any target write. A tampered or manifest-less checkpoint is
  rejected with `checkpoint_integrity_failed`; the valid checkpoint path is
  unchanged.
* The manifest is corruption detection, not a signature: a writer able to
  replace both the checkpoint and its manifest can forge it.
