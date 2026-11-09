#!/usr/bin/env bash
# Phase A batches for the frozen 0.5.3 candidate (see
# docs/plans/RC_0.5.3_VERIFICATION_PLAN.md §3).
#
#   bash tmp/phase-a-batch1.sh            # batch 1: A0 candidate check, A1 import,
#                                         #          A2 binding template, fingerprint(before)
#   # edit and run evidence/A2-bind.sh, then:
#   bash tmp/phase-a-batch1.sh --phase a3 # batch 2: A3 baseline, A4 capability matrix,
#                                         #          fingerprint(after), sanitized report, bundle
#
# The Controller always runs from the frozen candidate ZIP, against an isolated
# workspace/state/config triple. Nodes are only read (identity/status/capabilities);
# the production workspace, cache and bindings are never written.
set -uo pipefail

PHASE="a1"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase) PHASE=${2:?}; shift 2 ;;
    --phase=*) PHASE=${1#*=}; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

REPO=${REPO:-$(pwd)}
PROD_WS=${PROD_WS:-${VCL_FLEET_HOME:-$HOME/.config/vincula}}
PROD_STATE=${PROD_STATE:-${VCL_FLEET_LOCAL_STATE:-$HOME/.local/state/vincula}}
PROD_CONFIG=${PROD_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}}
CTRL_ZIP=${CTRL_ZIP:-$REPO/dist/vincula-controller-0.5.3.zip}
EXPECT_ZIP_SHA=65dbcc7b4ae19cfa480698ee2616ad67f43632460986ecae72ae89cfce0137a7
RUN_A4=${RUN_A4:-1}
# The production cache is expected to be live (monitor/sync keep writing), so
# hashing it would report false changes. Default: size+mtime only; set
# HASH_PROD_DB=1 for a byte-exact comparison while the Controller is stopped.
HASH_PROD_DB=${HASH_PROD_DB:-0}
# Copy the identity-file paths of the refs used by the imported nodes straight
# from the production bindings into the isolated A2-bind.sh (same machine, same
# user). Off by default: review the generated file before running it.
PREFILL_BINDINGS=${PREFILL_BINDINGS:-0}
OPERATOR=${VCL_OPERATOR:-unset}
ROOT=${VERIFY_ROOT:-$HOME/vcl-verify-$(date -u +%Y%m%dT%H%M%SZ)}
EVID="$ROOT/evidence"
META="$ROOT/batch-meta.env"
PASS=0
FAIL=0

note() { printf '%s\n' "$*" | tee -a "$ROOT/batch.log"; }
ok()   { PASS=$((PASS + 1)); note "PASS  $*"; }
bad()  { FAIL=$((FAIL + 1)); note "FAIL  $*"; }

if [[ "$PHASE" == "a3" ]]; then
  [[ -f "$META" ]] || { echo "STOP: $META missing; run batch 1 first with the same VERIFY_ROOT" >&2; exit 2; }
  # shellcheck disable=SC1090
  source "$META"
  mkdir -p "$EVID"
  export VCL_FLEET_HOME="$ROOT/ws" VCL_FLEET_LOCAL_STATE="$ROOT/state"
  export XDG_CONFIG_HOME="$ROOT/config" TMPDIR="$ROOT/tmp"
  CTRL="python3 $UNPACK/bin/vcl-fleet"
