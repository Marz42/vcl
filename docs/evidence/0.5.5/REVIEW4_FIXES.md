# Review-4 fixes for preparation deadline, status and archive handoff

**Scope: exactly the three findings reported against PR #15 HEAD `424d5ab`.**
No new stress scenario, no change to the WAL or checkpoint design, and no
change to the frozen `dist/` artifacts.

- Reviewed HEAD: `424d5abb7a21defe6cdcaf4d24ef561f9d8e8198`
- Fix commit: `21aba22157994d70bfcf2c17c1ec4ff38b9e9880`
- Live: **BLOCKED**; no production node, apply, migrate or rollback was run.
- Candidate: **unfrozen**, not published.

## 1. Deadline guard teardown no longer depends on `save()`

`lib/upgrade_prepare.py` previously did:

```
save(status) -> deadline_fired.set() -> killpg(helper) -> _exit(1)
```

An `ENOSPC` (or any other `save()` failure) exited the guard thread before the
event, helper termination and namespace exit.  With a SIGSTOPed supervisor,
the worker was left without a deadline owner again.

The guard now, while holding `status_lock`:

1. re-reads the status and returns without cancelling if a terminal record is
   already published;
2. sets `deadline_fired` **before** attempting the write;
3. captures `proc_holder['proc']` before the write;
4. attempts the CANCELLED record, catching `BaseException` from `save()` and
   from the best-effort diagnostic `print`;
5. releases the lock and sends `SIGTERM` to the helper process group;
6. waits the existing 5 s grace and calls `os._exit(1)`.

The main thread's later `save_status()` therefore observes
`deadline_fired` even when the guard's write failed and cannot publish
`RUNNING`/`SUCCEEDED` after the deadline.

Regression:
`test_worker_deadline_guard_survives_status_write_failure` injects one
`OSError(ENOSPC)` on the guard's write, verifies `killpg(..., SIGTERM)` was
called, verifies the process exits in under 8 s, and verifies the final record
is `CANCELLED/PREPARATION_DEADLINE` (written by the main thread after the event
was published).  Measured locally: **4.0 s** (4 s deadline plus immediate helper teardown).

## 2. `read_status()` re-reads after acquiring the lock

The previous sequence was:

1. read `RUNNING` without the lock;
2. worker writes `SUCCEEDED` and closes the lock fd;
3. query acquires the now-free lock and writes `FAILED/WORKER_LOST` from the
   stale snapshot.

`read_status()` now re-reads the file **after** `lock()` succeeds.  A terminal
record published by the worker is returned unchanged.  Only a record that is
still `RUNNING` after lock acquisition is converged to
`FAILED/WORKER_LOST`.  A busy lock still returns the current record without
mutation.

Regression:
`test_read_status_keeps_terminal_state_published_before_lock` publishes
`SUCCEEDED` inside a wrapped `lock()` call, exactly between the query's first
read and lock acquisition, and asserts both the returned and on-disk state stay
`SUCCEEDED`.

## 3. Archive handoff checks verification-time size and mtime

`_check_archive_unchanged()` previously compared the pinned fd and the current
pathname to each other, then compared only dev/ino to the verification
evidence.  An in-place write updates both fd and pathname views of the same
inode, so an 8-byte file grown to 19 bytes still passed.

The expected tuple is now taken from the evidence written by
`verify_archive_fd()`:
`(archive_dev, archive_ino, archive_size, archive_mtime_ns)`.  Both the pinned
fd and the current pathname must match it.  This rejects:

- pathname replacement (dev/ino);
- in-place growth/truncation (size);
- in-place rewrite that preserves size (mtime).

This remains a **handoff consistency check**, not a byte re-verification.  A
consumer must still open and verify the archive bytes it actually uses; the
recorded `archive_sha256` is the value to compare.  That boundary is unchanged
and is restated in the function docstring.

Regression:
`test_archive_stability_rejects_in_place_growth` keeps the same inode, writes
8 bytes then 19 bytes, and asserts the second check raises
`backup archive changed`; the unchanged case is accepted first.

## Tests

- Targeted module: **19 passed, 0 failed** (`review4-targeted.log`).
- Full Python suite: **228 passed, 10 skipped, 0 failed** (`python.log`).
  This is +3 tests over the previous 225/10.
- Bash suites: **1970 passed** as the normal user and **1968 passed** in a
  root user namespace, 0 failed (626 s / 610 s).  The clean-copy runs used
  `b256a33`; its runtime files are byte-identical to `21aba22`, and the only
  difference is the Python test's deadline margin, which the Bash suites do
  not execute.  No pressure scenario was added or expanded.
- New tests:
  - `test_worker_deadline_guard_survives_status_write_failure`
  - `test_read_status_keeps_terminal_state_published_before_lock`
  - `test_archive_stability_rejects_in_place_growth`

## Candidate

Two independent clean `git archive` directories at fix commit
`21aba22157994d70bfcf2c17c1ec4ff38b9e9880`, with
`SOURCE_DATE_EPOCH=1794384920`:

| artifact | SHA256 (A = B) |
| --- | --- |
| `vincula-node-0.5.5.tar.gz` | `7b7a1b60d5dfa228291b3b99ac2dd87afd97c22d22d86f9d7732c86157b63c4b` |
| `vincula-controller-0.5.5.zip` | `784ca4d0ef6e8181d683ab6f8ee998e216038cbf789c257c7dd50936394c7892` |

Changed payload hashes:

- `lib/upgrade_prepare.py`:
  `46c7fca93b14f431ed5cefb9895017a6afb6ebe5c279d424ed644cce74e590c9`
- `release.lock`:
  `29dabae9586054f8f17a7834d311409229d4266d788359822e9a7b8a184d50cd`
- `tests/test_upgrade_prepare.py`:
  `ed130a184cf6209cdd7bbf65f221bc80da7ec4c4ec6d373d373a6bf7923c0f1d`

`bin/vincula`, `lib/node_upgrade.py`, `lib/vincula-backup.py` and the
checkpoint/WAL behaviour are byte-identical to `f86dd5e` / `424d5ab`.

`BUILD_INPUTS.json`, `build-A.log`, `build-B.log`, lock verification and
`SHA256SUMS` are in `review-artifacts/` and `review-evidence/build/`.  The
local candidate directory is
`/mnt/d/Repos/Vincula/release-candidates/0.5.5-21aba22` (not published).  The
review-4 delta patch is
`review-evidence/05-review4-fixes.patch`, SHA256
`ce3fa6a1fee34e47939f365d36b40bfd6b9c66cccf60005ba2caf041d98c0260`.
