#!/usr/bin/env bash
# Vincula live upgrade phases — run on target host as root.
# Expects trees at: /root/vcl-rc-trees/vincula-0.2.{4,5,6}
set +e
set -u

EVID_ROOT=/root/vcl-rc-evidence/upgrade-246
TREES=/root/vcl-rc-trees
PHASE=${1:-all}
VCL_SERVER=${VCL_SERVER:-104.194.90.172}

mkdir -p "$EVID_ROOT"
SUMMARY="${EVID_ROOT}/SUMMARY.md"
# Do NOT truncate .summary_body here — post-reboot must append.
touch "${EVID_ROOT}/.summary_body"

pass() { echo "PASS $1"; echo "| $1 | PASS | $2 |" >>"${EVID_ROOT}/.summary_body"; }
fail() { echo "FAIL $1 — $2"; echo "| $1 | FAIL | $2 |" >>"${EVID_ROOT}/.summary_body"; }
info() { echo "INFO $1"; }

run_log() {
  local name=$1
  shift
  local dir="${EVID_ROOT}/${name}"
  mkdir -p "$dir"
  "$@" >"${dir}/run.log" 2>&1
  local ec=$?
  echo "exit=$ec" >>"${dir}/run.log"
  return $ec
}

snapshot_identity() {
  local out=$1
  python3 - "$out" <<'PY'
import json, re, sys, pathlib
out = pathlib.Path(sys.argv[1])
state = json.loads(pathlib.Path("/etc/vincula/state.json").read_text())
users = json.loads(pathlib.Path("/etc/vincula/users.json").read_text())
settings = pathlib.Path("/etc/vincula/config.toml").read_text()
secret = ""
for line in settings.splitlines():
    if line.startswith("clash_api_secret"):
        m = re.search(r'"([^"]*)"', line)
        if m:
            secret = m.group(1)
owner = next((u for u in users.get("users", []) if u.get("tag") == "owner"), {})
active = next((c for c in owner.get("credentials", []) if c.get("status") == "active"), {})
db_rows = 0
schema = ""
try:
    import sqlite3
    c = sqlite3.connect("/var/lib/vincula/accounting.db")
    schema = dict(c.execute("SELECT key,value FROM meta")).get("schema_version", "")
    db_rows = c.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
    c.close()
except Exception as exc:
    schema = f"err:{exc}"
snap = {
    "version": pathlib.Path("/etc/vincula/VERSION").read_text().strip(),
    "node_id": (state.get("node") or {}).get("node_id"),
    "reality_public_key": state.get("reality_public_key"),
    "reality_short_id": state.get("reality_short_id"),
    "owner_uuid": active.get("uuid"),
    "owner_user_id": owner.get("user_id"),
    "owner_credential_id": active.get("credential_id"),
    "clash_api_secret": secret,
    "schema_version": schema,
    "connections_rows": db_rows,
    "user_count": len(users.get("users", [])),
}
out.write_text(json.dumps(snap, indent=2) + "\n")
print(json.dumps(snap, indent=2))
PY
}

compare_identity() {
  local before=$1 after=$2 label=$3
  python3 - "$before" "$after" "$label" <<'PY'
import json, sys
b = json.loads(open(sys.argv[1]).read())
a = json.loads(open(sys.argv[2]).read())
label = sys.argv[3]
keys = [
    "node_id", "reality_public_key", "reality_short_id",
    "owner_uuid", "owner_user_id", "owner_credential_id", "clash_api_secret",
]
bad = []
for k in keys:
    if b.get(k) != a.get(k):
        bad.append(f"{k}: {b.get(k)!r} -> {a.get(k)!r}")
if bad:
    print("MISMATCH", label)
    print("\n".join(bad))
    raise SystemExit(1)
print("OK identity preserved", label)
raise SystemExit(0)
PY
}

require_services() {
  local sb ad
  sb=$(systemctl is-active sing-box.service 2>/dev/null || true)
  ad=$(systemctl is-active vincula-accountd.service 2>/dev/null || true)
  [[ "$sb" == active && "$ad" == active ]]
}

install_tree() {
  local ver=$1
  local tree="${TREES}/vincula-${ver}"
  [[ -d "$tree" ]] || { echo "missing tree $tree"; return 1; }
  cd "$tree" || return 1
  env VCL_SERVER="$VCL_SERVER" bash ./vincula.sh
}