else
  mkdir -p "$EVID"
  note "== phase A batch 1 (A0/A1/A2) =="
  note "operator=$OPERATOR  window_start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  note "repo=$REPO  prod_ws=$PROD_WS  prod_state=$PROD_STATE  verify_root=$ROOT"

  [[ -f "$CTRL_ZIP" ]] || { bad "candidate zip missing: $CTRL_ZIP"; exit 2; }
  ZIP_SHA=$(sha256sum -- "$CTRL_ZIP" | awk '{print $1}')
  [[ "$ZIP_SHA" == "$EXPECT_ZIP_SHA" ]] && ok "candidate zip sha256 matches the frozen digest" \
    || bad "candidate zip sha256 mismatch (got $ZIP_SHA)"
  python3 -c 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$CTRL_ZIP" "$ROOT/ctrl"
  UNPACK="$ROOT/ctrl/vincula-controller-0.5.3"
  [[ -f "$UNPACK/bin/vcl-fleet" ]] || { bad "unpacked controller missing bin/vcl-fleet"; exit 2; }

  export VCL_FLEET_HOME="$ROOT/ws" VCL_FLEET_LOCAL_STATE="$ROOT/state"
  export XDG_CONFIG_HOME="$ROOT/config" TMPDIR="$ROOT/tmp"
  mkdir -p "$VCL_FLEET_HOME" "$VCL_FLEET_LOCAL_STATE" "$XDG_CONFIG_HOME" "$TMPDIR"
  case "$VCL_FLEET_LOCAL_STATE" in "$PROD_STATE"*) bad "isolated state is production state"; exit 2;; esac
  case "$XDG_CONFIG_HOME" in "$PROD_CONFIG") bad "isolated config is production config"; exit 2;; esac
  case "$VCL_FLEET_HOME" in "$PROD_WS") bad "isolated home is production home"; exit 2;; esac
  ok "environment isolation guards passed"

  CTRL="python3 $UNPACK/bin/vcl-fleet"
  note "free space at VERIFY_ROOT: $(df -h --output=avail "$ROOT" 2>/dev/null | tail -1 | tr -d ' ')"
  note "NOTE: an isolated cache starts at cursor 0 and re-pulls the retained window;"
  note "      budget disk for it (the production cache is 2.1 GB for seven nodes)."
  VER=$($CTRL version 2>&1)
  [[ "$VER" == "vcl-fleet 0.5.3" ]] && ok "candidate reports $VER" || bad "unexpected version: $VER"

  fingerprint() {
    local tag=$1
    find "$PROD_WS" -type f -print0 2>/dev/null | sort -z | xargs -0 -r sha256sum > "$EVID/prod-ws-$tag.sha256"
    if [[ "$HASH_PROD_DB" == "1" ]]; then
      find "$PROD_STATE" -name 'fleet.db' -print0 2>/dev/null | sort -z \
        | xargs -0 -r sha256sum > "$EVID/prod-db-$tag.sha256"
    else
      { find "$PROD_STATE" -name 'fleet.db' -printf '%p %s %T@\n' 2>/dev/null | sort; } \
        > "$EVID/prod-db-$tag.sha256"
      printf '# size+mtime only (HASH_PROD_DB=0; the live production cache keeps writing)\n' \
        >> "$EVID/prod-db-$tag.sha256"
    fi
    find "$PROD_CONFIG/vincula/controllers" -type f -print0 2>/dev/null | sort -z \
      | xargs -0 -r sha256sum > "$EVID/prod-bindings-$tag.sha256"
    { find "$PROD_WS" "$PROD_STATE" "$PROD_CONFIG/vincula/controllers" -type f \
        -printf '%p %s %T@\n' 2>/dev/null | sort; } > "$EVID/prod-stat-$tag.txt"
  }
  fingerprint before
  python3 - "$PROD_WS/workspace.json" "$EVID" <<'PY'
import json, sys
from pathlib import Path
src, out = Path(sys.argv[1]), Path(sys.argv[2])
doc = {"present": src.is_file()}
if src.is_file():
    m = json.loads(src.read_text(encoding="utf-8"))
    doc.update({k: m.get(k) for k in ("fleet_id", "revision", "state_digest")})
(out / "prod-workspace-before.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
print("prod fleet_id/revision:", doc.get("fleet_id"), doc.get("revision"))
PY

  note "-- A1: export the production registry (read-only) and import into isolation --"
  if env VCL_FLEET_HOME="$PROD_WS" VCL_FLEET_LOCAL_STATE="$PROD_STATE" XDG_CONFIG_HOME="$PROD_CONFIG" \
       python3 "$REPO/lib/vincula-fleet.py" workspace export "$EVID/prod-ws-export.tgz" >>"$ROOT/batch.log" 2>&1; then
    ok "production workspace export (A1)"
  else
    bad "production workspace export failed"; exit 2
  fi
  if $CTRL workspace import "$EVID/prod-ws-export.tgz" > "$EVID/A1-import.txt" 2>&1; then
    tee -a "$ROOT/batch.log" < "$EVID/A1-import.txt"
    ok "isolated workspace import (A1)"
  else
    bad "isolated workspace import failed"; tee -a "$ROOT/batch.log" < "$EVID/A1-import.txt"; exit 2
  fi
  $CTRL workspace show > "$EVID/A1-workspace-show.json" 2>&1
  $CTRL node list > "$EVID/A1-nodes.txt" 2>&1
  python3 - "$EVID/prod-workspace-before.json" "$EVID/A1-workspace-show.json" <<'PY' | tee -a "$ROOT/batch.log"
import json, sys
before = json.loads(open(sys.argv[1]).read())
after = json.loads(open(sys.argv[2]).read())
same = before.get("fleet_id") == after.get("fleet_id")
print(f"fleet_id match: {same} (before {before.get('fleet_id')} / after {after.get('fleet_id')})")
print(f"revision: {before.get('revision')} -> {after.get('revision')}")
PY

  note "-- A2: bind the imported credential refs in the ISOLATED config --"
  PROD_FLEET_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("fleet_id",""))' "$VCL_FLEET_HOME/workspace.json" 2>/dev/null)
  PROD_BINDINGS_FILE="$PROD_CONFIG/vincula/controllers/${PROD_FLEET_ID}/credential-bindings.json"
  [[ "$PREFILL_BINDINGS" == "1" && -f "$PROD_BINDINGS_FILE" ]]     && note "prefilling ref paths from $PROD_BINDINGS_FILE"     || PROD_BINDINGS_FILE=""
  python3 - "$VCL_FLEET_HOME/fleet.json" "$EVID" "$ROOT" "$UNPACK/bin/vcl-fleet" "$PROD_BINDINGS_FILE" <<'PY' | tee -a "$ROOT/batch.log"
