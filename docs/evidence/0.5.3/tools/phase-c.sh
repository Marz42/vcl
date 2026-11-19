#!/usr/bin/env bash
# Phase C preparation/collection: 24h soak around the frozen 0.5.3 candidate.
#
#   bash tmp/phase-c.sh                 # prep: copies + preflight + telemetry soak burst
#                                       #       + start the 24h monitor and the 5-min sampler
#   bash tmp/phase-c.sh --collect       # after >=24h: stop, sample, series stats, summary, bundle
#
# Instruments (see docs/plans/RC_0.5.3_VERIFICATION_PLAN.md §5):
#   * scripts/soak-0.5.0-telemetry.sh  (1000x telemetry burst + node state-growth PASS/FAIL digest)
#   * vcl-fleet monitor                (unbuffered, 24h; health/findings/timeline/observation cache)
#   * a 5-minute cache-only sampler    (proxy success/failure, findings, timeline, DB sizes,
#                                       freshness, cache write errors)
#
# Isolation: production workspace/state/bindings are copied into $C_ROOT (the
# production roots are only read); every write lands in the copies.
#
# Env: C_ROOT, PROD_WS, PROD_STATE, PROD_CONFIG, CTRL_ZIP, SOAK_NODE,
#      SOAK_ITERATIONS=1000, INTERVAL=60, INSPECT_INTERVAL=300, CONCURRENCY=2,
#      TIMEOUT=60, SAMPLE_INTERVAL=300, SOAK_SECONDS=86400, FORCE=1, SKIP_SOAK=1
set -uo pipefail

PHASE="prep"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --collect) PHASE="collect"; shift ;;
    --prep) PHASE="prep"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

REPO=${REPO:-$(pwd)}
PROD_WS=${PROD_WS:-${VCL_FLEET_HOME:-$HOME/vincula-fleet-live}}
PROD_STATE=${PROD_STATE:-${VCL_FLEET_LOCAL_STATE:-$HOME/.local/state/vincula}}
PROD_CONFIG=${PROD_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}}
CTRL_ZIP=${CTRL_ZIP:-$REPO/dist/vincula-controller-0.5.3.zip}
EXPECT_ZIP_SHA=65dbcc7b4ae19cfa480698ee2616ad67f43632460986ecae72ae89cfce0137a7
SOAK_NODE=${SOAK_NODE:-neptunespear}
SOAK_ITERATIONS=${SOAK_ITERATIONS:-1000}
SKIP_SOAK=${SKIP_SOAK:-0}
# Real proxy probing needs a private probe-profiles/v1 file plus a pinned local
# sing-box (docs/operations/monitoring-runbook.md). Empty -> proxy stays UNKNOWN.
PROBE_PROFILES=${PROBE_PROFILES:-}
PROBE_SING_BOX=${PROBE_SING_BOX:-}
INTERVAL=${INTERVAL:-60}
INSPECT_INTERVAL=${INSPECT_INTERVAL:-300}
CONCURRENCY=${CONCURRENCY:-2}
TIMEOUT=${TIMEOUT:-60}
SAMPLE_INTERVAL=${SAMPLE_INTERVAL:-300}
SOAK_SECONDS=${SOAK_SECONDS:-86400}
FORCE=${FORCE:-0}
C_ROOT_EXPLICIT=${C_ROOT:-}
if [[ "$PHASE" == "collect" && -z "$C_ROOT_EXPLICIT" ]]; then
  C_ROOT=$(ls -1d "$HOME"/vcl-phase-c-* 2>/dev/null | while read -r d; do
             [[ -f "$d/c-meta.env" ]] && printf '%s\n' "$d"; done | sort | tail -1)
  [[ -n "$C_ROOT" ]] || C_ROOT="$HOME/vcl-phase-c-$(date -u +%Y%m%dT%H%M%SZ)"
  printf 'collect: using C_ROOT=%s (set C_ROOT to override)\n' "$C_ROOT"