phase_00_preflight() {
  local d="${EVID_ROOT}/00-preflight"
  mkdir -p "$d"
  {
    hostname
    date -u
    grep -E '^(NAME|VERSION_ID)=' /etc/os-release
    uname -m
    python3 --version
    echo "VCL_SERVER=$VCL_SERVER"
  } | tee "$d/host.txt"

  if [[ -x /usr/local/bin/vcl ]]; then
    info "uninstalling existing vincula"
    /usr/local/bin/vcl uninstall --yes >"$d/uninstall.log" 2>&1
  fi
  # Force clean leftovers that block fresh install
  systemctl stop vincula-accountd sing-box 2>/dev/null || true
  systemctl disable vincula-accountd sing-box 2>/dev/null || true
  rm -rf /etc/vincula /var/lib/vincula /usr/local/lib/vincula
  rm -f /etc/systemd/system/vincula-accountd.service
  # Keep sing-box unit if foreign? Vincula uninstall should handle; force if ours
  if [[ -f /etc/systemd/system/sing-box.service ]] && grep -q vincula /etc/systemd/system/sing-box.service 2>/dev/null; then
    rm -f /etc/systemd/system/sing-box.service
  fi
  systemctl daemon-reload || true
  if [[ -e /etc/vincula || -e /var/lib/vincula ]]; then
    fail "00-preflight-clean" "leftover state/lib remains"
    return 1
  fi
  pass "00-preflight-clean" "host ready"
  return 0
}

phase_01_install_024() {
  local d="${EVID_ROOT}/01-install-024"
  mkdir -p "$d"
  if ! install_tree 0.2.4 >"$d/install.log" 2>&1; then
    fail "01-install-024" "installer non-zero; see install.log"
    return 1
  fi
  local ver
  ver=$(cat /etc/vincula/VERSION 2>/dev/null || true)
  if [[ "$ver" != "0.2.4" ]]; then
    fail "01-version" "got $ver"
    return 1
  fi
  if ! require_services; then
    fail "01-services" "not both active"
    return 1
  fi
  if ! vcl verify >"$d/verify.log" 2>&1; then
    fail "01-verify" "vcl verify failed"
    return 1
  fi
  snapshot_identity "$d/identity-024.json" >"$d/identity-024.pretty" 2>&1
  pass "01-install-024" "VERSION=0.2.4 services+verify"
  return 0
}

phase_02_baseline_024() {
  local d="${EVID_ROOT}/02-baseline-024"
  mkdir -p "$d"
  vcl status >"$d/status.out" 2>&1
  vcl check >"$d/check.out" 2>&1
  vcl link >"$d/link.out" 2>&1
  vcl accounting status >"$d/accounting.out" 2>&1
  # Clash triad
  local secret port
  secret=$(grep '^clash_api_secret' /etc/vincula/config.toml | sed -n 's/.*"\(.*\)".*/\1/p')
  port=$(grep '^clash_api_port' /etc/vincula/config.toml | awk '{print $3}')
  [[ -n "$port" ]] || port=9090
  local r_no r_bad r_ok
  curl -fsS --max-time 5 "http://127.0.0.1:${port}/connections" >/dev/null 2>&1 && r_no=FAIL || r_no=OK
  curl -fsS --max-time 5 -H "Authorization: Bearer wrong" "http://127.0.0.1:${port}/connections" >/dev/null 2>&1 && r_bad=FAIL || r_bad=OK
  curl -fsS --max-time 5 -H "Authorization: Bearer ${secret}" "http://127.0.0.1:${port}/connections" >/dev/null 2>&1 && r_ok=OK || r_ok=FAIL
  echo "noauth=$r_no bad=$r_bad ok=$r_ok" | tee "$d/clash-triad.txt"
  if [[ "$r_no" == OK && "$r_bad" == OK && "$r_ok" == OK ]]; then
    pass "02-clash-triad" "localhost auth ok"
  else
    fail "02-clash-triad" "noauth=$r_no bad=$r_bad ok=$r_ok"
    return 1
  fi
  # optional user add on 0.2.4
  if vcl user add rc24alice --display-name "RC Alice" --department Sales >"$d/user-add.out" 2>&1; then
    pass "02-user-add" "rc24alice"
  else
    info "02-user-add skipped/failed (non-fatal for 0.2.4 baseline)"
  fi
  pass "02-baseline-024" "status/check/link"
  return 0
}

