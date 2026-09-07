#!/usr/bin/env bash
# Build the workstation controller zip under dist/ from the canonical repo root.
# Integrity: per-member controller.lock inside the zip, plus an independent
# sidecar dist/vincula-controller-<ver>.zip.sha256. Not a node release.lock /
# installer chain (no vincula.sh).
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "$ROOT"

VERSION=$(grep -E '^VCL_FLEET_VERSION[[:space:]]*=' "${ROOT}/lib/vincula-fleet.py" | head -1 | sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/')
[[ -n "$VERSION" ]] || { printf 'ERROR: could not parse VCL_FLEET_VERSION\n' >&2; exit 1; }

NAME="vincula-controller-${VERSION}"
DIST_ROOT="${ROOT}/dist"
OUT="${DIST_ROOT}/${NAME}"
ARCHIVE="${DIST_ROOT}/${NAME}.zip"
SIDECAR="${ARCHIVE}.sha256"

FILES=(
  README-controller.md
  bin/vcl-fleet
  bin/vcl-fleet.cmd
  lib/vincula-fleet.py
  lib/vincula-audit.py
  lib/vincula-backup.py
  lib/vincula-audit-archive.py
  lib/provision.py
  lib/legacy_seed.py
  lib/sing_box_release.py
  lib/workspace.py
  lib/access.py
  lib/trust.py
  lib/legacy.py
  lib/ssh_transport.py
  lib/node_upgrade.py
  lib/observation/capabilities.py
  lib/observation/telemetry.py
  lib/observation/schema_validate.py
  lib/vincula-ui/server.py
  lib/vincula-ui/static/index.html
  lib/vincula-ui/static/app.css
  lib/vincula-ui/static/app.js
)

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: python3 is required to write the controller zip\n' >&2
  exit 1
}
command -v sha256sum >/dev/null 2>&1 || {
  printf 'ERROR: sha256sum is required to write controller integrity files\n' >&2
  exit 1
}

printf 'Building %s\n' "$OUT"
rm -rf --one-file-system -- "$OUT"
mkdir -p "$OUT/bin" "$OUT/lib" "$OUT/lib/vincula-ui/static"

for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { printf 'missing canonical file: %s\n' "$f" >&2; exit 1; }
  install -D -m 0644 "$f" "${OUT}/${f}"
done
chmod 0755 "${OUT}/bin/vcl-fleet"

# D51: embed pinned node payload (not in FILES / controller.lock — own digest+manifest).
NODE_VER=$(grep -E '^readonly VINCULA_VERSION=' "${ROOT}/vincula.sh" | sed -E 's/.*"([^"]+)".*/\1/')
[[ -n "$NODE_VER" ]] || { printf 'ERROR: could not parse VINCULA_VERSION for node payload\n' >&2; exit 1; }
NODE_TAR="${DIST_ROOT}/vincula-node-${NODE_VER}.tar.gz"
[[ -f "$NODE_TAR" && -f "${NODE_TAR}.sha256" ]] || {
  printf 'ERROR: run build-release.sh first: missing %s\n' "$NODE_TAR" >&2
  exit 1
}
mkdir -p "${OUT}/payload"
install -m 0644 "$NODE_TAR" "${NODE_TAR}.sha256" "${OUT}/payload/"
DIGEST=$(awk '{print $1}' "${NODE_TAR}.sha256")
python3 - <<PY
import json
import pathlib

p = pathlib.Path("${OUT}/payload/payload-manifest.json")
p.write_text(
    json.dumps(
        {
            "controller_version": "${VERSION}",
            "node_payload_version": "${NODE_VER}",
            "sha256": "${DIGEST}",
            "supported_os": [
                "debian12",
                "debian13",
                "ubuntu22.04",
                "ubuntu24.04",
                "ubuntu26.04",
            ],
            "supported_arch": ["amd64", "arm64"],
        },
        indent=2,
    )
    + "\n"
)
PY
install -m 0644 "${OUT}/payload/"* "${DIST_ROOT}/"

(
  cd "$OUT"
  : > controller.lock
  for f in "${FILES[@]}"; do
    sha256sum -- "$f" >> controller.lock
  done
)

while read -r digest path; do
  [[ -n "${digest:-}" && -n "${path:-}" ]] || continue
  actual=$(sha256sum -- "${OUT}/${path}" | awk '{print $1}')
  [[ "$actual" == "$digest" ]] || {
    printf 'ERROR: controller.lock mismatch for %s (lock=%s actual=%s)\n' "$path" "$digest" "$actual" >&2
    exit 1
  }
done < "${OUT}/controller.lock"

