#!/usr/bin/env bash
# Phase B for the frozen 0.5.3 candidate: seven-node mixed-fleet re-verification.
#
#   bash tmp/phase-b.sh              # B0 prep (isolated copies) + B1 probe/verify
#                                    # + B2 capability/telemetry matrix + start the 2h monitor
#   bash tmp/phase-b.sh --collect    # stop the monitor, B3 series + B4 side-effect re-check
#
# Isolation: the production workspace is only READ; the Controller's state root
# and credential bindings are consistent COPIES under $B_ROOT, so every write
# (last-status.json, observation.db, findings.db, inspection.db, fleet.db)
# lands in the copies. Production workspace/cache/bindings are fingerprinted
# before and after and must stay unchanged.
#
# Env: B_ROOT, PROD_WS, PROD_STATE, PROD_CONFIG, CTRL_ZIP, INTERVAL=60,
#      INSPECT_INTERVAL=300, CONCURRENCY=2, TIMEOUT=60, MONITOR_SECONDS=7200,
#      PHASE_A_SUMMARY=<A1-A4-summary.json>, FORCE=1 (stop the monitor early)
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
INTERVAL=${INTERVAL:-60}
INSPECT_INTERVAL=${INSPECT_INTERVAL:-300}
CONCURRENCY=${CONCURRENCY:-2}
TIMEOUT=${TIMEOUT:-60}
MONITOR_SECONDS=${MONITOR_SECONDS:-7200}
FORCE=${FORCE:-0}
# For --collect, reuse the newest prepared root unless B_ROOT is given explicitly.
B_ROOT_EXPLICIT=${B_ROOT:-}
if [[ "$PHASE" == "collect" && -z "$B_ROOT_EXPLICIT" ]]; then
  B_ROOT=$(ls -1d "$HOME"/vcl-phase-b-* 2>/dev/null | while read -r d; do
             [[ -f "$d/b-meta.env" ]] && printf '%s\n' "$d"; done | sort | tail -1)
  [[ -n "$B_ROOT" ]] || B_ROOT="$HOME/vcl-phase-b-$(date -u +%Y%m%dT%H%M%SZ)"
  printf 'collect: using B_ROOT=%s (set B_ROOT to override)\n' "$B_ROOT"
else
  B_ROOT=${B_ROOT:-$HOME/vcl-phase-b-$(date -u +%Y%m%dT%H%M%SZ)}
fi
EVID="$B_ROOT/evidence"
META="$B_ROOT/b-meta.env"
MODE_FILE="$B_ROOT/mode-tier.env"
PASS=0
FAIL=0

note() { printf '%s\n' "$*" | tee -a "$B_ROOT/batch-b.log"; }
ok()   { PASS=$((PASS + 1)); note "PASS  $*"; }
bad()  { FAIL=$((FAIL + 1)); note "FAIL  $*"; }

