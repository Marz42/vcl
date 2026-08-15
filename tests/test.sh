#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "${TEST_DIR}/.." && pwd)
readonly TEST_DIR PROJECT_DIR

# The path is resolved dynamically from this file.
# shellcheck disable=SC1091
source "${PROJECT_DIR}/vincula.sh"

PASS_COUNT=0
FAIL_COUNT=0
TEST_TMP=""

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf 'ok %d - %s\n' "$PASS_COUNT" "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf 'not ok - %s\n' "$1" >&2
}

assert_equal() {
  local description=$1 expected=$2 actual=$3
  if [[ "$actual" == "$expected" ]]; then
    pass "$description"
  else
    fail "${description} (expected '${expected}', got '${actual}')"
  fi
}

assert_success() {
  local description=$1
  shift
  if "$@"; then
    pass "$description"
  else
    fail "$description"
  fi
}

assert_failure() {
  local description=$1
  shift
  if "$@"; then
    fail "${description} (unexpected success)"
  else
    pass "$description"
  fi
}

finish() {
  trap - EXIT
  if [[ -n "${TEST_TMP:-}" && "$TEST_TMP" == /tmp/vincula-tests.* && -d "$TEST_TMP" ]]; then
    rm -rf --one-file-system -- "$TEST_TMP"
  fi
  if (( FAIL_COUNT > 0 )); then
    printf '\n%d test(s) failed; %d passed.\n' "$FAIL_COUNT" "$PASS_COUNT" >&2
    exit 1
  fi
  printf '\nAll %d tests passed.\n' "$PASS_COUNT"
}

trap finish EXIT

assert_equal "maps x86_64 to amd64" "amd64" "$(map_arch x86_64)"
assert_equal "maps aarch64 to arm64" "arm64" "$(map_arch aarch64)"
assert_failure "rejects unsupported architecture" map_arch riscv64

assert_success "supports Debian 12" is_supported_os debian 12
assert_success "supports Debian 13" is_supported_os debian 13
assert_success "supports Ubuntu 26.04" is_supported_os ubuntu 26.04
assert_failure "rejects Ubuntu 20.04" is_supported_os ubuntu 20.04
assert_failure "rejects Alpine" is_supported_os alpine 3.22

assert_success "accepts port 1" validate_port 1
assert_success "accepts port 443" validate_port 443
assert_success "accepts port 65535" validate_port 65535
assert_failure "rejects port 0" validate_port 0
assert_failure "rejects port 65536" validate_port 65536
assert_failure "rejects port with leading zeros" validate_port 0443
assert_failure "rejects non-numeric port" validate_port 443tcp

assert_success "accepts IPv4 server" validate_server 203.0.113.10
assert_success "accepts IPv6 server" validate_server 2001:db8::10
assert_success "accepts DNS server" validate_server node.example.com
assert_failure "rejects bracketed IPv6 input" validate_server '[2001:db8::10]'
assert_failure "rejects malformed IPv4" validate_server 203.0.113.999
assert_failure "rejects overlong IPv6" validate_server 1:2:3:4:5:6:7:8:9
assert_failure "rejects repeated IPv6 compression" validate_server 2001::db8::10
assert_failure "rejects malformed DNS name" validate_server bad_name.example.com

assert_equal "pins amd64 archive digest" \
  "d34d987ed6ae39ca3760269264fb502b867e5477db45518c829b07776245c495" \
  "$(expected_archive_sha256 amd64)"
assert_equal "pins arm64 archive digest" \
  "a894f6152cade4a2c9d062762d54dea0c1aee673ab4759e0829e19cace932719" \
  "$(expected_archive_sha256 arm64)"
assert_equal "builds immutable amd64 release URL" \
  "https://github.com/SagerNet/sing-box/releases/download/v1.13.18/sing-box-1.13.18-linux-amd64.tar.gz" \
  "$(release_asset_url amd64)"
assert_equal "runs when read from standard input" "vincula 0.2.6" \
  "$(bash -s -- --version < "${PROJECT_DIR}/vincula.sh")"
assert_equal "uses vincula state directory" "/etc/vincula" "$STATE_DIR"
assert_equal "uses vincula lib directory" "/usr/local/lib/vincula" "$LIB_DIR"
assert_equal "installs vincula helper" "/usr/local/bin/vincula" "$HELPER_PATH"
assert_equal "installs vcl alias" "/usr/local/bin/vcl" "$HELPER_ALIAS_PATH"
assert_success "flags RFC1918 10/8 as unusable public address" is_private_or_reserved_ipv4 10.8.0.1
assert_success "flags RFC1918 192.168/16 as unusable public address" is_private_or_reserved_ipv4 192.168.1.1
assert_success "flags CGNAT as unusable public address" is_private_or_reserved_ipv4 100.64.0.1
assert_success "flags TEST-NET-3 as reserved" is_private_or_reserved_ipv4 203.0.113.10
assert_failure "does not flag 8.8.8.8 as private" is_private_or_reserved_ipv4 8.8.8.8
assert_success "migrates from 0.1.0" is_supported_upgrade_from 0.1.0
assert_success "migrates from 0.1.4" is_supported_upgrade_from 0.1.4
assert_success "migrates from 0.1.5" is_supported_upgrade_from 0.1.5
assert_success "migrates from 0.2.0" is_supported_upgrade_from 0.2.0
assert_success "migrates from 0.2.1" is_supported_upgrade_from 0.2.1
assert_success "migrates from 0.2.2" is_supported_upgrade_from 0.2.2
assert_success "migrates from 0.2.3" is_supported_upgrade_from 0.2.3
assert_success "migrates from 0.2.4" is_supported_upgrade_from 0.2.4
assert_success "migrates from 0.2.5" is_supported_upgrade_from 0.2.5
assert_failure "does not migrate the current version" is_supported_upgrade_from 0.2.6
assert_failure "does not migrate 0.3.0" is_supported_upgrade_from 0.3.0

assert_success "accepts owner tag" is_valid_user_tag owner
assert_success "accepts alice tag" is_valid_user_tag alice
assert_success "accepts tag with hyphen and underscore" is_valid_user_tag alice_01-x
assert_success "accepts tag with dots" is_valid_user_tag bob.li
assert_failure "rejects empty tag" is_valid_user_tag ""
assert_failure "rejects uppercase tag" is_valid_user_tag Alice
assert_failure "rejects tag starting with hyphen" is_valid_user_tag -alice
assert_failure "rejects overlong tag" is_valid_user_tag a23456789012345678901234567890123

assert_success "flags www.microsoft.com as known-bad for pinned sing-box" \
  is_known_bad_reality_host www.microsoft.com
assert_success "known-bad REALITY host match is case-insensitive" \
  is_known_bad_reality_host WWW.MICROSOFT.COM
assert_failure "does not flag www.cloudflare.com as known-bad" \
  is_known_bad_reality_host www.cloudflare.com
assert_failure "does not flag microsoft.com apex as known-bad" \
  is_known_bad_reality_host microsoft.com
assert_failure "default REALITY host is not on the pinned known-bad list" \
  is_known_bad_reality_host "$DEFAULT_REALITY_HOST"

assert_equal "uses default REALITY host when unset" "$DEFAULT_REALITY_HOST" \
  "$(VCL_REALITY_HOST= select_reality_host)"
assert_equal "respects explicit REALITY host" "www.example.com" \
  "$(VCL_REALITY_HOST=www.example.com select_reality_host)"

microsoft_err=""
if microsoft_err=$(VCL_REALITY_HOST=www.microsoft.com select_reality_host 2>&1); then
  fail "explicit microsoft REALITY host is rejected (unexpected success)"
else
  if [[ "$microsoft_err" == *"www.microsoft.com is known to be incompatible with"* && \
        "$microsoft_err" == *"SagerNet/sing-box#4290"* && \
        "$microsoft_err" != "$DEFAULT_REALITY_HOST" ]]; then
    pass "explicit microsoft REALITY host is rejected without fallback"
  else
    fail "explicit microsoft REALITY host is rejected without fallback (got '${microsoft_err}')"
  fi
fi

assert_success "matches sing-box pid in ss line" \
  ss_line_is_sing_box_pid 'LISTEN 0 4096 *:443 *:* users:(("sing-box",pid=1234,fd=8))' 1234
assert_failure "rejects other process owning the port" \
  ss_line_is_sing_box_pid 'LISTEN 0 4096 *:443 *:* users:(("nginx",pid=1234,fd=8))' 1234
assert_failure "rejects sing-box line with a different pid" \
  ss_line_is_sing_box_pid 'LISTEN 0 4096 *:443 *:* users:(("sing-box",pid=99,fd=8))' 1234

key_output=$'PrivateKey: private-key_value\nPublicKey: public-key_value'
assert_equal "parses REALITY private key" "private-key_value" "$(parse_private_key "$key_output")"
assert_equal "parses REALITY public key" "public-key_value" "$(parse_public_key "$key_output")"

readonly TEST_UUID="11111111-1111-4111-8111-111111111111"
readonly TEST_PRIVATE_KEY="mJxjowf_ACp9m8GGpt702b3Rs6-slRLfRJ0nyPEYP0k"
readonly TEST_PUBLIC_KEY="D5-T68ZKFx7tdcZr3hbik7OQ7qwTQIRGyu5J-9LfHwU"
readonly TEST_SHORT_ID="82fd91f729d69f6e"

