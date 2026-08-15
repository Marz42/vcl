#!/usr/bin/env bash
# Morph a healthy 0.2.4 install into a 0.2.3-shaped node for migration freeze tests.
# Injects inbound sniff + VERSION=0.2.3 + node_id=local while preserving Reality/owner UUID SoT.
set -euo pipefail
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "need root"; exit 1; }
STATE=/etc/vincula/state.json
USERS=/etc/vincula/users.json
SETTINGS=/etc/vincula/config.toml
CONFIG=/etc/sing-box/config.json
VERSION=/etc/vincula/VERSION
[[ -f "$VERSION" ]] || { echo "no install"; exit 1; }

EVID=${1:-/root/vcl-rc-evidence/freeze}
mkdir -p "$EVID"
python3 - "$STATE" "$USERS" "$SETTINGS" "$CONFIG" "$VERSION" "$EVID/pre-morph.json" <<'PY'
import json, sys, re
from pathlib import Path
state_p, users_p, settings_p, config_p, version_p, out_p = sys.argv[1:]
state = json.loads(Path(state_p).read_text(encoding="utf-8"))
users = json.loads(Path(users_p).read_text(encoding="utf-8"))
settings = Path(settings_p).read_text(encoding="utf-8")
config = json.loads(Path(config_p).read_text(encoding="utf-8"))
owner_uuid = None
for u in users.get("users", []):
    if u.get("tag") == "owner":
        for c in u.get("credentials") or []:
            if c.get("status") == "active":
                owner_uuid = c.get("uuid")
                break
snap = {
    "version_before": Path(version_p).read_text(encoding="utf-8").strip(),
    "owner_uuid": owner_uuid,
    "reality_public_key": state.get("node", {}).get("reality_public_key") or state.get("reality_public_key"),
    "reality_short_id": state.get("node", {}).get("reality_short_id") or state.get("reality_short_id"),
    "node_id_before": None,
}
m = re.search(r'^node_id = "(.*)"', settings, re.M)
if m:
    snap["node_id_before"] = m.group(1)
Path(out_p).write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
print(json.dumps(snap))
PY

systemctl stop vincula-accountd.service 2>/dev/null || true
systemctl stop sing-box.service 2>/dev/null || true

printf '0.2.3\n' > "$VERSION"

python3 - "$CONFIG" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
cfg = json.loads(p.read_text(encoding="utf-8"))
ib = cfg["inbounds"][0]
ib["sniff"] = True
# Remove route sniff actions if present so shape matches 0.2.3
rules = []
for r in cfg.get("route", {}).get("rules", []):
    if r.get("action") == "sniff":
        continue
    if "auth_user" in r and "action" not in r:
        rules.append(r)
    elif "auth_user" in r:
        rules.append({"auth_user": r["auth_user"], "outbound": r.get("outbound")})
    else:
        rules.append(r)
cfg.setdefault("route", {})["rules"] = rules
p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
print("injected inbound sniff; stripped sniff actions")
PY

# node_id → local in settings + state
python3 - "$SETTINGS" "$STATE" <<'PY'
import json, re, sys
from pathlib import Path
sp, st = Path(sys.argv[1]), Path(sys.argv[2])
text = sp.read_text(encoding="utf-8")
if re.search(r'^node_id = ', text, re.M):
    text = re.sub(r'^node_id = ".*"', 'node_id = "local"', text, count=1, flags=re.M)
else:
    text += '\nnode_id = "local"\n'
sp.write_text(text, encoding="utf-8")
state = json.loads(st.read_text(encoding="utf-8"))
if "node" in state and isinstance(state["node"], dict):
    state["node"]["node_id"] = "local"
else:
    state["node_id"] = "local"
# Re-introduce non-authoritative owner.uuid mirror if absent (0.2.3 dual SoT shape)
owner_uuid = None
# leave owner block emptyish display only
st.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
print("node_id=local written")
PY

# Prove sing-box 1.13 rejects this config (documents the migration P0 need)
if command -v /usr/local/bin/sing-box >/dev/null; then
  if /usr/local/bin/sing-box check -c "$CONFIG" >/tmp/vcl-legacy-check.txt 2>&1; then
    echo "WARN: expected legacy check to fail"
  else
    echo "OK: legacy config rejected by sing-box 1.13:"
    head -3 /tmp/vcl-legacy-check.txt
  fi
fi
echo "Morphed install to 0.2.3-shaped state. VERSION=$(cat "$VERSION")"