else
  C_ROOT=${C_ROOT:-$HOME/vcl-phase-c-$(date -u +%Y%m%dT%H%M%SZ)}
fi
EVID="$C_ROOT/evidence"
META="$C_ROOT/c-meta.env"
MODE_FILE="$C_ROOT/c-mode.env"
PASS=0
FAIL=0

note() { printf '%s\n' "$*" | tee -a "$C_ROOT/batch-c.log"; }
ok()   { PASS=$((PASS + 1)); note "PASS  $*"; }
bad()  { FAIL=$((FAIL + 1)); note "FAIL  $*"; }

fingerprint() {
  local tag=$1
  [[ -d "$PROD_WS" ]] && find "$PROD_WS" -type f -print0 2>/dev/null | sort -z \
    | xargs -0 -r sha256sum > "$EVID/prod-ws-$tag.sha256"
  [[ -d "$PROD_CONFIG/vincula/controllers" ]] && find "$PROD_CONFIG/vincula/controllers" -type f -print0 2>/dev/null \
    | sort -z | xargs -0 -r sha256sum > "$EVID/prod-bindings-$tag.sha256"
  [[ -d "$PROD_STATE" ]] && { find "$PROD_STATE" -type f \( -name 'fleet.db' -o -name 'observation.db' \
      -o -name 'findings.db' -o -name 'inspection.db' \) -printf '%p %s %T@\n' 2>/dev/null | sort; } \
    > "$EVID/prod-db-$tag.sha256"
  { find "$PROD_WS" "$PROD_STATE" "$PROD_CONFIG/vincula/controllers" -type f \
      -printf '%p %s %T@\n' 2>/dev/null | sort; } > "$EVID/prod-stat-$tag.txt"
}

copy_state() {
  local fleet_id=$1
  python3 - "$PROD_STATE" "$C_ROOT/state" "$fleet_id" <<'COPY'
import shutil, sqlite3, sys
from pathlib import Path

src, dst, fleet_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sdir, ddir = src / fleet_id, dst / fleet_id
ddir.mkdir(parents=True, exist_ok=True)
for name in ("fleet.db", "observation.db", "findings.db", "inspection.db"):
    s = sdir / name
    if not s.is_file():
        print(f"  {name}: absent in production state")
        continue
    con = sqlite3.connect(f"file:{s}?mode=ro", uri=True)
    out = sqlite3.connect(str(ddir / name))
    con.backup(out)
    out.close()
    con.close()
    print(f"  {name}: copied {s.stat().st_size} bytes")
if (sdir / "workspace-view.json").is_file():
    shutil.copy2(sdir / "workspace-view.json", ddir / "workspace-view.json")
for sub in ("ui-runtime", "archives"):
    if (sdir / sub).is_dir():
        shutil.copytree(sdir / sub, ddir / sub, dirs_exist_ok=True)
COPY
}