assert_equal "renders IPv4 VLESS URI" \
  "vless://${TEST_UUID}@203.0.113.10:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.cloudflare.com&fp=chrome&pbk=${TEST_PUBLIC_KEY}&sid=${TEST_SHORT_ID}&type=tcp#vincula-owner" \
  "$(render_vless_uri "$TEST_UUID" 203.0.113.10 443 www.cloudflare.com "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID")"
assert_equal "brackets IPv6 in VLESS URI" \
  "vless://${TEST_UUID}@[2001:db8::10]:8443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.cloudflare.com&fp=chrome&pbk=${TEST_PUBLIC_KEY}&sid=${TEST_SHORT_ID}&type=tcp#vincula-owner" \
  "$(render_vless_uri "$TEST_UUID" 2001:db8::10 8443 www.cloudflare.com "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID")"

parse_vless_uri "$(render_vless_uri "$TEST_UUID" 203.0.113.10 443 www.cloudflare.com "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID")"
assert_equal "parses VLESS UUID" "$TEST_UUID" "$VLESS_UUID"
assert_equal "parses VLESS host" "203.0.113.10" "$VLESS_HOST"
assert_equal "parses VLESS port" "443" "$VLESS_PORT"
assert_equal "parses VLESS SNI" "www.cloudflare.com" "$VLESS_SNI"
assert_equal "parses VLESS public key" "$TEST_PUBLIC_KEY" "$VLESS_PBK"
assert_equal "parses VLESS short ID" "$TEST_SHORT_ID" "$VLESS_SID"
assert_equal "parses VLESS flow" "xtls-rprx-vision" "$VLESS_FLOW"
parse_vless_uri "$(render_vless_uri "$TEST_UUID" 2001:db8::10 8443 www.cloudflare.com "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID")"
assert_equal "parses bracketed VLESS host" "2001:db8::10" "$VLESS_HOST"
assert_equal "parses bracketed VLESS port" "8443" "$VLESS_PORT"

TEST_TMP=$(mktemp -d /tmp/vincula-tests.XXXXXXXX)
readonly TEST_NODE_ID="6fc96a10-1111-4111-8111-111111111111"
render_sing_box_config "${TEST_TMP}/config.json" "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_SHORT_ID" 443 www.cloudflare.com
render_state "${TEST_TMP}/state.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 false false 0 0 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node
render_users "${TEST_TMP}/users.json" "$TEST_UUID" 2026-08-12T00:00:00Z "" "" "$TEST_NODE_ID"
render_settings "${TEST_TMP}/config.toml" 203.0.113.10 443 www.cloudflare.com amd64 9090 test-secret 90 90 "$TEST_NODE_ID" test-node
printf '%s\n' "$(render_vless_uri "$TEST_UUID" 203.0.113.10 443 www.cloudflare.com "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID")" > "${TEST_TMP}/owner.uri"
render_systemd_unit "${TEST_TMP}/sing-box.service"
render_helper "${TEST_TMP}/vincula"
render_self_test_server_config "${TEST_TMP}/selftest-server.json" "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_SHORT_ID" 23456 www.cloudflare.com
render_self_test_client_config "${TEST_TMP}/selftest-client.json" "$TEST_UUID" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 23456 23457 www.cloudflare.com

if command -v python3 >/dev/null 2>&1; then
  assert_success "renders valid config JSON" python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${TEST_TMP}/config.json"
  assert_success "renders valid state JSON" python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${TEST_TMP}/state.json"
  assert_success "renders valid users JSON" python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${TEST_TMP}/users.json"
  assert_equal "users.json schema_version is 2" "2" "$(json_numeric_field "${TEST_TMP}/users.json" schema_version)"
  assert_success "users.json has owner tag" grep -q '"tag": "owner"' "${TEST_TMP}/users.json"
  assert_success "users.json has user_id" grep -q '"user_id"' "${TEST_TMP}/users.json"
  assert_success "users.json has credential_id" grep -q '"credential_id"' "${TEST_TMP}/users.json"
  assert_success "users.json has node_id UUID" grep -q "\"node_id\": \"${TEST_NODE_ID}\"" "${TEST_TMP}/users.json"
  assert_failure "users.json does not hardcode local node_id" grep -q '"node_id": "local"' "${TEST_TMP}/users.json"
  assert_success "renders valid self-test server JSON" python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${TEST_TMP}/selftest-server.json"
  assert_success "renders valid self-test client JSON" python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${TEST_TMP}/selftest-client.json"
fi
assert_equal "extracts owner uuid from users registry" "$TEST_UUID" "$(json_quoted_field "${TEST_TMP}/users.json" uuid)"
assert_equal "state includes node_id UUID" "$TEST_NODE_ID" "$(json_quoted_field "${TEST_TMP}/state.json" node_id)"
assert_failure "state does not keep owner.uuid as SoT" grep -q '"owner"' "${TEST_TMP}/state.json"
assert_success "settings include node_id UUID" grep -q "^node_id = \"${TEST_NODE_ID}\"\$" "${TEST_TMP}/config.toml"
assert_failure "settings do not hardcode local node_id" grep -q '^node_id = "local"$' "${TEST_TMP}/config.toml"
assert_success "self-test server binds localhost only" grep -q '"listen": "127.0.0.1"' "${TEST_TMP}/selftest-server.json"
assert_success "self-test client exposes localhost SOCKS" grep -q '"type": "socks"' "${TEST_TMP}/selftest-client.json"
assert_success "renders syntactically valid helper" bash -n "${TEST_TMP}/vincula"
assert_success "renders expected service user" grep -q '^User=sing-box$' "${TEST_TMP}/sing-box.service"
assert_success "renders low-port capability" grep -q '^AmbientCapabilities=CAP_NET_BIND_SERVICE$' "${TEST_TMP}/sing-box.service"
assert_success "keeps management state private by design" grep -q '^project_version = "0.2.6"$' "${TEST_TMP}/config.toml"
assert_success "render_settings snapshot has daily retention 90" \
  grep -q '^accounting_daily_retention_days = 90$' "${TEST_TMP}/config.toml"
render_settings "${TEST_TMP}/settings-ret-default.toml" 203.0.113.10 443 www.cloudflare.com amd64 9090 test-secret
assert_success "render_settings default daily retention is 90" \
  grep -q '^accounting_daily_retention_days = 90$' "${TEST_TMP}/settings-ret-default.toml"
assert_success "render_settings default raw retention is 90" \
  grep -q '^accounting_raw_retention_days = 90$' "${TEST_TMP}/settings-ret-default.toml"
assert_equal "reads canonical port from state" "443" "$(json_numeric_field "${TEST_TMP}/state.json" port)"
assert_success "generated artifacts match canonical state" \
  verify_identity_consistency "${TEST_TMP}/state.json" "${TEST_TMP}/config.toml" "${TEST_TMP}/config.json" "${TEST_TMP}/owner.uri" "${TEST_TMP}/users.json"
printf '%s\n' "$(render_vless_uri 00000000-0000-4000-8000-000000000000 203.0.113.10 443 www.cloudflare.com "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID")" > "${TEST_TMP}/owner.uri.bad"
assert_failure "detects UUID drift between URI and state" \
  verify_identity_consistency "${TEST_TMP}/state.json" "${TEST_TMP}/config.toml" "${TEST_TMP}/config.json" "${TEST_TMP}/owner.uri.bad" "${TEST_TMP}/users.json"
printf '%s\n' "$(render_vless_uri "$TEST_UUID" 203.0.113.10 443 www.cloudflare.com "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID")" > "${TEST_TMP}/owner.uri"
assert_success "helper documents vcl verify" grep -q 'vcl verify' "${TEST_TMP}/vincula"
assert_success "migration tolerates legacy inbound check failure" \
  grep -q 'legacy inbound fields removed in sing-box 1.13' "${PROJECT_DIR}/vincula.sh"
assert_success "migration uses owner_active_uuid_from_registry" \
  grep -q 'owner_active_uuid_from_registry "\$USERS_FILE"' "${PROJECT_DIR}/vincula.sh"
assert_success "migration skips health wait for legacy config" \
  grep -q 'Skipping pre-migration service health wait' "${PROJECT_DIR}/vincula.sh"
assert_failure "helper must not reassign readonly USERS_FILE" \
  grep -q 'USERS_FILE=$staged_users' "${PROJECT_DIR}/bin/vincula"
assert_success "user_mutation_apply passes staged users path" \
  grep -q 'render_config_from_registry "$staged_config" "$staged_users"' "${PROJECT_DIR}/bin/vincula"
assert_success "helper tracks vincula state dir" grep -q '/etc/vincula' "${TEST_TMP}/vincula"
assert_success "helper documents vcl command" grep -q 'vcl info' "${TEST_TMP}/vincula"
assert_success "helper documents logs follow" grep -q 'vcl logs -f' "${TEST_TMP}/vincula"
assert_success "helper documents diagnose" grep -q 'vcl diagnose' "${TEST_TMP}/vincula"
assert_success "diagnose reports untestable external reachability" grep -q 'cannot be tested locally' "${TEST_TMP}/vincula"
assert_success "diagnose includes REALITY self-test" grep -q 'REALITY end-to-end self-test' "${TEST_TMP}/vincula"
assert_success "helper status checks listener ownership" grep -q 'owned by sing-box' "${TEST_TMP}/vincula"
assert_success "unit is labeled as vincula-managed" grep -q 'managed by vincula' "${TEST_TMP}/sing-box.service"
assert_success "unit checks config before start" grep -q '^ExecStartPre=/usr/local/bin/sing-box check -c /etc/sing-box/config.json$' "${TEST_TMP}/sing-box.service"
assert_success "unit has Managed-By ownership marker" unit_has_vincula_marker "${TEST_TMP}/sing-box.service"
assert_success "helper has Managed-By ownership marker" helper_has_vincula_marker "${TEST_TMP}/vincula"

