#!/usr/bin/env bash
# Build a deployable release tree under dist/ from the canonical repo root.
# Never edit dist/ by hand — regenerate from this script.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "$ROOT"

VERSION=$(grep -E '^readonly VINCULA_VERSION=' "${ROOT}/vincula.sh" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
[[ -n "$VERSION" ]] || { printf 'ERROR: could not parse VINCULA_VERSION\n' >&2; exit 1; }

NAME="vincula-${VERSION}"
DIST_ROOT="${ROOT}/dist"
OUT="${DIST_ROOT}/${NAME}"
ARCHIVE="${DIST_ROOT}/${NAME}.tar.gz"

FILES=(
  vincula.sh
  vincula-bootstrap.sh
  bin/vincula
  lib/vincula-common.sh
  lib/vincula-accountd.py
  lib/vincula-accountd.service
  lib/vincula-event.schema.json
)

printf 'Building %s\n' "$OUT"
rm -rf --one-file-system -- "$OUT"
mkdir -p "$OUT/bin" "$OUT/lib"

for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { printf 'missing canonical file: %s\n' "$f" >&2; exit 1; }
  install -D -m 0644 "$f" "${OUT}/${f}"
done
chmod 0755 "${OUT}/vincula.sh" "${OUT}/vincula-bootstrap.sh" "${OUT}/bin/vincula"

(
  cd "$OUT"
  : > release.lock
  for f in vincula.sh bin/vincula lib/vincula-common.sh lib/vincula-accountd.py \
           lib/vincula-accountd.service lib/vincula-event.schema.json; do
    sha256sum -- "$f" >> release.lock
  done
  sha256sum -- vincula.sh | tee vincula.sh.sha256 >/dev/null
)

bash "${ROOT}/scripts/gen-release-lock.sh" >/dev/null

while read -r digest path; do
  [[ -n "${digest:-}" && -n "${path:-}" ]] || continue
  actual=$(sha256sum -- "${OUT}/${path}" | awk '{print $1}')
  [[ "$actual" == "$digest" ]] || {
    printf 'ERROR: digest mismatch for %s (lock=%s actual=%s)\n' "$path" "$digest" "$actual" >&2
    exit 1
  }
done < "${OUT}/release.lock"

rm -f -- "$ARCHIVE" "${ARCHIVE}.sha256"
tar -C "$DIST_ROOT" -czf "$ARCHIVE" "$NAME"
( cd "$DIST_ROOT" && sha256sum -- "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256" )

printf 'wrote %s\n' "$OUT"
printf 'wrote %s\n' "$ARCHIVE"
cat "${ARCHIVE}.sha256"
printf 'OK package verified against release.lock\n'