# ------------------------------------------------------------------ sampler
write_sampler() {
  cat > "$C_ROOT/sampler.sh" <<'SAMPLER'
#!/usr/bin/env bash
# Cache-only sampler: one JSON line every SAMPLE_INTERVAL seconds.
set -uo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
# shellcheck disable=SC1091
source "$here/c-meta.env"
CTRL="$UNPACK/bin/vcl-fleet"   # prep chmod +x'd the unpacked copy
out="$here/evidence/C-samples.jsonl"
mkdir -p "$here/evidence"
while true; do
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  python3 - "$CTRL" "$VCL_FLEET_LOCAL_STATE" "$FLEET_ID" "$ts" "$out" <<'ONESHOT'
import json, os, sqlite3, subprocess, sys
from pathlib import Path

ctrl, state_root, fleet_id, ts, out = sys.argv[1:6]
state = Path(state_root) / fleet_id


def run(*args):
    p = subprocess.run([ctrl, *args], capture_output=True, text=True)
    try:
        return p.returncode, json.loads(p.stdout)
    except Exception:
        return p.returncode, {}


def size(name):
    p = state / name
    return p.stat().st_size if p.is_file() else None


def count(db, sql):
    p = state / db
    if not p.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        row = con.execute(sql).fetchone()
        con.close()
        return row[0] if row else 0
    except sqlite3.Error:
        return None


h_rc, health = run("health", "--json")
f_rc, findings = run("findings", "--json")
t_rc, timeline = run("timeline", "--json", "--limit", "200")
rec = {
    "ts": ts,
    "exit": {"health": h_rc, "findings": f_rc, "timeline": t_rc},
    "rows": {"audit_events": count("fleet.db", "SELECT COUNT(*) FROM audit_events"),
             "daily_usage": count("fleet.db", "SELECT COUNT(*) FROM daily_usage")},
    "cache_state": {"health": health.get("cache_state"), "findings": findings.get("cache_state"),
                    "timeline": timeline.get("cache_state")},
    "db_bytes": {n: size(n) for n in ("fleet.db", "observation.db", "findings.db", "inspection.db")},
    "nodes": {},
    "findings_open": len(findings.get("findings") or []),
    "finding_types": sorted({(f.get("type") or f.get("rule")) for f in (findings.get("findings") or [])
                             if isinstance(f, dict)}),
    "timeline_events": len(timeline.get("events") or []),
}
for row in health.get("nodes") or []:
    if not isinstance(row, dict):
        continue
    h = row.get("health") or {}
    def st(key):
        v = h.get(key)
        return v.get("state") if isinstance(v, dict) else v
    rec["nodes"][row.get("name")] = {
        "observation_state": row.get("observation_state"),
        "overall": row.get("overall"),
        "node": st("node"), "observation": st("observation"),
        "proxy": st("proxy"), "accounting": st("accounting"),
        "proxy_failures": (h.get("proxy") or {}).get("failures") if isinstance(h.get("proxy"), dict) else None,
        "proxy_successes": (h.get("proxy") or {}).get("successes") if isinstance(h.get("proxy"), dict) else None,
        "restart_count": (row.get("metrics") or {}).get("restart_count"),
        "telemetry_age_s": row.get("telemetry_age_seconds"),
    }
with open(out, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
ONESHOT
  sleep "$SAMPLE_INTERVAL"
done
SAMPLER
  chmod +x "$C_ROOT/sampler.sh"
}

if [[ "$PHASE" == "collect" ]]; then
  [[ -f "$META" ]] || { echo "STOP: $META missing; run the prep phase first" >&2; exit 2; }
  # shellcheck disable=SC1090
  source "$META"
  export VCL_FLEET_HOME="$C_ROOT/ws" VCL_FLEET_LOCAL_STATE="$C_ROOT/state"
  export XDG_CONFIG_HOME="$C_ROOT/config" TMPDIR="$C_ROOT/tmp"
  CTRL=(python3 "$UNPACK/bin/vcl-fleet")
else
  mkdir -p "$EVID" "$C_ROOT/tmp"
  note "== phase C (prep) ==  run=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  note "prod_ws=$PROD_WS  prod_state=$PROD_STATE  prod_config=$PROD_CONFIG  c_root=$C_ROOT"
  note "soak_node=$SOAK_NODE iterations=$SOAK_ITERATIONS monitor=${INTERVAL}s/${INSPECT_INTERVAL}s sampler=${SAMPLE_INTERVAL}s target=${SOAK_SECONDS}s"
  note "prod controller processes now: $(pgrep -af 'vcl-fleet' | grep -v phase-c | head -3 | tr '\n' ';' || true)"

  [[ -f "$CTRL_ZIP" ]] || { bad "candidate zip missing: $CTRL_ZIP"; exit 2; }
  ZIP_SHA=$(sha256sum -- "$CTRL_ZIP" | awk '{print $1}')
  [[ "$ZIP_SHA" == "$EXPECT_ZIP_SHA" ]] && ok "candidate zip sha256 matches the frozen digest" \
    || bad "candidate zip sha256 mismatch (got $ZIP_SHA)"
  python3 -c 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$CTRL_ZIP" "$C_ROOT/ctrl"
  UNPACK="$C_ROOT/ctrl/vincula-controller-0.5.3"
  [[ -f "$UNPACK/bin/vcl-fleet" ]] || { bad "unpacked controller missing bin/vcl-fleet"; exit 2; }
  chmod +x "$UNPACK/bin/vcl-fleet"   # zipfile does not restore the exec bit on ext4
  ok "unpacked controller executable bit set on the copy (artifact itself untouched)"

  mkdir -p "$C_ROOT/ws" "$C_ROOT/state" "$C_ROOT/config" "$C_ROOT/tmp"
  cp -a "$PROD_WS/." "$C_ROOT/ws/" 2>/dev/null || bad "cannot copy the production workspace"
  export VCL_FLEET_HOME="$C_ROOT/ws" VCL_FLEET_LOCAL_STATE="$C_ROOT/state"
  export XDG_CONFIG_HOME="$C_ROOT/config" TMPDIR="$C_ROOT/tmp"
  case "$VCL_FLEET_LOCAL_STATE" in "$PROD_STATE"*) bad "isolated state is production state"; exit 2;; esac
  case "$XDG_CONFIG_HOME" in "$PROD_CONFIG") bad "isolated config is production config"; exit 2;; esac
  ok "environment isolation guards passed (production roots are read-only copies)"

  CTRL=(python3 "$UNPACK/bin/vcl-fleet")
  VER=$("${CTRL[@]}" version 2>&1)
  [[ "$VER" == "vcl-fleet 0.5.3" ]] && ok "candidate reports $VER" || bad "unexpected version: $VER"

  fingerprint before
  FLEET_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fleet_id"])' "$PROD_WS/workspace.json")
  note "-- C0: consistent copies of the production state and credential bindings --"
  note "fleet_id=$FLEET_ID (production workspace is only read)"
  copy_state "$FLEET_ID" | tee -a "$C_ROOT/batch-c.log"
  mkdir -p "$VCL_FLEET_LOCAL_STATE/$FLEET_ID"
  if [[ -d "$PROD_CONFIG/vincula/controllers/$FLEET_ID" ]]; then
    mkdir -p "$XDG_CONFIG_HOME/vincula/controllers/$FLEET_ID"
    cp -a "$PROD_CONFIG/vincula/controllers/$FLEET_ID/." "$XDG_CONFIG_HOME/vincula/controllers/$FLEET_ID/"
    ok "credential bindings copied into the isolated config"
  else
    note "no production bindings directory for this fleet_id"
  fi
  cat > "$META" <<EOF
