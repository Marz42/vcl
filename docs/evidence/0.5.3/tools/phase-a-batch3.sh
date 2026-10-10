#!/usr/bin/env bash
# Phase A batch 3 for the frozen 0.5.3 candidate: large backlog, one-page
# resume and the failure/recovery cases (plan §3 A6/A7/A9).
#
# Runs ONLY against an isolated workspace created by tmp/phase-a-batch1.sh
# (batch 1+2). The production workspace/cache/bindings are fingerprint-checked
# before and after and are never written. The Nodes are read-only (audit
# export / identity / status).
#
#   export VERIFY_ROOT=/home/marz/vcl-verify-...
#   bash tmp/phase-a-batch3.sh                 # node defaults to $PAGE_A_NODE
#   PAGE_A_NODE=neptunespar bash tmp/phase-a-batch3.sh
#
# Options (env): PAGE_A_NODE, PAGE_SIZE=5000, MAX_PAGES=300, TIMEOUT=60,
#                STDOUT_CAP=16777216, BUDGET=3600, INTERRUPT_AFTER=60,
#                FRESH=1 (drop the ISOLATED cache first), LOCK_SECONDS=20
set -uo pipefail

REPO=${REPO:-$(pwd)}
NODE=${PAGE_A_NODE:-neptunespear}
PAGE_SIZE=${PAGE_SIZE:-5000}
MAX_PAGES=${MAX_PAGES:-300}
TIMEOUT=${TIMEOUT:-60}
STDOUT_CAP=${STDOUT_CAP:-16777216}
BUDGET=${BUDGET:-3600}
INTERRUPT_AFTER=${INTERRUPT_AFTER:-60}
A6_MAX_PAGES=${A6_MAX_PAGES:-}   # empty -> MAX_PAGES (full drain)
FRESH=${FRESH:-1}
LOCK_SECONDS=${LOCK_SECONDS:-20}
LOCK_SECONDS_IMPORT=${LOCK_SECONDS_IMPORT:-40}
EXPECT_ZIP_SHA=65dbcc7b4ae19cfa480698ee2616ad67f43632460986ecae72ae89cfce0137a7

ROOT=${VERIFY_ROOT:?set VERIFY_ROOT to the isolated root created by batch 1}
EVID="$ROOT/evidence"
META="$ROOT/batch-meta.env"
[[ -f "$META" ]] || { echo "STOP: $META missing; run batch 1 first" >&2; exit 2; }
# shellcheck disable=SC1090
source "$META"
mkdir -p "$EVID"
PASS=0
FAIL=0
note() { printf '%s\n' "$*" | tee -a "$ROOT/batch3.log"; }
ok()   { PASS=$((PASS + 1)); note "PASS  $*"; }
bad()  { FAIL=$((FAIL + 1)); note "FAIL  $*"; }

# production paths must never resolve to the isolated root (and vice versa)
case "$VCL_FLEET_HOME" in "$PROD_WS") bad "isolated home equals production home"; exit 2;; esac
case "$VCL_FLEET_LOCAL_STATE" in "$PROD_STATE"*) bad "isolated state is production state"; exit 2;; esac
CTRL=(python3 "$UNPACK/bin/vcl-fleet")
FLEET_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fleet_id"])' "$VCL_FLEET_HOME/workspace.json")
DB="$VCL_FLEET_LOCAL_STATE/$FLEET_ID/fleet.db"

: > "$EVID/B3-steps.jsonl"
note "== phase A batch 3 (A6/A7/A9) ==  run=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
note "node=$NODE page_size=$PAGE_SIZE max_pages=$MAX_PAGES timeout=$TIMEOUT stdout_cap=$STDOUT_CAP budget=$BUDGET"
note "isolated home=$VCL_FLEET_HOME"
note "isolated cache=$DB (fresh=$FRESH)"

ZIP="${CTRL_ZIP:-$ROOT/ctrl/vincula-controller-0.5.3.zip}"
if [[ -f "$ZIP" ]]; then
  [[ "$(sha256sum -- "$ZIP" | awk '{print $1}')" == "$EXPECT_ZIP_SHA" ]] \
    && ok "candidate zip digest matches" || bad "candidate zip digest mismatch ($ZIP)"
else
  note "candidate zip not found at $ZIP (batch 1 recorded the digest; continuing)"
