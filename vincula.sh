#!/usr/bin/env bash
# vincula v0.2.7-dev
# Minimal, pinned sing-box bootstrap for Debian/Ubuntu VPS hosts.
#
# Supported environment overrides:
#   VCL_SERVER        Public IP address or hostname written to the VLESS URI.
#   VCL_PORT          Listening port (default: 443).
#   VCL_REALITY_HOST  REALITY handshake server and SNI (default: www.cloudflare.com).

set -Eeuo pipefail
IFS=$'\n\t'
umask 077

readonly VINCULA_VERSION="0.2.7-dev"
readonly SING_BOX_VERSION="1.13.18"
readonly SING_BOX_AMD64_SHA256="d34d987ed6ae39ca3760269264fb502b867e5477db45518c829b07776245c495"
readonly SING_BOX_ARM64_SHA256="a894f6152cade4a2c9d062762d54dea0c1aee673ab4759e0829e19cace932719"
readonly SING_BOX_RELEASE_BASE="https://github.com/SagerNet/sing-box/releases/download/v${SING_BOX_VERSION}"
readonly PUBLIC_IP_URL="https://api.ipify.org"
readonly DEFAULT_LISTEN="0.0.0.0"
readonly BACKUP_MARKER=".vincula-backup"
readonly DEFAULT_REALITY_HOST="www.cloudflare.com"
# Version-specific knowledge for SING_BOX_VERSION, not a permanent property of the domain.
# Revisit when the pinned sing-box release changes. See SagerNet/sing-box#4290.
readonly -a KNOWN_BAD_REALITY_HOSTS=(
  "www.microsoft.com"
)

readonly STATE_DIR="/etc/vincula"
readonly SING_BOX_DIR="/etc/sing-box"
readonly CONFIG_FILE="${SING_BOX_DIR}/config.json"
readonly BINARY_PATH="/usr/local/bin/sing-box"
readonly HELPER_PATH="/usr/local/bin/vincula"
readonly HELPER_ALIAS_PATH="/usr/local/bin/vcl"
readonly LIB_DIR="/usr/local/lib/vincula"
readonly SYSTEMD_UNIT="/etc/systemd/system/sing-box.service"
readonly ACCOUNTD_UNIT="/etc/systemd/system/vincula-accountd.service"
readonly ACCOUNTD_PY="${LIB_DIR}/vincula-accountd.py"
readonly STATS_PY="${LIB_DIR}/vincula-stats.py"
readonly EVENT_SCHEMA_FILE="${LIB_DIR}/vincula-event.schema.json"
readonly VAR_LIB_VINCULA="/var/lib/vincula"
readonly ACCOUNTING_DB_FILE="${VAR_LIB_VINCULA}/accounting.db"
readonly EVENTS_JSONL_FILE="${VAR_LIB_VINCULA}/events.jsonl"
readonly DEFAULT_CLASH_API_PORT=9090
readonly VERSION_FILE="${STATE_DIR}/VERSION"
readonly STATE_FILE="${STATE_DIR}/state.json"
readonly USERS_FILE="${STATE_DIR}/users.json"
readonly SETTINGS_FILE="${STATE_DIR}/config.toml"
readonly URI_FILE="${STATE_DIR}/owner.uri"
readonly BINARY_CHECKSUM_FILE="${STATE_DIR}/sing-box.binary.sha256"
readonly INSTALL_MANIFEST_FILE="${STATE_DIR}/install.manifest"
readonly MANIFEST_FILE="${LIB_DIR}/sing-box.lock"
readonly SERVICE_USER="sing-box"
readonly SERVICE_GROUP="sing-box"
readonly BACKUP_ROOT="/var/backups/vincula"
readonly VAR_LIB_SING_BOX="/var/lib/sing-box"
# Canonical state: state.json (node identity / REALITY), users.json (credentials),
# config.toml (non-secret admin settings). Generated artifacts: config.json, owner.uri, systemd unit.
# Ownership: install.manifest records Vincula-owned files; uninstall removes only those.

TMP_DIR=""
MUTATION_STARTED=0
INSTALL_COMMITTED=0
SERVICE_USER_CREATED=0
SERVICE_GROUP_CREATED=0
SERVICE_UID=""
SERVICE_GID=""
SERVICE_HOME=""
SERVICE_SHELL=""
MIGRATION_STARTED=0
MIGRATION_BACKUP=""

if [[ -t 1 ]]; then
  readonly C_GREEN=$'\033[32m'
  readonly C_YELLOW=$'\033[33m'
  readonly C_RED=$'\033[31m'
  readonly C_RESET=$'\033[0m'
else
  readonly C_GREEN=""
  readonly C_YELLOW=""
  readonly C_RED=""
  readonly C_RESET=""
fi

log_ok() {
  printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"
}

log_info() {
  printf '  %s\n' "$*"
}

log_warn() {
  printf '%s!%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2
}

die() {
  printf '%sERROR:%s %s\n' "$C_RED" "$C_RESET" "$*" >&2
  exit 1
}

