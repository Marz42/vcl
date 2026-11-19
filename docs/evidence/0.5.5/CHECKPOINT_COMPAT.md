# Checkpoint helper compatibility (final candidate)

## Helper used for checkpoint creation

`lib/upgrade_prepare.py` runs the staged helper path it was started with:

```
[python3, .../upgrade_prepare.py, ...] -> worker -> bash doc['helper'] upgrade checkpoint --json
doc['helper'] = <staged payload>/bin/vincula
```

In the isolated test the staged candidate was `/tmp/payload/bin/vincula`,
SHA-256 `8314b5385a689ccc419ad757779096f6f960e46d796103b68af7418f074215f8`.
`cmd_upgrade_checkpoint` writes the marker and the
`.vincula-upgrade-checkpoint.manifest.json` last.

## Helper embedded in the checkpoint

`cmd_upgrade_checkpoint` also copies `BASH_SOURCE` to
`<checkpoint>/upgrade-rollback-helper`. Tested hash:

```
8314b5385a689ccc419ad757779096f6f960e46d796103b68af7418f074215f8
```

It is the same candidate helper. This is the durable manual-recovery path.

## Automatic rollback helper

`lib/node_upgrade.py:_attempt_post_upgrade_rollback` invokes the **installed**
`vcl` (normally `/usr/local/bin/vcl`). It now first calls:

```
vcl upgrade rollback <checkpoint> --verify-only --json
```

If the installed helper is old and does not support `--verify-only`, the
preflight fails harmlessly and no rollback mutation occurs; the Controller
returns PARTIAL and leaves the embedded candidate helper as the operator
recovery path. If the installed helper is the candidate, preflight verifies
the manifest and the normal rollback follows (and verifies again).

This avoids the old behavior where an old installed `vcl` could be called for
an unverified mutation.

## Old helper evidence

Old helper from `9ea55c6`:
`aca00a2001168727000756bd36fecbbb0a0346a92b88093e36b1bf2a90ed3348`.

A real CLI test created a candidate checkpoint, corrupted its
`accounting.db`, then ran that old helper. It returned `ok:true` and replaced
the target DB: the old helper does not verify the manifest.

The candidate helper with `--verify-only` returned rc=1
`checkpoint_integrity_failed` for the same checkpoint and did not change the
target. The preflight unit tests cover old/unknown helper failure and the
candidate success path.

## No-manifest historical checkpoints

The candidate helper checks the manifest before the service-stop gate and
before any target write. A missing manifest, a mode/hash/size mismatch, an
extra/missing member, or an unlisted file is rejected with
`checkpoint_integrity_failed`; unit tests cover the missing-manifest and
tampered cases. Historical checkpoints without a manifest are rejected by the
candidate helper.

This does not remove rollback capability from the supported path: a candidate
checkpoint contains the manifest and the candidate preflight/rollback succeeds.
An old checkpoint handled by an old helper is outside the supported matrix.

Limits: the manifest is corruption/partial-replacement detection, not a
signature. A writer able to replace both the checkpoint and its manifest can
forge it. A deliberately invoked old helper can still accept an old checkpoint;
the automatic path now refuses that helper before mutation.
