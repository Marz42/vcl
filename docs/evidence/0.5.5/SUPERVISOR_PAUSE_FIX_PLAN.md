# Supervisor pause gap — minimal fix plan (before code)

## Confirmed failure

The supervisor is the only deadline owner. `SIGSTOP` on it stops the only code
that can expire the deadline; the worker and helper keep running past the
absolute deadline. Resuming the supervisor later does converge, but while it
is stopped the operation has no deadline protection. This round treats that
as a real gap, not a documentation issue.

## Minimal mechanism

1. Keep the supervisor as the primary deadline owner and the holder of the
   operation lock.
2. The supervisor already passes the **same absolute monotonic deadline** to
   the worker as `VCL_PREPARE_DEADLINE_MONO`. Do not derive a second deadline
   and do not add any extension on resume.
3. In the worker, start exactly one daemon `deadline_guard` thread **before**
   the helper is launched. It sleeps until that absolute deadline.
4. On expiry, if status is still `RUNNING`:
   - atomically write `CANCELLED/PREPARATION_DEADLINE` with
     `deadline_owner="worker_guard"`;
   - set a `deadline_fired` event so subsequent main-thread status writes
     cannot publish `SUCCEEDED`;
   - send `SIGTERM` to the helper process group, wait at most the same 5 s
     grace, then `os._exit` the worker. The worker is namespace PID 1; kernel
     teardown removes any helper descendants that ignore TERM.
5. If the status is already terminal, the guard does nothing.
6. The guard thread is independent of the main thread's blocking calls, so it
   remains able to act while the main thread is in `proc.wait()`,
   `snapshot_sqlite()` or `verify_archive_fd()`. It is not a between-phase
   timestamp check and not another watchdog layer.

## Ownership and death matrix

| State | Who enforces deadline |
| --- | --- |
| both running | supervisor (primary); worker guard is a redundant same-deadline path |
| supervisor stopped | worker guard |
| worker stopped | supervisor |
| worker and supervisor stopped | neither; explicitly out of scope |
| worker SIGKILLed | supervisor observes exit and tears down namespace |
| supervisor SIGKILLed | worker PDEATHSIG handler writes failure and exits; kernel clears namespace |

No new 900 s budget is created. The guard is a thread inside the existing
worker, not a new service or a chain of watchdogs.

## Verification scope

- `SIGSTOP` supervisor only: status must become `CANCELLED` and descendants
  must disappear without requiring `SIGCONT`; lock must be free.
- `SIGSTOP` worker only: supervisor must still enforce the deadline.
- existing worker/supervisor `SIGKILL` cases: unchanged.
- second preparation during cleanup: still `PREPARATION_BUSY`; no overlap.
- 900 s shared budget: no reset and no second budget.
- unit test: block the main worker in a mocked archive verifier past the
  deadline; the guard must cancel without waiting for the verifier.

## Explicit boundaries

A fully frozen machine, all supervisor processes stopped together, a worker
stopped while its guard thread is also stopped, and a permanent kernel D state
are not solved by this mechanism. Those remain documented limits and are not
claimed as passes.

## Implementation note (after the plan)

The supervisor closes its own lock fd immediately after forking the worker.
The worker/helper tree holds the only lock copy; kernel namespace teardown
releases it after the worker tree is gone. This is required for the
`SIGSTOP supervisor` case: otherwise the stopped supervisor would keep the
lock fd and new operations would remain blocked even after the worker guard
had cleaned the namespace. It also means `read_status` can reconcile after the
worker tree is gone without waiting for a stopped supervisor.
