# Shared sing-box release asset naming (provision preflight + vincula.sh installer).
# Keep in sync with lib/sing_box_release.py (tests assert parity).
readonly SING_BOX_VERSION="1.13.18"
readonly SING_BOX_RELEASE_BASE="https://github.com/SagerNet/sing-box/releases/download/v${SING_BOX_VERSION}"

release_asset_name() {
  printf 'sing-box-%s-linux-%s.tar.gz\n' "$SING_BOX_VERSION" "$1"
}

release_asset_url() {
  printf '%s/%s\n' "$SING_BOX_RELEASE_BASE" "$(release_asset_name "$1")"
}