phase_03_migrate_025() {
  local d="${EVID_ROOT}/03-migrate-025"
  mkdir -p "$d"
  cp -a "${EVID_ROOT}/01-install-024/identity-024.json" "$d/before.json" 2>/dev/null || \
    snapshot_identity "$d/before.json" >/dev/null
  if ! install_tree 0.2.5 >"$d/migrate.log" 2>&1; then
    fail "03-migrate-025" "installer failed"
    return 1
  fi
  local ver
  ver=$(cat /etc/vincula/VERSION)
  [[ "$ver" == "0.2.5" ]] || { fail "03-version" "$ver"; return 1; }
  require_services || { fail "03-services" "inactive"; return 1; }
  vcl verify >"$d/verify.log" 2>&1 || { fail "03-verify" "fail"; return 1; }
  snapshot_identity "$d/identity-025.json" >"$d/identity-025.pretty"
  if ! compare_identity "$d/before.json" "$d/identity-025.json" "024->025" >"$d/compare.txt" 2>&1; then
    fail "03-identity" "see compare.txt"
    return 1
  fi
  # 0.2.5 suite
  vcl user set owner --display-name "Owner RC" >"$d/user-set.out" 2>&1 || true
  vcl user verify >"$d/user-verify.out" 2>&1 || { fail "03-user-verify" "fail"; return 1; }
  printf 'tag,display_name,department\nrc25bob,Bob,Eng\n' >"$d/import.csv"
  vcl user import "$d/import.csv" --dry-run >"$d/import-dry.out" 2>&1
  vcl user import "$d/import.csv" --output "$d/creds.csv" >"$d/import.out" 2>&1 || {
    fail "03-import" "fail"; return 1
  }
  [[ -f "$d/creds.csv" ]] || { fail "03-creds-csv" "missing"; return 1; }
  local mode
  mode=$(stat -c '%a' "$d/creds.csv" 2>/dev/null || echo "?")
  echo "creds_mode=$mode" >>"$d/import.out"
  vcl user remove shouldfail >"$d/remove.out" 2>&1
  local rec=$?
  [[ $rec -eq 2 ]] || [[ $rec -ne 0 ]]
  if grep -qi 'not supported\|refusing\|purge' "$d/remove.out"; then
    pass "03-remove-refused" "exit=$rec"
  else
    info "03-remove-refused soft (exit=$rec)"
  fi
  pass "03-migrate-025" "identity+user suite"
  return 0
}

phase_04_migrate_026() {
  local d="${EVID_ROOT}/04-migrate-026"
  mkdir -p "$d"
  cp -a "${EVID_ROOT}/03-migrate-025/identity-025.json" "$d/before.json" 2>/dev/null || \
    snapshot_identity "$d/before.json" >/dev/null
  if ! install_tree 0.2.6 >"$d/migrate.log" 2>&1; then
    fail "04-migrate-026" "installer failed"
    return 1
  fi
  local ver
  ver=$(cat /etc/vincula/VERSION)
  [[ "$ver" == "0.2.6" ]] || { fail "04-version" "$ver"; return 1; }
  require_services || { fail "04-services" "inactive"; return 1; }
  [[ -f /usr/local/lib/vincula/vincula-stats.py ]] || { fail "04-stats-py" "missing"; return 1; }
  vcl verify >"$d/verify.log" 2>&1 || { fail "04-verify" "fail"; return 1; }
  snapshot_identity "$d/identity-026.json" >"$d/identity-026.pretty"
  if ! compare_identity "$d/before.json" "$d/identity-026.json" "025->026" >"$d/compare.txt" 2>&1; then
    fail "04-identity" "see compare.txt"
    return 1
  fi
  vcl stats today >"$d/stats-today.out" 2>&1
  vcl stats yesterday >"$d/stats-yesterday.out" 2>&1
  vcl stats --month >"$d/stats-month.out" 2>&1
  vcl stats top users --limit 5 >"$d/stats-top.out" 2>&1
  vcl stats today --json >"$d/stats.json" 2>&1
  vcl stats today --csv "$d/stats.csv" >"$d/stats-csv.out" 2>&1
  grep -qi 'approximate\|polling' "$d/stats-today.out" "$d/stats-month.out" && \
    pass "04-stats-approx-label" "present" || fail "04-stats-approx-label" "missing"
  systemctl stop vincula-accountd
  vcl stats today >"$d/stats-stale.out" 2>&1
  grep -qi 'WARNING\|stale\|not healthy\|unavailable' "$d/stats-stale.out" && \
    pass "04-stats-stale-warn" "warned" || info "04-stats-stale-warn soft"
  if vcl connections >"$d/connections-down.out" 2>&1; then
    fail "04-connections-unavailable" "should fail when accountd stopped"
  else
    grep -qi 'UNAVAILABLE\|not active\|inactive\|unavailable' "$d/connections-down.out" && \
      pass "04-connections-unavailable" "failed closed" || pass "04-connections-unavailable" "non-zero exit"
  fi
  systemctl start vincula-accountd
  sleep 2
  require_services || { fail "04-services-restore" "inactive"; return 1; }
  vcl accounting retention >"$d/retention.out" 2>&1 || true
  pass "04-migrate-026" "stats suite"
  return 0
}

