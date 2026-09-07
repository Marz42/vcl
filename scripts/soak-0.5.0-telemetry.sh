#!/usr/bin/env bash
# 0.5.0 LIVE telemetry soak + node state-growth measurement (G5 / AC-5.0-10).
#
# LIVE-ONLY. Not invoked by tests/test.sh.
# Never prints IPs, URIs, UUIDs, Reality keys, or Clash secrets into evidence.
#
# Usage:
#   VCL_SOAK_LIVE=1 VCL_FLEET_HOME=... bash scripts/soak-0.5.0-telemetry.sh NODE
#   VCL_SOAK_LIVE=1 ... bash scripts/soak-0.5.0-telemetry.sh NODE --iterations 1000
#
# Evidence (local; do not commit secrets):
#   ${SOAK_EVIDENCE_DIR:-$HOME/vcl-rc-evidence/0.5.0-soak}/<NODE>/
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
FLEET_BIN="${VCL_FLEET_BIN:-${ROOT}/bin/vcl-fleet}"
ITERATIONS=1000
NODE=""
LIVE=0

usage() {
  cat <<'EOF'
Vincula 0.5.0 LIVE telemetry soak (1000×) + state-growth measurement.

Requires: VCL_SOAK_LIVE=1 or --live, VCL_FLEET_HOME (or workspace), NODE name.

Options:
  --iterations N   default 1000
  --live           same as VCL_SOAK_LIVE=1
  -h, --help

Evidence dir: $SOAK_EVIDENCE_DIR or ~/vcl-rc-evidence/0.5.0-soak/<NODE>/
Writes: before.json, after.json, soak.log, SUMMARY.txt (no secrets).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --live) LIVE=1; shift ;;
    --iterations) ITERATIONS=${2:?}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*)
      printf 'unknown option: %s\n' "$1" >&2
      exit 2
      ;;
    *)
      if [[ -z "$NODE" ]]; then NODE=$1; shift
      else printf 'unexpected arg: %s\n' "$1" >&2; exit 2
      fi
      ;;
  esac
done

if [[ "${VCL_SOAK_LIVE:-0}" == "1" ]]; then LIVE=1; fi
if (( LIVE != 1 )); then
  printf 'REFUSED: LIVE-ONLY. Pass --live or set VCL_SOAK_LIVE=1.\n' >&2
  exit 2
fi
if [[ -z "$NODE" ]]; then
  printf 'usage: %s NODE [--iterations N] --live\n' "$0" >&2
  exit 2
fi
if [[ ! -x "$FLEET_BIN" ]]; then
  printf 'missing vcl-fleet: %s\n' "$FLEET_BIN" >&2
  exit 2
fi

EVIDENCE_ROOT="${SOAK_EVIDENCE_DIR:-${HOME}/vcl-rc-evidence/0.5.0-soak}"
OUT="${EVIDENCE_ROOT}/${NODE}"
mkdir -p "$OUT"
LOG="${OUT}/soak.log"
: >"$LOG"

fleet() { "$FLEET_BIN" "$@"; }

log() {
  printf '%s\n' "$*" | tee -a "$LOG"
}

take_snapshot() {
  local dest=$1
  python3 - "$ROOT" "$NODE" "$dest" <<'PY'
import base64
import importlib.util
import json
import sys
from pathlib import Path

root, name, dest = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
fleet_path = root / "lib/vincula-fleet.py"
spec = importlib.util.spec_from_file_location("fleet", fleet_path)
fleet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleet)