fi

fingerprint() {
  local tag=$1
  find "$PROD_WS" -type f -print0 2>/dev/null | sort -z | xargs -0 -r sha256sum > "$EVID/prod-ws-$tag.sha256"
  { find "$PROD_STATE" -name 'fleet.db' -printf '%p %s %T@\n' 2>/dev/null | sort; } > "$EVID/prod-db-$tag.sha256"
  find "$PROD_CONFIG/vincula/controllers" -type f -print0 2>/dev/null | sort -z \
    | xargs -0 -r sha256sum > "$EVID/prod-bindings-$tag.sha256"
  { find "$PROD_WS" "$PROD_STATE" "$PROD_CONFIG/vincula/controllers" -type f \
      -printf '%p %s %T@\n' 2>/dev/null | sort; } > "$EVID/prod-stat-$tag.txt"
}
fingerprint b3before

if [[ "$FRESH" == "1" ]]; then
  if [[ -f "$DB" ]]; then
    rm -f "$DB" "$DB-wal" "$DB-shm"
    ok "dropped the ISOLATED cache for a clean backlog run"
  else
    note "isolated cache did not exist yet"
  fi
fi

# Read-only view of the isolated cache: rows, max export_seq, cursor.
state() {
  python3 - "$DB" <<'PY'
import sqlite3, sys, os
p = sys.argv[1]
if not os.path.isfile(p):
    print("rows=0 max_seq=0 cursor=0")
    raise SystemExit(0)
def q(conn, sql, default=0):
    try:
        row = conn.execute(sql).fetchone()
        return row[0] if row else default
    except sqlite3.Error:
        return "?"

try:
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
except sqlite3.Error:
    print("rows=? max_seq=? cursor=? unreadable=1")
    raise SystemExit(0)
rows = q(c, "SELECT COUNT(*) FROM audit_events")
mx = q(c, "SELECT COALESCE(MAX(export_seq),0) FROM audit_events")
cur = q(c, "SELECT COALESCE(last_export_seq,0) FROM sync_cursor")
c.close()
unknown = any(v == "?" for v in (rows, mx, cur))
print(f"rows={rows} max_seq={mx} cursor={cur}" + (" unreadable=1" if unknown else ""))
PY
}

run_step() {   # run_step <tag> <description> <args...>
  local tag=$1 desc=$2; shift 2
  local before after rc t0 t1
  before=${RUN_STEP_BEFORE:-$(state)}
  unset RUN_STEP_BEFORE
  t0=$(date -u +%s)
  "${CTRL[@]}" sync --node "$NODE" "$@" --json > "$EVID/B3-$tag.json" 2>"$EVID/B3-$tag.err"
  rc=$?
  t1=$(date -u +%s)
  after=$(state)
  python3 - "$EVID/B3-$tag.json" "$tag" "$desc" "$rc" "$((t1 - t0))" "$before" "$after" \
    >> "$EVID/B3-steps.jsonl" <<'PY'
import json, sys
path, tag, desc, rc, elapsed, before, after = sys.argv[1:8]
def parse_state(text):
    out = {}
    for part in text.split():
        k, _, v = part.partition("=")
        out[k] = None if v in ("?", "") else int(v)
    return out
doc = {}
try:
    doc = json.loads(open(path, encoding="utf-8").read())
except Exception:
    pass
row = (doc.get("nodes") or [{}])[0] if isinstance(doc, dict) else {}
b, a = parse_state(before), parse_state(after)
rec = {
    "tag": tag, "description": desc, "exit_code": int(rc), "elapsed_s": int(elapsed),
    "state": doc.get("state") if isinstance(doc, dict) else None,
    "status": row.get("status"), "error_code": row.get("error_code"),
    "error_phase": row.get("error_phase"), "retryable": row.get("retryable"),
    "audit_pages": row.get("audit_pages"), "inserted": row.get("inserted"),
    "start_cursor": row.get("after"), "end_cursor": row.get("last_export_seq"),
    "more_pending": row.get("more_pending"), "error": row.get("error"),
    "before": b, "after": a,
    "cursor_continuity": (row.get("after") == b["cursor"]
                          if row and b.get("cursor") is not None else None),
    "no_row_past_cursor": (a["max_seq"] <= a["cursor"]
                           if a.get("max_seq") is not None and a.get("cursor") is not None
                           else None),
}
print(json.dumps(rec, ensure_ascii=False))
PY
  note "  $tag: rc=$rc ${before} -> ${after} ($((t1 - t0))s)"
  cat "$EVID/B3-$tag.err" >> "$ROOT/batch3.log"
}