verify_sibling_release_lock() {
  local src=${BASH_SOURCE[0]-} root lock line hash path actual
  [[ -n "$src" && "$src" != "-" && "$src" != /dev/fd/* ]] || return 0
  root=$(cd -- "$(dirname -- "$src")" && pwd 2>/dev/null || true)
  [[ -n "$root" ]] || return 0
  lock="${root}/release.lock"
  if [[ ! -f "$lock" ]]; then
    log_warn "release.lock not found beside installer; skipping first-party digest check"
    return 0
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -n "$line" ]] || continue
    hash=${line%% *}
    path=${line#*  }
    path=${path# }
    [[ -f "${root}/${path}" ]] || die "release.lock lists missing file: ${path}"
    actual=$(sha256sum "${root}/${path}" | awk '{print $1}')
    [[ "$actual" == "$hash" ]] || die "release.lock hash mismatch for ${path}"
  done < "$lock"
}

load_vincula_common() {
  local candidates=()
  local src=${BASH_SOURCE[0]-}
  if [[ -n "$src" && "$src" != "-" && "$src" != /dev/fd/* ]]; then
    local root
    root=$(cd -- "$(dirname -- "$src")" && pwd 2>/dev/null || true)
    if [[ -n "$root" ]]; then
      candidates+=("${root}/lib/vincula-common.sh")
    fi
  fi
  candidates+=("${LIB_DIR}/vincula-common.sh")
  local c
  for c in "${candidates[@]}"; do
    if [[ -f "$c" ]]; then
      # shellcheck disable=SC1091
      source "$c"
      return 0
    fi
  done
  return 1
}

# Prefer release-tree / installed common; stdin-only --version/--help still work without it.
verify_sibling_release_lock
load_vincula_common || true

usage() {
  cat <<'USAGE'
vincula v0.2.7-dev

Usage:
  sudo bash vincula.sh
  bash vincula.sh --help
  bash vincula.sh --version

Optional environment overrides:
  VCL_SERVER=203.0.113.10      Public address used in the client URI
  VCL_PORT=443                 Listening port
  VCL_REALITY_HOST=example.com REALITY handshake server and SNI

The normal installation path is non-interactive. Existing vincula v0.2.7-dev
credentials are preserved when the script is run again. Older 0.1.x and
0.2.0–0.2.6 installations are migrated in place without rotating UUID or REALITY keys.
Use 'vcl uninstall' to remove a Vincula-managed installation.
USAGE
}

cleanup_temp() {
  if [[ -n "${TMP_DIR:-}" && "$TMP_DIR" == /tmp/vincula.* && -d "$TMP_DIR" ]]; then
    rm -rf --one-file-system -- "$TMP_DIR"
  fi
}

rollback_install() {
  log_warn "Installation failed; removing files created by this transaction."
  systemctl disable --now sing-box.service >/dev/null 2>&1 || true
  systemctl disable --now vincula-accountd.service >/dev/null 2>&1 || true

  local path
  for path in \
    "$SYSTEMD_UNIT" \
    "$HELPER_ALIAS_PATH" \
    "$HELPER_PATH" \
    "$BINARY_PATH" \
    "$CONFIG_FILE" \
    "$VERSION_FILE" \
    "$STATE_FILE" \
    "$USERS_FILE" \
    "$SETTINGS_FILE" \
    "$URI_FILE" \
    "$BINARY_CHECKSUM_FILE" \
    "$INSTALL_MANIFEST_FILE" \
    "$MANIFEST_FILE" \
    "${LIB_DIR}/vincula-common.sh" \
    "$ACCOUNTD_PY" \
    "$STATS_PY" \
    "$EVENT_SCHEMA_FILE" \
    "$ACCOUNTD_UNIT" \
    "$ACCOUNTING_DB_FILE" \
    "${ACCOUNTING_DB_FILE}-wal" \
    "${ACCOUNTING_DB_FILE}-shm" \
    "$EVENTS_JSONL_FILE"; do
    if [[ -f "$path" || -L "$path" ]]; then
      rm -f -- "$path"
    fi
    rm -f -- "$path".new.*
  done

  rmdir -- "$STATE_DIR" "$SING_BOX_DIR" "$LIB_DIR" >/dev/null 2>&1 || true
  rmdir -- "$VAR_LIB_SING_BOX" >/dev/null 2>&1 || true
  rmdir -- "$VAR_LIB_VINCULA" >/dev/null 2>&1 || true
  systemctl daemon-reload >/dev/null 2>&1 || true

  if (( SERVICE_USER_CREATED == 1 )); then
    userdel "$SERVICE_USER" >/dev/null 2>&1 || true
  fi
  if (( SERVICE_GROUP_CREATED == 1 )); then
    groupdel "$SERVICE_GROUP" >/dev/null 2>&1 || true
  fi
}

rollback_migration() {
  log_warn "Migration failed; restoring the previous installation from backup."
  if [[ -z "${MIGRATION_BACKUP:-}" || ! -d "$MIGRATION_BACKUP" ]]; then
    log_warn "No migration backup directory is available."
    return
  fi

  systemctl disable --now vincula-accountd.service >/dev/null 2>&1 || true
  systemctl disable --now sing-box.service >/dev/null 2>&1 || true

  local path name
  for path in \
    "$SYSTEMD_UNIT" \
    "$HELPER_ALIAS_PATH" \
    "$HELPER_PATH" \
    "$CONFIG_FILE" \
    "$VERSION_FILE" \
    "$STATE_FILE" \
    "$USERS_FILE" \
    "$SETTINGS_FILE" \
    "$URI_FILE" \
    "$BINARY_CHECKSUM_FILE" \
    "$INSTALL_MANIFEST_FILE" \
    "$MANIFEST_FILE" \
    "${LIB_DIR}/vincula-common.sh" \
    "$ACCOUNTD_PY" \
    "$STATS_PY" \
    "$EVENT_SCHEMA_FILE" \
    "$ACCOUNTD_UNIT" \
    "$EVENTS_JSONL_FILE"; do
    name=$(basename -- "$path")
    if [[ -e "${MIGRATION_BACKUP}/${name}" || -L "${MIGRATION_BACKUP}/${name}" ]]; then
      mkdir -p -- "$(dirname -- "$path")"
      rm -f -- "$path"
      cp -a -- "${MIGRATION_BACKUP}/${name}" "$path"
    elif [[ "$path" == "$INSTALL_MANIFEST_FILE" || "$path" == "$ACCOUNTD_UNIT" || "$path" == "$ACCOUNTD_PY" || "$path" == "$STATS_PY" || "$path" == "$EVENT_SCHEMA_FILE" ]]; then
      rm -f -- "$path"
    fi
  done

  if [[ -f "${MIGRATION_BACKUP}/accounting.db" ]]; then
    mkdir -p -- "$VAR_LIB_VINCULA"
    rm -f -- "$ACCOUNTING_DB_FILE" "${ACCOUNTING_DB_FILE}-wal" "${ACCOUNTING_DB_FILE}-shm"
    cp -a -- "${MIGRATION_BACKUP}/accounting.db" "$ACCOUNTING_DB_FILE"
  fi

  systemctl daemon-reload >/dev/null 2>&1 || true

  local state_file="${MIGRATION_BACKUP}/SERVICE_STATE"
  local sing_enabled=0 sing_active=0 acct_enabled=0 acct_active=0
  if [[ -f "$state_file" ]]; then
    # shellcheck disable=SC1090
    source "$state_file" || true
  fi
  if (( sing_enabled == 1 )); then
    systemctl enable sing-box.service >/dev/null 2>&1 || true
  fi
  if (( sing_active == 1 )); then
    systemctl start sing-box.service >/dev/null 2>&1 || true
  fi
  if (( acct_enabled == 1 )); then
    systemctl enable vincula-accountd.service >/dev/null 2>&1 || true
  fi
  if (( acct_active == 1 )); then
    systemctl start vincula-accountd.service >/dev/null 2>&1 || true
  elif [[ -f "$ACCOUNTD_UNIT" ]]; then
    systemctl restart vincula-accountd.service >/dev/null 2>&1 || true
  fi
  if (( sing_active == 1 )) || [[ -f "$SYSTEMD_UNIT" ]]; then
    systemctl restart sing-box.service >/dev/null 2>&1 || true
  fi
}

on_exit() {
  local status=$1
  trap - EXIT
  if (( status != 0 && MIGRATION_STARTED == 1 && INSTALL_COMMITTED == 0 )); then
    rollback_migration
  elif (( status != 0 && MUTATION_STARTED == 1 && INSTALL_COMMITTED == 0 )); then
    rollback_install
  fi
  cleanup_temp
  exit "$status"
}

strip_os_value() {
  local value=$1
  value=${value#\"}
  value=${value%\"}
  value=${value#\'}
  value=${value%\'}
  printf '%s\n' "$value"
}

read_os_release() {
  local key value
  OS_ID=""
  OS_VERSION=""
  [[ -r /etc/os-release ]] || die "/etc/os-release is missing."

  while IFS='=' read -r key value; do
    case "$key" in
      ID) OS_ID=$(strip_os_value "$value") ;;
      VERSION_ID) OS_VERSION=$(strip_os_value "$value") ;;
    esac
  done < /etc/os-release

  OS_ID=${OS_ID,,}
  [[ -n "$OS_ID" && -n "$OS_VERSION" ]] || die "Could not identify the operating system."
}

is_supported_os() {
  local os_id=$1 os_version=$2
  case "${os_id}:${os_version}" in
    debian:12|debian:13|ubuntu:22.04|ubuntu:24.04|ubuntu:26.04) return 0 ;;
    *) return 1 ;;
  esac
}

map_arch() {
  case "$1" in
    x86_64|amd64) printf 'amd64\n' ;;
    aarch64|arm64) printf 'arm64\n' ;;
    *) return 1 ;;
  esac
}

expected_archive_sha256() {
  case "$1" in
    amd64) printf '%s\n' "$SING_BOX_AMD64_SHA256" ;;
    arm64) printf '%s\n' "$SING_BOX_ARM64_SHA256" ;;
    *) return 1 ;;
  esac
}

release_asset_name() {
  printf 'sing-box-%s-linux-%s.tar.gz\n' "$SING_BOX_VERSION" "$1"
}

release_asset_url() {
  printf '%s/%s\n' "$SING_BOX_RELEASE_BASE" "$(release_asset_name "$1")"
}

validate_port() {
  local port=$1
  [[ "$port" =~ ^[1-9][0-9]*$ ]] || return 1
  (( 10#$port <= 65535 ))
}

is_ipv4() {
  local value=$1 part
  local -a parts
  IFS='.' read -r -a parts <<< "$value"
  (( ${#parts[@]} == 4 )) || return 1
  for part in "${parts[@]}"; do
    [[ "$part" =~ ^[0-9]{1,3}$ ]] || return 1
    (( 10#$part <= 255 )) || return 1
  done
}

is_private_or_reserved_ipv4() {
  local value=$1
  local -a octets
  is_ipv4 "$value" || return 1
  IFS='.' read -r -a octets <<< "$value"
  (( 10#${octets[0]} == 0 )) && return 0
  (( 10#${octets[0]} == 10 )) && return 0
  (( 10#${octets[0]} == 127 )) && return 0
  (( 10#${octets[0]} == 169 && 10#${octets[1]} == 254 )) && return 0
  (( 10#${octets[0]} == 172 && 10#${octets[1]} >= 16 && 10#${octets[1]} <= 31 )) && return 0
  (( 10#${octets[0]} == 192 && 10#${octets[1]} == 168 )) && return 0
  (( 10#${octets[0]} == 100 && 10#${octets[1]} >= 64 && 10#${octets[1]} <= 127 )) && return 0
  (( 10#${octets[0]} == 192 && 10#${octets[1]} == 0 && 10#${octets[2]} == 2 )) && return 0
  (( 10#${octets[0]} == 198 && 10#${octets[1]} == 51 && 10#${octets[2]} == 100 )) && return 0
  (( 10#${octets[0]} == 203 && 10#${octets[1]} == 0 && 10#${octets[2]} == 113 )) && return 0
  (( 10#${octets[0]} >= 224 )) && return 0
  return 1
}

is_ipv6() {
  local value=$1 left right group count=0
  local -a groups
  [[ "$value" == *:* ]] || return 1
  [[ "$value" =~ ^[0-9A-Fa-f:]+$ ]] || return 1
  [[ "$value" != *:::* ]] || return 1

  if [[ "$value" == *::* ]]; then
    left=${value%%::*}
    right=${value#*::}
    [[ "$right" != *::* ]] || return 1

    if [[ -n "$left" ]]; then
      IFS=':' read -r -a groups <<< "$left"
      for group in "${groups[@]}"; do
        [[ "$group" =~ ^[0-9A-Fa-f]{1,4}$ ]] || return 1
        count=$((count + 1))
      done
    fi
    if [[ -n "$right" ]]; then
      IFS=':' read -r -a groups <<< "$right"
      for group in "${groups[@]}"; do
        [[ "$group" =~ ^[0-9A-Fa-f]{1,4}$ ]] || return 1
        count=$((count + 1))
      done
    fi
    (( count < 8 ))
  else
    [[ "$value" != :* && "$value" != *: ]] || return 1
    IFS=':' read -r -a groups <<< "$value"
    (( ${#groups[@]} == 8 )) || return 1
    for group in "${groups[@]}"; do
      [[ "$group" =~ ^[0-9A-Fa-f]{1,4}$ ]] || return 1
    done
  fi
}

is_dns_name() {
  local value=$1 label
  local -a labels
  (( ${#value} >= 1 && ${#value} <= 253 )) || return 1
  [[ "$value" == *.* && "$value" != *..* ]] || return 1
  IFS='.' read -r -a labels <<< "$value"
  for label in "${labels[@]}"; do
    (( ${#label} >= 1 && ${#label} <= 63 )) || return 1
    [[ "$label" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]] || return 1
  done
}

is_known_bad_reality_host() {
  local host=${1,,} candidate
  for candidate in "${KNOWN_BAD_REALITY_HOSTS[@]}"; do
    [[ "$host" == "${candidate,,}" ]] && return 0
  done
  return 1
}

die_known_bad_reality_host() {
  local host=$1
  die "${host} is known to be incompatible with
REALITY on the pinned sing-box version.

Upstream: SagerNet/sing-box#4290

Choose another target with VCL_REALITY_HOST."
}

select_reality_host() {
  local host
  if [[ -n "${VCL_REALITY_HOST:-}" ]]; then
    host=$VCL_REALITY_HOST
    is_dns_name "$host" || die "VCL_REALITY_HOST must be a valid DNS name."
  else
    host=$DEFAULT_REALITY_HOST
  fi
  if is_known_bad_reality_host "$host"; then
    die_known_bad_reality_host "$host"
  fi
  printf '%s\n' "$host"
}

curl_supports_socks5_hostname() {
  curl --help all 2>&1 | grep -q -- '--socks5-hostname'
}

is_supported_upgrade_from() {
  local from=$1
  [[ "$from" != "$VINCULA_VERSION" ]] || return 1
  case "$from" in
    0.1.0|0.1.1|0.1.2|0.1.3|0.1.4|0.1.5|0.2.0|0.2.1|0.2.2|0.2.3|0.2.4|0.2.5|0.2.6) return 0 ;;
    *) return 1 ;;
  esac
}

migrate_legacy_daily_retention() {
  # stdin unused. Args: source_version current_daily
  # stdout: new daily integer. Return 0 always.
  # If migrated 730→90, print the log line to stderr (log_info).
  local source=$1 current_daily=$2
  [[ -n "$current_daily" ]] || current_daily=90
  if is_supported_upgrade_from "$source" && [[ "$current_daily" == "730" ]]; then
    log_info "Migrated legacy default daily retention 730 → 90." >&2
    printf '%s\n' 90
    return 0
  fi
  printf '%s\n' "$current_daily"
}

print_local_success() {
  local port=$1
  log_ok "sing-box owns TCP ${port}"
  if systemctl is-active --quiet sing-box.service; then
    log_ok "sing-box.service active"
  fi
  if systemctl is-active --quiet vincula-accountd.service; then
    log_ok "vincula-accountd.service active"
  fi
  printf '\nLocal checks passed.\n\n'
  printf 'External TCP/%s reachability has NOT been verified.\n' "$port"
  printf 'Check the VPS provider firewall/security group before client testing.\n'
}

host_resolves() {
  local host=$1
  getent ahosts "$host" >/dev/null 2>&1
}

tcp_443_reachable() {
  local host=$1 ip
  ip=$(getent ahostsv4 "$host" 2>/dev/null | awk '{print $1; exit}')
  [[ -n "$ip" ]] || return 1
  timeout 5 bash -c "echo >/dev/tcp/${ip}/443" >/dev/null 2>&1
}

https_reachable() {
  local host=$1
  curl --silent --show-error --noproxy '*' \
    --proto '=https' --tlsv1.2 \
    --connect-timeout 5 --max-time 10 \
    --output /dev/null --head \
    "https://${host}/" >/dev/null 2>&1
}

ipv4_outbound_available() {
  timeout 5 bash -c 'echo >/dev/tcp/1.1.1.1/443' >/dev/null 2>&1
}

dns_resolution_working() {
  getent ahosts www.cloudflare.com >/dev/null 2>&1
}

preflight_reality_target() {
  local host=$1
  host_resolves "$host" || die "REALITY target ${host} did not resolve. Choose another target with VCL_REALITY_HOST."
  log_ok "REALITY target ${host} resolves"
  tcp_443_reachable "$host" || die "TCP ${host}:443 is not reachable from this host. Choose another target with VCL_REALITY_HOST."
  log_ok "TCP ${host}:443 reachable"
  https_reachable "$host" || die "HTTPS/TLS handshake to ${host} failed. Choose another target with VCL_REALITY_HOST."
  log_ok "HTTPS/TLS handshake to ${host} reachable"
}

pick_free_tcp_port() {
  local port attempt
  for (( attempt = 0; attempt < 30; attempt++ )); do
    port=$((32768 + RANDOM % 20000))
    if ! ss -H -ltn "sport = :${port}" 2>/dev/null | grep -q .; then
      printf '%s\n' "$port"
      return 0
    fi
  done
  return 1
}

wait_local_listen() {
  local port=$1 remaining
  for (( remaining = 0; remaining < 15; remaining++ )); do
    ss -H -ltn "sport = :${port}" 2>/dev/null | grep -q . && return 0
    sleep 1
  done
  return 1
}

render_self_test_server_config() {
  local output=$1 uuid=$2 private_key=$3 short_id=$4 port=$5 reality_host=$6
  cat > "$output" <<EOF
{
  "log": {
    "level": "warn",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "vless",
      "tag": "vless-selftest-in",
      "listen": "127.0.0.1",
      "listen_port": ${port},
      "users": [
        {
          "name": "selftest",
          "uuid": "${uuid}",
          "flow": "xtls-rprx-vision"
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "${reality_host}",
        "reality": {
          "enabled": true,
          "handshake": {
            "server": "${reality_host}",
            "server_port": 443
          },
          "private_key": "${private_key}",
          "short_id": "${short_id}"
        }
      }
    }
  ],
  "outbounds": [
    {
      "type": "direct",
      "tag": "direct"
    }
  ]
}
EOF
}

render_self_test_client_config() {
  local output=$1 uuid=$2 public_key=$3 short_id=$4 server_port=$5 socks_port=$6 reality_host=$7
  cat > "$output" <<EOF
{
  "log": {
    "level": "warn",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "socks",
      "tag": "socks-in",
      "listen": "127.0.0.1",
      "listen_port": ${socks_port}
    }
  ],
  "outbounds": [
    {
      "type": "vless",
      "tag": "vless-out",
      "server": "127.0.0.1",
      "server_port": ${server_port},
      "uuid": "${uuid}",
      "flow": "xtls-rprx-vision",
      "tls": {
        "enabled": true,
        "server_name": "${reality_host}",
        "utls": {
          "enabled": true,
          "fingerprint": "chrome"
        },
        "reality": {
          "enabled": true,
          "public_key": "${public_key}",
          "short_id": "${short_id}"
        }
      }
    }
  ]
}
EOF
}

run_reality_self_test() {
  local binary=$1 uuid=$2 private_key=$3 public_key=$4 short_id=$5 reality_host=$6
  (
    set -Eeuo pipefail
    umask 077
    work_dir=""
    owned_temp=0
    server_pid=0
    client_pid=0
    cleanup() {
      if [[ "${server_pid:-0}" -gt 0 ]]; then
        kill "$server_pid" >/dev/null 2>&1 || true
      fi
      if [[ "${client_pid:-0}" -gt 0 ]]; then
        kill "$client_pid" >/dev/null 2>&1 || true
      fi
      if [[ "${server_pid:-0}" -gt 0 ]]; then
        wait "$server_pid" >/dev/null 2>&1 || true
      fi
      if [[ "${client_pid:-0}" -gt 0 ]]; then
        wait "$client_pid" >/dev/null 2>&1 || true
      fi
      if [[ "${owned_temp:-0}" -eq 1 && -n "${work_dir:-}" && "$work_dir" == /tmp/vincula-selftest.* && -d "$work_dir" ]]; then
        rm -rf --one-file-system -- "$work_dir"
      fi
    }
    trap cleanup EXIT

    if [[ -n "${TMP_DIR:-}" && -d "$TMP_DIR" && "$TMP_DIR" == /tmp/vincula.* ]]; then
      work_dir="${TMP_DIR}/selftest"
      mkdir -p "$work_dir"
    else
      work_dir=$(mktemp -d /tmp/vincula-selftest.XXXXXXXX)
      owned_temp=1
    fi

    curl_supports_socks5_hostname || {
      printf 'ERROR: curl does not support SOCKS5; REALITY self-test cannot run.\n' >&2
      exit 1
    }

    server_port=$(pick_free_tcp_port) || {
      printf 'ERROR: Could not allocate a localhost port for the REALITY self-test server.\n' >&2
      exit 1
    }
    socks_port=$(pick_free_tcp_port) || {
      printf 'ERROR: Could not allocate a localhost port for the REALITY self-test client.\n' >&2
      exit 1
    }
    [[ "$server_port" != "$socks_port" ]] || socks_port=$(pick_free_tcp_port)

    server_json="${work_dir}/server.json"
    client_json="${work_dir}/client.json"
    server_log="${work_dir}/server.log"
    client_log="${work_dir}/client.log"
    render_self_test_server_config "$server_json" "$uuid" "$private_key" "$short_id" "$server_port" "$reality_host"
    render_self_test_client_config "$client_json" "$uuid" "$public_key" "$short_id" "$server_port" "$socks_port" "$reality_host"
    "$binary" check -c "$server_json" >/dev/null
    "$binary" check -c "$client_json" >/dev/null

    "$binary" run -c "$server_json" >"$server_log" 2>&1 &
    server_pid=$!
    wait_local_listen "$server_port" || {
      printf 'ERROR: REALITY self-test server did not listen on 127.0.0.1:%s.\n' "$server_port" >&2
      cat "$server_log" >&2 || true
      exit 1
    }

    "$binary" run -c "$client_json" >"$client_log" 2>&1 &
    client_pid=$!
    wait_local_listen "$socks_port" || {
      printf 'ERROR: REALITY self-test client did not listen on 127.0.0.1:%s.\n' "$socks_port" >&2
      cat "$client_log" >&2 || true
      exit 1
    }

    http_code=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
      --connect-timeout 5 --max-time 20 \
      --socks5-hostname "127.0.0.1:${socks_port}" \
      --proto '=https' --tlsv1.2 \
      --head "https://${reality_host}/" || true)
    if [[ "$http_code" =~ ^[23][0-9][0-9]$ || "$http_code" == "403" || "$http_code" == "404" ]]; then
      exit 0
    fi
    printf 'ERROR: REALITY end-to-end self-test failed for %s (HTTP status %s).\n' "$reality_host" "${http_code:-none}" >&2
    printf '--- self-test server log ---\n' >&2
    cat "$server_log" >&2 || true
    printf '--- self-test client log ---\n' >&2
    cat "$client_log" >&2 || true
    exit 1
  )
}

validate_server() {
  local value=$1
  if [[ "$value" == *:* ]]; then
    is_ipv6 "$value"
  elif [[ "$value" =~ ^[0-9.]+$ ]]; then
    is_ipv4 "$value"
  else
    is_dns_name "$value"
  fi
}


parse_private_key() {
  sed -n 's/^PrivateKey:[[:space:]]*//p' <<< "$1" | head -n 1
}

parse_public_key() {
  sed -n 's/^PublicKey:[[:space:]]*//p' <<< "$1" | head -n 1
}

ensure_dependencies() {
  local -a packages=()
  command -v curl >/dev/null 2>&1 || packages+=(curl)
  [[ -s /etc/ssl/certs/ca-certificates.crt ]] || packages+=(ca-certificates)
  command -v tar >/dev/null 2>&1 || packages+=(tar)
  command -v sha256sum >/dev/null 2>&1 || packages+=(coreutils)
  command -v install >/dev/null 2>&1 || packages+=(coreutils)
  command -v systemctl >/dev/null 2>&1 || packages+=(systemd)
  command -v useradd >/dev/null 2>&1 || packages+=(passwd)
  command -v getent >/dev/null 2>&1 || packages+=(libc-bin)
  command -v ss >/dev/null 2>&1 || packages+=(iproute2)
  command -v ip >/dev/null 2>&1 || packages+=(iproute2)
  command -v timeout >/dev/null 2>&1 || packages+=(coreutils)
  command -v awk >/dev/null 2>&1 || packages+=(mawk)
  command -v sed >/dev/null 2>&1 || packages+=(sed)
  command -v grep >/dev/null 2>&1 || packages+=(grep)
  command -v python3 >/dev/null 2>&1 || packages+=(python3)

  if (( ${#packages[@]} > 0 )); then
    local package_list
    command -v apt-get >/dev/null 2>&1 || die "Required commands are missing and apt-get is unavailable."
    printf -v package_list '%s ' "${packages[@]}"
    log_info "Installing required OS packages: ${package_list% }"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"
  fi
}

check_systemd() {
  [[ -d /run/systemd/system ]] || die "systemd is not running as PID 1."
  systemctl --version >/dev/null 2>&1 || die "systemctl is not usable."
}

port_is_listening() {
  local port=$1
  ss -H -ltn "sport = :${port}" 2>/dev/null | grep -q .
}

ss_line_is_sing_box_pid() {
  local line=$1 pid=$2
  [[ "$line" == *'"sing-box"'* ]] || return 1
  [[ "$line" == *"pid=${pid},"* || "$line" == *"pid=${pid})"* ]]
}

port_owned_by_sing_box() {
  local port=$1 main_pid line
  main_pid=$(systemctl show -p MainPID --value sing-box.service 2>/dev/null || true)
  [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || return 1
  while IFS= read -r line; do
    ss_line_is_sing_box_pid "$line" "$main_pid" && return 0
  done < <(ss -H -ltnp "sport = :${port}" 2>/dev/null || true)
  return 1
}

detect_public_server() {
  local candidate=""
  if [[ -n "${VCL_SERVER:-}" ]]; then
    validate_server "$VCL_SERVER" || die "VCL_SERVER must be an IPv4 address, an unbracketed IPv6 address, or a DNS name."
    printf '%s\n' "$VCL_SERVER"
    return
  fi

  candidate=$(curl -4 --fail --silent --show-error --noproxy '*' \
    --proto '=https' --tlsv1.2 --connect-timeout 5 --max-time 10 \
    "$PUBLIC_IP_URL" 2>/dev/null || true)
  candidate=${candidate//$'\r'/}
  candidate=${candidate//$'\n'/}

  if [[ -n "$candidate" ]] && is_ipv4 "$candidate"; then
    if is_private_or_reserved_ipv4 "$candidate"; then
      die "Public IP lookup returned a private or reserved address (${candidate}). Re-run with VCL_SERVER=<public-IPv4-or-hostname>."
    fi
    printf '%s\n' "$candidate"
    return
  fi

  if [[ -n "$candidate" ]] && is_ipv6 "$candidate"; then
    die "Public IP lookup returned IPv6 (${candidate}). V0.1 prefers IPv4; re-run with VCL_SERVER=<IPv4-or-hostname> or VCL_SERVER=${candidate}."
  fi

  candidate=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i=="src") {print $(i+1); exit}}' || true)
  if [[ -n "$candidate" ]] && is_ipv4 "$candidate" && ! is_private_or_reserved_ipv4 "$candidate"; then
    log_warn "Public IP lookup failed; using the local IPv4 address ${candidate}."
    printf '%s\n' "$candidate"
    return
  fi

  if [[ -n "$candidate" ]] && is_private_or_reserved_ipv4 "$candidate"; then
    die "Could not determine a public IPv4 address (local route is ${candidate}). Re-run with VCL_SERVER=<public-IPv4-or-hostname>."
  fi

  die "Could not determine a public IPv4 address. Re-run with VCL_SERVER=<public-IPv4-or-hostname>."
}

download_sing_box() {
  local arch=$1 destination_dir=$2
  local asset archive expected extracted_root binary actual_version
  asset=$(release_asset_name "$arch")
  archive="${destination_dir}/${asset}"
  expected=$(expected_archive_sha256 "$arch")
  extracted_root="sing-box-${SING_BOX_VERSION}-linux-${arch}"

  log_info "Downloading pinned sing-box ${SING_BOX_VERSION} (${arch})" >&2
  curl --fail --location --silent --show-error \
    --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --retry 3 --retry-all-errors --connect-timeout 10 --max-time 300 \
    --output "$archive" "$(release_asset_url "$arch")"

  if ! printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status; then
    die "sing-box archive SHA-256 verification failed."
  fi
  log_ok "sing-box archive SHA-256 verified" >&2

  tar --extract --gzip --file "$archive" --directory "$destination_dir" \
    --no-same-owner --no-same-permissions "${extracted_root}/sing-box"
  binary="${destination_dir}/${extracted_root}/sing-box"
  chmod 0755 "$binary"

  actual_version=$("$binary" version | awk 'NR==1 {print $3}')
  [[ "$actual_version" == "$SING_BOX_VERSION" ]] || die "Extracted binary reports version ${actual_version:-unknown}, expected ${SING_BOX_VERSION}."
  printf '%s\n' "$binary"
}

render_sing_box_config_with_users() {
  local output=$1 users_json=$2 private_key=$3 short_id=$4 port=$5 reality_host=$6
  local listen=${7:-$DEFAULT_LISTEN}
  local clash_api_port=${8:-$DEFAULT_CLASH_API_PORT}
  local clash_secret=${9:-}
  local sniff=${10:-true}
  write_sing_box_server_config "$output" "$users_json" "$private_key" "$short_id" "$port" "$reality_host" \
    "$listen" "$clash_api_port" "$clash_secret" "$sniff"
}

render_sing_box_config() {
  local output=$1 uuid=$2 private_key=$3 short_id=$4 port=$5 reality_host=$6
  local users_json
  # Keep each field on its own line so json_quoted_field (line-oriented) still works.
  users_json=$(printf '[\n  {\n    "name": "owner",\n    "uuid": "%s",\n    "flow": "xtls-rprx-vision"\n  }\n]' "$uuid")
  render_sing_box_config_with_users "$output" "$users_json" "$private_key" "$short_id" "$port" "$reality_host"
}

render_sing_box_config_from_registry() {
  local output=$1 users_file=$2 private_key=$3 short_id=$4 port=$5 reality_host=$6
  local listen clash_port clash_secret sniff
  listen=${7:-$DEFAULT_LISTEN}
  clash_port=${8:-$DEFAULT_CLASH_API_PORT}
  clash_secret=${9:-}
  sniff=${10:-true}
  if [[ -z "$clash_secret" ]]; then
    clash_secret=$(generate_clash_api_secret)
  fi
  render_sing_box_config_accounting "$output" "$users_file" "$private_key" "$short_id" \
    "$port" "$reality_host" "$listen" "$clash_port" "$clash_secret" "$sniff"
}


render_state() {
  local output=$1 server=$2 port=$3 reality_host=$4 uuid=$5 private_key=$6 public_key=$7 short_id=$8 installed_at=$9 arch=${10}
  local created_user=${11:-false}
  local created_group=${12:-false}
  local uid=${13:-0}
  local gid=${14:-0}
  local home=${15:-/var/lib/sing-box}
  local shell=${16:-/usr/sbin/nologin}
  local node_id=${17:-}
  local node_name=${18:-}
  case "$created_user" in true|false) ;; *) created_user=false ;; esac
  case "$created_group" in true|false) ;; *) created_group=false ;; esac
  [[ "$uid" =~ ^[0-9]+$ ]] || uid=0
  [[ "$gid" =~ ^[0-9]+$ ]] || gid=0
  [[ -n "$node_id" ]] || node_id=$(generate_uuid_v4)
  [[ -n "$node_name" ]] || node_name=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo node)
  # uuid param retained for call-site compatibility; credential UUID lives only in users.json.
  : "${uuid:-}"
  cat > "$output" <<EOF
{
  "schema_version": 1,
  "project_version": "${VINCULA_VERSION}",
  "sing_box_version": "${SING_BOX_VERSION}",
  "architecture": "${arch}",
  "installed_at": "${installed_at}",
  "node": {
    "node_id": "${node_id}",
    "node_name": "${node_name}",
    "server": "${server}",
    "listen": "${DEFAULT_LISTEN}",
    "port": ${port},
    "reality_handshake_server": "${reality_host}",
    "reality_server_name": "${reality_host}",
    "reality_private_key": "${private_key}",
    "reality_public_key": "${public_key}",
    "reality_short_id": "${short_id}"
  },
  "service_account": {
    "user": "${SERVICE_USER}",
    "uid": ${uid},
    "group": "${SERVICE_GROUP}",
    "gid": ${gid},
    "home": "${home}",
    "shell": "${shell}",
    "created_by_vincula": ${created_user},
    "group_created_by_vincula": ${created_group}
  }
}
EOF
}

render_users() {
  local output=$1 uuid=$2 installed_at=$3
  local user_id=${4:-}
  local credential_id=${5:-}
  local node_id=${6:-}
  local display_name=${7:-Owner}
  [[ -n "$user_id" ]] || user_id=$(generate_uuid_v4)
  [[ -n "$credential_id" ]] || credential_id=$(generate_uuid_v4)
  [[ -n "$node_id" ]] || node_id=$(generate_uuid_v4)
  cat > "$output" <<EOF
{
  "schema_version": 2,
  "users": [
    {
      "user_id": "${user_id}",
      "tag": "owner",
      "display_name": "${display_name}",
      "department": "",
      "enabled": true,
      "created_at": "${installed_at}",
      "credentials": [
        {
          "credential_id": "${credential_id}",
          "node_id": "${node_id}",
          "uuid": "${uuid}",
          "status": "active",
          "created_at": "${installed_at}",
          "revoked_at": null
        }
      ]
    }
  ]
}
EOF
}

render_settings() {
  local output=$1 server=$2 port=$3 reality_host=$4 arch=$5
  local clash_port=${6:-$DEFAULT_CLASH_API_PORT}
  local clash_secret=${7:-}
  local raw_days=${8:-90}
  local daily_days=${9:-90}
  local node_id=${10:-}
  local node_name=${11:-}
  local cycle_start=${12:-1}
  if [[ -z "$clash_secret" ]]; then
    clash_secret=$(generate_clash_api_secret)
  fi
  [[ -n "$node_id" ]] || node_id=$(generate_uuid_v4)
  [[ -n "$node_name" ]] || node_name=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo node)
  [[ -n "$cycle_start" ]] || cycle_start=1
  cat > "$output" <<EOF
project_version = "${VINCULA_VERSION}"
sing_box_version = "${SING_BOX_VERSION}"
architecture = "${arch}"
node_id = "${node_id}"
node_name = "${node_name}"
server = "${server}"
listen = "${DEFAULT_LISTEN}"
port = ${port}
reality_handshake_server = "${reality_host}"
reality_server_name = "${reality_host}"
clash_api_port = ${clash_port}
clash_api_secret = "${clash_secret}"
accounting_raw_retention_days = ${raw_days}
accounting_daily_retention_days = ${daily_days}
billing_cycle_start_day = ${cycle_start}
EOF
}


