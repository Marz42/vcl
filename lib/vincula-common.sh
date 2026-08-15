#!/usr/bin/env bash
# Shared pure helpers for vincula installer, helper, and tests.
# Sourced only; not executed as a main program.

# shellcheck shell=bash

readonly VINCULA_COMMON_VERSION="0.2.4"

json_quoted_field() {
  local file=$1 field=$2
  sed -n "s/^[[:space:]]*\"${field}\":[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "$file" | head -n 1
}

json_numeric_field() {
  local file=$1 field=$2
  sed -n "s/^[[:space:]]*\"${field}\":[[:space:]]*\\([0-9][0-9]*\\).*/\\1/p" "$file" | head -n 1
}

json_bool_field() {
  local file=$1 field=$2
  sed -n "s/^[[:space:]]*\"${field}\":[[:space:]]*\\(true\\|false\\).*/\\1/p" "$file" | head -n 1
}

toml_get() {
  local file=$1 key=$2
  awk -F' = ' -v key="$key" '$1 == key {value=$2; gsub(/^"|"$/, "", value); print value; exit}' "$file"
}

vless_query() {
  local query=$1 want=$2 pair key value
  local IFS='&'
  local -a pairs
  read -r -a pairs <<< "$query"
  for pair in "${pairs[@]}"; do
    key=${pair%%=*}
    value=${pair#*=}
    if [[ "$key" == "$want" ]]; then
      printf '%s\n' "$value"
      return 0
    fi
  done
  return 1
}

parse_vless_uri() {
  local uri=$1 rest hostport query
  uri=${uri//$'\r'/}
  uri=${uri//$'\n'/}
  [[ "$uri" == vless://* ]] || return 1
  rest=${uri#vless://}
  rest=${rest%%#*}
  VLESS_UUID=${rest%%@*}
  rest=${rest#*@}
  if [[ "$rest" == *'?'* ]]; then
    hostport=${rest%%'?'*}
    query=${rest#*'?'}
  else
    hostport=$rest
    query=""
  fi
  if [[ "$hostport" == \[* ]]; then
    [[ "$hostport" == *\]:* ]] || return 1
    VLESS_HOST=${hostport#\[}
    VLESS_HOST=${VLESS_HOST%%\]*}
    VLESS_PORT=${hostport##*\]:}
  else
    VLESS_HOST=${hostport%:*}
    VLESS_PORT=${hostport##*:}
  fi
  VLESS_SNI=$(vless_query "$query" sni || true)
  VLESS_PBK=$(vless_query "$query" pbk || true)
  VLESS_SID=$(vless_query "$query" sid || true)
  VLESS_FLOW=$(vless_query "$query" flow || true)
  [[ -n "$VLESS_UUID" && -n "$VLESS_HOST" && -n "$VLESS_PORT" ]]
}

uri_authority_host() {
  local server=$1
  if [[ "$server" == *:* ]]; then
    printf '[%s]\n' "$server"
  else
    printf '%s\n' "$server"
  fi
}

render_vless_uri() {
  local uuid=$1 server=$2 port=$3 server_name=$4 public_key=$5 short_id=$6
  local tag=${7:-owner}
  local authority
  authority=$(uri_authority_host "$server")
  printf 'vless://%s@%s:%s?encryption=none&flow=xtls-rprx-vision&security=reality&sni=%s&fp=chrome&pbk=%s&sid=%s&type=tcp#vincula-%s\n' \
    "$uuid" "$authority" "$port" "$server_name" "$public_key" "$short_id" "$tag"
}

verify_identity_consistency() {
  local state_file=$1 settings_file=$2 config_file=$3 uri_file=$4
  local users_file=${5:-}
  local fail=0 uri
  local uuid_canonical uuid_config uuid_uri
  local pbk_state sid_state sid_config sni_state sni_settings sni_config sni_handshake
  local port_state port_settings port_config flow_config private_state private_config

  uri=$(< "$uri_file")
  parse_vless_uri "$uri" || {
    printf '✗ UUID consistent\n'
    printf '✗ Reality key consistent\n'
    printf '✗ short ID consistent\n'
    printf '✗ SNI consistent\n'
    printf '✗ port consistent\n'
    printf '✗ flow consistent\n'
    return 1
  }

  if [[ -n "$users_file" && -f "$users_file" ]]; then
    uuid_canonical=$(owner_active_uuid_from_registry "$users_file")
  else
    uuid_canonical=$(json_quoted_field "$state_file" uuid)
  fi
  uuid_config=$(json_quoted_field "$config_file" uuid)
  uuid_uri=$VLESS_UUID
  pbk_state=$(json_quoted_field "$state_file" reality_public_key)
  private_state=$(json_quoted_field "$state_file" reality_private_key)
  private_config=$(json_quoted_field "$config_file" private_key)
  sid_state=$(json_quoted_field "$state_file" reality_short_id)
  sid_config=$(json_quoted_field "$config_file" short_id)
  sni_state=$(json_quoted_field "$state_file" reality_server_name)
  sni_settings=$(toml_get "$settings_file" reality_server_name)
  sni_config=$(json_quoted_field "$config_file" server_name)
  sni_handshake=$(json_quoted_field "$config_file" server)
  port_state=$(json_numeric_field "$state_file" port)
  port_settings=$(toml_get "$settings_file" port)
  port_config=$(json_numeric_field "$config_file" listen_port)
  flow_config=$(json_quoted_field "$config_file" flow)

  if [[ -n "$uuid_canonical" && "$uuid_canonical" == "$uuid_config" && "$uuid_config" == "$uuid_uri" ]]; then
    printf '✓ UUID consistent\n'
  else
    printf '✗ UUID consistent\n'
    fail=1
  fi
  if [[ -n "$pbk_state" && "$pbk_state" == "$VLESS_PBK" && -n "$private_state" && "$private_state" == "$private_config" ]]; then
    printf '✓ Reality key consistent\n'
  else
    printf '✗ Reality key consistent\n'
    fail=1
  fi
  if [[ -n "$sid_state" && "$sid_state" == "$sid_config" && "$sid_config" == "$VLESS_SID" ]]; then
    printf '✓ short ID consistent\n'
  else
    printf '✗ short ID consistent\n'
    fail=1
  fi
  if [[ -n "$sni_state" && "$sni_state" == "$sni_settings" && "$sni_settings" == "$sni_config" && "$sni_config" == "$sni_handshake" && "$sni_handshake" == "$VLESS_SNI" ]]; then
    printf '✓ SNI consistent\n'
  else
    printf '✗ SNI consistent\n'
    fail=1
  fi
  if [[ -n "$port_state" && "$port_state" == "$port_settings" && "$port_settings" == "$port_config" && "$port_config" == "$VLESS_PORT" ]]; then
    printf '✓ port consistent\n'
  else
    printf '✗ port consistent\n'
    fail=1
  fi
  if [[ "$flow_config" == "xtls-rprx-vision" && "$VLESS_FLOW" == "xtls-rprx-vision" ]]; then
    printf '✓ flow consistent\n'
  else
    printf '✗ flow consistent\n'
    fail=1
  fi
  (( fail == 0 ))
}

# User tags: lowercase alphanumeric, underscore, hyphen; start with alnum; max 32.
# No reserved tags beyond the format itself.
is_valid_user_tag() {
  local tag=$1
  [[ ${#tag} -ge 1 && ${#tag} -le 32 ]] || return 1
  [[ "$tag" =~ ^[a-z0-9][a-z0-9_-]*$ ]]
}

require_python3() {
  command -v python3 >/dev/null 2>&1 || {
    printf 'ERROR: python3 is required for users.json registry operations.\n' >&2
    return 1
  }
}

generate_uuid_v4() {
  require_python3 || return 1
  python3 -c 'import uuid; print(uuid.uuid4())'
}

generate_clash_api_secret() {
  require_python3 || return 1
  python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
}

# Render sing-box config with localhost Clash API + acct/<tag> outbounds/routes.
# Args: output users_file private_key short_id port reality_host listen clash_port clash_secret [sniff=true|false]
render_sing_box_config_accounting() {
  local output=$1 users_file=$2 private_key=$3 short_id=$4 port=$5 reality_host=$6
  local listen=${7:-0.0.0.0}
  local clash_port=${8:-9090}
  local clash_secret=${9:-}
  local sniff=${10:-true}
  require_python3 || return 1
  python3 - "$output" "$users_file" "$private_key" "$short_id" "$port" "$reality_host" \
    "$listen" "$clash_port" "$clash_secret" "$sniff" <<'PY'
import json, sys

(
    output, users_file, private_key, short_id, port, reality_host,
    listen, clash_port, clash_secret, sniff,
) = sys.argv[1:]

with open(users_file, encoding="utf-8") as f:
    data = json.load(f)

users = []
tags = []
for user in data.get("users", []):
    if not user.get("enabled", False):
        continue
    tag = user.get("tag") or ""
    active = None
    for cred in user.get("credentials") or []:
        if cred.get("status") == "active" and cred.get("uuid"):
            active = cred
            break
    if not active or not tag:
        continue
    users.append({
        "name": tag,
        "uuid": active["uuid"],
        "flow": "xtls-rprx-vision",
    })
    tags.append(tag)

if not users:
    raise SystemExit("no enabled users with active credentials")

inbound = {
    "type": "vless",
    "tag": "vless-reality-in",
    "listen": listen,
    "listen_port": int(port),
    "users": users,
    "tls": {
        "enabled": True,
        "server_name": reality_host,
        "reality": {
            "enabled": True,
            "handshake": {
                "server": reality_host,
                "server_port": 443,
            },
            "private_key": private_key,
            "short_id": short_id,
        },
    },
}
# sing-box 1.13+: inbound sniff/domain_strategy removed; use route rule actions.
# https://sing-box.sagernet.org/migration/#migrate-legacy-inbound-fields-to-rule-actions

outbounds = [{"type": "direct", "tag": "direct"}]
rules = []
if sniff.lower() in ("1", "true", "yes", "on"):
    rules.append({
        "inbound": ["vless-reality-in"],
        "action": "sniff",
    })
for tag in tags:
    outbounds.append({"type": "direct", "tag": f"acct/{tag}"})
    rules.append({
        "auth_user": [tag],
        "action": "route",
        "outbound": f"acct/{tag}",
    })

cfg = {
    "log": {"level": "info", "timestamp": True},
    "inbounds": [inbound],
    "outbounds": outbounds,
    "route": {
        "rules": rules,
        "final": "direct",
    },
    "experimental": {
        "clash_api": {
            "external_controller": f"127.0.0.1:{int(clash_port)}",
            "secret": clash_secret,
        }
    },
}

with open(output, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
}

# Emit inbound users JSON array fragment for sing-box from schema 2 users.json.
inbound_users_json_from_registry() {
  local users_file=$1
  require_python3 || return 1
  python3 - "$users_file" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
users = []
for user in data.get("users", []):
    if not user.get("enabled", False):
        continue
    tag = user.get("tag") or ""
    active = None
    for cred in user.get("credentials") or []:
        if cred.get("status") == "active" and cred.get("uuid"):
            active = cred
            break
    if not active:
        continue
    users.append({
        "name": tag,
        "uuid": active["uuid"],
        "flow": "xtls-rprx-vision",
    })
if not users:
    raise SystemExit("no enabled users with active credentials")
# Pretty-print so line-oriented json_quoted_field can read uuid/flow.
print(json.dumps(users, ensure_ascii=False, indent=2))
PY
}

owner_active_uuid_from_registry() {
  local users_file=$1
  require_python3 || return 1
  python3 - "$users_file" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
for user in data.get("users", []):
    if user.get("tag") != "owner":
        continue
    for cred in user.get("credentials") or []:
        if cred.get("status") == "active" and cred.get("uuid"):
            print(cred["uuid"])
            raise SystemExit(0)
    raise SystemExit("owner has no active credential")
raise SystemExit("owner user not found")
PY
}

# Return "tag\tuuid" lines for each enabled user with an active credential.
registry_enabled_active_pairs() {
  local users_file=$1
  require_python3 || return 1
  python3 - "$users_file" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
for user in data.get("users", []):
    if not user.get("enabled", False):
        continue
    tag = user.get("tag") or ""
    for cred in user.get("credentials") or []:
        if cred.get("status") == "active" and cred.get("uuid"):
            print(f"{tag}\t{cred['uuid']}")
            break
PY
}

verify_users_in_config() {
  local users_file=$1 config_file=$2
  local fail=0 line tag uuid
  while IFS=$'\t' read -r tag uuid; do
    [[ -n "$tag" && -n "$uuid" ]] || continue
    if grep -q "\"name\": \"${tag}\"" "$config_file" && grep -q "\"uuid\": \"${uuid}\"" "$config_file"; then
      printf '✓ user %s present in config\n' "$tag"
    else
      printf '✗ user %s present in config\n' "$tag"
      fail=1
    fi
  done < <(registry_enabled_active_pairs "$users_file")
  (( fail == 0 ))
}

# Migrate schema 1 users.json to schema 2, preserving owner UUID. Writes to output path.
migrate_users_to_schema2() {
  local input=$1 output=$2 node_id=${3:-local}
  require_python3 || return 1
  python3 - "$input" "$output" "$node_id" <<'PY'
import json, sys, uuid
from datetime import datetime, timezone

src, dst, node_id = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src, encoding="utf-8") as f:
    data = json.load(f)

schema = data.get("schema_version", 1)
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

if schema >= 2:
    # Ensure required fields exist; rewrite to dst.
    for user in data.get("users", []):
        user.setdefault("user_id", str(uuid.uuid4()))
        user.setdefault("display_name", user.get("tag", "").title() or "User")
        user.setdefault("department", "")
        user.setdefault("created_at", now)
        for cred in user.get("credentials") or []:
            cred.setdefault("credential_id", str(uuid.uuid4()))
            existing = cred.get("node_id") or cred.pop("node", None)
            if not existing or existing == "local":
                cred["node_id"] = node_id
            cred.setdefault("revoked_at", None)
    data["schema_version"] = 2
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    raise SystemExit(0)

# schema 1 → 2
out_users = []
for user in data.get("users", []):
    tag = user.get("tag") or "owner"
    enabled = bool(user.get("enabled", True))
    creds_out = []
    for cred in user.get("credentials") or []:
        existing_nid = cred.get("node_id") or cred.get("node") or node_id
        if not existing_nid or existing_nid == "local":
            existing_nid = node_id
        creds_out.append({
            "credential_id": str(uuid.uuid4()),
            "node_id": existing_nid,
            "uuid": cred["uuid"],
            "status": cred.get("status") or "active",
            "created_at": cred.get("created_at") or now,
            "revoked_at": cred.get("revoked_at"),
        })
    out_users.append({
        "user_id": str(uuid.uuid4()),
        "tag": tag,
        "display_name": "Owner" if tag == "owner" else tag,
        "department": "",
        "enabled": enabled,
        "created_at": (creds_out[0]["created_at"] if creds_out else now),
        "credentials": creds_out,
    })

out = {"schema_version": 2, "users": out_users}
with open(dst, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
    f.write("\n")
PY
}

# Mutate schema 2 users registry. action: add|remove|disable|enable|rotate
# Extra env/args via python argv.
users_registry_mutate() {
  local users_file=$1 action=$2
  shift 2
  require_python3 || return 1
  python3 - "$users_file" "$action" "$@" <<'PY'
import json, sys, uuid
from datetime import datetime, timezone

path, action = sys.argv[1], sys.argv[2]
args = sys.argv[3:]
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

with open(path, encoding="utf-8") as f:
    data = json.load(f)

if data.get("schema_version") != 2:
    raise SystemExit("users.json must be schema_version 2")

users = data.setdefault("users", [])

def find(tag):
    for u in users:
        if u.get("tag") == tag:
            return u
    return None

def enabled_count():
    return sum(1 for u in users if u.get("enabled"))

if action == "add":
    tag, display_name, department, vless_uuid, node_id = args
    if find(tag):
        raise SystemExit(f"user tag already exists: {tag}")
    users.append({
        "user_id": str(uuid.uuid4()),
        "tag": tag,
        "display_name": display_name or tag,
        "department": department or "",
        "enabled": True,
        "created_at": now,
        "credentials": [{
            "credential_id": str(uuid.uuid4()),
            "node_id": node_id,
            "uuid": vless_uuid,
            "status": "active",
            "created_at": now,
            "revoked_at": None,
        }],
    })
elif action == "remove":
    tag, = args
    user = find(tag)
    if not user:
        raise SystemExit(f"user not found: {tag}")
    if tag == "owner":
        raise SystemExit("refusing to remove the owner user")
    if user.get("enabled") and enabled_count() <= 1:
        raise SystemExit("refusing to remove the last enabled user")
    users[:] = [u for u in users if u.get("tag") != tag]
elif action == "disable":
    tag, = args
    user = find(tag)
    if not user:
        raise SystemExit(f"user not found: {tag}")
    if user.get("enabled") and enabled_count() <= 1:
        raise SystemExit("refusing to disable the last enabled user")
    user["enabled"] = False
elif action == "enable":
    tag, = args
    user = find(tag)
    if not user:
        raise SystemExit(f"user not found: {tag}")
    user["enabled"] = True
elif action == "rotate":
    tag, new_uuid, node_id = args
    user = find(tag)
    if not user:
        raise SystemExit(f"user not found: {tag}")
    found_active = False
    for cred in user.get("credentials") or []:
        if cred.get("status") == "active":
            cred["status"] = "revoked"
            cred["revoked_at"] = now
            found_active = True
    if not found_active:
        raise SystemExit(f"user {tag} has no active credential to rotate")
    user.setdefault("credentials", []).append({
        "credential_id": str(uuid.uuid4()),
        "node_id": node_id,
        "uuid": new_uuid,
        "status": "active",
        "created_at": now,
        "revoked_at": None,
    })
else:
    raise SystemExit(f"unknown action: {action}")

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
}

users_registry_show() {
  local users_file=$1 tag=$2
  require_python3 || return 1
  python3 - "$users_file" "$tag" <<'PY'
import json, sys
path, tag = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
for user in data.get("users", []):
    if user.get("tag") == tag:
        print(json.dumps(user, indent=2, ensure_ascii=False))
        raise SystemExit(0)
raise SystemExit(f"user not found: {tag}")
PY
}

users_registry_list() {
  local users_file=$1
  require_python3 || return 1
  python3 - "$users_file" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
print(f"{'TAG':<20} {'ENABLED':<8} {'DEPARTMENT':<16} ACTIVE_UUID")
for user in data.get("users", []):
    tag = user.get("tag") or ""
    enabled = "yes" if user.get("enabled") else "no"
    dept = user.get("department") or ""
    active = "-"
    for cred in user.get("credentials") or []:
        if cred.get("status") == "active":
            active = cred.get("uuid") or "-"
            break
    print(f"{tag:<20} {enabled:<8} {dept:<16} {active}")
PY
}

active_uuid_for_tag() {
  local users_file=$1 tag=$2
  require_python3 || return 1
  python3 - "$users_file" "$tag" <<'PY'
import json, sys
path, tag = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
for user in data.get("users", []):
    if user.get("tag") != tag:
        continue
    for cred in user.get("credentials") or []:
        if cred.get("status") == "active" and cred.get("uuid"):
            print(cred["uuid"])
            raise SystemExit(0)
    raise SystemExit(f"user {tag} has no active credential")
raise SystemExit(f"user not found: {tag}")
PY
}

# Write production sing-box config with localhost-only Clash API and per-user
# accounting outbounds (acct/<tag>) routed via auth_user rules.
# users_json: JSON array of inbound users ({name,uuid,flow}).
write_sing_box_server_config() {
  local output=$1 users_json=$2 private_key=$3 short_id=$4 port=$5 reality_host=$6
  local listen=${7:-0.0.0.0}
  local clash_api_port=${8:-9090}
  local clash_secret=${9:-}
  local sniff=${10:-true}
  require_python3 || return 1
  python3 - "$output" "$users_json" "$private_key" "$short_id" "$port" "$reality_host" \
    "$listen" "$clash_api_port" "$clash_secret" "$sniff" <<'PY'
import json, sys

(
    output,
    users_json,
    private_key,
    short_id,
    port,
    reality_host,
    listen,
    clash_api_port,
    clash_secret,
    sniff,
) = sys.argv[1:11]

users = json.loads(users_json)
if not isinstance(users, list) or not users:
    raise SystemExit("users_json must be a non-empty JSON array")

outbounds = [{"type": "direct", "tag": "direct"}]
rules = []
if sniff.lower() in ("1", "true", "yes", "on"):
    rules.append({
        "inbound": ["vless-reality-in"],
        "action": "sniff",
    })
for user in users:
    tag = user.get("name") or ""
    if not tag:
        continue
    acct = f"acct/{tag}"
    outbounds.append({"type": "direct", "tag": acct})
    rules.append({
        "auth_user": [tag],
        "action": "route",
        "outbound": acct,
    })

inbound = {
    "type": "vless",
    "tag": "vless-reality-in",
    "listen": listen,
    "listen_port": int(port),
    "users": users,
    "tls": {
        "enabled": True,
        "server_name": reality_host,
        "reality": {
            "enabled": True,
            "handshake": {"server": reality_host, "server_port": 443},
            "private_key": private_key,
            "short_id": short_id,
        },
    },
}
# sing-box 1.13+: do not set inbound sniff (removed); see route action above.

config = {
    "log": {"level": "info", "timestamp": True},
    "inbounds": [inbound],
    "outbounds": outbounds,
    "route": {"rules": rules, "final": "direct"},
    "experimental": {
        "clash_api": {
            "external_controller": f"127.0.0.1:{int(clash_api_port)}",
            "secret": clash_secret,
        }
    },
}

with open(output, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
}
