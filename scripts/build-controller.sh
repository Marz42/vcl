#!/usr/bin/env bash
# Build the workstation controller zip under dist/ from the canonical repo root.
# User-local tool: no release.lock and no installer integrity chain.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "$ROOT"

VERSION=$(grep -E '^readonly VINCULA_VERSION=' "${ROOT}/vincula.sh" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
[[ -n "$VERSION" ]] || { printf 'ERROR: could not parse VINCULA_VERSION\n' >&2; exit 1; }

NAME="vincula-controller-${VERSION}"
DIST_ROOT="${ROOT}/dist"
OUT="${DIST_ROOT}/${NAME}"
ARCHIVE="${DIST_ROOT}/${NAME}.zip"

FILES=(
  README-controller.md
  bin/vcl-fleet
  bin/vcl-fleet.cmd
  lib/vincula-fleet.py
)

printf 'Building %s\n' "$OUT"
rm -rf --one-file-system -- "$OUT"
mkdir -p "$OUT/bin" "$OUT/lib"

for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { printf 'missing canonical file: %s\n' "$f" >&2; exit 1; }
  install -D -m 0644 "$f" "${OUT}/${f}"
done
chmod 0755 "${OUT}/bin/vcl-fleet"

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: python3 is required to write the controller zip\n' >&2
  exit 1
}

rm -f -- "$ARCHIVE"
(
  cd "$DIST_ROOT"
  python3 -m zipfile -c "$(basename "$ARCHIVE")" "$NAME"
)

python3 - "$ARCHIVE" "$NAME" <<'PY'
import sys
import zipfile

archive, prefix = sys.argv[1], sys.argv[2]
need = (
    f"{prefix}/README-controller.md",
    f"{prefix}/bin/vcl-fleet",
    f"{prefix}/bin/vcl-fleet.cmd",
    f"{prefix}/lib/vincula-fleet.py",
)
forbidden = ("vincula.sh", "release.lock", "vincula-accountd.service")
with zipfile.ZipFile(archive) as zf:
    names = zf.namelist()
missing = [n for n in need if n not in names]
if missing:
    raise SystemExit("missing zip members: " + ", ".join(missing))
for name in names:
    base = name.rstrip("/").rsplit("/", 1)[-1]
    if base in forbidden:
        raise SystemExit(f"forbidden zip member: {name}")
PY

printf 'wrote %s\n' "$OUT"
printf 'wrote %s\n' "$ARCHIVE"
printf 'OK controller zip (no release.lock)\n'