render_manifest() {
  local output=$1 arch=$2 archive_sha=$3 binary_sha=$4
  cat > "$output" <<EOF
project=vincula
project_version=${VINCULA_VERSION}
sing_box_version=${SING_BOX_VERSION}
architecture=${arch}
source_url=$(release_asset_url "$arch")
archive_sha256=${archive_sha}
binary_sha256=${binary_sha}
EOF
}

render_install_manifest() {
  local output=$1
  cat > "$output" <<EOF
schema_version=1
project=vincula
project_version=${VINCULA_VERSION}

file=${BINARY_PATH}
file=${HELPER_PATH}
symlink=${HELPER_ALIAS_PATH}
file=${CONFIG_FILE}
file=${STATE_FILE}
file=${USERS_FILE}
file=${SETTINGS_FILE}
file=${URI_FILE}
file=${BINARY_CHECKSUM_FILE}
file=${VERSION_FILE}
file=${INSTALL_MANIFEST_FILE}
file=${MANIFEST_FILE}
file=${SYSTEMD_UNIT}
file=${LIB_DIR}/vincula-common.sh
file=${ACCOUNTD_PY}
file=${STATS_PY}
file=${EVENT_SCHEMA_FILE}
file=${ACCOUNTD_UNIT}
file=${ACCOUNTING_DB_FILE}
file=${EVENTS_JSONL_FILE}

directory=${STATE_DIR}
directory=${SING_BOX_DIR}
directory=${LIB_DIR}
directory=${VAR_LIB_VINCULA}

service=sing-box.service
service=vincula-accountd.service
EOF
}


