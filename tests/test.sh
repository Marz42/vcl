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
assert_equal "runs when read from standard input" "vincula 0.2.9-dev" \
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
assert_success "migrates from 0.2.6" is_supported_upgrade_from 0.2.6
assert_success "migrates from 0.2.7" is_supported_upgrade_from 0.2.7
assert_success "migrates from 0.2.8" is_supported_upgrade_from 0.2.8
assert_failure "does not migrate the current version" is_supported_upgrade_from 0.2.9-dev
assert_failure "does not migrate 0.3.0" is_supported_upgrade_from 0.3.0

assert_equal "D18 730 from 0.2.6 becomes 90" "90" "$(migrate_legacy_daily_retention 0.2.6 730)"
assert_equal "D18 730 from 0.2.5 becomes 90" "90" "$(migrate_legacy_daily_retention 0.2.5 730)"
assert_equal "D18 custom 365 preserved" "365" "$(migrate_legacy_daily_retention 0.2.6 365)"
assert_equal "D18 custom 180 preserved" "180" "$(migrate_legacy_daily_retention 0.2.4 180)"
assert_equal "D18 custom 30 preserved" "30" "$(migrate_legacy_daily_retention 0.1.5 30)"
assert_equal "D18 already 90 stays 90" "90" "$(migrate_legacy_daily_retention 0.2.6 90)"
assert_equal "D18 730 from 0.2.8 is preserved" "730" "$(migrate_legacy_daily_retention 0.2.8 730)"
d18_err=$(migrate_legacy_daily_retention 0.2.6 730 2>&1 >/dev/null)
assert_success "D18 730 logs migration message" \
  grep -q 'Migrated legacy default daily retention 730 → 90.' <<< "$d18_err"
assert_success "migrate reads daily retention from settings" \
  grep -q 'toml_get "$SETTINGS_FILE" accounting_daily_retention_days' "${PROJECT_DIR}/vincula.sh"

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
readonly TEST_INSTANCE_ID="7aa07b21-2222-4222-8222-222222222222"
render_sing_box_config "${TEST_TMP}/config.json" "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_SHORT_ID" 443 www.cloudflare.com
render_state "${TEST_TMP}/state.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 false false 0 0 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node "$TEST_INSTANCE_ID"
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
assert_equal "state.json schema_version is 2" "2" "$(json_numeric_field "${TEST_TMP}/state.json" schema_version)"
assert_equal "state includes instance_id UUID" "$TEST_INSTANCE_ID" "$(json_quoted_field "${TEST_TMP}/state.json" instance_id)"
assert_failure "state does not keep owner.uuid as SoT" grep -q '"owner"' "${TEST_TMP}/state.json"
assert_success "settings include node_id UUID" grep -q "^node_id = \"${TEST_NODE_ID}\"\$" "${TEST_TMP}/config.toml"
assert_failure "settings do not hardcode local node_id" grep -q '^node_id = "local"$' "${TEST_TMP}/config.toml"
assert_failure "settings do not store instance_id" \
  grep -q '^instance_id' "${TEST_TMP}/config.toml"
assert_equal "preserves existing instance_id" "$TEST_INSTANCE_ID" \
  "$(mint_or_preserve_instance_id "$TEST_INSTANCE_ID" "$TEST_NODE_ID")"
fresh=$(mint_or_preserve_instance_id "" "$TEST_NODE_ID")
assert_success "fresh instance_id is UUID" \
  python3 -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", sys.argv[1]) else 1)' "$fresh"
assert_failure "fresh instance_id is not node_id" test "$fresh" = "$TEST_NODE_ID"
copied=$(mint_or_preserve_instance_id "$TEST_NODE_ID" "$TEST_NODE_ID")
assert_failure "refuses node_id copy as instance_id" test "$copied" = "$TEST_NODE_ID"
assert_success "copied-path mint is UUID" \
  python3 -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", sys.argv[1]) else 1)' "$copied"
assert_equal "re-run does not remint instance_id" "$fresh" \
  "$(mint_or_preserve_instance_id "$fresh" "$TEST_NODE_ID")"
python3 - "${TEST_TMP}/state-schema1.json" "$TEST_NODE_ID" <<'PY'
import json, sys
path, node_id = sys.argv[1], sys.argv[2]
json.dump({
    "schema_version": 1,
    "project_version": "0.2.7",
    "node": {
        "node_id": node_id,
        "node_name": "test-node",
        "server": "203.0.113.10",
        "port": 443,
    },
}, open(path, "w", encoding="utf-8"), indent=2)
open(path, "a", encoding="utf-8").write("\n")
PY
schema1_existing=$(json_quoted_field "${TEST_TMP}/state-schema1.json" instance_id || true)
assert_equal "schema 1 state has no instance_id" "" "$schema1_existing"
assert_equal "schema 1 migrate keeps node_id" "$TEST_NODE_ID" \
  "$(json_quoted_field "${TEST_TMP}/state-schema1.json" node_id)"
schema1_mint=$(mint_or_preserve_instance_id "$schema1_existing" "$TEST_NODE_ID")
assert_success "schema 1 migrate mints instance_id UUID" \
  python3 -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", sys.argv[1]) else 1)' "$schema1_mint"
assert_failure "schema 1 migrate does not copy node_id" test "$schema1_mint" = "$TEST_NODE_ID"
assert_equal "schema 1 migrate remint is idempotent" "$schema1_mint" \
  "$(mint_or_preserve_instance_id "$schema1_mint" "$TEST_NODE_ID")"
render_state "${TEST_TMP}/state-schema1-migrated.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 false false 0 0 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node "$schema1_mint"
assert_equal "schema 1 migrate writes schema 2" "2" \
  "$(json_numeric_field "${TEST_TMP}/state-schema1-migrated.json" schema_version)"
assert_equal "schema 1 migrate preserves node_id in schema 2" "$TEST_NODE_ID" \
  "$(json_quoted_field "${TEST_TMP}/state-schema1-migrated.json" node_id)"
assert_equal "schema 1 migrate writes minted instance_id" "$schema1_mint" \
  "$(json_quoted_field "${TEST_TMP}/state-schema1-migrated.json" instance_id)"
render_state "${TEST_TMP}/state-fresh-mint.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 false false 0 0 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node
fresh_state_iid=$(json_quoted_field "${TEST_TMP}/state-fresh-mint.json" instance_id)
assert_success "fresh render_state instance_id is UUID" \
  python3 -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", sys.argv[1]) else 1)' "$fresh_state_iid"
assert_failure "fresh render_state instance_id is not node_id" test "$fresh_state_iid" = "$TEST_NODE_ID"
assert_equal "fresh render_state keeps node_id" "$TEST_NODE_ID" \
  "$(json_quoted_field "${TEST_TMP}/state-fresh-mint.json" node_id)"
assert_equal "fresh render_state writes schema 2" "2" \
  "$(json_numeric_field "${TEST_TMP}/state-fresh-mint.json" schema_version)"
install_mint_src=$(awk '/^install_new_node\(\)/,/^main\(\)/ {print}' "${PROJECT_DIR}/vincula.sh")
migrate_mint_src=$(awk '/^migrate_existing_install\(\)/,/^verify_existing_install\(\)/ {print}' "${PROJECT_DIR}/vincula.sh")
verify_mint_src=$(awk '/^verify_existing_install\(\)/,/^handle_existing_install\(\)/ {print}' "${PROJECT_DIR}/vincula.sh")
if [[ "$install_mint_src" == *'mint_or_preserve_instance_id'* ]]; then
  pass "install_new_node mints instance_id"
else
  fail "install_new_node mints instance_id"
fi
if [[ "$migrate_mint_src" == *'mint_or_preserve_instance_id'* ]]; then
  pass "migrate_existing_install mints instance_id when missing"
else
  fail "migrate_existing_install mints instance_id when missing"
fi
if [[ "$verify_mint_src" == *'mint_or_preserve_instance_id'* ]]; then
  fail "verify_existing_install does not remint instance_id (unexpected mint)"
else
  pass "verify_existing_install does not remint instance_id"
fi
assert_success "self-test server binds localhost only" grep -q '"listen": "127.0.0.1"' "${TEST_TMP}/selftest-server.json"
assert_success "self-test client exposes localhost SOCKS" grep -q '"type": "socks"' "${TEST_TMP}/selftest-client.json"
assert_success "renders syntactically valid helper" bash -n "${TEST_TMP}/vincula"
assert_success "renders expected service user" grep -q '^User=sing-box$' "${TEST_TMP}/sing-box.service"
assert_success "renders low-port capability" grep -q '^AmbientCapabilities=CAP_NET_BIND_SERVICE$' "${TEST_TMP}/sing-box.service"
assert_success "keeps management state private by design" grep -q '^project_version = "0.2.9-dev"$' "${TEST_TMP}/config.toml"
assert_success "render_settings snapshot has daily retention 90" \
  grep -q '^accounting_daily_retention_days = 90$' "${TEST_TMP}/config.toml"
render_settings "${TEST_TMP}/settings-ret-default.toml" 203.0.113.10 443 www.cloudflare.com amd64 9090 test-secret
assert_success "render_settings default daily retention is 90" \
  grep -q '^accounting_daily_retention_days = 90$' "${TEST_TMP}/settings-ret-default.toml"
assert_success "render_settings default raw retention is 90" \
  grep -q '^accounting_raw_retention_days = 90$' "${TEST_TMP}/settings-ret-default.toml"
assert_success "render_settings snapshot has billing_cycle_start_day 1" \
  grep -q '^billing_cycle_start_day = 1$' "${TEST_TMP}/config.toml"
assert_success "render_settings default billing_cycle_start_day is 1" \
  grep -q '^billing_cycle_start_day = 1$' "${TEST_TMP}/settings-ret-default.toml"
render_settings "${TEST_TMP}/settings-cycle.toml" 203.0.113.10 443 www.cloudflare.com amd64 9090 test-secret 90 90 "$TEST_NODE_ID" test-node 5
assert_success "render_settings honors explicit billing_cycle_start_day" \
  grep -q '^billing_cycle_start_day = 5$' "${TEST_TMP}/settings-cycle.toml"
assert_success "migrate reads existing billing_cycle_start_day" \
  grep -q 'toml_get "$SETTINGS_FILE" billing_cycle_start_day' "${PROJECT_DIR}/vincula.sh"
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
assert_success "helper documents vcl identity" grep -q 'vcl identity' "${PROJECT_DIR}/bin/vincula"
assert_failure "node helper usage has no fleet" \
  grep -q 'vcl fleet' "${PROJECT_DIR}/bin/vincula"
identity_src=$(awk '/^cmd_identity\(\)/,/^cmd_status\(\)/ {print}' "${PROJECT_DIR}/bin/vincula")
if [[ "$identity_src" == *'json_quoted_field "$STATE_FILE" instance_id'* ]]; then
  pass "cmd_identity reads instance_id from state.json"
else
  fail "cmd_identity reads instance_id from state.json"
fi
main_src=$(awk '/^main\(\)/ {p=1} p' "${PROJECT_DIR}/bin/vincula")
if printf '%s\n' "$main_src" | grep -A12 '^        status)' | grep -q -- '--json'; then
  pass "status accepts --json in dispatch"
else
  fail "status accepts --json in dispatch"
fi
if printf '%s\n' "$main_src" | grep -A12 '^        verify)' | grep -q -- '--json'; then
  pass "verify accepts --json in dispatch"
else
  fail "verify accepts --json in dispatch"
fi
if printf '%s\n' "$main_src" | grep -A12 '^        identity)' | grep -q -- '--json'; then
  pass "identity accepts --json in dispatch"
else
  fail "identity accepts --json in dispatch"
fi
assert_success "identity-sample.json is valid JSON" \
  python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' \
  "${PROJECT_DIR}/tests/fixtures/identity-sample.json"
ident_json_rc=0
ident_json_out=$(python3 - "${TEST_TMP}/state.json" "${PROJECT_DIR}/tests/fixtures/identity-sample.json" "$TEST_NODE_ID" "$TEST_INSTANCE_ID" "$VINCULA_VERSION" <<'PY'
import json, sys
state_path, sample_path, node_id, instance_id, version = sys.argv[1:6]
state = json.load(open(state_path, encoding="utf-8"))
sample = json.load(open(sample_path, encoding="utf-8"))
ident_keys = ["schema_version", "vincula_version", "node_id", "instance_id", "node_name", "utc_now"]
status_keys = ["ok", "proxy", "accounting"]
status_proxy = ["ok", "sing_box_active", "port_listening", "port_owned"]
status_acct = ["ok", "service_active", "heartbeat", "heartbeat_age_seconds"]
verify_keys = ["ok", "identity", "proxy", "accounting", "utc_now"]
rows = []

def record(name, ok, detail=""):
    rows.append(("PASS" if ok else "FAIL", name, detail))

record("state.json schema_version is 2 for identity assembly", state.get("schema_version") == 2, str(state.get("schema_version")))
node = state.get("node") or {}
record("assembled node_id is UUID", node.get("node_id") == node_id, str(node.get("node_id")))
record("assembled instance_id is UUID", node.get("instance_id") == instance_id, str(node.get("instance_id")))
record("assembled instance_id is not node_id", node.get("instance_id") != node.get("node_id"), "")
assembled = {
    "schema_version": 1,
    "vincula_version": version,
    "node_id": node.get("node_id"),
    "instance_id": node.get("instance_id"),
    "node_name": node.get("node_name"),
    "utc_now": "2026-08-16T00:00:00Z",
}
record("identity JSON assembly has frozen keys", list(assembled) == ident_keys, ",".join(assembled))
record("identity JSON schema_version is contract 1", assembled["schema_version"] == 1, "")
record("identity-sample.json has frozen keys", list(sample) == ident_keys, ",".join(sample))
record("identity-sample.json schema_version is 1", sample.get("schema_version") == 1, str(sample.get("schema_version")))
record("identity-sample.json instance_id is not node_id", sample.get("instance_id") != sample.get("node_id"), "")
record("identity-sample.json node_name is lax", sample.get("node_name") == "lax", str(sample.get("node_name")))
record("identity-sample.json vincula_version matches tree", sample.get("vincula_version") == version, str(sample.get("vincula_version")))

status_doc = {
    "ok": True,
    "proxy": {
        "ok": True,
        "sing_box_active": True,
        "port_listening": True,
        "port_owned": True,
    },
    "accounting": {
        "ok": True,
        "service_active": True,
        "heartbeat": "fresh",
        "heartbeat_age_seconds": 12,
    },
}
record("status --json top-level keys", list(status_doc) == status_keys, ",".join(status_doc))
record("status --json proxy keys", list(status_doc["proxy"]) == status_proxy, ",".join(status_doc["proxy"]))
record("status --json accounting keys", list(status_doc["accounting"]) == status_acct, ",".join(status_doc["accounting"]))
record(
    "status --json heartbeat enum includes fresh",
    status_doc["accounting"]["heartbeat"] in ("fresh", "stale", "missing", "unreadable"),
    status_doc["accounting"]["heartbeat"],
)

verify_doc = {
    "ok": True,
    "identity": {"ok": True, "node_id": node_id, "instance_id": instance_id},
    "proxy": {"ok": True},
    "accounting": {"ok": True, "checks": [{"name": "heartbeat", "ok": True, "detail": "fresh"}]},
    "utc_now": "2026-08-16T00:00:00Z",
}
record("verify --json top-level keys", list(verify_doc) == verify_keys, ",".join(verify_doc))
record("verify --json identity keys", list(verify_doc["identity"]) == ["ok", "node_id", "instance_id"], "")
record("verify --json proxy keys", list(verify_doc["proxy"]) == ["ok"], "")
record("verify --json accounting has checks array", isinstance(verify_doc["accounting"]["checks"], list), "")
check = verify_doc["accounting"]["checks"][0]
record("verify --json check keys", list(check) == ["name", "ok", "detail"], ",".join(check))

for status, name, detail in rows:
    print(f"{status}\t{name}\t{detail}")
sys.exit(0 if all(s == "PASS" for s, _, _ in rows) else 1)
PY
) || ident_json_rc=$?
if [[ -z "$ident_json_out" ]]; then
  fail "identity/status/verify JSON contract fixtures produced output"
