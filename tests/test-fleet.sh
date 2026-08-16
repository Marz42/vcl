#!/usr/bin/env bash
# Sourced by tests/test.sh. Requires PROJECT_DIR, TEST_TMP, TEST_NODE_ID,
# TEST_INSTANCE_ID, and the assert_* helpers. Direct execution runs only
# these fleet tests.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -Eeuo pipefail
  IFS=$'\n\t'
  TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  PROJECT_DIR=$(cd -- "${TEST_DIR}/.." && pwd)
  PASS_COUNT=0
  FAIL_COUNT=0
  pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    printf 'ok %d - %s\n' "$PASS_COUNT" "$1"
  }
  fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf 'not ok - %s\n' "$1" >&2
  }
  assert_equal() {
    local description=$1 expected=$2 actual=$3
    if [[ "$actual" == "$expected" ]]; then
      pass "$description"
    else
      fail "${description} (expected '${expected}', got '${actual}')"
    fi
  }
  assert_success() {
    local description=$1
    shift
    if "$@"; then
      pass "$description"
    else
      fail "$description"
    fi
  }
  assert_failure() {
    local description=$1
    shift
    if "$@"; then
      fail "${description} (unexpected success)"
    else
      pass "$description"
    fi
  }
  TEST_TMP=$(mktemp -d /tmp/vincula-fleet-tests.XXXXXXXX)
  readonly TEST_NODE_ID="6fc96a10-1111-4111-8111-111111111111"
  readonly TEST_INSTANCE_ID="7aa07b21-2222-4222-8222-222222222222"
  finish_fleet() {
    trap - EXIT
    if [[ -n "${TEST_TMP:-}" && "$TEST_TMP" == /tmp/vincula-fleet-tests.* && -d "$TEST_TMP" ]]; then
      rm -rf --one-file-system -- "$TEST_TMP"
    fi
    if (( FAIL_COUNT > 0 )); then
      printf '\n%d test(s) failed; %d passed.\n' "$FAIL_COUNT" "$PASS_COUNT" >&2
      exit 1
    fi
    printf '\nAll %d tests passed.\n' "$PASS_COUNT"
  }
  trap finish_fleet EXIT
fi

readonly TEST_TOKYO_NODE_ID="8bb18c32-3333-4333-8333-333333333333"
readonly TEST_SG_NODE_ID="9cc29d43-4444-4444-8444-444444444444"

FLEET_SAVED_HOME="${HOME:-}"
export HOME="${TEST_TMP}/user-home"
mkdir -p "${HOME}"

export VCL_FLEET_HOME="${TEST_TMP}/fleet-home"
export VCL_FLEET_SSH="${PROJECT_DIR}/tests/fixtures/fake-ssh"
export VCL_FLEET_SSH_KEYSCAN="${PROJECT_DIR}/tests/fixtures/fake-ssh-keyscan"
readonly FAKE_SSH="${VCL_FLEET_SSH}"
readonly FAKE_KEYSCAN="${VCL_FLEET_SSH_KEYSCAN}"
readonly LAX_REMOTE_NODE_ID="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
readonly LAX_HOSTKEY_PUB="${PROJECT_DIR}/tests/fixtures/nodes/lax/hostkey.pub"
readonly TOKYO_HOSTKEY_PUB="${PROJECT_DIR}/tests/fixtures/nodes/tokyo/hostkey.pub"
readonly BADKEY_HOSTKEY_PUB="${PROJECT_DIR}/tests/fixtures/nodes/badkey/hostkey.pub"