node = fleet.require_node(fleet.load_registry(), name)
ident = fleet.node_identity_file_for_class(node, "admin")
remote_py = r'''
import json, os, subprocess, time
from pathlib import Path

def du_bytes(path):
    p = Path(path)
    if not p.exists():
        return None
    if p.is_file():
        return p.stat().st_size
    total = 0
    for root, dirs, files in os.walk(p):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total

def file_size(path):
    p = Path(path)
    return p.stat().st_size if p.is_file() else None

def count_files(path):
    p = Path(path)
    if not p.is_dir():
        return None
    n = 0
    for root, dirs, files in os.walk(p):
        n += len(files)
    return n

def systemctl_active(unit):
    try:
        r = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return (r.stdout or "").strip() or None
    except Exception:
        return None

def restart_count(unit):
    try:
        r = subprocess.run(
            ["systemctl", "show", unit, "-p", "NRestarts", "--value"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        text = (r.stdout or "").strip()
        return int(text) if text.isdigit() else None
    except Exception:
        return None

print(json.dumps({
    "observed_at_host": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "paths": {
        "state_dir_bytes": du_bytes("/var/lib/vincula"),
        "log_dir_bytes": du_bytes("/var/log/vincula"),
        "accounting_db_bytes": file_size("/var/lib/vincula/accounting.db"),
        "state_dir_file_count": count_files("/var/lib/vincula"),
        "log_dir_file_count": count_files("/var/log/vincula"),
    },
    "services": {
        "sing-box": {
            "active": systemctl_active("sing-box.service"),
            "nrestarts": restart_count("sing-box.service"),
        },
        "vincula-accountd": {
            "active": systemctl_active("vincula-accountd.service"),
            "nrestarts": restart_count("vincula-accountd.service"),
        },
    },
}, sort_keys=True))
'''
payload = base64.b64encode(remote_py.encode()).decode()
remote_cmd = [
    "python3",
    "-c",
    "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode())",
    payload,
]
proc = fleet.ssh_run(
    node["ssh_host"],
    node["ssh_user"],
    int(node.get("ssh_port") or 22),
    remote_cmd,
    batch=True,
    identity_file=ident,
    timeout=60,
)
if proc.returncode != 0:
    dest.write_text(
        json.dumps({"ok": False, "error": "ssh snapshot failed", "rc": proc.returncode}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    raise SystemExit(f"snapshot ssh failed rc={proc.returncode}")
doc = json.loads(proc.stdout)
doc["ok"] = True
tel = fleet.fetch_node_telemetry(node)
tel_safe = {"state": tel.get("state")}
if tel.get("state") == "OK" and isinstance(tel.get("snapshot"), dict):
    snap = tel["snapshot"]
    tel_safe["uptime_seconds"] = snap.get("uptime_seconds")
    sb = snap.get("sing_box") if isinstance(snap.get("sing_box"), dict) else {}
    ac = snap.get("accountd") if isinstance(snap.get("accountd"), dict) else {}
    tel_safe["sing_box_active"] = sb.get("active")
    tel_safe["sing_box_last_restart_at"] = sb.get("last_restart_at")
    tel_safe["accountd_active"] = ac.get("active")
    tel_safe["export_seq"] = ac.get("export_seq")
doc["telemetry"] = tel_safe
dest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {dest}")
PY
}

log "=== 0.5.0 telemetry soak ==="
log "node=${NODE} iterations=${ITERATIONS}"
log "evidence=${OUT}"
log "fleet_home=${VCL_FLEET_HOME:-}"

pre_rc=0
pre_json=$(fleet telemetry "$NODE" --json) || pre_rc=$?
# Store state/detail only (drop snapshot body from evidence copy)
python3 - "$pre_json" "${OUT}/preflight-telemetry.json" <<'PY'
import json, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
safe = {
    "state": doc.get("state"),
    "detail": doc.get("detail"),
    "credential_class": doc.get("credential_class"),
}
if doc.get("state") == "OK" and isinstance(doc.get("snapshot"), dict):
    snap = doc["snapshot"]
    safe["schema"] = snap.get("schema")
    safe["uptime_seconds"] = snap.get("uptime_seconds")
Path(sys.argv[2]).write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
assert doc.get("state") == "OK", safe
print("preflight telemetry OK")
PY
if (( pre_rc != 0 )); then
  log "PREFLIGHT FAIL: telemetry exit ${pre_rc}"
  exit 1
fi

log "Taking BEFORE snapshot..."
take_snapshot "${OUT}/before.json"

fail_at=0
ok=0
t0=$(date +%s)
for i in $(seq 1 "$ITERATIONS"); do
  if fleet telemetry "$NODE" --json >/dev/null; then
    ok=$((ok + 1))
  else
    fail_at=$i
    log "FAIL at iteration ${i}"
    break
  fi
  if (( i % 100 == 0 )); then
    log "progress ${i}/${ITERATIONS} ok=${ok}"
  fi
done
t1=$(date +%s)
elapsed=$((t1 - t0))

log "Taking AFTER snapshot..."
take_snapshot "${OUT}/after.json"

python3 - "$OUT" "$NODE" "$ITERATIONS" "$ok" "$fail_at" "$elapsed" <<'PY'
import json, sys
from pathlib import Path

out, node, iterations, ok, fail_at, elapsed = sys.argv[1:7]
out = Path(out)
iterations = int(iterations)
ok = int(ok)
fail_at = int(fail_at)
elapsed = int(elapsed)
before = json.loads((out / "before.json").read_text(encoding="utf-8"))
after = json.loads((out / "after.json").read_text(encoding="utf-8"))

def dig(doc, *keys):
    cur = doc
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur

checks = []

def compare(label, a, b, *, allow_non_decrease=False, max_growth=None, must_equal=False):
    if a is None or b is None:
        checks.append((label, "SKIP", "missing metric"))
        return
    if must_equal:
        checks.append((label, "PASS" if a == b else "FAIL", f"{a} → {b}"))
        return
    if allow_non_decrease and isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if b < a:
            checks.append((label, "FAIL", f"decreased {a} → {b}"))
        elif max_growth is not None and (b - a) > max_growth:
            checks.append((label, "FAIL", f"growth {b - a} exceeds {max_growth} ({a} → {b})"))
        else:
            checks.append((label, "PASS", f"{a} → {b} (Δ {b - a})"))
        return
    checks.append((label, "PASS" if a == b else "WARN", f"{a} → {b}"))

compare(
    "state_dir_bytes",
    dig(before, "paths", "state_dir_bytes"),
    dig(after, "paths", "state_dir_bytes"),
    allow_non_decrease=True,
    # Live nodes accumulate accounting under traffic; gate leaks via file_count + restarts.
    max_growth=16 * 1024 * 1024,
)
compare(
    "accounting_db_bytes",
    dig(before, "paths", "accounting_db_bytes"),
    dig(after, "paths", "accounting_db_bytes"),
    allow_non_decrease=True,
    max_growth=16 * 1024 * 1024,
)
compare(
    "state_dir_file_count",
    dig(before, "paths", "state_dir_file_count"),
    dig(after, "paths", "state_dir_file_count"),
    allow_non_decrease=True,
    max_growth=8,
)
compare(
    "log_dir_file_count",
    dig(before, "paths", "log_dir_file_count"),
    dig(after, "paths", "log_dir_file_count"),
    allow_non_decrease=True,
    max_growth=32,
)
compare(
    "sing-box NRestarts",
    dig(before, "services", "sing-box", "nrestarts"),
    dig(after, "services", "sing-box", "nrestarts"),
    must_equal=True,
)
compare(
    "accountd NRestarts",
    dig(before, "services", "vincula-accountd", "nrestarts"),
    dig(after, "services", "vincula-accountd", "nrestarts"),
    must_equal=True,
)
compare(
    "sing-box active",
    dig(before, "services", "sing-box", "active"),
    dig(after, "services", "sing-box", "active"),
    must_equal=True,
)
compare(
    "accountd active",
    dig(before, "services", "vincula-accountd", "active"),
    dig(after, "services", "vincula-accountd", "active"),
    must_equal=True,
)

soak_pass = fail_at == 0 and ok == iterations
growth_fail = any(s == "FAIL" for _, s, _ in checks)
overall = "PASS LIVE" if soak_pass and not growth_fail else "FAIL LIVE"

lines = [
    f"node={node}",
    f"iterations={iterations}",
    f"ok={ok}",
    f"fail_at={fail_at}",
    f"elapsed_seconds={elapsed}",
    f"soak={('PASS' if soak_pass else 'FAIL')}",
    f"state_growth={('PASS' if not growth_fail else 'FAIL')}",
    f"outcome={overall}",
    "",
    "metrics:",
]
for label, status, detail in checks:
    lines.append(f"  [{status}] {label}: {detail}")
text = "\n".join(lines) + "\n"
(out / "SUMMARY.txt").write_text(text, encoding="utf-8")
print(text)
if overall != "PASS LIVE":
    raise SystemExit(1)
PY

log "Done. Summary: ${OUT}/SUMMARY.txt"
