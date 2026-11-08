# 0.5.5 support-boundary verification handoff

Scope: isolated source validation and packaging only. Do not load the live
Workspace, start SSH, upgrade a Node, merge main, tag, or publish a release.
This patch includes the November 8 scope/document changes as well as code/tests.

## 1. Apply to an isolated LF checkout

Place `vcl-0.5.5-support-boundary.patch` from the handoff ZIP somewhere outside
the worktree. Replace PATCH below with that actual absolute path.

```bash
set -euo pipefail
PATCH=/absolute/path/vcl-0.5.5-support-boundary.patch
repo=/mnt/d/Repos/Vincula
work=$(mktemp -d "$HOME/vcl-055-boundary.XXXXXXXX")
git -C "$repo" -c core.autocrlf=false worktree add --detach "$work" 56a1626
cd "$work"
git apply --check "$PATCH"
git apply "$PATCH"
git diff --check
python3 - <<'PY'
import hashlib, json
from pathlib import Path
p=Path('docs/evidence/0.5.5/SUPPORT_BOUNDARY_SOURCE_INPUTS.json')
doc=json.loads(p.read_text())
bad=[]
for row in doc['source_files']:
    source=Path(row['path'])
    if not source.is_file() or hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=row['sha256_lf']:
        bad.append(row['path'])
assert not bad, bad
print('source inputs match:', len(doc['source_files']))
PY
```

Do not apply on top of unrelated edits. The patch does not contain secrets or
runtime Workspace data. Preserve the original candidate's build directory.

## 2. Linux tests and deterministic build

These commands require a Linux executor with noninteractive sudo available for
the temporary-filesystem privilege tests. If unavailable, report BLOCKED; do not
silently treat ordinary-user skips as privilege coverage.

```bash
export PYTHONDONTWRITEBYTECODE=1 SOURCE_DATE_EPOCH=1793689859
mkdir -p tmp/support-boundary
python3 -B -m unittest discover -s tests -p 'test_*.py' \
  2>&1 | tee tmp/support-boundary/python-user.log
sudo -n env PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
  -s tests -p 'test_*.py' 2>&1 | tee tmp/support-boundary/python-root.log
bash tests/test.sh 2>&1 | tee tmp/support-boundary/bash-user.log
sudo -n env PYTHONDONTWRITEBYTECODE=1 bash tests/test.sh \
  2>&1 | tee tmp/support-boundary/bash-root.log
bash scripts/build-release.sh 2>&1 | tee tmp/support-boundary/node-build.log
bash scripts/build-controller.sh 2>&1 | tee tmp/support-boundary/controller-build.log
sudo -n env PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/check-controller-artifact.py \
  dist/vincula-controller-0.5.5.zip 2>&1 | tee tmp/support-boundary/artifact.log
(cd dist && sha256sum -c vincula-node-0.5.5.tar.gz.sha256 \
  && sha256sum -c vincula-controller-0.5.5.zip.sha256)
(cd dist/vincula-node-0.5.5 && sha256sum -c release.lock)
(cd dist/vincula-controller-0.5.5 && sha256sum -c controller.lock)
sha256sum dist/vincula-node-0.5.5.tar.gz dist/vincula-controller-0.5.5.zip \
  > tmp/support-boundary/first-build.sha256
bash scripts/build-release.sh > tmp/support-boundary/node-rebuild.log 2>&1
bash scripts/build-controller.sh > tmp/support-boundary/controller-rebuild.log 2>&1
sha256sum -c tmp/support-boundary/first-build.sha256
```

Use `set -euo pipefail` throughout. Stop on any failure, retain the original log,
and record fixes/rechecks separately. Do not change expected digests to pass.
At this epoch the unchanged Node is expected to remain
`383362401f0574c44649e5071b81f31ab03f03f54588ee6456e62e4627524671`.
The revised Controller must not equal the original
`14312b21216bb4863a68c50ad9a443ac44786052c04b7648811cf4ca21ec233b`.
Both builds must match each other. Local PASS does not substitute for remote CI.

## 3. Review and freeze

- Return source-input verification, test counts/skips, failures, artifact-check
  JSON, both SHA256 values and deterministic-rebuild result first.
- After local validation, commit reviewed code/tests/docs to the development
  branch and run the existing required CI against that exact head. Keep the
  PR draft and main unchanged until human H05 PASS. Do not reuse CI #129.
- Run the separately recorded ten-node synthetic two-hour matrix with the new
  Observation inputs; it does not prove real SSH, proxy, or Node behavior.
- Generate the new source/artifact evidence with the actual source commit:

```bash
python3 -B docs/evidence/0.5.5/tools/gen-source-inputs.py \
  docs/evidence/0.5.5/SOURCE_INPUTS_SUPPORT_BOUNDARY_RC.json \
  --base-commit "$(git rev-parse HEAD)" --source-date-epoch 1793689859 \
  --artifact dist/vincula-node-0.5.5.tar.gz \
  --artifact dist/vincula-controller-0.5.5.zip \
  --payload-manifest dist/payload-manifest.json \
  --log tmp/support-boundary/python-user.log \
  --log tmp/support-boundary/python-root.log \
  --log tmp/support-boundary/bash-user.log \
  --log tmp/support-boundary/bash-root.log \
  --log tmp/support-boundary/artifact.log \
  --status 'BUILD VERIFIED / PENDING CI REVIEW / PENDING LIVE / PENDING HUMAN'
```

Only after the required checks and exact-head CI pass, add a new candidate freeze
record and update the current SUMMARY pointer. Keep original candidate records
as historical evidence. Final 24h live soak and H05 remain pending after code
freeze. Never set their status to PASS from offline tests.
