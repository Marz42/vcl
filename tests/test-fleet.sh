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

assert_equal "vcl-fleet version" "vcl-fleet 0.2.8-dev" \
  "$(python3 "${PROJECT_DIR}/bin/vcl-fleet" version)"
assert_equal "vcl-fleet.py version" "vcl-fleet 0.2.8-dev" \
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

export VCL_FLEET_HOME="${OFFLINE_FLEET_HOME}"
if [[ -n "${FLEET_SAVED_HOME}" ]]; then
  export HOME="${FLEET_SAVED_HOME}"
else
  unset HOME
fi