else
  while IFS=$'\t' read -r ident_status ident_name ident_detail; do
    [[ -n "$ident_status" ]] || continue
    if [[ "$ident_status" == "PASS" ]]; then
      pass "$ident_name"
    else
      fail "${ident_name} (${ident_detail})"
    fi
  done <<< "$ident_json_out"
fi
if (( ident_json_rc != 0 )) && [[ -z "$ident_json_out" ]]; then
  fail "identity/status/verify JSON contract python exited ${ident_json_rc}"
fi
status_src=$(awk '/^cmd_status\(\)/,/^cmd_check\(\)/ {print}' "${PROJECT_DIR}/bin/vincula")
if [[ "$status_src" == *'sing_box_active'* && "$status_src" == *'heartbeat_age_seconds'* && "$status_src" == *'accounting_last_success_status'* ]]; then
  pass "cmd_status --json emits proxy and accounting heartbeat keys"
else
  fail "cmd_status --json emits proxy and accounting heartbeat keys"
fi
verify_json_src=$(awk '/^cmd_verify_json\(\)/,/^cmd_verify_accounting_plane\(\)/ {print}' "${PROJECT_DIR}/bin/vincula")
if [[ "$verify_json_src" == *'"checks"'* && "$verify_json_src" == *'utc_now'* && "$verify_json_src" == *'accounting_plane_checks'* ]]; then
  pass "cmd_verify --json emits identity proxy accounting checks"
else
  fail "cmd_verify --json emits identity proxy accounting checks"
fi
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

render_state "${TEST_TMP}/state-created.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 true true 0 0 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node "$TEST_INSTANCE_ID"
assert_equal "persists Vincula-created service account" "true" \
  "$(json_bool_field "${TEST_TMP}/state-created.json" created_by_vincula)"
assert_equal "persists Vincula-created service group" "true" \
  "$(json_bool_field "${TEST_TMP}/state-created.json" group_created_by_vincula)"
render_state "${TEST_TMP}/state-reused.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 false false 0 0 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node "$TEST_INSTANCE_ID"
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
assert_success "helper documents vcl accounting check" grep -q 'vcl accounting check' "${TEST_TMP}/vincula"
assert_success "helper documents vcl audit user" grep -q 'vcl audit user TAG' "${TEST_TMP}/vincula"
assert_success "helper documents vcl audit --user-id" grep -q 'vcl audit --user-id UUID' "${TEST_TMP}/vincula"
assert_failure "accounting status does not prefer JSONL ingest" \
  grep -q 'non-empty events.jsonl' "${PROJECT_DIR}/bin/vincula"
assert_success "accounting status is Clash poll only" \
  grep -q 'Clash API poll only' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents stats month" grep -q 'vcl stats today|yesterday|--days N|--month' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents stats top" grep -q 'vcl stats top users|departments|hosts' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents stats host" grep -q 'vcl stats host' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents accounting retention" grep -q 'vcl accounting retention' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents accounting check" grep -q 'vcl accounting check' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents accounting cycle" grep -q 'vcl accounting cycle' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents accounting cycle --set" grep -q 'vcl accounting cycle --set N' "${PROJECT_DIR}/bin/vincula"
assert_success "helper documents stats --date" grep -q 'vcl stats --date YYYY-MM-DD' "${PROJECT_DIR}/bin/vincula"
assert_success "helper routes audit command" grep -q 'audit) cmd_audit' "${PROJECT_DIR}/bin/vincula"
assert_success "helper defines resolve_audit_py" grep -q '^resolve_audit_py()' "${PROJECT_DIR}/bin/vincula"
if bash "${PROJECT_DIR}/bin/vincula" help | grep -q 'vcl audit user'; then
  pass "vcl help lists audit"
else
  fail "vcl help lists audit"
fi
if bash "${PROJECT_DIR}/bin/vincula" help | grep -q 'vcl accounting check'; then
  pass "vcl help lists accounting check"
else
  fail "vcl help lists accounting check"
fi
assert_success "stats --month help mentions billing cycle start" \
  grep -q '从账期起始日(默认每月1日)到今天' "${PROJECT_DIR}/bin/vincula"
assert_success "connections fail when accountd inactive" \
  grep -q 'UNAVAILABLE: vincula-accountd' "${PROJECT_DIR}/bin/vincula"
assert_success "gen-release-lock includes vincula-stats.py" \
  grep -q 'lib/vincula-stats.py' "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_success "gen-release-lock includes vincula-audit.py" \
  grep -q 'lib/vincula-audit.py' "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_success "gen-release-lock includes vincula-bootstrap.sh" \
  grep -q 'vincula-bootstrap.sh' "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_success "release.lock includes vincula-bootstrap.sh" \
  grep -q 'vincula-bootstrap.sh' "${PROJECT_DIR}/release.lock"
assert_success "release.lock includes vincula-audit.py" \
  grep -q 'lib/vincula-audit.py' "${PROJECT_DIR}/release.lock"
assert_failure "release.lock does not include event schema" \
  grep -q 'vincula-event.schema.json' "${PROJECT_DIR}/release.lock"
assert_equal "release.lock has 8 first-party files" "8" \
  "$(wc -l < "${PROJECT_DIR}/release.lock" | tr -d ' ')"
assert_failure "release.lock does not include vincula-fleet.py" \
  grep -q 'vincula-fleet' "${PROJECT_DIR}/release.lock"
assert_failure "gen-release-lock does not include vincula-fleet.py" \
  grep -q 'vincula-fleet' "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_success "verify_sibling_release_lock warns when lock is missing" \
  grep -q 'release.lock not found beside installer' "${PROJECT_DIR}/vincula.sh"
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
assert_success "build-release includes vincula-audit.py" \
  grep -q 'lib/vincula-audit.py' "${PROJECT_DIR}/scripts/build-release.sh"
assert_success "python3 can compile vincula-stats" \
  python3 -m py_compile "${PROJECT_DIR}/lib/vincula-stats.py"
assert_success "python3 can compile vincula-audit" \
  python3 -m py_compile "${PROJECT_DIR}/lib/vincula-audit.py"
assert_failure "audit module does not import accountd" \
  grep -q 'vincula-accountd' "${PROJECT_DIR}/lib/vincula-audit.py"
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

render_state "${TEST_TMP}/state-identity.json" 203.0.113.10 443 www.cloudflare.com "$TEST_UUID" "$TEST_PRIVATE_KEY" "$TEST_PUBLIC_KEY" "$TEST_SHORT_ID" 2026-08-12T00:00:00Z amd64 true true 995 995 /var/lib/sing-box /usr/sbin/nologin "$TEST_NODE_ID" test-node "$TEST_INSTANCE_ID"
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
assert_success "accountd unit version stamp is 0.2.9-dev" \
  grep -q 'Vincula-Version: 0.2.9-dev' "${PROJECT_DIR}/lib/vincula-accountd.service"
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
assert_failure "event schema file is not shipped" \
  test -f "${PROJECT_DIR}/lib/vincula-event.schema.json"
assert_failure "gen-release-lock does not include event schema" \
  grep -q 'vincula-event.schema.json' "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_failure "build-release does not include event schema" \
  grep -q 'vincula-event.schema.json' "${PROJECT_DIR}/scripts/build-release.sh"
assert_failure "accountd has no JSONL ingest path" \
  grep -Eiq 'jsonl|ingest-file|EVENTS_JSONL' "${PROJECT_DIR}/lib/vincula-accountd.py"
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
assert_failure "install.manifest does not list events.jsonl" \
  grep -q 'events.jsonl' "${TEST_TMP}/install.manifest"
assert_failure "install.manifest does not list event schema" \
  grep -q 'vincula-event.schema.json' "${TEST_TMP}/install.manifest"
assert_success "helper uninstall mentions historical accounting data" \
  grep -q 'Historical accounting data' "${TEST_TMP}/vincula"
assert_success "bootstrap script exists" \
  test -f "${PROJECT_DIR}/vincula-bootstrap.sh"
assert_success "gen-release-lock script exists" \
  test -f "${PROJECT_DIR}/scripts/gen-release-lock.sh"
assert_success "build-release script exists" \
  test -f "${PROJECT_DIR}/scripts/build-release.sh"
assert_success "build-controller script exists" \
  test -f "${PROJECT_DIR}/scripts/build-controller.sh"
assert_success "build-release produces verified dist package" \
  bash "${PROJECT_DIR}/scripts/build-release.sh" >/dev/null
assert_success "dist tree contains release.lock" \
  test -f "${PROJECT_DIR}/dist/vincula-node-${VINCULA_VERSION}/release.lock"
assert_success "dist archive exists" \
  test -f "${PROJECT_DIR}/dist/vincula-node-${VINCULA_VERSION}.tar.gz"
assert_failure "legacy dist archive name is unused" \
  test -f "${PROJECT_DIR}/dist/vincula-${VINCULA_VERSION}.tar.gz"
assert_equal "dist node release.lock has 8 first-party files" "8" \
  "$(wc -l < "${PROJECT_DIR}/dist/vincula-node-${VINCULA_VERSION}/release.lock" | tr -d ' ')"
assert_failure "node release.lock does not include vincula-fleet.py" \
  grep -q 'vincula-fleet' "${PROJECT_DIR}/dist/vincula-node-${VINCULA_VERSION}/release.lock"
node_listing=$(tar -tzf "${PROJECT_DIR}/dist/vincula-node-${VINCULA_VERSION}.tar.gz")
assert_failure "node tarball does not contain vincula-fleet.py" \
  grep -q 'vincula-fleet.py' <<< "$node_listing"
assert_success "build-controller produces zip" \
  bash "${PROJECT_DIR}/scripts/build-controller.sh" >/dev/null
assert_success "controller zip exists" \
  test -f "${PROJECT_DIR}/dist/vincula-controller-${VINCULA_VERSION}.zip"
controller_zip_rc=0
python3 - "${PROJECT_DIR}/dist/vincula-controller-${VINCULA_VERSION}.zip" "${VINCULA_VERSION}" <<'PY' || controller_zip_rc=$?
import sys
import zipfile

archive, version = sys.argv[1], sys.argv[2]
prefix = f"vincula-controller-{version}"
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
assert not missing, missing
for name in names:
    base = name.rstrip("/").rsplit("/", 1)[-1]
    assert base not in forbidden, name
PY
if (( controller_zip_rc == 0 )); then
  pass "AC-2.8-11 controller zip members"
else
  fail "AC-2.8-11 controller zip members"
fi
assert_success "README mentions vincula-node artifact" \
  grep -q 'vincula-node-' "${PROJECT_DIR}/README.md"
assert_success "README mentions vincula-controller artifact" \
  grep -q 'vincula-controller-' "${PROJECT_DIR}/README.md"

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
assert_success "install.manifest lists vincula-audit.py" \
  grep -q 'vincula-audit.py' "${TEST_TMP}/install.manifest"
assert_success "install.manifest lists vincula-accountd.service" \
  grep -q 'vincula-accountd.service' "${TEST_TMP}/install.manifest"

# Sample connection write without root (needs users.json for tag→user_id)
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
sample_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$SAMPLE_DB" "$SAMPLE_USERS" <<'PY' || sample_rc=$?
import importlib.util, sys

mod_path, db, users = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users)
conn = mod.open_db(db)
mod.upsert_connection(conn, {
    "connection_id": "c-test-1",
    "node_id": "6fc96a10-1111-4111-8111-111111111111",
    "user_id": "u-alice",
    "user_tag": "alice",
    "destination_host": mod.normalize_destination_host("Example.COM."),
    "destination_ip": "203.0.113.10",
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 100,
    "download_bytes": 2000,
    "started_at": "2026-08-14T06:00:00Z",
    "closed_at": "2026-08-14T06:01:00Z",
    "ts": "2026-08-14T06:01:00Z",
}, close=True)
conn.commit()
conn.close()
PY
if (( sample_rc == 0 )); then
  pass "accountd upserts sample connection"
else
  fail "accountd upserts sample connection"
fi
assert_success "ingested connection row has user_id" \
  python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); n=c.execute("select count(*) from connections where user_id=\"u-alice\"").fetchone()[0]; raise SystemExit(0 if n>=1 else 1)' "$SAMPLE_DB"
assert_success "meta.schema_version is 3" \
  python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); v=c.execute("select value from meta where key=\"schema_version\"").fetchone()[0]; raise SystemExit(0 if v=="3" else 1)' "$SAMPLE_DB"
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

conn = mod.open_db(db)
assert mod.meta_get(conn, "schema_version") == "3"
mod.upsert_connection(conn, {
    "event": "connection_close",
    "connection_id": "r1",
    "node_id": "n1",
    "user_id": "u-bob",
    "user_tag": "bob",
    "destination_host": "cdn.example",
    "destination_ip": "198.51.100.2",
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 50,
    "download_bytes": 500,
    "started_at": "2026-08-14T10:00:00Z",
    "closed_at": "2026-08-14T10:05:00Z",
    "ts": "2026-08-14T10:05:00Z",
}, close=True)
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

# Restart: empty known_open, existing DB row with accounted bytes, still live in Clash
mod.upsert_connection(conn, {
    "connection_id": "p-restart",
    "node_id": "n1",
    "user_id": "u-alice",
    "user_tag": "alice",
    "destination_host": "r.example",
    "destination_ip": None,
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 5000,
    "download_bytes": 8000,
    "started_at": "2026-08-14T11:00:00Z",
    "ts": "2026-08-14T11:00:10Z",
}, close=False, accounted_upload=5000, accounted_download=8000)
known_restart = {}
live_restart = [dict(live1[0], connection_id="p-restart",
                     upload_bytes=9000, download_bytes=12000,
                     ts="2026-08-14T11:05:00Z")]