render_install_manifest "${TEST_TMP}/install.manifest"
assert_success "install.manifest records project vincula" grep -q '^project=vincula$' "${TEST_TMP}/install.manifest"
assert_equal "install.manifest lists sing-box binary" "/usr/local/bin/sing-box" \
  "$(manifest_values "${TEST_TMP}/install.manifest" file | awk '$0=="/usr/local/bin/sing-box" {print; exit}')"
assert_equal "install.manifest lists vcl symlink" "/usr/local/bin/vcl" \
  "$(manifest_values "${TEST_TMP}/install.manifest" symlink | awk '$0=="/usr/local/bin/vcl" {print; exit}')"
assert_success "install.manifest lists state directory" grep -q '^directory=/etc/vincula$' "${TEST_TMP}/install.manifest"

render_state "${TEST_TMP}/state-created.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 true true 0 0 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node
assert_equal "persists Vincula-created service account" "true" \
  "$(json_bool_field "${TEST_TMP}/state-created.json" created_by_vincula)"
assert_equal "persists Vincula-created service group" "true" \
  "$(json_bool_field "${TEST_TMP}/state-created.json" group_created_by_vincula)"
render_state "${TEST_TMP}/state-reused.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 false false 0 0 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node
assert_equal "persists reused service account" "false" \
  "$(json_bool_field "${TEST_TMP}/state-reused.json" created_by_vincula)"
assert_success "treats created_by_vincula true as owned" \
  service_account_flag "${TEST_TMP}/state-created.json" created_by_vincula
assert_failure "treats created_by_vincula false as not owned" \
  service_account_flag "${TEST_TMP}/state-reused.json" created_by_vincula

assert_success "accepts uninstall confirmation y" is_uninstall_affirmative y
assert_success "accepts uninstall confirmation YES" is_uninstall_affirmative YES
assert_failure "rejects uninstall confirmation n" is_uninstall_affirmative n
assert_failure "rejects uninstall confirmation Yes" is_uninstall_affirmative Yes

printf 'owned\n' > "${TEST_TMP}/probe.bin"
printf '%s  %s\n' "$(sha256sum "${TEST_TMP}/probe.bin" | awk '{print $1}')" "${TEST_TMP}/probe.bin" > "${TEST_TMP}/probe.bin.sha256"
assert_success "accepts matching binary checksum" verify_binary_matches_checksum "${TEST_TMP}/probe.bin.sha256"
printf 'tampered\n' > "${TEST_TMP}/probe.bin"
assert_failure "rejects mismatched binary checksum" verify_binary_matches_checksum "${TEST_TMP}/probe.bin.sha256"

ln -s /usr/local/bin/vincula "${TEST_TMP}/vcl"
assert_success "accepts Vincula vcl symlink" symlink_target_is "${TEST_TMP}/vcl" /usr/local/bin/vincula
rm -f "${TEST_TMP}/vcl"
printf 'foreign\n' > "${TEST_TMP}/vcl"
assert_failure "rejects foreign vcl file" symlink_target_is "${TEST_TMP}/vcl" /usr/local/bin/vincula
rm -f "${TEST_TMP}/vcl"
ln -s /usr/local/bin/true "${TEST_TMP}/vcl"
assert_failure "rejects vcl symlink to another program" symlink_target_is "${TEST_TMP}/vcl" /usr/local/bin/vincula

mkdir -p "${TEST_TMP}/unmanaged-dir"
printf 'keep\n' > "${TEST_TMP}/unmanaged-dir/custom.txt"
assert_failure "preserves non-empty unmanaged directory" remove_directory_if_empty "${TEST_TMP}/unmanaged-dir"
assert_success "unmanaged file still exists after rmdir attempt" test -f "${TEST_TMP}/unmanaged-dir/custom.txt"
mkdir -p "${TEST_TMP}/empty-dir"
assert_success "removes empty managed directory" remove_directory_if_empty "${TEST_TMP}/empty-dir"
assert_failure "empty directory is gone after rmdir" test -d "${TEST_TMP}/empty-dir"

printf 'file\n' > "${TEST_TMP}/owned.txt"
remove_managed_file "${TEST_TMP}/owned.txt" >/dev/null
assert_failure "managed file is deleted" test -e "${TEST_TMP}/owned.txt"

mkdir -p "${TEST_TMP}/not-a-file-dir"
remove_managed_file "${TEST_TMP}/not-a-file-dir" >/dev/null
assert_success "does not delete directories via file removal" test -d "${TEST_TMP}/not-a-file-dir"

assert_success "helper documents vcl uninstall" grep -q 'vcl uninstall' "${TEST_TMP}/vincula"
assert_success "helper documents uninstall --yes" grep -q 'vcl uninstall --yes' "${TEST_TMP}/vincula"
assert_success "helper rejects uninstall --force" grep -q 'uninstall --force is not supported' "${TEST_TMP}/vincula"
assert_success "helper documents vcl connections" grep -q 'vcl connections' "${TEST_TMP}/vincula"
assert_success "helper documents vcl stats" grep -q 'vcl stats today' "${TEST_TMP}/vincula"
assert_success "helper documents vcl accounting status" grep -q 'vcl accounting status' "${TEST_TMP}/vincula"
assert_success "accounting status prefers non-empty JSONL" \
  grep -q 'non-empty events.jsonl' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents stats month" grep -q 'vcl stats today|yesterday|--days N|--month' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents stats top" grep -q 'vcl stats top users|departments|hosts' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents stats host" grep -q 'vcl stats host' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents accounting retention" grep -q 'vcl accounting retention' "${PROJECT_DIR}/bin/vincula"
assert_success "connections fail when accountd inactive" \
  grep -q 'UNAVAILABLE: vincula-accountd' "${PROJECT_DIR}/bin/vincula"
assert_success "gen-release-lock includes vincula-stats.py" \
  grep -q 'lib/vincula-stats.py' "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_success "gen-release-lock includes vincula-bootstrap.sh" \
  grep -q 'vincula-bootstrap.sh' "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_success "release.lock includes vincula-bootstrap.sh" \
  grep -q 'vincula-bootstrap.sh' "${PROJECT_DIR}/release.lock"
assert_success "verify_sibling_release_lock warns when lock is missing" \
  awk '/^verify_sibling_release_lock\(\)/,/^}/ {print}' "${PROJECT_DIR}/vincula.sh" | grep -q 'release.lock not found'
nolock_dir="${TEST_TMP}/missing-release-lock"
mkdir -p "$nolock_dir"
cp "${PROJECT_DIR}/vincula.sh" "${nolock_dir}/vincula.sh"
nolock_rc=0
nolock_err=$(bash -c 'source "$1"' _ "${nolock_dir}/vincula.sh" 2>&1 >/dev/null) || nolock_rc=$?
if (( nolock_rc == 0 )) && [[ "$nolock_err" == *"release.lock not found"* ]]; then
  pass "missing release.lock prints WARN and continues"
else
  fail "missing release.lock prints WARN and continues (rc=${nolock_rc}, err=${nolock_err})"
fi
assert_success "build-release includes vincula-stats.py" \
  grep -q 'lib/vincula-stats.py' "${PROJECT_DIR}/scripts/build-release.sh"
assert_success "python3 can compile vincula-stats" \
  python3 -m py_compile "${PROJECT_DIR}/lib/vincula-stats.py"
assert_success "helper notes polling is not exact billing" grep -q 'Polling ≠ exact billing' "${TEST_TMP}/vincula"

uninstall_fn=$(awk '
  /^cmd_uninstall\(\)/ {in_fn=1}
  in_fn {print}
  /^}$/ && in_fn {exit}
' "${TEST_TMP}/vincula")
if [[ "$uninstall_fn" == *curl* || "$uninstall_fn" == *wget* || "$uninstall_fn" == *apt* ]]; then
  fail "uninstall does not call curl wget or apt"
else
  pass "uninstall does not call curl wget or apt"
fi
if [[ "$uninstall_fn" == *'rm -rf'* ]]; then
  fail "uninstall does not rm -rf managed roots"
else
  pass "uninstall does not rm -rf managed roots"
fi

assert_equal "looks up IPv4 from api.ipify.org" "https://api.ipify.org" "$PUBLIC_IP_URL"
assert_equal "production listener is IPv4" "0.0.0.0" "$DEFAULT_LISTEN"
assert_success "generated config listens on IPv4" grep -q '"listen": "0.0.0.0"' "${TEST_TMP}/config.json"
assert_success "settings listen on IPv4" grep -q '^listen = "0.0.0.0"$' "${TEST_TMP}/config.toml"
assert_success "detects SOCKS5 via curl --help all" curl_supports_socks5_hostname
assert_success "helper uses curl --help all for SOCKS5" grep -q 'curl --help all' "${TEST_TMP}/vincula"
assert_failure "helper does not use truncated curl --help for SOCKS5" \
  grep -q 'curl --help 2>&1' "${TEST_TMP}/vincula"

