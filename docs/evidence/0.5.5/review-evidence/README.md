# Review evidence (sanitized)

These are the focused raw results for the 0.5.5 preparation review. No
production credentials, node state, checkpoints, or private keys are included.

- `lifecycle2-*`: worker/supervisor kill, SIGSTOP worker/supervisor, overlap,
  and no-CAP refusal. Host PIDs and operation IDs are test fixtures only.
- `latency/`: 400 MiB checkpoint-phase writer localization and the
  auto-checkpoint control.
- `checkpoint-compat/`: old-helper acceptance, candidate verify-only rejection,
  and candidate actual-rollback rejection.
- `regression/counts.json`: final Python/Bash counts; full logs are in the CI
  run and the source commit.
- `build/`: the two independent build logs and build input manifest.

Downloadable candidate binaries are in `../review-artifacts/`; `SHA256SUMS`
covers both artifacts. These are **unfrozen** candidates, not releases.