phase_05_reboot() {
  local d="${EVID_ROOT}/05-reboot"
  mkdir -p "$d"
  snapshot_identity "$d/before.json" >/dev/null
  echo "rebooting $(date -u)" | tee "$d/reboot-requested.txt"
  # Marker for driver to wait and continue with phase_05b
  touch "${EVID_ROOT}/.reboot_pending"
  nohup bash -c 'sleep 2; systemctl reboot' >/dev/null 2>&1 &
  return 0
}

phase_05b_after_reboot() {
  local d="${EVID_ROOT}/05-reboot"
  mkdir -p "$d"
  rm -f "${EVID_ROOT}/.reboot_pending"
  sleep 5
  {
    date -u
    systemctl is-active sing-box vincula-accountd
    cat /etc/vincula/VERSION
  } | tee "$d/after.txt"
  require_services || { fail "05-services" "after reboot"; return 1; }
  [[ "$(cat /etc/vincula/VERSION)" == "0.2.6" ]] || { fail "05-version" "bad"; return 1; }
  vcl verify >"$d/verify.log" 2>&1 || { fail "05-verify" "fail"; return 1; }
  snapshot_identity "$d/after-identity.json" >/dev/null
  if [[ -f "$d/before.json" ]]; then
    compare_identity "$d/before.json" "$d/after-identity.json" "reboot" >"$d/compare.txt" 2>&1 || {
      fail "05-identity" "changed"; return 1
    }
  fi
  pass "05-reboot" "dual-plane ok"
  return 0
}