known_restart = mod.apply_poll_delta(conn, live_restart, known_restart)
row = conn.execute(
    "SELECT upload_bytes, download_bytes, closed_at FROM connections WHERE connection_id='p-restart'"
).fetchone()
assert row[0] == 5000 and row[1] == 8000, row   # NOT zeroed
assert row[2] is None, row
# subsequent poll: monotonic delta from new baseline 9000/12000
live_restart2 = [dict(live_restart[0], upload_bytes=9500, download_bytes=12100)]
known_restart = mod.apply_poll_delta(conn, live_restart2, known_restart)
row = conn.execute(
    "SELECT upload_bytes, download_bytes FROM connections WHERE connection_id='p-restart'"
).fetchone()
assert row[0] == 5500 and row[1] == 8100, row

# AC-2.7-02: empty known_open, DB absent, large Clash counters → baseline only
known_unknown = {}
live_unknown = [dict(live1[0], connection_id="p-unknown",
                     upload_bytes=999999, download_bytes=888888,
                     ts="2026-08-14T11:06:00Z")]
known_unknown = mod.apply_poll_delta(conn, live_unknown, known_unknown)
row = conn.execute(
    "SELECT upload_bytes, download_bytes FROM connections WHERE connection_id='p-unknown'"
).fetchone()
assert row[0] == 0 and row[1] == 0, row

# Closed generation must not be reopened by later first sight (D6/D8):
# old row stays closed with preserved bytes; a new generation is baseline-only.
conn.execute(
    "UPDATE connections SET closed_at = ? WHERE connection_id = 'p-restart'",
    ("2026-08-14T11:05:30Z",),
)
known_reopen = {}
known_reopen = mod.apply_poll_delta(conn, live_restart2, known_reopen)
rows = conn.execute(
    "SELECT generation, upload_bytes, download_bytes, closed_at FROM connections "
    "WHERE connection_id='p-restart' ORDER BY generation"
).fetchall()
assert len(rows) == 2, rows
assert rows[0][0] == 0 and rows[0][1] == 5500 and rows[0][2] == 8100, rows
assert rows[0][3] is not None, rows
assert rows[1][0] == 1 and rows[1][1] == 0 and rows[1][2] == 0, rows
assert rows[1][3] is None, rows

# live set: keep still-alive open rows; close only ids absent from Clash
mod.upsert_connection(conn, {
    "connection_id": "p-stale-live",
    "node_id": "n1",
    "user_id": "u-alice",
    "user_tag": "alice",
    "destination_host": "s.example",
    "destination_ip": None,
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 11,
    "download_bytes": 22,
    "started_at": "2026-08-14T11:00:00Z",
    "ts": "2026-08-14T11:00:10Z",
}, close=False, accounted_upload=11, accounted_download=22)
n_live = mod.close_stale_open_connections(
    conn, ["p-restart", "p1", "p-unknown"], now="2026-08-14T11:07:00Z"
)
assert n_live == 1, n_live
row = conn.execute(
    "SELECT closed_at FROM connections "
    "WHERE connection_id='p-restart' AND closed_at IS NULL"
).fetchone()
assert row is not None and row[0] is None, row
row = conn.execute(
    "SELECT closed_at, upload_bytes FROM connections WHERE connection_id='p-stale-live'"
).fetchone()
assert row[0] == "2026-08-14T11:07:00Z" and row[1] == 11, row

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
  pass "event parse + rollup + stale close + poll baseline + restart bytes preserved"
else
  fail "event parse + rollup + stale close + poll baseline + restart bytes preserved"
fi

# Schema 2 → 3 migration: preserve accounted bytes, assign event_id / generation=0,
# leave instance_id NULL, do not seed poll_baseline from unknown Clash counters.
schema3_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/schema2to3.db" "${TEST_TMP}/schema3-empty.db" <<'PY' || schema3_rc=$?
import importlib.util, pathlib, re, sqlite3, sys

mod_path, old_db, empty_db = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert mod.SCHEMA_VERSION == 3
src = pathlib.Path(mod_path).read_text(encoding="utf-8")
for i, line in enumerate(src.splitlines(), 1):
    code = line.split("#", 1)[0]
    if re.search(r"instance_id\s*=\s*.*node_id", code):
        raise AssertionError(f"D5: instance_id assigned from node_id at {i}: {line}")