manifest_values() {
  local file=$1 kind=$2
  awk -F= -v kind="$kind" '$1 == kind { print substr($0, index($0, "=") + 1) }' "$file"
}

unit_has_vincula_marker() {
  local unit_file=$1
  [[ -f "$unit_file" ]] || return 1
  grep -q '^# Managed-By: vincula$' "$unit_file"
}

helper_has_vincula_marker() {
  local helper_file=$1
  [[ -f "$helper_file" ]] || return 1
  grep -q '^# Managed-By: vincula$' "$helper_file" \
    && grep -q 'readonly VINCULA_VERSION=' "$helper_file"
}

symlink_target_is() {
  local link=$1 expected=$2
  [[ -L "$link" ]] || return 1
  [[ "$(readlink -- "$link")" == "$expected" ]]
}

is_uninstall_affirmative() {
  case "$1" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

service_account_flag() {
  local state_file=$1 field=$2
  local value
  value=$(json_bool_field "$state_file" "$field")
  [[ "$value" == true ]]
}

remove_managed_file() {
  local path=$1
  if [[ ! -e "$path" && ! -L "$path" ]]; then
    return 0
  fi
  if [[ -d "$path" && ! -L "$path" ]]; then
    log_warn "${path} is a directory; not removing with file deletion."
    return 0
  fi
  rm -f -- "$path"
  log_ok "Removed ${path}"
}

remove_managed_symlink() {
  local path=$1 expected_target=$2
  if [[ ! -e "$path" && ! -L "$path" ]]; then
    return 0
  fi
  if [[ ! -L "$path" ]]; then
    log_warn "${path} is not a Vincula symlink; preserved."
    return 1
  fi
  if [[ "$(readlink -- "$path")" != "$expected_target" ]]; then
    log_warn "${path} points elsewhere; preserved."
    return 1
  fi
  rm -f -- "$path"
  log_ok "Removed ${path}"
}

remove_directory_if_empty() {
  local dir=$1
  if [[ ! -e "$dir" && ! -L "$dir" ]]; then
    return 0
  fi
  if [[ -L "$dir" || ! -d "$dir" ]]; then
    log_warn "${dir} is not a directory; preserved."
    return 1
  fi
  if rmdir -- "$dir" 2>/dev/null; then
    log_ok "Removed ${dir}"
    return 0
  fi
  log_warn "${dir} contains unmanaged files; directory preserved."
  return 1
}

verify_binary_matches_checksum() {
  local checksum_file=$1
  [[ -f "$checksum_file" ]] || return 1
  sha256sum --check --status "$checksum_file"
}

write_backup_marker() {
  local dir=$1 source_version=$2
  cat > "${dir}/${BACKUP_MARKER}" <<EOF
project=vincula
type=migration-backup
version=${VINCULA_VERSION}
source_version=${source_version}
EOF
  chmod 0600 "${dir}/${BACKUP_MARKER}"
}

is_vincula_backup_dir() {
  local dir=$1
  [[ -d "$dir" ]] || return 1
  if [[ -f "${dir}/${BACKUP_MARKER}" ]]; then
    grep -q '^project=vincula$' "${dir}/${BACKUP_MARKER}" || return 1
    grep -Eq '^type=(migration-backup|mutation-backup)$' "${dir}/${BACKUP_MARKER}" || return 1
    return 0
  fi
  [[ -f "${dir}/state.json" ]] || return 1
  grep -q '"project_version"' "${dir}/state.json" || return 1
  grep -q '"reality_private_key"' "${dir}/state.json" || return 1
}

passwd_identity_matches() {
  local expected_uid=$1 expected_gid=$2 expected_home=$3 expected_shell=$4
  local actual_uid=$5 actual_gid=$6 actual_home=$7 actual_shell=$8
  [[ "$expected_uid" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "$expected_gid" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ -n "$expected_home" && -n "$expected_shell" ]] || return 1
  [[ "$expected_uid" == "$actual_uid" && "$expected_gid" == "$actual_gid" && "$expected_home" == "$actual_home" && "$expected_shell" == "$actual_shell" ]]
}

resolve_migration_reality_host() {
  local current=$1
  if ! is_known_bad_reality_host "$current"; then
    printf '%s\n' "$current"
    return 0
  fi
  [[ -n "${VCL_REALITY_HOST:-}" ]] || return 1
  select_reality_host
}

install_manifest_matches_expected() {
  local actual=$1
  local expected rc
  expected=$(mktemp)
  render_install_manifest "$expected"
  cmp -s "$expected" "$actual"
  rc=$?
  rm -f -- "$expected"
  return "$rc"
}

render_systemd_unit() {
  local output=$1
  cat > "$output" <<'UNIT'
# Managed-By: vincula
# Vincula-Version: 0.2.7-dev
[Unit]
Description=sing-box (managed by vincula)
Documentation=https://sing-box.sagernet.org/
After=network-online.target nss-lookup.target
Wants=network-online.target

[Service]
Type=simple
User=sing-box
Group=sing-box
ExecStartPre=/usr/local/bin/sing-box check -c /etc/sing-box/config.json
ExecStart=/usr/local/bin/sing-box run -c /etc/sing-box/config.json
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5s
LimitNOFILE=1048576
UMask=0027
StateDirectory=sing-box
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
UNIT
}


installer_root() {
  local src=${BASH_SOURCE[0]-}
  if [[ -n "$src" && "$src" != "-" && "$src" != /dev/fd/* ]]; then
    (cd -- "$(dirname -- "$src")" && pwd)
    return
  fi
  return 1
}

render_helper() {
  local output=$1 root src
  root=$(installer_root) || die "Cannot locate installer directory; run from the Vincula release tree (not via stdin-only pipe without bin/vincula)."
  src="${root}/bin/vincula"
  [[ -f "$src" ]] || die "Missing ${src}. Download the full Vincula release directory."
  install -m 0755 "$src" "$output"
}


capture_service_account_identity() {
  local entry
  SERVICE_UID=""
  SERVICE_GID=""
  SERVICE_HOME=""
  SERVICE_SHELL=""
  entry=$(getent passwd "$SERVICE_USER") || return 1
  SERVICE_UID=$(cut -d: -f3 <<< "$entry")
  SERVICE_GID=$(cut -d: -f4 <<< "$entry")
  SERVICE_HOME=$(cut -d: -f6 <<< "$entry")
  SERVICE_SHELL=$(cut -d: -f7 <<< "$entry")
}

create_service_account() {
  local entry uid shell
  SERVICE_USER_CREATED=0
  SERVICE_GROUP_CREATED=0
  if entry=$(getent passwd "$SERVICE_USER"); then
    uid=$(cut -d: -f3 <<< "$entry")
    shell=$(cut -d: -f7 <<< "$entry")
    (( uid > 0 && uid < 1000 )) || die "Existing ${SERVICE_USER} account is not a system account."
    case "$shell" in
      */nologin|*/false) ;;
      *) die "Existing ${SERVICE_USER} account has an interactive shell; refusing to use it." ;;
    esac
    getent group "$SERVICE_GROUP" >/dev/null || die "Existing ${SERVICE_USER} account has no matching ${SERVICE_GROUP} group."
    capture_service_account_identity
    return
  fi

  if getent group "$SERVICE_GROUP" >/dev/null; then
    useradd --system --gid "$SERVICE_GROUP" --home-dir "$VAR_LIB_SING_BOX" --no-create-home \
      --shell /usr/sbin/nologin "$SERVICE_USER"
    SERVICE_USER_CREATED=1
  else
    useradd --system --user-group --home-dir "$VAR_LIB_SING_BOX" --no-create-home \
      --shell /usr/sbin/nologin "$SERVICE_USER"
    SERVICE_USER_CREATED=1
    SERVICE_GROUP_CREATED=1
  fi
  capture_service_account_identity
}

atomic_install() {
  local source=$1 destination=$2 mode=$3 owner=$4 group=$5
  local staged
  staged=$(mktemp "${destination}.new.XXXXXXXX")
  if ! install -o "$owner" -g "$group" -m "$mode" "$source" "$staged"; then
    rm -f -- "$staged"
    return 1
  fi
  if ! mv -f -- "$staged" "$destination"; then
    rm -f -- "$staged"
    return 1
  fi
}

preflight_clean_install() {
  local path
  for path in \
    "$BINARY_PATH" \
    "$HELPER_PATH" \
    "$HELPER_ALIAS_PATH" \
    "$SYSTEMD_UNIT" \
    "$ACCOUNTD_UNIT" \
    "$CONFIG_FILE" \
    "$VERSION_FILE" \
    "$STATE_FILE" \
    "$USERS_FILE" \
    "$SETTINGS_FILE" \
    "$URI_FILE" \
    "$BINARY_CHECKSUM_FILE" \
    "$INSTALL_MANIFEST_FILE" \
    "$MANIFEST_FILE" \
    "$ACCOUNTD_PY" \
    "$STATS_PY" \
    "$EVENT_SCHEMA_FILE" \
    "$VAR_LIB_VINCULA" \
    "$ACCOUNTING_DB_FILE" \
    "$EVENTS_JSONL_FILE"; do
    [[ ! -e "$path" && ! -L "$path" ]] || die "Existing path detected: ${path}. vincula will not overwrite a non-managed installation.
Fresh install refuses leftover accounting files.
If you intend a clean install, as root:
  rm -f ${ACCOUNTING_DB_FILE} ${ACCOUNTING_DB_FILE}-wal ${ACCOUNTING_DB_FILE}-shm ${EVENTS_JSONL_FILE}
  rmdir ${VAR_LIB_VINCULA}"
  done
  if systemctl cat sing-box.service >/dev/null 2>&1; then
    die "An existing sing-box.service was found. vincula will not replace it."
  fi
  if systemctl cat vincula-accountd.service >/dev/null 2>&1; then
    die "An existing vincula-accountd.service was found. vincula will not replace it."
  fi
}

require_canonical_files() {
  local path
  for path in "$STATE_FILE" "$USERS_FILE" "$SETTINGS_FILE" "$URI_FILE" "$BINARY_CHECKSUM_FILE" "$CONFIG_FILE" "$BINARY_PATH" "$SYSTEMD_UNIT"; do
    [[ -e "$path" ]] || die "Existing vincula installation is incomplete: missing ${path}."
  done
}

backup_existing_install() {
  local installed_version=$1 name path
  local sing_enabled=0 sing_active=0 acct_enabled=0 acct_active=0
  MIGRATION_BACKUP="${BACKUP_ROOT}/${installed_version}-$(date -u +'%Y%m%dT%H%M%SZ')"
  install -d -o root -g root -m 0700 "$BACKUP_ROOT"
  install -d -o root -g root -m 0700 "$MIGRATION_BACKUP"

  if systemctl is-enabled --quiet sing-box.service 2>/dev/null; then sing_enabled=1; fi
  if systemctl is-active --quiet sing-box.service 2>/dev/null; then sing_active=1; fi
  if systemctl is-enabled --quiet vincula-accountd.service 2>/dev/null; then acct_enabled=1; fi
  if systemctl is-active --quiet vincula-accountd.service 2>/dev/null; then acct_active=1; fi
  cat > "${MIGRATION_BACKUP}/SERVICE_STATE" <<EOF
sing_enabled=${sing_enabled}
sing_active=${sing_active}
acct_enabled=${acct_enabled}
acct_active=${acct_active}
EOF
  chmod 0600 "${MIGRATION_BACKUP}/SERVICE_STATE"

  for path in \
    "$SYSTEMD_UNIT" \
    "$HELPER_ALIAS_PATH" \
    "$HELPER_PATH" \
    "$CONFIG_FILE" \
    "$VERSION_FILE" \
    "$STATE_FILE" \
    "$USERS_FILE" \
    "$SETTINGS_FILE" \
    "$URI_FILE" \
    "$BINARY_CHECKSUM_FILE" \
    "$INSTALL_MANIFEST_FILE" \
    "$MANIFEST_FILE" \
    "${LIB_DIR}/vincula-common.sh" \
    "$ACCOUNTD_PY" \
    "$STATS_PY" \
    "$EVENT_SCHEMA_FILE" \
    "$ACCOUNTD_UNIT" \
    "$EVENTS_JSONL_FILE"; do
    if [[ -e "$path" || -L "$path" ]]; then
      name=$(basename -- "$path")
      cp -a -- "$path" "${MIGRATION_BACKUP}/${name}"
    fi
  done
  if [[ -f "$ACCOUNTING_DB_FILE" ]]; then
    if command -v sqlite3 >/dev/null 2>&1; then
      sqlite3 "$ACCOUNTING_DB_FILE" ".backup '${MIGRATION_BACKUP}/accounting.db'" \
        || cp -a -- "$ACCOUNTING_DB_FILE" "${MIGRATION_BACKUP}/accounting.db"
    else
      cp -a -- "$ACCOUNTING_DB_FILE" "${MIGRATION_BACKUP}/accounting.db"
    fi
  fi
  if [[ ! -e "$HELPER_PATH" && -x /usr/local/bin/sb ]]; then
    cp -a -- /usr/local/bin/sb "${MIGRATION_BACKUP}/sb"
  fi
  write_backup_marker "$MIGRATION_BACKUP" "$installed_version"
  log_ok "Backup written to ${MIGRATION_BACKUP}"
}

migrate_existing_install() {
  local installed_version=$1
  local uuid private_key public_key short_id server port reality_host arch installed_at users_uuid
  local binary_sha archive_sha uri
  local staged_config staged_state staged_users staged_settings staged_uri staged_manifest staged_install_manifest staged_unit staged_helper staged_version staged_common root
  local created_user created_group clash_secret clash_port
  local original_host host_changed=0
  local node_id node_name
  local legacy_inbound_config=0
  local check_err

  log_info "Installed: ${installed_version}"
  log_info "Installer: ${VINCULA_VERSION}"
  require_canonical_files

  # Stop accounting plane before backup so SQLite is quiescent.
  if systemctl cat vincula-accountd.service >/dev/null 2>&1; then
    systemctl stop vincula-accountd.service >/dev/null 2>&1 || true
  fi

  # Credential UUID SoT is users.json (registry); fall back to line-oriented scan / state.
  uuid=$(owner_active_uuid_from_registry "$USERS_FILE" 2>/dev/null || true)
  [[ -n "$uuid" ]] || uuid=$(json_quoted_field "$USERS_FILE" uuid)
  [[ -n "$uuid" ]] || uuid=$(json_quoted_field "$STATE_FILE" uuid)
  private_key=$(json_quoted_field "$STATE_FILE" reality_private_key)
  public_key=$(json_quoted_field "$STATE_FILE" reality_public_key)
  short_id=$(json_quoted_field "$STATE_FILE" reality_short_id)
  installed_at=$(json_quoted_field "$STATE_FILE" installed_at)
  server=$(toml_get "$SETTINGS_FILE" server)
  port=$(toml_get "$SETTINGS_FILE" port)
  reality_host=$(toml_get "$SETTINGS_FILE" reality_server_name)
  arch=$(toml_get "$SETTINGS_FILE" architecture)
  users_uuid=$(owner_active_uuid_from_registry "$USERS_FILE" 2>/dev/null || true)
  [[ -n "$users_uuid" ]] || users_uuid=$(json_quoted_field "$USERS_FILE" uuid)
  node_id=$(toml_get "$SETTINGS_FILE" node_id || true)
  [[ -n "$node_id" ]] || node_id=$(json_quoted_field "$STATE_FILE" node_id || true)
  node_name=$(toml_get "$SETTINGS_FILE" node_name || true)
  [[ -n "$node_name" ]] || node_name=$(json_quoted_field "$STATE_FILE" node_name || true)
  [[ -n "$node_name" ]] || node_name=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo node)
  if [[ -z "$node_id" || "$node_id" == "local" ]]; then
    node_id=$(generate_uuid_v4)
    log_info "Assigned permanent node_id ${node_id}"
  fi

  [[ -n "$server" ]] || server=$(json_quoted_field "$STATE_FILE" server)
  [[ -n "$port" ]] || port=$(json_numeric_field "$STATE_FILE" port)
  [[ -n "$reality_host" ]] || reality_host=$(json_quoted_field "$STATE_FILE" reality_server_name)
  [[ -n "$arch" ]] || arch=$(json_quoted_field "$STATE_FILE" architecture)
  [[ -n "$installed_at" ]] || installed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

  [[ "$uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "Canonical owner UUID is invalid."
  [[ "$private_key" =~ ^[A-Za-z0-9_-]{43,44}$ ]] || die "Canonical REALITY private key is invalid."
  [[ "$public_key" =~ ^[A-Za-z0-9_-]{43,44}$ ]] || die "Canonical REALITY public key is invalid."
  [[ "$short_id" =~ ^[0-9a-f]{16}$ ]] || die "Canonical REALITY short ID is invalid."
  validate_port "$port" || die "Canonical port is invalid."
  [[ -n "$server" ]] || die "Canonical server address is missing."
  is_dns_name "$reality_host" || die "Canonical REALITY host is invalid."
  [[ "$users_uuid" == "$uuid" ]] || die "users.json UUID does not match canonical owner UUID; refusing to migrate."

  original_host=$reality_host
  if ! reality_host=$(resolve_migration_reality_host "$original_host"); then
    die "Installed REALITY target ${original_host} is known-bad.

Re-run:
VCL_REALITY_HOST=${DEFAULT_REALITY_HOST} ./vincula.sh"
  fi
  if [[ "$reality_host" != "$original_host" ]]; then
    host_changed=1
    log_info "REALITY target ${original_host} → ${reality_host} (UUID and REALITY keys preserved)"
    preflight_reality_target "$reality_host"
  fi

  sha256sum --check --status "$BINARY_CHECKSUM_FILE" || die "Installed sing-box binary failed its stored SHA-256 check."
  local installed_sing_box_version
  installed_sing_box_version=$("$BINARY_PATH" version | awk 'NR==1 {print $3}')
  [[ "$installed_sing_box_version" == "$SING_BOX_VERSION" ]] || die "Installed sing-box version ${installed_sing_box_version:-unknown} differs from the pinned version ${SING_BOX_VERSION}."

  # sing-box 1.13 removed inbound sniff/domain_strategy. A 0.2.3-era config may fail check
  # and refuse to stay healthy; migration regenerates config from SoT, so allow continue.
  check_err=$(mktemp /tmp/vincula-check.XXXXXX)
  if ! "$BINARY_PATH" check -c "$CONFIG_FILE" >"$check_err" 2>&1; then
    if grep -qiE 'legacy inbound|removed in sing-box 1\.13|deprecated in sing-box 1\.11' "$check_err"; then
      legacy_inbound_config=1
      log_warn "Existing config uses legacy inbound fields removed in sing-box 1.13; migration will regenerate config from canonical state."
    else
      cat "$check_err" >&2 || true
      rm -f -- "$check_err"
      die "Existing configuration failed sing-box check."
    fi
  fi
  rm -f -- "$check_err"

  systemctl enable sing-box.service >/dev/null
  if (( legacy_inbound_config == 1 )); then
    systemctl stop sing-box.service >/dev/null 2>&1 || true
    log_warn "Skipping pre-migration service health wait (legacy config cannot run on sing-box ${SING_BOX_VERSION})."
  else
    if ! systemctl is-active --quiet sing-box.service; then
      systemctl start sing-box.service
    fi
    wait_for_service "$port" || die "Existing installation did not become healthy. Run 'journalctl -u sing-box.service'."
  fi
  log_ok "Existing vincula ${installed_version} installation verified; identity preserved"

  created_user=$(json_bool_field "$STATE_FILE" created_by_vincula)
  created_group=$(json_bool_field "$STATE_FILE" group_created_by_vincula)
  [[ "$created_user" == true ]] || created_user=false
  [[ "$created_group" == true ]] || created_group=false
  if capture_service_account_identity; then
    :
  else
    SERVICE_UID=0
    SERVICE_GID=0
    SERVICE_HOME=/var/lib/sing-box
    SERVICE_SHELL=/usr/sbin/nologin
  fi

  backup_existing_install "$installed_version"
  TMP_DIR=$(mktemp -d /tmp/vincula.XXXXXXXX)
  MIGRATION_STARTED=1

  staged_config="${TMP_DIR}/config.json"
  staged_state="${TMP_DIR}/state.json"
  staged_users="${TMP_DIR}/users.json"
  staged_settings="${TMP_DIR}/config.toml"
  staged_uri="${TMP_DIR}/owner.uri"
  staged_manifest="${TMP_DIR}/sing-box.lock"
  staged_install_manifest="${TMP_DIR}/install.manifest"
  staged_unit="${TMP_DIR}/sing-box.service"
  staged_helper="${TMP_DIR}/vincula"
  staged_version="${TMP_DIR}/VERSION"
  staged_common="${TMP_DIR}/vincula-common.sh"

  migrate_users_to_schema2 "$USERS_FILE" "$staged_users" "$node_id"
  [[ "$(owner_active_uuid_from_registry "$staged_users")" == "$uuid" ]] \
    || die "Migration attempted to change the owner UUID in users.json."

  uri=$(render_vless_uri "$uuid" "$server" "$port" "$reality_host" "$public_key" "$short_id" owner)
  binary_sha=$(sha256sum "$BINARY_PATH" | awk '{print $1}')
  archive_sha=$(expected_archive_sha256 "$arch")
  clash_secret=$(toml_get "$SETTINGS_FILE" clash_api_secret || true)
  clash_port=$(toml_get "$SETTINGS_FILE" clash_api_port || true)
  [[ -n "$clash_port" ]] || clash_port=$DEFAULT_CLASH_API_PORT
  validate_port "$clash_port" || die "Stored clash_api_port is invalid."
  [[ -n "$clash_secret" ]] || clash_secret=$(generate_clash_api_secret)
  cycle_start=$(toml_get "$SETTINGS_FILE" billing_cycle_start_day || true)
  [[ -n "$cycle_start" ]] || cycle_start=1
  render_sing_box_config_from_registry "$staged_config" "$staged_users" "$private_key" "$short_id" \
    "$port" "$reality_host" "$DEFAULT_LISTEN" "$clash_port" "$clash_secret" true
  render_state "$staged_state" "$server" "$port" "$reality_host" "$uuid" "$private_key" "$public_key" "$short_id" "$installed_at" "$arch" "$created_user" "$created_group" "${SERVICE_UID:-0}" "${SERVICE_GID:-0}" "${SERVICE_HOME:-/var/lib/sing-box}" "${SERVICE_SHELL:-/usr/sbin/nologin}" "$node_id" "$node_name"
  raw_days=$(toml_get "$SETTINGS_FILE" accounting_raw_retention_days || true)
  [[ -n "$raw_days" ]] || raw_days=90
  daily_days=$(toml_get "$SETTINGS_FILE" accounting_daily_retention_days || true)
  [[ -n "$daily_days" ]] || daily_days=90
  daily_days=$(migrate_legacy_daily_retention "$installed_version" "$daily_days")
  render_settings "$staged_settings" "$server" "$port" "$reality_host" "$arch" \
    "$clash_port" "$clash_secret" "$raw_days" "$daily_days" "$node_id" "$node_name" "$cycle_start"
  printf '%s\n' "$uri" > "$staged_uri"
  printf '%s\n' "$VINCULA_VERSION" > "$staged_version"
  render_manifest "$staged_manifest" "$arch" "$archive_sha" "$binary_sha"
  render_install_manifest "$staged_install_manifest"
  render_systemd_unit "$staged_unit"
  render_helper "$staged_helper"
  root=$(installer_root) || die "Cannot locate installer directory for vincula-common.sh."
  install -m 0644 "${root}/lib/vincula-common.sh" "$staged_common"


  [[ "$(owner_active_uuid_from_registry "$staged_users")" == "$uuid" ]] \
    || die "Migration attempted to change the UUID."
  [[ "$(json_quoted_field "$staged_state" reality_private_key)" == "$private_key" ]] || die "Migration attempted to change the REALITY private key."
  [[ "$(json_quoted_field "$staged_state" reality_public_key)" == "$public_key" ]] || die "Migration attempted to change the REALITY public key."
  [[ "$(json_quoted_field "$staged_state" reality_short_id)" == "$short_id" ]] || die "Migration attempted to change the REALITY short ID."

  "$BINARY_PATH" check -c "$staged_config" >/dev/null
  log_ok "Candidate configuration passed sing-box check"
  verify_identity_consistency "$staged_state" "$staged_settings" "$staged_config" "$staged_uri" "$staged_users" >/dev/null \
    || die "Generated artifacts are inconsistent with canonical state."

  if (( host_changed == 1 )); then
    run_reality_self_test "$BINARY_PATH" "$uuid" "$private_key" "$public_key" "$short_id" "$reality_host" \
      || die "REALITY end-to-end self-test failed for replacement target ${reality_host}."
    log_ok "REALITY end-to-end self-test passed for ${reality_host}"
  fi

  install -d -o root -g root -m 0755 "$LIB_DIR"
  atomic_install "$staged_config" "$CONFIG_FILE" 0640 root "$SERVICE_GROUP"
  atomic_install "$staged_state" "$STATE_FILE" 0600 root root
  atomic_install "$staged_users" "$USERS_FILE" 0600 root root
  atomic_install "$staged_settings" "$SETTINGS_FILE" 0600 root root
  atomic_install "$staged_uri" "$URI_FILE" 0600 root root
  atomic_install "$staged_version" "$VERSION_FILE" 0600 root root
  atomic_install "$staged_manifest" "$MANIFEST_FILE" 0644 root root
  atomic_install "$staged_install_manifest" "$INSTALL_MANIFEST_FILE" 0644 root root
  atomic_install "$staged_common" "${LIB_DIR}/vincula-common.sh" 0644 root root
  atomic_install "$staged_helper" "$HELPER_PATH" 0755 root root
  ln -sfn "$HELPER_PATH" "$HELPER_ALIAS_PATH"
  atomic_install "$staged_unit" "$SYSTEMD_UNIT" 0644 root root

  if [[ -x /usr/local/bin/sb && /usr/local/bin/sb -ef "$HELPER_PATH" ]]; then
    true
  elif [[ -f /usr/local/bin/sb ]] && grep -q 'vincula\|sb-mini' /usr/local/bin/sb; then
    rm -f -- /usr/local/bin/sb
  fi

  systemctl daemon-reload
  systemctl restart sing-box.service
  wait_for_service "$port" || die "sing-box did not become healthy after migration."
  install_accountd_artifacts
  validate_accounting_artifacts
  enable_accountd_service

  INSTALL_COMMITTED=1
  log_ok "Migrated vincula ${installed_version} → ${VINCULA_VERSION}"
  print_local_success "$port"
  printf '\nUser: owner\nNode:\n'
  cat "$URI_FILE"
  printf '\nNext checks:\n  vcl verify\n  vcl diagnose\n  vcl connections\n  vcl stats today\n  vcl link\n'
}

verify_existing_install() {
  local installed_project_version installed_sing_box_version port clash_port clash_secret
  local fail=0 schema

  installed_project_version=$(< "$VERSION_FILE")
  installed_project_version=${installed_project_version//$'\r'/}
  installed_project_version=${installed_project_version//$'\n'/}

  require_canonical_files
  [[ -e "$HELPER_PATH" ]] || die "Existing vincula installation is incomplete: missing ${HELPER_PATH}."

  printf '[Proxy Plane]\n'
  if sha256sum --check --status "$BINARY_CHECKSUM_FILE"; then
    log_ok "sing-box binary"
  else
    log_warn "sing-box binary"
    fail=1
  fi
  installed_sing_box_version=$("$BINARY_PATH" version | awk 'NR==1 {print $3}')
  if [[ "$installed_sing_box_version" == "$SING_BOX_VERSION" ]] && "$BINARY_PATH" check -c "$CONFIG_FILE" >/dev/null; then
    log_ok "config"
  else
    log_warn "config"
    fail=1
  fi

  port=$(toml_get "$SETTINGS_FILE" port)
  validate_port "$port" || die "Stored port is invalid."
  systemctl enable sing-box.service >/dev/null
  if ! systemctl is-active --quiet sing-box.service; then
    systemctl start sing-box.service
  fi
  if wait_for_service "$port"; then
    log_ok "service"
    log_ok "listener"
  else
    log_warn "service"
    log_warn "listener"
    fail=1
  fi

  printf '\n[Accounting Plane]\n'
  if [[ -f "$ACCOUNTD_PY" && -f "$EVENT_SCHEMA_FILE" && -f "$STATS_PY" ]]; then
    log_ok "accountd artifact"
  else
    log_warn "accountd artifact"
    fail=1
  fi
  if unit_has_vincula_marker "$ACCOUNTD_UNIT"; then
    log_ok "accountd unit"
  else
    log_warn "accountd unit"
    fail=1
  fi
  systemctl enable vincula-accountd.service >/dev/null 2>&1 || true
  if ! systemctl is-active --quiet vincula-accountd.service; then
    systemctl start vincula-accountd.service >/dev/null 2>&1 || true
  fi
  if systemctl is-active --quiet vincula-accountd.service; then
    log_ok "accountd service active"
  else
    log_warn "accountd service active"
    fail=1
  fi

  clash_port=$(toml_get "$SETTINGS_FILE" clash_api_port || true)
  [[ -n "$clash_port" ]] || clash_port=$DEFAULT_CLASH_API_PORT
  clash_secret=$(toml_get "$SETTINGS_FILE" clash_api_secret || true)
  if validate_port "$clash_port" && clash_api_reachable_with_secret "$clash_port" "$clash_secret"; then
    log_ok "Clash API reachable"
    log_ok "Clash API authentication"
  else
    log_warn "Clash API reachable"
    log_warn "Clash API authentication"
    fail=1
  fi

  if [[ -r "$ACCOUNTING_DB_FILE" ]]; then
    log_ok "SQLite database readable"
    schema=$(python3 - "$ACCOUNTING_DB_FILE" <<'PY' 2>/dev/null || true
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
print(row[0] if row else "")
conn.close()
PY
)
    if [[ "$schema" == "2" ]]; then
      log_ok "expected DB schema"
    else
      log_warn "expected DB schema"
      fail=1
    fi
    wait_for_accountd_healthy || true
    # Do not treat Clash/schema health as collector freshness; require last_success_at.
    if accounting_last_success_fresh_wait "$ACCOUNTING_DB_FILE"; then
      log_ok "collector recently successful"
    else
      log_warn "collector recently successful"
      fail=1
    fi
  else
    log_warn "SQLite database readable"
    fail=1
  fi

  (( fail == 0 )) || die "Existing vincula ${installed_project_version} installation failed dual-plane verification."

  log_ok "Existing vincula ${VINCULA_VERSION} installation verified; credentials preserved"
  print_local_success "$port"
  printf '\nUser: owner\nNode:\n'
  cat "$URI_FILE"
}

handle_existing_install() {
  local installed_project_version
  installed_project_version=$(< "$VERSION_FILE")
  installed_project_version=${installed_project_version//$'\r'/}
  installed_project_version=${installed_project_version//$'\n'/}

  if [[ "$installed_project_version" == "$VINCULA_VERSION" ]]; then
    verify_existing_install
    return
  fi
  if is_supported_upgrade_from "$installed_project_version"; then
    migrate_existing_install "$installed_project_version"
    return
  fi
  die "Installed vincula version is ${installed_project_version}; this installer can migrate 0.1.0–0.1.5 and 0.2.0–0.2.6 to ${VINCULA_VERSION}, but will not downgrade or skip versions."
}

wait_for_service() {
  local port=$1 remaining
  for (( remaining = 0; remaining < 15; remaining++ )); do
    if systemctl is-active --quiet sing-box.service && port_is_listening "$port" && port_owned_by_sing_box "$port"; then
      return 0
    fi
    sleep 1
  done
  journalctl -u sing-box.service -n 30 --no-pager >&2 || true
  return 1
}


install_accountd_artifacts() {
  local root staged_unit staged_py staged_stats staged_schema
  root=$(installer_root) || die "Cannot locate installer directory for accounting artifacts."
  staged_py="${TMP_DIR}/vincula-accountd.py"
  staged_stats="${TMP_DIR}/vincula-stats.py"
  staged_unit="${TMP_DIR}/vincula-accountd.service"
  staged_schema="${TMP_DIR}/vincula-event.schema.json"
  [[ -f "${root}/lib/vincula-accountd.py" ]] || die "Missing ${root}/lib/vincula-accountd.py"
  [[ -f "${root}/lib/vincula-stats.py" ]] || die "Missing ${root}/lib/vincula-stats.py"
  [[ -f "${root}/lib/vincula-accountd.service" ]] || die "Missing ${root}/lib/vincula-accountd.service"
  [[ -f "${root}/lib/vincula-event.schema.json" ]] || die "Missing ${root}/lib/vincula-event.schema.json"
  install -m 0644 "${root}/lib/vincula-accountd.py" "$staged_py"
  install -m 0644 "${root}/lib/vincula-stats.py" "$staged_stats"
  install -m 0644 "${root}/lib/vincula-accountd.service" "$staged_unit"
  install -m 0644 "${root}/lib/vincula-event.schema.json" "$staged_schema"
  install -d -o root -g root -m 0700 "$VAR_LIB_VINCULA"
  atomic_install "$staged_py" "$ACCOUNTD_PY" 0644 root root
  atomic_install "$staged_stats" "$STATS_PY" 0644 root root
  atomic_install "$staged_schema" "$EVENT_SCHEMA_FILE" 0644 root root
  atomic_install "$staged_unit" "$ACCOUNTD_UNIT" 0644 root root
  # Create empty DB file ownership marker (daemon initializes schema).
  if [[ ! -f "$ACCOUNTING_DB_FILE" ]]; then
    : > "$ACCOUNTING_DB_FILE"
    chmod 0600 "$ACCOUNTING_DB_FILE"
  fi
}

validate_accounting_artifacts() {
  [[ -f "$ACCOUNTD_PY" ]] || die "Missing accounting daemon ${ACCOUNTD_PY}"
  [[ -f "$STATS_PY" ]] || die "Missing stats helper ${STATS_PY}"
  [[ -f "$EVENT_SCHEMA_FILE" ]] || die "Missing event schema ${EVENT_SCHEMA_FILE}"
  [[ -f "$ACCOUNTD_UNIT" ]] || die "Missing accounting unit ${ACCOUNTD_UNIT}"
  python3 -m py_compile "$ACCOUNTD_PY" || die "vincula-accountd.py failed py_compile"
  python3 -m py_compile "$STATS_PY" || die "vincula-stats.py failed py_compile"
  python3 -m json.tool "$EVENT_SCHEMA_FILE" >/dev/null || die "vincula-event.schema.json is not valid JSON"
  if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "$ACCOUNTD_UNIT" || die "vincula-accountd.service failed systemd-analyze verify"
  fi
}

localhost_port_free_or_ours() {
  local port=$1
  validate_port "$port" || return 1
  if ! ss -H -ltn "sport = :${port}" 2>/dev/null | grep -q .; then
    return 0
  fi
  # Allow if sing-box already owns it (re-install / migrate paths).
  if command -v port_owned_by_sing_box >/dev/null 2>&1 && port_owned_by_sing_box "$port"; then
    return 0
  fi
  # ss users:("sing-box"...
  ss -H -ltnp "sport = :${port}" 2>/dev/null | grep -q 'sing-box' && return 0
  return 1
}

wait_for_accountd_healthy() {
  local remaining port secret schema
  for (( remaining = 0; remaining < 15; remaining++ )); do
    if systemctl is-active --quiet vincula-accountd.service; then
      break
    fi
    sleep 1
  done
  systemctl is-active --quiet vincula-accountd.service || return 1

  [[ -r "$ACCOUNTING_DB_FILE" ]] || return 1
  schema=""
  for (( remaining = 0; remaining < 15; remaining++ )); do
    schema=$(python3 - "$ACCOUNTING_DB_FILE" <<'PY' 2>/dev/null || true
import sqlite3, sys
try:
    conn = sqlite3.connect(sys.argv[1])
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    print(row[0] if row else "")
    conn.close()
except Exception:
    pass
PY
)
    [[ "$schema" == "2" ]] && break
    sleep 1
  done
  [[ "$schema" == "2" ]] || return 1

  port=$(toml_get "$SETTINGS_FILE" clash_api_port || true)
  [[ -n "$port" ]] || port=$DEFAULT_CLASH_API_PORT
  secret=$(toml_get "$SETTINGS_FILE" clash_api_secret || true)
  validate_port "$port" || return 1
  for (( remaining = 0; remaining < 15; remaining++ )); do
    if clash_api_reachable_with_secret "$port" "$secret"; then
      # Secret must be required: bare / wrong Bearer must fail when secret is set.
      if [[ -n "$secret" ]]; then
        clash_api_reachable_with_secret "$port" "" && return 1
        clash_api_reachable_with_secret "$port" "wrong-${secret}" && return 1
      fi
      return 0
    fi
    sleep 1
  done
  return 1
}

enable_accountd_service() {
  systemctl daemon-reload
  systemctl enable --now vincula-accountd.service || die "vincula-accountd.service failed to enable/start"
  wait_for_accountd_healthy || die "vincula-accountd health check failed; refusing to commit install"
}

install_new_node() {
  local os_arch arch port reality_host server binary key_output private_key public_key uuid short_id
  local installed_at uri binary_sha archive_sha
  local staged_config staged_state staged_users staged_settings staged_uri staged_checksum staged_manifest staged_install_manifest staged_unit staged_helper staged_version staged_common root
  local created_user created_group clash_secret
  local node_id node_name clash_port

  os_arch=$(uname -m)
  arch=$(map_arch "$os_arch") || die "Unsupported architecture: ${os_arch}. Only amd64 and arm64 are supported."
  port=${VCL_PORT:-443}
  validate_port "$port" || die "VCL_PORT must be an integer between 1 and 65535."
  reality_host=$(select_reality_host)
  clash_port=$DEFAULT_CLASH_API_PORT
  validate_port "$clash_port" || die "clash_api_port is invalid."

  preflight_clean_install
  if port_is_listening "$port"; then
    die "TCP port ${port} is already in use. Choose another port with VCL_PORT=<port>."
  fi
  localhost_port_free_or_ours "$clash_port" \
    || die "Clash API port ${clash_port} is already in use on localhost."
  server=$(detect_public_server)
  log_ok "Environment supported (${OS_ID} ${OS_VERSION}, ${arch})"
  log_ok "Client address resolved as ${server}"
  preflight_reality_target "$reality_host"

  TMP_DIR=$(mktemp -d /tmp/vincula.XXXXXXXX)
  binary=$(download_sing_box "$arch" "$TMP_DIR")

  key_output=$("$binary" generate reality-keypair)
  private_key=$(parse_private_key "$key_output")
  public_key=$(parse_public_key "$key_output")
  uuid=$("$binary" generate uuid)
  short_id=$("$binary" generate rand --hex 8)
  node_id=$("$binary" generate uuid)
  node_name=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo node)

  [[ "$private_key" =~ ^[A-Za-z0-9_-]{43,44}$ ]] || die "Could not parse the generated REALITY private key."
  [[ "$public_key" =~ ^[A-Za-z0-9_-]{43,44}$ ]] || die "Could not parse the generated REALITY public key."
  [[ "$uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "Could not validate the generated UUID."
  [[ "$node_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "Could not validate the generated node_id."
  [[ "$short_id" =~ ^[0-9a-f]{16}$ ]] || die "Could not validate the generated REALITY short ID."

  run_reality_self_test "$binary" "$uuid" "$private_key" "$public_key" "$short_id" "$reality_host" \
    || die "REALITY end-to-end self-test failed for ${reality_host}. Choose another target with VCL_REALITY_HOST."
  log_ok "REALITY end-to-end self-test passed"

  installed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
  uri=$(render_vless_uri "$uuid" "$server" "$port" "$reality_host" "$public_key" "$short_id")
  binary_sha=$(sha256sum "$binary" | awk '{print $1}')
  archive_sha=$(expected_archive_sha256 "$arch")

  staged_config="${TMP_DIR}/config.json"
  staged_state="${TMP_DIR}/state.json"
  staged_users="${TMP_DIR}/users.json"
  staged_settings="${TMP_DIR}/config.toml"
  staged_uri="${TMP_DIR}/owner.uri"
  staged_checksum="${TMP_DIR}/sing-box.binary.sha256"
  staged_manifest="${TMP_DIR}/sing-box.lock"
  staged_install_manifest="${TMP_DIR}/install.manifest"
  staged_unit="${TMP_DIR}/sing-box.service"
  staged_helper="${TMP_DIR}/vincula"
  staged_version="${TMP_DIR}/VERSION"

  render_users "$staged_users" "$uuid" "$installed_at" "" "" "$node_id"
  clash_secret=$(generate_clash_api_secret)
  render_sing_box_config_from_registry "$staged_config" "$staged_users" "$private_key" "$short_id" \
    "$port" "$reality_host" "$DEFAULT_LISTEN" "$clash_port" "$clash_secret" true
  render_settings "$staged_settings" "$server" "$port" "$reality_host" "$arch" \
    "$clash_port" "$clash_secret" 90 90 "$node_id" "$node_name"
  printf '%s\n' "$uri" > "$staged_uri"
  printf '%s  %s\n' "$binary_sha" "$BINARY_PATH" > "$staged_checksum"
  printf '%s\n' "$VINCULA_VERSION" > "$staged_version"
  render_manifest "$staged_manifest" "$arch" "$archive_sha" "$binary_sha"
  render_install_manifest "$staged_install_manifest"
  render_systemd_unit "$staged_unit"
  render_helper "$staged_helper"
  staged_common="${TMP_DIR}/vincula-common.sh"
  root=$(installer_root) || die "Cannot locate installer directory for vincula-common.sh."
  install -m 0644 "${root}/lib/vincula-common.sh" "$staged_common"


  "$binary" check -c "$staged_config" >/dev/null
  log_ok "Generated configuration passed sing-box check"

  MUTATION_STARTED=1
  create_service_account
  created_user=false
  created_group=false
  if (( SERVICE_USER_CREATED == 1 )); then
    created_user=true
  fi
  if (( SERVICE_GROUP_CREATED == 1 )); then
    created_group=true
  fi
  render_state "$staged_state" "$server" "$port" "$reality_host" "$uuid" "$private_key" "$public_key" "$short_id" "$installed_at" "$arch" "$created_user" "$created_group" "${SERVICE_UID:-0}" "${SERVICE_GID:-0}" "${SERVICE_HOME:-/var/lib/sing-box}" "${SERVICE_SHELL:-/usr/sbin/nologin}" "$node_id" "$node_name"

  install -d -o root -g root -m 0700 "$STATE_DIR"
  install -d -o root -g "$SERVICE_GROUP" -m 0750 "$SING_BOX_DIR"
  install -d -o root -g root -m 0755 "$LIB_DIR"

  atomic_install "$binary" "$BINARY_PATH" 0755 root root
  atomic_install "$staged_config" "$CONFIG_FILE" 0640 root "$SERVICE_GROUP"
  atomic_install "$staged_state" "$STATE_FILE" 0600 root root
  atomic_install "$staged_users" "$USERS_FILE" 0600 root root
  atomic_install "$staged_settings" "$SETTINGS_FILE" 0600 root root
  atomic_install "$staged_uri" "$URI_FILE" 0600 root root
  atomic_install "$staged_checksum" "$BINARY_CHECKSUM_FILE" 0600 root root
  atomic_install "$staged_version" "$VERSION_FILE" 0600 root root
  atomic_install "$staged_manifest" "$MANIFEST_FILE" 0644 root root
  atomic_install "$staged_install_manifest" "$INSTALL_MANIFEST_FILE" 0644 root root
  atomic_install "$staged_common" "${LIB_DIR}/vincula-common.sh" 0644 root root
  atomic_install "$staged_helper" "$HELPER_PATH" 0755 root root
  ln -sfn "$HELPER_PATH" "$HELPER_ALIAS_PATH"
  atomic_install "$staged_unit" "$SYSTEMD_UNIT" 0644 root root

  "$BINARY_PATH" check -c "$CONFIG_FILE" >/dev/null
  sha256sum --check --status "$BINARY_CHECKSUM_FILE" || die "Installed binary checksum verification failed."
  systemctl daemon-reload
  systemctl enable --now sing-box.service >/dev/null
  wait_for_service "$port" || die "sing-box did not become healthy after installation."
  install_accountd_artifacts
  validate_accounting_artifacts
  enable_accountd_service

  INSTALL_COMMITTED=1
  log_ok "sing-box installed and binary integrity recorded"
  print_local_success "$port"
  printf '\nUser: owner\nNode:\n%s\n' "$uri"
  printf '\nNext checks:\n  vcl verify\n  vcl check\n  vcl diagnose\n  vcl connections\n  vcl stats today\n  vcl link\n'
}

main() {
  case "${1:-}" in
    -h|--help) usage; return ;;
    -V|--version) printf 'vincula %s\n' "$VINCULA_VERSION"; return ;;
    "") ;;
    *) die "Unknown argument: $1. Run with --help." ;;
  esac

  [[ -n "${BASH_VERSION:-}" ]] || die "This installer requires bash."
  (( EUID == 0 )) || die "Run this installer as root (for example: sudo bash vincula.sh)."
  read_os_release
  is_supported_os "$OS_ID" "$OS_VERSION" || die "Unsupported platform: ${OS_ID} ${OS_VERSION}. Supported: Debian 12/13 and Ubuntu 22.04/24.04/26.04."
  ensure_dependencies
  check_systemd

  if [[ -f "$VERSION_FILE" ]]; then
    handle_existing_install
  else
    install_new_node
  fi
}

if [[ -z "${BASH_SOURCE[0]-}" ]] || [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  trap 'on_exit $?' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  main "$@"
fi