note "-- A7a: one page only (bounded resume boundary) --"
run_step A7a "one page only" --page-size "$PAGE_SIZE" --max-pages 1 --timeout "$TIMEOUT" --stdout-cap "$STDOUT_CAP" --budget "$BUDGET"

note "-- A9a: second page timeout (page must not commit) --"
run_step A9a "second page timeout" --page-size "$PAGE_SIZE" --timeout 1 --stdout-cap "$STDOUT_CAP" --budget 120

note "-- A9b: oversized page (stdout cap) --"
run_step A9b "oversized page" --page-size "$PAGE_SIZE" --timeout "$TIMEOUT" --stdout-cap 1024 --budget 120

note "-- A9c: run budget exhausted before a page --"
run_step A9c "budget exhausted before a page" --page-size "$PAGE_SIZE" --timeout "$TIMEOUT" --stdout-cap "$STDOUT_CAP" --budget 2

lock_db() {   # hold an exclusive lock on the ISOLATED cache for LOCK_SECONDS
  python3 - "$DB" "$LOCK_SECONDS" <<'LOCKER' &
import sqlite3, sys, time
c = sqlite3.connect(sys.argv[1])
c.execute("BEGIN EXCLUSIVE")
time.sleep(float(sys.argv[2]))
c.rollback()
c.close()
LOCKER
}

note "-- A9d0: cache locked BEFORE the run (connect-time failure) --"
RUN_STEP_BEFORE=$(state)   # read before the exclusive lock is taken
lock_db
LOCK_PID=$!
sleep 1
run_step A9d0 "connect-time lock" --page-size "$PAGE_SIZE" --timeout "$TIMEOUT" --stdout-cap "$STDOUT_CAP" --budget 5
wait "$LOCK_PID" 2>/dev/null || true

note "-- A9d1: cache locked AFTER the page fetch (import-time lock must outlive the budget) --"
D1_BEFORE=$(state)
D1_T0=$(date -u +%s)
"${CTRL[@]}" sync --node "$NODE" --page-size "$PAGE_SIZE" --timeout "$TIMEOUT" \
  --stdout-cap "$STDOUT_CAP" --budget 30 --json \
  > "$EVID/B3-A9d1.json" 2>"$EVID/B3-A9d1.err" &
SYNC_PID=$!
sleep 3
python3 - "$DB" "$LOCK_SECONDS_IMPORT" <<'LOCKER2' &
import sqlite3, sys, time
c = sqlite3.connect(sys.argv[1])
c.execute("BEGIN EXCLUSIVE")
time.sleep(float(sys.argv[2]))
c.rollback()
c.close()
LOCKER2
LOCK_PID=$!
wait "$SYNC_PID" 2>/dev/null
SYNC_RC=$?
D1_T1=$(date -u +%s)
wait "$LOCK_PID" 2>/dev/null || true
python3 - "$EVID/B3-A9d1.json" "$EVID/B3-steps.jsonl" "$D1_BEFORE" "$(state)" "$SYNC_RC" "$((D1_T1 - D1_T0))" <<'RECORD'
import json, sys
path, out, before, after, sync_rc, elapsed = sys.argv[1:7]
def parse(text):
    return {k: (None if v in ("?", "") else int(v))
            for k, _, v in (p.partition("=") for p in text.split())}
try:
    doc = json.loads(open(path, encoding="utf-8").read())
except Exception:
    doc = {}
row = (doc.get("nodes") or [{}])[0] if isinstance(doc, dict) else {}
b, a = parse(before), parse(after)
rec = {"tag": "A9d1", "description": "import-time lock vs budget",
       "exit_code": int(sync_rc) if str(sync_rc).isdigit() else None,
       "elapsed_s": int(elapsed), "state": doc.get("state"),
       "status": row.get("status"), "error_code": row.get("error_code"),
       "error_phase": row.get("error_phase"), "retryable": row.get("retryable"),
       "audit_pages": row.get("audit_pages"), "inserted": row.get("inserted"),
       "start_cursor": row.get("after"), "end_cursor": row.get("last_export_seq"),
       "more_pending": row.get("more_pending"), "error": row.get("error"),
       "before": b, "after": a,
       "cursor_continuity": (row.get("after") == b.get("cursor")
                             if row and b.get("cursor") is not None else None),
       "no_row_past_cursor": (a["max_seq"] <= a["cursor"]
                              if a.get("max_seq") is not None and a.get("cursor") is not None
                              else None)}
