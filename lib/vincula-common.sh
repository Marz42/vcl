#!/usr/bin/env bash
# Shared pure helpers for vincula installer, helper, and tests.
# Sourced only; not executed as a main program.

# shellcheck shell=bash

readonly VINCULA_COMMON_VERSION="0.2.8"

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

toml_set() {
  local file=$1 key=$2 value=$3
  local tmp
  [[ -n "$file" && -n "$key" && -f "$file" ]] || return 1
  tmp=$(mktemp "${file}.XXXXXX") || return 1
  if awk -F' = ' -v key="$key" -v value="$value" '
    BEGIN { found=0 }
    $1 == key {
      print key " = " value
      found=1
      next
    }
    { print }
    END {
      if (!found) print key " = " value
    }
  ' "$file" > "$tmp"; then
    mv -f -- "$tmp" "$file"
  else
    rm -f -- "$tmp"
    return 1
  fi
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

# User tags: lowercase alphanumeric, underscore, hyphen, dot; start with alnum; max 32.
# No reserved tags beyond the format itself.
is_valid_user_tag() {
  local tag=$1
  [[ "$tag" =~ ^[a-z0-9][a-z0-9._-]{0,31}$ ]]
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

# Probe Clash /connections on localhost. When secret is non-empty, send Bearer.
clash_api_reachable_with_secret() {
  local port=$1 secret=${2:-}
  local url="http://127.0.0.1:${port}/connections"
  local args=(-fsS --max-time 5)
  if [[ -n "$secret" ]]; then
    args+=(-H "Authorization: Bearer ${secret}")
  fi
  curl "${args[@]}" "$url" >/dev/null 2>&1
}

# Print fresh|stale|missing|unreadable for meta.last_success_at. Exit 0 iff fresh.
# Fresh means the timestamp exists and is at most max_age_seconds old (default 300).
accounting_last_success_status() {
  local db=$1
  local max_age=${2:-300}
  if [[ -z "$db" || ! -r "$db" ]]; then
    printf 'unreadable\n'
    return 1
  fi
  python3 - "$db" "$max_age" <<'PY'
import sqlite3, sys
from datetime import datetime, timezone

db = sys.argv[1]
try:
    max_age = float(sys.argv[2])
except ValueError:
    print("unreadable")
    raise SystemExit(1)
try:
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT value FROM meta WHERE key='last_success_at'").fetchone()
    conn.close()
except Exception:
    print("unreadable")
    raise SystemExit(1)
if not row or not row[0]:
    print("missing")
    raise SystemExit(1)
ts = str(row[0]).strip()
if ts.endswith("Z"):
    ts = ts[:-1] + "+00:00"
try:
    when = datetime.fromisoformat(ts)
except ValueError:
    print("unreadable")
    raise SystemExit(1)
if when.tzinfo is None:
    when = when.replace(tzinfo=timezone.utc)
age = (datetime.now(timezone.utc) - when).total_seconds()
if age <= max_age:
    print("fresh")
    raise SystemExit(0)
print("stale")
raise SystemExit(1)
PY
}

accounting_last_success_fresh() {
  local status
  status=$(accounting_last_success_status "$@") || true
  [[ "$status" == "fresh" ]]
}

# Retry a few seconds when last_success_at is missing (first poll ~5s after start).
# A stale timestamp cannot become fresh by waiting, so that fails immediately.
accounting_last_success_fresh_wait() {
  local db=$1
  local max_age=${2:-300}
  local attempts=${3:-3}
  local delay=${4:-2}
  local i status
  for (( i = 0; i < attempts; i++ )); do
    status=$(accounting_last_success_status "$db" "$max_age") || true
    case "$status" in
      fresh) return 0 ;;
      stale) return 1 ;;
    esac
    if (( i + 1 < attempts )); then
      sleep "$delay"
    fi
  done
  return 1
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

# Mutate schema 2 users registry. action: add|disable|enable|rotate|set
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
elif action == "set":
    tag, display_name, department = args
    user = find(tag)
    if not user:
        raise SystemExit(f"user not found: {tag}")
    user["display_name"] = display_name
    user["department"] = department
else:
    raise SystemExit(f"unknown action: {action}")

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
}

users_registry_show() {
  local users_file=$1 tag=$2
  users_registry_show_human "$users_file" "$tag"
}