raw = sqlite3.connect(old_db)
raw.executescript("""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE connections (
  connection_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  destination_host TEXT,
  destination_ip TEXT,
  destination_port INTEGER,
  network TEXT,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  closed_at TEXT,
  last_seen_at TEXT NOT NULL
);
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
raw.execute("INSERT INTO meta(key,value) VALUES('schema_version','2')")
raw.execute(
    """
    INSERT INTO connections(
      connection_id, node_id, user_id, user_tag, destination_host, destination_ip,
      destination_port, network, upload_bytes, download_bytes,
      started_at, closed_at, last_seen_at
    ) VALUES (?, 'n1', 'u-alice', 'alice', 'open.example', NULL, 443, 'tcp',
              12345, 67890, '2026-08-14T10:00:00Z', NULL, '2026-08-14T10:05:00Z')
    """,
    ("c-open",),
)
raw.execute(
    """
    INSERT INTO connections(
      connection_id, node_id, user_id, user_tag, destination_host, destination_ip,
      destination_port, network, upload_bytes, download_bytes,
      started_at, closed_at, last_seen_at
    ) VALUES (?, 'n1', 'u-bob', 'bob', 'closed.example', '198.51.100.9', 443, 'tcp',
              10, 20, '2026-08-14T09:00:00Z', '2026-08-14T09:01:00Z',
              '2026-08-14T09:01:00Z')
    """,
    ("c-closed",),
)
raw.execute(
    """
    INSERT INTO daily_usage(
      date, user_id, user_tag, destination_host,
      upload_bytes, download_bytes, connection_count
    ) VALUES ('2026-08-14', 'u-alice', 'alice', 'open.example', 12345, 67890, 1)
    """
)
raw.commit()
raw.close()

conn = mod.open_db(old_db)
assert mod.meta_get(conn, "schema_version") == "3"
cols = [r[1] for r in conn.execute("PRAGMA table_info(connections)").fetchall()]
for required in ("event_id", "generation", "instance_id", "connection_id", "user_id"):
    assert required in cols, cols
tables = {
    r[0]
    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
}
assert "poll_baseline" in tables, tables
idx = {
    r[0]
    for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='connections'"
    ).fetchall()
}
assert "idx_connections_user_started" in idx, idx

rows = conn.execute(
    "SELECT connection_id, generation, instance_id, event_id, "
    "upload_bytes, download_bytes, closed_at, node_id "
    "FROM connections ORDER BY event_id"
).fetchall()
assert len(rows) == 2, rows
assert rows[0][3] >= 1 and rows[1][3] > rows[0][3], rows
by_cid = {r[0]: r for r in rows}
open_row = by_cid["c-open"]
closed_row = by_cid["c-closed"]
assert open_row[1] == 0 and open_row[2] is None, open_row
assert open_row[4] == 12345 and open_row[5] == 67890, open_row
assert open_row[6] is None, open_row
assert open_row[7] == "n1" and open_row[2] is not open_row[7]
assert closed_row[1] == 0 and closed_row[2] is None, closed_row
assert closed_row[4] == 10 and closed_row[5] == 20, closed_row
assert closed_row[6] == "2026-08-14T09:01:00Z", closed_row
daily = conn.execute(
    "SELECT upload_bytes, download_bytes, connection_count FROM daily_usage"
).fetchone()
assert daily[0] == 12345 and daily[1] == 67890 and daily[2] == 1, daily
n_base = conn.execute("SELECT COUNT(*) FROM poll_baseline").fetchone()[0]
assert n_base == 0, n_base

# First sight after migrate: keep accounted bytes; large Clash counters are baseline.
known = {}
live = [{
    "connection_id": "c-open",
    "node_id": "n1",
    "user_id": "u-alice",
    "user_tag": "alice",
    "destination_host": "open.example",
    "destination_ip": None,
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 999999,
    "download_bytes": 888888,
    "started_at": "2026-08-14T10:00:00Z",
    "ts": "2026-08-14T11:00:00Z",
}]
known = mod.apply_poll_delta(conn, live, known)
row = conn.execute(
    "SELECT upload_bytes, download_bytes, generation, instance_id "
    "FROM connections WHERE connection_id='c-open'"
).fetchone()
assert row[0] == 12345 and row[1] == 67890, row
assert row[2] == 0 and row[3] is None, row

# Subsequent poll: only the positive delta from the new baseline.
live2 = [dict(live[0], upload_bytes=1000099, download_bytes=888938,
              ts="2026-08-14T11:00:01Z")]
known = mod.apply_poll_delta(conn, live2, known)
row = conn.execute(
    "SELECT upload_bytes, download_bytes, generation, instance_id "
    "FROM connections WHERE connection_id='c-open' AND generation=0"
).fetchone()
assert row[0] == 12445 and row[1] == 67940, row
assert row[2] == 0 and row[3] is None, row

# UNIQUE(connection_id, generation): a new generation is a second row.
mod.upsert_connection(conn, {
    "connection_id": "c-open",
    "generation": 1,
    "node_id": "n1",
    "user_id": "u-alice",
    "user_tag": "alice",
    "destination_host": "open.example",
    "destination_ip": None,
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 0,
    "download_bytes": 0,
    "started_at": "2026-08-14T11:00:00Z",
    "ts": "2026-08-14T11:00:00Z",
}, close=False, accounted_upload=0, accounted_download=0)
gens = conn.execute(
    "SELECT generation, event_id, upload_bytes, instance_id FROM connections "
    "WHERE connection_id='c-open' ORDER BY generation"
).fetchall()
assert len(gens) == 2, gens
assert gens[0][0] == 0 and gens[0][2] == 12445, gens
assert gens[1][0] == 1 and gens[1][2] == 0, gens
assert gens[1][1] > gens[0][1], gens
assert gens[0][3] is None, gens  # migrated generation stays NULL on UPDATE/INSERT of other gens
try:
    conn.execute(
        """
        INSERT INTO connections(
          connection_id, generation, user_id, node_id, started_at, last_seen_at
        ) VALUES ('c-open', 0, 'u-alice', 'n1',
                  '2026-08-14T10:00:00Z', '2026-08-14T10:00:00Z')
        """
    )
    raise AssertionError("expected UNIQUE(connection_id, generation) violation")
except sqlite3.IntegrityError:
    pass

# AUTOINCREMENT: delete a row, insert same connection_id new generation → event_id
# is strictly greater (no reuse).
deleted_id = closed_row[3]
max_id = conn.execute("SELECT MAX(event_id) FROM connections").fetchone()[0]
conn.execute("DELETE FROM connections WHERE connection_id='c-closed'")
conn.commit()
mod.upsert_connection(conn, {
    "connection_id": "c-closed",
    "generation": 1,
    "node_id": "n1",
    "user_id": "u-bob",
    "user_tag": "bob",
    "destination_host": "closed.example",
    "destination_ip": "198.51.100.9",
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 0,
    "download_bytes": 0,
    "started_at": "2026-08-14T12:00:00Z",
    "ts": "2026-08-14T12:00:00Z",
}, close=False)
new_id = conn.execute(
    "SELECT event_id, generation, instance_id FROM connections "
    "WHERE connection_id='c-closed'"
).fetchone()
assert new_id[0] > max_id and new_id[0] != deleted_id, (new_id, max_id, deleted_id)
assert new_id[1] == 1, new_id
conn.close()

# Empty DB via open_db is schema 3 with poll_baseline.
fresh = mod.open_db(empty_db)
assert mod.meta_get(fresh, "schema_version") == "3"
fresh_cols = [r[1] for r in fresh.execute("PRAGMA table_info(connections)").fetchall()]
assert "event_id" in fresh_cols and "generation" in fresh_cols
assert "instance_id" in fresh_cols, fresh_cols
fresh_tables = {
    r[0]
    for r in fresh.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
}
assert "poll_baseline" in fresh_tables, fresh_tables
fresh.close()
PY
if (( schema3_rc == 0 )); then
  pass "schema 2 to 3 preserves accounted bytes"
  pass "schema 3 UNIQUE(connection_id, generation) and AUTOINCREMENT"
  pass "open_db empty database is schema 3"
  pass "D5 historical instance_id stays NULL after migrate"
else
  fail "schema 2 to 3 preserves accounted bytes"
  fail "schema 3 UNIQUE(connection_id, generation) and AUTOINCREMENT"
  fail "open_db empty database is schema 3"
  fail "D5 historical instance_id stays NULL after migrate"
fi

# D5 split: new INSERT stamps instance_id from state.json; UPDATE never overwrites.
d5_stamp_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" \
  "${TEST_TMP}/d5-stamp.db" "${TEST_TMP}/state.json" "${TEST_TMP}/config.toml" \
  "$TEST_INSTANCE_ID" "$TEST_NODE_ID" "${TEST_TMP}/d5-state" <<'PY' || d5_stamp_rc=$?
import importlib.util, json, os, sqlite3, sys
from pathlib import Path

mod_path, db, state_path, settings_path, iid, nid, fixtures = sys.argv[1:]
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert mod.DEFAULT_STATE == "/etc/vincula/state.json"
assert mod.load_instance_id(state_path) == iid
assert mod.load_instance_id("/no/such/vincula-state.json") is None

fx = Path(fixtures)
fx.mkdir(parents=True, exist_ok=True)

schema1 = fx / "schema1.json"
schema1.write_text(json.dumps({
    "schema_version": 1,
    "node": {"node_id": nid, "node_name": "old"},
}), encoding="utf-8")
assert mod.load_instance_id(str(schema1)) is None

bad = fx / "bad-uuid.json"
bad.write_text(json.dumps({
    "schema_version": 2,
    "node": {"node_id": nid, "instance_id": "not-a-uuid"},
}), encoding="utf-8")
assert mod.load_instance_id(str(bad)) is None

copied = fx / "copied.json"
copied.write_text(json.dumps({
    "schema_version": 2,
    "node": {"node_id": nid, "instance_id": nid},
}), encoding="utf-8")
assert mod.load_instance_id(str(copied)) is None

os.environ["VCL_STATE_FILE"] = state_path
os.environ["VCL_USERS_FILE"] = str(Path(settings_path).with_name("users.json"))
mod.build_daemon_from_settings(settings_path)
assert mod.INSTANCE_ID == iid

conn = mod.open_db(db)

def ev(cid, up=0, dn=0, generation=0):
    return {
        "connection_id": cid,
        "generation": generation,
        "node_id": "n1",
        "user_id": "u-alice",
        "user_tag": "alice",
        "destination_host": "stamp.example",
        "destination_ip": None,
        "destination_port": 443,
        "network": "tcp",
        "upload_bytes": up,
        "download_bytes": dn,
        "started_at": "2026-08-16T00:00:00Z",
        "ts": "2026-08-16T00:00:01Z",
    }

mod.INSTANCE_ID = iid
mod.upsert_connection(conn, ev("c-new"), close=False, accounted_upload=0, accounted_download=0)
row = conn.execute(
    "SELECT instance_id, generation FROM connections WHERE connection_id='c-new'"
).fetchone()
assert row[0] == iid and row[1] == 0, row

other = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
mod.INSTANCE_ID = other
mod.upsert_connection(
    conn, ev("c-new", up=10, dn=20), close=False,
    accounted_upload=10, accounted_download=20,
)
row = conn.execute(
    "SELECT instance_id, upload_bytes, download_bytes FROM connections "
    "WHERE connection_id='c-new' AND generation=0"
).fetchone()
assert row[0] == iid, row
assert row[1] == 10 and row[2] == 20, row

mod.INSTANCE_ID = None
mod.upsert_connection(conn, ev("c-hist"), close=False, accounted_upload=1, accounted_download=1)
row = conn.execute(
    "SELECT instance_id FROM connections WHERE connection_id='c-hist' AND generation=0"
).fetchone()
assert row[0] is None, row
mod.INSTANCE_ID = iid
mod.upsert_connection(
    conn, ev("c-hist", up=2, dn=2), close=False,
    accounted_upload=2, accounted_download=2,
)
row = conn.execute(
    "SELECT instance_id, upload_bytes FROM connections "
    "WHERE connection_id='c-hist' AND generation=0"
).fetchone()
assert row[0] is None and row[1] == 2, row

mod.upsert_connection(
    conn, ev("c-hist", generation=1), close=False,
    accounted_upload=0, accounted_download=0, generation=1,
)
gens = conn.execute(
    "SELECT generation, instance_id FROM connections "
    "WHERE connection_id='c-hist' ORDER BY generation"
).fetchall()
assert len(gens) == 2, gens
assert gens[0][0] == 0 and gens[0][1] is None, gens[0]
assert gens[1][0] == 1 and gens[1][1] == iid, gens[1]

mod.INSTANCE_ID = mod.load_instance_id(str(copied))
assert mod.INSTANCE_ID is None
mod.upsert_connection(conn, ev("c-copy"), close=False, accounted_upload=0, accounted_download=0)
row = conn.execute(
    "SELECT instance_id FROM connections WHERE connection_id='c-copy'"
).fetchone()
assert row[0] is None, row
conn.close()
PY
if (( d5_stamp_rc == 0 )); then
  pass "D5 new INSERT stamps instance_id from state.json"
  pass "D5 UPDATE does not overwrite instance_id"
  pass "load_instance_id refuses node_id copy and missing state"
else
  fail "D5 new INSERT stamps instance_id from state.json"
  fail "D5 UPDATE does not overwrite instance_id"
  fail "load_instance_id refuses node_id copy and missing state"
fi

# D7/D8: durable poll_baseline, generation reset, commit-then-cache.
d7_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/d7-baseline.db" "$SAMPLE_USERS" <<'PY' || d7_rc=$?
import importlib.util, sqlite3, sys

mod_path, db, users = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users)

def live_ev(cid, up, dn, ts="2026-08-14T12:00:00Z", **extra):
    ev = {
        "connection_id": cid,
        "node_id": "n1",
        "user_id": "u-alice",
        "user_tag": "alice",
        "destination_host": "d.example",
        "destination_ip": None,
        "destination_port": 443,
        "network": "tcp",
        "upload_bytes": up,
        "download_bytes": dn,
        "started_at": "2026-08-14T11:00:00Z",
        "ts": ts,
    }
    ev.update(extra)
    return ev

conn = mod.open_db(db)

# TASK 22: write baseline → reload → fields match; closed generation stays out of cache.
mod.upsert_connection(conn, live_ev("c-reload", 0, 0), close=False,
                      accounted_upload=40, accounted_download=60, generation=0)
mod.upsert_poll_baseline(conn, "c-reload", 0, 100, 200, 40, 60, "2026-08-14T12:00:00Z")
mod.upsert_connection(conn, live_ev("c-closed-gen", 0, 0, generation=0), close=True,
                      accounted_upload=7, accounted_download=8, generation=0)
mod.upsert_poll_baseline(conn, "c-closed-gen", 0, 1, 2, 7, 8, "2026-08-14T12:00:00Z")
known = mod.reload_known_open_from_db(conn)
assert "c-reload" in known and "c-closed-gen" not in known, known.keys()
st = known["c-reload"]
assert st["generation"] == 0 and st["raw_up"] == 100 and st["raw_dn"] == 200, st
assert st["acc_up"] == 40 and st["acc_dn"] == 60, st
assert st["ev"]["user_id"] == "u-alice", st["ev"]

# TASK 23: two generations → two event_id; updating open gen does not touch closed bytes.
mod.upsert_connection(conn, live_ev("c-gens", 0, 0), close=True,
                      accounted_upload=111, accounted_download=222, generation=0)
ok_closed = mod.upsert_connection(conn, live_ev("c-gens", 0, 0), close=False,
                                  accounted_upload=0, accounted_download=0, generation=0)
assert ok_closed is False
mod.upsert_connection(conn, live_ev("c-gens", 0, 0), close=False,
                      accounted_upload=0, accounted_download=0, generation=1)
mod.upsert_connection(conn, live_ev("c-gens", 0, 0, ts="2026-08-14T12:01:00Z"), close=False,
                      accounted_upload=15, accounted_download=25, generation=1)
gens = conn.execute(
    "SELECT generation, event_id, upload_bytes, download_bytes, closed_at "
    "FROM connections WHERE connection_id='c-gens' ORDER BY generation"
).fetchall()
assert len(gens) == 2, gens
assert gens[0][0] == 0 and gens[0][2] == 111 and gens[0][3] == 222, gens
assert gens[0][4] is not None, gens
assert gens[1][0] == 1 and gens[1][2] == 15 and gens[1][3] == 25, gens
assert gens[1][4] is None, gens
assert gens[1][1] > gens[0][1], gens

# TASK 24: same-generation monotonic delta via durable baseline.
known = {}
known = mod.apply_poll_delta(conn, [live_ev("c-mono", 1000, 2000, ts="2026-08-14T12:10:00Z")], known)
row = conn.execute(
    "SELECT upload_bytes, download_bytes, generation FROM connections WHERE connection_id='c-mono'"
).fetchone()
assert row[0] == 0 and row[1] == 0 and row[2] == 0, row
base = mod.load_poll_baseline(conn, "c-mono")
assert base["raw_up"] == 1000 and base["acc_up"] == 0 and base["generation"] == 0, base
# Empty cache still continues from DB baseline (not first-sight zeroing).
known = mod.apply_poll_delta(
    conn, [live_ev("c-mono", 1500, 2600, ts="2026-08-14T12:10:05Z")], {}
)
row = conn.execute(
    "SELECT upload_bytes, download_bytes, generation FROM connections WHERE connection_id='c-mono'"
).fetchone()
assert row[0] == 500 and row[1] == 600 and row[2] == 0, row
assert known["c-mono"]["acc_up"] == 500 and known["c-mono"]["generation"] == 0, known["c-mono"]

# TASK 24: counter drop → new generation, no negative, old row bytes preserved.
known = mod.apply_poll_delta(
    conn, [live_ev("c-mono", 10, 20, ts="2026-08-14T12:10:10Z")], known
)
rows = conn.execute(
    "SELECT generation, upload_bytes, download_bytes, closed_at FROM connections "
    "WHERE connection_id='c-mono' ORDER BY generation"
).fetchall()
assert len(rows) == 2, rows
assert rows[0][0] == 0 and rows[0][1] == 500 and rows[0][2] == 600, rows
assert rows[0][3] is not None, rows
assert rows[1][0] == 1 and rows[1][1] == 0 and rows[1][2] == 0, rows
assert rows[1][3] is None, rows
assert rows[1][1] >= 0 and rows[1][2] >= 0
base = mod.load_poll_baseline(conn, "c-mono")
assert base["generation"] == 1 and base["raw_up"] == 10 and base["acc_up"] == 0, base
assert base["raw_up"] >= 0 and base["raw_dn"] >= 0, base
assert base["acc_up"] >= 0 and base["acc_dn"] >= 0, base
# Next poll on the new generation is a positive delta only.
known = mod.apply_poll_delta(
    conn, [live_ev("c-mono", 20, 30, ts="2026-08-14T12:10:15Z")], known
)
row = conn.execute(
    "SELECT upload_bytes, download_bytes FROM connections "
    "WHERE connection_id='c-mono' AND generation=1"
).fetchone()
assert row[0] == 10 and row[1] == 10, row
old = conn.execute(
    "SELECT upload_bytes, download_bytes, closed_at FROM connections "
    "WHERE connection_id='c-mono' AND generation=0"
).fetchone()
assert old[0] == 500 and old[1] == 600 and old[2] is not None, old
neg_conn = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE upload_bytes < 0 OR download_bytes < 0"
).fetchone()[0]
assert neg_conn == 0, neg_conn
neg_base = conn.execute(
    "SELECT COUNT(*) FROM poll_baseline WHERE last_upload_counter < 0 "
    "OR last_download_counter < 0 OR accounted_upload < 0 OR accounted_download < 0"
).fetchone()[0]
assert neg_base == 0, neg_base

# TASK 24: unknown active with large Clash counters → baseline only (new gen if closed exists).
known_unknown = mod.apply_poll_delta(
    conn, [live_ev("c-gens", 999999, 888888, ts="2026-08-14T12:11:00Z")], {}
)
# c-gens gen 1 is still open without a matching baseline → 1a keep 15/25.
row = conn.execute(
    "SELECT generation, upload_bytes, download_bytes, closed_at FROM connections "
    "WHERE connection_id='c-gens' AND closed_at IS NULL"
).fetchone()
assert row[0] == 1 and row[1] == 15 and row[2] == 25, row
# Brand-new id with huge counters: accounted 0.
known_unknown = mod.apply_poll_delta(
    conn, [live_ev("c-unknown", 999999, 888888, ts="2026-08-14T12:11:00Z")], {}
)
row = conn.execute(
    "SELECT upload_bytes, download_bytes, generation FROM connections WHERE connection_id='c-unknown'"
).fetchone()
assert row[0] == 0 and row[1] == 0 and row[2] == 0, row
base = mod.load_poll_baseline(conn, "c-unknown")
assert base["raw_up"] == 999999 and base["acc_up"] == 0, base

# Closed-only connection_id: new generation, never overwrite the closed row.
known_unknown = mod.apply_poll_delta(
    conn, [live_ev("c-closed-gen", 5000, 6000, ts="2026-08-14T12:11:30Z")], {}
)
rows = conn.execute(
    "SELECT generation, upload_bytes, download_bytes, closed_at FROM connections "
    "WHERE connection_id='c-closed-gen' ORDER BY generation"
).fetchall()
assert len(rows) == 2, rows
assert rows[0][0] == 0 and rows[0][1] == 7 and rows[0][2] == 8 and rows[0][3] is not None, rows
assert rows[1][0] == 1 and rows[1][1] == 0 and rows[1][2] == 0 and rows[1][3] is None, rows

# Invalid counters are skipped (no huge/negative delta).
before = conn.execute(
    "SELECT upload_bytes FROM connections WHERE connection_id='c-unknown'"
).fetchone()[0]
mod.apply_poll_delta(conn, [live_ev("c-unknown", 2**63, 0)], known_unknown)
mod.apply_poll_delta(conn, [live_ev("c-unknown", -1, 0)], known_unknown)
after = conn.execute(
    "SELECT upload_bytes, generation FROM connections WHERE connection_id='c-unknown'"
).fetchone()
assert after[0] == before and after[1] == 0, after

# TASK 25: commit failure → cache reloaded from DB, uncommitted delta discarded.
mod.upsert_connection(conn, live_ev("c-fail", 0, 0), close=False,
                      accounted_upload=100, accounted_download=100, generation=0)
mod.upsert_poll_baseline(conn, "c-fail", 0, 50, 50, 100, 100, "2026-08-14T12:20:00Z")
conn.commit()
known = mod.reload_known_open_from_db(conn)
new_known = mod.apply_poll_delta(
    conn, [live_ev("c-fail", 80, 80, ts="2026-08-14T12:20:05Z")], known
)
assert new_known["c-fail"]["acc_up"] == 130, new_known["c-fail"]

class FailCommit:
    def __init__(self, inner):
        self._inner = inner
    def commit(self):
        raise sqlite3.DatabaseError("injected")
    def rollback(self):
        return self._inner.rollback()
    def __getattr__(self, name):
        return getattr(self._inner, name)

holder = {"known": {"c-fail": {"acc_up": 999}}}
def setter(k):
    holder["known"] = k
try:
    mod.commit_accounting(FailCommit(conn), new_known, setter)
    raise AssertionError("expected commit failure")
except sqlite3.DatabaseError as exc:
    assert "injected" in str(exc)
assert holder["known"]["c-fail"]["acc_up"] == 100, holder["known"]["c-fail"]
row = conn.execute(
    "SELECT upload_bytes, download_bytes FROM connections WHERE connection_id='c-fail'"
).fetchone()
assert row[0] == 100 and row[1] == 100, row
base = mod.load_poll_baseline(conn, "c-fail")
assert base["raw_up"] == 50 and base["acc_up"] == 100, base

# TASK 25 via _tick: daemon cache must not keep the failed transaction's delta.
daemon = mod.AccountDaemon(db_path=db, clash_url="http://127.0.0.1:1/connections")
daemon._known_open = mod.reload_known_open_from_db(conn)
assert daemon._known_open["c-fail"]["acc_up"] == 100

def fake_fetch(*_a, **_k):
    return [live_ev("c-fail", 80, 80, ts="2026-08-14T12:20:10Z")]
mod.fetch_clash_connections = fake_fetch

class TickFailConn:
    def __init__(self, inner):
        self._inner = inner
        self._n = 0
    def commit(self):
        self._n += 1
        if self._n == 1:
            raise sqlite3.DatabaseError("injected-tick")
        return self._inner.commit()
    def rollback(self):
        return self._inner.rollback()
    def execute(self, *a, **k):
        return self._inner.execute(*a, **k)
    def __getattr__(self, name):
        return getattr(self._inner, name)

try:
    daemon._tick(TickFailConn(conn))
    raise AssertionError("expected _tick commit failure")
except sqlite3.DatabaseError as exc:
    assert "injected-tick" in str(exc)
assert daemon._known_open["c-fail"]["acc_up"] == 100, daemon._known_open["c-fail"]
row = conn.execute(
    "SELECT upload_bytes FROM connections WHERE connection_id='c-fail'"
).fetchone()
assert row[0] == 100, row

# TASK 26: startup loads known_open from poll_baseline; next poll is delta-only.
fresh = mod.AccountDaemon(db_path=db, clash_url="http://127.0.0.1:1/connections")
fresh._known_open = mod.reload_known_open_from_db(conn)
assert fresh._known_open["c-fail"]["raw_up"] == 50, fresh._known_open["c-fail"]
assert fresh._known_open["c-fail"]["acc_up"] == 100, fresh._known_open["c-fail"]
assert fresh._known_open["c-fail"]["generation"] == 0
mod.fetch_clash_connections = lambda *_a, **_k: [
    live_ev("c-fail", 55, 55, ts="2026-08-14T12:21:00Z")
]
# Successful _tick: commit then cache. Bump cycles so we skip rollup/retention.
fresh._cycles = 2
fresh._tick(conn)
assert fresh._known_open["c-fail"]["acc_up"] == 105, fresh._known_open["c-fail"]
row = conn.execute(
    "SELECT upload_bytes, download_bytes, generation FROM connections WHERE connection_id='c-fail'"
).fetchone()
assert row[0] == 105 and row[1] == 105 and row[2] == 0, row
conn.close()
PY
if (( d7_rc == 0 )); then
  pass "reload_known_open_from_db matches poll_baseline"
  pass "same-generation monotonic delta"
  pass "counter reset opens new generation without negative delta"
  pass "unknown active connection is baseline only"
  pass "commit failure reloads cache from DB"
  pass "startup loads known_open from poll_baseline"
else
  fail "reload_known_open_from_db matches poll_baseline"
  fail "same-generation monotonic delta"
  fail "counter reset opens new generation without negative delta"
  fail "unknown active connection is baseline only"
  fail "commit failure reloads cache from DB"
  fail "startup loads known_open from poll_baseline"
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
          connection_id, generation, node_id, user_id, user_tag, destination_host, destination_ip,
          destination_port, network, upload_bytes, download_bytes,
          started_at, closed_at, last_seen_at
        ) VALUES (?, 0, 'n1', 'u-bob', 'bob', ?, NULL, 443, 'tcp', 1, 2, ?, ?, ?)
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

# TASK 27: retention DELETE is capped at RETENTION_DELETE_BATCH (2000) per
# table per call; leftover backlog drains across later calls. Open rows and
# recent closed rows stay. Ingest commit happens before apply_retention.
ret_batch_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/ret-batch.db" "$SAMPLE_USERS" <<'PY' || ret_batch_rc=$?
import importlib.util, sqlite3, sys
from datetime import datetime, timedelta, timezone

mod_path, db, users = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users)

assert mod.RETENTION_DELETE_BATCH == 2000, mod.RETENTION_DELETE_BATCH

conn = mod.open_db(db)
now = datetime.now(timezone.utc)
old_ts = (now - timedelta(days=120)).strftime("%Y-%m-%dT12:00:00Z")
recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT12:00:00Z")
old_day = (now - timedelta(days=120)).strftime("%Y-%m-%d")
recent_day = (now - timedelta(days=1)).strftime("%Y-%m-%d")
cutoff_iso = datetime.fromtimestamp(
    now.timestamp() - 90 * 86400, timezone.utc
).strftime("%Y-%m-%dT%H:%M:%SZ")

n_expired = 5005
conn.executemany(
    """
    INSERT INTO connections(
      connection_id, generation, node_id, user_id, user_tag, destination_host,
      destination_ip, destination_port, network, upload_bytes, download_bytes,
      started_at, closed_at, last_seen_at
    ) VALUES (?, 0, 'n1', 'u-alice', 'alice', 'old.example', NULL, 443, 'tcp',
              1, 2, ?, ?, ?)
    """,
    [(f"exp-{i}", old_ts, old_ts, old_ts) for i in range(n_expired)],
)
# Closed generations past cutoff must go; open rows with old last_seen stay.
conn.execute(
    """
    INSERT INTO connections(
      connection_id, generation, node_id, user_id, user_tag, destination_host,
      destination_ip, destination_port, network, upload_bytes, download_bytes,
      started_at, closed_at, last_seen_at
    ) VALUES ('open-old', 0, 'n1', 'u-alice', 'alice', 'live.example', NULL, 443,
              'tcp', 9, 9, ?, NULL, ?)
    """,
    (old_ts, old_ts),
)
conn.execute(
    """
    INSERT INTO connections(
      connection_id, generation, node_id, user_id, user_tag, destination_host,
      destination_ip, destination_port, network, upload_bytes, download_bytes,
      started_at, closed_at, last_seen_at
    ) VALUES ('recent-closed', 0, 'n1', 'u-alice', 'alice', 'new.example', NULL,
              443, 'tcp', 3, 4, ?, ?, ?)
    """,
    (recent_ts, recent_ts, recent_ts),
)
n_daily_expired = 2505
conn.executemany(
    """
    INSERT INTO daily_usage(
      date, user_id, user_tag, destination_host,
      upload_bytes, download_bytes, connection_count
    ) VALUES (?, 'u-alice', 'alice', ?, 1, 2, 1)
    """,
    [(old_day, f"old-host-{i}.example") for i in range(n_daily_expired)],
)
conn.execute(
    """
    INSERT INTO daily_usage(
      date, user_id, user_tag, destination_host,
      upload_bytes, download_bytes, connection_count
    ) VALUES (?, 'u-alice', 'alice', 'recent.example', 1, 2, 1)
    """,
    (recent_day,),
)
conn.commit()

max_expired_id = conn.execute(
    "SELECT MAX(event_id) FROM connections "
    "WHERE last_seen_at < ? AND closed_at IS NOT NULL",
    (cutoff_iso,),
).fetchone()[0]
seq_before = conn.execute(
    "SELECT seq FROM sqlite_sequence WHERE name='connections'"
).fetchone()[0]
assert seq_before >= max_expired_id, (seq_before, max_expired_id)

def expired_conn_n():
    return conn.execute(
        "SELECT COUNT(*) FROM connections "
        "WHERE last_seen_at < ? AND closed_at IS NOT NULL",
        (cutoff_iso,),
    ).fetchone()[0]

def expired_daily_n():
    cutoff_date = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - 90 * 86400, timezone.utc
    ).strftime("%Y-%m-%d")
    return conn.execute(
        "SELECT COUNT(*) FROM daily_usage WHERE date < ?", (cutoff_date,)
    ).fetchone()[0]

assert expired_conn_n() == n_expired, expired_conn_n()
assert expired_daily_n() == n_daily_expired, expired_daily_n()

mod.apply_retention(conn, 90, 90)
assert expired_conn_n() == n_expired - 2000, expired_conn_n()
assert expired_daily_n() == n_daily_expired - 2000, expired_daily_n()
open_n = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE connection_id='open-old' AND closed_at IS NULL"
).fetchone()[0]
assert open_n == 1
recent_n = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE connection_id='recent-closed'"
).fetchone()[0]
assert recent_n == 1
recent_daily = conn.execute(
    "SELECT COUNT(*) FROM daily_usage WHERE destination_host='recent.example'"
).fetchone()[0]
assert recent_daily == 1

mod.apply_retention(conn, 90, 90)
assert expired_conn_n() == n_expired - 4000, expired_conn_n()
assert expired_daily_n() == n_daily_expired - 2505, expired_daily_n()

mod.apply_retention(conn, 90, 90)
assert expired_conn_n() == 0, expired_conn_n()
assert expired_daily_n() == 0, expired_daily_n()
open_n = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE connection_id='open-old' AND closed_at IS NULL"
).fetchone()[0]
assert open_n == 1
recent_n = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE connection_id='recent-closed'"
).fetchone()[0]
assert recent_n == 1

seq_after = conn.execute(
    "SELECT seq FROM sqlite_sequence WHERE name='connections'"
).fetchone()[0]
assert seq_after == seq_before, (seq_after, seq_before)
mod.upsert_connection(conn, {
    "connection_id": "post-retention",
    "node_id": "n1",
    "user_id": "u-alice",
    "user_tag": "alice",
    "destination_host": "after.example",
    "destination_ip": None,
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 1,
    "download_bytes": 1,
    "started_at": recent_ts,
    "ts": recent_ts,
}, close=True)
conn.commit()
new_id = conn.execute(
    "SELECT event_id FROM connections WHERE connection_id='post-retention'"
).fetchone()[0]
assert new_id > max_expired_id, (new_id, max_expired_id)
assert new_id > seq_after, (new_id, seq_after)
conn.close()

# Structural: _tick commits collection before calling apply_retention.
struct_db = db + "-struct"
conn = mod.open_db(struct_db)
order = []
real_retention = mod.apply_retention

def traced_retention(*a, **k):
    order.append("retention")
    return real_retention(*a, **k)

class TraceConn:
    def __init__(self, inner):
        self._inner = inner
    def commit(self):
        order.append("commit")
        return self._inner.commit()
    def __getattr__(self, name):
        return getattr(self._inner, name)

mod.apply_retention = traced_retention
mod.fetch_clash_connections = lambda *_a, **_k: []
daemon = mod.AccountDaemon(
    db_path=struct_db, clash_url="http://127.0.0.1:1/connections"
)
daemon._cycles = 0
try:
    daemon._tick(TraceConn(conn))
finally:
    mod.apply_retention = real_retention
assert "commit" in order and "retention" in order, order
assert order.index("commit") < order.index("retention"), order
conn.close()
PY
if (( ret_batch_rc == 0 )); then
  pass "retention deletes at most 2000 rows per call"
  pass "retention batches daily_usage at most 2000 rows per call"
  pass "retention backlog drains across calls"
  pass "retention does not hold collection commit"
  pass "retention leaves open rows and recent closed rows"
else
  fail "retention deletes at most 2000 rows per call"
  fail "retention batches daily_usage at most 2000 rows per call"
  fail "retention backlog drains across calls"
  fail "retention does not hold collection commit"
  fail "retention leaves open rows and recent closed rows"
fi

# F1: tag→user_id hot-reload on users.json mtime change
f1_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/f1-hotreload" <<'PY' || f1_rc=$?
import importlib.util, json, os, sys, time

mod_path, work = sys.argv[1], sys.argv[2]
os.makedirs(work, exist_ok=True)
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

users_path = os.path.join(work, "users.json")
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

alice_item = {
    "id": "c-alice-1",
    "upload": 1,
    "download": 2,
    "start": "2026-08-14T10:00:00Z",
    "chains": ["DIRECT", "acct/alice"],
    "metadata": {
        "host": "a.example",
        "destinationPort": 443,
        "network": "tcp",
    },
}

def fake_fetch(*_a, **_k):
    ev = mod.parse_clash_connection(alice_item)
    return [ev] if ev else []

mod.fetch_clash_connections = fake_fetch
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users_path)
os.environ["VCL_USERS_FILE"] = users_path
daemon = mod.AccountDaemon(
    db_path=db_path,
    clash_url="http://127.0.0.1:1/connections",
    users_path=users_path,
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

# F2: Clash poll failure does not refresh last_success_at; leftover JSONL is not a collector
f2_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/f2-clash" "$SAMPLE_USERS" <<'PY' || f2_rc=$?
import importlib.util, inspect, os, sys, urllib.error

mod_path, work, users = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(work, exist_ok=True)
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users)

# Leftover residue file must not become an ingest path.
residue = os.path.join(work, "events.jsonl")
with open(residue, "w", encoding="utf-8") as f:
    f.write(
        '{"event":"connection_closed","connection_id":"c-bob-1","node_id":"n1",'
        '"user":"bob","destination_host":"b.example","destination_port":443,'
        '"network":"tcp","upload_bytes":3,"download_bytes":4,'
        '"started_at":"2026-08-14T10:00:00Z","closed_at":"2026-08-14T10:00:01Z"}\n'
    )
db_path = os.path.join(work, "acct.db")

polls = []

def fake_fetch(*_a, **_k):
    polls.append("poll")
    raise urllib.error.URLError("fake clash down")

mod.fetch_clash_connections = fake_fetch
daemon = mod.AccountDaemon(
    db_path=db_path,
    clash_url="http://127.0.0.1:1/connections",
    users_path=users,
)
assert not hasattr(mod, "parse_jsonl_event")
assert not hasattr(mod, "read_new_jsonl")
assert not hasattr(mod, "apply_jsonl_events")
assert not hasattr(mod, "ingest_events_file")
assert not hasattr(daemon, "_jsonl_offset")
assert not hasattr(daemon, "_prefer_jsonl")
assert not hasattr(daemon, "events_path")
src = inspect.getsource(mod.AccountDaemon._collect)
assert "_poll_clash" in src
assert "jsonl" not in src.lower()

conn = mod.open_db(db_path)
assert mod.meta_get(conn, "last_success_at") == ""
daemon._tick(conn)
assert polls == ["poll"], polls
assert mod.meta_get(conn, "last_success_at") == "", "failed Clash poll must not refresh last_success_at"
n = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
assert n == 0, n
conn.close()

# --once uses the same collect path
polls.clear()
once_db = os.path.join(work, "once.db")
daemon2 = mod.AccountDaemon(
    db_path=once_db,
    clash_url="http://127.0.0.1:1/connections",
    users_path=users,
)
conn = mod.open_db(once_db)
mod.close_stale_open_connections(conn)
daemon2._tick(conn)
assert "poll" in polls
assert mod.meta_get(conn, "last_success_at") == ""
conn.close()
PY
if (( f2_rc == 0 )); then
  pass "failed Clash poll does not refresh last_success_at"
else
  fail "failed Clash poll does not refresh last_success_at"
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

  render_sing_box_config_accounting \
    "${PROV_DIR}/cfg-before-set.json" "${PROV_DIR}/users.json" \
    "$TEST_PRIVATE_KEY" "$TEST_SHORT_ID" 443 www.cloudflare.com \
    0.0.0.0 9090 "$TEST_SECRET" true
  assert_success "users_registry_mutate set updates metadata" \
    users_registry_mutate "${PROV_DIR}/users.json" set alice "Alice Chen" Engineering
  assert_equal "set updates display_name" "Alice Chen" \
    "$(users_registry_field "${PROV_DIR}/users.json" alice display_name)"
  assert_equal "set updates department" "Engineering" \
    "$(users_registry_field "${PROV_DIR}/users.json" alice department)"
  render_sing_box_config_accounting \
    "${PROV_DIR}/cfg-after-set.json" "${PROV_DIR}/users.json" \
    "$TEST_PRIVATE_KEY" "$TEST_SHORT_ID" 443 www.cloudflare.com \
    0.0.0.0 9090 "$TEST_SECRET" true
  assert_success "metadata-only set leaves rendered config unchanged" \
    python3 -c 'import json,sys; a=json.load(open(sys.argv[1], encoding="utf-8")); b=json.load(open(sys.argv[2], encoding="utf-8")); raise SystemExit(0 if a==b else 1)' \
      "${PROV_DIR}/cfg-before-set.json" "${PROV_DIR}/cfg-after-set.json"

  cp -a -- "${PROV_DIR}/users.json" "${PROV_DIR}/users-o1.json"
  rm_rc=0
  rm_err=$(users_registry_mutate "${PROV_DIR}/users-o1.json" remove alice 2>&1) || rm_rc=$?
  if (( rm_rc != 0 )) && [[ "$rm_err" == *"unknown action"* ]]; then
    pass "users_registry_mutate remove is unknown action"
  else
    fail "users_registry_mutate remove is unknown action (rc=${rm_rc} err=${rm_err})"
  fi
  assert_success "remove action does not purge alice" \
    grep -q '"tag": "alice"' "${PROV_DIR}/users-o1.json"
  assert_success "users_registry_mutate add still works" \
    users_registry_mutate "${PROV_DIR}/users-o1.json" add bob "Bob" qa \
      "cccccccc-cccc-4ccc-8ccc-cccccccccccc" "$NODE_ID"
  assert_success "users_registry_mutate disable still works" \
    users_registry_mutate "${PROV_DIR}/users-o1.json" disable bob
  assert_success "users_registry_mutate enable still works" \
    users_registry_mutate "${PROV_DIR}/users-o1.json" enable bob
  assert_success "users_registry_mutate set still works after remove deletion" \
    users_registry_mutate "${PROV_DIR}/users-o1.json" set bob "Bobby" qa

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
  assert_success "helper documents metadata-only user set skips restart" \
    grep -q 'metadata-only user set does not' "${PROJECT_DIR}/bin/vincula"
  assert_success "user mutation compares rendered config before restart" \
    grep -q 'cmp -s -- "$staged_config" "$CONFIG_FILE"' "${PROJECT_DIR}/bin/vincula"
  assert_success "user mutation compares owner uri before restart" \
    grep -q 'cmp -s -- "$staged_uri" "$URI_FILE"' "${PROJECT_DIR}/bin/vincula"
  assert_success "README says metadata-only user set does not restart" \
    grep -q '仅改 metadata 的 `user set` 不重启' "${PROJECT_DIR}/README.md"
  assert_success "RC CLI coverage keeps pre-add remove cleanup" \
    grep -q 'vcl user remove bob 2>/dev/null || true' "${PROJECT_DIR}/scripts/rc-vcl-cli-coverage.sh"
  assert_success "RC CLI coverage expects user remove exit 2" \
    grep -q 'user-remove-bob-refused' "${PROJECT_DIR}/scripts/rc-vcl-cli-coverage.sh"
  assert_success "RC CLI coverage expects bob still listed after remove" \
    grep -q 'user-remove-bob-still-listed' "${PROJECT_DIR}/scripts/rc-vcl-cli-coverage.sh"
  assert_failure "RC CLI coverage must not assert remove success" \
    grep -q 'user-remove-bob-gone' "${PROJECT_DIR}/scripts/rc-vcl-cli-coverage.sh"
  assert_failure "users_registry_mutate has no remove action" \
    grep -q 'action == "remove"' "${PROJECT_DIR}/lib/vincula-common.sh"
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

  # Absolute dates, billing cycle windows, argparse exclusivity (frozen UTC clock).
  DATE_DIR="${TEST_TMP}/stats-dates"
  mkdir -p "$DATE_DIR"
  if python3 - "$DATE_DIR" "${PROJECT_DIR}/lib/vincula-stats.py" <<'PY'
import io, json, os, sqlite3, subprocess, sys
from datetime import date
from pathlib import Path

base = Path(sys.argv[1])
stats_py = sys.argv[2]
os.environ["VINCULA_STATS_NOW"] = "2026-08-15"

import importlib.util
spec = importlib.util.spec_from_file_location("vstats", stats_py)
mod = importlib.util.module_from_spec(spec)
sys.modules["vstats"] = mod
spec.loader.exec_module(mod)

assert mod.period_for_month(0, 1) == ("2026-08-01", "2026-08-15")
assert mod.period_for_month(0, 5) == ("2026-08-05", "2026-08-15")
assert mod.period_for_days(1, 0) == ("2026-08-15", "2026-08-15")
assert mod.period_for_days(1, 1) == ("2026-08-14", "2026-08-14")
assert mod.period_for_days(7, 0) == ("2026-08-09", "2026-08-15")
os.environ["VINCULA_STATS_NOW"] = "2026-08-03"
assert mod.period_for_month(0, 5) == ("2026-07-05", "2026-08-03")
assert mod.period_for_month(0, 1) == ("2026-08-01", "2026-08-03")
os.environ["VINCULA_STATS_NOW"] = "2026-08-15"

db = base / "accounting.db"
users = base / "users.json"
users.write_text(json.dumps({
    "schema_version": 2,
    "users": [{"user_id": "u-alice", "tag": "alice", "display_name": "Alice", "department": "Engineering"}],
}), encoding="utf-8")
conn = sqlite3.connect(db)
conn.executescript("""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE daily_usage (
  date TEXT NOT NULL, user_id TEXT NOT NULL, user_tag TEXT,
  destination_host TEXT NOT NULL, upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0, connection_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (date, user_id, destination_host)
);
""")
conn.execute("INSERT INTO meta(key,value) VALUES('last_success_at','2026-08-15T00:00:00Z')")
conn.executemany(
    "INSERT INTO daily_usage VALUES (?,?,?,?,?,?,?)",
    [
        ("2026-08-15", "u-alice", "alice", "today.example", 1, 1, 1),
        ("2026-08-05", "u-alice", "alice", "cycle.example", 2, 2, 1),
        ("2026-08-01", "u-alice", "alice", "month.example", 4, 4, 1),
        ("2026-07-20", "u-alice", "alice", "july.example", 8, 8, 1),
    ],
)
conn.commit()
conn.close()

def run(*extra, check=True):
    cmd = [
        sys.executable, stats_py,
        "--db", str(db), "--users", str(users),
        "--collector-state", "active",
        "--last-success-at", "2026-08-15T00:00:00Z",
        "--format", "json",
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

out = run("--mode", "summary", "--date", "2026-08-15")
data = json.loads(out.stdout)
assert data["meta"]["period_start"] == "2026-08-15" and data["meta"]["period_end"] == "2026-08-15"
assert data["rows"] and data["rows"][0]["total_bytes"] == 2
out = run("--mode", "top_hosts", "--date", "2026-08-15")
hosts = {r["destination_host"] for r in json.loads(out.stdout)["rows"]}
assert hosts == {"today.example"}, hosts

out = run("--mode", "summary", "--from", "2026-08-01", "--to", "2026-08-05")
data = json.loads(out.stdout)
assert data["meta"]["period_start"] == "2026-08-01" and data["meta"]["period_end"] == "2026-08-05"
assert data["rows"][0]["total_bytes"] == 12
out = run("--mode", "top_hosts", "--from", "2026-08-01", "--to", "2026-08-05")
hosts = {r["destination_host"] for r in json.loads(out.stdout)["rows"]}
assert hosts == {"cycle.example", "month.example"}, hosts

# regression: default start_day=1 month/days/today/yesterday identical to calendar windows
out = run("--mode", "summary", "--month", "1")
data = json.loads(out.stdout)
assert data["meta"]["period_start"] == "2026-08-01" and data["meta"]["period_end"] == "2026-08-15"
out = run("--mode", "summary", "--days", "1", "--day-offset", "0")
assert json.loads(out.stdout)["meta"]["period_start"] == "2026-08-15"
out = run("--mode", "summary", "--days", "1", "--day-offset", "1")
assert json.loads(out.stdout)["meta"]["period_start"] == "2026-08-14"
assert json.loads(run("--mode", "summary", "--days", "7").stdout)["meta"]["period_start"] == "2026-08-09"

out = run("--mode", "summary", "--month", "1", "--cycle-start", "5")
data = json.loads(out.stdout)
assert data["meta"]["period_start"] == "2026-08-05" and data["meta"]["period_end"] == "2026-08-15"
out = run("--mode", "top_hosts", "--month", "1", "--cycle-start", "5")
hosts = {r["destination_host"] for r in json.loads(out.stdout)["rows"]}
assert "month.example" not in hosts and "cycle.example" in hosts and "today.example" in hosts, hosts

# missing --cycle-start ≡ 1
out = run("--mode", "summary", "--month", "1")
assert json.loads(out.stdout)["meta"]["period_start"] == "2026-08-01"

# invalid toml/CLI cycle-start → fallback 1 + warning
out = run("--mode", "summary", "--month", "1", "--cycle-start", "0", check=False)
assert out.returncode == 0, out.stderr
assert "falling back to 1" in out.stderr
assert json.loads(out.stdout)["meta"]["period_start"] == "2026-08-01"
out = run("--mode", "summary", "--month", "1", "--cycle-start", "29", check=False)
assert out.returncode == 0 and "falling back to 1" in out.stderr
out = run("--mode", "summary", "--month", "1", "--cycle-start", "abc", check=False)
assert out.returncode == 0 and "falling back to 1" in out.stderr

# exclusivity
out = run("--mode", "summary", "--date", "2026-08-15", "--month", "1", check=False)
assert out.returncode != 0
out = run("--mode", "summary", "--date", "2026-08-15", "--days", "3", check=False)
assert out.returncode != 0
out = run("--mode", "summary", "--from", "2026-08-01", check=False)
assert out.returncode != 0 and "must both be given" in out.stderr
out = run("--mode", "summary", "--to", "2026-08-15", check=False)
assert out.returncode != 0 and "must both be given" in out.stderr
out = run("--mode", "summary", "--from", "2026-08-15", "--to", "2026-08-01", check=False)
assert out.returncode != 0

print("dates-ok")
PY
  then
    pass "vincula-stats --date/--from/--to and billing cycle windows"
  else
    fail "vincula-stats --date/--from/--to and billing cycle windows"
  fi
fi

# --- 0.2.7 vincula-audit.py (TASK 31–34; CLI wired in 1c-cli) ---
if command -v python3 >/dev/null 2>&1; then
  AUDIT_DIR="${TEST_TMP}/audit027"
  mkdir -p "$AUDIT_DIR"
  if python3 - "$AUDIT_DIR" "${PROJECT_DIR}/lib/vincula-audit.py" "${PROJECT_DIR}/lib/vincula-accountd.py" <<'PY'
import importlib.util, json, sqlite3, subprocess, sys
from pathlib import Path

base = Path(sys.argv[1])
audit_py = sys.argv[2]
accountd_py = sys.argv[3]
db = base / "accounting.db"
users = base / "users.json"

users.write_text(json.dumps({
    "schema_version": 2,
    "users": [
        {"user_id": "u-alice", "tag": "alice", "display_name": "Alice"},
        {"user_id": "u-bob", "tag": "bob", "display_name": "Bob"},
    ],
}), encoding="utf-8")

spec_a = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec_a)
spec_a.loader.exec_module(acct)
conn = acct.open_db(str(db))
assert acct.meta_get(conn, "schema_version") == "3"

def insert(**kw):
    conn.execute(
        """
        INSERT INTO connections (
          connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            kw["cid"], kw.get("generation", 0), kw["user_id"], kw.get("node_id", "n1"),
            None, kw["tag"], kw["started"], kw["last_seen"], kw.get("closed"),
            kw.get("host"), kw.get("ip"), kw.get("port", 443), kw.get("network", "tcp"),
            kw.get("up", 10), kw.get("down", 20),
        ),
    )

