#!/usr/bin/env bash
# vincula-bootstrap.sh — download a pinned Vincula release tarball, verify, exec installer.
#
# Production (required):
#   RELEASE_URL=https://example.com/vincula-node-0.3.1-rc2.tar.gz \
#   RELEASE_SHA256=<hex> \
#   bash vincula-bootstrap.sh
#
# RELEASE_SHA256 (or a non-empty EMBEDDED_RELEASE_SHA256 baked in by release
# engineering) is the external pin. The published ${RELEASE_URL}.sha256 is
# fetched as well; the pin, that file, and the archive bytes must all agree.
#
# Fetching .sha256 from the same URL as the archive only detects transport
# corruption, not source replacement of both files. Production must pin the
# digest out-of-band (environment, image, or embed). Do not treat the sibling
# digest as a substitute for RELEASE_SHA256.
#
# Non-production only:
#   --allow-insecure-sibling-digest
#   (or VCL_ALLOW_INSECURE_SIBLING_DIGEST=1)
#   When no pin is set, use ${RELEASE_URL}.sha256 as the expected digest.
#
# For local/dev installs from a full git/release tree, run sudo bash vincula.sh
# directly instead of this bootstrapper (no single-file curl|bash install).
#
# Optional:
#   RELEASE_SHA256=<hex>   expected archive digest (required in production)
#   RELEASE_URL            archive URL (required unless embedded URL is set)

set -Eeuo pipefail
IFS=$'\n\t'
umask 077

# Placeholder for release engineering to embed a default pin:
# EMBEDDED_RELEASE_URL="https://example.com/releases/vincula-node-0.3.1-rc2.tar.gz"
# EMBEDDED_RELEASE_SHA256="<hex>"
EMBEDDED_RELEASE_URL="${EMBEDDED_RELEASE_URL:-}"
EMBEDDED_RELEASE_SHA256="${EMBEDDED_RELEASE_SHA256:-}"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

ALLOW_INSECURE_SIBLING=0
if [[ "${VCL_ALLOW_INSECURE_SIBLING_DIGEST:-0}" == "1" ]]; then
  ALLOW_INSECURE_SIBLING=1
fi
_bootstrap_args=()
for _arg in "$@"; do
  if [[ "$_arg" == "--allow-insecure-sibling-digest" ]]; then
    ALLOW_INSECURE_SIBLING=1
  else
    _bootstrap_args+=("$_arg")
  fi
done
set -- "${_bootstrap_args[@]}"

normalize_sha256() {
  local h=$1
  [[ "$h" =~ ^[0-9a-fA-F]{64}$ ]] || return 1
  printf '%s' "$h" | tr 'A-F' 'a-f'
}

RELEASE_URL=${RELEASE_URL:-$EMBEDDED_RELEASE_URL}
[[ -n "$RELEASE_URL" ]] || die "Set RELEASE_URL to the vincula release tar.gz (or embed EMBEDDED_RELEASE_URL)."

PIN_RAW=${RELEASE_SHA256:-$EMBEDDED_RELEASE_SHA256}
PIN=""
if [[ -n "$PIN_RAW" ]]; then
  PIN=$(normalize_sha256 "$PIN_RAW") || die "Invalid SHA-256 pin."
fi
if [[ -z "$PIN" && "$ALLOW_INSECURE_SIBLING" -eq 0 ]]; then
  die "Production bootstrap requires RELEASE_SHA256 (or a baked-in EMBEDDED_RELEASE_SHA256). Fetching ${RELEASE_URL}.sha256 from the same host only detects transport corruption, not source replacement. Pin the digest out-of-band. For non-production, pass --allow-insecure-sibling-digest."
fi

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

if ! curl --fail --silent --show-error --location --output "$SUMFILE" "${RELEASE_URL}.sha256"; then
  if [[ -n "$PIN" ]]; then
    die "Failed to download shipped digest ${RELEASE_URL}.sha256 (pin and shipped digest must both match the archive)."
  fi
  die "Failed to download ${RELEASE_URL}.sha256"
fi
SHIPPED_RAW=$(awk '{print $1; exit}' "$SUMFILE")
SHIPPED=$(normalize_sha256 "$SHIPPED_RAW") || die "Invalid SHA-256 in shipped digest file ${RELEASE_URL}.sha256."

ACTUAL=$(sha256sum "$ARCHIVE" | awk '{print $1}')
ACTUAL=$(printf '%s' "$ACTUAL" | tr 'A-F' 'a-f')

if [[ -n "$PIN" ]]; then
  [[ "$ACTUAL" == "$PIN" ]] || die "Archive SHA-256 mismatch (expected ${PIN}, got ${ACTUAL})."
  [[ "$SHIPPED" == "$PIN" ]] || die "Shipped digest ${RELEASE_URL}.sha256 does not match RELEASE_SHA256 pin."
fi
[[ "$ACTUAL" == "$SHIPPED" ]] || die "Archive SHA-256 mismatch against shipped digest (expected ${SHIPPED}, got ${ACTUAL})."
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