fingerprint_of() {
  python3 - "$1" <<'PY'
import base64, hashlib, sys
line = open(sys.argv[1], encoding="utf-8").read().strip()
parts = line.split()
blob = parts[2]
pad = "=" * ((4 - len(blob) % 4) % 4)
digest = hashlib.sha256(base64.b64decode(blob + pad)).digest()
print("SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("="))
PY
}

LAX_HOST_KEY=$(fingerprint_of "$LAX_HOSTKEY_PUB")
TOKYO_HOST_KEY=$(fingerprint_of "$TOKYO_HOSTKEY_PUB")
BADKEY_HOST_KEY=$(fingerprint_of "$BADKEY_HOSTKEY_PUB")

if command -v ssh-keygen >/dev/null 2>&1; then
  keygen_lax=$(ssh-keygen -l -f "$LAX_HOSTKEY_PUB" | awk '{print $2}')
  assert_equal "ssh-keygen cross-check matches hashlib lax fingerprint" \
    "$LAX_HOST_KEY" "$keygen_lax"
fi

fleet() {
  python3 "${PROJECT_DIR}/lib/vincula-fleet.py" "$@"
}

assert_success "clock skew warn is 30s" \
  grep -q 'CLOCK_SKEW_WARN_SECONDS = 30' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "clock skew fail is 300s" \
  grep -q 'CLOCK_SKEW_FAIL_SECONDS = 300' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "clock skew fail check is audit-clock-health" \
  grep -q 'CLOCK_SKEW_FAIL_CHECK = "audit-clock-health"' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet schema version is 1" \
  grep -q 'FLEET_SCHEMA_VERSION = 1' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "vcl-fleet Unix entry exists" test -f "${PROJECT_DIR}/bin/vcl-fleet"
assert_success "vcl-fleet Windows entry exists" test -f "${PROJECT_DIR}/bin/vcl-fleet.cmd"

assert_equal "vcl-fleet version" "vcl-fleet 0.2.9-dev" \
  "$(python3 "${PROJECT_DIR}/bin/vcl-fleet" version)"
assert_equal "vcl-fleet.py version" "vcl-fleet 0.2.9-dev" \
  "$(fleet version)"

assert_success "init creates fleet.json" fleet init
assert_success "init wrote fleet.json under VCL_FLEET_HOME" \
  test -f "${VCL_FLEET_HOME}/fleet.json"
case "${VCL_FLEET_HOME}" in
  "${TEST_TMP}"/*)
    pass "VCL_FLEET_HOME is isolated under TEST_TMP"
    ;;
  *)
    fail "VCL_FLEET_HOME is isolated under TEST_TMP"
    ;;
esac

init_schema_rc=0
python3 - "${VCL_FLEET_HOME}/fleet.json" <<'PY' || init_schema_rc=$?
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
assert data.get("schema_version") == 1, data
assert data.get("nodes") == [], data
assert "instance_id" not in data
for node in data.get("nodes") or []:
    assert "instance_id" not in node
PY
if (( init_schema_rc == 0 )); then
  pass "init creates schema-1 empty registry"
else
  fail "init creates schema-1 empty registry"
fi

assert_success "init is idempotent on empty registry" fleet init

assert_success "offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$TEST_NODE_ID" \
    --instance-id "$TEST_INSTANCE_ID"
list_out=$(fleet node list)
assert_success "node list contains lax" grep -q 'lax' <<< "$list_out"
assert_success "node list contains lax node_id" grep -q "$TEST_NODE_ID" <<< "$list_out"

dup_rc=0
dup_err=$(fleet node add tokyo --host 203.0.113.11 --offline --node-id "$TEST_NODE_ID" 2>&1) || dup_rc=$?
if (( dup_rc != 0 )); then
  pass "duplicate node_id rejected"
else
  fail "duplicate node_id rejected"
fi
assert_success "duplicate node_id error names node_id" \
  grep -q 'duplicate node_id' <<< "$dup_err"

bad_id_rc=0
bad_id_err=$(fleet node add badid --host 203.0.113.10 --offline --node-id not-a-uuid 2>&1) || bad_id_rc=$?
if (( bad_id_rc != 0 )); then
  pass "invalid node_id rejected"
else
  fail "invalid node_id rejected"
fi
assert_success "invalid node_id error names node_id" \
  grep -q 'invalid node_id' <<< "$bad_id_err"

bad_name_rc=0
bad_name_err=$(fleet node add Lax --host 203.0.113.10 --offline --node-id "$TEST_TOKYO_NODE_ID" 2>&1) || bad_name_rc=$?
if (( bad_name_rc != 0 )); then
  pass "invalid name rejected"
else
  fail "invalid name rejected"
fi
assert_success "invalid name error names name" \
  grep -q 'invalid name' <<< "$bad_name_err"

empty_host_rc=0
fleet node add emptyhost --host "" --offline --node-id "$TEST_TOKYO_NODE_ID" >/dev/null 2>&1 || empty_host_rc=$?
if (( empty_host_rc != 0 )); then
  pass "empty ssh_host rejected"
else
  fail "empty ssh_host rejected"
fi

assert_success "node set lax host" fleet node set lax --host 203.0.113.28
show_out=$(fleet node show lax)
assert_success "node show host updated" grep -q 'ssh_host=203.0.113.28' <<< "$show_out"
assert_success "node show node_id unchanged" grep -q "node_id=${TEST_NODE_ID}" <<< "$show_out"
assert_failure "node set does not copy instance_id into show" \
  grep -q 'instance_id' <<< "$show_out"

assert_success "node disable lax" fleet node disable lax
disable_out=$(fleet node show lax)
assert_success "node show enabled false after disable" \
  grep -q 'enabled=false' <<< "$disable_out"
assert_success "node enable lax" fleet node enable lax
enable_out=$(fleet node show lax)
assert_success "node show enabled true after enable" \
  grep -q 'enabled=true' <<< "$enable_out"

assert_failure "fleet.json stores no password" \
  grep -E 'password|passwd' "${VCL_FLEET_HOME}/fleet.json"

roundtrip_rc=0
python3 - "${VCL_FLEET_HOME}/fleet.json" "$TEST_NODE_ID" <<'PY' || roundtrip_rc=$?
import json, sys
path, node_id = sys.argv[1], sys.argv[2]
raw = open(path, encoding="utf-8").read()
assert "instance_id" not in raw
data = json.load(open(path, encoding="utf-8"))
assert data.get("schema_version") == 1, data
assert "instance_id" not in data
nodes = data.get("nodes") or []
assert len(nodes) == 1, nodes
node = nodes[0]
assert "instance_id" not in node
assert node["node_id"] == node_id
assert node["name"] == "lax"
assert node["ssh_host"] == "203.0.113.28"
assert node["ssh_user"] == "root"
assert node["ssh_port"] == 22
assert node["enabled"] is True
PY
if (( roundtrip_rc == 0 )); then
  pass "fleet.json schema 1 has no instance_id"
else
  fail "fleet.json schema 1 has no instance_id"
fi

assert_success "offline add tokyo" \
  fleet node add tokyo --host 203.0.113.11 --offline --node-id "$TEST_TOKYO_NODE_ID"
dup_name_rc=0
dup_name_err=$(fleet node add tokyo --host 203.0.113.99 --offline --node-id "$TEST_SG_NODE_ID" 2>&1) || dup_name_rc=$?
if (( dup_name_rc != 0 )); then
  pass "duplicate name rejected"
else
  fail "duplicate name rejected"
fi
assert_success "duplicate name error names name" \
  grep -q 'duplicate name' <<< "$dup_name_err"

assert_success "offline add sg" \
  fleet node add sg --host 203.0.113.12 --offline --node-id "$TEST_SG_NODE_ID"
three=$(fleet node list)
assert_success "AC-2.8-01 fixture lax listed" grep -q '^lax ' <<< "$three"
assert_success "AC-2.8-01 fixture tokyo listed" grep -q '^tokyo ' <<< "$three"
assert_success "AC-2.8-01 fixture sg listed" grep -q '^sg ' <<< "$three"

init_busy_rc=0
fleet init >/dev/null 2>&1 || init_busy_rc=$?
if (( init_busy_rc != 0 )); then
  pass "init refuses to overwrite a non-empty registry"
else
  fail "init refuses to overwrite a non-empty registry"
fi

ssh_add_rc=0
ssh_add_err=$(fleet node add nantes --host 203.0.113.40 --node-id "$TEST_SG_NODE_ID" 2>&1) || ssh_add_rc=$?
if (( ssh_add_rc != 0 )); then
  pass "node add without --host-key is non-zero"
else
  fail "node add without --host-key is non-zero (rc=${ssh_add_rc})"
fi
assert_success "non-interactive add requires --host-key even if keyscan exists" \
  grep -q 'non-interactive add requires --host-key SHA256:' <<< "$ssh_add_err"
assert_failure "SSH failure does not register nantes" \
  grep -q 'nantes' "${VCL_FLEET_HOME}/fleet.json"

offline_noid_rc=0
fleet node add nantes --host 203.0.113.40 --offline >/dev/null 2>&1 || offline_noid_rc=$?
if (( offline_noid_rc != 0 )); then
  pass "--offline without --node-id rejected"
else
  fail "--offline without --node-id rejected"
fi

reload_list=$(python3 "${PROJECT_DIR}/lib/vincula-fleet.py" node list)
assert_success "AC-2.8-09 registry survives a new process" \
  grep -q '^sg ' <<< "$reload_list"

assert_success "fake-ssh is executable" test -x "$FAKE_SSH"
assert_success "fake-ssh-keyscan is executable" test -x "$FAKE_KEYSCAN"
keyscan_rc=0
"$FAKE_KEYSCAN" -p 22 203.0.113.10 >/dev/null || keyscan_rc=$?
if (( keyscan_rc == 0 )); then
  pass "fake-ssh-keyscan lax exits 0"
else
  fail "fake-ssh-keyscan lax exits 0 (rc=${keyscan_rc})"
fi
keyscan_lax=$("$FAKE_KEYSCAN" 203.0.113.10)
assert_success "fake-ssh-keyscan prints ed25519 candidate" \
  grep -q 'ssh-ed25519' <<< "$keyscan_lax"
fake_ident_rc=0
"$FAKE_SSH" 203.0.113.10 -- vcl identity --json >/dev/null || fake_ident_rc=$?
if (( fake_ident_rc == 0 )); then
  pass "fake-ssh lax identity exits 0"
else
  fail "fake-ssh lax identity exits 0 (rc=${fake_ident_rc})"
fi
lax_ident=$("$FAKE_SSH" root@203.0.113.10 -- vcl identity --json)
assert_success "fake-ssh lax identity has fixture node_id" \
  grep -q "$LAX_REMOTE_NODE_ID" <<< "$lax_ident"

sg_ssh_rc=0
sg_ssh_err=$("$FAKE_SSH" 203.0.113.12 -- vcl identity --json 2>&1) || sg_ssh_rc=$?
if (( sg_ssh_rc == 255 )); then
  pass "fake-ssh sg exits 255"
else
  fail "fake-ssh sg exits 255 (rc=${sg_ssh_rc})"
fi
assert_success "fake-ssh sg stderr is connection refused" \
  grep -q 'Connection refused' <<< "$sg_ssh_err"

badkey_rc=0
badkey_err=$("$FAKE_SSH" 203.0.113.13 -- vcl identity --json 2>&1) || badkey_rc=$?
if (( badkey_rc == 255 )); then
  pass "fake-ssh badkey exits 255"
else
  fail "fake-ssh badkey exits 255 (rc=${badkey_rc})"
fi
assert_success "fake-ssh badkey stderr is host key verification failed" \
  grep -q 'Host key verification failed' <<< "$badkey_err"

ask_rc=0
ask_err=$("$FAKE_SSH" 203.0.113.17 -- vcl identity --json 2>&1) || ask_rc=$?
if (( ask_rc == 255 )); then
  pass "fake-ssh ask exits 255"
else
  fail "fake-ssh ask exits 255 (rc=${ask_rc})"
fi
assert_success "fake-ssh ask stderr is authenticity prompt" \
  grep -q "authenticity of host" <<< "$ask_err"

forbid_rc=0
forbid_err=$("$FAKE_SSH" -o StrictHostKeyChecking=no 203.0.113.10 2>&1) || forbid_rc=$?
if (( forbid_rc == 2 )); then
  pass "fake-ssh rejects StrictHostKeyChecking=no"
else
  fail "fake-ssh rejects StrictHostKeyChecking=no (rc=${forbid_rc})"
fi
assert_success "fake-ssh forbidden option names FORBIDDEN_HOSTKEY_OPTION" \
  grep -q 'FORBIDDEN_HOSTKEY_OPTION' <<< "$forbid_err"

null_hosts_rc=0
"$FAKE_SSH" -o UserKnownHostsFile=/dev/null 203.0.113.10 >/dev/null 2>&1 || null_hosts_rc=$?
if (( null_hosts_rc == 2 )); then
  pass "fake-ssh rejects UserKnownHostsFile=/dev/null"
else
  fail "fake-ssh rejects UserKnownHostsFile=/dev/null (rc=${null_hosts_rc})"
fi

argv_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$FAKE_SSH" <<'PY' || argv_rc=$?
import importlib.util
import os
import sys

path, fake = sys.argv[1], sys.argv[2]
os.environ["VCL_FLEET_SSH"] = fake
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
argv = mod.ssh_argv(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
)
assert argv[0] == fake, argv[0]
assert "-p" in argv and "22" in argv
assert "BatchMode=yes" in argv
assert "IdentitiesOnly=no" in argv
assert "root@203.0.113.10" in argv
assert "--" in argv
assert argv[argv.index("--") + 1 :] == ["vcl", "identity", "--json"]
assert "StrictHostKeyChecking=no" not in argv
assert "UserKnownHostsFile=/dev/null" not in " ".join(argv)
assert not any(arg.startswith("UserKnownHostsFile=") for arg in argv)
nobatch = mod.ssh_argv(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "status", "--json"],
    batch=False,
)
assert "BatchMode=yes" not in nobatch
proc = mod.ssh_run(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
)
assert proc.returncode == 0, proc.stderr
ident = mod.parse_identity_json(proc.stdout)
assert ident["node_id"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
assert ident["instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
hang = mod.ssh_run(
    "203.0.113.14",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
    timeout=0.4,
)
assert hang.returncode == 255, hang
assert "timed out" in (hang.stderr or "")
bad = mod.ssh_run(
    "203.0.113.15",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
)
assert bad.returncode == 0
raised = False
import io
buf = io.StringIO()
old_err = sys.stderr
sys.stderr = buf
try:
    mod.parse_identity_json(bad.stdout)
except SystemExit:
    raised = True
finally:
    sys.stderr = old_err
assert raised, bad.stdout
PY
if (( argv_rc == 0 )); then
  pass "ssh_argv/ssh_run use injectable ssh without host-key weakening"
else
  fail "ssh_argv/ssh_run use injectable ssh without host-key weakening"
fi

assert_failure "fleet.py never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_failure "fleet.py never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_failure "vcl-fleet never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "${PROJECT_DIR}/bin/vcl-fleet"
assert_failure "vcl-fleet never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "${PROJECT_DIR}/bin/vcl-fleet"
assert_failure "vcl-fleet.cmd never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_failure "vcl-fleet.cmd never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_failure "AC-2.8-02 controller has no bind" \
  grep -E '0\.0\.0\.0|HTTPServer|socket\.bind' \
    "${PROJECT_DIR}/lib/vincula-fleet.py" \
    "${PROJECT_DIR}/bin/vcl-fleet" \
    "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_failure "AC-2.8-02 controller has no listen/http.server" \
  grep -E 'http\.server|socket\.listen|socket\.socket' \
    "${PROJECT_DIR}/lib/vincula-fleet.py" \
    "${PROJECT_DIR}/bin/vcl-fleet" \
    "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_failure "AC-2.8-10 shipped controller has no StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' \
    "${PROJECT_DIR}/lib/vincula-fleet.py" \
    "${PROJECT_DIR}/bin/vcl-fleet" \
    "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_failure "AC-2.8-10 shipped controller has no UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' \
    "${PROJECT_DIR}/lib/vincula-fleet.py" \
    "${PROJECT_DIR}/bin/vcl-fleet" \
    "${PROJECT_DIR}/bin/vcl-fleet.cmd"

hostkey_py_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$FAKE_SSH" "$FAKE_KEYSCAN" \
  "$LAX_HOSTKEY_PUB" "$HOME" <<'PY' || hostkey_py_rc=$?
import argparse
import importlib.util
import io
import os
import sys

path, fake, keyscan, lax_pub, home = sys.argv[1:6]
os.environ["VCL_FLEET_SSH"] = fake
os.environ["VCL_FLEET_SSH_KEYSCAN"] = keyscan
os.environ["HOME"] = home
os.environ["VCL_FLEET_HOME"] = os.path.join(home, "fleet-home-hostkey-py")
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

line = open(lax_pub, encoding="utf-8").read().strip()
fp = mod.fingerprint_sha256(line)
assert fp.startswith("SHA256:"), fp
assert fp == mod.normalize_fingerprint(fp)
cands = mod.candidate_host_keys("203.0.113.10", 22)
assert cands, cands
assert any(mod.fingerprint_sha256(row) == fp for row in cands)
assert mod.candidate_host_keys("203.0.113.99", 22) == []

mod.stdin_is_tty = lambda: False
raised = False
buf = io.StringIO()
old_err = sys.stderr
sys.stderr = buf
try:
    extra, batch = mod.prepare_ssh_host_key("203.0.113.10", 22, None)
except SystemExit:
    raised = True
finally:
    sys.stderr = old_err
assert raised
assert "non-interactive add requires --host-key SHA256:" in buf.getvalue()

mod.pin_host_key("203.0.113.10", 22, fp)
kh = mod.default_known_hosts_path()
text = kh.read_text(encoding="utf-8")
assert "203.0.113.10" in text
assert "ssh-ed25519" in text
assert "/dev/null" not in text

tokyo_pub = os.path.normpath(os.path.join(os.path.dirname(lax_pub), "..", "tokyo", "hostkey.pub"))
extra, batch = mod.prepare_ssh_host_key(
    "203.0.113.11",
    22,
    mod.fingerprint_sha256(open(tokyo_pub, encoding="utf-8").read()),
)
assert batch is True
assert extra is not None
assert "StrictHostKeyChecking=yes" in extra
assert "StrictHostKeyChecking=no" not in extra
argv = mod.ssh_argv(
    "203.0.113.11",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=batch,
    extra=extra,
)
assert "BatchMode=yes" in argv
assert "StrictHostKeyChecking=yes" in argv
assert "StrictHostKeyChecking=no" not in argv
assert "UserKnownHostsFile=/dev/null" not in " ".join(argv)

mismatch = False
buf = io.StringIO()
sys.stderr = buf
try:
    mod.pin_host_key("203.0.113.10", 22, "SHA256:deadbeef")
except SystemExit:
    mismatch = True
finally:
    sys.stderr = old_err
assert mismatch
assert "host key mismatch" in buf.getvalue()

# TTY first-connect: authenticity prompt → guidance, no registry write
mod.stdin_is_tty = lambda: True
ns = argparse.Namespace(
    name="ask",
    host="203.0.113.17",
    user=None,
    port=22,
    node_id=None,
    instance_id=None,
    offline=False,
    host_key=None,
)
ask_fail = False
buf = io.StringIO()
sys.stderr = buf
try:
    mod.cmd_node_add(ns)
except SystemExit:
    ask_fail = True
finally:
    sys.stderr = old_err
assert ask_fail
ask_err = buf.getvalue()
assert "authenticity of host" in ask_err
assert "--host-key SHA256:" in ask_err

ns = argparse.Namespace(
    name="badkey",
    host="203.0.113.13",
    user=None,
    port=22,
    node_id=None,
    instance_id=None,
    offline=False,
    host_key=None,
)
bad_fail = False
buf = io.StringIO()
sys.stderr = buf
try:
    mod.cmd_node_add(ns)
except SystemExit:
    bad_fail = True
finally:
    sys.stderr = old_err
assert bad_fail
assert "Host key verification failed" in buf.getvalue()

ns = argparse.Namespace(
    name="sglive",
    host="203.0.113.12",
    user=None,
    port=22,
    node_id=None,
    instance_id=None,
    offline=False,
    host_key=None,
)
sg_fail = False
buf = io.StringIO()
sys.stderr = buf
try:
    mod.cmd_node_add(ns)
except SystemExit:
    sg_fail = True
finally:
    sys.stderr = old_err
assert sg_fail
assert "Connection refused" in buf.getvalue()

ns = argparse.Namespace(
    name="badjson",
    host="203.0.113.15",
    user=None,
    port=22,
    node_id=None,
    instance_id=None,
    offline=False,
    host_key=None,
)
badjson_fail = False
buf = io.StringIO()
sys.stderr = buf
try:
    mod.cmd_node_add(ns)
except SystemExit:
    badjson_fail = True
finally:
    sys.stderr = old_err
assert badjson_fail
assert "not JSON" in buf.getvalue()

ns = argparse.Namespace(
    name="copied",
    host="203.0.113.16",
    user=None,
    port=22,
    node_id=None,
    instance_id=None,
    offline=False,
    host_key=None,
)
copied_fail = False
buf = io.StringIO()
sys.stderr = buf
try:
    mod.cmd_node_add(ns)
except SystemExit:
    copied_fail = True
finally:
    sys.stderr = old_err
assert copied_fail
assert "instance_id equals node_id" in buf.getvalue()
PY
if (( hostkey_py_rc == 0 )); then
  pass "host-key policy: keyscan candidates, pin, TTY authenticity guidance"
else
  fail "host-key policy: keyscan candidates, pin, TTY authenticity guidance"
fi

OFFLINE_FLEET_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="${TEST_TMP}/fleet-home-hostkey"
assert_success "host-key fleet home init" fleet init

nohk_rc=0
nohk_err=$(fleet node add lax --host 203.0.113.10 2>&1) || nohk_rc=$?
if (( nohk_rc != 0 )); then
  pass "AC-2.8-10 non-TTY add without --host-key fails"
else
  fail "AC-2.8-10 non-TTY add without --host-key fails (rc=${nohk_rc})"
fi
assert_success "non-TTY error names --host-key SHA256" \
  grep -q 'non-interactive add requires --host-key SHA256:' <<< "$nohk_err"
assert_failure "non-TTY without --host-key does not register lax" \
  grep -q 'lax' "${VCL_FLEET_HOME}/fleet.json"

mismatch_rc=0
mismatch_err=$(fleet node add lax --host 203.0.113.10 --host-key SHA256:deadbeef 2>&1) || mismatch_rc=$?
if (( mismatch_rc != 0 )); then
  pass "--host-key mismatch fails"
else
  fail "--host-key mismatch fails (rc=${mismatch_rc})"
fi
assert_success "--host-key mismatch names host key mismatch" \
  grep -q 'host key mismatch' <<< "$mismatch_err"
assert_failure "--host-key mismatch does not register lax" \
  grep -q 'lax' "${VCL_FLEET_HOME}/fleet.json"

badfmt_rc=0
badfmt_err=$(fleet node add lax --host 203.0.113.10 --host-key not-a-fingerprint 2>&1) || badfmt_rc=$?
if (( badfmt_rc != 0 )); then
  pass "invalid --host-key format rejected"
else
  fail "invalid --host-key format rejected"
fi
assert_success "invalid --host-key names SHA256" \
  grep -q 'SHA256:' <<< "$badfmt_err"

badkey_pin_rc=0
badkey_pin_err=$(fleet node add badkey --host 203.0.113.13 --host-key "$BADKEY_HOST_KEY" 2>&1) || badkey_pin_rc=$?
if (( badkey_pin_rc != 0 )); then
  pass "node add 203.0.113.13 fails after pin"
else
  fail "node add 203.0.113.13 fails after pin (rc=${badkey_pin_rc})"
fi
assert_success "pinned badkey names Host key verification failed" \
  grep -q 'Host key verification failed' <<< "$badkey_pin_err"
assert_failure "host-key failure does not register badkey" \
  grep -q 'badkey' "${VCL_FLEET_HOME}/fleet.json"

assert_success "live SSH add lax with --host-key" \
  fleet node add lax --host 203.0.113.10 --host-key "$LAX_HOST_KEY"
lax_show=$(fleet node show lax)
assert_success "live add registers remote node_id" \
  grep -q "node_id=${LAX_REMOTE_NODE_ID}" <<< "$lax_show"
assert_success "live add records ssh_host" \
  grep -q 'ssh_host=203.0.113.10' <<< "$lax_show"
assert_success "live add defaults ssh_user root" \
  grep -q 'ssh_user=root' <<< "$lax_show"
assert_failure "live add does not store instance_id" \
  grep -q 'instance_id' <<< "$lax_show"
assert_success "pinned lax host key landed in user known_hosts" \
  grep -q '203.0.113.10' "${HOME}/.ssh/known_hosts"
assert_failure "known_hosts is not /dev/null" \
  grep -q '/dev/null' "${HOME}/.ssh/known_hosts"

assert_success "live SSH add tokyo via user@host and --host-key" \
  fleet node add tokyo --host root@203.0.113.11 --host-key "$TOKYO_HOST_KEY"
tokyo_show=$(fleet node show tokyo)
assert_success "live tokyo uses remote node_id" \
  grep -q "node_id=${TEST_TOKYO_NODE_ID}" <<< "$tokyo_show"
assert_success "live tokyo ssh_host strips user" \
  grep -q 'ssh_host=203.0.113.11' <<< "$tokyo_show"

sg_live_rc=0
sg_live_err=$(fleet node add sg --host 203.0.113.12 2>&1) || sg_live_rc=$?
if (( sg_live_rc != 0 )); then
  pass "live SSH add sg without --host-key fails"
else
  fail "live SSH add sg without --host-key fails (rc=${sg_live_rc})"
fi
assert_success "live SSH add sg without --host-key names --host-key" \
  grep -q 'non-interactive add requires --host-key SHA256:' <<< "$sg_live_err"
assert_failure "SSH failure does not register sg before offline add" \
  grep -q '"name": "sg"' "${VCL_FLEET_HOME}/fleet.json"

dup_live_rc=0
dup_live_err=$(fleet node add lax2 --host 203.0.113.10 --host-key "$LAX_HOST_KEY" 2>&1) || dup_live_rc=$?
if (( dup_live_rc != 0 )); then
  pass "live SSH add rejects duplicate remote node_id"
else
  fail "live SSH add rejects duplicate remote node_id"
fi
assert_success "live duplicate names node_id" \
  grep -q 'duplicate node_id' <<< "$dup_live_err"

assert_success "offline add sg into SSH fleet home" \
  fleet node add sg --host 203.0.113.12 --offline --node-id "$TEST_SG_NODE_ID"
ssh_three=$(fleet node list)
assert_success "AC-2.8-01 SSH fleet list has lax" grep -q '^lax ' <<< "$ssh_three"
assert_success "AC-2.8-01 SSH fleet list has tokyo" grep -q '^tokyo ' <<< "$ssh_three"
assert_success "AC-2.8-01 SSH fleet list has sg" grep -q '^sg ' <<< "$ssh_three"
node_lines=$(grep -cE '^(lax|tokyo|sg) ' <<< "$ssh_three" || true)
assert_equal "AC-2.8-01 list has exactly 3 fixture nodes" "3" "$node_lines"

ssh_reg_rc=0
python3 - "${VCL_FLEET_HOME}/fleet.json" "$LAX_REMOTE_NODE_ID" "$TEST_TOKYO_NODE_ID" "$TEST_SG_NODE_ID" <<'PY' || ssh_reg_rc=$?
import json, sys
path, lax_id, tokyo_id, sg_id = sys.argv[1:5]
raw = open(path, encoding="utf-8").read()
assert "instance_id" not in raw
assert "password" not in raw
data = json.load(open(path, encoding="utf-8"))
assert data.get("schema_version") == 1
names = {n["name"]: n for n in data["nodes"]}
assert set(names) == {"lax", "tokyo", "sg"}, set(names)
assert names["lax"]["node_id"] == lax_id
assert names["tokyo"]["node_id"] == tokyo_id
assert names["sg"]["node_id"] == sg_id
assert names["lax"]["ssh_host"] == "203.0.113.10"
assert names["tokyo"]["ssh_host"] == "203.0.113.11"
assert names["sg"]["ssh_host"] == "203.0.113.12"
PY
if (( ssh_reg_rc == 0 )); then
  pass "live SSH registry stores remote node_ids without instance_id"
else
  fail "live SSH registry stores remote node_ids without instance_id"
fi

clock_fn_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY' || clock_fn_rc=$?
import importlib.util
import sys
from datetime import datetime, timedelta, timezone

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
now = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)
assert mod.clock_skew_result(now, now)[0] == "OK"
assert mod.clock_skew_result(now, now + timedelta(seconds=30))[0] == "OK"
assert mod.clock_skew_result(now, now + timedelta(seconds=31))[0] == "WARN"
assert mod.clock_skew_result(now, now + timedelta(seconds=300))[0] == "WARN"
assert mod.clock_skew_result(now, now + timedelta(seconds=301))[0] == "FAIL"
fail_state, fail_detail = mod.clock_skew_result(now, now + timedelta(seconds=301))
assert fail_state == "FAIL"
assert mod.CLOCK_SKEW_FAIL_CHECK in fail_detail
assert str(mod.CLOCK_SKEW_FAIL_SECONDS) in fail_detail
warn_state, warn_detail = mod.clock_skew_result(now, now + timedelta(seconds=31))
assert warn_state == "WARN"
assert str(mod.CLOCK_SKEW_WARN_SECONDS) in warn_detail
missing = mod.clock_skew_from_identity(now, {"node_id": "x"})
assert missing[0] == "FAIL"
assert mod.CLOCK_SKEW_FAIL_CHECK in missing[1]
stale = {
    "ok": False,
    "proxy": {"ok": True},
    "accounting": {"ok": False, "heartbeat": "stale"},
}
healthy = {
    "ok": True,
    "proxy": {"ok": True},
    "accounting": {"ok": True, "heartbeat": "fresh"},
}
proxy_fail = {
    "ok": False,
    "proxy": {"ok": False},
    "accounting": {"ok": True, "heartbeat": "fresh"},
}
acct_fail = {
    "ok": False,
    "proxy": {"ok": True},
    "accounting": {"ok": False, "heartbeat": "missing"},
}
assert mod.classify_proxy(healthy) == "OK"
assert mod.classify_accounting(healthy) == "OK"
assert mod.classify_accounting(stale) == "STALE"
assert mod.classify_proxy(proxy_fail) == "FAIL"
assert mod.classify_accounting(acct_fail) == "FAIL"
assert mod.classify_proxy(None) == "UNKNOWN"
assert mod.classify_accounting(None) == "UNKNOWN"
PY
if (( clock_fn_rc == 0 )); then
  pass "clock_skew_result 0=OK 31=WARN 301=FAIL; accounting stale vs fail"
else
  fail "clock_skew_result 0=OK 31=WARN 301=FAIL; accounting stale vs fail"
fi

verify_help=$(fleet verify --help)
assert_success "verify --help mentions 30" grep -q '30' <<< "$verify_help"
assert_success "verify --help mentions 300" grep -q '300' <<< "$verify_help"
assert_success "verify --help mentions audit-clock-health" \
  grep -q 'audit-clock-health' <<< "$verify_help"
assert_success "status --help lists NODE_ID column" \
  grep -q 'NODE_ID' <<< "$(fleet status --help)"

status_rc=0
status_out=$(fleet status 2>&1) || status_rc=$?
if (( status_rc != 0 )); then
  pass "AC-2.8-03 three-fixture status exits non-zero (sg SSH FAIL)"
else
  fail "AC-2.8-03 three-fixture status exits non-zero (sg SSH FAIL) (rc=${status_rc})"
fi
assert_success "status table header has NAME NODE_ID INSTANCE SSH PROXY ACCOUNTING" \
  grep -Eq 'NAME.+NODE_ID.+INSTANCE.+SSH.+PROXY.+ACCOUNTING' <<< "$status_out"
assert_success "AC-2.8-03 status lax OK/OK/OK" \
  grep -Eq '^lax[[:space:]].*[[:space:]]OK[[:space:]]+OK[[:space:]]+OK[[:space:]]*$' <<< "$status_out"
assert_success "AC-2.8-03 status tokyo OK/OK/STALE" \
  grep -Eq '^tokyo[[:space:]].*[[:space:]]OK[[:space:]]+OK[[:space:]]+STALE[[:space:]]*$' <<< "$status_out"
assert_success "AC-2.8-03 status sg FAIL/UNKNOWN/UNKNOWN" \
  grep -Eq '^sg[[:space:]].*[[:space:]]FAIL[[:space:]]+UNKNOWN[[:space:]]+UNKNOWN[[:space:]]*$' <<< "$status_out"

status_json_rc=0
status_json=$(fleet status --json 2>/dev/null) || status_json_rc=$?
if (( status_json_rc != 0 )); then
  pass "status --json exits non-zero with sg FAIL"
else
  fail "status --json exits non-zero with sg FAIL (rc=${status_json_rc})"
fi
status_json_shape_rc=0
python3 - "$status_json" "$LAX_REMOTE_NODE_ID" "$TEST_TOKYO_NODE_ID" "$TEST_SG_NODE_ID" <<'PY' || status_json_shape_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
lax_id, tokyo_id, sg_id = sys.argv[2:5]
assert list(doc)[:4] == ["schema_version", "ok", "controller_utc", "nodes"], list(doc)
assert doc["schema_version"] == 1
assert doc["ok"] is False
nodes = {n["name"]: n for n in doc["nodes"]}
assert set(nodes) == {"lax", "tokyo", "sg"}, set(nodes)
for name, node_id in (("lax", lax_id), ("tokyo", tokyo_id), ("sg", sg_id)):
    assert nodes[name]["node_id"] == node_id
    assert list(nodes[name])[:7] == [
        "name", "node_id", "instance_id", "enabled", "ssh", "proxy", "accounting"
    ]
assert nodes["lax"]["ssh"] == "OK"
assert nodes["lax"]["proxy"] == "OK"
assert nodes["lax"]["accounting"] == "OK"
assert nodes["lax"]["instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
assert nodes["tokyo"]["ssh"] == "OK"
assert nodes["tokyo"]["proxy"] == "OK"
assert nodes["tokyo"]["accounting"] == "STALE"
assert nodes["sg"]["ssh"] == "FAIL"
assert nodes["sg"]["proxy"] == "UNKNOWN"
assert nodes["sg"]["accounting"] == "UNKNOWN"
assert nodes["sg"]["instance_id"] is None
PY
if (( status_json_shape_rc == 0 )); then
  pass "status --json shape: lax OK tokyo STALE sg FAIL/UNKNOWN"
else
  fail "status --json shape: lax OK tokyo STALE sg FAIL/UNKNOWN"
fi

verify_rc=0
verify_out=$(fleet verify 2>&1) || verify_rc=$?
if (( verify_rc != 0 )); then
  pass "verify three-fixture exits non-zero (sg FAIL)"
else
  fail "verify three-fixture exits non-zero (sg FAIL) (rc=${verify_rc})"
fi
assert_success "verify reports lax version" grep -q '0.2.9-dev' <<< "$verify_out"
assert_success "verify reports lax node_id" grep -q "$LAX_REMOTE_NODE_ID" <<< "$verify_out"
assert_success "verify reports lax instance_id" \
  grep -q 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' <<< "$verify_out"
assert_success "verify lax ssh OK" grep -q 'ssh: OK' <<< "$verify_out"
assert_success "verify sg SSH FAIL" grep -q 'SSH unreachable' <<< "$verify_out"
assert_success "verify tokyo accounting STALE" grep -q 'accounting: STALE' <<< "$verify_out"

verify_json_rc=0
verify_json=$(fleet verify --json 2>/dev/null) || verify_json_rc=$?
if (( verify_json_rc != 0 )); then
  pass "verify --json exits non-zero with sg FAIL"
else
  fail "verify --json exits non-zero with sg FAIL (rc=${verify_json_rc})"
fi
verify_json_shape_rc=0
python3 - "$verify_json" "$LAX_REMOTE_NODE_ID" <<'PY' || verify_json_shape_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
lax_id = sys.argv[2]
assert doc["schema_version"] == 1
assert doc["ok"] is False
assert "controller_utc" in doc
nodes = {n["name"]: n for n in doc["nodes"]}
need = [
    "name", "ok", "vincula_version", "node_id", "instance_id", "enabled",
    "ssh", "proxy", "accounting", "registry", "clock", "clock_skew_seconds",
    "warnings", "checks",
]
assert list(nodes["lax"]) == need, list(nodes["lax"])
assert nodes["lax"]["ok"] is True
assert nodes["lax"]["vincula_version"] == "0.2.9-dev"
assert nodes["lax"]["node_id"] == lax_id
assert nodes["lax"]["ssh"] == "OK"
assert nodes["lax"]["proxy"] == "OK"
assert nodes["lax"]["accounting"] == "OK"
assert nodes["lax"]["registry"] == "OK"
assert nodes["lax"]["clock"] == "OK"
assert nodes["tokyo"]["ok"] is True
assert nodes["tokyo"]["accounting"] == "STALE"
assert nodes["sg"]["ok"] is False
assert nodes["sg"]["ssh"] == "FAIL"
assert nodes["sg"]["proxy"] == "UNKNOWN"
assert nodes["sg"]["accounting"] == "UNKNOWN"
assert nodes["sg"]["clock"] == "UNKNOWN"
PY
if (( verify_json_shape_rc == 0 )); then
  pass "verify --json shape: lax pass, tokyo STALE, sg FAIL"
else
  fail "verify --json shape: lax pass, tokyo STALE, sg FAIL"
fi

assert_success "disable sg for stale-only status" fleet node disable sg
stale_status_rc=0
stale_status=$(fleet status 2>&1) || stale_status_rc=$?
if (( stale_status_rc == 0 )); then
  pass "status exits 0 when only accounting STALE remains"
else
  fail "status exits 0 when only accounting STALE remains (rc=${stale_status_rc})"
fi
assert_failure "status without --all omits disabled sg" \
  grep -Eq '^sg[[:space:]]' <<< "$stale_status"
assert_success "status --all shows disabled sg" \
  grep -Eq '^sg[[:space:]].*DISABLED' <<< "$(fleet status --all)"
stale_verify_rc=0
fleet verify >/dev/null 2>&1 || stale_verify_rc=$?
if (( stale_verify_rc == 0 )); then
  pass "verify exits 0 when sg is disabled and tokyo is STALE"
else
  fail "verify exits 0 when sg is disabled and tokyo is STALE (rc=${stale_verify_rc})"
fi
assert_success "re-enable sg" fleet node enable sg

CLOCK_FLEET_HOME="${TEST_TMP}/fleet-home-clock"
SAVED_STATUS_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="${CLOCK_FLEET_HOME}"
assert_success "clock-skew fleet home init" fleet init
assert_success "clock-skew register lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"

export VCL_FAKE_CLOCK_SKEW_SECONDS=45
warn_rc=0
warn_out=$(fleet verify 2>&1) || warn_rc=$?
if (( warn_rc == 0 )); then
  pass "clock skew 45s verify still exits 0"
else
  fail "clock skew 45s verify still exits 0 (rc=${warn_rc})"
fi
assert_success "clock skew 45s prints WARN" grep -q 'WARN' <<< "$warn_out"
assert_success "clock skew 45s warn names 30s threshold" grep -q '30' <<< "$warn_out"
unset VCL_FAKE_CLOCK_SKEW_SECONDS

export VCL_FAKE_CLOCK_SKEW_SECONDS=400
fail_clock_rc=0
fail_clock_out=$(fleet verify 2>&1) || fail_clock_rc=$?
if (( fail_clock_rc != 0 )); then
  pass "clock skew 400s verify exits non-zero"
else
  fail "clock skew 400s verify exits non-zero (rc=${fail_clock_rc})"
fi
assert_success "clock skew 400s names audit-clock-health" \
  grep -q 'audit-clock-health' <<< "$fail_clock_out"
fail_clock_json=$(fleet verify --json 2>/dev/null) || true
clock_json_rc=0
python3 - "$fail_clock_json" <<'PY' || clock_json_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
assert doc["ok"] is False
node = doc["nodes"][0]
assert node["clock"] == "FAIL"
assert node["ok"] is False
names = [c.get("name") for c in node.get("checks") or []]
assert "audit-clock-health" in names, names
PY
if (( clock_json_rc == 0 )); then
  pass "clock skew 400s --json FAIL check is audit-clock-health"
else
  fail "clock skew 400s --json FAIL check is audit-clock-health"
fi
unset VCL_FAKE_CLOCK_SKEW_SECONDS
export VCL_FLEET_HOME="${SAVED_STATUS_HOME}"

# --- Batch 7-ac: named AC-2.8 identity / port / duplicate checks ---

ac_28_identity() {
  local uuid_re='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  local ids_rc=0
  python3 - "${VCL_FLEET_HOME}/fleet.json" "$uuid_re" <<'PY' || ids_rc=$?
import json, re, sys
path, uuid_re = sys.argv[1], sys.argv[2]
raw = open(path, encoding="utf-8").read()
assert "instance_id" not in raw
data = json.load(open(path, encoding="utf-8"))
nodes = data.get("nodes") or []
assert nodes, nodes
seen = set()
for node in nodes:
    nid = node["node_id"]
    assert re.fullmatch(uuid_re, nid), nid
    assert nid not in seen, nid
    seen.add(nid)
    assert "instance_id" not in node
PY
  if (( ids_rc == 0 )); then
    pass "AC-2.8-04 node_id is a stable UUID in registry (not recast)"
  else
    fail "AC-2.8-04 node_id is a stable UUID in registry (not recast)"
  fi

  local before after nid_before host_before nid_after host_after
  before=$(python3 - "${VCL_FLEET_HOME}/fleet.json" <<'PY'
import json, sys
nodes = {n["name"]: n for n in json.load(open(sys.argv[1], encoding="utf-8"))["nodes"]}
print(nodes["lax"]["node_id"])
print(nodes["lax"]["ssh_host"])
PY
)
  nid_before=$(sed -n '1p' <<< "$before")
  host_before=$(sed -n '2p' <<< "$before")
  assert_success "AC-2.8-06 node set lax host for identity check" \
    fleet node set lax --host 203.0.113.28
  after=$(python3 - "${VCL_FLEET_HOME}/fleet.json" <<'PY'
import json, sys
nodes = {n["name"]: n for n in json.load(open(sys.argv[1], encoding="utf-8"))["nodes"]}
print(nodes["lax"]["node_id"])
print(nodes["lax"]["ssh_host"])
PY
)
  nid_after=$(sed -n '1p' <<< "$after")
  host_after=$(sed -n '2p' <<< "$after")
  assert_equal "AC-2.8-06 ssh_host change does not alter node_id" "$nid_before" "$nid_after"
  assert_equal "AC-2.8-06 ssh_host updated" "203.0.113.28" "$host_after"
  assert_success "AC-2.8-06 restore lax ssh_host" \
    fleet node set lax --host "$host_before"
}

ac_28_identity

reinstall_cmp_rc=0
python3 - \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity-reinstall.json" <<'PY' || reinstall_cmp_rc=$?
import json, sys
a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
assert a["node_name"] == b["node_name"] == "lax"
assert a["node_id"] == b["node_id"]
assert a["instance_id"] != b["instance_id"]
assert a["instance_id"] != a["node_id"]
assert b["instance_id"] != b["node_id"]
PY
if (( reinstall_cmp_rc == 0 )); then
  pass "AC-2.8-05 reinstall fixture keeps node_id and mints a new instance_id"
else
  fail "AC-2.8-05 reinstall fixture keeps node_id and mints a new instance_id"
fi

assert_success "disable sg for reinstall verify" fleet node disable sg
base_re_rc=0
fleet verify >/dev/null 2>&1 || base_re_rc=$?
if (( base_re_rc == 0 )); then
  pass "AC-2.8-05 baseline verify writes last-status before reinstall"
else
  fail "AC-2.8-05 baseline verify writes last-status before reinstall (rc=${base_re_rc})"
fi
lax_nid_before=$(python3 - "${VCL_FLEET_HOME}/fleet.json" <<'PY'
import json, sys
nodes = {n["name"]: n for n in json.load(open(sys.argv[1], encoding="utf-8"))["nodes"]}
print(nodes["lax"]["node_id"])
PY
)
export VCL_FAKE_REINSTALL=1
reinstall_rc=0
reinstall_out=$(fleet verify 2>&1) || reinstall_rc=$?
if (( reinstall_rc == 0 )); then
  pass "AC-2.8-05 reinstall verify still exits 0 (WARN, not FAIL)"
else
  fail "AC-2.8-05 reinstall verify still exits 0 (WARN, not FAIL) (rc=${reinstall_rc})"
fi
assert_success "AC-2.8-05 verify WARNs instance changed, node_id stable" \
  grep -q 'instance changed, node_id stable' <<< "$reinstall_out"
reinstall_json_rc=0
python3 - "${VCL_FLEET_HOME}/last-status.json" "$LAX_REMOTE_NODE_ID" \
  "${VCL_FLEET_HOME}/fleet.json" <<'PY' || reinstall_json_rc=$?
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
lax_id, registry_path = sys.argv[2], sys.argv[3]
nodes = {n["name"]: n for n in doc["nodes"]}
lax = nodes["lax"]
assert lax["node_id"] == lax_id
assert lax["instance_id"] == "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
assert "instance changed, node_id stable" in (lax.get("warnings") or []), lax
assert lax["ok"] is True
raw = open(registry_path, encoding="utf-8").read()
assert "instance_id" not in raw
reg = json.load(open(registry_path, encoding="utf-8"))
reg_lax = next(n for n in reg["nodes"] if n["name"] == "lax")
assert reg_lax["node_id"] == lax_id
PY
if (( reinstall_json_rc == 0 )); then
  pass "AC-2.8-05 registry node_id unchanged and instance_id not stored"
else
  fail "AC-2.8-05 registry node_id unchanged and instance_id not stored"
fi
unset VCL_FAKE_REINSTALL
lax_nid_after=$(python3 - "${VCL_FLEET_HOME}/fleet.json" <<'PY'
import json, sys
nodes = {n["name"]: n for n in json.load(open(sys.argv[1], encoding="utf-8"))["nodes"]}
print(nodes["lax"]["node_id"])
PY
)
assert_equal "AC-2.8-05 registry node_id identical after reinstall verify" \
  "$lax_nid_before" "$lax_nid_after"
assert_success "re-enable sg after reinstall verify" fleet node enable sg

dup_named_rc=0
dup_named_err=$(fleet node add lax-reinstall --host 203.0.113.10 --host-key "$LAX_HOST_KEY" 2>&1) || dup_named_rc=$?
if (( dup_named_rc != 0 )); then
  pass "AC-2.8-07 live add of already-registered node_id refused"
else
  fail "AC-2.8-07 live add of already-registered node_id refused"
fi
assert_success "AC-2.8-07 duplicate live add names node_id" \
  grep -q 'duplicate node_id' <<< "$dup_named_err"
assert_failure "AC-2.8-07 duplicate live add does not register lax-reinstall" \
  grep -q 'lax-reinstall' "${VCL_FLEET_HOME}/fleet.json"

assert_success "PARTIAL OP_SUCCESS/OP_FAILED constants" \
  grep -q 'OP_SUCCESS, OP_FAILED = "SUCCESS", "FAILED"' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "PARTIAL exit code is 2" \
  grep -q 'MUTATION_EXIT_PARTIAL = 2' "${PROJECT_DIR}/lib/vincula-fleet.py"

partial_fn_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY' || partial_fn_rc=$?
import importlib.util
import sys

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

uid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
assert mod.OP_SUCCESS == "SUCCESS"
assert mod.OP_FAILED == "FAILED"
assert mod.OP_PARTIAL == "PARTIAL"
assert mod.OP_PLANNED == "PLANNED"
assert mod.OP_APPLYING == "APPLYING"
assert mod.MUTATION_EXIT_SUCCESS == 0
assert mod.MUTATION_EXIT_PARTIAL == 2

planned = mod.plan_mutation(["lax", "tokyo"], tag="alice", user_id=uid)
assert planned["state"] == "PLANNED"
assert planned["planned_nodes"] == ["lax", "tokyo"]
assert planned["nodes"] == []
assert mod.plan_state([]) == "PLANNED"
assert mod.final_state([]) == "PLANNED"
applying = mod.mark_applying(planned)
assert applying["state"] == "APPLYING"
assert planned["state"] == "PLANNED"

ok_results = []
ok_results = mod.record_result(
    ok_results, "lax", True, {"credential_id": "c-lax", "vless_uri": "vless://lax"}
)
ok_results = mod.record_result(
    ok_results, "tokyo", True, {"credential_id": "c-tokyo", "vless_uri": "vless://tokyo"}
)
assert [row["status"] for row in ok_results] == ["SUCCESS", "SUCCESS"]
assert mod.plan_state(ok_results) == "SUCCESS"
assert mod.final_state(ok_results) == "SUCCESS"
ok_doc = mod.mutation_report(ok_results, tag="alice", user_id=uid)
assert ok_doc["state"] == "SUCCESS"
assert ok_doc["remediation"] == []
assert mod.never_report_full_success(ok_doc) == 0
ok_report = mod.format_partial_report(ok_doc)
assert ok_report.splitlines()[0] == "STATE SUCCESS"
assert "lax" in ok_report and "tokyo" in ok_report
assert "Remediation:" not in ok_report

mix = []
mix = mod.record_result(
    mix, "lax", True, {"credential_id": "c-lax", "vless_uri": "vless://lax"}
)
mix = mod.record_result(mix, "tokyo", False, "ssh exit 1: boom")
assert mod.plan_state(mix) == "PARTIAL"
assert mod.final_state(mix) == "PARTIAL"
assert mod.final_state(mix) != "SUCCESS"
mix_doc = mod.mutation_report(mix, tag="alice", user_id=uid)
assert mix_doc["state"] == "PARTIAL"
assert [(n["name"], n["status"]) for n in mix_doc["nodes"]] == [
    ("lax", "SUCCESS"),
    ("tokyo", "FAILED"),
]
assert mix_doc["nodes"][1]["error"] == "ssh exit 1: boom"
expect_cmd = f"vcl-fleet user add alice --nodes tokyo --user-id {uid}"
assert mix_doc["remediation"] == [expect_cmd]
mix_report = mod.format_partial_report(mix_doc)
assert mix_report.splitlines()[0] == "STATE PARTIAL"
assert "tokyo" in mix_report
assert "FAILED" in mix_report
assert "lax" in mix_report
assert "--user-id" in mix_report
assert uid in mix_report
assert expect_cmd in mix_report
assert "Remediation:" in mix_report
assert mod.render_partial_report(mix, tag="alice", user_id=uid) == mix_report
assert mod.never_report_full_success(mix_doc) == 2

all_fail = []
all_fail = mod.record_result(all_fail, "lax", False, "ssh exit 1: lax")
all_fail = mod.record_result(all_fail, "tokyo", False, "ssh exit 1: tokyo")
assert mod.plan_state(all_fail) == "PARTIAL"
assert mod.final_state(all_fail) == "PARTIAL"
assert mod.final_state(all_fail) != "SUCCESS"
fail_doc = mod.mutation_report(all_fail, tag="bob", user_id=uid)
assert fail_doc["state"] == "PARTIAL"
assert fail_doc["state"] != "SUCCESS"
assert all(n["status"] == "FAILED" for n in fail_doc["nodes"])
assert [n["name"] for n in fail_doc["nodes"]] == ["lax", "tokyo"]
assert fail_doc["remediation"] == [
    f"vcl-fleet user add bob --nodes lax --user-id {uid}",
    f"vcl-fleet user add bob --nodes tokyo --user-id {uid}",
]
fail_report = mod.format_partial_report(fail_doc)
assert fail_report.splitlines()[0] == "STATE PARTIAL"
assert "STATE SUCCESS" not in fail_report
assert mod.never_report_full_success(fail_doc) == 2
assert "rollback" not in fail_report.lower()
PY
if (( partial_fn_rc == 0 )); then
  pass "PARTIAL state machine: all-ok SUCCESS, one-fail/all-fail PARTIAL, exit 0/2"
else
  fail "PARTIAL state machine: all-ok SUCCESS, one-fail/all-fail PARTIAL, exit 0/2"
fi

assert_failure "fake-ssh classifies remote argv, not identity substring" \
  grep -q '"identity" in text' "$FAKE_SSH"

unknown_cmd_rc=0
unknown_cmd_err=$("$FAKE_SSH" 203.0.113.10 -- vcl nosuch --json 2>&1) || unknown_cmd_rc=$?
if (( unknown_cmd_rc == 1 )) && [[ "$unknown_cmd_err" == *"unknown vcl command"* ]]; then
  pass "fake-ssh unknown vcl subcommand exits 1"
else
  fail "fake-ssh unknown vcl subcommand exits 1 (rc=${unknown_cmd_rc} err=${unknown_cmd_err})"
fi
assert_failure "fake-ssh unknown subcommand does not emit identity JSON" \
  grep -q 'node_id' <<< "$unknown_cmd_err"

nostate_rc=0
nostate_err=$("$FAKE_SSH" 203.0.113.10 -- vcl user list --json 2>&1) || nostate_rc=$?
if (( nostate_rc != 0 )) && [[ "$nostate_err" == *"VCL_FAKE_STATE_DIR"* ]]; then
  pass "fake-ssh user commands require VCL_FAKE_STATE_DIR"
else
  fail "fake-ssh user commands require VCL_FAKE_STATE_DIR (rc=${nostate_rc} err=${nostate_err})"
fi

ident_nostate=$("$FAKE_SSH" 203.0.113.10 -- vcl identity --json)
assert_success "fake-ssh identity still works without VCL_FAKE_STATE_DIR" \
  grep -q 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' <<< "$ident_nostate"

FAKE_USER_STATE="${TEST_TMP}/fake-user-state"
export VCL_FAKE_STATE_DIR="$FAKE_USER_STATE"
mkdir -p "$VCL_FAKE_STATE_DIR"

ALICE_UID="11111111-1111-4111-8111-111111111111"
BOB_UID="22222222-2222-4222-8222-222222222222"
CAROL_UID="33333333-3333-4333-8333-333333333333"

add_alice_rc=0
add_alice=$("$FAKE_SSH" 203.0.113.10 -- vcl user add alice --user-id "$ALICE_UID" \
  --display-name Alice --department Engineering --json) || add_alice_rc=$?
if (( add_alice_rc == 0 )); then
  pass "fake-ssh user add alice on lax exits 0"
else
  fail "fake-ssh user add alice on lax exits 0 (rc=${add_alice_rc})"
fi

lax_list=$("$FAKE_SSH" 203.0.113.10 -- vcl user list --json)
tokyo_list=$("$FAKE_SSH" 203.0.113.11 -- vcl user list --json)
if python3 - "$add_alice" "$lax_list" "$tokyo_list" "$ALICE_UID" <<'PY'
import json, sys
add, lax, tokyo, uid = sys.argv[1:5]
add_doc = json.loads(add)
lax_doc = json.loads(lax)
tokyo_doc = json.loads(tokyo)
assert add_doc["schema_version"] == 1 and add_doc["ok"] is True, add_doc
assert add_doc["tag"] == "alice" and add_doc["user_id"] == uid, add_doc
assert add_doc["enabled"] is True and add_doc["status"] == "active", add_doc
assert add_doc["credential_id"], add_doc
assert add_doc["vless_uri"].startswith("vless://"), add_doc
assert "@203.0.113.10:443" in add_doc["vless_uri"], add_doc
assert add_doc["vless_uri"].endswith("#alice"), add_doc
assert "uuid" not in add_doc, add_doc
alice = next(u for u in lax_doc["users"] if u["tag"] == "alice")
assert alice["user_id"] == uid, alice
assert alice["display_name"] == "Alice", alice
assert alice["department"] == "Engineering", alice
assert alice["enabled"] is True, alice
assert alice["active_credential_id"] == add_doc["credential_id"], alice
assert tokyo_doc["schema_version"] == 1, tokyo_doc
assert tokyo_doc["users"] == [], tokyo_doc
PY
then
  pass "fake-ssh user add on lax is visible in lax list, not tokyo"
else
  fail "fake-ssh user add on lax is visible in lax list, not tokyo"
fi

assert_success "fake-ssh wrote lax users.json under VCL_FAKE_STATE_DIR" \
  test -f "${VCL_FAKE_STATE_DIR}/lax/users.json"
assert_success "fake-ssh initialized empty tokyo users.json" \
  test -f "${VCL_FAKE_STATE_DIR}/tokyo/users.json"

lax_show=$("$FAKE_SSH" 203.0.113.10 -- vcl user show alice --json)
assert_success "fake-ssh user show alice includes user_id" \
  grep -q "$ALICE_UID" <<< "$lax_show"
assert_success "fake-ssh user show credentials omit vless uuid field" \
  python3 -c 'import json,sys; d=json.loads(sys.stdin.read());
assert all("uuid" not in c for c in d["credentials"])' <<< "$lax_show"

last_disable_rc=0
last_disable_err=$("$FAKE_SSH" 203.0.113.10 -- vcl user disable alice --json 2>&1) || last_disable_rc=$?
if (( last_disable_rc != 0 )) && [[ "$last_disable_err" == *"last enabled user"* ]]; then
  pass "fake-ssh refuses to disable the last enabled user"
else
  fail "fake-ssh refuses to disable the last enabled user (rc=${last_disable_rc} err=${last_disable_err})"
fi

add_bob_rc=0
"$FAKE_SSH" 203.0.113.10 -- vcl user add bob --user-id "$BOB_UID" --json >/dev/null || add_bob_rc=$?
if (( add_bob_rc == 0 )); then
  pass "fake-ssh user add bob on lax exits 0"
else
  fail "fake-ssh user add bob on lax exits 0 (rc=${add_bob_rc})"
fi

old_cred=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["credential_id"])' <<< "$add_alice")
rotate_rc=0
rotate_out=$("$FAKE_SSH" 203.0.113.10 -- vcl user rotate alice --json) || rotate_rc=$?
if (( rotate_rc == 0 )); then
  pass "fake-ssh rotate alice on lax exits 0"
else
  fail "fake-ssh rotate alice on lax exits 0 (rc=${rotate_rc})"
fi
new_list=$("$FAKE_SSH" 203.0.113.10 -- vcl user list --json)
new_show=$("$FAKE_SSH" 203.0.113.10 -- vcl user show alice --json)
if python3 - "$rotate_out" "$new_list" "$new_show" "$old_cred" "$ALICE_UID" <<'PY'
import json, sys
rotate, listed, show, old_cred, uid = sys.argv[1:6]
rot = json.loads(rotate)
lax = json.loads(listed)
show_doc = json.loads(show)
assert rot["ok"] is True and rot["user_id"] == uid, rot
assert rot["credential_id"] != old_cred, (rot["credential_id"], old_cred)
assert rot["vless_uri"].startswith("vless://")
assert rot["credential_id"] in rot["vless_uri"]
alice = next(u for u in lax["users"] if u["tag"] == "alice")
assert alice["user_id"] == uid, alice
assert alice["active_credential_id"] == rot["credential_id"], alice
assert alice["active_credential_id"] != old_cred, alice
assert alice["credentials"]["count"] == 2, alice
assert alice["credentials"]["active"] == 1, alice
assert alice["credentials"]["revoked"] == 1, alice
statuses = [c["status"] for c in show_doc["credentials"]]
assert statuses.count("revoked") == 1 and statuses.count("active") == 1, statuses
assert all("uuid" not in c for c in show_doc["credentials"])
PY
then
  pass "fake-ssh rotate alice on lax changes credential_id"
else
  fail "fake-ssh rotate alice on lax changes credential_id"
fi

disable_out=$("$FAKE_SSH" 203.0.113.10 -- vcl user disable alice --json)
disable_list=$("$FAKE_SSH" 203.0.113.10 -- vcl user list --json)
if python3 - "$disable_out" "$disable_list" <<'PY'
import json, sys
dis = json.loads(sys.argv[1])
listed = json.loads(sys.argv[2])
assert dis["schema_version"] == 1 and dis["ok"] is True, dis
assert dis["tag"] == "alice" and dis["enabled"] is False, dis
alice = next(u for u in listed["users"] if u["tag"] == "alice")
bob = next(u for u in listed["users"] if u["tag"] == "bob")
assert alice["enabled"] is False, alice
assert bob["enabled"] is True, bob
PY
then
  pass "fake-ssh disable alice is reflected in subsequent list"
else
  fail "fake-ssh disable alice is reflected in subsequent list"
fi

enable_out=$("$FAKE_SSH" 203.0.113.10 -- vcl user enable alice --json)
assert_success "fake-ssh enable alice reports enabled true" \
  python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["enabled"] is True' <<< "$enable_out"

export VCL_FAKE_FAIL_USER_ADD=tokyo
fail_tokyo_rc=0
fail_tokyo=$("$FAKE_SSH" 203.0.113.11 -- vcl user add carol --user-id "$CAROL_UID" --json) || fail_tokyo_rc=$?
fail_tokyo_list=$("$FAKE_SSH" 203.0.113.11 -- vcl user list --json)
lax_carol_rc=0
lax_carol=$("$FAKE_SSH" 203.0.113.10 -- vcl user add carol --user-id "$CAROL_UID" --json) || lax_carol_rc=$?
if python3 - "$fail_tokyo" "$fail_tokyo_list" "$lax_carol" "$fail_tokyo_rc" "$lax_carol_rc" "$CAROL_UID" <<'PY'
import json, sys
fail_out, tokyo_list, lax_add, fail_rc, lax_rc, uid = sys.argv[1:7]
fail_doc = json.loads(fail_out)
tokyo_doc = json.loads(tokyo_list)
lax_doc = json.loads(lax_add)
assert int(fail_rc) == 1, fail_rc
assert fail_doc.get("ok") is False, fail_doc
assert fail_doc.get("error") == "failed", fail_doc
assert fail_doc.get("schema_version") == 1, fail_doc
assert tokyo_doc["users"] == [], tokyo_doc
assert int(lax_rc) == 0, lax_rc
assert lax_doc["ok"] is True and lax_doc["tag"] == "carol", lax_doc
assert lax_doc["user_id"] == uid, lax_doc
PY
then
  pass "fake-ssh VCL_FAKE_FAIL_USER_ADD=tokyo injects per-host user add failure"
else
  fail "fake-ssh VCL_FAKE_FAIL_USER_ADD=tokyo injects per-host user add failure"
fi
unset VCL_FAKE_FAIL_USER_ADD

ident_with_state=$("$FAKE_SSH" 203.0.113.10 -- vcl identity --json)
assert_success "fake-ssh identity still works with VCL_FAKE_STATE_DIR set" \
  grep -q 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' <<< "$ident_with_state"

status_with_state_rc=0
"$FAKE_SSH" 203.0.113.10 -- vcl status --json >/dev/null || status_with_state_rc=$?
if (( status_with_state_rc == 0 )); then
  pass "fake-ssh status still works with VCL_FAKE_STATE_DIR set"
else
  fail "fake-ssh status still works with VCL_FAKE_STATE_DIR set (rc=${status_with_state_rc})"
fi

unset VCL_FAKE_STATE_DIR

assert_success "SSH mutation timeout is 60s" \
  grep -q 'SSH_MUTATION_TIMEOUT_SECONDS = 60' "${PROJECT_DIR}/lib/vincula-fleet.py"

user_add_help_rc=0
user_add_help=$(fleet user add -h 2>&1) || user_add_help_rc=$?
if (( user_add_help_rc == 0 )) && [[ "$user_add_help" == *"PARTIAL"* ]] \
  && [[ "$user_add_help" == *"--nodes"* ]] && [[ "$user_add_help" == *"--user-id"* ]]; then
  pass "user add -h prints PARTIAL/--nodes/--user-id help"
else
  fail "user add -h prints PARTIAL/--nodes/--user-id help (rc=${user_add_help_rc})"
fi
assert_success "user add help does not promise rollback" \
  grep -qi 'not promised' <<< "$user_add_help"

USER_FLEET_HOME="${TEST_TMP}/fleet-home-users"
USER_FAKE_STATE="${TEST_TMP}/fake-fleet-user-state"
export VCL_FLEET_HOME="$USER_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$USER_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "$VCL_FAKE_STATE_DIR"
assert_success "user-test fleet init" fleet init
assert_success "user-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"
assert_success "user-test offline add tokyo" \
  fleet node add tokyo --host 203.0.113.11 --offline --node-id "$TEST_TOKYO_NODE_ID"

add_alice_rc=0
add_alice_out=$(fleet user add alice --nodes lax,tokyo --display-name Alice --department Engineering) || add_alice_rc=$?
if (( add_alice_rc == 0 )); then
  pass "AC-2.9-01 user add alice --nodes lax,tokyo exits 0"
else
  fail "AC-2.9-01 user add alice --nodes lax,tokyo exits 0 (rc=${add_alice_rc})"
fi
assert_success "AC-2.9-07 credential CSV header" \
  grep -q '^user,node,credential_id,vless_uri$' <<< "$add_alice_out"

ac_add_rc=0
python3 - "$add_alice_out" "$VCL_FAKE_STATE_DIR" <<'PY' || ac_add_rc=$?
import csv, io, json, sys
from pathlib import Path

text, state = sys.argv[1], Path(sys.argv[2])
rows = list(csv.DictReader(io.StringIO(text)))
assert [r for r in text.splitlines() if r][0] == "user,node,credential_id,vless_uri"
assert {row["user"] for row in rows} == {"alice"}, rows
by_node = {row["node"]: row for row in rows}
assert set(by_node) == {"lax", "tokyo"}, by_node
assert by_node["lax"]["credential_id"] != by_node["tokyo"]["credential_id"]
assert by_node["lax"]["vless_uri"] != by_node["tokyo"]["vless_uri"]
assert "@203.0.113.10:443" in by_node["lax"]["vless_uri"]
assert "@203.0.113.11:443" in by_node["tokyo"]["vless_uri"]
assert by_node["lax"]["credential_id"] in by_node["lax"]["vless_uri"]
assert by_node["tokyo"]["credential_id"] in by_node["tokyo"]["vless_uri"]
lax = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
tokyo = json.loads((state / "tokyo" / "users.json").read_text(encoding="utf-8"))
alice_lax = next(u for u in lax["users"] if u["tag"] == "alice")
alice_tokyo = next(u for u in tokyo["users"] if u["tag"] == "alice")
assert alice_lax["user_id"] == alice_tokyo["user_id"], (alice_lax["user_id"], alice_tokyo["user_id"])
assert alice_lax["user_id"]
assert alice_lax["display_name"] == "Alice"
assert alice_lax["department"] == "Engineering"
lax_active = next(c for c in alice_lax["credentials"] if c["status"] == "active")
tokyo_active = next(c for c in alice_tokyo["credentials"] if c["status"] == "active")
assert lax_active["credential_id"] == by_node["lax"]["credential_id"]
assert tokyo_active["credential_id"] == by_node["tokyo"]["credential_id"]
assert lax_active["credential_id"] != tokyo_active["credential_id"]
open(state / "alice_user_id.txt", "w", encoding="utf-8").write(alice_lax["user_id"])
open(state / "alice_lax_cred.txt", "w", encoding="utf-8").write(lax_active["credential_id"])
open(state / "alice_tokyo_cred.txt", "w", encoding="utf-8").write(tokyo_active["credential_id"])
PY
if (( ac_add_rc == 0 )); then
  pass "AC-2.9-01 same user_id two nodes different credential UUID"
  pass "AC-2.9-07 credential CSV is node-specific (lax/tokyo hosts)"
else
  fail "AC-2.9-01 same user_id two nodes different credential UUID"
  fail "AC-2.9-07 credential CSV is node-specific (lax/tokyo hosts)"
fi
ALICE_FLEET_UID=$(cat "${VCL_FAKE_STATE_DIR}/alice_user_id.txt")
ALICE_LAX_CRED=$(cat "${VCL_FAKE_STATE_DIR}/alice_lax_cred.txt")
ALICE_TOKYO_CRED=$(cat "${VCL_FAKE_STATE_DIR}/alice_tokyo_cred.txt")

add_json_rc=0
add_json_out=$(fleet user add alice --nodes lax,tokyo --user-id "$ALICE_FLEET_UID" --json) || add_json_rc=$?
if python3 - "$add_json_out" "$add_json_rc" "$ALICE_FLEET_UID" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
assert doc["state"] == "SUCCESS", doc
assert doc["user_id"] == sys.argv[3], (doc["user_id"], sys.argv[3])
assert {n["name"]: n["status"] for n in doc["nodes"]} == {"lax": "SUCCESS", "tokyo": "SUCCESS"}
assert doc["nodes"][0]["credential_id"] != doc["nodes"][1]["credential_id"]
PY
then
  pass "user add --json is idempotent SUCCESS with the same user_id"
else
  fail "user add --json is idempotent SUCCESS with the same user_id"
fi

list_out=$(fleet user list)
assert_success "user list header TAG USER_ID NODES" \
  grep -q '^TAG USER_ID NODES$' <<< "$list_out"
assert_success "user list alice spans lax,tokyo" \
  grep -Eq "^alice ${ALICE_FLEET_UID} (lax,tokyo|tokyo,lax)$" <<< "$list_out"

list_json=$(fleet user list --json)
if python3 - "$list_json" "$ALICE_FLEET_UID" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
uid = sys.argv[2]
assert doc["schema_version"] == 1 and doc["ok"] is True, doc
alice = next(u for u in doc["users"] if u["tag"] == "alice")
assert alice["user_id"] == uid, alice
assert {n["name"] for n in alice["nodes"]} == {"lax", "tokyo"}, alice
PY
then
  pass "user list --json aggregates alice by user_id"
else
  fail "user list --json aggregates alice by user_id"
fi

show_out=$(fleet user show alice)
assert_success "user show alice names both nodes" \
  grep -q '^lax ' <<< "$show_out"
assert_success "user show alice includes tokyo" \
  grep -q '^tokyo ' <<< "$show_out"

show_json=$(fleet user show alice --json)
if python3 - "$show_json" "$ALICE_FLEET_UID" "$ALICE_LAX_CRED" "$ALICE_TOKYO_CRED" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
uid, lax_cred, tokyo_cred = sys.argv[2:5]
assert doc["ok"] is True and doc["tag"] == "alice", doc
assert doc["user_id"] == uid, doc
by_name = {n["name"]: n for n in doc["nodes"]}
assert by_name["lax"]["credential_id"] == lax_cred, by_name["lax"]
assert by_name["tokyo"]["credential_id"] == tokyo_cred, by_name["tokyo"]
assert by_name["lax"]["enabled"] is True and by_name["tokyo"]["enabled"] is True
assert by_name["lax"]["status"] == "active"
PY
then
  pass "user show alice --json reports per-node credentials"
else
  fail "user show alice --json reports per-node credentials"
fi

rotate_rc=0
rotate_out=$(fleet user rotate alice --node lax) || rotate_rc=$?
if (( rotate_rc == 0 )); then
  pass "user rotate alice --node lax exits 0"
else
  fail "user rotate alice --node lax exits 0 (rc=${rotate_rc})"
fi
assert_success "rotate stdout is a credential CSV row" \
  grep -q '^user,node,credential_id,vless_uri$' <<< "$rotate_out"

rotate_check_rc=0
python3 - "$rotate_out" "$VCL_FAKE_STATE_DIR" "$ALICE_LAX_CRED" "$ALICE_TOKYO_CRED" <<'PY' || rotate_check_rc=$?
import csv, io, json, sys
from pathlib import Path
text, state, old_lax, old_tokyo = sys.argv[1:5]
rows = list(csv.DictReader(io.StringIO(text)))
assert len(rows) == 1, rows
assert rows[0]["user"] == "alice" and rows[0]["node"] == "lax"
assert rows[0]["credential_id"] != old_lax
assert "@203.0.113.10:443" in rows[0]["vless_uri"]
lax = json.loads((Path(state) / "lax" / "users.json").read_text(encoding="utf-8"))
tokyo = json.loads((Path(state) / "tokyo" / "users.json").read_text(encoding="utf-8"))
alice_lax = next(u for u in lax["users"] if u["tag"] == "alice")
alice_tokyo = next(u for u in tokyo["users"] if u["tag"] == "alice")
lax_active = next(c for c in alice_lax["credentials"] if c["status"] == "active")
tokyo_active = next(c for c in alice_tokyo["credentials"] if c["status"] == "active")
assert lax_active["credential_id"] == rows[0]["credential_id"]
assert lax_active["credential_id"] != old_lax
assert tokyo_active["credential_id"] == old_tokyo
assert alice_lax["user_id"] == alice_tokyo["user_id"]
PY
if (( rotate_check_rc == 0 )); then
  pass "AC-2.9-02 rotate one node does not change the other node's credential"
else
  fail "AC-2.9-02 rotate one node does not change the other node's credential"
fi

dave_add_rc=0
dave_add_out=$(fleet user add dave --node lax) || dave_add_rc=$?
if (( dave_add_rc == 0 )); then
  pass "user add dave on lax (so alice is not last enabled)"
else
  fail "user add dave on lax (so alice is not last enabled) (rc=${dave_add_rc})"
fi

disable_rc=0
disable_out=$(fleet user disable alice --node lax) || disable_rc=$?
if (( disable_rc == 0 )) && [[ "$disable_out" == *"disabled on lax"* ]]; then
  pass "user disable alice --node lax exits 0"
else
  fail "user disable alice --node lax exits 0 (rc=${disable_rc} out=${disable_out})"
fi

disable_json=$(fleet user show alice --json)
if python3 - "$disable_json" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
by_name = {n["name"]: n for n in doc["nodes"]}
assert by_name["lax"]["enabled"] is False, by_name["lax"]
assert by_name["tokyo"]["enabled"] is True, by_name["tokyo"]
PY
then
  pass "AC-2.9-03 disable one node does not disable the user on other nodes"
else
  fail "AC-2.9-03 disable one node does not disable the user on other nodes"
fi

enable_back_rc=0
fleet user enable alice --node lax >/dev/null || enable_back_rc=$?
if (( enable_back_rc == 0 )); then
  pass "user enable alice --node lax exits 0"
else
  fail "user enable alice --node lax exits 0 (rc=${enable_back_rc})"
fi

no_node_rc=0
no_node_err=$(fleet user disable alice 2>&1) || no_node_rc=$?
if (( no_node_rc != 0 )) && [[ "$no_node_err" == *"refusing fleet-wide disable"* ]]; then
  pass "user disable without --node is refused"
else
  fail "user disable without --node is refused (rc=${no_node_rc} err=${no_node_err})"
fi

export VCL_FAKE_FAIL_USER_ADD=tokyo
partial_rc=0
partial_out=$(fleet user add bob --nodes lax,tokyo --display-name Bob 2>&1) || partial_rc=$?
unset VCL_FAKE_FAIL_USER_ADD
if (( partial_rc == 2 )); then
  pass "AC-2.9-06 partial user add exits 2"
else
  fail "AC-2.9-06 partial user add exits 2 (rc=${partial_rc})"
fi
assert_success "AC-2.9-06 output contains PARTIAL" \
  grep -q '^STATE PARTIAL' <<< "$partial_out"
assert_failure "AC-2.9-06 overall state is not SUCCESS" \
  grep -q '^STATE SUCCESS' <<< "$partial_out"
assert_success "AC-2.9-06 tokyo FAILED" \
  grep -Eq 'tokyo[[:space:]]+FAILED' <<< "$partial_out"
assert_success "AC-2.9-06 remediation includes --user-id" \
  grep -q 'vcl-fleet user add bob --nodes tokyo --user-id ' <<< "$partial_out"
assert_success "AC-2.9-06 successful lax row is still in CSV" \
  grep -q '^bob,lax,' <<< "$partial_out"

if python3 - "$VCL_FAKE_STATE_DIR" <<'PY'
import json, sys
from pathlib import Path
state = Path(sys.argv[1])
lax = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
tokyo = json.loads((state / "tokyo" / "users.json").read_text(encoding="utf-8"))
assert any(u["tag"] == "bob" for u in lax["users"]), lax
assert not any(u["tag"] == "bob" for u in tokyo["users"]), tokyo
PY
then
  pass "AC-2.9-06 bob exists on lax only after tokyo FAIL inject"
else
  fail "AC-2.9-06 bob exists on lax only after tokyo FAIL inject"
fi

unset VCL_FAKE_STATE_DIR

assert_success "docs/fleet.md exists" test -f "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md documents vcl-fleet.cmd" \
  grep -q 'vcl-fleet.cmd' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md documents --host-key" \
  grep -q -- '--host-key' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md names CLOCK_SKEW_WARN_SECONDS 30" \
  grep -q 'CLOCK_SKEW_WARN_SECONDS = 30' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md names CLOCK_SKEW_FAIL_SECONDS 300" \
  grep -q 'CLOCK_SKEW_FAIL_SECONDS = 300' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md has AC-2.8-01" \
  grep -q 'AC-2.8-01' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md has AC-2.8-10" \
  grep -q 'AC-2.8-10' "${PROJECT_DIR}/docs/fleet.md"

export VCL_FLEET_HOME="${OFFLINE_FLEET_HOME}"
if [[ -n "${FLEET_SAVED_HOME}" ]]; then
  export HOME="${FLEET_SAVED_HOME}"
else
  unset HOME
fi