fingerprint() {   # fingerprint <tag>
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

copy_state() {   # consistent online backup of the production state into $B_ROOT
  local fleet_id=$1
  python3 - "$PROD_STATE" "$B_ROOT/state" "$fleet_id" <<'COPY'
import shutil, sqlite3, sys
from pathlib import Path

src, dst, fleet_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sdir, ddir = src / fleet_id, dst / fleet_id
ddir.mkdir(parents=True, exist_ok=True)
dbs = ("fleet.db", "observation.db", "findings.db", "inspection.db")
for name in dbs:
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
for name in ("workspace-view.json",):
    if (sdir / name).is_file():
        shutil.copy2(sdir / name, ddir / name)
for sub in ("ui-runtime", "archives"):
    if (sdir / sub).is_dir():
        shutil.copytree(sdir / sub, ddir / sub, dirs_exist_ok=True)
COPY
}

if [[ "$PHASE" == "collect" ]]; then
  [[ -f "$META" ]] || { echo "STOP: $META missing; run the prep phase first" >&2; exit 2; }
  # shellcheck disable=SC1090
  source "$META"   # exports VCL_FLEET_HOME=$B_ROOT/ws, LOCAL_STATE, XDG_CONFIG_HOME, TMPDIR
  export XDG_CONFIG_HOME="$B_ROOT/config" TMPDIR="$B_ROOT/tmp"
  CTRL=(python3 "$UNPACK/bin/vcl-fleet")
else
  mkdir -p "$EVID" "$B_ROOT/tmp"
  note "== phase B (prep) ==  run=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  note "prod_ws=$PROD_WS  prod_state=$PROD_STATE  prod_config=$PROD_CONFIG  b_root=$B_ROOT"
  note "prod controller processes now: $(pgrep -af 'vcl-fleet' | grep -v phase-b | head -3 | tr '\n' ';' || true)"

  [[ -f "$CTRL_ZIP" ]] || { bad "candidate zip missing: $CTRL_ZIP"; exit 2; }
  ZIP_SHA=$(sha256sum -- "$CTRL_ZIP" | awk '{print $1}')
  [[ "$ZIP_SHA" == "$EXPECT_ZIP_SHA" ]] && ok "candidate zip sha256 matches the frozen digest" \
    || bad "candidate zip sha256 mismatch (got $ZIP_SHA)"
  python3 -c 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$CTRL_ZIP" "$B_ROOT/ctrl"
  UNPACK="$B_ROOT/ctrl/vincula-controller-0.5.3"
  [[ -f "$UNPACK/bin/vcl-fleet" ]] || { bad "unpacked controller missing bin/vcl-fleet"; exit 2; }

  # byte-identical copy of the (small) production workspace; the production root
  # is never written by this script
  mkdir -p "$B_ROOT/ws"
  cp -a "$PROD_WS/." "$B_ROOT/ws/" 2>/dev/null || bad "cannot copy the production workspace"
  export VCL_FLEET_HOME="$B_ROOT/ws" VCL_FLEET_LOCAL_STATE="$B_ROOT/state"
  export XDG_CONFIG_HOME="$B_ROOT/config" TMPDIR="$B_ROOT/tmp"
  mkdir -p "$B_ROOT/state" "$XDG_CONFIG_HOME" "$B_ROOT/tmp"
  case "$VCL_FLEET_LOCAL_STATE" in "$PROD_STATE"*) bad "isolated state is production state"; exit 2;; esac
  case "$XDG_CONFIG_HOME" in "$PROD_CONFIG") bad "isolated config is production config"; exit 2;; esac
  ok "environment isolation guards passed (workspace is read-only, state/config are copies)"

  CTRL=(python3 "$UNPACK/bin/vcl-fleet")
  VER=$("${CTRL[@]}" version 2>&1)
  [[ "$VER" == "vcl-fleet 0.5.3" ]] && ok "candidate reports $VER" || bad "unexpected version: $VER"

  fingerprint before
  FLEET_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fleet_id"])' "$PROD_WS/workspace.json")
  note "-- B0: consistent copies of the production state and credential bindings --"
  note "fleet_id=$FLEET_ID (production workspace is only read)"
  copy_state "$FLEET_ID" | tee -a "$B_ROOT/batch-b.log"
  mkdir -p "$VCL_FLEET_LOCAL_STATE/$FLEET_ID"
  if [[ -d "$PROD_CONFIG/vincula/controllers/$FLEET_ID" ]]; then
    cp -a "$PROD_CONFIG/vincula/controllers/$FLEET_ID" "$XDG_CONFIG_HOME/vincula/controllers/" 2>/dev/null \
      || { mkdir -p "$XDG_CONFIG_HOME/vincula/controllers/$FLEET_ID"; \
           cp -a "$PROD_CONFIG/vincula/controllers/$FLEET_ID/." "$XDG_CONFIG_HOME/vincula/controllers/$FLEET_ID/"; }
    ok "credential bindings copied into the isolated config (production bindings are read-only here)"
  else
    note "no production bindings directory for this fleet_id"
  fi
  cat > "$META" <<EOF
