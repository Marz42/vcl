#!/usr/bin/env bash
# Generate release.lock with SHA-256 digests of first-party Vincula release files.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "$ROOT"

files=(
  vincula.sh
  vincula-bootstrap.sh
  bin/vincula
  lib/vincula-common.sh
  lib/vincula-accountd.py
  lib/vincula-stats.py
  lib/vincula-accountd.service
  lib/vincula-event.schema.json
)

out="${ROOT}/release.lock"
: > "$out"
for f in "${files[@]}"; do
  [[ -f "$f" ]] || { printf 'missing %s\n' "$f" >&2; exit 1; }
  sha256sum -- "$f" >> "$out"
done

sha256sum -- vincula.sh | tee vincula.sh.sha256 >/dev/null
printf 'wrote %s\n' "$out"
cat "$out"
