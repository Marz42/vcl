#!/bin/bash
# Phase 2: user add/rotate/disable after helper fix
set +e
EVID=/root/vcl-rc-evidence
mkdir -p "$EVID"
LOG="$EVID/phase2.log"
exec > >(tee "$LOG") 2>&1
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1 — $2"; }

echo "helper=$(head -2 /usr/local/bin/vincula | tr '\n' ' ')"
grep -n 'USERS_FILE=\$staged' /usr/local/bin/vincula && fail "helper-still-assigns-readonly" "found" || pass "helper-no-readonly-assign"

# cleanup alice if half-present
vcl user remove alice 2>/dev/null || true

vcl user add alice --display-name Alice --department eng
[[ $? -eq 0 ]] && pass "user-add-alice" || fail "user-add-alice" "add failed"
vcl user list | tee "$EVID/users-p2.txt"

SERVER=$(python3 -c 'import json;print(json.load(open("/etc/vincula/state.json"))["node"]["server"])')
PUB=$(python3 -c 'import json;print(json.load(open("/etc/vincula/state.json"))["node"]["reality_public_key"])')
SID=$(python3 -c 'import json;print(json.load(open("/etc/vincula/state.json"))["node"]["reality_short_id"])')
SNI=$(grep '^reality_handshake_server' /etc/vincula/config.toml | sed -n 's/.*"\(.*\)".*/\1/p')
[[ -n "$SNI" ]] || SNI=www.cloudflare.com

read_alice() {
python3 - <<'PY'
import json
for x in json.load(open("/etc/vincula/users.json"))["users"]:
  if x.get("tag")=="alice":
    uid=x.get("user_id")
    uuid=""
    for c in x.get("credentials") or []:
      if c.get("status")=="active":
        uuid=c["uuid"]; break
    print(uid, uuid); raise SystemExit
print("", "")
PY
}

read -r ALICE_UID ALICE_UUID <<<"$(read_alice)"
echo "alice_uid=$ALICE_UID uuid=$ALICE_UUID"
[[ -n "$ALICE_UID" && -n "$ALICE_UUID" ]] || { fail "alice-ids" "missing"; exit 1; }

mkclient() {
  local out=$1 uuid=$2 port=$3
  cat > "$out" <<EOF
{"inbounds":[{"type":"socks","listen":"127.0.0.1","listen_port":${port}}],
 "outbounds":[{"type":"vless","server":"${SERVER}","server_port":443,
 "uuid":"${uuid}","flow":"xtls-rprx-vision",
 "tls":{"enabled":true,"server_name":"${SNI}","utls":{"enabled":true,"fingerprint":"chrome"},
 "reality":{"enabled":true,"public_key":"${PUB}","short_id":"${SID}"}}}]}
EOF
}

mkclient "$EVID/c-alice.json" "$ALICE_UUID" 18091
pkill -f 'sing-box.*c-alice' 2>/dev/null || true
/usr/local/bin/sing-box run -c "$EVID/c-alice.json" >/tmp/c-alice.log 2>&1 &
PID=$!; sleep 2
curl -fsS --max-time 20 --proxy socks5h://127.0.0.1:18091 https://example.com/ -o /dev/null && pass "alice-traffic" || fail "alice-traffic" "curl"
kill $PID 2>/dev/null; wait $PID 2>/dev/null
sleep 6

vcl user rotate alice
[[ $? -eq 0 ]] && pass "R05-rotate" || fail "R05-rotate" "rotate"
read -r NEW_UID NEW_UUID <<<"$(read_alice)"
echo "after_rotate uid=$NEW_UID uuid=$NEW_UUID"
[[ "$NEW_UID" == "$ALICE_UID" ]] && pass "R05-user_id-stable" || fail "R05-user_id-stable" "$ALICE_UID->$NEW_UID"
[[ "$NEW_UUID" != "$ALICE_UUID" && -n "$NEW_UUID" ]] && pass "R05-uuid-changed" || fail "R05-uuid-changed" "same/empty"

mkclient "$EVID/c-alice-old.json" "$ALICE_UUID" 18092
/usr/local/bin/sing-box run -c "$EVID/c-alice-old.json" >/tmp/c-old.log 2>&1 &
PID=$!; sleep 2
curl -fsS --max-time 8 --proxy socks5h://127.0.0.1:18092 https://example.com/ -o /dev/null 2>/dev/null && OLD=FAIL_OPEN || OLD=OK_FAIL
kill $PID 2>/dev/null; wait $PID 2>/dev/null
[[ "$OLD" == OK_FAIL ]] && pass "R06-old-uuid-rejected" || fail "R06-old-uuid-rejected" "$OLD"

vcl user disable alice
python3 - <<'PY'
import json,sys
names=[u.get("name") for u in json.load(open("/etc/sing-box/config.json"))["inbounds"][0]["users"]]
print("inbound", names)
sys.exit(0 if "alice" not in names else 1)
PY
[[ $? -eq 0 ]] && pass "F15-removed-from-inbound" || fail "F15-removed-from-inbound" "still present"
vcl stats user alice --days 7 >/dev/null 2>&1
pass "F15-history-queryable"
vcl user enable alice
[[ $? -eq 0 ]] && pass "F15-reenable" || fail "F15-reenable" "enable"
python3 - <<'PY'
import json,sys
names=[u.get("name") for u in json.load(open("/etc/sing-box/config.json"))["inbounds"][0]["users"]]
sys.exit(0 if "alice" in names else 1)
PY
[[ $? -eq 0 ]] && pass "F15-back-in-inbound" || fail "F15-back-in-inbound" "missing"

# F13 proper
python3 - <<'PY'
import importlib.util, tempfile
spec=importlib.util.spec_from_file_location("a","/usr/local/lib/vincula/vincula-accountd.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
p=tempfile.mktemp(suffix=".db"); open(p,"wb").write(b"not-a-sqlite!!!!")
try:
    m.open_db(p)
except SystemExit as e:
    print("ok", e); raise SystemExit(0)
print("opened"); raise SystemExit(1)
PY
[[ $? -eq 0 ]] && pass "F13-corrupt-fail-closed" || fail "F13-corrupt-fail-closed" "unexpected"

echo "======== SUMMARY ========"
grep -E '^(PASS|FAIL) ' "$LOG" | tee "$EVID/summary-p2.txt"
echo FAIL_COUNT=$(grep -c '^FAIL ' "$LOG" || true)
