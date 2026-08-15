#!/usr/bin/env bash
# vincula-bootstrap.sh — download a pinned Vincula release tarball, verify, exec installer.
#
# Usage:
#   RELEASE_URL=https://example.com/vincula-node-0.2.8-dev.tar.gz bash vincula-bootstrap.sh
#
# For local/dev installs from a full git/release tree, run sudo bash vincula.sh
# directly instead of this bootstrapper (no single-file curl|bash install).
#
# Optional:
#   RELEASE_SHA256=<hex>   expected archive digest (preferred over .sha256 sibling)
#   RELEASE_URL            archive URL (required unless embedded pin is set below)

set -Eeuo pipefail
IFS=$'\n\t'
umask 077

# Placeholder for release engineering to embed a default pin:
# EMBEDDED_RELEASE_URL="https://example.com/releases/vincula-node-0.2.8-dev.tar.gz"
# EMBEDDED_RELEASE_SHA256="<hex>"
EMBEDDED_RELEASE_URL="${EMBEDDED_RELEASE_URL:-}"
EMBEDDED_RELEASE_SHA256="${EMBEDDED_RELEASE_SHA256:-}"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

RELEASE_URL=${RELEASE_URL:-$EMBEDDED_RELEASE_URL}
[[ -n "$RELEASE_URL" ]] || die "Set RELEASE_URL to the vincula release tar.gz (or embed EMBEDDED_RELEASE_URL)."

command -v curl >/dev/null 2>&1 || die "curl is required"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required"
command -v tar >/dev/null 2>&1 || die "tar is required"

WORKDIR=$(mktemp -d /tmp/vincula-bootstrap.XXXXXXXX)
cleanup() { rm -rf --one-file-system -- "$WORKDIR"; }
trap cleanup EXIT

ARCHIVE="${WORKDIR}/vincula.tar.gz"
SUMFILE="${WORKDIR}/vincula.tar.gz.sha256"

printf 'Downloading %s\n' "$RELEASE_URL"
curl --fail --silent --show-error --location --output "$ARCHIVE" "$RELEASE_URL"

EXPECTED=${RELEASE_SHA256:-$EMBEDDED_RELEASE_SHA256}
if [[ -z "$EXPECTED" ]]; then
  curl --fail --silent --show-error --location --output "$SUMFILE" "${RELEASE_URL}.sha256" \
    || die "No RELEASE_SHA256 set and failed to download ${RELEASE_URL}.sha256"
  EXPECTED=$(awk '{print $1; exit}' "$SUMFILE")
fi
[[ "$EXPECTED" =~ ^[0-9a-fA-F]{64}$ ]] || die "Invalid SHA-256 pin."

ACTUAL=$(sha256sum "$ARCHIVE" | awk '{print $1}')
[[ "$ACTUAL" == "$EXPECTED" ]] || die "Archive SHA-256 mismatch (expected ${EXPECTED}, got ${ACTUAL})."
printf '✓ archive sha256 verified\n'

EXTRACT="${WORKDIR}/extract"
mkdir -p "$EXTRACT"
tar -xzf "$ARCHIVE" -C "$EXTRACT"

# Find release root (tar may contain a single top-level directory).
ROOT=$EXTRACT
if [[ ! -f "${ROOT}/vincula.sh" ]]; then
  mapfile -t kids < <(find "$EXTRACT" -mindepth 1 -maxdepth 1 -type d | head -n 2)
  (( ${#kids[@]} == 1 )) || die "Could not locate vincula.sh in archive."
  ROOT=${kids[0]}
fi
[[ -f "${ROOT}/vincula.sh" ]] || die "Archive missing vincula.sh"
[[ -f "${ROOT}/release.lock" ]] || die "Archive missing release.lock"

verify_release_lock() {
  local lock=$1 base=$2
  local hash path line
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -n "$line" ]] || continue
    hash=${line%% *}
    path=${line#*  }
    path=${path# }
    [[ -f "${base}/${path}" ]] || die "release.lock lists missing file: ${path}"
    actual=$(sha256sum "${base}/${path}" | awk '{print $1}')
    [[ "$actual" == "$hash" ]] || die "release.lock mismatch for ${path}"
  done < "$lock"
}

verify_release_lock "${ROOT}/release.lock" "$ROOT"
printf '✓ release.lock per-file hashes verified\n'

exec bash "${ROOT}/vincula.sh" "$@"