import json, sys
from pathlib import Path
reg, out, root, ctrl = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
prefill = Path(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else None
nodes = json.loads(reg.read_text(encoding="utf-8"))["nodes"]
prod_bindings = {}
if prefill is not None and prefill.is_file():
    try:
        prod_bindings = (json.loads(prefill.read_text(encoding="utf-8")) or {}).get("bindings") or {}
    except Exception:
        prod_bindings = {}
lines = ["#!/usr/bin/env bash",
         "# Generated by phase-a-batch1.sh.",
         "# Run with:  source <verify_root>/batch-meta.env && bash A2-bind.sh",
         "# Replace any remaining <..._KEY_PATH> placeholder first.",
         "set -euo pipefail",
         '[[ -n "${VCL_FLEET_HOME:-}" ]] || { echo "source batch-meta.env first" >&2; exit 2; }',
         f'CTRL="python3 {ctrl}"']
refs = {}
for n in nodes:
    for purpose in ("admin", "observe"):
        ref = n.get(f"{purpose}_credential_ref")
        if ref:
            refs.setdefault(ref, set()).add(f"{n['name']}:{purpose}")
mapping = [{"ref": r, "used_by": sorted(u)} for r, u in sorted(refs.items())]
if prefill is not None:
    lines.insert(1, "# NOTE: identity-file paths were copied from the production bindings")
    lines.insert(2, "# on this machine; keep this generated file local.")
for ref, users in sorted(refs.items()):
    lines.append(f'# ref used by: {", ".join(sorted(users))}')
    entry = prod_bindings.get(ref) if isinstance(prod_bindings, dict) else None
    if isinstance(entry, dict) and entry.get("type") == "identity_file" and entry.get("path"):
        lines.append(f'$CTRL access bind {ref} --identity-file "{entry["path"]}"')
    elif isinstance(entry, dict) and entry.get("type") == "openssh-default":
        lines.append(f'$CTRL access bind {ref} --openssh-default')
    else:
        lines.append(f'$CTRL access bind {ref} --identity-file "<{ref.upper()}_KEY_PATH>"')
no_ref = [n["name"] for n in nodes
          if not n.get("observe_credential_ref") and not n.get("admin_credential_ref")]
for name in no_ref:
    lines.append(f'# node {name}: no credential ref -> uses OpenSSH default identity '
                 '(agent / ~/.ssh) for both classes; record this in the evidence')
(out / "A2-bind.sh").write_text("\n".join(lines) + "\n", encoding="utf-8")
(out / "A2-refs.json").write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
(out / "A2-nodes.json").write_text(
    json.dumps([{k: n.get(k) for k in ("name", "admin_credential_ref", "observe_credential_ref")}
                for n in nodes], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"nodes={len(nodes)} distinct_refs={len(mapping)}")
for m in mapping:
    print("  ref", m["ref"], "<-", ", ".join(m["used_by"]))
if no_ref:
    print("  nodes with no credential ref (OpenSSH default identity):", ", ".join(no_ref))
PY

  cat > "$META" <<EOF
# Source this file to work in the isolated verification environment.
export VCL_FLEET_HOME="$VCL_FLEET_HOME"
export VCL_FLEET_LOCAL_STATE="$VCL_FLEET_LOCAL_STATE"
export XDG_CONFIG_HOME="$XDG_CONFIG_HOME"
export TMPDIR="$TMPDIR"
ROOT="$ROOT"
EVID="$EVID"
UNPACK="$UNPACK"
PROD_WS="$PROD_WS"
PROD_STATE="$PROD_STATE"
PROD_CONFIG="$PROD_CONFIG"
OPERATOR="$OPERATOR"
WINDOW_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
EOF
  MISSING=$($CTRL access list 2>/dev/null | wc -l)
  note "isolated bindings present: $MISSING"
  note "== batch 1 done: PASS=$PASS FAIL=$FAIL =="
  if [[ "$PREFILL_BINDINGS" == "1" && -n "$PROD_BINDINGS_FILE" ]]; then
    note "next: 1) review $EVID/A2-bind.sh (paths prefilled from production bindings)"
  else
    note "next: 1) edit $EVID/A2-bind.sh (replace <..._KEY_PATH>)"
  fi
  note "      2) source $META && bash $EVID/A2-bind.sh"
  note "      3) VERIFY_ROOT=$ROOT bash tmp/phase-a-batch1.sh --phase a3"
  exit $(( FAIL > 0 ? 1 : 0 ))
fi

# ------------------------------------------------------------------ phase a3
note "== phase A batch 2 (A3/A4 + production re-check) =="
note "operator=$OPERATOR  window_start_utc=$WINDOW_START"

note "-- A3: read-only baseline (probe / verify / status) --"
$CTRL probe --json > "$EVID/A3-probe.json" 2>"$EVID/A3-probe.err"; P1=$?
$CTRL verify --json > "$EVID/A3-verify.json" 2>"$EVID/A3-verify.err"; P2=$?
$CTRL status --json > "$EVID/A3-status.json" 2>"$EVID/A3-status.err"; P3=$?
$CTRL status > "$EVID/A3-status.txt" 2>&1
note "probe_exit=$P1 verify_exit=$P2 status_exit=$P3"

if [[ "$RUN_A4" == "1" ]]; then
  note "-- A4: capability matrix per node (read-only) --"
  mapfile -t NAMES < <(python3 -c 'import json,sys; [print(n["name"]) for n in json.load(open(sys.argv[1]))["nodes"]]' "$VCL_FLEET_HOME/fleet.json")
  for n in "${NAMES[@]}"; do
    $CTRL capabilities "$n" --json > "$EVID/A4-cap-$n.json" 2>&1
    printf 'capabilities %s exit=%s\n' "$n" "$?" >> "$ROOT/batch.log"
  done
fi

find "$PROD_WS" -type f -print0 2>/dev/null | sort -z | xargs -0 -r sha256sum > "$EVID/prod-ws-after.sha256"
if [[ "$HASH_PROD_DB" == "1" ]]; then
  find "$PROD_STATE" -name 'fleet.db' -print0 2>/dev/null | sort -z \
    | xargs -0 -r sha256sum > "$EVID/prod-db-after.sha256"
else
  { find "$PROD_STATE" -name 'fleet.db' -printf '%p %s %T@\n' 2>/dev/null | sort; } \
    > "$EVID/prod-db-after.sha256"
  printf '# size+mtime only (HASH_PROD_DB=0; the live production cache keeps writing)\n' \
    >> "$EVID/prod-db-after.sha256"
fi
find "$PROD_CONFIG/vincula/controllers" -type f -print0 2>/dev/null | sort -z \
  | xargs -0 -r sha256sum > "$EVID/prod-bindings-after.sha256"
{ find "$PROD_WS" "$PROD_STATE" "$PROD_CONFIG/vincula/controllers" -type f \
    -printf '%p %s %T@\n' 2>/dev/null | sort; } > "$EVID/prod-stat-after.txt"
note "prod db check: $( [[ "$HASH_PROD_DB" == "1" ]] && echo 'sha256' || echo 'size+mtime (HASH_PROD_DB=0)' )"
for kind in ws db bindings; do
  if diff -q "$EVID/prod-$kind-before.sha256" "$EVID/prod-$kind-after.sha256" >/dev/null 2>&1; then
    ok "production $kind unchanged"
  else
    bad "production $kind CHANGED (see prod-$kind-before/after.sha256)"
  fi
done
diff -q "$EVID/prod-stat-before.txt" "$EVID/prod-stat-after.txt" >/dev/null 2>&1 \
  && ok "production sizes/mtimes unchanged" \
  || note "NOTE: production size/mtime diff present (explain it: the live Controller may be writing)"

python3 - "$EVID" "$OPERATOR" "$WINDOW_START" <<'PY'
import hashlib, json, re, sys
from pathlib import Path

evid, operator, window = Path(sys.argv[1]), sys.argv[2], sys.argv[3]

LEAK_PATTERNS = (
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("port", re.compile(r"\bport\s+\d+\b", re.I)),
    ("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
    ("connection_refused", re.compile(r"connection refused", re.I)),
    ("auth_text", re.compile(r"permission denied|publickey|too many authentication", re.I)),
    ("remote_text", re.compile(r"fake-ssh:|unknown vcl command", re.I)),
)


def leak_scan(text):
    if not text:
        return []
    return [name for name, rx in LEAK_PATTERNS if rx.search(text)]


def short(value):
    return None if not value else "sha256:" + hashlib.sha256(str(value).encode()).hexdigest()[:12]


def load(name):
    p = evid / name
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


report = {"operator": operator, "window_start_utc": window, "nodes": {}}
for doc_name, kind in (("A3-probe.json", "probe"), ("A3-verify.json", "verify"), ("A3-status.json", "status")):
    doc = load(doc_name)
    if not isinstance(doc, dict):
        continue
    for row in doc.get("nodes", []):
        entry = report["nodes"].setdefault(row.get("name", "?"), {})
        if kind == "probe":
            entry["probe"] = {k: row.get(k) for k in
                              ("ssh", "ssh_reason", "proxy", "accounting", "clock",
                               "clock_skew_seconds", "vincula_version", "registry", "ok")}
            text = row.get("ssh_detail")
            if text:
                entry.setdefault("detail_scan", {})["ssh_detail"] = {
                    "text": str(text)[:160], "flags": leak_scan(str(text))}
        elif kind == "verify":
            entry["verify"] = {k: row.get(k) for k in
                               ("ssh", "ssh_reason", "ok", "vincula_version", "proxy", "accounting")}
            for field in ("ssh_detail", "clock_detail"):
                text = row.get(field)
                if text:
                    entry.setdefault("detail_scan", {})[field] = {
                        "text": str(text)[:160], "flags": leak_scan(str(text))}
            if isinstance(row.get("checks"), list):
                entry["verify_failed_checks"] = [c.get("name") for c in row["checks"]
                                                 if isinstance(c, dict) and c.get("ok") is False]
        else:
            entry["status"] = {k: row.get(k) for k in
                               ("ssh", "proxy", "accounting", "cursor_status",
                                "data_age", "last_sync_at", "synced_at")}
        entry["identity_ref"] = short(row.get("node_id"))
        entry["instance_ref"] = short(row.get("instance_id"))
for p in sorted(evid.glob("A4-cap-*.json")):
    name = p.stem[len("A4-cap-"):]
    doc = load(p.name)
    if isinstance(doc, dict):
        entry = report["nodes"].setdefault(name, {})
        entry["capabilities"] = {
            "state": doc.get("state"), "node_version": doc.get("node_version"),
            "capabilities": doc.get("capabilities")}
        text = doc.get("detail")
        if text:
            entry.setdefault("detail_scan", {})["capabilities_detail"] = {
                "text": str(text)[:160], "flags": leak_scan(str(text))}
report["refs"] = load("A2-refs.json")
report["nodes_registry"] = load("A2-nodes.json")
report["import"] = (evid / "A1-import.txt").read_text(encoding="utf-8").strip() \
    if (evid / "A1-import.txt").is_file() else None
(evid / "A1-A4-summary.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
lines = ["# Phase A batch summary (sanitized)", "", f"- operator: {operator}",
         f"- window start (UTC): {window}", "",
         "| node | ssh | reason | version | proxy | accounting | caps | cached_cursor |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
for name, entry in sorted(report["nodes"].items()):
    pr, caps, st = entry.get("probe", {}), entry.get("capabilities", {}), entry.get("status", {})
    version = (entry.get("verify", {}).get("vincula_version") or caps.get("node_version"))
    lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
        name, pr.get("ssh"), pr.get("ssh_reason"), version,
        pr.get("proxy"), pr.get("accounting"), caps.get("state"),
        st.get("cursor_status")))
flagged = {n: e["detail_scan"] for n, e in report["nodes"].items() if e.get("detail_scan")}
lines += ["", "## Remote-text leak scan (FR-04 check)",
          f"- fields with remote text: {len(flagged)}"
          if flagged else "- no remote text in any detail field"] + [
    f"- {n}.{f}: flags={v['flags'] or 'clean'}" for n, fields in flagged.items()
    for f, v in fields.items()]
(evid / "A1-A4-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
PY

note "== batch 2 done: PASS=$PASS FAIL=$FAIL =="
BUNDLE="$(dirname "$ROOT")/$(basename "$ROOT")-phaseA.tgz"
tar -C "$(dirname "$ROOT")" -czf "$BUNDLE" "$(basename "$ROOT")"
note "bundle: $BUNDLE"
note "bundle sha256: $(sha256sum -- "$BUNDLE" | awk '{print $1}')"
note "hand back: evidence/A1-A4-summary.md, A1-A4-summary.json, A1-nodes.txt, A2-refs.json, batch.log"
exit $(( FAIL > 0 ? 1 : 0 ))
