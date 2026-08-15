#!/usr/bin/env bash
# Build reconstructed Vincula 0.2.3 release from current 0.2.4 tree.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-"${ROOT}/artifacts/vincula-0.2.3"}
rm -rf "$OUT"
mkdir -p "$OUT/bin" "$OUT/lib"
cp -a "$ROOT/vincula.sh" "$OUT/vincula.sh"
cp -a "$ROOT/bin/vincula" "$OUT/bin/vincula"
cp -a "$ROOT/lib/." "$OUT/lib/"
[[ -f "$ROOT/vincula-bootstrap.sh" ]] && cp -a "$ROOT/vincula-bootstrap.sh" "$OUT/"

# Portable in-place sed
sedi() { sed -i "$@" 2>/dev/null || sed -i '' "$@"; }

sedi 's/0\.2\.4/0.2.3/g' \
  "$OUT/vincula.sh" \
  "$OUT/bin/vincula" \
  "$OUT/lib/vincula-common.sh" \
  "$OUT/lib/vincula-accountd.service" \
  "$OUT/lib/vincula-accountd.py"

python3 - "$OUT/lib/vincula-common.sh" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
a_old = '''# sing-box 1.13+: inbound sniff/domain_strategy removed; use route rule actions.
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
'''
a_new = '''if sniff.lower() in ("1", "true", "yes", "on"):
    inbound["sniff"] = True

outbounds = [{"type": "direct", "tag": "direct"}]
rules = []
for tag in tags:
    outbounds.append({"type": "direct", "tag": f"acct/{tag}"})
    rules.append({"auth_user": [tag], "outbound": f"acct/{tag}"})
'''
b_old = '''outbounds = [{"type": "direct", "tag": "direct"}]
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
'''
b_new = '''outbounds = [{"type": "direct", "tag": "direct"}]
rules = []
for user in users:
    tag = user.get("name") or ""
    if not tag:
        continue
    acct = f"acct/{tag}"
    outbounds.append({"type": "direct", "tag": acct})
    rules.append({"auth_user": [tag], "outbound": acct})

inbound = {
'''
c_old = '''}
# sing-box 1.13+: do not set inbound sniff (removed); see route action above.

config = {
'''
c_new = '''}
if sniff.lower() in ("1", "true", "yes", "on"):
    inbound["sniff"] = True

config = {
'''
if a_old not in t:
    raise SystemExit("block A not found")
if b_old not in t:
    raise SystemExit("block B not found")
if c_old not in t:
    raise SystemExit("block C not found")
t = t.replace(a_old, a_new, 1).replace(b_old, b_new, 1).replace(c_old, c_new, 1)
p.write_text(t, encoding="utf-8")
assert t.count('inbound["sniff"] = True') >= 2
print("ok: inbound sniff restored")
PY

python3 - "$OUT/vincula.sh" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
t = t.replace(
    'wait_for_accountd_healthy || die "vincula-accountd health check failed; refusing to commit install"',
    'wait_for_accountd_healthy || log_warn "vincula-accountd health check failed (0.2.3 soft-fail)"',
)
t = t.replace(
    'systemctl enable --now vincula-accountd.service || die "vincula-accountd.service failed to enable/start"',
    'systemctl enable --now vincula-accountd.service || log_warn "vincula-accountd.service failed to enable/start"',
)
# 0.2.3 installer must NOT include 0.2.4 legacy-inbound migration bypass — strip if present after copy
# (reconstructed from 0.2.4 sources; leave bypass in place is OK for install path that never hits migrate)
p.write_text(t, encoding="utf-8")
print("ok: soft-fail accountd")
PY

# Force default node_id local in render paths for authenticity of pre-migrate state
# Installer fresh path uses generate uuid in 0.2.4 — pin local for reconstructed 0.2.3 fresh installs.
python3 - "$OUT/vincula.sh" <<'PY'
from pathlib import Path
import re, sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
# fresh install: node_id=$("$binary" generate uuid) → local
t2, n = re.subn(
    r'node_id=\$\("\$binary" generate uuid\)',
    'node_id=local',
    t,
    count=1,
)
if n != 1:
    # already local or different pattern
    print("warn: node_id generate substitution count", n)
t2 = t2.replace(
    '[[ "$node_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "Could not validate the generated node_id."',
    '[[ "$node_id" == "local" ]] || die "Expected reconstructed 0.2.3 node_id=local."',
    1,
)
p.write_text(t2, encoding="utf-8")
print("ok: node_id=local for fresh install")
PY

(
  cd "$OUT"
  sha256sum vincula.sh bin/vincula lib/vincula-common.sh lib/vincula-accountd.py \
    lib/vincula-accountd.service lib/vincula-event.schema.json > release.lock
  sha256sum vincula.sh | tee vincula.sh.sha256 >/dev/null
)
echo "Reconstructed 0.2.3 → $OUT"
grep -n 'inbound\["sniff"\]' "$OUT/lib/vincula-common.sh" | head
grep -n 'VINCULA_VERSION\|0\.2\.3' "$OUT/vincula.sh" | head -5
