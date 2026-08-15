#!/usr/bin/env bash
# Build installable trees for RC live upgrade from git tags v0.2.4 / v0.2.5 / v0.2.6.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
OUT_ROOT="${ROOT}/dist/rc-live"
WORKDIR="${ROOT}/dist/rc-worktrees"
TAGS=(v0.2.4 v0.2.5 v0.2.6)

assemble_tree() {
  local src=$1 dest=$2
  local f
  rm -rf --one-file-system -- "$dest"
  mkdir -p "$dest/bin" "$dest/lib"
  for f in vincula.sh vincula-bootstrap.sh bin/vincula \
           lib/vincula-common.sh lib/vincula-accountd.py \
           lib/vincula-accountd.service lib/vincula-event.schema.json; do
    [[ -f "${src}/${f}" ]] || { printf 'missing %s in %s\n' "$f" "$src" >&2; return 1; }
    install -D -m 0644 "${src}/${f}" "${dest}/${f}"
  done
  if [[ -f "${src}/lib/vincula-stats.py" ]]; then
    install -D -m 0644 "${src}/lib/vincula-stats.py" "${dest}/lib/vincula-stats.py"
  fi
  chmod 0755 "${dest}/vincula.sh" "${dest}/vincula-bootstrap.sh" "${dest}/bin/vincula"
  (
    cd "$dest"
    : > release.lock
    for f in vincula.sh bin/vincula lib/vincula-common.sh lib/vincula-accountd.py \
             lib/vincula-accountd.service lib/vincula-event.schema.json; do
      sha256sum -- "$f" >> release.lock
    done
    if [[ -f lib/vincula-stats.py ]]; then
      sha256sum -- lib/vincula-stats.py >> release.lock
    fi
    sha256sum -- vincula.sh | tee vincula.sh.sha256 >/dev/null
  )
  # Verify lock
  while read -r digest path; do
    [[ -n "${digest:-}" && -n "${path:-}" ]] || continue
    actual=$(sha256sum -- "${dest}/${path}" | awk '{print $1}')
    [[ "$actual" == "$digest" ]] || {
      printf 'digest mismatch %s\n' "$path" >&2
      return 1
    }
  done < "${dest}/release.lock"
  printf 'assembled %s\n' "$dest"
}

mkdir -p "$OUT_ROOT" "$WORKDIR"
cd "$ROOT"

for tag in "${TAGS[@]}"; do
  ver=${tag#v}
  wt="${WORKDIR}/${tag}"
  dest="${OUT_ROOT}/vincula-${ver}"
  printf '=== %s ===\n' "$tag"
  git rev-parse "$tag" >/dev/null
  rm -rf --one-file-system -- "$wt"
  git worktree remove --force "$wt" 2>/dev/null || true
  git worktree add --detach "$wt" "$tag"
  assemble_tree "$wt" "$dest"
  ver_file=$(grep -E '^readonly VINCULA_VERSION=' "${dest}/vincula.sh" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
  [[ "$ver_file" == "$ver" ]] || {
    printf 'ERROR: expected version %s got %s\n' "$ver" "$ver_file" >&2
    exit 1
  }
  tar -C "$OUT_ROOT" -czf "${OUT_ROOT}/vincula-${ver}.tar.gz" "vincula-${ver}"
  ( cd "$OUT_ROOT" && sha256sum -- "vincula-${ver}.tar.gz" > "vincula-${ver}.tar.gz.sha256" )
  git worktree remove --force "$wt"
done

printf '\nArtifacts ready under %s\n' "$OUT_ROOT"
ls -la "$OUT_ROOT"
