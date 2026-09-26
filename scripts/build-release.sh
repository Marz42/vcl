#!/usr/bin/env bash
# Build a deployable release tree under dist/ from the canonical repo root.
# Never edit dist/ by hand — regenerate from this script.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "$ROOT"

VERSION=$(grep -E '^readonly VINCULA_VERSION=' "${ROOT}/vincula.sh" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
[[ -n "$VERSION" ]] || { printf 'ERROR: could not parse VINCULA_VERSION\n' >&2; exit 1; }

NAME="vincula-node-${VERSION}"
DIST_ROOT="${ROOT}/dist"
OUT="${DIST_ROOT}/${NAME}"
ARCHIVE="${DIST_ROOT}/${NAME}.tar.gz"
LEGACY_NAME="vincula-${VERSION}"

FILES=(
  vincula.sh
  vincula-bootstrap.sh
  bin/vincula
  lib/vincula-common.sh
  lib/legacy_seed.py
  lib/sing-box-release.sh
  lib/vincula-accountd.py
  lib/accountd_runtime.py
  lib/observer.py
  lib/vincula-observer.socket
  lib/vincula-observer@.service
  lib/vincula-stats.py
  lib/vincula-audit.py
  lib/vincula-backup.py
  lib/telemetry_snapshot.py
  lib/vincula-accountd.service
)

printf 'Building %s\n' "$OUT"
mkdir -p "$DIST_ROOT"
rm -rf --one-file-system -- "$OUT" "${DIST_ROOT}/${LEGACY_NAME}"
rm -f -- "${DIST_ROOT}/${LEGACY_NAME}.tar.gz" "${DIST_ROOT}/${LEGACY_NAME}.tar.gz.sha256"
mkdir -p "$OUT/bin" "$OUT/lib"

for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { printf 'missing canonical file: %s\n' "$f" >&2; exit 1; }
  install -D -m 0644 "$f" "${OUT}/${f}"
done
chmod 0755 "${OUT}/vincula.sh" "${OUT}/vincula-bootstrap.sh" "${OUT}/bin/vincula"

(
  cd "$OUT"
  : > release.lock
  for f in vincula.sh vincula-bootstrap.sh bin/vincula lib/vincula-common.sh lib/legacy_seed.py lib/sing-box-release.sh lib/vincula-accountd.py \
           lib/accountd_runtime.py lib/observer.py lib/vincula-observer.socket lib/vincula-observer@.service lib/vincula-stats.py lib/vincula-audit.py lib/vincula-backup.py lib/telemetry_snapshot.py lib/vincula-accountd.service; do
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
# Deterministic tar: sorted names, fixed mtime/owner (SOURCE_DATE_EPOCH or HEAD).
# Normalize modes on a POSIX filesystem before archiving. WSL DrvFs reports
# files under /mnt/* as 0777 even after install/chmod, which otherwise changes
# the tar (and the controller zip that embeds it) for identical source bytes.
PACKAGE_TMP=$(mktemp -d /tmp/vcl-node-package.XXXXXXXX)
cleanup_package_tmp() {
  if [[ "${PACKAGE_TMP:-}" == /tmp/vcl-node-package.* && -d "$PACKAGE_TMP" ]]; then
    rm -rf --one-file-system -- "$PACKAGE_TMP"
  fi
}
trap cleanup_package_tmp EXIT
mkdir -p "${PACKAGE_TMP}/${NAME}"
cp -a -- "${OUT}/." "${PACKAGE_TMP}/${NAME}/"
find "${PACKAGE_TMP}/${NAME}" -type d -exec chmod 0755 {} +
find "${PACKAGE_TMP}/${NAME}" -type f -exec chmod 0644 {} +
chmod 0755 \
  "${PACKAGE_TMP}/${NAME}/vincula.sh" \
  "${PACKAGE_TMP}/${NAME}/vincula-bootstrap.sh" \
  "${PACKAGE_TMP}/${NAME}/bin/vincula"
[[ "$(stat -c %a "${PACKAGE_TMP}/${NAME}")" == 755 \
  && "$(stat -c %a "${PACKAGE_TMP}/${NAME}/lib/vincula-audit.py")" == 644 \
  && "$(stat -c %a "${PACKAGE_TMP}/${NAME}/bin/vincula")" == 755 ]] || {
  printf 'ERROR: /tmp does not support canonical POSIX package modes\n' >&2
  exit 1
}
# Clamp to 1980-01-01 UTC so packaging stays aligned with ZIP epoch rules.
TAR_EPOCH_MIN=315532800
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" log -1 --pretty=%ct 2>/dev/null || printf '%s' "$TAR_EPOCH_MIN")}"
if [[ "$SOURCE_DATE_EPOCH" -lt "$TAR_EPOCH_MIN" ]]; then
  SOURCE_DATE_EPOCH="$TAR_EPOCH_MIN"
fi
export SOURCE_DATE_EPOCH
tar --sort=name \
  --mtime="@${SOURCE_DATE_EPOCH}" \
  --owner=0 --group=0 --numeric-owner \
  --format=gnu \
  -C "$PACKAGE_TMP" -czf "$ARCHIVE" "$NAME"
( cd "$DIST_ROOT" && sha256sum -- "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256" )

printf 'wrote %s\n' "$OUT"
printf 'wrote %s\n' "$ARCHIVE"
cat "${ARCHIVE}.sha256"
printf 'OK package verified against release.lock\n'
