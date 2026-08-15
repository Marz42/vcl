#!/usr/bin/env bash
# Vincula v0.2.7 accounting soak protocol.
#
# LIVE-ONLY. Not invoked by tests/test.sh. 24h PASS is READY FOR RC (D20).
# 72h optional. Accelerated clocks / unit tests do NOT satisfy AC-2.7-09.
#
# This script never mutates the node: no systemctl, no reboot, no sqlite
# writes, no firewall changes. Inject subcommands print operator actions
# only. Snapshot / check / watch are read-only.
#
# Usage:
#   bash scripts/soak-0.2.7.sh              # print protocol (safe anywhere)
#   bash scripts/soak-0.2.7.sh protocol
#   VCL_SOAK_LIVE=1 bash scripts/soak-0.2.7.sh --live snapshot
#   VCL_SOAK_LIVE=1 bash scripts/soak-0.2.7.sh --live check
#   VCL_SOAK_LIVE=1 bash scripts/soak-0.2.7.sh --live watch
#   bash scripts/soak-0.2.7.sh inject-accountd
#
# Evidence directory (created only with --live / VCL_SOAK_LIVE=1):
#   ${SOAK_EVIDENCE_DIR:-/root/vcl-rc-evidence/0.2.7-soak}
# Do not write soak evidence into the git tree. docs/evidence/0.2.7-soak/
# is the in-repo destination after the live run is copied off-box (Phase 3).
set -u
IFS=$'\n\t'

ACCOUNTING_DB="${ACCOUNTING_DB:-/var/lib/vincula/accounting.db}"
EVIDENCE_DIR="${SOAK_EVIDENCE_DIR:-/root/vcl-rc-evidence/0.2.7-soak}"
WATCH_INTERVAL="${SOAK_INTERVAL:-3600}"
VCL_BIN="${VCL_BIN:-vcl}"

LIVE=0
COMMAND=""

usage() {
  cat <<'EOF'
Vincula 0.2.7 LIVE-ONLY soak protocol (AC-2.7-08 / AC-2.7-09 / D20).

Commands:
  protocol          Print the 24h/72h checklist (default; safe anywhere)
  criteria          Print PASS / FAIL / READY FOR RC exit criteria
  snapshot          Read-only baseline: verify + sqlite sums + stats + audit
  check             Read-only sanity: no negatives, schema 3, collector heartbeat
  watch             Repeat check every $SOAK_INTERVAL seconds (default 3600)
  inject-accountd   Print T+1h accountd restart steps (does not execute)
  inject-singbox    Print T+2h sing-box restart steps (does not execute)
  inject-clash      Print T+4h Clash API outage steps (does not execute)
  inject-dns        Print DNS/network failure steps (does not execute)
  inject-reboot     Print T+6h reboot steps (does not execute)

Live gates:
  snapshot / check / watch require a real Vincula node AND
  VCL_SOAK_LIVE=1 or --live. This script is not a unit test and must
  not be started from CI.

This script does not modify anything.
EOF
}