assert_equal "keeps a healthy REALITY host during migration" "www.cloudflare.com" \
  "$(resolve_migration_reality_host www.cloudflare.com)"
assert_failure "refuses known-bad REALITY host without VCL_REALITY_HOST" \
  resolve_migration_reality_host www.microsoft.com
assert_equal "replaces known-bad REALITY host when VCL_REALITY_HOST is set" "www.cloudflare.com" \
  "$(VCL_REALITY_HOST=www.cloudflare.com resolve_migration_reality_host www.microsoft.com)"

write_backup_marker "${TEST_TMP}" 0.1.4
assert_success "recognizes a marked Vincula backup directory" is_vincula_backup_dir "$TEST_TMP"
mkdir -p "${TEST_TMP}/legacy-backup"
printf '%s\n' '{"project_version":"0.1.3","reality_private_key":"x"}' > "${TEST_TMP}/legacy-backup/state.json"
assert_success "recognizes a legacy unmarked Vincula backup" is_vincula_backup_dir "${TEST_TMP}/legacy-backup"
mkdir -p "${TEST_TMP}/foreign-backup"
printf 'nope\n' > "${TEST_TMP}/foreign-backup/notes.txt"
assert_failure "rejects a foreign backup directory" is_vincula_backup_dir "${TEST_TMP}/foreign-backup"

assert_success "matches persisted service account identity" \
  passwd_identity_matches 995 995 /var/lib/sing-box /usr/sbin/nologin 995 995 /var/lib/sing-box /usr/sbin/nologin
assert_failure "rejects service account UID drift" \
  passwd_identity_matches 995 995 /var/lib/sing-box /usr/sbin/nologin 1100 995 /var/lib/sing-box /usr/sbin/nologin
assert_failure "rejects incomplete service account identity" \
  passwd_identity_matches 0 995 /var/lib/sing-box /usr/sbin/nologin 0 995 /var/lib/sing-box /usr/sbin/nologin

render_state "${TEST_TMP}/state-identity.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 true true 995 995 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node
assert_equal "persists service account uid" "995" "$(json_numeric_field "${TEST_TMP}/state-identity.json" uid)"
assert_equal "persists service account home" "/var/lib/sing-box" "$(json_quoted_field "${TEST_TMP}/state-identity.json" home)"

render_install_manifest "${TEST_TMP}/install.manifest.expected"
assert_success "install.manifest matches the renderer" \
  install_manifest_matches_expected "${TEST_TMP}/install.manifest"

assert_success "helper stops the service before deleting files" \
  grep -q 'no files were removed' "${TEST_TMP}/vincula"
assert_success "helper uninstall lists migration backups" \
  grep -q '/var/backups/vincula' "${TEST_TMP}/vincula"

# --- V0.2.1–0.2.4 accounting ---
assert_success "accountd unit has Managed-By marker" \
  grep -q '^# Managed-By: vincula$' "${PROJECT_DIR}/lib/vincula-accountd.service"
assert_success "accountd unit After=sing-box" \
  grep -q 'After=.*sing-box.service' "${PROJECT_DIR}/lib/vincula-accountd.service"
assert_success "accountd unit has NoNewPrivileges" \
  grep -q '^NoNewPrivileges=true$' "${PROJECT_DIR}/lib/vincula-accountd.service"
assert_success "accountd unit version stamp is 0.2.6" \
  grep -q 'Vincula-Version: 0.2.6' "${PROJECT_DIR}/lib/vincula-accountd.service"
assert_success "accountd unit has ProtectKernelTunables" \
  grep -q '^ProtectKernelTunables=true$' "${PROJECT_DIR}/lib/vincula-accountd.service"
assert_success "accountd unit has ProtectKernelModules" \
  grep -q '^ProtectKernelModules=true$' "${PROJECT_DIR}/lib/vincula-accountd.service"
assert_success "accountd unit has ProtectControlGroups" \
  grep -q '^ProtectControlGroups=true$' "${PROJECT_DIR}/lib/vincula-accountd.service"
assert_success "accountd unit has RestrictRealtime" \
  grep -q '^RestrictRealtime=true$' "${PROJECT_DIR}/lib/vincula-accountd.service"
assert_success "python3 can compile vincula-accountd" \
  python3 -m py_compile "${PROJECT_DIR}/lib/vincula-accountd.py"
assert_success "event schema file exists" \
  test -f "${PROJECT_DIR}/lib/vincula-event.schema.json"
assert_success "accounting reliability doc exists" \
  test -f "${PROJECT_DIR}/docs/accounting-reliability.md"
assert_success "preflight lists VAR_LIB_VINCULA" \
  grep -q 'VAR_LIB_VINCULA' "${PROJECT_DIR}/vincula.sh"
if awk '/^preflight_clean_install\(\)/,/^}/ {print}' "${PROJECT_DIR}/vincula.sh" | grep -q 'ACCOUNTING_DB_FILE'; then
  pass "preflight_clean_install mentions ACCOUNTING_DB_FILE"
else
  fail "preflight_clean_install mentions ACCOUNTING_DB_FILE"
fi
rollback_fn=$(awk '/^rollback_install\(\)/,/^}/ {print}' "${PROJECT_DIR}/vincula.sh")
if [[ "$rollback_fn" == *'-wal'* ]]; then
  pass "rollback_install removal loop includes -wal"
else
  fail "rollback_install removal loop includes -wal"
fi
if [[ "$rollback_fn" == *'-shm'* ]]; then
  pass "rollback_install removal loop includes -shm"
else
  fail "rollback_install removal loop includes -shm"
fi
uninstall_src_fn=$(awk '
  /^cmd_uninstall\(\)/ {in_fn=1}
  in_fn {print}
  /^}$/ && in_fn {exit}
' "${PROJECT_DIR}/bin/vincula")
if [[ "$uninstall_src_fn" == *'-wal'* ]]; then
  pass "cmd_uninstall removal loop includes -wal"
else
  fail "cmd_uninstall removal loop includes -wal"
fi
if [[ "$uninstall_src_fn" == *'-shm'* ]]; then
  pass "cmd_uninstall removal loop includes -shm"
else
  fail "cmd_uninstall removal loop includes -shm"
fi
if awk '/^preflight_clean_install\(\)/,/^}/ {print}' "${PROJECT_DIR}/vincula.sh" | grep -q 'rm -f'; then
  pass "preflight refusal message contains rm -f guidance"
else
  fail "preflight refusal message contains rm -f guidance"
fi
assert_success "enable_accountd hard-fails on health" \
  grep -q 'wait_for_accountd_healthy || die' "${PROJECT_DIR}/vincula.sh"
if awk '/^enable_accountd_service\(\)/,/^}/ {print}' "${PROJECT_DIR}/vincula.sh" | grep -q 'log_warn'; then
  fail "enable_accountd has no log_warn soft-fail path (unexpected soft-fail)"
else
  pass "enable_accountd has no log_warn soft-fail path"
fi
assert_success "install.manifest lists events.jsonl" \
  grep -q 'events.jsonl' "${TEST_TMP}/install.manifest"
assert_success "helper uninstall mentions historical accounting data" \
  grep -q 'Historical accounting data' "${TEST_TMP}/vincula"
assert_success "bootstrap script exists" \
  test -f "${PROJECT_DIR}/vincula-bootstrap.sh"
assert_success "gen-release-lock script exists" \
  test -f "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_success "build-release script exists" \
  test -f "${PROJECT_DIR}/scripts/build-release.sh"
assert_success "build-release produces verified dist package" \
  bash "${PROJECT_DIR}/scripts/build-release.sh" >/dev/null
assert_success "dist tree contains release.lock" \
  test -f "${PROJECT_DIR}/dist/vincula-${VINCULA_VERSION}/release.lock"
assert_success "dist archive exists" \
  test -f "${PROJECT_DIR}/dist/vincula-${VINCULA_VERSION}.tar.gz"

assert_success "stats/connections warn on stale accounting" \
  grep -q 'warn_if_accounting_stale' "${PROJECT_DIR}/bin/vincula"
assert_success "accountd health rejects wrong Clash secret" \
  grep -q 'wrong-\${secret}' "${PROJECT_DIR}/vincula.sh"

TEST_SECRET="test-clash-secret-not-for-production"
render_sing_box_config_accounting \
  "${TEST_TMP}/acct-config.json" "${TEST_TMP}/users.json" \
  "$TEST_PRIVATE_KEY" "$TEST_SHORT_ID" 443 www.cloudflare.com \
  0.0.0.0 9090 "$TEST_SECRET" true
if command -v python3 >/dev/null 2>&1; then
  assert_success "accounting config is valid JSON" \
    python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${TEST_TMP}/acct-config.json"
fi
assert_success "accounting config binds clash_api to 127.0.0.1" \
  grep -q '127.0.0.1:9090' "${TEST_TMP}/acct-config.json"
assert_failure "accounting config must not bind clash_api to 0.0.0.0" \
  grep -q '"external_controller": "0.0.0.0' "${TEST_TMP}/acct-config.json"
assert_success "accounting config has acct/owner outbound" \
  grep -q '"tag": "acct/owner"' "${TEST_TMP}/acct-config.json"
assert_success "accounting config has auth_user route" \
  grep -q '"auth_user"' "${TEST_TMP}/acct-config.json"