# TASK 32 A/B/C plus extras for outside / fully-inside / started_at==query_to.
insert(cid="conn-a", user_id="u-alice", tag="alice",
       started="2026-08-10T08:00:00Z", last_seen="2026-08-10T12:00:00Z",
       closed="2026-08-10T12:00:00Z", host="example.com", ip="203.0.113.10")
insert(cid="conn-b", user_id="u-alice", tag="alice",
       started="2026-08-10T13:00:00Z", last_seen="2026-08-10T18:00:00Z",
       closed="2026-08-10T18:00:00Z", host="other.example", ip="198.51.100.2")
insert(cid="conn-c", user_id="u-bob", tag="bob",
       started="2026-08-10T07:00:00Z", last_seen="2026-08-10T20:00:00Z",
       closed=None, host="example.com", ip="203.0.113.11")
insert(cid="conn-inside", user_id="u-alice", tag="alice",
       started="2026-08-10T10:00:00Z", last_seen="2026-08-10T11:00:00Z",
       closed="2026-08-10T11:00:00Z", host="inside.example", ip="203.0.113.12")
insert(cid="conn-before", user_id="u-alice", tag="alice",
       started="2026-08-10T05:00:00Z", last_seen="2026-08-10T06:00:00Z",
       closed="2026-08-10T06:00:00Z", host="before.example", ip="203.0.113.13")