export VCL_FLEET_HOME="$C_ROOT/ws"
export VCL_FLEET_LOCAL_STATE="$C_ROOT/state"
export XDG_CONFIG_HOME="$C_ROOT/config"
export TMPDIR="$C_ROOT/tmp"
C_ROOT="$C_ROOT"
EVID="$EVID"
UNPACK="$UNPACK"
REPO="$REPO"
PROD_WS="$PROD_WS"
PROD_STATE="$PROD_STATE"
PROD_CONFIG="$PROD_CONFIG"
FLEET_ID="$FLEET_ID"
SOAK_NODE="$SOAK_NODE"
SOAK_ITERATIONS="$SOAK_ITERATIONS"
INTERVAL="$INTERVAL"
INSPECT_INTERVAL="$INSPECT_INTERVAL"
CONCURRENCY="$CONCURRENCY"
TIMEOUT="$TIMEOUT"
SAMPLE_INTERVAL="$SAMPLE_INTERVAL"
SOAK_SECONDS="$SOAK_SECONDS"
PROBE_PROFILES="$PROBE_PROFILES"
PROBE_SING_BOX="$PROBE_SING_BOX"
EOF

  note "-- C1: preflight telemetry for every enabled node (observe class, read-only) --"
  mapfile -t NAMES < <(python3 -c 'import json,sys; [print(n["name"]) for n in json.load(open(sys.argv[1]))["nodes"]]' "$VCL_FLEET_HOME/fleet.json")
  for n in "${NAMES[@]}"; do
    "${CTRL[@]}" telemetry "$n" --json > "$EVID/C1-telemetry-$n.json" 2>&1
    printf 'telemetry %s exit=%s\n' "$n" "$?" >> "$C_ROOT/batch-c.log"
  done

  note "-- C2: telemetry soak burst on ${SOAK_NODE} (${SOAK_ITERATIONS} iterations) --"
  if [[ "$SKIP_SOAK" == "1" ]]; then
    note "SKIP_SOAK=1: burst skipped (mechanics dry-run)"
  else
    if [[ "$SOAK_NODE" == "auto" ]]; then
      SOAK_NODE=$(python3 - "$EVID" <<'PY'
import json, sys
from pathlib import Path
evid = Path(sys.argv[1])
for p in sorted(evid.glob("C1-telemetry-*.json")):
    try:
        if json.loads(p.read_text(encoding="utf-8")).get("state") == "OK":
            print(p.stem[len("C1-telemetry-"):]); break
    except Exception:
        pass
PY
)
      [[ -n "$SOAK_NODE" ]] && note "auto-selected soak node: $SOAK_NODE"
    fi
    SOAK_EVIDENCE_DIR="$EVID/soak" VCL_SOAK_LIVE=1 VCL_FLEET_HOME="$VCL_FLEET_HOME" \
      VCL_FLEET_LOCAL_STATE="$VCL_FLEET_LOCAL_STATE" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" \
      VCL_FLEET_BIN="$UNPACK/bin/vcl-fleet" \
      bash "$REPO/scripts/soak-0.5.0-telemetry.sh" "$SOAK_NODE" --iterations "$SOAK_ITERATIONS" --live \
      > "$C_ROOT/soak-burst.log" 2>&1
    SOAK_RC=$?
    tail -25 "$C_ROOT/soak-burst.log" | tee -a "$C_ROOT/batch-c.log"
    [[ $SOAK_RC -eq 0 ]] && ok "telemetry soak burst PASS LIVE (${SOAK_ITERATIONS} iterations)" \
      || bad "telemetry soak burst rc=$SOAK_RC (see soak-burst.log; evidence kept)"
  fi

  note "-- C3: starting the 24h monitor and the ${SAMPLE_INTERVAL}s sampler --"
  note "note: continuous monitor prints no stdout (only --once does); samples and counters live in observation.db/findings.db/inspection.db"
  VCL_FLEET_HOME="$VCL_FLEET_HOME" VCL_FLEET_LOCAL_STATE="$VCL_FLEET_LOCAL_STATE" \
  XDG_CONFIG_HOME="$XDG_CONFIG_HOME" TMPDIR="$TMPDIR" \
  PROBE_ARGS=()
  if [[ -n "$PROBE_PROFILES" ]]; then
    PROBE_ARGS+=(--probe-profiles "$PROBE_PROFILES")
    [[ -n "$PROBE_SING_BOX" ]] && PROBE_ARGS+=(--probe-sing-box "$PROBE_SING_BOX")
    note "proxy probing ENABLED via $PROBE_PROFILES"
  else
    note "proxy probing NOT CONFIGURED: proxy health will stay UNKNOWN (runbook requires a private probe-profiles/v1 file)"
  fi
  nohup python3 -u "$UNPACK/bin/vcl-fleet" monitor \
    --interval "$INTERVAL" --inspect-interval "$INSPECT_INTERVAL" \
    --timeout "$TIMEOUT" --concurrency "$CONCURRENCY" "${PROBE_ARGS[@]}" --json \
    >> "$C_ROOT/monitor.log" 2>&1 &
  MONITOR_PID=$!
  disown 2>/dev/null || true
  write_sampler
  nohup "$C_ROOT/sampler.sh" >> "$C_ROOT/sampler.log" 2>&1 &
  SAMPLER_PID=$!
  disown 2>/dev/null || true
  date -u +%s > "$C_ROOT/window.start"
  cat > "$MODE_FILE" <<EOF