export VCL_FLEET_HOME="$B_ROOT/ws"
export VCL_FLEET_LOCAL_STATE="$B_ROOT/state"
export XDG_CONFIG_HOME="$B_ROOT/config"
export TMPDIR="$B_ROOT/tmp"
B_ROOT="$B_ROOT"
EVID="$EVID"
UNPACK="$UNPACK"
PROD_WS="$PROD_WS"
PROD_STATE="$PROD_STATE"
PROD_CONFIG="$PROD_CONFIG"
FLEET_ID="$FLEET_ID"
INTERVAL="$INTERVAL"
INSPECT_INTERVAL="$INSPECT_INTERVAL"
CONCURRENCY="$CONCURRENCY"
TIMEOUT="$TIMEOUT"
MONITOR_SECONDS="$MONITOR_SECONDS"
PHASE_A_SUMMARY="${PHASE_A_SUMMARY:-}"
EOF

  note "-- B1: production-context baseline (probe / verify / status) --"
  "${CTRL[@]}" probe --json > "$EVID/B1-probe.json" 2>"$EVID/B1-probe.err"; P1=$?
  "${CTRL[@]}" verify --json > "$EVID/B1-verify.json" 2>"$EVID/B1-verify.err"; P2=$?
  "${CTRL[@]}" status --json > "$EVID/B1-status.json" 2>"$EVID/B1-status.err"; P3=$?
  note "probe_exit=$P1 verify_exit=$P2 status_exit=$P3"
  [[ -s "$EVID/B1-probe.err" ]] && cat "$EVID/B1-probe.err" >> "$B_ROOT/batch-b.log"

  note "-- B2: capability + telemetry matrix (observe class, read-only) --"
  mapfile -t NAMES < <(python3 -c 'import json,sys; [print(n["name"]) for n in json.load(open(sys.argv[1]))["nodes"]]' "$VCL_FLEET_HOME/fleet.json")
  for n in "${NAMES[@]}"; do
    "${CTRL[@]}" capabilities "$n" --json > "$EVID/B2-cap-$n.json" 2>&1
    "${CTRL[@]}" telemetry "$n" --json > "$EVID/B2-telemetry-$n.json" 2>&1
    printf 'capabilities/telemetry %s done\n' "$n" >> "$B_ROOT/batch-b.log"
  done

  note "-- B3: starting the 2h monitor (interval=${INTERVAL}s inspect=${INSPECT_INTERVAL}s) --"
  export VCL_FAKE_STATE_DIR="${VCL_FAKE_STATE_DIR:-}"
  VCL_FLEET_HOME="$B_ROOT/ws" VCL_FLEET_LOCAL_STATE="$B_ROOT/state" \
  XDG_CONFIG_HOME="$B_ROOT/config" TMPDIR="$B_ROOT/tmp" \
  nohup python3 "$UNPACK/bin/vcl-fleet" monitor \
    --interval "$INTERVAL" --inspect-interval "$INSPECT_INTERVAL" \
    --timeout "$TIMEOUT" --concurrency "$CONCURRENCY" --json \
    >> "$B_ROOT/monitor.log" 2>&1 &
  MONITOR_PID=$!
  disown 2>/dev/null || true
  echo "$MONITOR_PID" > "$B_ROOT/monitor.pid"
  date -u +%s > "$B_ROOT/monitor.start"
  cat > "$MODE_FILE" <<EOF
MONITOR_PID=$MONITOR_PID
MONITOR_START=$(cat "$B_ROOT/monitor.start")
MONITOR_SECONDS=$MONITOR_SECONDS
EOF
  sleep 3
  if kill -0 "$MONITOR_PID" 2>/dev/null; then
    ok "monitor running (pid $MONITOR_PID, log $B_ROOT/monitor.log)"
  else
    bad "monitor exited immediately; see $B_ROOT/monitor.log"
  fi
  note "== prep done: PASS=$PASS FAIL=$FAIL =="
  note "next: wait ${MONITOR_SECONDS}s and then run:"
  note "      B_ROOT=$B_ROOT bash $0 --collect"
  note "      (or stop early: FORCE=1 B_ROOT=$B_ROOT bash $0 --collect)"
  exit $(( FAIL > 0 ? 1 : 0 ))
fi