insert(cid="conn-after", user_id="u-alice", tag="alice",
       started="2026-08-10T19:00:00Z", last_seen="2026-08-10T21:00:00Z",
       closed="2026-08-10T21:00:00Z", host="after.example", ip="203.0.113.14")
insert(cid="conn-eq-to", user_id="u-alice", tag="alice",
       started="2026-08-10T18:00:00Z", last_seen="2026-08-10T19:00:00Z",
       closed="2026-08-10T19:00:00Z", host="boundary.example", ip="203.0.113.15")
conn.commit()
n_baseline = conn.execute("SELECT COUNT(*) FROM poll_baseline").fetchone()[0]
assert n_baseline == 0, n_baseline
conn.close()

spec = importlib.util.spec_from_file_location("vaudit", audit_py)
audit = importlib.util.module_from_spec(spec)
sys.modules["vaudit"] = audit
spec.loader.exec_module(audit)

assert audit.parse_rfc3339("2026-08-10T09:00:00Z") == "2026-08-10T09:00:00Z"
assert audit.parse_rfc3339("2026-08-10T09:00:00+00:00") == "2026-08-10T09:00:00Z"
assert audit.parse_rfc3339("2026-08-10T17:00:00+08:00") == "2026-08-10T09:00:00Z"
assert audit.interval_overlap_sql() == (
    "started_at < ? AND COALESCE(closed_at, last_seen_at) >= ?"
)

try:
    audit.parse_rfc3339("2026-08-10")
    raise AssertionError("date-only must fail")
except SystemExit:
    pass
try:
    audit.parse_rfc3339("2026-08-10T09:00:00")
    raise AssertionError("naive datetime must fail")
except SystemExit:
    pass

ro = audit.open_db_readonly(str(db))
try:
    ro.execute(
        "INSERT INTO poll_baseline(connection_id, generation, last_upload_counter, "
        "last_download_counter, accounted_upload, accounted_download, last_seen_at) "
        "VALUES ('x',0,0,0,0,0,'2026-08-10T00:00:00Z')"
    )
    raise AssertionError("read-only connection must not allow INSERT")
except sqlite3.OperationalError:
    pass

def ids(rows):
    return [r["connection_id"] for r in rows]

# 09:00–18:00: A (straddle start), B (closed==to), C (open), inside.
# Exclude: before, after, started_at==query_to.
rows = audit.query_audit(
    ro, query_from="2026-08-10T09:00:00Z", query_to="2026-08-10T18:00:00Z",
)
got = ids(rows)
assert got == ["conn-c", "conn-a", "conn-inside", "conn-b"], got
assert all(list(r.keys()) == list(audit.ROW_KEYS) for r in rows), rows[0].keys()

# from=12:00 to=12:30: A (closed==from INCLUDE) and C (open last_seen).
rows = audit.query_audit(
    ro, query_from="2026-08-10T12:00:00Z", query_to="2026-08-10T12:30:00Z",
)
got = ids(rows)
assert got == ["conn-c", "conn-a"], got

rows = audit.query_audit(
    ro, query_from="2026-08-10T09:00:00Z", query_to="2026-08-10T18:00:00Z",
    user_tag="alice", users_path=str(users),
)
got = ids(rows)
assert got == ["conn-a", "conn-inside", "conn-b"], got
assert all(r["user_id"] == "u-alice" for r in rows)