MONITOR_PID=$MONITOR_PID
SAMPLER_PID=$SAMPLER_PID
WINDOW_START=$(cat "$C_ROOT/window.start")
SOAK_SECONDS=$SOAK_SECONDS
SOAK_NODE=$SOAK_NODE
EOF
  sleep 5
  kill -0 "$MONITOR_PID" 2>/dev/null && ok "monitor running (pid $MONITOR_PID)" || bad "monitor exited immediately (see monitor.log)"
  kill -0 "$SAMPLER_PID" 2>/dev/null && ok "sampler running (pid $SAMPLER_PID)" || bad "sampler exited immediately (see sampler.log)"
  note "== prep done: PASS=$PASS FAIL=$FAIL =="
  note "next: wait ${SOAK_SECONDS}s (24h), keep production untouched, then run:"
  note "      C_ROOT=$C_ROOT bash $0 --collect"
  exit $(( FAIL > 0 ? 1 : 0 ))
fi

# ------------------------------------------------------------------ collect
note "== phase C (collect) ==  run=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# shellcheck disable=SC1090
source "$MODE_FILE"
NOW=$(date -u +%s)
ELAPSED=$((NOW - WINDOW_START))
note "window elapsed: ${ELAPSED}s of target ${SOAK_SECONDS}s"