with open(out, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
print("  A9d1:", rec["status"], rec["error_code"], rec["error_phase"])
RECORD
unset D1_BEFORE

wait "$LOCK_PID" 2>/dev/null || true

note "-- A9e: interrupt a running catch-up (SIGINT), then resume (A6/A7b) --"
E_BEFORE=$(state)
E_T0=$(date -u +%s)
python3 - "$INTERRUPT_AFTER" "$UNPACK/bin/vcl-fleet" "$NODE" "$PAGE_SIZE" "$MAX_PAGES" \
  "$TIMEOUT" "$STDOUT_CAP" "$BUDGET" "$EVID/B3-A9e-interrupted.json" \
  "$EVID/B3-A9e-interrupted.err" "$EVID/B3-A9e-rc.txt" <<'INTERRUPT'
import signal, subprocess, sys, time
from pathlib import Path

(after, ctrl, node, page_size, max_pages, timeout, cap, budget, out, err, rcfile) = sys.argv[1:12]
# the unpacked bin/vcl-fleet has no exec bit on ext4 -> run it via this interpreter
cmd = [sys.executable, ctrl, "sync", "--node", node, "--page-size", page_size,
       "--max-pages", max_pages, "--timeout", timeout, "--stdout-cap", cap,
       "--budget", budget, "--json"]
with open(out, "w", encoding="utf-8") as fo, open(err, "w", encoding="utf-8") as fe:
    proc = subprocess.Popen(cmd, stdout=fo, stderr=fe)
    time.sleep(float(after))
    proc.send_signal(signal.SIGINT)   # default disposition here: real interrupt
    rc = proc.wait()
Path(rcfile).write_text(str(rc) + "\n", encoding="utf-8")
print(f"  A9e: SIGINT after {after}s -> child rc={rc} "
      f"({'killed by signal' if rc < 0 else 'exited'})")
INTERRUPT
E_T1=$(date -u +%s)
E_RC=$(cat "$EVID/B3-A9e-rc.txt" 2>/dev/null || echo 0)
E_AFTER=$(state)
python3 - "$EVID/B3-steps.jsonl" "$E_BEFORE" "$E_AFTER" "$E_RC" "$((E_T1 - E_T0))" "$INTERRUPT_AFTER" <<'EREC'
import json, sys
out, before, after, rc, elapsed, after_s = sys.argv[1:7]

def parse(text):
    return {k: (None if v in ("?", "") else int(v))
            for k, _, v in (p.partition("=") for p in text.split())}

b, a = parse(before), parse(after)
rec = {"tag": "A9e", "description": f"SIGINT after {after_s}s",
       "exit_code": int(rc), "elapsed_s": int(elapsed), "state": None,
       "status": None, "error_code": None, "error_phase": None,
       "retryable": None, "audit_pages": None, "inserted": None,
       "start_cursor": b.get("cursor"), "end_cursor": a.get("cursor"),
       "more_pending": None, "error": None, "before": b, "after": a,
       "cursor_continuity": None,
       "no_row_past_cursor": (a["max_seq"] <= a["cursor"]
                              if a.get("max_seq") is not None and a.get("cursor") is not None
                              else None),
       "interrupt_effective": int(rc) != 0,
       "committed_pages_kept": (b.get("cursor") is not None and a.get("cursor") is not None
                                and a["cursor"] >= b["cursor"])}
with open(out, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
print(f"  A9e: rc={rc} cursor {b.get('cursor')} -> {a.get('cursor')} "
      f"interrupt_effective={rec['interrupt_effective']}")
EREC
unset E_BEFORE

note "-- A6/A7b: resume with the production-like parameters --"
A6_PAGES=${A6_MAX_PAGES:-$MAX_PAGES}
[[ "$A6_PAGES" != "$MAX_PAGES" ]] && note "  (bounded resume: max_pages=$A6_PAGES)"
run_step A6 "resume after interrupt" --page-size "$PAGE_SIZE" --max-pages "$A6_PAGES" --timeout "$TIMEOUT" --stdout-cap "$STDOUT_CAP" --budget "$BUDGET"

note "-- A8: sync --full refresh on the caught-up cache (snapshot freshness) --"
A8_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
A8_T0=$(date -u +%s)
A8_BEFORE=$(state)
"${CTRL[@]}" status --json > "$EVID/B3-A8-status-before.json" 2>&1
"${CTRL[@]}" sync --full --node "$NODE" --page-size "$PAGE_SIZE" --timeout "$TIMEOUT" \
  --stdout-cap "$STDOUT_CAP" --budget "$BUDGET" --json \
  > "$EVID/B3-A8-full.json" 2>"$EVID/B3-A8-full.err"
A8_RC=$?
"${CTRL[@]}" status --json > "$EVID/B3-A8-status-after.json" 2>&1
"${CTRL[@]}" verify --json > "$EVID/B3-A8-verify.json" 2>&1
A8_AFTER=$(state)
A8_T1=$(date -u +%s)
python3 - "$EVID" "$A8_START" "$A8_RC" "$A8_BEFORE" "$A8_AFTER" "$NODE" "$((A8_T1 - A8_T0))" <<'A8REC'
import json, sys
from pathlib import Path
evid, started, rc, before, after, node, elapsed = sys.argv[1:8]

def load(name):
    p = Path(evid) / name
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def parse(text):
    return {k: (None if v in ("?", "") else int(v))
            for k, _, v in (q.partition("=") for q in text.split())}

full = load("B3-A8-full.json")
status = load("B3-A8-status-after.json")
verify = load("B3-A8-verify.json")
row = (full.get("nodes") or [{}])[0] if isinstance(full, dict) else {}
srow = next((r for r in status.get("nodes", []) if r.get("name") == node), {})
b, a = parse(before), parse(after)
rec = {
    "tag": "A8", "description": "sync --full snapshot refresh",
    "exit_code": int(rc), "elapsed_s": int(elapsed), "state": full.get("state"),
    "operation": full.get("operation"), "status": row.get("status"),
    "error_code": row.get("error_code"), "error_phase": row.get("error_phase"),
    "audit_pages": row.get("audit_pages"), "inserted": row.get("inserted"),
    "start_cursor": row.get("after"), "end_cursor": row.get("last_export_seq"),
    "more_pending": row.get("more_pending"), "error": row.get("error"),
    "before": b, "after": a,
    "cursor_continuity": (row.get("after") == b.get("cursor")
                          if row and b.get("cursor") is not None else None),
    "no_row_past_cursor": (a["max_seq"] <= a["cursor"]
                           if a.get("max_seq") is not None and a.get("cursor") is not None
                           else None),
    "snapshot_synced_at": srow.get("synced_at"),
    "snapshot_fresh": bool(srow.get("synced_at") and str(srow["synced_at"]) >= started),
    "snapshot_instance_id": srow.get("instance_id"),
    "verify_ssh": next((r.get("ssh") for r in verify.get("nodes", [])
                        if r.get("name") == node), None),
    "verify_node_ok": next((r.get("ok") for r in verify.get("nodes", [])
                            if r.get("name") == node), None),
    "verify_fleet_ok": verify.get("ok"),   # fleet-wide: other nodes can fail
}
with open(Path(evid) / "B3-steps.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
print(f"  A8: operation={rec['operation']} status={rec['status']} "
      f"synced_at={rec['snapshot_synced_at']} fresh={rec['snapshot_fresh']} "
      f"cursor={rec['start_cursor']}->{rec['end_cursor']}")
A8REC
[[ -s "$EVID/B3-A8-full.err" ]] && cat "$EVID/B3-A8-full.err" >> "$ROOT/batch3.log"

python3 - "$DB" <<'PY'
import os, sqlite3, sys
p = sys.argv[1]
def q(conn, sql, default=0):
    try:
        row = conn.execute(sql).fetchone()
        return row[0] if row else default
    except sqlite3.Error:
        return "?"
c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
rows = q(c, "SELECT COUNT(*) FROM audit_events")
mx = q(c, "SELECT COALESCE(MAX(export_seq),0) FROM audit_events")
cur = q(c, "SELECT COALESCE(last_export_seq,0) FROM sync_cursor")
partial = q(c, "SELECT COUNT(*) FROM audit_events WHERE export_seq > " + str(cur))
c.close()
print(f"final: rows={rows} max_export_seq={mx} cursor={cur} rows_past_cursor={partial}")
print(f"size_bytes={os.path.getsize(p)}")
PY

fingerprint b3after
for kind in ws db bindings; do
  diff -q "$EVID/prod-$kind-b3before.sha256" "$EVID/prod-$kind-b3after.sha256" >/dev/null 2>&1 \
    && ok "production $kind unchanged" || bad "production $kind CHANGED"
done
diff -q "$EVID/prod-stat-b3before.txt" "$EVID/prod-stat-b3after.txt" >/dev/null 2>&1 \
  && ok "production sizes/mtimes unchanged" \
  || note "NOTE: production size/mtime diff (explain it)"

python3 - "$EVID" <<'PY'
import json, re, sys
from pathlib import Path
evid = Path(sys.argv[1])
steps = [json.loads(l) for l in (evid / "B3-steps.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
LEAK = (("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
        ("port", re.compile(r"\bport\s+\d+\b", re.I)),
        ("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
        ("connection_refused", re.compile(r"connection refused", re.I)),
        ("auth_text", re.compile(r"permission denied|publickey|too many authentication", re.I)))
lines = ["# Phase A batch 3 summary (sanitized)", "",
         "| step | exit | state | status | code | phase | pages | inserted | cursor | elapsed |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
bad = []
unknown = []
for s in steps:
    lines.append("| {tag} | {exit_code} | {state} | {status} | {error_code} | {error_phase} | {audit_pages} | {inserted} | {start_cursor}->{end_cursor} | {elapsed} |".format(elapsed=("-" if s.get("elapsed_s") is None else str(s["elapsed_s"]) + "s"), **s))
    if s.get("cursor_continuity") is False:
        bad.append(f"{s['tag']}: run did not start at the committed cursor")
    if s.get("no_row_past_cursor") is False:
        bad.append(f"{s['tag']}: rows exist past the committed cursor (partial page)")
    if s.get("no_row_past_cursor") is None:
        unknown.append(s["tag"])
    elif s.get("cursor_continuity") is None and s.get("tag") != "A9e":
        unknown.append(s["tag"])
    text = s.get("error") or ""
    if text:
        flags = [n for n, rx in LEAK if rx.search(text)]
        lines.append(f"  - {s['tag']} error text: {text[:160]!r} flags={flags or 'clean'}")
inv = [f"- FAIL {b}" for b in bad]
if unknown:
    inv.append("- UNKNOWN (no node row and/or the cache was locked during measurement): " + ", ".join(unknown))
if not inv:
    inv.append("- cursor continuity and no-partial-page holds for every step")
a8 = next((s for s in steps if s.get("tag") == "A8"), None)
if a8:
    lines += ["", "## A8 sync --full snapshot freshness", "",
              f"- operation: {a8.get('operation')}   status: {a8.get('status')}   exit: {a8.get('exit_code')}",
              f"- snapshot synced_at: {a8.get('snapshot_synced_at')}   fresh (>= run start): {a8.get('snapshot_fresh')}",
              f"- verify: ssh={a8.get('verify_ssh')} node_ok={a8.get('verify_node_ok')} "
              f"fleet_ok={a8.get('verify_fleet_ok')} (fleet_ok also counts the AUTH_FAILED nodes)",
              f"- cursor: {a8.get('start_cursor')} -> {a8.get('end_cursor')}"]
lines += ["", "## Invariants", ""] + inv
(evid / "B3-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
PY

note "== batch 3 done: PASS=$PASS FAIL=$FAIL =="
BUNDLE="$(dirname "$ROOT")/$(basename "$ROOT")-phaseA-b3.tgz"
tar -C "$(dirname "$ROOT")" -czf "$BUNDLE" "$(basename "$ROOT")"
note "bundle: $BUNDLE"
note "bundle sha256: $(sha256sum -- "$BUNDLE" | awk '{print $1}')"
note "hand back: evidence/B3-summary.md, B3-steps.jsonl, B3-A6.json, batch3.log"
exit $(( FAIL > 0 ? 1 : 0 ))