# ------------------------------------------------------------------ collect
note "== phase B (collect) ==  run=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# shellcheck disable=SC1090
source "$MODE_FILE"
NOW=$(date -u +%s)
ELAPSED=$((NOW - MONITOR_START))
note "monitor elapsed: ${ELAPSED}s of target ${MONITOR_SECONDS}s"
if kill -0 "$MONITOR_PID" 2>/dev/null; then
  if (( ELAPSED < MONITOR_SECONDS )) && [[ "$FORCE" != "1" ]]; then
    bad "monitor still running and only ${ELAPSED}s elapsed; re-run with FORCE=1 to stop early"
    exit 2
  fi
  kill -TERM "$MONITOR_PID" 2>/dev/null
  for _ in $(seq 1 30); do kill -0 "$MONITOR_PID" 2>/dev/null || break; sleep 1; done
  kill -0 "$MONITOR_PID" 2>/dev/null && { kill -KILL "$MONITOR_PID" 2>/dev/null; note "monitor needed SIGKILL"; }
  ok "monitor stopped after ${ELAPSED}s (kept: $(wc -l < "$B_ROOT/monitor.log") log lines)"
else
  note "monitor already exited; log lines=$(wc -l < "$B_ROOT/monitor.log" 2>/dev/null || echo 0)"
fi

note "-- B3: cache-only series (no SSH) --"
"${CTRL[@]}" health --json > "$EVID/B3-health.json" 2>&1
"${CTRL[@]}" findings --json --refresh > "$EVID/B3-findings.json" 2>&1
"${CTRL[@]}" timeline --json --limit 500 > "$EVID/B3-timeline.json" 2>&1
"${CTRL[@]}" inspect --json > "$EVID/B3-inspect.json" 2>&1

note "-- B4: node-side read-only facts (telemetry before/after) + production fingerprint --"
mapfile -t NAMES < <(python3 -c 'import json,sys; [print(n["name"]) for n in json.load(open(sys.argv[1]))["nodes"]]' "$VCL_FLEET_HOME/fleet.json")
for n in "${NAMES[@]}"; do
  "${CTRL[@]}" capabilities "$n" --json > "$EVID/B4-cap-$n.json" 2>&1
  "${CTRL[@]}" telemetry "$n" --json > "$EVID/B4-telemetry-$n.json" 2>&1
done
"${CTRL[@]}" probe --json > "$EVID/B4-probe.json" 2>&1
"${CTRL[@]}" verify --json > "$EVID/B4-verify.json" 2>&1

fingerprint after
for kind in ws db bindings; do
  diff -q "$EVID/prod-$kind-before.sha256" "$EVID/prod-$kind-after.sha256" >/dev/null 2>&1 \
    && ok "production $kind unchanged" || bad "production $kind CHANGED"
done
diff -q "$EVID/prod-stat-before.txt" "$EVID/prod-stat-after.txt" >/dev/null 2>&1 \
  && ok "production sizes/mtimes unchanged" || note "NOTE: production size/mtime diff (explain it)"

python3 - "$EVID" "$B_ROOT" "$MONITOR_START" "$NOW" "$INTERVAL" "$PHASE_A_SUMMARY" "$MONITOR_SECONDS" <<'REPORT'
import json, sqlite3, sys
from pathlib import Path