assert_success "accounting config uses sniff route action not inbound sniff" \
  grep -q '"action": "sniff"' "${TEST_TMP}/acct-config.json"
assert_failure "accounting config must not use removed inbound sniff field" \
  grep -q '"sniff": true' "${TEST_TMP}/acct-config.json"
assert_success "accounting config uses route action for auth_user" \
  grep -q '"action": "route"' "${TEST_TMP}/acct-config.json"
assert_success "accounting config keeps route.final direct" \
  grep -q '"final": "direct"' "${TEST_TMP}/acct-config.json"
assert_success "settings include clash_api_port" \
  grep -q '^clash_api_port = ' "${TEST_TMP}/config.toml"
assert_success "settings include clash_api_secret" \
  grep -q '^clash_api_secret = ' "${TEST_TMP}/config.toml"
assert_success "install.manifest lists vincula-accountd.py" \
  grep -q 'vincula-accountd.py' "${TEST_TMP}/install.manifest"
assert_success "install.manifest lists vincula-stats.py" \
  grep -q 'vincula-stats.py' "${TEST_TMP}/install.manifest"
assert_success "install.manifest lists vincula-accountd.service" \
  grep -q 'vincula-accountd.service' "${TEST_TMP}/install.manifest"

# Sample events.jsonl ingest without root (needs users.json for tag→user_id)
SAMPLE_EVENTS="${TEST_TMP}/events.jsonl"
SAMPLE_DB="${TEST_TMP}/accounting.db"
SAMPLE_USERS="${TEST_TMP}/users-acct.json"
cat > "$SAMPLE_USERS" <<'JSON'
{
  "schema_version": 2,
  "users": [
    {
      "user_id": "u-alice",
      "tag": "alice",
      "display_name": "Alice",
      "department": "",
      "enabled": true,
      "created_at": "2026-08-14T00:00:00Z",
      "credentials": []
    },
    {
      "user_id": "u-bob",
      "tag": "bob",
      "display_name": "Bob",
      "department": "",
      "enabled": true,
      "created_at": "2026-08-14T00:00:00Z",
      "credentials": []
    }
  ]
}
JSON
cat > "$SAMPLE_EVENTS" <<'JSONL'
{"event":"connection_closed","connection_id":"c-test-1","node_id":"6fc96a10-1111-4111-8111-111111111111","user":"alice","destination_host":"Example.COM.","destination_ip":"203.0.113.10","destination_port":443,"network":"tcp","upload_bytes":100,"download_bytes":2000,"started_at":"2026-08-14T06:00:00Z","closed_at":"2026-08-14T06:01:00Z"}
JSONL
assert_success "accountd ingests sample jsonl event" \
  python3 "${PROJECT_DIR}/lib/vincula-accountd.py" --db "$SAMPLE_DB" --users "$SAMPLE_USERS" --ingest-file "$SAMPLE_EVENTS"
assert_success "ingested connection row has user_id" \
  python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); n=c.execute("select count(*) from connections where user_id=\"u-alice\"").fetchone()[0]; raise SystemExit(0 if n>=1 else 1)' "$SAMPLE_DB"
assert_success "meta.schema_version is 2" \
  python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); v=c.execute("select value from meta where key=\"schema_version\"").fetchone()[0]; raise SystemExit(0 if v=="2" else 1)' "$SAMPLE_DB"
assert_success "destination host normalized lowercase strip dot" \
  python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); h=c.execute("select destination_host from connections where connection_id=\"c-test-1\"").fetchone()[0]; raise SystemExit(0 if h=="example.com" else 1)' "$SAMPLE_DB"

# Multi-user config: owner + alice → acct tags + localhost clash_api
ALICE_UUID="22222222-2222-4222-8222-222222222222"
python3 - "${TEST_TMP}/users-multi.json" "$TEST_UUID" "$ALICE_UUID" "$TEST_NODE_ID" <<'PY'
import json, sys
path, owner_uuid, alice_uuid, node_id = sys.argv[1:5]
data = {
  "schema_version": 2,
  "users": [
    {
      "user_id": "u-owner", "tag": "owner", "display_name": "Owner", "department": "",
      "enabled": True, "created_at": "2026-08-14T00:00:00Z",
      "credentials": [{"credential_id": "c1", "node_id": node_id, "uuid": owner_uuid,
                       "status": "active", "created_at": "2026-08-14T00:00:00Z", "revoked_at": None}],
    },
    {
      "user_id": "u-alice", "tag": "alice", "display_name": "Alice", "department": "eng",
      "enabled": True, "created_at": "2026-08-14T00:00:00Z",
      "credentials": [{"credential_id": "c2", "node_id": node_id, "uuid": alice_uuid,
                       "status": "active", "created_at": "2026-08-14T00:00:00Z", "revoked_at": None}],
    },
  ],
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
render_sing_box_config_accounting \
  "${TEST_TMP}/multi-config.json" "${TEST_TMP}/users-multi.json" \
  "$TEST_PRIVATE_KEY" "$TEST_SHORT_ID" 443 www.cloudflare.com \
  0.0.0.0 9090 "$TEST_SECRET" true
assert_success "multi-user config has acct/alice" grep -q '"tag": "acct/alice"' "${TEST_TMP}/multi-config.json"
assert_success "multi-user config has acct/owner" grep -q '"tag": "acct/owner"' "${TEST_TMP}/multi-config.json"
assert_success "multi-user clash_api is localhost" grep -q '127.0.0.1:9090' "${TEST_TMP}/multi-config.json"

# Event schema parsing + rollup math + stale open close + poll baseline
rollup_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/rollup.db" "$SAMPLE_USERS" <<'PY' || rollup_rc=$?
import importlib.util, sys

mod_path, db, users = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users)

assert mod.normalize_destination_host("Example.COM.") == "example.com"
assert mod.normalize_destination_host("foo.") == "foo"
assert mod.normalize_destination_host(None) is None

line = '{"event":"connection_closed","connection_id":"r1","node_id":"n1","user":"bob","destination_host":"cdn.example","destination_ip":"198.51.100.2","destination_port":443,"network":"tcp","upload_bytes":50,"download_bytes":500,"started_at":"2026-08-14T10:00:00Z","closed_at":"2026-08-14T10:05:00Z"}'
ev = mod.parse_jsonl_event(line)
assert ev and ev["user_tag"] == "bob" and ev["user_id"] == "u-bob" and ev["event"] == "connection_close", ev

conn = mod.open_db(db)
assert mod.meta_get(conn, "schema_version") == "2"
mod.upsert_connection(conn, ev, close=True)
mod.upsert_connection(conn, {
    "connection_id": "stale-1",
    "node_id": "n1",
    "user_id": "u-bob",
    "user_tag": "bob",
    "destination_host": None,
    "destination_ip": "198.51.100.9",
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 10,
    "download_bytes": 20,
    "started_at": "2026-08-14T09:00:00Z",
    "ts": "2026-08-14T09:01:00Z",
}, close=False)
n = mod.close_stale_open_connections(conn, now="2026-08-14T12:00:00Z")
assert n == 1, n
row = conn.execute("SELECT closed_at, upload_bytes FROM connections WHERE connection_id='stale-1'").fetchone()
assert row[0] == "2026-08-14T12:00:00Z" and row[1] == 10

# Poll baseline: first sight zero delta; second sight positive delta only
known = {}
live1 = [{
    "connection_id": "p1",
    "node_id": "n1",
    "user_id": "u-alice",
    "user_tag": "alice",
    "destination_host": "a.example",
    "destination_ip": None,
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 1000,
    "download_bytes": 2000,
    "started_at": "2026-08-14T11:00:00Z",
    "ts": "2026-08-14T11:00:00Z",
}]
known = mod.apply_poll_delta(conn, live1, known)
row = conn.execute("SELECT upload_bytes, download_bytes FROM connections WHERE connection_id='p1'").fetchone()
assert row[0] == 0 and row[1] == 0, row
live2 = [dict(live1[0], upload_bytes=1500, download_bytes=2500, ts="2026-08-14T11:00:05Z")]
known = mod.apply_poll_delta(conn, live2, known)
row = conn.execute("SELECT upload_bytes, download_bytes FROM connections WHERE connection_id='p1'").fetchone()
assert row[0] == 500 and row[1] == 500, row

mod.rollup_daily_usage(conn)
conn.commit()
agg = conn.execute(
    "SELECT SUM(upload_bytes), SUM(download_bytes), SUM(connection_count) FROM daily_usage WHERE user_id='u-bob'"
).fetchone()
assert agg[0] == 60 and agg[1] == 520 and agg[2] == 2, agg
cols = [r[1] for r in conn.execute("PRAGMA table_info(connections)").fetchall()]
assert "user_id" in cols and "user_tag" in cols, cols
conn.close()
PY
if (( rollup_rc == 0 )); then
  pass "event parse + rollup + stale close + poll baseline"
else
  fail "event parse + rollup + stale close + poll baseline"
fi

# D1: rollup crash-safety (injected INSERT failure must not commit an empty table)
# and retention×rollup ordering with 90/90 defaults.
d1_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/d1-rollup.db" "$SAMPLE_USERS" <<'PY' || d1_rc=$?
import importlib.util, sqlite3, sys
from datetime import datetime, timedelta, timezone

mod_path, db, users = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users)

