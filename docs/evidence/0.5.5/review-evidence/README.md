# Review evidence (sanitized)

These are the focused raw results for the 0.5.5 preparation review. No
production credentials, node state, checkpoints, or private keys are included.

- `lifecycle2-*`: worker/supervisor kill, SIGSTOP worker/supervisor, overlap,
  and no-CAP refusal. Host PIDs and operation IDs are test fixtures only.
- `latency/`: 400 MiB checkpoint-phase writer localization and the
  auto-checkpoint control. Not rerun for review-4; unchanged code path.
- `checkpoint-compat/`: old-helper acceptance, candidate verify-only rejection,
  and candidate actual-rollback rejection. Not rerun for review-4; unchanged
  helper/rollback code.
- `regression/`: current Python counts and logs; the review-4 targeted log is
  `review4-targeted.log`, and `python.log` is the full suite. Existing Bash
  counts are in `counts.json`.
- `build/`: two independent build logs (`build-A.log`, `build-B.log`) and the
  build input manifest for the review-4 candidate.

Downloadable candidate binaries are in `../review-artifacts/`; `SHA256SUMS`
covers both artifacts. These are **unfrozen** candidates, not releases.