users_registry_show_human() {
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
    print(f"Tag:           {user.get('tag') or ''}")
    print(f"Display name:  {user.get('display_name') or ''}")
    print(f"Department:    {user.get('department') or '-'}")
    print(f"User ID:       {user.get('user_id') or ''}")
    print(f"Enabled:       {'yes' if user.get('enabled') else 'no'}")
    print(f"Created at:    {user.get('created_at') or ''}")
    print()
    print("Credentials:")
    print(f"{'credential_id':<38} {'status':<10} {'created_at':<22} revoked_at")
    for cred in user.get("credentials") or []:
        cid = cred.get("credential_id") or "-"
        status = cred.get("status") or "-"
        created = cred.get("created_at") or "-"
        revoked = cred.get("revoked_at") or "-"
        print(f"{cid:<38} {status:<10} {created:<22} {revoked}")
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
print(f"{'TAG':<10} {'NAME':<14} {'DEPARTMENT':<16} STATUS")
for user in data.get("users", []):
    tag = user.get("tag") or ""
    name = user.get("display_name") or tag
    dept = user.get("department") or "-"
    status = "active" if user.get("enabled") else "disabled"
    print(f"{tag:<10} {name:<14} {dept:<16} {status}")
PY
}

users_registry_field() {
  local users_file=$1 tag=$2 field=$3
  require_python3 || return 1
  python3 - "$users_file" "$tag" "$field" <<'PY'
import json, sys

path, tag, field = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
for user in data.get("users", []):
    if user.get("tag") != tag:
        continue
    if field == "active_credential_id":
        for cred in user.get("credentials") or []:
            if cred.get("status") == "active" and cred.get("credential_id"):
                print(cred["credential_id"])
                raise SystemExit(0)
        raise SystemExit(f"user {tag} has no active credential")
    value = user.get(field)
    if value is None:
        raise SystemExit(f"field {field} missing for user {tag}")
    print(value)
    raise SystemExit(0)
raise SystemExit(f"user not found: {tag}")
PY
}

users_registry_verify() {
  local users_file=$1 config_file=$2
  require_python3 || return 1
  python3 - "$users_file" "$config_file" <<'PY'
import json, sys
from collections import Counter

users_path, config_path = sys.argv[1], sys.argv[2]
fail = 0

def ok(msg):
    print(f"✓ {msg}")

def bad(msg):
    global fail
    fail = 1
    print(f"✗ {msg}")

with open(users_path, encoding="utf-8") as f:
    data = json.load(f)

print("[Registry]")
if data.get("schema_version") == 2:
    ok("schema_version 2")
else:
    bad(f"schema_version {data.get('schema_version')!r} (expected 2)")

users = data.get("users") or []
ok(f"{len(users)} users")

user_ids = [u.get("user_id") for u in users if u.get("user_id")]
tags = [u.get("tag") for u in users if u.get("tag")]
cred_ids = []
active_uuids = []
for u in users:
    for c in u.get("credentials") or []:
        if c.get("credential_id"):
            cred_ids.append(c["credential_id"])
        if c.get("status") == "active" and c.get("uuid"):
            active_uuids.append(c["uuid"])

def unique(label, values):
    if len(values) == len(set(values)):
        ok(f"{label} unique")
    else:
        dups = [k for k, n in Counter(values).items() if n > 1]
        bad(f"{label} not unique: {', '.join(map(str, dups[:5]))}")

unique("user IDs", user_ids)
unique("tags", tags)
unique("credential IDs", cred_ids)

print()
print("[Credentials]")
unique("active UUIDs", active_uuids)

enabled_active_ok = True
for u in users:
    if not u.get("enabled"):
        continue
    actives = [c for c in (u.get("credentials") or []) if c.get("status") == "active" and c.get("uuid")]
    if len(actives) != 1:
        enabled_active_ok = False
        bad(f"enabled user {u.get('tag')} has {len(actives)} active credential(s) (expected 1)")
if enabled_active_ok:
    ok("each enabled user has exactly one active credential")

revoked_ok = True
for u in users:
    for c in u.get("credentials") or []:
        if c.get("status") == "revoked" and c.get("uuid") in {
            x.get("uuid") for x in (u.get("credentials") or []) if x.get("status") == "active"
        }:
            revoked_ok = False
if revoked_ok:
    ok("revoked credentials excluded from active set")

print()
print("[sing-box]")
try:
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
except OSError as exc:
    bad(f"cannot read config: {exc}")
    config = {}

inbound_users = []
for inbound in config.get("inbounds") or []:
    if inbound.get("tag") == "vless-reality-in" or inbound.get("type") == "vless":
        inbound_users = inbound.get("users") or []
        break

inbound_by_name = {}
for iu in inbound_users:
    name = iu.get("name")
    if name:
        inbound_by_name[name] = iu.get("uuid")

disabled_ok = True
for u in users:
    if u.get("enabled"):
        continue
    tag = u.get("tag")
    if tag in inbound_by_name:
        disabled_ok = False
        bad(f"disabled user {tag} still present in sing-box inbound users")
if disabled_ok:
    ok("disabled users have no sing-box auth entry")

expected = {}
for u in users:
    if not u.get("enabled"):
        continue
    tag = u.get("tag")
    for c in u.get("credentials") or []:
        if c.get("status") == "active" and c.get("uuid"):
            expected[tag] = c["uuid"]
            break

auth_ok = True
for tag, uuid in expected.items():
    if tag not in inbound_by_name:
        auth_ok = False
        bad(f"active registry user {tag} missing from sing-box inbound")
    elif inbound_by_name[tag] != uuid:
        auth_ok = False
        bad(f"UUID mismatch for {tag}")
for name in inbound_by_name:
    if name not in expected:
        auth_ok = False
        bad(f"sing-box inbound user {name} not an enabled registry active credential")
if auth_ok:
    ok("generated auth users match Registry")

print()
print("[Accounting]")
map_ok = True
for u in users:
    if not u.get("enabled"):
        continue
    if not u.get("user_id") or not u.get("tag"):
        map_ok = False
        bad(f"enabled user missing user_id/tag for accounting map")
if map_ok:
    ok("all active auth users map to stable user_id")

print()
if fail:
    print("Result: FAIL")
    raise SystemExit(1)
print("Result: PASS")
raise SystemExit(0)
PY
}