assert mod.DEFAULT_DAILY_RETENTION_DAYS == 90, mod.DEFAULT_DAILY_RETENTION_DAYS
assert mod.DEFAULT_RAW_RETENTION_DAYS == 90, mod.DEFAULT_RAW_RETENTION_DAYS

conn = mod.open_db(db)
mod.upsert_connection(conn, {
    "connection_id": "keep-1",
    "node_id": "n1",
    "user_id": "u-bob",
    "user_tag": "bob",
    "destination_host": "keep.example",
    "destination_ip": None,
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 10,
    "download_bytes": 20,
    "started_at": "2026-08-14T09:00:00Z",
    "closed_at": "2026-08-14T09:01:00Z",
    "ts": "2026-08-14T09:01:00Z",
}, close=True)
mod.rollup_daily_usage(conn)
conn.commit()
before = conn.execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0]
assert before > 0, before

def deny_live_daily_insert(action, table, _column, _dbname, _source):
    if action == sqlite3.SQLITE_INSERT and table == "daily_usage":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK

conn.set_authorizer(deny_live_daily_insert)
try:
    mod.rollup_daily_usage(conn)
    raise AssertionError("rollup_daily_usage should have failed")
except sqlite3.DatabaseError as exc:
    msg = str(exc).lower()
    assert "not authorized" in msg or "denied" in msg or "authorizer" in msg, exc
conn.set_authorizer(None)
conn.commit()
after = conn.execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0]
assert after == before and after > 0, (before, after)
conn.close()

# 100 days of connections + prefilled daily; rollup then apply_retention(90, 90)
ret_db = db + "-retention"
conn = mod.open_db(ret_db)
now = datetime.now(timezone.utc)
for i in range(100):
    when = now - timedelta(days=i)
    day = when.strftime("%Y-%m-%d")
    ts = when.strftime("%Y-%m-%dT12:00:00Z")
    conn.execute(
        """
        INSERT INTO connections(
          connection_id, node_id, user_id, user_tag, destination_host, destination_ip,
          destination_port, network, upload_bytes, download_bytes,
          started_at, closed_at, last_seen_at
        ) VALUES (?, 'n1', 'u-bob', 'bob', ?, NULL, 443, 'tcp', 1, 2, ?, ?, ?)
        """,
        (f"c-{i}", f"host-{i}.example", ts, ts, ts),
    )
    conn.execute(
        """
        INSERT INTO daily_usage(
          date, user_id, user_tag, destination_host,
          upload_bytes, download_bytes, connection_count
        ) VALUES (?, 'u-bob', 'bob', ?, 1, 2, 1)
        """,
        (day, f"host-{i}.example"),
    )
conn.commit()
mod.rollup_daily_usage(conn)
mod.apply_retention(conn, 90, 90)
conn.commit()
daily_n = conn.execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0]
assert daily_n > 0, daily_n
dates = [r[0] for r in conn.execute("SELECT date FROM daily_usage ORDER BY date").fetchall()]
cutoff_date = datetime.fromtimestamp(now.timestamp() - 90 * 86400, timezone.utc).strftime("%Y-%m-%d")
assert min(dates) >= cutoff_date, (min(dates), cutoff_date)
today = now.strftime("%Y-%m-%d")
assert today in dates or (now - timedelta(days=1)).strftime("%Y-%m-%d") in dates, dates[-3:]
old_ts = (now - timedelta(days=99)).strftime("%Y-%m-%dT12:00:00Z")
old_n = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE last_seen_at = ?", (old_ts,)
).fetchone()[0]
assert old_n == 0, old_n
recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT12:00:00Z")
recent_n = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE last_seen_at = ?", (recent_ts,)
).fetchone()[0]
assert recent_n == 1, recent_n
conn.close()
PY
if (( d1_rc == 0 )); then
  pass "rollup failure does not empty daily_usage"
  pass "retention x rollup keeps recent daily rows at 90/90"
else
  fail "rollup failure does not empty daily_usage"
  fail "retention x rollup keeps recent daily rows at 90/90"
fi

# F1: tag→user_id hot-reload on users.json mtime change
f1_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/f1-hotreload" <<'PY' || f1_rc=$?
import importlib.util, json, os, sys, time, urllib.error

mod_path, work = sys.argv[1], sys.argv[2]
os.makedirs(work, exist_ok=True)
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

users_path = os.path.join(work, "users.json")
events_path = os.path.join(work, "events.jsonl")
db_path = os.path.join(work, "acct.db")

bob_only = {
    "schema_version": 2,
    "users": [
        {
            "user_id": "u-bob",
            "tag": "bob",
            "display_name": "Bob",
            "department": "",
            "enabled": True,
            "created_at": "2026-08-14T00:00:00Z",
            "credentials": [],
        }
    ],
}
with open(users_path, "w", encoding="utf-8") as f:
    json.dump(bob_only, f)

alice_line = (
    '{"event":"connection_closed","connection_id":"c-alice-1","node_id":"n1",'
    '"user":"alice","destination_host":"a.example","destination_ip":null,'
    '"destination_port":443,"network":"tcp","upload_bytes":1,"download_bytes":2,'
    '"started_at":"2026-08-14T10:00:00Z","closed_at":"2026-08-14T10:00:01Z"}\n'
)
alice_line2 = alice_line.replace("c-alice-1", "c-alice-2")
with open(events_path, "w", encoding="utf-8") as f:
    f.write(alice_line)

mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users_path)
os.environ["VCL_USERS_FILE"] = users_path
daemon = mod.AccountDaemon(
    db_path=db_path,
    events_path=events_path,
    clash_url="http://127.0.0.1:1/connections",
    users_path=users_path,
)
mod.fetch_clash_connections = lambda *a, **k: (_ for _ in ()).throw(
    urllib.error.URLError("fake clash unused")
)
conn = mod.open_db(db_path)
daemon._tick(conn)
n = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
assert n == 0, n

bob_and_alice = {
    "schema_version": 2,
    "users": bob_only["users"]
    + [
        {
            "user_id": "u-alice",
            "tag": "alice",
            "display_name": "Alice",
            "department": "",
            "enabled": False,
            "created_at": "2026-08-14T00:00:00Z",
            "credentials": [],
        }
    ],
}
# Ensure mtime actually changes even on coarse filesystems.
time.sleep(0.05)
with open(users_path, "w", encoding="utf-8") as f:
    json.dump(bob_and_alice, f)
os.utime(users_path, None)
with open(events_path, "a", encoding="utf-8") as f:
    f.write(alice_line2)

daemon._tick(conn)
n = conn.execute("SELECT COUNT(*) FROM connections WHERE user_id='u-alice'").fetchone()[0]
assert n >= 1, n
assert mod.TAG_TO_USER_ID.get("alice") == "u-alice"
# Disabled users remain resolvable after full map replace.
assert mod.resolve_user_id("alice") == "u-alice"

kept = dict(mod.TAG_TO_USER_ID)
time.sleep(0.05)
with open(users_path, "w", encoding="utf-8") as f:
    f.write("{not json")
os.utime(users_path, None)
daemon._tick(conn)
assert mod.TAG_TO_USER_ID == kept, mod.TAG_TO_USER_ID
conn.close()
PY
if (( f1_rc == 0 )); then
  pass "mtime hot-reload maps new tag after users.json change"
else
  fail "mtime hot-reload maps new tag after users.json change"
fi

# F2: empty events.jsonl is not success and must not block Clash polling
f2_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/f2-jsonl" "$SAMPLE_USERS" <<'PY' || f2_rc=$?
import importlib.util, os, sys, urllib.error

mod_path, work, users = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(work, exist_ok=True)
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users)

events_path = os.path.join(work, "events.jsonl")
db_path = os.path.join(work, "acct.db")
open(events_path, "w", encoding="utf-8").close()
assert os.path.getsize(events_path) == 0

polls = []

def fake_fetch(*_a, **_k):
    polls.append("poll")
    raise urllib.error.URLError("fake clash down")

mod.fetch_clash_connections = fake_fetch
daemon = mod.AccountDaemon(
    db_path=db_path,
    events_path=events_path,
    clash_url="http://127.0.0.1:1/connections",
    users_path=users,
)
conn = mod.open_db(db_path)
assert mod.meta_get(conn, "last_success_at") == ""
daemon._tick(conn)
assert polls == ["poll"], polls
assert mod.meta_get(conn, "last_success_at") == "", "empty JSONL must not refresh last_success_at"
conn.close()

# --once uses the same collect path
polls.clear()
once_db = os.path.join(work, "once.db")
daemon2 = mod.AccountDaemon(
    db_path=once_db,
    events_path=events_path,
    clash_url="http://127.0.0.1:1/connections",
    users_path=users,
)
conn = mod.open_db(once_db)
mod.close_stale_open_connections(conn)
daemon2._tick(conn)
assert "poll" in polls
assert mod.meta_get(conn, "last_success_at") == ""
conn.close()

# Legitimate JSONL events skip poll and count as success.
polls.clear()
legit = os.path.join(work, "legit.jsonl")
with open(legit, "w", encoding="utf-8") as f:
    f.write(
        '{"event":"connection_closed","connection_id":"c-bob-1","node_id":"n1",'
        '"user":"bob","destination_host":"b.example","destination_port":443,'
        '"network":"tcp","upload_bytes":3,"download_bytes":4,'
        '"started_at":"2026-08-14T10:00:00Z","closed_at":"2026-08-14T10:00:01Z"}\n'
    )
