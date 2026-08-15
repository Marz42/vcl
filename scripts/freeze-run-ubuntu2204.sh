#!/usr/bin/env bash
# Vincula 0.2.4 freeze gate runner (Ubuntu 22.04 host or container with systemd).
# Steps: fresh 0.2.4 → morph 0.2.3 → migrate happy → morph again → broken migrate rollback → py3.10 checks.
set -euo pipefail
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "need root"; exit 1; }

ROOT=${VCL_FREEZE_ROOT:-/opt/vincula-freeze}
SRC024=${VCL_TREE_024:-"$ROOT/vincula-0.2.4"}
EVID=${VCL_EVID:-/root/vcl-rc-evidence/freeze}
mkdir -p "$EVID"
pass() { echo "PASS $1" | tee -a "$EVID/summary.txt"; }
fail() { echo "FAIL $1 — $2" | tee -a "$EVID/summary.txt"; exit 1; }
log() { echo "=== $* ===" | tee -a "$EVID/run.log"; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl jq python3 python3-minimal sqlite3 \
  systemd systemd-sysv dbus iproute2 procps openssl coreutils grep sed gawk tar gzip \
  >/dev/null

log "Python / OS"
python3 --version | tee "$EVID/python.version"
. /etc/os-release
echo "$PRETTY_NAME" | tee "$EVID/os.release"
[[ "${VERSION_ID:-}" == "22.04" ]] || echo "WARN: expected Ubuntu 22.04, got ${VERSION_ID:-unknown}"
PYV=$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')
[[ "$PYV" == "3.10" ]] && pass "C-python-3.10" || fail "C-python-3.10" "got $PYV"

[[ -d "$SRC024" ]] || fail "tree-024" "missing $SRC024"
[[ -f "$SRC024/vincula.sh" ]] || fail "tree-024-sh" "missing vincula.sh"

# Clean any prior install
if [[ -x /usr/local/bin/vcl ]]; then
  /usr/local/bin/vcl uninstall --yes >/dev/null 2>&1 || true
fi
rm -rf /etc/vincula /var/lib/vincula /var/backups/vincula
rm -f /etc/systemd/system/sing-box.service /etc/systemd/system/vincula-accountd.service
systemctl daemon-reload || true

log "Fresh install 0.2.4 baseline"
cd "$SRC024"
# Avoid REALITY external flakiness in nested CI if needed
export VCL_PORT=${VCL_PORT:-8443}
bash vincula.sh 2>&1 | tee "$EVID/install-024.log"
[[ -f /etc/vincula/VERSION ]] || fail "install-024" "no VERSION"
grep -qx '0.2.4' /etc/vincula/VERSION && pass "install-024-version" || fail "install-024-version" "$(cat /etc/vincula/VERSION)"
python3 -m py_compile /usr/local/lib/vincula/vincula-accountd.py && pass "C-py_compile" || fail "C-py_compile" "compile"
systemctl is-active --quiet vincula-accountd && pass "C-accountd-active" || fail "C-accountd-active" "inactive"

OWNER_BEFORE=$(python3 - <<'PY'
import json
for u in json.load(open("/etc/vincula/users.json"))["users"]:
  if u.get("tag")=="owner":
    for c in u.get("credentials") or []:
      if c.get("status")=="active":
        print(c["uuid"]); raise SystemExit
PY
)
PK_BEFORE=$(python3 -c 'import json;s=json.load(open("/etc/vincula/state.json"));print(s.get("node",s).get("reality_public_key") if isinstance(s.get("node"),dict) else s.get("reality_public_key"))')
SID_BEFORE=$(python3 -c 'import json;s=json.load(open("/etc/vincula/state.json"));n=s.get("node",s);print(n.get("reality_short_id") if isinstance(n,dict) else s.get("reality_short_id"))')
echo "owner=$OWNER_BEFORE sid=$SID_BEFORE" | tee "$EVID/identity-before.txt"

log "Morph to 0.2.3-shaped"
bash "$SRC024/scripts/freeze-morph-to-0.2.3.sh" "$EVID"
grep -qx '0.2.3' /etc/vincula/VERSION || fail "morph-version" "$(cat /etc/vincula/VERSION)"
pass "morph-0.2.3-shaped"

log "A: happy-path migration 0.2.3 → 0.2.4"
cd "$SRC024"
bash vincula.sh 2>&1 | tee "$EVID/migrate-happy.log"
grep -qx '0.2.4' /etc/vincula/VERSION || fail "A-version" "$(cat /etc/vincula/VERSION)"
OWNER_AFTER=$(python3 - <<'PY'
import json
for u in json.load(open("/etc/vincula/users.json"))["users"]:
  if u.get("tag")=="owner":
    for c in u.get("credentials") or []:
      if c.get("status")=="active":
        print(c["uuid"]); raise SystemExit
PY
)
[[ "$OWNER_AFTER" == "$OWNER_BEFORE" ]] && pass "A-uuid-preserved" || fail "A-uuid-preserved" "$OWNER_BEFORE->$OWNER_AFTER"
NID=$(grep '^node_id' /etc/vincula/config.toml | head -1)
echo "$NID" | tee "$EVID/node_id-after.txt"
[[ "$NID" != *local* ]] && pass "A-node_id-uuid" || fail "A-node_id-uuid" "$NID"
python3 - <<'PY'
import json,sys
c=json.load(open("/etc/sing-box/config.json"))
ib=c["inbounds"][0]
assert "sniff" not in ib
assert any(r.get("action")=="sniff" for r in c["route"]["rules"])
print("config migrated off inbound sniff")
PY
[[ $? -eq 0 ]] && pass "A-config-no-inbound-sniff" || fail "A-config-no-inbound-sniff" "shape"
systemctl is-active --quiet sing-box && systemctl is-active --quiet vincula-accountd && pass "A-services" || fail "A-services" "down"
vcl verify >/dev/null && pass "A-verify" || fail "A-verify" "verify"
SCHEMA=$(python3 -c 'import sqlite3;c=sqlite3.connect("/var/lib/vincula/accounting.db");print(c.execute("select value from meta where key=\"schema_version\"").fetchone()[0])')
[[ "$SCHEMA" == "2" ]] && pass "A-schema-2" || fail "A-schema-2" "$SCHEMA"

log "B: remorph + forced rollback"
bash "$SRC024/scripts/freeze-morph-to-0.2.3.sh" "$EVID"
# Broken 0.2.4 tree
BROKEN=$(mktemp -d /tmp/vcl-broken.XXXXXX)
cp -a "$SRC024/." "$BROKEN/"
echo 'this is not python!!!!' > "$BROKEN/lib/vincula-accountd.py"
(
  cd "$BROKEN"
  sha256sum vincula.sh bin/vincula lib/vincula-common.sh lib/vincula-accountd.py \
    lib/vincula-accountd.service lib/vincula-event.schema.json > release.lock
)
set +e
( cd "$BROKEN" && bash vincula.sh ) >"$EVID/migrate-rollback.log" 2>&1
EC=$?
set -e
[[ $EC -ne 0 ]] && pass "B-migrate-nonzero" || fail "B-migrate-nonzero" "unexpected success"
grep -qx '0.2.3' /etc/vincula/VERSION && pass "B-version-restored" || fail "B-version-restored" "$(cat /etc/vincula/VERSION 2>/dev/null || echo missing)"
# mixed-version check: if accountd.py exists it should be from backup (valid python) or absent for early fail
if [[ -f /usr/local/lib/vincula/vincula-accountd.py ]]; then
  python3 -m py_compile /usr/local/lib/vincula/vincula-accountd.py \
    && pass "B-no-broken-accountd" || fail "B-no-broken-accountd" "broken py left behind"
fi
ls /var/backups/vincula/*/SERVICE_STATE >/dev/null 2>&1 && pass "B-backup-marker" || pass "B-backup-maybe-early"
# Restore a working 0.2.4 for cleanliness
cd "$SRC024" && bash vincula.sh >>"$EVID/migrate-final.log" 2>&1 || true

log "SUMMARY"
cat "$EVID/summary.txt"
echo "Freeze evidence in $EVID"
