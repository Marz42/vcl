# 400 MiB checkpoint-phase 32 s commit: localization

Two runs used the same 400 MiB schema-5 WAL DB, 5 commits/s, 10 MiB/s
read+write cgroup limit, cold reads, and the same 900 s preparation. The only
difference was the writer connection's `PRAGMA wal_autocheckpoint`:
**1000 pages (default)** versus **0**.

## Default (auto WAL checkpoint enabled)

- Total preparation: 152.87 s; checkpoint phase: 41.0 s.
- Writer: 767 commits, 0 failures.
- The one long commit was `seq=601`, planned at `t=...` and started 0.10 ms
  later; it completed **32,650 ms** later. It was in the checkpoint phase.
- Commit state sampled 1,615 `D` and 1 `R`; the process was in uninterruptible
  IO wait, not running a Python busy loop.
- 159 commits accumulated >1 s backlog (max 32,451 ms). This is a commit
  throughput tail, not 32 s of agent/API downtime.
- SQLite `busy_timeout=10000`; 32.65 s > 10 s, so this was not a SQLite
  `SQLITE_BUSY` lock wait.
- Checkpoint-phase write-lock probe: **204/204 `BEGIN IMMEDIATE` attempts
  succeeded**, 0 `database is locked`. No long DB write lock was held by the
  checkpoint.
- WAL before/after the long commit: **4,115,912 → 4,128,272 bytes** (delta
  12,360); `wal_autocheckpoint=1000` (~4,096,000 B). The threshold had just
  been crossed. The WAL was not truncated during the stall.
- cgroup: writer and preparation worker/supervisor in `vcllat`;
  `io.max=7:1 rbps=10485760 wbps=10485760`; `io.pressure` some/full
  avg10 92.59/87.19; `io.stat` 420,044,800 read / 1,267,830,784 written.

## Control (`wal_autocheckpoint=0`)

- Total preparation: 153.04 s; checkpoint phase: 41.16 s.
- Writer: 768 commits, 0 failures.
- **No commit over 1 s; max 0.267 s; 0 commits with >1 s backlog.**
- WAL grew higher (**5,265,392 B**) because no auto checkpoint ran.
- Checkpoint-phase write-lock probe: 206/206 acquired, 0 locked.
- Same 10 MiB/s limits; `io.pressure` some/full avg10 84.19/78.62.
- 400 MiB read/write counts and total duration were effectively unchanged.

## Conclusion

The 32 s commit is caused by the **writer's own automatic WAL checkpoint**
being triggered at the 1000-page threshold while the preparation holds the
long WAL read snapshot; the checkpoint cannot reset the WAL, and the writer's
commit waits in D state on the same 10 MiB/s block-device quota. It is not
primarily a DB write-lock wait (write-lock probes all succeeded, 32 s > 10 s
busy timeout) and it is not merely general IO load (the auto=0 control has the
same IO quota/pressure and no stall). Shared IO quota determines how long the
auto-checkpoint takes; the auto-checkpoint is the trigger.

This is a real throughput limitation during one checkpoint phase (~159 commits
delayed), but it does not by itself prove a 32 s agent/API outage.

## Minimal recommendation (not implemented this round)

1. Do not change the 900 s budget or the checkpoint read transaction for this.
2. Have the accountd writer use `wal_autocheckpoint=0` during preparation (or
   globally with a bounded periodic checkpoint), and run a **bounded passive
   checkpoint** after the preparation read snapshot is released. Keep an
   explicit WAL size cap and backpressure; do not let WAL grow without bound.
3. Measure actual request-path latency on a real node with the <=3 s target.
   If the auto-checkpoint commit is behind a request path, fix it; otherwise
   record it as a resource-limited throughput constraint, not proxy downtime.