legit_db = os.path.join(work, "legit.db")
daemon3 = mod.AccountDaemon(
    db_path=legit_db,
    events_path=legit,
    clash_url="http://127.0.0.1:1/connections",
    users_path=users,
)
conn = mod.open_db(legit_db)
daemon3._tick(conn)
assert polls == [], polls
assert mod.meta_get(conn, "last_success_at")
n = conn.execute("SELECT COUNT(*) FROM connections WHERE connection_id='c-bob-1'").fetchone()[0]
assert n == 1, n

# Non-empty file caught up (producer idle): stay in JSONL mode, do not poll.
polls.clear()
before_success = mod.meta_get(conn, "last_success_at")
daemon3._tick(conn)
assert polls == [], "caught-up JSONL must not fall back to poll"
assert mod.meta_get(conn, "last_success_at") >= before_success
conn.close()
PY
if (( f2_rc == 0 )); then
  pass "empty JSONL is not success and does not block polling"
else
  fail "empty JSONL is not success and does not block polling"
fi

# --- 0.2.5 user provisioning offline tests ---
if command -v python3 >/dev/null 2>&1; then
  PROV_DIR="${TEST_TMP}/provision"
  mkdir -p "$PROV_DIR"
  OWNER_UUID="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
  NODE_ID="$TEST_NODE_ID"
  cat > "${PROV_DIR}/users.json" <<JSON
{
  "schema_version": 2,
  "users": [
    {
      "user_id": "11111111-1111-4111-8111-111111111111",
      "tag": "owner",
      "display_name": "Owner",
      "department": "",
      "enabled": true,
      "created_at": "2026-08-15T00:00:00Z",
      "credentials": [
        {
          "credential_id": "22222222-2222-4222-8222-222222222222",
          "node_id": "${NODE_ID}",
          "uuid": "${OWNER_UUID}",
          "status": "active",
          "created_at": "2026-08-15T00:00:00Z",
          "revoked_at": null
        }
      ]
    },
    {
      "user_id": "33333333-3333-4333-8333-333333333333",
      "tag": "alice",
      "display_name": "Alice Zhang",
      "department": "Sales",
      "enabled": true,
      "created_at": "2026-08-15T00:00:00Z",
      "credentials": [
        {
          "credential_id": "44444444-4444-4444-8444-444444444444",
          "node_id": "${NODE_ID}",
          "uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          "status": "active",
          "created_at": "2026-08-15T00:00:00Z",
          "revoked_at": null
        }
      ]
    }
  ]
}
JSON

  cat > "${PROV_DIR}/config-ok.json" <<'JSON'
{
  "inbounds": [
    {
      "type": "vless",
      "tag": "vless-reality-in",
      "users": [
        {"name": "owner", "uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "flow": "xtls-rprx-vision"},
        {"name": "alice", "uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "flow": "xtls-rprx-vision"}
      ]
    }
  ]
}
JSON
  assert_success "users_registry_verify passes for consistent registry/config" \
    users_registry_verify "${PROV_DIR}/users.json" "${PROV_DIR}/config-ok.json"

  cat > "${PROV_DIR}/config-bad.json" <<'JSON'
{
  "inbounds": [
    {
      "type": "vless",
      "tag": "vless-reality-in",
      "users": [
        {"name": "owner", "uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "flow": "xtls-rprx-vision"},
        {"name": "alice", "uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "flow": "xtls-rprx-vision"},
        {"name": "ghost", "uuid": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "flow": "xtls-rprx-vision"}
      ]
    }
  ]
}
JSON
  assert_failure "users_registry_verify fails when config has extra inbound user" \
    users_registry_verify "${PROV_DIR}/users.json" "${PROV_DIR}/config-bad.json"

  assert_success "users_registry_mutate set updates metadata" \
    users_registry_mutate "${PROV_DIR}/users.json" set alice "Alice Chen" Engineering
  assert_equal "set updates display_name" "Alice Chen" \
    "$(users_registry_field "${PROV_DIR}/users.json" alice display_name)"
  assert_equal "set updates department" "Engineering" \
    "$(users_registry_field "${PROV_DIR}/users.json" alice department)"

  list_out=$(users_registry_list "${PROV_DIR}/users.json")
  if [[ "$list_out" == *"TAG"* && "$list_out" == *"STATUS"* && "$list_out" != *"ACTIVE_UUID"* ]]; then
    pass "users_registry_list uses human STATUS format without UUID"
  else
    fail "users_registry_list uses human STATUS format without UUID"
  fi
  show_out=$(users_registry_show_human "${PROV_DIR}/users.json" alice)
  if [[ "$show_out" == *"Display name:"* && "$show_out" == *"Alice Chen"* && "$show_out" != *"bbbbbbbb-bbbb"* ]]; then
    pass "users_registry_show_human omits raw UUID"
  else
    fail "users_registry_show_human omits raw UUID"
  fi

  cat > "${PROV_DIR}/import-ok.csv" <<'CSV'
tag,display_name,department
bob.li,Bob Li,Engineering
charlie,王明,Engineering
CSV
  assert_success "import dry-run accepts valid CSV with dotted tags" \
    users_import_prepare "${PROV_DIR}/import-ok.csv" "${PROV_DIR}/users.json" "$NODE_ID" "" "" 0 1

  cat > "${PROV_DIR}/import-bad.csv" <<'CSV'
tag,display_name,department
alice,Dup Alice,Sales
Bad Tag,Nope,Sales
bob.li,Bob,Eng
bob.li,Bob Again,Eng
CSV
  assert_failure "import dry-run rejects conflicts and invalid tags" \
    users_import_prepare "${PROV_DIR}/import-bad.csv" "${PROV_DIR}/users.json" "$NODE_ID" "" "" 0 1

  assert_success "import prepare writes staged registry" \
    users_import_prepare "${PROV_DIR}/import-ok.csv" "${PROV_DIR}/users.json" "$NODE_ID" \
      "${PROV_DIR}/users-imported.json" "${PROV_DIR}/creds.csv" 0 0 \
      203.0.113.10 443 www.cloudflare.com "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID"
  assert_success "import staged registry includes bob.li" \
    grep -q '"tag": "bob.li"' "${PROV_DIR}/users-imported.json"
  assert_success "import credential CSV is written" test -f "${PROV_DIR}/creds.csv"
  assert_success "import credential CSV has vless_uri" grep -q 'vless://' "${PROV_DIR}/creds.csv"

  export_meta=$(users_export_csv "${PROV_DIR}/users.json" "" 0 0)
  if [[ "$export_meta" == tag,display_name,department,status,user_id* && "$export_meta" == *alice* ]]; then
    pass "users_export_csv metadata goes to stdout"
  else
    fail "users_export_csv metadata goes to stdout"
  fi

  # 100-user uniqueness + verify against minimal fake config
  if python3 - "$PROV_DIR" "$NODE_ID" <<'PY'
import json, uuid, sys
from pathlib import Path
base = Path(sys.argv[1])
node_id = sys.argv[2]
users = [{
    "user_id": "11111111-1111-4111-8111-111111111111",
    "tag": "owner",
    "display_name": "Owner",
    "department": "",
    "enabled": True,
    "created_at": "2026-08-15T00:00:00Z",
    "credentials": [{
        "credential_id": "22222222-2222-4222-8222-222222222222",
        "node_id": node_id,
        "uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "status": "active",
        "created_at": "2026-08-15T00:00:00Z",
        "revoked_at": None,
    }],
}]
inbound = [{"name": "owner", "uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "flow": "xtls-rprx-vision"}]
for i in range(100):
    tag = f"u{i:03d}"
    uid = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    vuuid = str(uuid.uuid4())
    users.append({
        "user_id": uid,
        "tag": tag,
        "display_name": f"User {i}",
        "department": "bulk",
        "enabled": True,
        "created_at": "2026-08-15T00:00:00Z",
        "credentials": [{
            "credential_id": cid,
            "node_id": node_id,
            "uuid": vuuid,
            "status": "active",
            "created_at": "2026-08-15T00:00:00Z",
            "revoked_at": None,
        }],
    })
    inbound.append({"name": tag, "uuid": vuuid, "flow": "xtls-rprx-vision"})
for i in range(20):
    users[1 + i]["enabled"] = False
    inbound = [x for x in inbound if x["name"] != users[1 + i]["tag"]]
for i in range(5):
    u = users[1 + i]
    u["enabled"] = True
    active = next(c for c in u["credentials"] if c["status"] == "active")
    inbound.append({"name": u["tag"], "uuid": active["uuid"], "flow": "xtls-rprx-vision"})
for i in range(30, 40):
    u = users[1 + i]
    old = u["credentials"][0]
    old["status"] = "revoked"
    old["revoked_at"] = "2026-08-15T01:00:00Z"
    new_uuid = str(uuid.uuid4())
    u["credentials"].append({
        "credential_id": str(uuid.uuid4()),
        "node_id": node_id,
        "uuid": new_uuid,
        "status": "active",
        "created_at": "2026-08-15T01:00:00Z",
        "revoked_at": None,
    })
    for x in inbound:
        if x["name"] == u["tag"]:
            x["uuid"] = new_uuid
for i in range(40, 60):
    users[1 + i]["display_name"] = f"Renamed {i}"
    users[1 + i]["department"] = "ops"
uids = [u["user_id"] for u in users]
tags = [u["tag"] for u in users]
cids = [c["credential_id"] for u in users for c in u["credentials"]]
active_uuids = [c["uuid"] for u in users for c in u["credentials"] if c["status"] == "active"]
assert len(uids) == len(set(uids)) == 101
assert len(tags) == len(set(tags)) == 101
assert len(cids) == len(set(cids))
assert len(active_uuids) == len(set(active_uuids))
(base / "users-100.json").write_text(json.dumps({"schema_version": 2, "users": users}, indent=2) + "\n", encoding="utf-8")
(base / "config-100.json").write_text(json.dumps({
    "inbounds": [{"type": "vless", "tag": "vless-reality-in", "users": inbound}]
}, indent=2) + "\n", encoding="utf-8")
PY
  then
    pass "100-user registry builds with unique ids"
  else
    fail "100-user registry builds with unique ids"
  fi
  assert_success "100-user verify PASS after disable/rotate/metadata" \
    users_registry_verify "${PROV_DIR}/users-100.json" "${PROV_DIR}/config-100.json"

  assert_success "helper documents user import" grep -q 'vcl user import' "${PROJECT_DIR}/bin/vincula"
  assert_success "helper documents user export" grep -q 'vcl user export' "${PROJECT_DIR}/bin/vincula"
  assert_success "helper documents user verify" grep -q 'vcl user verify' "${PROJECT_DIR}/bin/vincula"
  assert_success "helper documents user set" grep -q 'vcl user set' "${PROJECT_DIR}/bin/vincula"
  assert_success "helper warns on user mutation restart" \
    grep -q 'applying user changes restarts sing-box' "${PROJECT_DIR}/bin/vincula"
fi

# --- 0.2.6 accounting UX / vincula-stats.py ---
if command -v python3 >/dev/null 2>&1; then
  STATS_DIR="${TEST_TMP}/stats026"
  mkdir -p "$STATS_DIR"
  python3 - "$STATS_DIR" "${PROJECT_DIR}/lib/vincula-stats.py" <<'PY'
import json, os, sqlite3, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

base = Path(sys.argv[1])
stats_py = sys.argv[2]
db = base / "accounting.db"
users = base / "users.json"
today = datetime.now(timezone.utc).date()
yesterday = today - timedelta(days=1)
today_s, yday_s = today.isoformat(), yesterday.isoformat()

users.write_text(json.dumps({
    "schema_version": 2,
    "users": [
        {"user_id": "u-alice", "tag": "alice", "display_name": "Alice", "department": "Engineering"},
        {"user_id": "u-bob", "tag": "bob", "display_name": "Bob", "department": "Sales"},
        {"user_id": "u-carol", "tag": "carol", "display_name": "Carol", "department": "Engineering"},
    ],
}), encoding="utf-8")

conn = sqlite3.connect(db)
conn.executescript("""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE daily_usage (
  date TEXT NOT NULL,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  destination_host TEXT NOT NULL,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  connection_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (date, user_id, destination_host)
);
""")
conn.execute("INSERT INTO meta(key,value) VALUES('last_success_at', ?)", (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),))
rows = [
    (today_s, "u-alice", "alice", "github.com", 100, 1000, 2),
    (today_s, "u-alice", "alice", "203.0.113.10", 50, 50, 1),
    (today_s, "u-bob", "bob", "github.com", 200, 2000, 3),
    (yday_s, "u-carol", "carol", "example.com", 10, 90, 1),
    (yday_s, "u-alice", "alice", "example.com", 5, 5, 1),
]
conn.executemany(
    "INSERT INTO daily_usage VALUES (?,?,?,?,?,?,?)",
    rows,
)
conn.commit()
conn.close()

def run(*extra):
    cmd = [
        sys.executable, stats_py,
        "--db", str(db), "--users", str(users),
        "--collector-state", "active",
        "--last-success-at", "2026-08-15T00:00:00Z",
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)

# today window
out = run("--mode", "summary", "--days", "1", "--day-offset", "0", "--format", "json")
data = json.loads(out.stdout)
assert data["meta"]["accounting_mode"].startswith("approximate"), data["meta"]
assert data["meta"]["period_start"] == today_s and data["meta"]["period_end"] == today_s
tags = {r["tag"] for r in data["rows"]}
assert "alice" in tags and "bob" in tags and "carol" not in tags, tags

# yesterday window
out = run("--mode", "summary", "--days", "1", "--day-offset", "1", "--format", "json")
data = json.loads(out.stdout)
assert data["meta"]["period_start"] == yday_s
tags = {r["tag"] for r in data["rows"]}
assert "carol" in tags and "bob" not in tags, tags

# department current attribution (alice+carol Engineering)
out = run("--mode", "department", "--department", "Engineering", "--days", "30", "--format", "json")
data = json.loads(out.stdout)
tags = {r["tag"] for r in data["rows"]}
assert tags == {"alice", "carol"}, tags
assert all(r["department"] == "Engineering" for r in data["rows"])

# host + IP-only label
out = run("--mode", "top_hosts", "--days", "30", "--format", "json")
data = json.loads(out.stdout)
labels = {r["host_label"] for r in data["rows"]}
assert any(l.startswith("[IP only]") for l in labels), labels
assert "github.com" in {r["destination_host"] for r in data["rows"]}

out = run("--mode", "host", "--host", "GitHub.COM.", "--days", "30", "--format", "json")
data = json.loads(out.stdout)
assert sum(r["total_bytes"] for r in data["rows"]) == 100 + 1000 + 200 + 2000

# top users
out = run("--mode", "top_users", "--days", "30", "--limit", "10", "--format", "json")
data = json.loads(out.stdout)
assert data["rows"][0]["total_bytes"] >= data["rows"][-1]["total_bytes"]
assert data["meta"]["accounting_mode"]

# csv raw integers
csv_path = base / "out.csv"
run("--mode", "summary", "--days", "30", "--format", "csv", "--csv-file", str(csv_path))
text = csv_path.read_text(encoding="utf-8")
assert "upload_bytes" in text and "18.4" not in text and "GiB" not in text
assert "100" in text or "1050" in text
mode = oct(csv_path.stat().st_mode & 0o777)
assert mode == "0o600", mode

# json accounting_mode
out = run("--mode", "summary", "--days", "1", "--format", "json")
assert "approximate" in json.loads(out.stdout)["meta"]["accounting_mode"]

# 100k rows performance
conn = sqlite3.connect(db)
batch = []
for i in range(100_000):
    batch.append((
        today_s,
        f"u-{i % 500}",
        f"user{i % 500}",
        f"host{i}.example",
        i % 100,
        (i % 100) * 10,
        1,
    ))
t0 = time.perf_counter()
conn.executemany(
    "INSERT INTO daily_usage(date,user_id,user_tag,destination_host,upload_bytes,download_bytes,connection_count) VALUES (?,?,?,?,?,?,?)",
    batch,
)
conn.commit()
conn.close()
t1 = time.perf_counter()
out = run("--mode", "top_users", "--days", "1", "--limit", "20", "--format", "json")
t2 = time.perf_counter()
data = json.loads(out.stdout)
assert len(data["rows"]) <= 20
assert sum(r["total_bytes"] for r in data["rows"]) > 0
assert (t2 - t1) < 30.0, f"top_users took {t2 - t1:.2f}s (insert {t1 - t0:.2f}s)"
print("stats-ok")
PY
  stats_rc=$?
  if (( stats_rc == 0 )); then
    pass "vincula-stats today/yesterday/dept/host/top/csv/json/100k"
  else
    fail "vincula-stats today/yesterday/dept/host/top/csv/json/100k"
  fi
fi

if [[ "${VCL_INTEGRATION:-0}" == "1" ]]; then
  arch=$(map_arch "$(uname -m)") || {
    fail "integration test architecture unsupported"
    exit 1
  }
  integration_dir="${TEST_TMP}/integration"
  mkdir -p "$integration_dir"
  integration_binary=$(download_sing_box "$arch" "$integration_dir")
  assert_equal "downloaded binary reports pinned version" "$SING_BOX_VERSION" \
    "$("$integration_binary" version | awk 'NR==1 {print $3}')"
  assert_success "official sing-box validates generated config" \
    "$integration_binary" check -c "${TEST_TMP}/config.json"
  assert_success "official sing-box validates accounting config" \
    "$integration_binary" check -c "${TEST_TMP}/acct-config.json"

  generated_keypair=$("$integration_binary" generate reality-keypair)
  generated_private=$(parse_private_key "$generated_keypair")
  generated_public=$(parse_public_key "$generated_keypair")
  if [[ "$generated_private" =~ ^[A-Za-z0-9_-]{43,44}$ && "$generated_public" =~ ^[A-Za-z0-9_-]{43,44}$ ]]; then
    pass "official sing-box keypair output matches parser"
  else
    fail "official sing-box keypair output matches parser"
  fi
  generated_uuid=$("$integration_binary" generate uuid)
  generated_sid=$("$integration_binary" generate rand --hex 8)
  if run_reality_self_test "$integration_binary" "$generated_uuid" "$generated_private" "$generated_public" "$generated_sid" www.cloudflare.com; then
    pass "REALITY end-to-end self-test against Cloudflare"
  else
    fail "REALITY end-to-end self-test against Cloudflare"
  fi
fi