for pair in "monitor:$MONITOR_PID" "sampler:$SAMPLER_PID"; do
  name=${pair%%:*}; pid=${pair##*:}
  if kill -0 "$pid" 2>/dev/null; then
    if (( ELAPSED < SOAK_SECONDS )) && [[ "$FORCE" != "1" ]]; then
      bad "$name still running and only ${ELAPSED}s elapsed; re-run with FORCE=1 to stop early"
      exit 2
    fi
    kill -TERM "$pid" 2>/dev/null
    for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -0 "$pid" 2>/dev/null && { kill -KILL "$pid" 2>/dev/null; note "$name needed SIGKILL"; }
    ok "$name stopped after ${ELAPSED}s"
  else
    note "$name already exited"
  fi
done

note "-- C4: final cache-only views + one explicit monitor round --"
if [[ -n "${PROBE_PROFILES:-}" ]]; then
  "${CTRL[@]}" monitor --once --timeout "$TIMEOUT" --probe-profiles "$PROBE_PROFILES" \
    ${PROBE_SING_BOX:+--probe-sing-box "$PROBE_SING_BOX"} --json > "$EVID/C4-monitor-once.json" 2>&1
else
  "${CTRL[@]}" monitor --once --timeout "$TIMEOUT" --json > "$EVID/C4-monitor-once.json" 2>&1
fi
printf 'monitor --once exit=%s\n' "$?" >> "$C_ROOT/batch-c.log"
"${CTRL[@]}" health --json > "$EVID/C4-health.json" 2>&1
"${CTRL[@]}" findings --json --refresh > "$EVID/C4-findings.json" 2>&1
"${CTRL[@]}" timeline --json --limit 1000 > "$EVID/C4-timeline.json" 2>&1
"${CTRL[@]}" stats --json > "$EVID/C4-stats.json" 2>&1
"${CTRL[@]}" status --json > "$EVID/C4-status.json" 2>&1

fingerprint after
for kind in ws db bindings; do
  diff -q "$EVID/prod-$kind-before.sha256" "$EVID/prod-$kind-after.sha256" >/dev/null 2>&1 \
    && ok "production $kind unchanged" || bad "production $kind CHANGED"
done
diff -q "$EVID/prod-stat-before.txt" "$EVID/prod-stat-after.txt" >/dev/null 2>&1 \
  && ok "production sizes/mtimes unchanged" || note "NOTE: production size/mtime diff (explain it)"

python3 - "$EVID" "$WINDOW_START" "$NOW" "$INTERVAL" "$SOAK_SECONDS" "$SOAK_ITERATIONS" "$SOAK_NODE" \
  "${PROBE_PROFILES:+configured}" <<'REPORT'
import json, sqlite3, sys
from pathlib import Path

evid = Path(sys.argv[1])
start, end = float(sys.argv[2]), float(sys.argv[3])
interval, target = float(sys.argv[4]), float(sys.argv[5])
iterations, soak_node = int(sys.argv[6]), sys.argv[7]
probe_state = sys.argv[8] if len(sys.argv) > 8 else ""

def load(name):
    try:
        return json.loads((evid / name).read_text(encoding="utf-8"))
    except Exception:
        return {}

def q(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []

# --- samples from observation.db (copy) --------------------------------------
series = []
for path in (evid.parent / "state").glob("*/observation.db"):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = q(con, "SELECT node_id, at, payload FROM telemetry_samples WHERE at >= ? ORDER BY at", (start,))
    con.close()
    per = {}
    for node_id, at, payload in rows:
        name = None
        try:
            name = json.loads(payload).get("name")
        except Exception:
            pass
        per.setdefault(node_id, {"name": name, "times": []})["times"].append(float(at))
    for node_id, rec in per.items():
        ts = sorted(rec["times"])
        gaps = [b - a for a, b in zip(ts, ts[1:])]
        span = (ts[-1] - ts[0]) if len(ts) > 1 else 0.0
        expected = max(1, int(span / interval)) if span else 0
        series.append({"node": rec["name"] or node_id, "samples": len(ts),
                       "span_s": round(span, 1),
                       "max_gap_s": round(max(gaps), 1) if gaps else None,
                       "expected": expected,
                       "coverage": round(len(ts) / expected, 3) if expected else None,
                       "tail_gap_s": round(max(0.0, end - ts[-1]), 1) if ts else None})

# --- sampler time series -----------------------------------------------------
samples = []
sp = evid / "C-samples.jsonl"
if sp.is_file():
    for line in sp.read_text(encoding="utf-8").splitlines():
        try:
            samples.append(json.loads(line))
        except Exception:
            pass
first = samples[0] if samples else {}
last = samples[-1] if samples else {}
db_growth = {}
if first.get("db_bytes") and last.get("db_bytes"):
    for k in first["db_bytes"]:
        a, b = first["db_bytes"].get(k), last["db_bytes"].get(k)
        if isinstance(a, int) and isinstance(b, int):
            db_growth[k] = b - a
errs = sum(1 for s in samples if any(v not in (0, None) for v in (s.get("exit") or {}).values()))
proxy = {}
for s in samples:
    for node, rec in (s.get("nodes") or {}).items():
        p = proxy.setdefault(node, {"states": {}, "failures": 0, "successes": 0})
        p["states"][rec.get("proxy")] = p["states"].get(rec.get("proxy"), 0) + 1
        p["failures"] = max(p["failures"], rec.get("proxy_failures") or 0)
        p["successes"] = max(p["successes"], rec.get("proxy_successes") or 0)

monitor_once = load("C4-monitor-once.json")
monitor_errors = dict(monitor_once.get("run") or {})
inspection_events = []
for path in (evid.parent / "state").glob("*/inspection.db"):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    inspection_events += q(con, "SELECT at, node FROM events ORDER BY at")
    con.close()
inspection_last = max((e[0] for e in inspection_events), default=None) if inspection_events else None

row_growth = {}
if samples:
    a = samples[0].get("rows") or {}
    b = samples[-1].get("rows") or {}
    for k in set(a) | set(b):
        if isinstance(a.get(k), int) and isinstance(b.get(k), int):
            row_growth[k] = b[k] - a[k]

soak_digest = {}
dig = evid / "soak" / soak_node / "DIGEST.json"
if dig.is_file():
    soak_digest = load(Path("soak") / soak_node / "DIGEST.json")

report = {
    "window": {"start_epoch": start, "end_epoch": end, "elapsed_s": end - start, "target_s": target},
    "soak": {"node": soak_node, "iterations": iterations, "digest": soak_digest},
    "series": sorted(series, key=lambda s: s["node"]),
    "monitor_once": {"state": monitor_once.get("cache_state"),
                     "run": monitor_errors,
                     "proxy_probing_configured": probe_state == "configured"},
    "inspection": {"events_in_window": [e for e in inspection_events if float(e[0]) >= start],
                   "events_total": len(inspection_events),
                   "last_event_epoch": inspection_last,
                   "tail_gap_vs_last_inspection_s": (round(max(0.0, end - float(inspection_last)), 1)
                                                     if inspection_last is not None else None)},
    "row_growth": row_growth,
    "sampler": {"lines": len(samples), "first": first.get("ts"), "last": last.get("ts"),
                "lines_with_nonzero_exit": errs,
                "db_growth_bytes": db_growth,
                "findings_open_first": first.get("findings_open"),
                "findings_open_last": last.get("findings_open"),
                "timeline_first": first.get("timeline_events"),
                "timeline_last": last.get("timeline_events"),
                "cache_state_first": first.get("cache_state"),
                "cache_state_last": last.get("cache_state")},
    "proxy": proxy,
}
(evid / "C-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

lines = ["# Phase C summary (sanitized)", "",
         f"- window: {end - start:.0f}s (target {target:.0f}s)",
         f"- soak burst: node={soak_node} iterations={iterations} outcome={soak_digest.get('outcome')} "
         f"ok={soak_digest.get('ok')} fail_at={soak_digest.get('fail_at')}",
         f"- sampler lines: {len(samples)} ({first.get('ts')} .. {last.get('ts')}), lines with a non-zero view exit: {errs}"
         " (findings/timeline may legitimately exit non-zero while findings are open)",
         f"- DB growth (bytes): {db_growth}",
         f"- row growth (audit_events / daily_usage): {row_growth}",
         f"- monitor --once run counters: {monitor_errors}",
         f"- inspection events: {len(report['inspection']['events_in_window'])} in window, "
         f"last {report['inspection']['last_event_epoch']}, "
         f"tail gap vs last inspection {report['inspection']['tail_gap_vs_last_inspection_s']}s",
         f"- proxy probing configured: {probe_state == 'configured'}",
         f"- findings open: {first.get('findings_open')} -> {last.get('findings_open')}",
         "", "## Telemetry series (per node, window)", "",
         "| node | samples | span s | max gap s | coverage | tail gap s |",
         "| --- | --- | --- | --- | --- | --- |"]
for s in report["series"]:
    lines.append("| {node} | {samples} | {span_s} | {max_gap_s} | {coverage} | {tail_gap_s} |".format(**s))
lines += ["", "## Proxy / observation states seen by the sampler", "",
          "| node | proxy states | proxy failures | proxy successes |", "| --- | --- | --- | --- |"]
for node, rec in sorted(report["proxy"].items()):
    lines.append(f"| {node} | {rec['states']} | {rec['failures']} | {rec['successes']} |")
if soak_digest.get("metric_results"):
    lines += ["", "## Soak burst metric results", ""]
    for m in soak_digest["metric_results"]:
        lines.append(f"- [{m.get('status')}] {m.get('label')}: {m.get('detail')}")
(evid / "C-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
REPORT

note "== collect done: PASS=$PASS FAIL=$FAIL =="
BUNDLE="$(dirname "$C_ROOT")/$(basename "$C_ROOT")-phaseC.tgz"
tar -C "$(dirname "$C_ROOT")" -czf "$BUNDLE" "$(basename "$C_ROOT")"
note "bundle: $BUNDLE"
note "bundle sha256: $(sha256sum -- "$BUNDLE" | awk '{print $1}')"
note "hand back: evidence/C-summary.md, C-report.json, evidence/soak/$SOAK_NODE/SUMMARY.txt, evidence/soak/$SOAK_NODE/DIGEST.json, evidence/C-samples.jsonl, batch-c.log"
exit $(( FAIL > 0 ? 1 : 0 ))