rows = audit.query_audit(
    ro, query_from="2026-08-10T09:00:00Z", query_to="2026-08-10T18:00:00Z",
    user_id="u-bob",
)
assert ids(rows) == ["conn-c"], ids(rows)

try:
    audit.query_audit(
        ro, query_from="2026-08-10T09:00:00Z", query_to="2026-08-10T18:00:00Z",
        user_tag="nobody", users_path=str(users),
    )
    raise AssertionError("unknown tag must fail")
except SystemExit:
    pass

rows = audit.query_audit(
    ro, query_from="2026-08-10T09:00:00Z", query_to="2026-08-10T18:00:00Z",
    dest_host="Example.COM.",
)
assert ids(rows) == ["conn-c", "conn-a"], ids(rows)

rows = audit.query_audit(
    ro, query_from="2026-08-10T09:00:00Z", query_to="2026-08-10T18:00:00Z",
    dest_ip="203.0.113.10",
)
assert ids(rows) == ["conn-a"], ids(rows)

rows = audit.query_audit(
    ro, query_from="2026-08-10T09:00:00Z", query_to="2026-08-10T18:00:00Z",
    node_id="n1",
)
assert ids(rows) == ["conn-c", "conn-a", "conn-inside", "conn-b"], ids(rows)
rows = audit.query_audit(
    ro, query_from="2026-08-10T09:00:00Z", query_to="2026-08-10T18:00:00Z",
    node_id="n-missing",
)
assert ids(rows) == [], ids(rows)
ro.close()

bad = base / "schema2.db"
s2 = sqlite3.connect(bad)
s2.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
s2.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '2')")
s2.commit()
s2.close()
try:
    audit.query_audit(
        audit.open_db_readonly(str(bad)),
        query_from="2026-08-10T09:00:00Z",
        query_to="2026-08-10T18:00:00Z",
    )
    raise AssertionError("schema 2 must fail closed")
except SystemExit:
    pass