rm -f -- "$ARCHIVE" "$SIDECAR"
# ZIP local-file dates cannot precede 1980-01-01; clamp when git metadata is absent
# (e.g. some CI containers where `git log` fails → epoch 0).
ZIP_EPOCH_MIN=315532800
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" log -1 --pretty=%ct 2>/dev/null || printf '%s' "$ZIP_EPOCH_MIN")}"
if [[ "$SOURCE_DATE_EPOCH" -lt "$ZIP_EPOCH_MIN" ]]; then
  SOURCE_DATE_EPOCH="$ZIP_EPOCH_MIN"
fi
export SOURCE_DATE_EPOCH
(
  cd "$DIST_ROOT"
  python3 - "$NAME" "$(basename "$ARCHIVE")" "$SOURCE_DATE_EPOCH" <<'PY'
import datetime
import os
import sys
import zipfile
from pathlib import Path

prefix, archive_name, epoch_s = sys.argv[1], sys.argv[2], int(sys.argv[3])
root = Path(prefix)
# ZIP does not support timestamps before 1980-01-01 UTC.
ZIP_EPOCH_MIN = 315532800
epoch_s = max(epoch_s, ZIP_EPOCH_MIN)
ts = datetime.datetime.fromtimestamp(epoch_s, tz=datetime.timezone.utc)
date_time = (ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second)

files: list[Path] = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames.sort()
    for name in sorted(filenames):
        files.append(Path(dirpath) / name)
files.sort(key=lambda p: p.as_posix())

with zipfile.ZipFile(archive_name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in files:
        arc = path.as_posix()
        info = zipfile.ZipInfo(arc, date_time=date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3  # Unix
        data = path.read_bytes()
        # Normalize executable bit for bin/vcl-fleet
        if path.name == "vcl-fleet" and "bin/" in arc:
            info.external_attr = (0o755 << 16)
        else:
            info.external_attr = (0o644 << 16)
        zf.writestr(info, data)
PY
)

python3 - "$ARCHIVE" "$NAME" "$NODE_VER" <<'PY'
import sys
import zipfile

archive, prefix, node_ver = sys.argv[1], sys.argv[2], sys.argv[3]
need = (
    f"{prefix}/README-controller.md",
    f"{prefix}/bin/vcl-fleet",
    f"{prefix}/bin/vcl-fleet.cmd",
    f"{prefix}/lib/vincula-fleet.py",
    f"{prefix}/lib/vincula-audit.py",
    f"{prefix}/lib/vincula-backup.py",
    f"{prefix}/lib/vincula-audit-archive.py",
    f"{prefix}/lib/provision.py",
    f"{prefix}/lib/legacy_seed.py",
    f"{prefix}/lib/sing_box_release.py",
    f"{prefix}/lib/workspace.py",
    f"{prefix}/lib/access.py",
    f"{prefix}/lib/trust.py",
    f"{prefix}/lib/legacy.py",
    f"{prefix}/lib/ssh_transport.py",
    f"{prefix}/lib/node_upgrade.py",
    f"{prefix}/lib/observation/capabilities.py",
    f"{prefix}/lib/observation/telemetry.py",
    f"{prefix}/lib/observation/schema_validate.py",
    f"{prefix}/lib/vincula-ui/server.py",
    f"{prefix}/lib/vincula-ui/static/index.html",
    f"{prefix}/lib/vincula-ui/static/app.css",
    f"{prefix}/lib/vincula-ui/static/app.js",
    f"{prefix}/controller.lock",
    f"{prefix}/payload/vincula-node-{node_ver}.tar.gz",
    f"{prefix}/payload/vincula-node-{node_ver}.tar.gz.sha256",
    f"{prefix}/payload/payload-manifest.json",
)
# Forbid installer/lock at zip lib roots; payload tarball contents are opaque.
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

VERIFY_DIR=$(mktemp -d /tmp/vincula-controller-verify.XXXXXXXX)
cleanup_verify() { rm -rf --one-file-system -- "$VERIFY_DIR"; }
trap cleanup_verify EXIT
python3 - "$ARCHIVE" "$VERIFY_DIR" <<'PY'
import sys
import zipfile

zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
PY
(
  cd "${VERIFY_DIR}/${NAME}"
  sha256sum --check --status controller.lock
) || {
  printf 'ERROR: unpacked controller.lock failed sha256sum --check\n' >&2
  exit 1
}
cleanup_verify
trap - EXIT

(
  cd "$DIST_ROOT"
  sha256sum -- "$(basename "$ARCHIVE")" > "$(basename "$SIDECAR")"
  sha256sum --check --status "$(basename "$SIDECAR")"
) || {
  printf 'ERROR: controller zip failed sidecar SHA-256 check\n' >&2
  exit 1
}

printf 'wrote %s\n' "$OUT"
printf 'wrote %s\n' "$ARCHIVE"
printf 'wrote %s\n' "$SIDECAR"
cat "$SIDECAR"
printf 'OK controller zip (controller.lock + zip sha256)\n'