# Validate/import CSV users into a candidate registry.
# dry_run=1: print report only. dry_run=0: write out_users_json; optional out_cred_csv.
# URI args (server..short_id) required when writing credential CSV.
users_import_prepare() {
  local csv_path=$1 users_file=$2 node_id=$3
  local out_users_json=${4:-}
  local out_cred_csv=${5:-}
  local include_uuid=${6:-0}
  local dry_run=${7:-1}
  local server=${8:-}
  local port=${9:-}
  local reality_host=${10:-}
  local public_key=${11:-}
  local short_id=${12:-}
  require_python3 || return 1
  python3 - "$csv_path" "$users_file" "$node_id" "$out_users_json" "$out_cred_csv" \
    "$include_uuid" "$dry_run" "$server" "$port" "$reality_host" "$public_key" "$short_id" <<'PY'
import csv, json, re, sys, uuid
from datetime import datetime, timezone

(
    csv_path, users_file, node_id, out_users_json, out_cred_csv,
    include_uuid, dry_run, server, port, reality_host, public_key, short_id,
) = sys.argv[1:13]
include_uuid = include_uuid in ("1", "true", "yes", "on")
dry_run = dry_run in ("1", "true", "yes", "on")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

with open(users_file, encoding="utf-8") as f:
    data = json.load(f)
if data.get("schema_version") != 2:
    print("ERROR: users.json must be schema_version 2", file=sys.stderr)
    raise SystemExit(1)

existing_tags = {u.get("tag") for u in data.get("users") or [] if u.get("tag")}
errors = []
rows = []
seen_in_file = {}

try:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "tag" not in [h.strip() for h in reader.fieldnames if h]:
            print("ERROR: CSV header must include tag", file=sys.stderr)
            raise SystemExit(1)
        # normalize fieldnames
        field_map = {h: h.strip() for h in reader.fieldnames if h}
        for i, raw in enumerate(reader, start=2):
            row = {field_map.get(k, k): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
            tag = (row.get("tag") or "").strip()
            display_name = (row.get("display_name") or "").strip()
            department = (row.get("department") or "").strip()
            if not tag and not display_name and not department:
                continue
            rows.append((i, tag, display_name, department))
            if not tag:
                errors.append(f'line {i}: missing tag')
                continue
            if not TAG_RE.match(tag):
                errors.append(f'line {i}: invalid tag "{tag}"')
            if tag in seen_in_file:
                errors.append(f"line {i}: duplicate tag {tag}")
            else:
                seen_in_file[tag] = i
            if tag in existing_tags:
                errors.append(f"line {i}: tag {tag} already exists")
except FileNotFoundError:
    print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
    raise SystemExit(1)

valid_new = []
for i, tag, display_name, department in rows:
    if any(e.startswith(f"line {i}:") for e in errors):
        continue
    valid_new.append((tag, display_name or tag, department))

conflicts = sum(1 for e in errors if "already exists" in e)
invalid_rows = len({e.split(":", 1)[0] for e in errors if "already exists" not in e})

print("User import dry-run" if dry_run else "User import plan")
print()
print(f"Input rows:       {len(rows)}")
print(f"Valid new users:  {len(valid_new)}")
print(f"Conflicts:        {conflicts}")
print(f"Invalid rows:     {invalid_rows}")
if errors:
    print()
    print("Errors:")
    for e in errors:
        print(f"  {e}")
if dry_run:
    print()
    print("No changes were made.")
    raise SystemExit(0 if not errors else 1)

if errors:
    raise SystemExit(1)

def uri_authority(host):
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host

def render_uri(vless_uuid, tag):
    auth = uri_authority(server)
    return (
        f"vless://{vless_uuid}@{auth}:{port}"
        f"?encryption=none&flow=xtls-rprx-vision&security=reality"
        f"&sni={reality_host}&fp=chrome&pbk={public_key}&sid={short_id}"
        f"&type=tcp#vincula-{tag}"
    )

new_users = []
cred_rows = []
for tag, display_name, department in valid_new:
    user_id = str(uuid.uuid4())
    credential_id = str(uuid.uuid4())
    vless_uuid = str(uuid.uuid4())
    new_users.append({
        "user_id": user_id,
        "tag": tag,
        "display_name": display_name,
        "department": department,
        "enabled": True,
        "created_at": now,
        "credentials": [{
            "credential_id": credential_id,
            "node_id": node_id,
            "uuid": vless_uuid,
            "status": "active",
            "created_at": now,
            "revoked_at": None,
        }],
    })
    if out_cred_csv:
        row = {
            "tag": tag,
            "display_name": display_name,
            "department": department,
            "user_id": user_id,
            "credential_id": credential_id,
            "vless_uri": render_uri(vless_uuid, tag),
        }
        if include_uuid:
            row["uuid"] = vless_uuid
        cred_rows.append(row)

data["users"] = list(data.get("users") or []) + new_users
if not out_users_json:
    print("ERROR: out_users_json path required for non-dry-run", file=sys.stderr)
    raise SystemExit(1)
with open(out_users_json, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")

if out_cred_csv:
    if not all([server, port, reality_host, public_key, short_id]):
        print("ERROR: URI parameters required for credential CSV", file=sys.stderr)
        raise SystemExit(1)
    fieldnames = ["tag", "display_name", "department", "user_id", "credential_id", "vless_uri"]
    if include_uuid:
        fieldnames.append("uuid")
    with open(out_cred_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cred_rows)
raise SystemExit(0)
PY
}

# Export users CSV. credentials=0: metadata. credentials=1: credential export with URIs.
# output empty => stdout (metadata only).
users_export_csv() {
  local users_file=$1
  local output=${2:-}
  local credentials=${3:-0}
  local include_uuid=${4:-0}
  local server=${5:-}
  local port=${6:-}
  local reality_host=${7:-}
  local public_key=${8:-}
  local short_id=${9:-}
  require_python3 || return 1
  python3 - "$users_file" "$output" "$credentials" "$include_uuid" \
    "$server" "$port" "$reality_host" "$public_key" "$short_id" <<'PY'
import csv, json, sys

(
    users_file, output, credentials, include_uuid,
    server, port, reality_host, public_key, short_id,
) = sys.argv[1:10]
credentials = credentials in ("1", "true", "yes", "on")
include_uuid = include_uuid in ("1", "true", "yes", "on")

with open(users_file, encoding="utf-8") as f:
    data = json.load(f)

def uri_authority(host):
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host

def render_uri(vless_uuid, tag):
    auth = uri_authority(server)
    return (
        f"vless://{vless_uuid}@{auth}:{port}"
        f"?encryption=none&flow=xtls-rprx-vision&security=reality"
        f"&sni={reality_host}&fp=chrome&pbk={public_key}&sid={short_id}"
        f"&type=tcp#vincula-{tag}"
    )

rows = []
if credentials:
    if not output:
        print("ERROR: credential export requires an output path", file=sys.stderr)
        raise SystemExit(1)
    if not all([server, port, reality_host, public_key, short_id]):
        print("ERROR: URI parameters required for credential export", file=sys.stderr)
        raise SystemExit(1)
    fieldnames = ["tag", "display_name", "department", "user_id", "credential_id", "vless_uri"]
    if include_uuid:
        fieldnames.append("uuid")
    for user in data.get("users") or []:
        active = None
        for cred in user.get("credentials") or []:
            if cred.get("status") == "active":
                active = cred
                break
        if not active:
            continue
        row = {
            "tag": user.get("tag") or "",
            "display_name": user.get("display_name") or "",
            "department": user.get("department") or "",
            "user_id": user.get("user_id") or "",
            "credential_id": active.get("credential_id") or "",
            "vless_uri": render_uri(active.get("uuid") or "", user.get("tag") or ""),
        }
        if include_uuid:
            row["uuid"] = active.get("uuid") or ""
        rows.append(row)
else:
    fieldnames = ["tag", "display_name", "department", "status", "user_id"]
    for user in data.get("users") or []:
        rows.append({
            "tag": user.get("tag") or "",
            "display_name": user.get("display_name") or "",
            "department": user.get("department") or "",
            "status": "active" if user.get("enabled") else "disabled",
            "user_id": user.get("user_id") or "",
        })

if output:
    with open(output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
else:
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
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