evid, broot = Path(sys.argv[1]), Path(sys.argv[2])
start, now, interval, phase_a_path, target = (
    float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), sys.argv[6], float(sys.argv[7]))


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def q(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []


# --- B1 comparison against the phase A baseline -------------------------------
phase_a = load(phase_a_path) if phase_a_path else {}
probe = load(evid / "B1-probe.json")
verify = load(evid / "B1-verify.json")
rows = {r.get("name"): r for r in probe.get("nodes", []) if isinstance(r, dict)}
vrows = {r.get("name"): r for r in verify.get("nodes", []) if isinstance(r, dict)}
diffs = []
for name, a in sorted((phase_a.get("nodes") or {}).items()):
    pa, v = a.get("probe", {}), vrows.get(name, {})
    cur, was = rows.get(name, {}), pa
    for field in ("ssh", "reason"):
        pass
    for field, old, new in (("ssh", was.get("ssh"), cur.get("ssh")),
                            ("ssh_reason", was.get("ssh_reason"), cur.get("ssh_reason")),
                            ("version", (a.get("verify") or {}).get("vincula_version"), v.get("vincula_version")),
                            ("proxy", was.get("proxy"), cur.get("proxy")),
                            ("accounting", was.get("accounting"), cur.get("accounting"))):
        if old != new:
            diffs.append(f"{name}.{field}: {old} -> {new}")

caps = {}
for p in sorted(evid.glob("B2-cap-*.json")):
    name = p.stem[len("B2-cap-"):]
    doc = load(p)
    caps[name] = {"state": doc.get("state"), "node_version": doc.get("node_version")}
cap_diffs = []
for name, old in sorted((phase_a.get("nodes") or {}).items()):
    was = (old.get("capabilities") or {}).get("state")
    now = caps.get(name, {}).get("state")
    if was != now:
        cap_diffs.append(f"{name}: {was} -> {now}")

# --- B3 series continuity from the copied observation.db ----------------------
obs = evid.parent / "state"
samples = {}
tl_events = 0
for path in obs.glob("*/observation.db"):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    for node_id, at, payload in q(con, "SELECT node_id, at, payload FROM telemetry_samples WHERE at >= ? ORDER BY at", (start,)):
        name = None
        try:
            name = json.loads(payload).get("name")
        except Exception:
            pass
        rec = samples.setdefault(node_id, {"name": name, "times": []})
        rec["times"].append(float(at))
        rec["name"] = rec["name"] or name
    con.close()
for path in obs.glob("*/findings.db"):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tl_events += len(q(con, "SELECT 1 FROM timeline WHERE at >= ?", (start,)))
    con.close()

series = []
for node_id, rec in sorted(samples.items(), key=lambda kv: kv[1]["name"] or ""):
    ts = sorted(rec["times"])
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    span = (ts[-1] - ts[0]) if len(ts) > 1 else 0.0
    expected = max(1, int(span / interval)) if span else 0
    series.append({
        "node": rec["name"] or node_id,
        "samples": len(ts),
        "first": ts[0] if ts else None,
        "last": ts[-1] if ts else None,
        "span_s": round(span, 1),
        "max_gap_s": round(max(gaps), 1) if gaps else None,
        "expected_samples": expected,
        "coverage": round(len(ts) / expected, 3) if expected else None,
    })

names = sorted({p.stem[len("B2-cap-"):] for p in evid.glob("B2-cap-*.json")}
               | set((phase_a.get("nodes") or {}).keys()))
telemetry_state = {}
for name in names:
    telemetry_state[name] = load(evid / f"B2-telemetry-{name}.json").get("state")

health = load(evid / "B3-health.json")
findings = load(evid / "B3-findings.json")
timeline = load(evid / "B3-timeline.json")

# --- B4 node-side facts: restart counts / service state / identity ------------
facts = []
for name in names:
    before = load(evid / f"B2-telemetry-{name}.json").get("snapshot") or {}
    after = load(evid / f"B4-telemetry-{name}.json").get("snapshot") or {}

    def get(doc, *keys, default=None):
        cur = doc
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return cur if cur is not None else default

    facts.append({
        "node": name,
        "instance_before": get(before, "instance_id"),
        "instance_after": get(after, "instance_id"),
        "sing_box_restarts_before": get(before, "sing_box", "restart_count"),
        "sing_box_restarts_after": get(after, "sing_box", "restart_count"),
        "sing_box_active_before": get(before, "sing_box", "active"),
        "sing_box_active_after": get(after, "sing_box", "active"),
        "accountd_active_before": get(before, "accountd", "active"),
        "accountd_active_after": get(after, "accountd", "active"),
        "uptime_before": get(before, "uptime_seconds"),
        "uptime_after": get(after, "uptime_seconds"),
        "tx_before": get(before, "network", "tx_bytes"),
        "tx_after": get(after, "network", "tx_bytes"),
        "connections_before": get(before, "sing_box", "connection_count"),
        "connections_after": get(after, "sing_box", "connection_count"),
    })

warnings = []
for s in series:
    state = telemetry_state.get(s["node"])
    if state != "OK":
        continue
    if s.get("coverage") is not None and s["coverage"] < 0.9:
        warnings.append(f"{s['node']}: coverage {s['coverage']} < 0.9")
    if s.get("max_gap_s") is not None and s["max_gap_s"] > 2.5 * interval:
        warnings.append(f"{s['node']}: max gap {s['max_gap_s']}s > 2.5x interval")

status_rows = {r.get("name"): r for r in load(evid / "B1-status.json").get("nodes", [])
               if isinstance(r, dict)}
rounds = 0
log = Path(broot) / "monitor.log"
if log.is_file():
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("{"):
            rounds += 1

report = {
    "window": {"start_epoch": start, "end_epoch": now, "elapsed_s": now - start,
               "interval_s": interval, "target_s": target, "monitor_rounds": rounds},
    "telemetry_state": telemetry_state,
    "continuity_warnings": warnings,
    "b1_status_rows": {n: {k: r.get(k) for k in ("ssh", "proxy", "accounting", "cursor_status",
                                                 "data_age", "last_sync_at")}
                       for n, r in sorted(status_rows.items())},
    "b1_diffs_vs_phase_a": diffs,
    "b2_capability_diffs_vs_phase_a": cap_diffs,
    "b3_series": series,
    "b3_timeline_events_in_window": tl_events,
    "b3_cache_state": {"health": health.get("cache_state"), "findings": findings.get("cache_state"),
                       "timeline": timeline.get("cache_state")},
    "b4_node_facts": facts,
}
(evid / "B-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

lines = ["# Phase B summary (sanitized)", "",
         f"- window: {now - start:.0f}s (target {target:.0f}s, interval {interval:.0f}s)",
         f"- B1 diffs vs phase A: {diffs or 'none'}",
         f"- B2 capability diffs vs phase A: {cap_diffs or 'none'}",
         f"- cache_state: {report['b3_cache_state']}",
         f"- monitor rounds logged: {rounds}",
         f"- timeline events in window: {tl_events}",
         f"- continuity warnings: {warnings or 'none'}", "",
         "## B1 cached status (copied production cache; no SSH)", "",
         "| node | ssh | proxy | accounting | cursor | data age | last sync |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
for n, r in sorted(status_rows.items()):
    lines.append(f"| {n} | {r.get('ssh')} | {r.get('proxy')} | {r.get('accounting')} | "
                 f"{r.get('cursor_status')} | {r.get('data_age')} | {r.get('last_sync_at')} |")
lines += ["",
         "## B3 series (telemetry_samples from the copied observation.db)", "",
         "| node | telemetry | samples | span s | max gap s | expected | coverage |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
for s in series:
    s = dict(s, telemetry=telemetry_state.get(s["node"]))
    lines.append("| {node} | {telemetry} | {samples} | {span_s} | {max_gap_s} | {expected_samples} | {coverage} |".format(**s))
lines += ["", "## B4 node-side facts (before -> after)", "",
          "| node | instance same | sing-box restarts | sing-box active | accountd active | uptime | tx bytes | connections |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
def cell(value):
    return "-" if value is None else value


for f in facts:
    lines.append("| {node} | {same} | {a} -> {b} | {c} -> {d} | {e} -> {g} | {h} -> {i} | {j} -> {k} | {l} -> {m} |".format(
        node=f["node"], same=f["instance_before"] == f["instance_after"],
        a=cell(f["sing_box_restarts_before"]), b=cell(f["sing_box_restarts_after"]),
        c=cell(f["sing_box_active_before"]), d=cell(f["sing_box_active_after"]),
        e=cell(f["accountd_active_before"]), g=cell(f["accountd_active_after"]),
        h=cell(f["uptime_before"]), i=cell(f["uptime_after"]),
        j=cell(f["tx_before"]), k=cell(f["tx_after"]),
        l=cell(f["connections_before"]), m=cell(f["connections_after"])))
(evid / "B-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
REPORT

note "== collect done: PASS=$PASS FAIL=$FAIL =="
BUNDLE="$(dirname "$B_ROOT")/$(basename "$B_ROOT")-phaseB.tgz"
tar -C "$(dirname "$B_ROOT")" -czf "$BUNDLE" "$(basename "$B_ROOT")"
note "bundle: $BUNDLE"
note "bundle sha256: $(sha256sum -- "$BUNDLE" | awk '{print $1}')"
note "hand back: evidence/B-summary.md, B-report.json, B1-verify.json, B3-health.json, B3-timeline.json, batch-b.log"
exit $(( FAIL > 0 ? 1 : 0 ))