protocol() {
  cat <<'EOF'
======== Vincula 0.2.7 soak protocol (LIVE-ONLY) ========

Minimum duration: 24 hours wall-clock on a REAL node (AC-2.7-09).
Recommended:      72 hours. Optional; not required for READY FOR RC.
Does NOT count:   unit tests, accelerated clocks, this script's --help.

Evidence root (live node):  /root/vcl-rc-evidence/0.2.7-soak
In-tree copy (after soak):  docs/evidence/0.2.7-soak/  (directory may be created later)

Moment     Action                                              Evidence
---------  --------------------------------------------------  --------------------------------
T+0        vcl verify                                          snapshot/T+0.*
           sqlite SUM(upload_bytes), SUM(download_bytes)
           MAX(event_id)
           vcl stats today --json
           vcl audit user owner --from <now-1h> --to <now>
T+1h       systemctl restart vincula-accountd                  snapshot after restart
           Totals must not drop to a wipe; no negatives
T+2h       systemctl restart sing-box                          new generation OK;
                                                               no huge jump / replay
T+4h       Temporarily stop Clash API (experimental or         collector recovers;
           block 127.0.0.1:9090) then restore                  last_success_at fresh
T+6h       reboot                                              proxy + accounting up
                                                               (AC-2.7-08)
hourly     vcl verify + SUM monotonic                          watch/*.log
           (undercount allowed; explosion forbidden)
T+24h      Full checkpoint vs T+0                              no 24h evidence
                                                               => MUST NOT READY FOR RC
T+72h      Optional extra checkpoint                           recommended evidence

Inject scenarios (operator-run; this script only prints them):
  accountd restart     inject-accountd
  sing-box restart     inject-singbox
  Clash API outage     inject-clash
  DNS/network failure  inject-dns
  reboot               inject-reboot

Checkpoints every snapshot/check:
  [ ] no exploding totals (order-of-magnitude jump without traffic)
  [ ] no negative upload_bytes / download_bytes / baseline counters
  [ ] no replayed history (SUM must not reset to zero; event_id not reused)
  [ ] collector recovers (vincula-accountd active, last_success_at recent)
  [ ] vcl audit remains queryable
  [ ] schema_version == 3

Exit criteria: see `soak-0.2.7.sh criteria`.
EOF
}

criteria() {
  cat <<'EOF'
======== Exit criteria ========

PASS (24h soak) when ALL of:
  - Wall-clock >= 24h on a live Vincula node with real Clash poll traffic
  - T+0, T+1h, T+2h, T+4h, T+6h, hourly, and T+24h snapshots exist
  - SUM(upload_bytes)+SUM(download_bytes) never went negative
  - Totals never collapsed to a wipe of previously accounted bytes
  - Totals did not explode (no replay of Clash cumulative counters)
  - After each inject, collector recovered (last_success_at fresh, accountd active)
  - vcl verify non-zero only for documented operator issues, not schema/counter FAIL
  - vcl audit user owner --from/--to succeeded after injects
  - After reboot: sing-box AND vincula-accountd active (AC-2.7-08)

FAIL if any of:
  - Accounted bytes reset to zero across an accountd restart
  - Negative bytes in connections or poll_baseline
  - Closed generation overwritten / event_id reused after DELETE
  - Collector did not recover after Clash outage
  - Soak ran in CI, with fake time, or shorter than 24h

READY FOR RC (D20):
  24h soak PASS  AND  other P0/P1 + migration evidence
  No 24h soak    => READY WITH DOCUMENTED LIMITATIONS only
  72h soak       => recommended extra evidence, not mandatory

This batch does not run the soak. It only documents how to run it.
EOF
}

is_live_node() {
  [[ -d /etc/vincula ]] || return 1
  [[ -f "$ACCOUNTING_DB" ]] || return 1
  command -v "$VCL_BIN" >/dev/null 2>&1 || [[ -x /usr/local/bin/vcl ]] || return 1
  return 0
}

require_live() {
  if [[ "$LIVE" != "1" ]]; then
    printf 'REFUSED: LIVE-ONLY. Pass --live or set VCL_SOAK_LIVE=1 on a real node.\n' >&2
    printf 'Unit tests and accelerated clocks do NOT satisfy AC-2.7-09.\n' >&2
    printf 'This script does not modify anything; snapshot/check/watch are read-only.\n' >&2
    exit 2
  fi
  if ! is_live_node; then
    printf 'REFUSED: this host is not a Vincula live node.\n' >&2
    printf 'Need /etc/vincula, %s, and vcl on PATH.\n' "$ACCOUNTING_DB" >&2
    exit 2
  fi
}

stamp() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

vcl_cmd() {
  if command -v "$VCL_BIN" >/dev/null 2>&1; then
    command "$VCL_BIN" "$@"
  else
    /usr/local/bin/vcl "$@"
  fi
}

sqlite_sanity() {
  python3 - "$ACCOUNTING_DB" <<'PY'
import sqlite3, sys
from datetime import datetime, timezone

db = sys.argv[1]
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print(f"ts_utc\t{now}")
print(f"db\t{db}")
try:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
except sqlite3.Error as exc:
    print(f"error\tcannot open: {exc}")
    raise SystemExit(1)

def scalar(sql, default=""):
    try:
        row = conn.execute(sql).fetchone()
    except sqlite3.Error as exc:
        return f"err:{exc}"
    if not row or row[0] is None:
        return default
    return row[0]

schema = scalar("SELECT value FROM meta WHERE key='schema_version'")
print(f"schema_version\t{schema}")
print(f"last_success_at\t{scalar('SELECT value FROM meta WHERE key=\"last_success_at\"')}")
print(f"sum_upload\t{scalar('SELECT IFNULL(SUM(upload_bytes),0) FROM connections', '0')}")
print(f"sum_download\t{scalar('SELECT IFNULL(SUM(download_bytes),0) FROM connections', '0')}")
print(f"max_event_id\t{scalar('SELECT IFNULL(MAX(event_id),0) FROM connections', '0')}")
print(f"open_rows\t{scalar('SELECT COUNT(*) FROM connections WHERE closed_at IS NULL', '0')}")
print(f"total_rows\t{scalar('SELECT COUNT(*) FROM connections', '0')}")
print(f"neg_connections\t{scalar('SELECT COUNT(*) FROM connections WHERE upload_bytes<0 OR download_bytes<0', '0')}")
print(f"neg_baseline\t{scalar('SELECT COUNT(*) FROM poll_baseline WHERE last_upload_counter<0 OR last_download_counter<0 OR accounted_upload<0 OR accounted_download<0', '0')}")
print(f"baseline_rows\t{scalar('SELECT COUNT(*) FROM poll_baseline', '0')}")
print(f"sqlite_sequence\t{scalar('SELECT IFNULL(seq,0) FROM sqlite_sequence WHERE name=\"connections\"', '0')}")
conn.close()
if str(schema) != "3":
    raise SystemExit(1)
PY
}

run_snapshot() {
  local label=${1:-manual}
  local dest="${EVIDENCE_DIR}/${label}"
  mkdir -p "$dest"
  local ts
  ts=$(stamp)
  {
    printf 'label=%s\n' "$label"
    printf 'ts_utc=%s\n' "$ts"
    printf 'host=%s\n' "$(hostname 2>/dev/null || echo unknown)"
    printf 'db=%s\n' "$ACCOUNTING_DB"
  } | tee "${dest}/meta.txt"

  printf '\n----- vcl version -----\n'
  vcl_cmd version 2>&1 | tee "${dest}/version.out" || true

  printf '\n----- vcl accounting status -----\n'
  vcl_cmd accounting status 2>&1 | tee "${dest}/accounting-status.out" || true

  printf '\n----- vcl verify -----\n'
  vcl_cmd verify 2>&1 | tee "${dest}/verify.out"
  local verify_rc=${PIPESTATUS[0]}
  printf 'verify_exit=%s\n' "$verify_rc" | tee -a "${dest}/meta.txt"

  printf '\n----- sqlite sanity -----\n'
  sqlite_sanity | tee "${dest}/sqlite.tsv"
  local sql_rc=${PIPESTATUS[0]}
  printf 'sqlite_exit=%s\n' "$sql_rc" | tee -a "${dest}/meta.txt"

  printf '\n----- vcl stats today --json -----\n'
  vcl_cmd stats today --json 2>&1 | tee "${dest}/stats-today.json" || true

  local from to
  from=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -v-1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || printf '%s\n' "$ts")
  to=$ts
  printf '\n----- vcl audit user owner --from %s --to %s -----\n' "$from" "$to"
  vcl_cmd audit user owner --from "$from" --to "$to" 2>&1 \
    | tee "${dest}/audit-owner.out" || true

  printf '\n----- checkpoints -----\n'
  python3 - "${dest}/sqlite.tsv" <<'PY' || true
import sys
vals = {}
path = sys.argv[1]
try:
    for line in open(path, encoding="utf-8"):
        if "\t" not in line:
            continue
        k, v = line.rstrip("\n").split("\t", 1)
        vals[k] = v
except FileNotFoundError:
    print("FAIL cannot read sqlite snapshot")
    raise SystemExit(0)

def n(key):
    try:
        return int(vals.get(key, "0"))
    except ValueError:
        return None

ok = True
def check(name, cond, detail):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"{status}  {name}  {detail}")

check("schema 3", vals.get("schema_version") == "3",
      f"schema_version={vals.get('schema_version')}")
check("no negative connections", n("neg_connections") == 0,
      f"neg_connections={vals.get('neg_connections')}")
check("no negative baseline", n("neg_baseline") == 0,
      f"neg_baseline={vals.get('neg_baseline')}")
su, sd = n("sum_upload"), n("sum_download")
check("non-negative sums", su is not None and sd is not None and su >= 0 and sd >= 0,
      f"sum_upload={su} sum_download={sd}")
mid, seq = n("max_event_id"), n("sqlite_sequence")
check("event_id not reused", mid is not None and seq is not None and seq >= mid,
      f"max_event_id={mid} sqlite_sequence={seq}")
print("INFO  exploding totals / wipe detection needs the previous snapshot SUM")
print("INFO  compare this sqlite.tsv against the prior snapshot in the evidence dir")
PY

  printf '\nsnapshot written: %s\n' "$dest"
}

run_check() {
  printf '======== soak check %s ========\n' "$(stamp)"
  printf '\n----- vcl accounting status -----\n'
  vcl_cmd accounting status || true
  printf '\n----- sqlite sanity -----\n'
  sqlite_sanity
  printf '\n----- vcl verify -----\n'
  vcl_cmd verify || true
}

run_watch() {
  printf 'watch interval=%ss evidence=%s\n' "$WATCH_INTERVAL" "$EVIDENCE_DIR"
  printf 'Ctrl-C to stop. This loop is read-only.\n'
  local n=0
  while true; do
    n=$((n + 1))
    local label
    label=$(printf 'watch-%s-%04d' "$(date -u +%Y%m%dT%H%M%SZ)" "$n")
    run_snapshot "$label" || true
    printf 'sleeping %ss...\n' "$WATCH_INTERVAL"
    sleep "$WATCH_INTERVAL"
  done
}

print_inject_accountd() {
  cat <<'EOF'
======== inject-accountd (T+1h) — PRINT ONLY, not executed ========

Operator:
  1. Take a snapshot:  VCL_SOAK_LIVE=1 bash scripts/soak-0.2.7.sh --live snapshot
  2. Restart accountd: systemctl restart vincula-accountd
  3. Wait until active: systemctl is-active vincula-accountd
  4. Snapshot again and compare SUM(upload_bytes)+SUM(download_bytes).

Must NOT:
  - drop accounted totals to a wipe of previously stored bytes
  - introduce negatives
  - replay Clash cumulative counters onto existing generations

Then continue hourly checks.
EOF
}

print_inject_singbox() {
  cat <<'EOF'
======== inject-singbox (T+2h) — PRINT ONLY, not executed ========

Operator:
  1. Snapshot.
  2. Restart proxy: systemctl restart sing-box
  3. Confirm: systemctl is-active sing-box vincula-accountd
  4. Snapshot. Expect new generation on surviving connection_ids.
     Accounted bytes on closed generations stay put. No huge jump.

AC-2.7-03 / AC-2.7-04: current < previous → new generation, no negative delta.
EOF
}

print_inject_clash() {
  cat <<'EOF'
======== inject-clash (T+4h) — PRINT ONLY, not executed ========

Operator (pick ONE, then undo it):
  A. Temporarily disable Clash/experimental API in sing-box config and reload, OR
  B. Block the local Clash port, e.g. nft/iptables on 127.0.0.1:9090, OR
  C. systemctl stop sing-box briefly if that is the only way to drop /connections.

During outage:
  - vcl accounting status: last_success_at grows stale
  - collector must not invent traffic

Restore Clash, then:
  - last_success_at becomes fresh
  - accountd stays active
  - snapshot: no replayed history

This script will not open ports, edit config, or call systemctl.
EOF
}

print_inject_dns() {
  cat <<'EOF'
======== inject-dns / network failure — PRINT ONLY, not executed ========

Operator:
  1. Snapshot.
  2. Introduce a temporary resolver or egress failure (move DNS, drop
     outbound, unplug WAN). Do not run those commands from this script.
  3. Confirm proxy/accounting stay up or recover without wiping SQLite.
  4. Restore network. Snapshot. Collector recovers; audit still queryable.

Must NOT edit /etc/resolv.conf, nftables, or interfaces from this script.
EOF
}

print_inject_reboot() {
  cat <<'EOF'
======== inject-reboot (T+6h) — PRINT ONLY, not executed ========

Operator:
  1. Snapshot and copy evidence off-box if the disk is small.
  2. reboot   (AC-2.7-08)
  3. After boot: systemctl is-active sing-box vincula-accountd
  4. vcl verify
  5. Snapshot. Accounted bytes preserved; unknown live connections baseline-only.

This script will not reboot the machine.
EOF
}

# ---- argv ----
while [[ $# -gt 0 ]]; do
  case "$1" in
    --live)
      LIVE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    protocol|criteria|snapshot|check|watch|inject-accountd|inject-singbox|inject-clash|inject-dns|inject-reboot|help)
      COMMAND=$1
      shift
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${VCL_SOAK_LIVE:-}" == "1" ]]; then
  LIVE=1
fi

if [[ -z "$COMMAND" || "$COMMAND" == "help" ]]; then
  COMMAND=protocol
fi

case "$COMMAND" in
  protocol)
    protocol
    printf '\n'
    usage
    if [[ "$LIVE" == "1" ]]; then
      printf '\n(live flag set; refusing to snapshot unless you pass snapshot|check|watch)\n'
    else
      printf '\nDefault mode printed the protocol only. No live checks ran.\n'
    fi
    ;;
  criteria)
    criteria
    ;;
  snapshot)
    require_live
    run_snapshot "snap-$(date -u +%Y%m%dT%H%M%SZ)"
    ;;
  check)
    require_live
    run_check
    ;;
  watch)
    require_live
    run_watch
    ;;
  inject-accountd)
    print_inject_accountd
    ;;
  inject-singbox)
    print_inject_singbox
    ;;
  inject-clash)
    print_inject_clash
    ;;
  inject-dns)
    print_inject_dns
    ;;
  inject-reboot)
    print_inject_reboot
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
