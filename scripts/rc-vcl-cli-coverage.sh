#!/bin/bash
# Exercise every previously untested / partial vcl command on a live node.
set +e
EVID=/root/vcl-rc-evidence/vcl-cli
mkdir -p "$EVID"
LOG="$EVID/run.log"
exec > >(tee "$LOG") 2>&1
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1 — $2"; }

require_cmd() {
  local name=$1
  shift
  "$@" >"$EVID/${name}.out" 2>"$EVID/${name}.err"
  local ec=$?
  if [[ $ec -eq 0 ]]; then
    pass "$name"
  else
    fail "$name" "exit=$ec stderr=$(tr '\n' ' ' <"$EVID/${name}.err" | head -c 200)"
  fi
  return $ec
}

echo "======== ENV ========"
hostname; date -u
vcl version | tee "$EVID/version.out"
systemctl is-active sing-box vincula-accountd

echo "======== HELP / META ========"
require_cmd help vcl help
require_cmd version vcl version

echo "======== READ-ONLY OPS ========"
require_cmd info vcl info
require_cmd status vcl status
require_cmd check vcl check
require_cmd diagnose vcl diagnose
require_cmd link vcl link

echo "======== LOGS ========"
require_cmd logs-default vcl logs
require_cmd logs-200 vcl logs 200
# -f would hang; take a short follow with timeout
timeout 3 vcl logs -f >"$EVID/logs-f.out" 2>"$EVID/logs-f.err"
ec=$?
# timeout returns 124 when it kills; that is success for follow mode
if [[ $ec -eq 124 || $ec -eq 0 ]]; then
  pass "logs-f-timeout"
else
  fail "logs-f-timeout" "exit=$ec"
fi

echo "======== RESTART ========"
require_cmd restart vcl restart
sleep 2
systemctl is-active --quiet sing-box && systemctl is-active --quiet vincula-accountd \
  && pass "restart-services-active" || fail "restart-services-active" "down"

echo "======== USER SHOW / LINK / REMOVE ========"
# ensure bob exists for show/link/remove
vcl user remove bob 2>/dev/null || true
vcl user add bob --display-name Bob --department qa
[[ $? -eq 0 ]] && pass "user-add-bob" || fail "user-add-bob" "add"
require_cmd user-show-bob vcl user show bob
require_cmd user-link-bob vcl user link bob
# alice may exist from prior tests
if vcl user list 2>/dev/null | grep -q '^alice'; then
  require_cmd user-show-alice vcl user show alice
  require_cmd user-link-alice vcl user link alice
fi
vcl user remove bob
[[ $? -eq 0 ]] && pass "user-remove-bob" || fail "user-remove-bob" "remove"
vcl user list | tee "$EVID/users-after-remove.txt"
if vcl user list 2>/dev/null | grep -q '^bob'; then
  fail "user-remove-bob-gone" "still listed"
else
  pass "user-remove-bob-gone"
fi
# owner cannot be removed
vcl user remove owner >"$EVID/user-remove-owner.out" 2>"$EVID/user-remove-owner.err"
[[ $? -ne 0 ]] && pass "user-remove-owner-refused" || fail "user-remove-owner-refused" "allowed"

echo "======== STATS VARIANTS ========"
require_cmd stats-today vcl stats today
require_cmd stats-yesterday vcl stats yesterday
require_cmd stats-days-7 vcl stats --days 7
require_cmd stats-user-owner-today vcl stats user owner --today
require_cmd stats-user-owner-top vcl stats user owner --days 7 --top 5
require_cmd stats-dept-eng vcl stats department eng --days 7
require_cmd stats-dept-qa vcl stats department qa --days 7
require_cmd stats-help vcl stats --help

echo "======== VERIFY AFTER MUTATIONS ========"
require_cmd verify vcl verify
require_cmd accounting-status vcl accounting status
require_cmd connections vcl connections

echo "======== UNINSTALL (DESTRUCTIVE) + REINSTALL ========"
# Cancel path also prints the accounting warning before prompt
printf 'N\n' | vcl uninstall >"$EVID/uninstall-cancel.out" 2>"$EVID/uninstall-cancel.err"
grep -qi 'cancelled\|canceled' "$EVID/uninstall-cancel.out" && pass "uninstall-cancel-N" || fail "uninstall-cancel-N" "no cancel"
grep -qi 'historical accounting' "$EVID/uninstall-cancel.out" && pass "uninstall-accounting-warning" || fail "uninstall-accounting-warning" "missing text"
[[ -f /etc/vincula/VERSION ]] && pass "uninstall-cancel-kept-install" || fail "uninstall-cancel-kept-install" "gone"

# Explicit --yes path
vcl uninstall --yes >"$EVID/uninstall-yes.out" 2>"$EVID/uninstall-yes.err"
[[ $? -eq 0 ]] && pass "uninstall-yes" || fail "uninstall-yes" "exit=$? $(tr '\n' ' ' <"$EVID/uninstall-yes.err" | head -c 180)"

[[ ! -e /etc/vincula/VERSION ]] && pass "uninstall-version-gone" || fail "uninstall-version-gone" "still present"
systemctl is-active --quiet sing-box 2>/dev/null && fail "uninstall-singbox-stopped" "still active" || pass "uninstall-singbox-stopped"
systemctl is-active --quiet vincula-accountd 2>/dev/null && fail "uninstall-accountd-stopped" "still active" || pass "uninstall-accountd-stopped"

# --yes on already-clean should refuse
vcl uninstall --yes >"$EVID/uninstall-yes-clean.out" 2>"$EVID/uninstall-yes-clean.err"
[[ $? -ne 0 ]] && pass "uninstall-yes-on-clean-refuses" || fail "uninstall-yes-on-clean-refuses" "unexpected success"

# Reinstall from release tree
[[ -d /root/release ]] || { fail "reinstall-release-dir" "missing /root/release"; echo "======== SUMMARY ========"; grep -E '^(PASS|FAIL) ' "$LOG"; exit 1; }
cd /root/release
[[ -f /root/vincula ]] && cp -a /root/vincula /root/release/bin/vincula
[[ -f /root/release.lock ]] && cp -a /root/release.lock /root/release/release.lock
bash /root/release/vincula.sh >"$EVID/reinstall.out" 2>"$EVID/reinstall.err"
[[ $? -eq 0 ]] && pass "reinstall" || fail "reinstall" "$(tail -8 "$EVID/reinstall.err" | tr '\n' ' ')"
systemctl is-active --quiet sing-box && systemctl is-active --quiet vincula-accountd \
  && pass "reinstall-services" || fail "reinstall-services" "down"
vcl verify >"$EVID/reinstall-verify.out" 2>"$EVID/reinstall-verify.err"
[[ $? -eq 0 ]] && pass "reinstall-verify" || fail "reinstall-verify" "verify failed"
vcl version | tee "$EVID/reinstall-version.out"
vcl info >/dev/null && pass "post-reinstall-info" || fail "post-reinstall-info" "info"
vcl status >/dev/null && pass "post-reinstall-status" || fail "post-reinstall-status" "status"
vcl check >/dev/null && pass "post-reinstall-check" || fail "post-reinstall-check" "check"

echo "======== SUMMARY ========"
grep -E '^(PASS|FAIL) ' "$LOG" | tee "$EVID/summary.txt"
echo "FAIL_COUNT=$(grep -c '^FAIL ' "$LOG" || true)"
echo "PASS_COUNT=$(grep -c '^PASS ' "$LOG" || true)"