def run(*extra, check=True):
    cmd = [
        sys.executable, audit_py,
        "--db", str(db), "--users", str(users),
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

out = run("--from", "2026-08-10T09:00:00Z", "--to", "2026-08-10T18:00:00Z", "--json")
data = json.loads(out.stdout)
assert "rows" in data and "query" in data, data.keys()
assert data["query"]["from"] == "2026-08-10T09:00:00Z"
assert data["query"]["to"] == "2026-08-10T18:00:00Z"
assert [r["connection_id"] for r in data["rows"]] == [
    "conn-c", "conn-a", "conn-inside", "conn-b",
]
assert list(data["rows"][0].keys()) == list(audit.ROW_KEYS)

out = run(
    "--from", "2026-08-10T17:00:00+08:00",
    "--to", "2026-08-11T02:00:00+08:00",
    "--format", "json",
)
data = json.loads(out.stdout)
assert data["query"]["from"] == "2026-08-10T09:00:00Z"
assert data["query"]["to"] == "2026-08-10T18:00:00Z"

out = run(
    "--from", "2026-08-10T09:00:00Z", "--to", "2026-08-10T18:00:00Z",
    "--user", "alice", "--json",
)
assert [r["connection_id"] for r in json.loads(out.stdout)["rows"]] == [
    "conn-a", "conn-inside", "conn-b",
]
out = run(
    "--from", "2026-08-10T09:00:00Z", "--to", "2026-08-10T18:00:00Z",
    "--user-id", "u-bob", "--json",
)
assert [r["connection_id"] for r in json.loads(out.stdout)["rows"]] == ["conn-c"]
out = run(
    "--from", "2026-08-10T09:00:00Z", "--to", "2026-08-10T18:00:00Z",
    "--node", "n-missing", "--json",
)
assert json.loads(out.stdout)["rows"] == []

out = run(
    "--from", "2026-08-10T09:00:00Z", "--to", "2026-08-10T18:00:00Z",
    "--host", "example.com", "--json",
)
assert [r["connection_id"] for r in json.loads(out.stdout)["rows"]] == [
    "conn-c", "conn-a",
]
out = run(
    "--from", "2026-08-10T09:00:00Z", "--to", "2026-08-10T18:00:00Z",
    "--ip", "203.0.113.10", "--json",
)
assert [r["connection_id"] for r in json.loads(out.stdout)["rows"]] == ["conn-a"]

out = run(
    "--from", "2026-08-10T12:00:00Z", "--to", "2026-08-10T12:30:00Z", "--json",
)
assert [r["connection_id"] for r in json.loads(out.stdout)["rows"]] == [
    "conn-c", "conn-a",
]

out = run("--from", "2026-08-10T09:00:00Z", "--to", "2026-08-10T18:00:00Z")
assert "interval-overlap" in out.stdout
assert "conn-a" in out.stdout and "conn-b" in out.stdout

out = run(
    "--from", "2026-08-10T09:00:00Z", "--to", "2026-08-10T18:00:00Z",
    "--user", "nobody", check=False,
)
assert out.returncode != 0 and "unknown user tag" in out.stderr
out = run("--from", "2026-08-10", "--to", "2026-08-10T18:00:00Z", check=False)
assert out.returncode != 0 and "RFC3339" in out.stderr
out = run("--from", "2026-08-10T09:00:00", "--to", "2026-08-10T18:00:00Z", check=False)
assert out.returncode != 0
assert "timezone" in out.stderr.lower() or "RFC3339" in out.stderr
out = run(
    "--from", "2026-08-10T18:00:00Z", "--to", "2026-08-10T09:00:00Z", check=False,
)
assert out.returncode != 0 and "must not be after" in out.stderr

chk = sqlite3.connect(db)
assert chk.execute("SELECT COUNT(*) FROM poll_baseline").fetchone()[0] == 0
chk.close()

print("audit-ok")
PY
  then
    pass "vincula-audit interval-overlap RFC3339 filters and json"
  else
    fail "vincula-audit interval-overlap RFC3339 filters and json"
  fi
fi

# toml_set round-trip preserves clash_api_secret and other keys
TOML_RT="${TEST_TMP}/toml-roundtrip.toml"
cat > "$TOML_RT" <<'EOF'
project_version = "0.2.6"
clash_api_secret = "keep-this-secret"
port = 443
accounting_raw_retention_days = 90
EOF
assert_success "toml_set appends billing_cycle_start_day" toml_set "$TOML_RT" billing_cycle_start_day 5
assert_equal "toml_set billing_cycle_start_day is 5" "5" "$(toml_get "$TOML_RT" billing_cycle_start_day)"
assert_equal "toml_set preserves clash_api_secret" "keep-this-secret" "$(toml_get "$TOML_RT" clash_api_secret)"
assert_equal "toml_set preserves port" "443" "$(toml_get "$TOML_RT" port)"
assert_success "toml_set replaces existing billing_cycle_start_day" toml_set "$TOML_RT" billing_cycle_start_day 12
assert_equal "toml_set billing_cycle_start_day updated to 12" "12" "$(toml_get "$TOML_RT" billing_cycle_start_day)"
assert_equal "toml_set still preserves clash_api_secret after replace" "keep-this-secret" "$(toml_get "$TOML_RT" clash_api_secret)"

# vcl accounting cycle --set via cmd_accounting (skip require_root/require_install)
acct_root="${TEST_TMP}/acct-cli"
mkdir -p "${acct_root}/bin"
ln -sfn "${PROJECT_DIR}/lib" "${acct_root}/lib"
sed -e 's|^readonly SETTINGS_FILE=.*|SETTINGS_FILE="${VCL_SETTINGS_FILE}"|' \
    -e 's|^main "$@"$|cmd_accounting "$@"|' \
    -e 's|candidates=("$COMMON_FILE")|candidates=()|' \
    "${PROJECT_DIR}/bin/vincula" > "${acct_root}/bin/vincula"
chmod +x "${acct_root}/bin/vincula"
CYCLE_TOML="${TEST_TMP}/cycle.toml"
cat > "$CYCLE_TOML" <<'EOF'
project_version = "0.2.6"
clash_api_secret = "cycle-secret"
port = 443
EOF
cycle_cli() {
  VCL_SETTINGS_FILE="$CYCLE_TOML" "${acct_root}/bin/vincula" "$@"
}
cycle_out=$(cycle_cli cycle)
assert_equal "missing billing_cycle_start_day prints 1" "billing_cycle_start_day = 1" "$cycle_out"
cycle_out=$(cycle_cli cycle --set 5)
assert_equal "vcl accounting cycle --set 5 prints value" "billing_cycle_start_day = 5" "$cycle_out"
assert_equal "vcl accounting cycle --set 5 persists" "5" "$(toml_get "$CYCLE_TOML" billing_cycle_start_day)"
assert_equal "cycle --set 5 preserves clash_api_secret" "cycle-secret" "$(toml_get "$CYCLE_TOML" clash_api_secret)"
cycle_out=$(cycle_cli cycle)
assert_equal "vcl accounting cycle prints persisted 5" "billing_cycle_start_day = 5" "$cycle_out"
assert_failure "vcl accounting cycle --set 0 fails" cycle_cli cycle --set 0
assert_failure "vcl accounting cycle --set 29 fails" cycle_cli cycle --set 29
assert_failure "vcl accounting cycle --set abc fails" cycle_cli cycle --set abc
assert_equal "failed --set leaves persisted 5" "5" "$(toml_get "$CYCLE_TOML" billing_cycle_start_day)"
set0_err=$(cycle_cli cycle --set 0 2>&1) || true
if [[ "$set0_err" == *"must be an integer from 1 to 28"* ]]; then
  pass "cycle --set 0 error mentions 1 to 28"
else
  fail "cycle --set 0 error mentions 1 to 28 (got '${set0_err}')"
fi

# F4: vcl verify dual-plane accounting checks (offline). Live Clash is operator-only:
#   sudo vcl verify   # on a running node; expect Clash triad + D3 plane + last_success_at ≤300s
verify_src_fn=$(awk '/^cmd_verify\(\)/,/^cmd_diagnose\(\)/ {print}' "${PROJECT_DIR}/bin/vincula")
if [[ "$verify_src_fn" == *'accounting_plane'* || "$verify_src_fn" == *'baseline sanity'* ]]; then
  pass "cmd_verify uses shared accounting plane checker"
else
  fail "cmd_verify uses shared accounting plane checker"
fi
assert_success "accounting_plane_checks is defined" \
  grep -q '^def accounting_plane_checks(' "${PROJECT_DIR}/lib/vincula-accountd.py"
acct_src_fn=$(awk '/^cmd_accounting\(\)/,/^resolve_stats_py\(\)/ {print}' "${PROJECT_DIR}/bin/vincula")
if [[ "$acct_src_fn" == *'check)'* && "$acct_src_fn" == *'cmd_verify_accounting_plane'* ]]; then
  pass "vcl accounting check aliases the shared accounting plane checker"
else
  fail "vcl accounting check aliases the shared accounting plane checker"
fi
assert_success "installer health checks expect accounting schema 3" \
  grep -q '"$schema" == "3"' "${PROJECT_DIR}/vincula.sh"
assert_failure "cmd_verify no longer inlines schema SQL" \
  grep -q '"$schema" == "3"' "${PROJECT_DIR}/bin/vincula"
assert_failure "cmd_verify no longer expects accounting schema 2" \
  grep -q '"$schema" == "2"' "${PROJECT_DIR}/bin/vincula"
assert_failure "installer health checks no longer expect accounting schema 2" \
  grep -q '"$schema" == "2"' "${PROJECT_DIR}/vincula.sh"
assert_failure "D5: instance_id is never assigned from node_id" \
  grep -E 'instance_id[[:space:]]*=[[:space:]].*node_id' "${PROJECT_DIR}/lib/vincula-accountd.py"
if [[ "$verify_src_fn" == *'heartbeat'* ]]; then
  pass "cmd_verify checks collector heartbeat"
else
  fail "cmd_verify checks collector heartbeat"
fi
if [[ "$verify_src_fn" == *'Bearer'* ]]; then
  pass "cmd_verify documents Bearer triad"
else
  fail "cmd_verify documents Bearer triad"
fi
if [[ "$verify_src_fn" == *'wrong-${clash_secret}'* ]]; then
  pass "cmd_verify rejects wrong Clash secret"
else
  fail "cmd_verify rejects wrong Clash secret"
fi
assert_success "clash_api_reachable_with_secret is defined in common" \
  grep -q '^clash_api_reachable_with_secret()' "${PROJECT_DIR}/lib/vincula-common.sh"
assert_failure "installer no longer defines clash_api_reachable_with_secret" \
  grep -q '^clash_api_reachable_with_secret()' "${PROJECT_DIR}/vincula.sh"
assert_success "installer still calls clash_api_reachable_with_secret" \
  grep -q 'clash_api_reachable_with_secret ' "${PROJECT_DIR}/vincula.sh"
assert_success "installer collector success requires last_success_at" \
  grep -q 'accounting_last_success_fresh_wait' "${PROJECT_DIR}/vincula.sh"
existing_verify_src=$(awk '/^verify_existing_install\(\)/,/^handle_existing_install\(\)/ {print}' "${PROJECT_DIR}/vincula.sh")
if printf '%s\n' "$existing_verify_src" | grep -A1 'wait_for_accountd_healthy' | grep -q 'collector recently successful'; then
  fail "installer must not print collector success from wait_for_accountd_healthy alone"
else
  pass "installer must not print collector success from wait_for_accountd_healthy alone"
fi

if command -v python3 >/dev/null 2>&1; then
  FRESH_DB="${TEST_TMP}/verify-freshness.db"
  python3 - "$FRESH_DB" <<'PY'
import sqlite3, sys
from datetime import datetime, timezone, timedelta
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
now = datetime.now(timezone.utc)
conn.execute("INSERT INTO meta(key,value) VALUES('schema_version','3')")
conn.execute(
    "INSERT INTO meta(key,value) VALUES('last_success_at', ?)",
    (now.strftime("%Y-%m-%dT%H:%M:%SZ"),),
)
conn.commit()
conn.close()
PY
  assert_equal "fresh last_success_at status is fresh" "fresh" "$(accounting_last_success_status "$FRESH_DB")"
  assert_success "fresh last_success_at is healthy" accounting_last_success_fresh "$FRESH_DB"
  python3 - "$FRESH_DB" <<'PY'
import sqlite3, sys
from datetime import datetime, timezone, timedelta
conn = sqlite3.connect(sys.argv[1])
old = (datetime.now(timezone.utc) - timedelta(seconds=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
conn.execute("UPDATE meta SET value=? WHERE key='last_success_at'", (old,))
conn.commit()
conn.close()
PY
  assert_equal "last_success_at older than 300s is stale" "stale" "$(accounting_last_success_status "$FRESH_DB")"
  assert_failure "last_success_at older than 300s is unhealthy" accounting_last_success_fresh "$FRESH_DB"
  stale_wait_start=$(date +%s)
  assert_failure "stale last_success_at fails wait without sleeping" accounting_last_success_fresh_wait "$FRESH_DB"
  stale_wait_elapsed=$(( $(date +%s) - stale_wait_start ))
  if (( stale_wait_elapsed < 2 )); then
    pass "stale last_success_at wait returns immediately"
  else
    fail "stale last_success_at wait returns immediately (elapsed ${stale_wait_elapsed}s)"
  fi
  MISSING_DB="${TEST_TMP}/verify-missing-success.db"
  python3 - "$MISSING_DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
conn.execute("INSERT INTO meta(key,value) VALUES('schema_version','3')")
conn.commit()
conn.close()
PY
  assert_equal "missing last_success_at status is missing" "missing" "$(accounting_last_success_status "$MISSING_DB")"
  assert_failure "missing last_success_at is unhealthy" accounting_last_success_fresh "$MISSING_DB"

  plane_out=""
  plane_rc=0
  plane_out=$(python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}" <<'PY'
import importlib.util, os, sqlite3, subprocess, sys
from datetime import datetime, timezone, timedelta

mod_path, tmp = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

rows = []

def record(name, ok, detail=""):
    rows.append(("PASS" if ok else "FAIL", name, detail))

def by_name(results):
    return {n: (ok, d) for n, ok, d in results}

schema2 = os.path.join(tmp, "plane-schema2.db")
conn = sqlite3.connect(schema2)
conn.executescript("""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE connections (
  connection_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  destination_host TEXT,
  destination_ip TEXT,
  destination_port INTEGER,
  network TEXT,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  closed_at TEXT,
  last_seen_at TEXT NOT NULL
);
""")
conn.execute("INSERT INTO meta(key,value) VALUES('schema_version','2')")
conn.execute(
    "INSERT INTO meta(key,value) VALUES('last_success_at', ?)",
    (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),),
)
conn.commit()
conn.close()
r2 = by_name(mod.accounting_plane_checks(
    schema2, service_active=True, raw_days=90, daily_days=90
))
record(
    "accounting_plane_checks schema 2 fails schema expected",
    r2["schema expected"][0] is False,
    r2["schema expected"][1],
)

healthy = os.path.join(tmp, "plane-healthy.db")
hconn = mod.open_db(healthy)
mod.meta_set(hconn, "last_success_at", mod.utc_now_iso())
hconn.commit()
hconn.close()
rh = by_name(mod.accounting_plane_checks(
    healthy, service_active=True, raw_days=90, daily_days=90
))
record(
    "accounting_plane_checks schema 3 healthy passes schema",
    rh["schema expected"][0] is True,
    rh["schema expected"][1],
)
record(
    "accounting_plane_checks schema 3 healthy passes database readable",
    rh["database readable"][0] is True,
    rh["database readable"][1],
)
record(
    "accounting_plane_checks schema 3 healthy passes counter sanity",
    rh["counter sanity"][0] is True,
    rh["counter sanity"][1],
)
record(
    "accounting_plane_checks schema 3 healthy passes heartbeat",
    rh["heartbeat"][0] is True,
    rh["heartbeat"][1],
)
record(
    "accounting_plane_checks service_active True is healthy",
    rh["accountd service"][0] is True,
    rh["accountd service"][1],
)
roff = by_name(mod.accounting_plane_checks(
    healthy, service_active=False, raw_days=90, daily_days=90
))
record(
    "accounting_plane_checks service_active False is unhealthy",
    roff["accountd service"][0] is False,
    roff["accountd service"][1],
)

stale = os.path.join(tmp, "plane-stale.db")
sconn = mod.open_db(stale)
old = (datetime.now(timezone.utc) - timedelta(seconds=mod.HEARTBEAT_MAX_AGE_SECONDS + 100)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)
mod.meta_set(sconn, "last_success_at", old)
sconn.commit()
sconn.close()
rs = by_name(mod.accounting_plane_checks(
    stale, service_active=True, raw_days=90, daily_days=90
))
record(
    "accounting_plane_checks stale heartbeat is unhealthy",
    rs["heartbeat"][0] is False,
    rs["heartbeat"][1],
)

neg = os.path.join(tmp, "plane-negative.db")
nconn = mod.open_db(neg)
mod.meta_set(nconn, "last_success_at", mod.utc_now_iso())
nconn.execute(
    """
    INSERT INTO connections(
      connection_id, generation, user_id, node_id,
      started_at, last_seen_at, closed_at, upload_bytes, download_bytes
    ) VALUES ('neg-1', 0, 'u-alice', 'n1',
              '2026-08-14T00:00:00Z', '2026-08-14T01:00:00Z',
              '2026-08-14T01:00:00Z', -5, 10)
    """
)
nconn.commit()
nconn.close()
rn = by_name(mod.accounting_plane_checks(
    neg, service_active=True, raw_days=90, daily_days=90
))
record(
    "accounting_plane_checks negative counter is unhealthy",
    rn["counter sanity"][0] is False,
    rn["counter sanity"][1],
)

nobase = os.path.join(tmp, "plane-open-nobaseline.db")
bconn = mod.open_db(nobase)
mod.meta_set(bconn, "last_success_at", mod.utc_now_iso())
bconn.execute(
    """
    INSERT INTO connections(
      connection_id, generation, user_id, node_id,
      started_at, last_seen_at, closed_at, upload_bytes, download_bytes
    ) VALUES ('open-1', 0, 'u-alice', 'n1',
              '2026-08-14T00:00:00Z', '2026-08-14T01:00:00Z',
              NULL, 100, 200)
    """
)
bconn.commit()
bconn.close()
rb = by_name(mod.accounting_plane_checks(
    nobase, service_active=True, raw_days=90, daily_days=90
))
record(
    "accounting_plane_checks open without baseline is unhealthy",
    rb["baseline sanity"][0] is False,
    rb["baseline sanity"][1],
)

proc = subprocess.run(
    [
        sys.executable, mod_path, "--check-accounting-plane",
        "--db", schema2, "--service-active", "--raw-days", "90", "--daily-days", "90",
    ],
    capture_output=True, text=True,
)
record(
    "accounting_plane CLI reports FAIL schema expected on schema 2",
    proc.returncode != 0 and "FAIL\tschema expected" in proc.stdout,
    (proc.stdout + proc.stderr).replace("\n", " | "),
)

for status, name, detail in rows:
    print(f"{status}\t{name}\t{detail}")
sys.exit(0 if all(s == "PASS" for s, _, _ in rows) else 1)
PY
) || plane_rc=$?
  if [[ -z "$plane_out" ]]; then
    fail "accounting_plane_checks fixtures produced output"
  else
    while IFS=$'\t' read -r plane_status plane_name plane_detail; do
      [[ -n "$plane_status" ]] || continue
      if [[ "$plane_status" == "PASS" ]]; then
        pass "$plane_name"
      else
        fail "${plane_name} (${plane_detail})"
      fi
    done <<< "$plane_out"
  fi
  if (( plane_rc != 0 )) && [[ -z "$plane_out" ]]; then
    fail "accounting_plane_checks python fixtures exited ${plane_rc}"
  fi
else
  fail "python3 required for last_success_at freshness helper tests"
fi

# Phase 2 TASK 40/42: schema 3 restart with empty known_open + poll_baseline,
# and open_db fail-closed on corrupt / future schema_version.
# TASK 38/39/41 already pass in the D7 and retention blocks above.
phase2_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${TEST_TMP}/phase2" "$SAMPLE_USERS" <<'PY' || phase2_rc=$?
import importlib.util, os, sqlite3, sys

mod_path, work, users = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(work, exist_ok=True)
spec = importlib.util.spec_from_file_location("accountd", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.TAG_TO_USER_ID = mod.load_tag_to_user_id(users)

def live_ev(cid, up, dn, ts="2026-08-16T01:00:00Z"):
    return {
        "connection_id": cid,
        "node_id": "n1",
        "user_id": "u-alice",
        "user_tag": "alice",
        "destination_host": "r.example",
        "destination_ip": None,
        "destination_port": 443,
        "network": "tcp",
        "upload_bytes": up,
        "download_bytes": dn,
        "started_at": "2026-08-16T00:00:00Z",
        "ts": ts,
    }

# TASK 40: empty known_open, existing open row + poll_baseline (schema 3).
db = os.path.join(work, "restart.db")
conn = mod.open_db(db)
mod.upsert_connection(
    conn, live_ev("p-restart3", 0, 0), close=False,
    accounted_upload=5000, accounted_download=8000, generation=0,
)
mod.upsert_poll_baseline(
    conn, "p-restart3", 0, 9000, 12000, 5000, 8000, "2026-08-16T01:00:00Z"
)
conn.commit()
event_id = conn.execute(
    "SELECT event_id FROM connections WHERE connection_id='p-restart3' AND generation=0"
).fetchone()[0]

known = {}
known = mod.apply_poll_delta(
    conn,
    [live_ev("p-restart3", 9000, 12000, ts="2026-08-16T01:05:00Z")],
    known,
)
row = conn.execute(
    "SELECT event_id, generation, upload_bytes, download_bytes, closed_at, instance_id "
    "FROM connections WHERE connection_id='p-restart3' AND generation=0"
).fetchone()
assert row[0] == event_id, row
assert row[1] == 0 and row[2] == 5000 and row[3] == 8000, row
assert row[4] is None, row
assert row[5] is None, row
assert known["p-restart3"]["acc_up"] == 5000, known["p-restart3"]
assert known["p-restart3"]["generation"] == 0, known["p-restart3"]
base = mod.load_poll_baseline(conn, "p-restart3")
assert base["generation"] == 0 and base["raw_up"] == 9000 and base["acc_up"] == 5000, base

known = mod.apply_poll_delta(
    conn,
    [live_ev("p-restart3", 9500, 12100, ts="2026-08-16T01:05:05Z")],
    {},
)
row = conn.execute(
    "SELECT event_id, generation, upload_bytes, download_bytes FROM connections "
    "WHERE connection_id='p-restart3' AND generation=0"
).fetchone()
assert row[0] == event_id, row
assert row[1] == 0 and row[2] == 5500 and row[3] == 8100, row
assert known["p-restart3"]["acc_up"] == 5500, known["p-restart3"]
gens = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE connection_id='p-restart3'"
).fetchone()[0]
assert gens == 1, gens
neg = conn.execute(
    "SELECT COUNT(*) FROM connections WHERE upload_bytes < 0 OR download_bytes < 0"
).fetchone()[0]
assert neg == 0, neg
conn.close()

# TASK 42: corrupt / future schema_version → SystemExit, no destructive rewrite.
def schema2_fixture(path, version):
    raw = sqlite3.connect(path)
    raw.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE connections (
          connection_id TEXT PRIMARY KEY,
          node_id TEXT NOT NULL,
          user_id TEXT NOT NULL,
          user_tag TEXT,
          destination_host TEXT,
          destination_ip TEXT,
          destination_port INTEGER,
          network TEXT,
          upload_bytes INTEGER NOT NULL DEFAULT 0,
          download_bytes INTEGER NOT NULL DEFAULT 0,
          started_at TEXT NOT NULL,
          closed_at TEXT,
          last_seen_at TEXT NOT NULL
        );
    """)
    raw.execute("INSERT INTO meta(key,value) VALUES('schema_version', ?)", (version,))
    raw.execute(
        "INSERT INTO connections(connection_id, node_id, user_id, user_tag, "
        "destination_host, destination_ip, destination_port, network, "
        "upload_bytes, download_bytes, started_at, closed_at, last_seen_at) "
        "VALUES ('keep-me', 'n1', 'u-alice', 'alice', 'x.example', NULL, 443, "
        "'tcp', 12345, 67890, '2026-08-16T00:00:00Z', NULL, '2026-08-16T00:00:00Z')"
    )
    raw.commit()
    raw.close()

def assert_fail_closed(path, version):
    try:
        mod.open_db(path)
        raise AssertionError(f"open_db must fail-closed for schema_version={version!r}")
    except SystemExit:
        pass
    probe = sqlite3.connect(path)
    got = probe.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    assert got == version, (got, version)
    cols = [r[1] for r in probe.execute("PRAGMA table_info(connections)")]
    assert "event_id" not in cols, cols
    row = probe.execute(
        "SELECT upload_bytes, download_bytes FROM connections WHERE connection_id='keep-me'"
    ).fetchone()
    assert row == (12345, 67890), row
    tables = {
        r[0] for r in probe.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "connections_v3" not in tables, tables
    probe.close()

bogus = os.path.join(work, "schema-bogus.db")
schema2_fixture(bogus, "bogus")
assert_fail_closed(bogus, "bogus")

future = os.path.join(work, "schema-future.db")
schema2_fixture(future, "4")
assert_fail_closed(future, "4")

# Antique schema 1 without user_id: still fail-closed, no schema 3 rewrite.
antique = os.path.join(work, "schema-antique.db")
raw = sqlite3.connect(antique)
raw.executescript("""
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE connections (
      connection_id TEXT PRIMARY KEY,
      node_id TEXT NOT NULL,
      user_tag TEXT,
      destination_host TEXT,
      upload_bytes INTEGER NOT NULL DEFAULT 0,
      download_bytes INTEGER NOT NULL DEFAULT 0,
      started_at TEXT NOT NULL,
      closed_at TEXT,
      last_seen_at TEXT NOT NULL
    );
""")
raw.execute("INSERT INTO meta(key,value) VALUES('schema_version','1')")
raw.execute(
    "INSERT INTO connections(connection_id, node_id, user_tag, destination_host, "
    "upload_bytes, download_bytes, started_at, last_seen_at) "
    "VALUES ('ghost', 'n1', 'nobody', 'y.example', 9, 8, "
    "'2026-08-16T00:00:00Z', '2026-08-16T00:00:00Z')"
)
raw.commit()
raw.close()
try:
    mod.open_db(antique)
    raise AssertionError("open_db must fail-closed on unmapped schema 1 user_tag")
except SystemExit:
    pass
probe = sqlite3.connect(antique)
assert probe.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "1"
cols = [r[1] for r in probe.execute("PRAGMA table_info(connections)")]
assert "event_id" not in cols, cols
row = probe.execute(
    "SELECT upload_bytes, download_bytes FROM connections WHERE connection_id='ghost'"
).fetchone()
assert row == (9, 8), row
probe.close()
PY
if (( phase2_rc == 0 )); then
  pass "restart empty known_open preserves generation bytes"
  pass "open_db fail-closed on unknown schema_version"
else
  fail "restart empty known_open preserves generation bytes"
  fail "open_db fail-closed on unknown schema_version"
fi

assert_success "soak protocol script exists" \
  test -f "${PROJECT_DIR}/scripts/soak-0.2.7.sh"
assert_success "soak protocol is LIVE-ONLY and not a CI gate" \
  grep -q 'Not invoked by tests/test.sh' "${PROJECT_DIR}/scripts/soak-0.2.7.sh"
assert_success "soak protocol documents 24h READY FOR RC" \
  grep -q 'AC-2.7-09' "${PROJECT_DIR}/scripts/soak-0.2.7.sh"

if [[ -f "${TEST_DIR}/test-fleet.sh" ]]; then
  # shellcheck disable=SC1091
  source "${TEST_DIR}/test-fleet.sh"
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