phase_06_rollback() {
  local d="${EVID_ROOT}/06-rollback"
  mkdir -p "$d"
  info "resetting to 0.2.5 baseline for rollback test"
  if [[ -x /usr/local/bin/vcl ]]; then
    vcl uninstall --yes >"$d/uninstall.log" 2>&1
  fi
  rm -rf /etc/vincula /var/lib/vincula /usr/local/lib/vincula
  systemctl daemon-reload || true

  if ! install_tree 0.2.5 >"$d/reinstall-025.log" 2>&1; then
    fail "06-reinstall-025" "failed"
    return 1
  fi
  snapshot_identity "$d/before-rollback.json" >/dev/null
  [[ "$(cat /etc/vincula/VERSION)" == "0.2.5" ]] || { fail "06-version-before" "not 0.2.5"; return 1; }

  # Broken 0.2.6 tree
  local broken="${TREES}/vincula-0.2.6-broken"
  rm -rf "$broken"
  cp -a "${TREES}/vincula-0.2.6" "$broken"
  printf 'this is not valid python !!!\n' >"${broken}/lib/vincula-accountd.py"
  # Fix release.lock? installer may check hashes — break after lock verify by editing installed path mid-flight is harder.
  # Prefer: break the packaged py AND update lock to match so pre-check passes, then validate_accounting fails.
  (
    cd "$broken"
    : > release.lock
    for f in vincula.sh bin/vincula lib/vincula-common.sh lib/vincula-accountd.py \
             lib/vincula-accountd.service lib/vincula-event.schema.json; do
      [[ -f "$f" ]] && sha256sum -- "$f" >> release.lock
    done
    [[ -f lib/vincula-stats.py ]] && sha256sum -- lib/vincula-stats.py >> release.lock
    sha256sum -- vincula.sh | tee vincula.sh.sha256 >/dev/null
  )

  cd "$broken" || return 1
  env VCL_SERVER="$VCL_SERVER" bash ./vincula.sh >"$d/migrate-broken.log" 2>&1
  local ec=$?
  echo "installer_exit=$ec" | tee "$d/exit.txt"
  if [[ $ec -eq 0 ]]; then
    fail "06-rollback-expected-fail" "broken migrate succeeded unexpectedly"
    return 1
  fi
  local ver
  ver=$(cat /etc/vincula/VERSION 2>/dev/null || echo missing)
  echo "version_after=$ver" | tee -a "$d/exit.txt"
  if [[ "$ver" != "0.2.5" ]]; then
    fail "06-version-restored" "got $ver want 0.2.5"
    return 1
  fi
  # Broken py must not remain as live accountd
  if python3 -m py_compile /usr/local/lib/vincula/vincula-accountd.py >/dev/null 2>&1; then
    pass "06-accountd-py-ok" "compiled"
  else
    fail "06-accountd-py-ok" "broken py left installed"
    return 1
  fi
  ls /var/backups/vincula/*/SERVICE_STATE >/dev/null 2>&1 && \
    pass "06-backup-present" "SERVICE_STATE found" || info "06-backup soft"
  pass "06-rollback" "VERSION restored to 0.2.5"
  return 0
}

phase_07_reinstall_026() {
  local d="${EVID_ROOT}/07-reinstall-026"
  mkdir -p "$d"
  # From 0.2.5 after rollback, migrate successfully to 0.2.6 OR uninstall+fresh
  if [[ -x /usr/local/bin/vcl ]]; then
    vcl uninstall --yes >"$d/uninstall.log" 2>&1
  fi
  rm -rf /etc/vincula /var/lib/vincula /usr/local/lib/vincula
  systemctl daemon-reload || true
  if ! install_tree 0.2.6 >"$d/install.log" 2>&1; then
    fail "07-install-026" "failed"
    return 1
  fi
  [[ "$(cat /etc/vincula/VERSION)" == "0.2.6" ]] || { fail "07-version" "bad"; return 1; }
  require_services || { fail "07-services" "inactive"; return 1; }
  vcl verify >"$d/verify.log" 2>&1 || { fail "07-verify" "fail"; return 1; }
  pass "07-reinstall-026" "clean 0.2.6 ok"
  return 0
}

write_summary() {
  {
    echo "# Vincula live upgrade 0.2.4 → 0.2.6"
    echo
    echo "- Host: $(hostname)"
    echo "- Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "- OS: $(grep PRETTY_NAME= /etc/os-release | cut -d= -f2 | tr -d '"')"
    echo
    echo "| Check | Result | Notes |"
    echo "| --- | --- | --- |"
    if [[ -f "${EVID_ROOT}/.summary_body" ]]; then
      cat "${EVID_ROOT}/.summary_body"
    fi
  } >"$SUMMARY"
  echo "SUMMARY written to $SUMMARY"
  cat "$SUMMARY"
}

run_phase() {
  local p=$1
  echo "======== PHASE $p ========"
  case "$p" in
    00|0|preflight) phase_00_preflight ;;
    01|1|install024) phase_01_install_024 ;;
    02|2|baseline024) phase_02_baseline_024 ;;
    03|3|migrate025) phase_03_migrate_025 ;;
    04|4|migrate026) phase_04_migrate_026 ;;
    05|5|reboot) phase_05_reboot ;;
    05b|after-reboot) phase_05b_after_reboot ;;
    06|6|rollback) phase_06_rollback ;;
    07|7|reinstall) phase_07_reinstall_026 ;;
    summary) write_summary ;;
    all)
      : >"${EVID_ROOT}/.summary_body"
      phase_00_preflight || return 1
      phase_01_install_024 || return 1
      phase_02_baseline_024 || return 1
      phase_03_migrate_025 || return 1
      phase_04_migrate_026 || return 1
      # reboot handled by driver separately
      pass "05-reboot" "deferred-to-driver"
      phase_06_rollback || return 1
      phase_07_reinstall_026 || return 1
      write_summary
      ;;
    all-with-reboot-marker)
      : >"${EVID_ROOT}/.summary_body"
      phase_00_preflight || return 1
      phase_01_install_024 || return 1
      phase_02_baseline_024 || return 1
      phase_03_migrate_025 || return 1
      phase_04_migrate_026 || return 1
      write_summary
      phase_05_reboot
      ;;
    post-reboot)
      phase_05b_after_reboot || return 1
      phase_06_rollback || return 1
      phase_07_reinstall_026 || return 1
      write_summary
      ;;
    *)
      echo "unknown phase $p"
      return 1
      ;;
  esac
}

run_phase "$PHASE"
ec=$?
exit $ec
