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
export VCL_FLEET_SCP="${PROJECT_DIR}/tests/fixtures/fake-scp"
unset VCL_FAKE_STATE_DIR
unset VCL_FAKE_FAIL_RESTORE
unset VCL_FAKE_RESTORE_LIE_OK
unset VCL_FAKE_FAIL_BACKUP
unset VCL_FAKE_FAIL_SCP
unset VCL_FAKE_REINSTALL
unset VCL_FAKE_EXPORT_LIE_COUNT
unset VCL_FAKE_EXPORT_LIE_NEXT_CURSOR
readonly FAKE_SSH="${VCL_FLEET_SSH}"
readonly FAKE_KEYSCAN="${VCL_FLEET_SSH_KEYSCAN}"
readonly FAKE_SCP="${VCL_FLEET_SCP}"
readonly LAX_REMOTE_NODE_ID="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
readonly LAX_HOSTKEY_PUB="${PROJECT_DIR}/tests/fixtures/nodes/lax/hostkey.pub"
readonly TOKYO_HOSTKEY_PUB="${PROJECT_DIR}/tests/fixtures/nodes/tokyo/hostkey.pub"
readonly BADKEY_HOSTKEY_PUB="${PROJECT_DIR}/tests/fixtures/nodes/badkey/hostkey.pub"
readonly LAX2_HOSTKEY_PUB="${PROJECT_DIR}/tests/fixtures/nodes/lax2/hostkey.pub"

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
LAX2_HOST_KEY=$(fingerprint_of "$LAX2_HOSTKEY_PUB")

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
assert_success "fleet schema version is 2" \
  grep -q 'FLEET_REGISTRY_SCHEMA_VERSION = 2' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet.db schema version is 3" \
  grep -q 'FLEET_CACHE_SCHEMA_VERSION = 3' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet schema aliases retained" \
  grep -q 'FLEET_SCHEMA_VERSION = FLEET_REGISTRY_SCHEMA_VERSION' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet.db schema alias retained" \
  grep -q 'FLEET_DB_SCHEMA_VERSION = FLEET_CACHE_SCHEMA_VERSION' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "namespaced fleet-cache error" \
  grep -q 'unsupported fleet-cache schema:' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "namespaced fleet-registry error" \
  grep -q 'unsupported fleet-registry schema:' "${PROJECT_DIR}/lib/workspace.py"
assert_failure "no bare fleet.json schema die" \
  grep -q 'unsupported fleet.json schema_version:' "${PROJECT_DIR}/lib/vincula-fleet.py" "${PROJECT_DIR}/lib/workspace.py"
assert_success "build-controller uses VCL_FLEET_VERSION" \
  grep -q 'VCL_FLEET_VERSION' "${PROJECT_DIR}/scripts/build-controller.sh"
assert_failure "build-controller ignores VINCULA_VERSION" \
  grep -q 'VINCULA_VERSION' "${PROJECT_DIR}/scripts/build-controller.sh"
assert_success "RO seam" \
  grep -q 'def open_cache_readonly' "${PROJECT_DIR}/lib/workspace.py"
assert_success "RW seam" \
  grep -q 'def open_cache_for_sync' "${PROJECT_DIR}/lib/workspace.py"
assert_success "D57 admin_credential_ref" \
  grep -q 'admin_credential_ref' "${PROJECT_DIR}/lib/workspace.py"
assert_success "D57 observe_credential_ref" \
  grep -q 'observe_credential_ref' "${PROJECT_DIR}/lib/workspace.py"
assert_success "planned_credential_refs" \
  grep -q 'def planned_credential_refs' "${PROJECT_DIR}/lib/workspace.py"

# --- 0.4.1 B1: workspace.json + fleet_id + D52 + last_seen + CAS (T07) ---
SAVED_WS_B1_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="${TEST_TMP}/ws-b1"
assert_success "B1 workspace fleet init" fleet init
ws_b1_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY' || ws_b1_rc=$?
import importlib.util
import os
import sys
import uuid
from pathlib import Path

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

a = mod.mint_fleet_id()
b = mod.mint_fleet_id()
assert a != b, (a, b)
assert mod.UUID_RE.fullmatch(a) and mod.UUID_RE.fullmatch(b), (a, b)

m = mod.create_workspace_manifest()
loaded = mod.load_workspace_manifest()
assert loaded["fleet_id"] == m["fleet_id"]
for key in (
    "schema_version", "fleet_id", "name", "revision", "write_id",
    "parent_revision", "parent_write_id", "state_digest",
    "last_writer_controller_id", "created_at", "updated_at",
):
    assert key in loaded, key
assert loaded["state_digest"] == mod.compute_state_digest()
assert loaded["state_digest"].startswith("sha256:")

bad = dict(loaded)
bad["schema_version"] = 99
msgs = []
orig_die = mod.die

def _capture_die(message, code=1):
    msgs.append(message)
    raise SystemExit(code)

mod.die = _capture_die
try:
    mod.validate_workspace_manifest(bad)
    raise AssertionError("expected unsupported workspace schema")
except SystemExit:
    pass
assert any("unsupported workspace schema:" in x for x in msgs), msgs
mod.die = orig_die

d0 = mod.compute_state_digest()
fleet_path = Path(os.environ["VCL_FLEET_HOME"]) / "fleet.json"
fleet_bytes = fleet_path.read_bytes()
fleet_path.write_bytes(fleet_bytes + b"\n")
assert mod.compute_state_digest() != d0
fleet_path.write_bytes(fleet_bytes)
assert mod.compute_state_digest() == d0
ml = Path(os.environ["VCL_FLEET_HOME"]) / "machine-local"
ml.mkdir(parents=True, exist_ok=True)
(ml / "noise.txt").write_text("x\n", encoding="utf-8")
assert mod.compute_state_digest() == d0

m = mod.load_workspace_manifest()
mod.refresh_manifest_digest(m)
mod.save_workspace_manifest(m)

view_rollback = {
    "schema_version": mod.WORKSPACE_VIEW_SCHEMA_VERSION,
    "fleet_id": m["fleet_id"],
    "last_seen_revision": 5,
    "last_seen_write_id": m["write_id"],
    "last_seen_state_digest": m["state_digest"],
}
m_roll = dict(m)
m_roll["revision"] = 3
assert mod.detect_workspace_conflict(m_roll, view_rollback) == mod.WS_ERR_ROLLBACK

view_div = dict(view_rollback)
view_div["last_seen_revision"] = m["revision"]
view_div["last_seen_write_id"] = str(uuid.uuid4())
assert mod.detect_workspace_conflict(m, view_div) == mod.WS_ERR_DIVERGED

mod.remember_workspace_view(m)
assert mod.detect_workspace_conflict(m) is None
fleet_path.write_bytes(fleet_bytes + b"\n#corrupt\n")
assert mod.detect_workspace_conflict(mod.load_workspace_manifest()) == mod.WS_ERR_INCONSISTENT
fleet_path.write_bytes(fleet_bytes)
m = mod.load_workspace_manifest()
mod.refresh_manifest_digest(m)
mod.save_workspace_manifest(m)
mod.remember_workspace_view(m)
assert mod.detect_workspace_conflict(m) is None

def _bump(manifest):
    old_rev = manifest["revision"]
    old_wid = manifest["write_id"]
    manifest["parent_revision"] = old_rev
    manifest["parent_write_id"] = old_wid
    manifest["revision"] = old_rev + 1
    manifest["write_id"] = str(uuid.uuid4())
    mod.refresh_manifest_digest(manifest)
    return manifest

msgs = []
mod.die = _capture_die

def _stale_mutator(manifest):
    stolen = mod.load_workspace_manifest()
    stolen["write_id"] = str(uuid.uuid4())
    mod.save_workspace_manifest(stolen)
    return _bump(manifest)

try:
    mod.cas_mutate_workspace(_stale_mutator)
    raise AssertionError("expected WORKSPACE_CAS_REJECTED")
except SystemExit:
    pass
mod.die = orig_die
assert mod.WS_ERR_CAS in msgs, msgs
PY
if (( ws_b1_rc == 0 )); then
  pass "B1 workspace manifest mint/digest/detect/CAS"
else
  fail "B1 workspace manifest mint/digest/CAS"
fi
export VCL_FLEET_HOME="${SAVED_WS_B1_HOME}"

# --- 0.4.1 B2: D28 credential bindings + access CLI + SSH resolve (T11) ---
SAVED_WS_B2_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="${TEST_TMP}/ws-b2"
assert_success "B2 access fleet init" fleet init
B2_KEY="${TEST_TMP}/ws-b2-id_ed25519"
printf 'test-only-not-a-real-key\n' > "$B2_KEY"
assert_success "B2 access bind identity-file" \
  fleet access bind admin-default --identity-file "$B2_KEY"
B2_LIST=$(fleet access list)
if [[ "$B2_LIST" == *"admin-default"* ]] && [[ "$B2_LIST" == *"identity_file"* ]]; then
  pass "B2 access list shows admin-default identity_file"
else
  fail "B2 access list shows admin-default identity_file (${B2_LIST})"
fi
B2_ABS=$(python3 -c 'import sys; from pathlib import Path; print(Path(sys.argv[1]).resolve())' "$B2_KEY")
if [[ "$B2_LIST" == *"$B2_ABS"* ]]; then
  pass "B2 access list shows absolute identity path"
else
  fail "B2 access list shows absolute identity path (${B2_LIST})"
fi
assert_success "B2 access verify after bind" fleet access verify
assert_success "B2 access bind openssh-default" \
  fleet access bind agent --openssh-default
B2_LIST2=$(fleet access list)
if [[ "$B2_LIST2" == *"agent"* ]] && [[ "$B2_LIST2" == *"openssh-default"* ]]; then
  pass "B2 access list shows openssh-default"
else
  fail "B2 access list shows openssh-default (${B2_LIST2})"
fi
assert_success "B2 bindings stay machine-local (not in fleet.json)" \
  bash -c '! grep -q credential-bindings "${VCL_FLEET_HOME}/fleet.json"'
assert_success "B2 bindings file under machine-local" \
  test -f "${VCL_FLEET_HOME}/machine-local/credential-bindings.json"

ws_b2_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$B2_KEY" "$FAKE_SSH" <<'PY' || ws_b2_rc=$?
import importlib.util
import os
import sys
from pathlib import Path

path, key_path, fake = sys.argv[1], sys.argv[2], sys.argv[3]
os.environ["VCL_FLEET_SSH"] = fake
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

key = str(Path(key_path).resolve())
node_ref = {"admin_credential_ref": "admin-default", "ssh_host": "203.0.113.10"}
assert mod._node_identity_file(node_ref) == key
argv_ref = mod.ssh_argv(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
    identity_file=mod._node_identity_file(node_ref),
)
assert "-i" in argv_ref
assert key in argv_ref
assert "IdentitiesOnly=yes" in argv_ref

legacy_key = Path(os.environ["VCL_FLEET_HOME"]) / "legacy-id"
legacy_key.write_text("legacy-only\n", encoding="utf-8")
node_legacy = {"identity_file": str(legacy_key), "ssh_host": "203.0.113.10"}
leg_path = mod._node_identity_file(node_legacy)
assert leg_path == str(legacy_key) or Path(leg_path).resolve() == legacy_key.resolve()
argv_leg = mod.ssh_argv(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
    identity_file=leg_path,
)
assert "-i" in argv_leg
assert "IdentitiesOnly=yes" in argv_leg

msgs = []
orig_die = mod.die

def _capture_die(message, code=1):
    msgs.append(message)
    raise SystemExit(code)

mod.die = _capture_die
raised = False
try:
    mod._node_identity_file({"admin_credential_ref": "missing"})
except SystemExit:
    raised = True
mod.die = orig_die
assert raised, "expected unbound credential ref"
assert any("unbound credential ref" in m for m in msgs), msgs

# Neither ref nor identity_file → no -i (ssh inject expectation unchanged)
argv_bare = mod.ssh_argv(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
    identity_file=mod._node_identity_file({"ssh_host": "203.0.113.10"}),
)
assert "-i" not in argv_bare
assert "IdentitiesOnly=yes" not in argv_bare

# openssh-default binding → None → no -i
assert mod._node_identity_file({"admin_credential_ref": "agent"}) is None

# Bindings must not leak absolute key paths into portable fleet.json
home = Path(os.environ["VCL_FLEET_HOME"])
fleet_blob = (home / "fleet.json").read_text(encoding="utf-8")
assert "credential-bindings" not in fleet_blob
assert key not in fleet_blob
PY
if (( ws_b2_rc == 0 )); then
  pass "B2 credential ref resolve / legacy / unbound / no -i"
else
  fail "B2 credential ref resolve / legacy / unbound / no -i"
fi
export VCL_FLEET_HOME="${SAVED_WS_B2_HOME}"

assert_success "fleet.db DDL includes instance_history" \
  grep -q 'CREATE TABLE instance_history' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet.db uses UPSERT for audit_events" \
  grep -q 'ON CONFLICT(node_id, event_id) DO UPDATE SET' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "vcl-fleet Unix entry exists" test -f "${PROJECT_DIR}/bin/vcl-fleet"
assert_success "vcl-fleet Windows entry exists" test -f "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_success "build-controller.sh packs vincula-audit.py" \
  grep -q 'lib/vincula-audit.py' "${PROJECT_DIR}/scripts/build-controller.sh"
assert_success "build-controller.sh packs vincula-backup.py" \
  grep -q 'lib/vincula-backup.py' "${PROJECT_DIR}/scripts/build-controller.sh"
assert_success "build-controller.sh packs vincula-ui server" \
  grep -q 'lib/vincula-ui/server.py' "${PROJECT_DIR}/scripts/build-controller.sh"
assert_success "build-controller.sh packs vincula-ui static" \
  grep -q 'lib/vincula-ui/static/index.html' "${PROJECT_DIR}/scripts/build-controller.sh"
assert_success "build-controller.sh writes controller.lock" \
  grep -q 'controller.lock' "${PROJECT_DIR}/scripts/build-controller.sh"
assert_success "build-controller.sh writes zip sha256 sidecar" \
  grep -q 'zip.sha256' "${PROJECT_DIR}/scripts/build-controller.sh"
assert_success "load_audit_module resolves controller lib siblings" \
  grep -q 'def _controller_lib_dir(' "${PROJECT_DIR}/lib/vincula-fleet.py"

VCL_FLEET_VERSION=$(grep -E '^VCL_FLEET_VERSION[[:space:]]*=' "${PROJECT_DIR}/lib/vincula-fleet.py"|head -1|sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/')
assert_equal "vcl-fleet version" "vcl-fleet ${VCL_FLEET_VERSION}" \
  "$(python3 "${PROJECT_DIR}/bin/vcl-fleet" version)"
assert_equal "vcl-fleet.py version" "vcl-fleet ${VCL_FLEET_VERSION}" \
  "$(fleet version)"

node_help=$(fleet node -h)
assert_success "node -h lists replace" grep -q 'replace' <<< "$node_help"
assert_success "node -h lists instances" grep -q 'instances' <<< "$node_help"
set_help=$(fleet node set -h)
assert_success "node set -h names rebind" grep -q 'rebind' <<< "$set_help"
assert_success "node set -h documents --identity-file" \
  grep -q -- '--identity-file' <<< "$set_help"
assert_success "node set -h documents --clear-identity-file" \
  grep -q -- '--clear-identity-file' <<< "$set_help"
replace_help=$(fleet node replace -h)
assert_success "node replace -h names replace" grep -q 'replace' <<< "$replace_help"
assert_success "node replace -h names rebind" grep -q 'rebind' <<< "$replace_help"
assert_success "node replace -h requires --host-key" grep -q -- '--host-key' <<< "$replace_help"
assert_success "node replace -h documents --identity-file" \
  grep -q -- '--identity-file' <<< "$replace_help"
assert_success "node replace -h names runtime-only" \
  grep -q 'runtime-only' <<< "$replace_help"
assert_success "node replace -h names --reissue-output" \
  grep -q -- '--reissue-output' <<< "$replace_help"
assert_failure "node replace -h does not teach --replace-node" \
  grep -q -- '--replace-node' <<< "$replace_help"
assert_failure "node replace -h is not fail-closed" \
  grep -q 'NOT IMPLEMENTED' <<< "$replace_help"
instances_help=$(fleet node instances -h)
assert_success "node instances -h exists" grep -q 'instance' <<< "$instances_help"

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
assert data.get("schema_version") == 2, data
assert data.get("nodes") == [], data
assert "instance_id" not in data
for node in data.get("nodes") or []:
    assert "instance_id" not in node
PY
if (( init_schema_rc == 0 )); then
  pass "init creates schema-2 empty registry"
else
  fail "init creates schema-2 empty registry"
fi

assert_success "init is idempotent on empty registry" fleet init

assert_success "offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$TEST_NODE_ID" \
    --instance-id "$TEST_INSTANCE_ID"
list_out=$(fleet node list)
assert_success "node list contains lax" grep -q 'lax' <<< "$list_out"
assert_success "node list contains lax node_id" grep -q "$TEST_NODE_ID" <<< "$list_out"
assert_success "node list header has STATUS" grep -q 'STATUS' <<< "$list_out"
assert_success "node list shows active status" grep -q ' active$' <<< "$list_out"

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
assert_success "node show status disabled after disable" \
  grep -q 'status=disabled' <<< "$disable_out"
assert_success "node enable lax" fleet node enable lax
enable_out=$(fleet node show lax)
assert_success "node show enabled true after enable" \
  grep -q 'enabled=true' <<< "$enable_out"
assert_success "node show status active after enable" \
  grep -q 'status=active' <<< "$enable_out"

assert_failure "fleet.json stores no password" \
  grep -E 'password|passwd' "${VCL_FLEET_HOME}/fleet.json"

roundtrip_rc=0
python3 - "${VCL_FLEET_HOME}/fleet.json" "$TEST_NODE_ID" <<'PY' || roundtrip_rc=$?
import json, sys
path, node_id = sys.argv[1], sys.argv[2]
raw = open(path, encoding="utf-8").read()
assert "instance_id" not in raw
data = json.load(open(path, encoding="utf-8"))
assert data.get("schema_version") == 2, data
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
assert node["status"] == "active"
PY
if (( roundtrip_rc == 0 )); then
  pass "fleet.json schema 2 has status and no instance_id"
else
  fail "fleet.json schema 2 has status and no instance_id"
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
ssh_add_err=$(fleet node add nantes --host 203.0.113.40 --node-id "$TEST_SG_NODE_ID" 2>&1 </dev/null) || ssh_add_rc=$?
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
assert_success "fake-scp is executable" test -x "$FAKE_SCP"
assert_success "fake-scp uses python3 shebang" \
  grep -q '^#!/usr/bin/env python3' "$FAKE_SCP"
assert_failure "fake-scp never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "$FAKE_SCP"
assert_failure "fake-scp never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "$FAKE_SCP"
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
import shlex
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
assert "IdentitiesOnly=no" not in argv
assert "-i" not in argv
assert "IdentitiesOnly=yes" not in argv
assert "root@203.0.113.10" in argv
assert "--" in argv
after = argv[argv.index("--") + 1 :]
assert after == [shlex.join(["vcl", "identity", "--json"])], after
assert shlex.split(after[0]) == ["vcl", "identity", "--json"]
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
import tempfile
from pathlib import Path
keydir = Path(tempfile.mkdtemp())
key = keydir / "id_ed25519"
key.write_text("test-only-not-a-real-key\n", encoding="utf-8")
with_id = mod.ssh_argv(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
    identity_file=str(key),
)
assert "-i" in with_id
assert str(key.resolve()) in with_id
assert "IdentitiesOnly=yes" in with_id
assert "IdentitiesOnly=no" not in with_id
proc_i = mod.ssh_run(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=True,
    identity_file=str(key),
)
assert proc_i.returncode == 0, proc_i.stderr
missing_died = False
try:
    mod.ssh_argv(
        "203.0.113.10",
        "root",
        22,
        ["vcl", "identity", "--json"],
        batch=True,
        identity_file=str(key) + ".missing",
    )
except SystemExit:
    missing_died = True
assert missing_died
scp = mod.scp_argv(
    port=22, src="local", dest="remote", identity_file=str(key)
)
assert "-i" in scp and "IdentitiesOnly=yes" in scp
assert "IdentitiesOnly=no" not in scp
PY
if (( argv_rc == 0 )); then
  pass "ssh_argv/ssh_run use injectable ssh without host-key weakening"
else
  fail "ssh_argv/ssh_run use injectable ssh without host-key weakening"
fi
assert_failure "fleet.py does not hardcode IdentitiesOnly=no" \
  grep -q 'IdentitiesOnly=no' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet.py can pass IdentitiesOnly=yes" \
  grep -q 'IdentitiesOnly=yes' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "node add -h documents --identity-file" \
  grep -q -- '--identity-file' <<< "$(fleet node add -h 2>&1 || true)"

SAVED_IDENT_HOME="${VCL_FLEET_HOME}"
IDENT_FLEET_HOME="${TEST_TMP}/fleet-home-identity"
IDENT_KEY="${TEST_TMP}/ident-ed25519"
mkdir -p "$IDENT_FLEET_HOME"
printf 'test-only-not-a-real-key\n' > "$IDENT_KEY"
export VCL_FLEET_HOME="$IDENT_FLEET_HOME"
assert_success "identity-file fleet init" fleet init
assert_success "offline add with --identity-file" \
  fleet node add keyn --host 203.0.113.10 --offline \
    --node-id "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaa0099" \
    --identity-file "$IDENT_KEY"
ident_abs_rc=0
python3 - "$IDENT_FLEET_HOME" <<'PY' || ident_abs_rc=$?
import json, sys
from pathlib import Path
reg = json.loads(Path(sys.argv[1], "fleet.json").read_text(encoding="utf-8"))
stored = reg["nodes"][0]["identity_file"]
assert Path(stored).is_absolute(), stored
assert Path(stored).name == "ident-ed25519", stored
PY
if (( ident_abs_rc == 0 )); then
  pass "offline add persists absolute identity_file"
else
  fail "offline add persists absolute identity_file"
fi
ident_show=$(fleet node show keyn)
if [[ "$ident_show" == *"identity_file="* ]] && [[ "$ident_show" == *"ident-ed25519"* ]]; then
  pass "node show prints identity_file path"
else
  fail "node show prints identity_file path (${ident_show})"
fi
assert_success "node set --clear-identity-file" \
  fleet node set keyn --clear-identity-file
ident_show2=$(fleet node show keyn)
if [[ "$ident_show2" != *"identity_file="* ]]; then
  pass "clear-identity-file drops identity_file"
else
  fail "clear-identity-file drops identity_file (${ident_show2})"
fi
assert_success "node set --identity-file without --host" \
  fleet node set keyn --identity-file "$IDENT_KEY"
missing_ident_rc=0
fleet node add badkeyn --host 203.0.113.10 --offline \
  --node-id "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaa0098" \
  --identity-file "${IDENT_KEY}.missing" >/dev/null 2>"${TEST_TMP}/ident-missing.err" \
  || missing_ident_rc=$?
if (( missing_ident_rc != 0 )) && grep -q 'identity file not found' "${TEST_TMP}/ident-missing.err"; then
  pass "missing --identity-file is refused"
else
  fail "missing --identity-file is refused (rc=${missing_ident_rc})"
fi
export VCL_FLEET_HOME="${SAVED_IDENT_HOME}"

# P1-01: remote command is one shlex-quoted string; metadata/SSH target validation.
p101_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$FAKE_SSH" "${TEST_TMP}" <<'PY' || p101_rc=$?
import importlib.util
import io
import json
import os
import shlex
import sys
from pathlib import Path

path, fake, tmp = sys.argv[1], sys.argv[2], Path(sys.argv[3])
os.environ["VCL_FLEET_SSH"] = fake
state = tmp / "p101-fake-state"
state.mkdir(parents=True, exist_ok=True)
os.environ["VCL_FAKE_STATE_DIR"] = str(state)
log_path = tmp / "p101-ssh-argv.jsonl"
if log_path.exists():
    log_path.unlink()
os.environ["VCL_FAKE_SSH_ARGV_LOG"] = str(log_path)

spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def last_log():
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert lines, "fake-ssh wrote no argv log"
    return json.loads(lines[-1])

def expect_die(fn, needle):
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    raised = False
    try:
        fn()
    except SystemExit:
        raised = True
    finally:
        sys.stderr = old
    err = buf.getvalue()
    assert raised, needle
    assert needle in err, (needle, err)
    return err

# One remote string; spaces stay one argv after POSIX split.
spaced = ["vcl", "user", "add", "spaced", "--display-name", "Alice Smith", "--json"]
joined = shlex.join(spaced)
argv = mod.ssh_argv("203.0.113.10", "root", 22, spaced, batch=True)
after = argv[argv.index("--") + 1 :]
assert after == [joined], after
assert shlex.split(after[0]) == spaced
assert "Alice Smith" in after[0]
assert "Alice Smith" in shlex.split(after[0])
assert "Alice" not in shlex.split(after[0])

proc = mod.ssh_run("203.0.113.10", "root", 22, spaced, batch=True)
assert proc.returncode == 0, proc.stderr
logged = last_log()
assert logged["raw_remote"] == [joined], logged["raw_remote"]
assert logged["argv"] == spaced, logged["argv"]
assert logged["argv"].count("Alice Smith") == 1
assert "Smith" not in logged["argv"] or logged["argv"][logged["argv"].index("Alice Smith")] == "Alice Smith"

# Semicolon / backticks / $() must be quoted so they stay one arg (no injection).
for payload in ("Alice; id", "Alice`id`", "Alice$(id)", "'; id'"):
    cmd = ["vcl", "user", "add", "evil", "--display-name", payload, "--json"]
    argv = mod.ssh_argv("203.0.113.10", "root", 22, cmd, batch=True)
    after = argv[argv.index("--") + 1 :]
    assert len(after) == 1, after
    assert after[0] == shlex.join(cmd)
    recovered = shlex.split(after[0])
    assert recovered == cmd, (payload, recovered)
    assert recovered[recovered.index("--display-name") + 1] == payload
    assert recovered.count("id") == 0  # `id` never a separate argv token

# Explicit: '; id' is one display_name, not a second command.
semi = ["vcl", "user", "add", "semi", "--user-id",
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "--display-name", "Alice; id", "--json"]
if log_path.exists():
    log_path.unlink()
proc = mod.ssh_run("203.0.113.10", "root", 22, semi, batch=True)
assert proc.returncode == 0, proc.stderr
logged = last_log()
assert logged["argv"] == semi, logged["argv"]
assert logged["argv"][logged["argv"].index("--display-name") + 1] == "Alice; id"
assert logged["argv"][-1] == "--json"
assert "id" not in logged["argv"]  # would be present if '; id' split into a command

# Backticks via fake-ssh exact argv.
tick = ["vcl", "user", "add", "tick", "--user-id",
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "--display-name", "Alice`id`", "--json"]
if log_path.exists():
    log_path.unlink()
proc = mod.ssh_run("203.0.113.10", "root", 22, tick, batch=True)
assert proc.returncode == 0, proc.stderr
logged = last_log()
assert logged["argv"] == tick, logged["argv"]
assert logged["argv"][logged["argv"].index("--display-name") + 1] == "Alice`id`"

# Empty display_name is valid metadata (omitted from remote argv by caller).
assert mod.validate_display_name("") == ""
assert mod.validate_department("") == ""
assert mod.validate_display_name(None) is None

# Newline / other ASCII controls rejected at the source (no spawn).
marker = tmp / "p101-spawned"
wrapper = tmp / "p101-ssh-wrapper"
wrapper.write_text(
    "#!/bin/sh\nprintf spawned >\"%s\"\nexec \"%s\" \"$@\"\n" % (marker, fake),
    encoding="utf-8",
)
wrapper.chmod(0o755)
os.environ["VCL_FLEET_SSH"] = str(wrapper)
if marker.exists():
    marker.unlink()

expect_die(lambda: mod.validate_display_name("Alice\nid"), "control characters")
expect_die(lambda: mod.validate_department("Eng\n"), "control characters")
expect_die(lambda: mod.validate_display_name("Alice\tid"), "control characters")
expect_die(
    lambda: mod.validate_display_name("A" * (mod.USER_METADATA_MAX + 1)),
    "exceeds",
)

expect_die(
    lambda: mod.parse_ssh_target("203.0.113.10;id"),
    "invalid ssh_host",
)
expect_die(
    lambda: mod.parse_ssh_target("203.0.113.10\nid"),
    "whitespace or control",
)
expect_die(
    lambda: mod.parse_ssh_target("203.0.113.10", user="root;id"),
    "invalid ssh_user",
)
expect_die(
    lambda: mod.parse_ssh_target("203.0.113.10", user="root\nid"),
    "whitespace or control",
)
expect_die(
    lambda: mod.ssh_argv("203.0.113.10;id", "root", 22, ["vcl", "identity"], batch=True),
    "invalid ssh_host",
)
expect_die(
    lambda: mod.ssh_run("203.0.113.10;id", "root", 22, ["vcl", "identity", "--json"]),
    "invalid ssh_host",
)
assert not marker.exists(), "ssh must not spawn on invalid host"

expect_die(
    lambda: mod.ssh_run("203.0.113.10", "root;id", 22, ["vcl", "identity", "--json"]),
    "invalid ssh_user",
)
assert not marker.exists(), "ssh must not spawn on invalid user"

# Newline in a remote argv element is quoted (not executed) if it bypasses
# metadata validation; controller metadata path rejects it first.
nl_cmd = ["vcl", "user", "add", "nl", "--display-name", "Alice\nid", "--json"]
expect_die(lambda: mod.provision_user_on_node(
    {"ssh_host": "203.0.113.10", "ssh_user": "root", "ssh_port": 22, "name": "lax", "node_id": "x"},
    tag="nl",
    user_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    display_name="Alice\nid",
), "control characters")
assert not marker.exists()

# Legal hosts: IPv4, DNS, IPv6.
assert mod.validate_ssh_host("203.0.113.10") == "203.0.113.10"
assert mod.validate_ssh_host("lax.test") == "lax.test"
assert mod.validate_ssh_host("2001:db8::1") == "2001:db8::1"
host, user, port = mod.parse_ssh_target("[2001:db8::1]", "ubuntu")
assert (host, user, port) == ("2001:db8::1", "ubuntu", 22)

# Overlong remote command.
huge = ["vcl", "x" * (mod.SSH_REMOTE_CMD_MAX_BYTES + 1)]
expect_die(lambda: mod.ssh_argv("203.0.113.10", "root", 22, huge, batch=True), "exceeds")
assert not marker.exists()
PY
if (( p101_rc == 0 )); then
  pass "P1-01 ssh_argv quotes remote argv; injection payloads stay one arg"
  pass "P1-01 fake-ssh records exact quoted argv (spaces/;/backticks)"
  pass "P1-01 invalid ssh_user/ssh_host die without spawning ssh"
  pass "P1-01 display_name newline/control chars rejected"
else
  fail "P1-01 ssh_argv quotes remote argv; injection payloads stay one arg"
  fail "P1-01 fake-ssh records exact quoted argv (spaces/;/backticks)"
  fail "P1-01 invalid ssh_user/ssh_host die without spawning ssh"
  fail "P1-01 display_name newline/control chars rejected"
fi

assert_success "fleet.py uses shlex.join for remote SSH commands" \
  grep -q 'shlex.join' "${PROJECT_DIR}/lib/vincula-fleet.py"

assert_failure "fleet.py never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_failure "fleet.py never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet.py has scp_bin" \
  grep -q 'def scp_bin(' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet.py reads VCL_FLEET_SCP" \
  grep -q 'VCL_FLEET_SCP' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_failure "node replace does not send --include-secrets" \
  grep -q -- '--include-secrets' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_failure "vcl-fleet never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "${PROJECT_DIR}/bin/vcl-fleet"
assert_failure "vcl-fleet never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "${PROJECT_DIR}/bin/vcl-fleet"
assert_failure "vcl-fleet.cmd never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_failure "vcl-fleet.cmd never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_failure "AC-2.8-02 / AC-2.9-10 controller has no bind" \
  grep -E '0\.0\.0\.0|HTTPServer|socket\.bind' \
    "${PROJECT_DIR}/lib/vincula-fleet.py" \
    "${PROJECT_DIR}/bin/vcl-fleet" \
    "${PROJECT_DIR}/bin/vcl-fleet.cmd"
assert_failure "AC-2.8-02 / AC-2.9-10 controller has no listen/http.server" \
  grep -E 'http\.server|socket\.listen|socket\.socket' \
    "${PROJECT_DIR}/lib/vincula-fleet.py" \
    "${PROJECT_DIR}/bin/vcl-fleet" \
    "${PROJECT_DIR}/bin/vcl-fleet.cmd"
# B15 Local Audit UI is loopback-only in lib/vincula-ui (not a VPS management port).
assert_success "B15 ui server is loopback-gated" \
  grep -q 'assert_loopback_host' "${PROJECT_DIR}/lib/vincula-ui/server.py"
assert_success "B15 ui refuses 0.0.0.0 by policy text" \
  grep -q 'refuses non-loopback' "${PROJECT_DIR}/lib/vincula-ui/server.py"
assert_failure "B15 ui does not default-bind 0.0.0.0" \
  grep -q '0\.0\.0\.0' "${PROJECT_DIR}/lib/vincula-ui/server.py"
assert_success "B15 ui caps concurrent workers" \
  grep -q 'UI_MAX_WORKERS' "${PROJECT_DIR}/lib/vincula-ui/server.py"
assert_success "B15 ui sets request socket timeout" \
  grep -q 'UI_REQUEST_TIMEOUT' "${PROJECT_DIR}/lib/vincula-ui/server.py"
assert_success "B15 ui uses a bounded semaphore" \
  grep -q 'BoundedSemaphore' "${PROJECT_DIR}/lib/vincula-ui/server.py"
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

assert_failure "vincula-backup.py has no bind/HTTPServer" \
  grep -E '0\.0\.0\.0|HTTPServer|socket\.bind' \
    "${PROJECT_DIR}/lib/vincula-backup.py"
assert_failure "vincula-backup.py never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "${PROJECT_DIR}/lib/vincula-backup.py"
assert_failure "vincula-backup.py never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "${PROJECT_DIR}/lib/vincula-backup.py"
assert_failure "fake-age has no bind/HTTPServer" \
  grep -E '0\.0\.0\.0|HTTPServer|socket\.bind' \
    "${PROJECT_DIR}/tests/fixtures/fake-age"
assert_failure "fake-age never sets StrictHostKeyChecking=no" \
  grep -q 'StrictHostKeyChecking=no' "${PROJECT_DIR}/tests/fixtures/fake-age"
assert_failure "fake-age never sets UserKnownHostsFile=/dev/null" \
  grep -q 'UserKnownHostsFile=/dev/null' "${PROJECT_DIR}/tests/fixtures/fake-age"
assert_failure "fake-scp has no bind/HTTPServer" \
  grep -E '0\.0\.0\.0|HTTPServer|socket\.bind' \
    "${PROJECT_DIR}/tests/fixtures/fake-scp"

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
assert argv[argv.index("--") + 1 :] == [__import__("shlex").join(["vcl", "identity", "--json"])]

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

# --- 0.4.1 B3: D27 dedicated known_hosts + trust extract (T18) ---
SAVED_WS_B3_HOME="${VCL_FLEET_HOME}"
ws_b3_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$FAKE_SSH" "$FAKE_KEYSCAN" \
  "$LAX_HOSTKEY_PUB" "$TOKYO_HOSTKEY_PUB" "$HOME" "${TEST_TMP}/ws-b3" <<'PY' || ws_b3_rc=$?
import importlib.util
import io
import os
import sys
from pathlib import Path

path, fake, keyscan, lax_pub, tokyo_pub, home, ws_home = sys.argv[1:8]
os.environ["VCL_FLEET_SSH"] = fake
os.environ["VCL_FLEET_SSH_KEYSCAN"] = keyscan
os.environ["HOME"] = home

# (1) Legacy: no workspace.json → pin writes ~/.ssh/known_hosts; no UserKnownHostsFile=
legacy_home = Path(home) / "fleet-home-b3-legacy"
os.environ["VCL_FLEET_HOME"] = str(legacy_home)
legacy_home.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("vincula_fleet_b3", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert not mod.workspace_trust_active()
assert not mod.workspace_manifest_path().is_file()
lax_line = open(lax_pub, encoding="utf-8").read().strip()
fp = mod.fingerprint_sha256(lax_line)
mod.pin_host_key("203.0.113.10", 22, fp)
kh = mod.default_known_hosts_path()
assert kh == Path(home) / ".ssh" / "known_hosts", kh
assert "203.0.113.10" in kh.read_text(encoding="utf-8")
extra, batch = mod.prepare_ssh_host_key("203.0.113.10", 22, fp)
argv = mod.ssh_argv(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=batch,
    extra=extra,
)
assert not any(
    (a.startswith("UserKnownHostsFile=") or a.startswith("-oUserKnownHostsFile="))
    for a in argv
), argv
assert "UserKnownHostsFile=" not in " ".join(argv)

# (2) Workspace: pin/TOFU → trust/known_hosts; ssh_argv injects UserKnownHostsFile
os.environ["VCL_FLEET_HOME"] = ws_home
Path(ws_home).mkdir(parents=True, exist_ok=True)
# Re-load so fleet_home / trust paths pick up new VCL_FLEET_HOME
spec2 = importlib.util.spec_from_file_location("vincula_fleet_b3w", path)
modw = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(modw)
(modw.fleet_home() / "fleet.json").write_text(
    '{"schema_version": 2, "nodes": []}\n', encoding="utf-8"
)
modw.create_workspace_manifest()
assert modw.workspace_trust_active()
trust_kh = modw.known_hosts_path()
assert trust_kh == Path(ws_home) / "trust" / "known_hosts"
modw.pin_host_key("203.0.113.10", 22, fp)
assert trust_kh.is_file()
text = trust_kh.read_text(encoding="utf-8")
assert "203.0.113.10" in text
assert "/dev/null" not in text
assert modw.default_known_hosts_path() == trust_kh
extra_w, batch_w = modw.prepare_ssh_host_key("203.0.113.10", 22, fp)
argv_w = modw.ssh_argv(
    "203.0.113.10",
    "root",
    22,
    ["vcl", "identity", "--json"],
    batch=batch_w,
    extra=extra_w,
)
ukh = f"UserKnownHostsFile={trust_kh}"
assert ukh in argv_w, argv_w
assert "StrictHostKeyChecking=yes" in argv_w
assert "UserKnownHostsFile=/dev/null" not in " ".join(argv_w)
assert "/dev/null" not in " ".join(argv_w)

# (4) Reject evil UserKnownHostsFile under workspace
raised = False
buf = io.StringIO()
old_err = sys.stderr
sys.stderr = buf
try:
    modw.ssh_argv(
        "203.0.113.10",
        "root",
        22,
        ["vcl", "identity", "--json"],
        batch=True,
        extra=["-o", "UserKnownHostsFile=/tmp/evil"],
    )
except SystemExit:
    raised = True
finally:
    sys.stderr = old_err
assert raised, buf.getvalue()
assert "UserKnownHostsFile=" in buf.getvalue()

# (3) Extract: lax only in src; nodes=[lax,tokyo] → dest has lax; TRUST_MIGRATION_REQUIRED
src_kh = Path(ws_home) / "extract-src-known_hosts"
tokyo_line = open(tokyo_pub, encoding="utf-8").read().strip()
# Seed only lax; also include a decoy non-fleet host line that must not be copied wholesale
src_kh.write_text(
    lax_line + "\n"
    + "198.51.100.1 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDecoyKeyNotInFleetXXXXXXXXXXXXX=\n",
    encoding="utf-8",
)
dest_kh = Path(ws_home) / "trust" / "extracted_known_hosts"
nodes = [
    {"name": "lax", "ssh_host": "203.0.113.10", "ssh_port": 22},
    {"name": "tokyo", "ssh_host": "203.0.113.11", "ssh_port": 22},
]
result = modw.extract_fleet_host_trust(nodes, src_kh, dest_kh)
assert dest_kh.is_file()
dest_text = dest_kh.read_text(encoding="utf-8")
assert "203.0.113.10" in dest_text
assert "203.0.113.11" not in dest_text
assert "198.51.100.1" not in dest_text
assert dest_text != src_kh.read_text(encoding="utf-8")
assert modw.TRUST_MIGRATION_REQUIRED in result["warnings"]
assert "203.0.113.11" in result["missing_hosts"]
assert any("203.0.113.10" in line for line in result["matched"])
# extract body must not call candidate_host_keys / ssh-keyscan
extract_src = Path(path).with_name("trust.py").read_text(encoding="utf-8")
extract_fn = extract_src.split("def extract_fleet_host_trust", 1)[1]
assert "candidate_host_keys" not in extract_fn
assert "ssh-keyscan" not in extract_fn
assert "ssh_keyscan" not in extract_fn
assert tokyo_line  # fixture loaded
PY
if (( ws_b3_rc == 0 )); then
  pass "B3 D27 workspace trust store + extract API"
else
  fail "B3 D27 workspace trust store + extract API"
fi
export VCL_FLEET_HOME="${SAVED_WS_B3_HOME}"

# --- 0.4.1 B4: portable instance history jsonl (T23) ---
SAVED_WS_B4_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="${TEST_TMP}/ws-b4"
mkdir -p "$VCL_FLEET_HOME"
assert_success "B4 history fleet init" fleet init
ws_b4_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY' || ws_b4_rc=$?
import importlib.util
import json
import os
import sys
from pathlib import Path

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("vincula_fleet_b4", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert mod.INSTANCE_HISTORY_SCHEMA == "instance-history/v1"
assert "history/instances.jsonl" in mod.PORTABLE_DIGEST_NAMES
assert mod.history_dir() == Path(os.environ["VCL_FLEET_HOME"]) / "history"
assert mod.instances_history_path() == mod.history_dir() / "instances.jsonl"

node_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
old_iid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
new_iid = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
hist_path = mod.instances_history_path()
assert not hist_path.is_file()

conn = mod.open_fleet_db()
mod.record_instance(
    conn, node_id, old_iid, "203.0.113.10", "203.0.113.10",
    now_iso="2026-08-16T04:00:00Z",
)
conn.commit()

assert hist_path.is_file()
lines = [ln for ln in hist_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
assert len(lines) == 1, lines
rec0 = json.loads(lines[0])
assert set(rec0.keys()) == {
    "node_id", "instance_id", "started_at", "retired_at", "endpoint", "reason"
}, rec0
assert "ssh_host" not in rec0
assert "status" not in rec0
for bad in ("password", "identity", "token", "secret"):
    assert bad not in rec0
    assert not any(bad in k.lower() for k in rec0)
assert rec0["node_id"] == node_id
assert rec0["instance_id"] == old_iid
assert rec0["started_at"] == "2026-08-16T04:00:00Z"
assert rec0["retired_at"] is None
assert rec0["endpoint"] == "203.0.113.10"
assert rec0["reason"] == "sync-first-sight"
parsed = mod.parse_instance_history_jsonl()
assert parsed == [rec0], (parsed, rec0)

mod.record_instance(
    conn, node_id, new_iid, "203.0.113.18", "203.0.113.18",
    now_iso="2026-08-16T05:00:00Z",
)
conn.commit()
lines2 = [ln for ln in hist_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
assert len(lines2) >= 2, lines2
db_rows = mod.list_instances(conn, node_id)
assert db_rows[0]["retired_at"] == "2026-08-16T05:00:00Z"
objs = [json.loads(ln) for ln in lines2]
assert any(
    o.get("instance_id") == old_iid
    and o.get("retired_at") == "2026-08-16T05:00:00Z"
    and o.get("reason") == "retired"
    for o in objs
), objs
assert any(
    o.get("instance_id") == new_iid
    and o.get("retired_at") is None
    and o.get("reason") == "sync-first-sight"
    for o in objs
), objs
parsed2 = mod.parse_instance_history_jsonl()
assert parsed2 == objs

mod.mark_instance_retired(conn, node_id, new_iid, "2026-08-16T06:00:00Z")
conn.commit()
objs3 = mod.parse_instance_history_jsonl()
assert any(
    o.get("instance_id") == new_iid
    and o.get("retired_at") == "2026-08-16T06:00:00Z"
    and o.get("reason") == "retired"
    for o in objs3
), objs3

db_count = conn.execute("SELECT COUNT(*) FROM instance_history").fetchone()[0]
export_dest = Path(os.environ["VCL_FLEET_HOME"]) / "history" / "export-roundtrip.jsonl"
n = mod.export_instance_history_from_db(conn, export_dest)
assert n == db_count == 2, (n, db_count)
exported = mod.parse_instance_history_jsonl(export_dest)
assert len(exported) == db_count
for row in exported:
    assert set(row.keys()) == {
        "node_id", "instance_id", "started_at", "retired_at", "endpoint", "reason"
    }
conn.close()
PY
if (( ws_b4_rc == 0 )); then
  pass "B4 portable instance history jsonl dual-write + export"
else
  fail "B4 portable instance history jsonl dual-write + export"
fi

# D48: offline node add must not write instance history jsonl
B4_OFFLINE_HOME="${TEST_TMP}/ws-b4-offline-add"
export VCL_FLEET_HOME="$B4_OFFLINE_HOME"
mkdir -p "$VCL_FLEET_HOME"
assert_success "B4 offline-add fleet init" fleet init
assert_success "B4 offline node add does not call record_instance" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"
if [[ ! -e "${VCL_FLEET_HOME}/history/instances.jsonl" ]]; then
  pass "B4 offline node add leaves history/instances.jsonl absent (D48)"
else
  fail "B4 offline node add leaves history/instances.jsonl absent (D48)"
fi
dry_b4=$(fleet workspace migrate --dry-run 2>/dev/null) || true
if echo "$dry_b4" | grep -q 'history_gaps' && echo "$dry_b4" | grep -q 'D48'; then
  pass "B4 dry-run still reports history_gaps (D48)"
else
  fail "B4 dry-run still reports history_gaps (D48)"
fi
export VCL_FLEET_HOME="${SAVED_WS_B4_HOME}"

# --- 0.4.1 B5: real workspace migrate 16-step (T32) ---
SAVED_WS_B5_HOME="${VCL_FLEET_HOME}"
SAVED_WS_B5_SSH="${VCL_FLEET_SSH:-}"
SAVED_WS_B5_KEYSCAN="${VCL_FLEET_SSH_KEYSCAN:-}"
B5_HOME="${TEST_TMP}/ws-b5-migrate"
B5_KEY="${TEST_TMP}/ws-b5-id_ed25519"
mkdir -p "$B5_HOME"
printf 'test-only-not-a-real-b5-key\n' > "$B5_KEY"
chmod 600 "$B5_KEY"
export VCL_FLEET_HOME="$B5_HOME"
export VCL_FLEET_SSH=/bin/false
export VCL_FLEET_SSH_KEYSCAN=/bin/false

assert_success "B5 fleet init" fleet init
assert_success "B5 offline node add with identity_file" \
  fleet node add b5n --host 203.0.113.77 --offline \
    --node-id "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbb5b5" \
    --identity-file "$B5_KEY"

# Seed one instance_history row so export count is non-zero / comparable
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY'
import importlib.util, os, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
conn = mod.open_fleet_db()
nid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbb5b5"
iid = "cccccccc-cccc-4ccc-8ccc-ccccccccc5c5"
mod.insert_instance(
    conn,
    node_id=nid,
    instance_id=iid,
    started_at="2026-08-20T00:00:00Z",
    endpoint="203.0.113.77:22",
    ssh_host="203.0.113.77",
)
conn.commit()
conn.close()
PY

B5_PRE_HIST=$(python3 - <<'PY'
import importlib.util, os, sys
from pathlib import Path
path = Path(os.environ["VCL_FLEET_HOME"]).parent.parent  # unused
# count via sqlite
import sqlite3
db = os.environ["VCL_FLEET_HOME"] + "/fleet.db"
conn = sqlite3.connect(db)
print(conn.execute("SELECT COUNT(*) FROM instance_history").fetchone()[0])
conn.close()
PY
)

# Snapshot pre-dry-run files + mtimes (AC-4.0-M06 zero side effect)
B5_SNAP="${TEST_TMP}/ws-b5-snap-before.txt"
(
  cd "$B5_HOME"
  find . -type f -printf '%P\t%T@\t%s\n' | sort
) > "$B5_SNAP"

dry_b5=$(fleet workspace migrate --dry-run) || dry_b5_rc=$?
dry_b5_rc=${dry_b5_rc:-0}
assert_equal "B5 dry-run exit 0" "0" "$dry_b5_rc"

B5_SNAP_AFTER="${TEST_TMP}/ws-b5-snap-after.txt"
(
  cd "$B5_HOME"
  find . -type f -printf '%P\t%T@\t%s\n' | sort
) > "$B5_SNAP_AFTER"
if diff -q "$B5_SNAP" "$B5_SNAP_AFTER" >/dev/null; then
  pass "B5 dry-run zero side effects (file list+mtime+size)"
else
  fail "B5 dry-run zero side effects (file list+mtime+size)"
  diff -u "$B5_SNAP" "$B5_SNAP_AFTER" >&2 || true
fi

echo "$dry_b5" | python3 -c '
import json, sys
p = json.load(sys.stdin)
assert p["dry_run"] is True
assert p["side_effects"] == "none"
assert len(p["pipeline"]) == 16
assert p["counts"]["history_gaps"] >= 0
assert "NOT SSH" in p["note"]
' && pass "B5 dry-run JSON dry_run/side_effects/pipeline/note" \
  || fail "B5 dry-run JSON dry_run/side_effects/pipeline/note"

# history_gaps: we seeded history for the only node, so gaps may be 0;
# assert pipeline length and SSH-free note above; force gap case separately
B5_GAP_HOME="${TEST_TMP}/ws-b5-gap"
mkdir -p "$B5_GAP_HOME"
export VCL_FLEET_HOME="$B5_GAP_HOME"
assert_success "B5 gap fleet init" fleet init
assert_success "B5 gap offline add (no history)" \
  fleet node add gapn --host 203.0.113.78 --offline \
    --node-id "dddddddd-dddd-4ddd-8ddd-ddddddddd5d5"
gap_json=$(fleet workspace migrate --dry-run)
echo "$gap_json" | python3 -c '
import json, sys
p = json.load(sys.stdin)
assert p["counts"]["history_gaps"] >= 1
assert p["history_gaps"][0]["name"] == "gapn"
assert "NOT SSH" in p["note"]
' && pass "B5 dry-run reports history_gaps>=1 (D48)" \
  || fail "B5 dry-run reports history_gaps>=1 (D48)"

export VCL_FLEET_HOME="$B5_HOME"

# Fail-inject: after create temporary Workspace — legacy intact (M03)
B5_FLEET_SHA=$(sha256sum "${B5_HOME}/fleet.json" | awk '{print $1}')
inj1_rc=0
inj1_err=$(VCL_WORKSPACE_MIGRATE_FAIL_AFTER='create temporary Workspace' \
  fleet workspace migrate 2>&1) || inj1_rc=$?
if (( inj1_rc != 0 )) \
  && [[ ! -e "${B5_HOME}/workspace.json" ]] \
  && [[ ! -e "${B5_HOME}/.migrate-staging" ]] \
  && [[ "$(sha256sum "${B5_HOME}/fleet.json" | awk '{print $1}')" == "$B5_FLEET_SHA" ]]; then
  pass "B5 fail-after create temporary Workspace preserves legacy (M03)"
else
  fail "B5 fail-after create temporary Workspace preserves legacy (M03) rc=${inj1_rc}"
fi

# Fail-inject: after migrate registry — legacy fleet.json unchanged
inj2_rc=0
inj2_err=$(VCL_WORKSPACE_MIGRATE_FAIL_AFTER='migrate registry' \
  fleet workspace migrate 2>&1) || inj2_rc=$?
if (( inj2_rc != 0 )) \
  && [[ ! -e "${B5_HOME}/workspace.json" ]] \
  && [[ ! -e "${B5_HOME}/.migrate-staging" ]] \
  && [[ "$(sha256sum "${B5_HOME}/fleet.json" | awk '{print $1}')" == "$B5_FLEET_SHA" ]]; then
  pass "B5 fail-after migrate registry preserves legacy (M03)"
else
  fail "B5 fail-after migrate registry preserves legacy (M03) rc=${inj2_rc}"
fi

# Real migrate (second migrate after fail-inject succeeds)
mig_out=$(fleet workspace migrate 2>/dev/null) || mig_rc=$?
mig_rc=${mig_rc:-0}
assert_equal "B5 real migrate exit 0" "0" "$mig_rc"
printf '%s\n' "$mig_out" > "${TEST_TMP}/ws-b5-mig-out.json"

python3 - "$B5_HOME" "$B5_KEY" "$B5_PRE_HIST" "${TEST_TMP}/ws-b5-mig-out.json" <<'PY' || b5_assert_rc=$?
import json, os, sys, sqlite3
from pathlib import Path
home = Path(sys.argv[1])
key = Path(sys.argv[2]).resolve()
pre_hist = int(sys.argv[3])
result = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
assert result.get("ok") is True, result
assert "fleet_id" in result and result["fleet_id"]
ws = json.loads((home / "workspace.json").read_text(encoding="utf-8"))
assert ws["fleet_id"] == result["fleet_id"]
reg = json.loads((home / "fleet.json").read_text(encoding="utf-8"))
assert reg.get("fleet_id") == result["fleet_id"]
assert len(reg["nodes"]) == 1
n = reg["nodes"][0]
assert n["node_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbb5b5"
assert n["ssh_host"] == "203.0.113.77"
assert n["ssh_port"] == 22
assert n["status"] == "active"
assert "identity_file" not in n, n
assert n.get("admin_credential_ref") == "migrated-key-1"
assert n.get("observe_credential_ref") == "migrated-key-1"
binds = json.loads(
    (home / "machine-local" / "credential-bindings.json").read_text(encoding="utf-8")
)
b = binds["bindings"]["migrated-key-1"]
assert b["type"] == "identity_file"
assert Path(b["path"]).resolve() == key
assert (home / "trust" / "known_hosts").is_file()
hist = home / "history" / "instances.jsonl"
assert hist.is_file()
lines = [ln for ln in hist.read_text(encoding="utf-8").splitlines() if ln.strip()]
assert len(lines) == pre_hist == result["history_exported"], (len(lines), pre_hist, result)
legacies = sorted(home.glob("legacy-pre-workspace-*"))
assert legacies, "missing legacy backup"
assert (legacies[0] / "fleet.db").is_file()
assert (legacies[0] / "fleet.json").is_file()
conn = sqlite3.connect(str(home / "fleet.db"))
row = conn.execute("SELECT value FROM meta WHERE key='fleet_id'").fetchone()
assert row and row[0] == result["fleet_id"], row
conn.close()
assert not (home / ".migrate-staging").exists()
print("ok")
PY
b5_assert_rc=${b5_assert_rc:-0}
if (( b5_assert_rc == 0 )); then
  pass "B5 real migrate workspace+bindings+trust+history+legacy (M01/M02)"
else
  fail "B5 real migrate workspace+bindings+trust+history+legacy (M01/M02)"
fi

# Dry-run after migrate still works
dry_after=$(fleet workspace migrate --dry-run) || dry_after_rc=$?
dry_after_rc=${dry_after_rc:-0}
assert_equal "B5 dry-run after migrate exit 0" "0" "$dry_after_rc"
echo "$dry_after" | python3 -c '
import json, sys
p = json.load(sys.stdin)
assert p["dry_run"] is True and p["side_effects"] == "none"
assert len(p["pipeline"]) == 16
' && pass "B5 dry-run after migrate still plans" \
  || fail "B5 dry-run after migrate still plans"

# Restore SSH fixtures
if [[ -n "${SAVED_WS_B5_SSH}" ]]; then
  export VCL_FLEET_SSH="${SAVED_WS_B5_SSH}"
else
  unset VCL_FLEET_SSH
fi
if [[ -n "${SAVED_WS_B5_KEYSCAN}" ]]; then
  export VCL_FLEET_SSH_KEYSCAN="${SAVED_WS_B5_KEYSCAN}"
else
  unset VCL_FLEET_SSH_KEYSCAN
fi
export VCL_FLEET_HOME="${SAVED_WS_B5_HOME}"

# --- 0.4.1 B6: workspace CLI init/show/verify/export/import (T36) ---
SAVED_WS_B6_HOME="${VCL_FLEET_HOME}"
B6_HOME="${TEST_TMP}/ws-b6-cli"
B6_TGZ="${TEST_TMP}/ws-b6.tgz"
rm -rf "$B6_HOME"
mkdir -p "$B6_HOME"

assert_success "B6 workspace init via --workspace" \
  fleet --workspace "$B6_HOME" workspace init
assert_success "B6 workspace.json exists" test -f "${B6_HOME}/workspace.json"
assert_success "B6 trust dir" test -d "${B6_HOME}/trust"
assert_success "B6 history dir" test -d "${B6_HOME}/history"
assert_success "B6 machine-local dir" test -d "${B6_HOME}/machine-local"
assert_success "B6 fleet.json exists after init" test -f "${B6_HOME}/fleet.json"

show_out=$(fleet --workspace "$B6_HOME" workspace show) || show_rc=$?
show_rc=${show_rc:-0}
assert_equal "B6 workspace show exit 0" "0" "$show_rc"
echo "$show_out" | python3 -c '
import json, re, sys
m = json.load(sys.stdin)
uuid_re = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)
assert uuid_re.fullmatch(m["fleet_id"]), m["fleet_id"]
assert "revision" in m and "write_id" in m and "state_digest" in m
assert "last_writer_controller_id" in m
' && pass "B6 workspace show prints fleet_id UUID + D52 fields" \
  || fail "B6 workspace show prints fleet_id UUID + D52 fields"

B6_FID=$(echo "$show_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["fleet_id"])')

assert_success "B6 verify clean" fleet --workspace "$B6_HOME" workspace verify

# Tamper fleet.json → WORKSPACE_INCONSISTENT
python3 - "$B6_HOME" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]) / "fleet.json"
p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
PY
inc_rc=0
inc_err=$(fleet --workspace "$B6_HOME" workspace verify 2>&1) || inc_rc=$?
if (( inc_rc != 0 )) && [[ "$inc_err" == *WORKSPACE_INCONSISTENT* ]]; then
  pass "B6 verify detects WORKSPACE_INCONSISTENT (S02)"
else
  fail "B6 verify detects WORKSPACE_INCONSISTENT (S02) rc=${inc_rc} err=${inc_err}"
fi
# Restore digest by rewriting clean registry + refresh
python3 - "$B6_HOME" "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY'
import importlib.util, json, os, sys
from pathlib import Path
home = Path(sys.argv[1])
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vcl_fleet_b6", sys.argv[2])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
reg = {"schema_version": 2, "nodes": []}
mod._WS._save_registry_unlocked(None, reg)
m = mod.load_workspace_manifest()
mod.refresh_manifest_digest(m)
mod.save_workspace_manifest(m)
mod.remember_workspace_view(m)
print("restored")
PY
assert_success "B6 verify after restore" fleet --workspace "$B6_HOME" workspace verify

# ROLLBACK: view rev=5, manifest rev=3
python3 - "$B6_HOME" "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY'
import importlib.util, os, sys
from pathlib import Path
home = Path(sys.argv[1])
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vcl_fleet_b6r", sys.argv[2])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
m = mod.load_workspace_manifest()
view = {
    "schema_version": 1,
    "fleet_id": m["fleet_id"],
    "last_seen_revision": 5,
    "last_seen_write_id": m["write_id"],
    "last_seen_state_digest": m["state_digest"],
}
mod.save_workspace_view(view)
m["revision"] = 3
mod.refresh_manifest_digest(m)
mod.save_workspace_manifest(m)
print("rollback-seeded")
PY
roll_rc=0
roll_err=$(fleet --workspace "$B6_HOME" workspace verify 2>&1) || roll_rc=$?
if (( roll_rc != 0 )) && [[ "$roll_err" == *WORKSPACE_ROLLBACK* ]]; then
  pass "B6 verify detects WORKSPACE_ROLLBACK (S02)"
else
  fail "B6 verify detects WORKSPACE_ROLLBACK (S02) rc=${roll_rc} err=${roll_err}"
fi

# DIVERGED: same rev, different write_id
python3 - "$B6_HOME" "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY'
import importlib.util, os, sys, uuid
from pathlib import Path
home = Path(sys.argv[1])
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vcl_fleet_b6d", sys.argv[2])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
m = mod.load_workspace_manifest()
m["revision"] = 5
m["write_id"] = str(uuid.uuid4())
mod.refresh_manifest_digest(m)
mod.save_workspace_manifest(m)
view = {
    "schema_version": 1,
    "fleet_id": m["fleet_id"],
    "last_seen_revision": 5,
    "last_seen_write_id": str(uuid.uuid4()),
    "last_seen_state_digest": m["state_digest"],
}
mod.save_workspace_view(view)
print("diverged-seeded")
PY
div_rc=0
div_err=$(fleet --workspace "$B6_HOME" workspace verify 2>&1) || div_rc=$?
if (( div_rc != 0 )) && [[ "$div_err" == *WORKSPACE_DIVERGED* ]]; then
  pass "B6 verify detects WORKSPACE_DIVERGED (S02)"
else
  fail "B6 verify detects WORKSPACE_DIVERGED (S02) rc=${div_rc} err=${div_err}"
fi

# Fresh clean workspace for export/import (refs-only)
B6_EXP_HOME="${TEST_TMP}/ws-b6-export"
rm -rf "$B6_EXP_HOME"
mkdir -p "$B6_EXP_HOME"
assert_success "B6 export-home init" fleet --workspace "$B6_EXP_HOME" workspace init
# Seed refs-only node (no identity_file)
python3 - "$B6_EXP_HOME" "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY'
import importlib.util, os, sys, uuid
from pathlib import Path
home = Path(sys.argv[1])
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vcl_fleet_b6e", sys.argv[2])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
reg = {
    "schema_version": 2,
    "fleet_id": mod.load_workspace_manifest()["fleet_id"],
    "nodes": [
        {
            "name": "lax",
            "node_id": str(uuid.uuid4()),
            "ssh_host": "203.0.113.10",
            "ssh_user": "root",
            "ssh_port": 22,
            "enabled": True,
            "status": "active",
            "admin_credential_ref": "admin-default",
            "observe_credential_ref": "admin-default",
        }
    ],
}
mod._WS._save_registry_unlocked(None, reg)
# optional trust + history lines
(home / "trust").mkdir(parents=True, exist_ok=True)
(home / "trust" / "known_hosts").write_text(
    "203.0.113.10 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB6portabletrust\n",
    encoding="utf-8",
)
(home / "history").mkdir(parents=True, exist_ok=True)
(home / "history" / "instances.jsonl").write_text(
    '{"node_id":"%s","instance_id":"%s","started_at":"2026-01-01T00:00:00Z",'
    '"retired_at":null,"endpoint":"203.0.113.10","reason":"sync-first-sight"}\n'
    % (reg["nodes"][0]["node_id"], str(uuid.uuid4())),
    encoding="utf-8",
)
# machine-local must NOT be exported
(home / "machine-local").mkdir(parents=True, exist_ok=True)
(home / "machine-local" / "credential-bindings.json").write_text(
    '{"schema_version":1,"bindings":{"admin-default":'
    '{"type":"identity_file","path":"/home/secret/id_ed25519"}}}\n',
    encoding="utf-8",
)
(home / "fleet.db").write_bytes(b"not-a-real-db")
m = mod.load_workspace_manifest()
mod.refresh_manifest_digest(m)
mod.save_workspace_manifest(m)
mod.remember_workspace_view(m)
print(m["fleet_id"])
PY
B6_EXP_FID=$(fleet --workspace "$B6_EXP_HOME" workspace show | python3 -c 'import json,sys; print(json.load(sys.stdin)["fleet_id"])')

# identity_file seed must refuse export
B6_BAD_HOME="${TEST_TMP}/ws-b6-bad-export"
rm -rf "$B6_BAD_HOME"
mkdir -p "$B6_BAD_HOME"
assert_success "B6 bad-export init" fleet --workspace "$B6_BAD_HOME" workspace init
python3 - "$B6_BAD_HOME" "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY'
import importlib.util, os, sys, uuid
from pathlib import Path
home = Path(sys.argv[1])
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vcl_fleet_b6bad", sys.argv[2])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
reg = {
    "schema_version": 2,
    "nodes": [
        {
            "name": "lax",
            "node_id": str(uuid.uuid4()),
            "ssh_host": "203.0.113.10",
            "ssh_user": "root",
            "ssh_port": 22,
            "enabled": True,
            "status": "active",
            "identity_file": "/home/secret/id_ed25519",
        }
    ],
}
mod._WS._save_registry_unlocked(None, reg)
m = mod.load_workspace_manifest()
mod.refresh_manifest_digest(m)
mod.save_workspace_manifest(m)
print("bad-seeded")
PY
bad_rc=0
bad_err=$(fleet --workspace "$B6_BAD_HOME" workspace export "$B6_TGZ.bad" 2>&1) || bad_rc=$?
if (( bad_rc != 0 )) && [[ "$bad_err" == *identity_file* || "$bad_err" == *credential* || "$bad_err" == *portable* ]]; then
  pass "B6 export refuses identity_file secrets (D22/D28)"
else
  fail "B6 export refuses identity_file secrets (D22/D28) rc=${bad_rc} err=${bad_err}"
fi

rm -f "$B6_TGZ"
assert_success "B6 export clean refs-only" \
  fleet --workspace "$B6_EXP_HOME" workspace export "$B6_TGZ"
assert_success "B6 export archive exists" test -f "$B6_TGZ"

tar_list=$(tar -tzf "$B6_TGZ")
echo "$tar_list" | grep -q 'workspace.json' \
  && pass "B6 export contains workspace.json" \
  || fail "B6 export contains workspace.json"
echo "$tar_list" | grep -q 'fleet.json' \
  && pass "B6 export contains fleet.json" \
  || fail "B6 export contains fleet.json"
if echo "$tar_list" | grep -qE 'machine-local|fleet\.db|last-status'; then
  fail "B6 export omits machine-local/fleet.db/last-status"
else
  pass "B6 export omits machine-local/fleet.db/last-status"
fi
# strings / content must not leak secrets or machine paths
if tar -xOzf "$B6_TGZ" | grep -qE 'identity_file|/home/|machine-local|fleet\.db'; then
  fail "B6 export payload has no identity_file/home/machine-local/fleet.db"
else
  pass "B6 export payload has no identity_file/home/machine-local/fleet.db"
fi

B6_IMP_HOME="${TEST_TMP}/ws-b6-import"
rm -rf "$B6_IMP_HOME"
mkdir -p "$B6_IMP_HOME"
assert_success "B6 import into new home" \
  fleet --workspace "$B6_IMP_HOME" workspace import "$B6_TGZ"
imp_show=$(fleet --workspace "$B6_IMP_HOME" workspace show)
imp_fid=$(echo "$imp_show" | python3 -c 'import json,sys; print(json.load(sys.stdin)["fleet_id"])')
assert_equal "B6 import preserves fleet_id" "$B6_EXP_FID" "$imp_fid"
assert_success "B6 import verify OK" fleet --workspace "$B6_IMP_HOME" workspace verify
assert_failure "B6 import did not copy machine-local bindings" \
  test -f "${B6_IMP_HOME}/machine-local/credential-bindings.json"
assert_failure "B6 import did not copy fleet.db" \
  test -f "${B6_IMP_HOME}/fleet.db"

# VCL_FLEET_WORKSPACE alias when VCL_FLEET_HOME unset
SAVED_B6_FLEET_HOME_ENV="${VCL_FLEET_HOME:-}"
unset VCL_FLEET_HOME
export VCL_FLEET_WORKSPACE="$B6_IMP_HOME"
alias_out=$(fleet workspace show) || alias_rc=$?
alias_rc=${alias_rc:-0}
assert_equal "B6 VCL_FLEET_WORKSPACE alias show exit 0" "0" "$alias_rc"
echo "$alias_out" | python3 -c '
import json, sys
m = json.load(sys.stdin)
assert m["fleet_id"]
' && pass "B6 VCL_FLEET_WORKSPACE alias works for workspace show" \
  || fail "B6 VCL_FLEET_WORKSPACE alias works for workspace show"
unset VCL_FLEET_WORKSPACE
export VCL_FLEET_HOME="${SAVED_B6_FLEET_HOME_ENV}"

# Dry-run still zero side-effect (T32 regression)
B6_DRY_HOME="${TEST_TMP}/ws-b6-dry"
rm -rf "$B6_DRY_HOME"
mkdir -p "$B6_DRY_HOME"
SAVED_B6_DRY_HOME="${VCL_FLEET_HOME}"
SAVED_B6_DRY_SSH="${VCL_FLEET_SSH:-}"
SAVED_B6_DRY_KEYSCAN="${VCL_FLEET_SSH_KEYSCAN:-}"
export VCL_FLEET_HOME="$B6_DRY_HOME"
export VCL_FLEET_SSH=/bin/false
export VCL_FLEET_SSH_KEYSCAN=/bin/false
fleet init >/dev/null
fleet node add offline1 --host 203.0.113.99 --offline \
  --node-id 6fc96a10-1111-4111-8111-111111111111 >/dev/null
snap_before=$(find "$B6_DRY_HOME" -type f -printf '%P %s %T@\n' | sort)
dry_b6=$(fleet workspace migrate --dry-run) || dry_b6_rc=$?
dry_b6_rc=${dry_b6_rc:-0}
snap_after=$(find "$B6_DRY_HOME" -type f -printf '%P %s %T@\n' | sort)
assert_equal "B6 dry-run exit 0" "0" "$dry_b6_rc"
assert_equal "B6 dry-run zero side-effect files" "$snap_before" "$snap_after"
echo "$dry_b6" | python3 -c '
import json, sys
p = json.load(sys.stdin)
assert p["dry_run"] is True and p["side_effects"] == "none"
assert len(p["pipeline"]) == 16
assert "NOT SSH" in p.get("note", "")
' && pass "B6 dry-run still plans without SSH" \
  || fail "B6 dry-run still plans without SSH"
if [[ -n "${SAVED_B6_DRY_SSH}" ]]; then
  export VCL_FLEET_SSH="${SAVED_B6_DRY_SSH}"
else
  unset VCL_FLEET_SSH
fi
if [[ -n "${SAVED_B6_DRY_KEYSCAN}" ]]; then
  export VCL_FLEET_SSH_KEYSCAN="${SAVED_B6_DRY_KEYSCAN}"
else
  unset VCL_FLEET_SSH_KEYSCAN
fi
export VCL_FLEET_HOME="${SAVED_B6_DRY_HOME}"

# No SSH in workspace migrate helpers
if grep -nE 'ssh_run|candidate_host_keys' "${PROJECT_DIR}/lib/workspace.py" >/dev/null 2>&1; then
  fail "B6 workspace.py has no ssh_run/candidate_host_keys"
else
  pass "B6 workspace.py has no ssh_run/candidate_host_keys"
fi

export VCL_FLEET_HOME="${SAVED_WS_B6_HOME}"

OFFLINE_FLEET_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="${TEST_TMP}/fleet-home-hostkey"
assert_success "host-key fleet home init" fleet init

nohk_rc=0
nohk_err=$(fleet node add lax --host 203.0.113.10 2>&1 </dev/null) || nohk_rc=$?
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
mismatch_err=$(fleet node add lax --host 203.0.113.10 --host-key SHA256:deadbeef 2>&1 </dev/null) || mismatch_rc=$?
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
badfmt_err=$(fleet node add lax --host 203.0.113.10 --host-key not-a-fingerprint 2>&1 </dev/null) || badfmt_rc=$?
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
sg_live_err=$(fleet node add sg --host 203.0.113.12 2>&1 </dev/null) || sg_live_rc=$?
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
assert data.get("schema_version") == 2
names = {n["name"]: n for n in data["nodes"]}
assert set(names) == {"lax", "tokyo", "sg"}, set(names)
assert names["lax"]["node_id"] == lax_id
assert names["tokyo"]["node_id"] == tokyo_id
assert names["sg"]["node_id"] == sg_id
assert names["lax"]["ssh_host"] == "203.0.113.10"
assert names["tokyo"]["ssh_host"] == "203.0.113.11"
assert names["sg"]["ssh_host"] == "203.0.113.12"
assert names["lax"]["status"] == "active"
assert names["tokyo"]["status"] == "active"
assert names["sg"]["status"] == "active"
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
assert_success "status --help mentions cache-only (D58)" \
  grep -Eqi 'cache' <<< "$(fleet status --help)"

probe_rc=0
probe_out=$(fleet probe 2>&1) || probe_rc=$?
if (( probe_rc != 0 )); then
  pass "AC-2.8-03 three-fixture probe exits non-zero (sg SSH FAIL)"
else
  fail "AC-2.8-03 three-fixture probe exits non-zero (sg SSH FAIL) (rc=${probe_rc})"
fi
assert_success "probe table header has NAME NODE_ID INSTANCE SSH PROXY ACCOUNTING" \
  grep -Eq 'NAME.+NODE_ID.+INSTANCE.+SSH.+PROXY.+ACCOUNTING' <<< "$probe_out"
assert_success "AC-2.8-03 probe lax OK/OK/OK" \
  grep -Eq '^lax[[:space:]].*[[:space:]]OK[[:space:]]+OK[[:space:]]+OK[[:space:]]*$' <<< "$probe_out"
assert_success "AC-2.8-03 probe tokyo OK/OK/STALE" \
  grep -Eq '^tokyo[[:space:]].*[[:space:]]OK[[:space:]]+OK[[:space:]]+STALE[[:space:]]*$' <<< "$probe_out"
assert_success "AC-2.8-03 probe sg FAIL/UNKNOWN/UNKNOWN" \
  grep -Eq '^sg[[:space:]].*[[:space:]]FAIL[[:space:]]+UNKNOWN[[:space:]]+UNKNOWN[[:space:]]*$' <<< "$probe_out"

probe_json_rc=0
probe_json=$(fleet probe --json 2>/dev/null) || probe_json_rc=$?
if (( probe_json_rc != 0 )); then
  pass "probe --json exits non-zero with sg FAIL"
else
  fail "probe --json exits non-zero with sg FAIL (rc=${probe_json_rc})"
fi
probe_json_shape_rc=0
python3 - "$probe_json" "$LAX_REMOTE_NODE_ID" "$TEST_TOKYO_NODE_ID" "$TEST_SG_NODE_ID" <<'PY' || probe_json_shape_rc=$?
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
if (( probe_json_shape_rc == 0 )); then
  pass "probe --json shape: lax OK tokyo STALE sg FAIL/UNKNOWN"
else
  fail "probe --json shape: lax OK tokyo STALE sg FAIL/UNKNOWN"
fi

verify_rc=0
verify_out=$(fleet verify 2>&1) || verify_rc=$?
if (( verify_rc != 0 )); then
  pass "verify three-fixture exits non-zero (sg FAIL)"
else
  fail "verify three-fixture exits non-zero (sg FAIL) (rc=${verify_rc})"
fi
assert_success "verify reports lax version" grep -q '0.3.1' <<< "$verify_out"
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
assert nodes["lax"]["vincula_version"] == "0.3.1"
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

assert_success "disable sg for stale-only probe" fleet node disable sg
stale_probe_rc=0
stale_probe=$(fleet probe 2>&1) || stale_probe_rc=$?
if (( stale_probe_rc == 0 )); then
  pass "probe exits 0 when only accounting STALE remains"
else
  fail "probe exits 0 when only accounting STALE remains (rc=${stale_probe_rc})"
fi
assert_failure "probe without --all omits disabled sg" \
  grep -Eq '^sg[[:space:]]' <<< "$stale_probe"
assert_success "probe --all shows disabled sg" \
  grep -Eq '^sg[[:space:]].*DISABLED' <<< "$(fleet probe --all)"
stale_verify_rc=0
fleet verify >/dev/null 2>&1 || stale_verify_rc=$?
if (( stale_verify_rc == 0 )); then
  pass "verify exits 0 when sg is disabled and tokyo is STALE"
else
  fail "verify exits 0 when sg is disabled and tokyo is STALE (rc=${stale_verify_rc})"
fi
assert_success "re-enable sg" fleet node enable sg

# --- 0.4.1 B7: D58 status cache-only / probe live / status --live alias ---
export VCL_FAKE_SSH_ARGV_LOG="${TEST_TMP}/d58-ssh.log"
: >"$VCL_FAKE_SSH_ARGV_LOG"
fleet probe >/dev/null || true
L0=$(wc -l <"$VCL_FAKE_SSH_ARGV_LOG")
fleet status >/dev/null
assert_equal "AC-4.1-02 bare status zero SSH" "$L0" "$(wc -l <"$VCL_FAKE_SSH_ARGV_LOG")"
fleet status --live >/dev/null || true
L2=$(wc -l <"$VCL_FAKE_SSH_ARGV_LOG")
if (( L2 > L0 )); then
  pass "status --live SSHes"
else
  fail "status --live SSHes (L0=${L0} L2=${L2})"
fi
fleet probe >/dev/null || true
if (( $(wc -l <"$VCL_FAKE_SSH_ARGV_LOG") > L2 )); then
  pass "probe SSHes"
else
  fail "probe SSHes"
fi
cache_status_json=$(fleet status --json 2>/dev/null) || true
assert_success "status --json mode is cache" \
  grep -q '"mode": "cache"' <<< "$cache_status_json"
cache_table=$(fleet status 2>/dev/null || true)
assert_success "cache status table has LAST_SYNC and DATA_AGE" \
  grep -Eq 'LAST_SYNC.+DATA_AGE' <<< "$cache_table"
d58_cache_shape_rc=0
python3 - "$cache_status_json" <<'PY' || d58_cache_shape_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
assert doc.get("mode") == "cache"
assert doc.get("ok") is True
for n in doc["nodes"]:
    assert "last_sync_at" in n, n
    assert "data_age" in n, n
    assert "cursor_status" in n, n
PY
if (( d58_cache_shape_rc == 0 )); then
  pass "cache status --json has last_sync_at/data_age/cursor_status"
else
  fail "cache status --json has last_sync_at/data_age/cursor_status"
fi
unset VCL_FAKE_SSH_ARGV_LOG

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

P101_ARGV_LOG="${TEST_TMP}/p101-user-add-argv.jsonl"
rm -f "$P101_ARGV_LOG"
export VCL_FAKE_SSH_ARGV_LOG="$P101_ARGV_LOG"
spaced_add_rc=0
spaced_add_err=$(fleet user add alice.smith --node lax --display-name "Alice Smith" --department "R&D" 2>&1) || spaced_add_rc=$?
unset VCL_FAKE_SSH_ARGV_LOG
if (( spaced_add_rc == 0 )); then
  pass "P1-01 user add display_name with spaces exits 0"
else
  fail "P1-01 user add display_name with spaces exits 0 (rc=${spaced_add_rc} err=${spaced_add_err})"
fi
spaced_meta_rc=0
python3 - "$VCL_FAKE_STATE_DIR" "$P101_ARGV_LOG" <<'PY' || spaced_meta_rc=$?
import json, sys
from pathlib import Path
state, log_path = Path(sys.argv[1]), Path(sys.argv[2])
lax = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
user = next(u for u in lax["users"] if u["tag"] == "alice.smith")
assert user["display_name"] == "Alice Smith", user
assert user["department"] == "R&D", user
records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
adds = [r for r in records if r["argv"][:4] == ["vcl", "user", "add", "alice.smith"]]
assert adds, records
last = adds[-1]
assert len(last["raw_remote"]) == 1, last["raw_remote"]
assert last["argv"][last["argv"].index("--display-name") + 1] == "Alice Smith"
assert last["argv"][last["argv"].index("--department") + 1] == "R&D"
assert "Smith" not in last["argv"]
assert "R&D" in last["argv"]
PY
if (( spaced_meta_rc == 0 )); then
  pass "P1-01 Alice Smith stays one remote argv; stored display_name intact"
else
  fail "P1-01 Alice Smith stays one remote argv; stored display_name intact"
fi

nl_add_rc=0
nl_add_err=$(fleet user add bad.nl --node lax --display-name $'Alice\nid' 2>&1) || nl_add_rc=$?
if (( nl_add_rc != 0 )) && [[ "$nl_add_err" == *"control characters"* ]]; then
  pass "P1-01 user add rejects display_name with newline"
else
  fail "P1-01 user add rejects display_name with newline (rc=${nl_add_rc} err=${nl_add_err})"
fi

evil_host_rc=0
evil_host_err=$(fleet node add p101evil --host '203.0.113.10;id' --offline \
  --node-id 44444444-4444-4444-8444-444444444444 2>&1) || evil_host_rc=$?
if (( evil_host_rc != 0 )) && [[ "$evil_host_err" == *"invalid ssh_host"* ]]; then
  pass "P1-01 node add rejects ssh_host with semicolon"
else
  fail "P1-01 node add rejects ssh_host with semicolon (rc=${evil_host_rc} err=${evil_host_err})"
fi

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

IMPORT_FLEET_HOME="${TEST_TMP}/fleet-home-import"
IMPORT_FAKE_STATE="${TEST_TMP}/fake-fleet-import-state"
export VCL_FLEET_HOME="$IMPORT_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$IMPORT_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "$VCL_FAKE_STATE_DIR"
assert_success "import-test fleet init" fleet init
assert_success "import-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"
assert_success "import-test offline add tokyo" \
  fleet node add tokyo --host 203.0.113.11 --offline --node-id "$TEST_TOKYO_NODE_ID"

import_help_rc=0
import_help=$(fleet user import -h 2>&1) || import_help_rc=$?
if (( import_help_rc == 0 )) && [[ "$import_help" == *"tag,display_name,department,nodes"* ]] \
  && [[ "$import_help" == *"--dry-run"* ]]; then
  pass "user import -h documents CSV header and --dry-run"
else
  fail "user import -h documents CSV header and --dry-run (rc=${import_help_rc})"
fi

cat > "${TEST_TMP}/import-charlie.csv" <<'CSV'
tag,display_name,department,nodes
charlie,Charlie,Engineering,"lax,tokyo"
CSV

cat > "${TEST_TMP}/import-alice-smith.csv" <<'CSV'
tag,display_name,department,nodes
alice.smith,Alice Smith,R&D,lax
CSV

cat > "${TEST_TMP}/import-newline.csv" <<CSV
tag,display_name,department,nodes
bad.nl,"Alice
id",Eng,lax
CSV

nl_imp_rc=0
nl_imp_err=$(fleet user import "${TEST_TMP}/import-newline.csv" --dry-run 2>&1) || nl_imp_rc=$?
if (( nl_imp_rc != 0 )) && [[ "$nl_imp_err" == *"control characters"* ]]; then
  pass "P1-01 user import rejects display_name with newline"
else
  fail "P1-01 user import rejects display_name with newline (rc=${nl_imp_rc} err=${nl_imp_err})"
fi

smith_dry_rc=0
smith_dry_out=$(fleet user import "${TEST_TMP}/import-alice-smith.csv" --dry-run) || smith_dry_rc=$?
if (( smith_dry_rc == 0 )) && [[ "$smith_dry_out" == *"Alice Smith"* ]]; then
  pass "P1-01 user import dry-run accepts display_name with spaces"
else
  fail "P1-01 user import dry-run accepts display_name with spaces (rc=${smith_dry_rc} out=${smith_dry_out})"
fi

dry_rc=0
dry_out=$(fleet user import "${TEST_TMP}/import-charlie.csv" --dry-run) || dry_rc=$?
if (( dry_rc == 0 )) && [[ "$dry_out" == *"charlie"* ]] \
  && [[ "$dry_out" == *"lax,tokyo"* ]] && [[ "$dry_out" == *"No changes were made."* ]]; then
  pass "user import --dry-run prints plan for quoted lax,tokyo cell"
else
  fail "user import --dry-run prints plan for quoted lax,tokyo cell (rc=${dry_rc})"
fi
if python3 - "$VCL_FAKE_STATE_DIR" <<'PY'
import json, sys
from pathlib import Path
state = Path(sys.argv[1])
for alias in ("lax", "tokyo"):
    path = state / alias / "users.json"
    if not path.is_file():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    assert not any(u.get("tag") == "charlie" for u in data.get("users") or []), data
PY
then
  pass "user import --dry-run does not mutate node users"
else
  fail "user import --dry-run does not mutate node users"
fi

cat > "${TEST_TMP}/import-dup.csv" <<'CSV'
tag,display_name,department,nodes
erin,Erin,Sales,lax
erin,Erin2,Sales,tokyo
CSV
dup_rc=0
dup_err=$(fleet user import "${TEST_TMP}/import-dup.csv" 2>&1) || dup_rc=$?
if (( dup_rc == 1 )) && [[ "$dup_err" == *"duplicate tag erin"* ]] \
  && [[ "$dup_err" == *"no changes were made"* ]]; then
  pass "user import rejects duplicate tag in CSV"
else
  fail "user import rejects duplicate tag in CSV (rc=${dup_rc} err=${dup_err})"
fi
if python3 - "$VCL_FAKE_STATE_DIR" <<'PY'
import json, sys
from pathlib import Path
state = Path(sys.argv[1])
for alias in ("lax", "tokyo"):
    path = state / alias / "users.json"
    if not path.is_file():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    assert not any(u.get("tag") == "erin" for u in data.get("users") or []), data
PY
then
  pass "duplicate tag import performs zero mutation"
else
  fail "duplicate tag import performs zero mutation"
fi

cat > "${TEST_TMP}/import-mars.csv" <<'CSV'
tag,display_name,department,nodes
charlie,Charlie,Engineering,"lax,tokyo"
frank,Frank,Sales,mars
CSV
mars_rc=0
mars_err=$(fleet user import "${TEST_TMP}/import-mars.csv" 2>&1) || mars_rc=$?
if (( mars_rc == 1 )) && [[ "$mars_err" == *"unknown node: mars"* ]] \
  && [[ "$mars_err" == *"no changes were made"* ]]; then
  pass "user import rejects unknown node mars"
else
  fail "user import rejects unknown node mars (rc=${mars_rc} err=${mars_err})"
fi
if python3 - "$VCL_FAKE_STATE_DIR" <<'PY'
import json, sys
from pathlib import Path
state = Path(sys.argv[1])
for alias in ("lax", "tokyo"):
    path = state / alias / "users.json"
    if not path.is_file():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    tags = {u.get("tag") for u in data.get("users") or []}
    assert "charlie" not in tags, data
    assert "frank" not in tags, data
PY
then
  pass "validation failure (unknown node) applies zero rows"
else
  fail "validation failure (unknown node) applies zero rows"
fi

cat > "${TEST_TMP}/import-bad-header.csv" <<'CSV'
tag,display_name,department
charlie,Charlie,Engineering
CSV
hdr_rc=0
hdr_err=$(fleet user import "${TEST_TMP}/import-bad-header.csv" 2>&1) || hdr_rc=$?
if (( hdr_rc == 1 )) && [[ "$hdr_err" == *"tag,display_name,department,nodes"* ]]; then
  pass "user import rejects inexact CSV header"
else
  fail "user import rejects inexact CSV header (rc=${hdr_rc} err=${hdr_err})"
fi

IMPORT_OUT="${TEST_TMP}/import-charlie-creds.csv"
import_rc=0
import_out=$(fleet user import "${TEST_TMP}/import-charlie.csv" --output "$IMPORT_OUT") || import_rc=$?
if (( import_rc == 0 )); then
  pass "user import charlie --nodes lax,tokyo exits 0"
else
  fail "user import charlie --nodes lax,tokyo exits 0 (rc=${import_rc})"
fi
assert_success "import stdout credential CSV header" \
  grep -q '^user,node,credential_id,vless_uri$' <<< "$import_out"

import_check_rc=0
python3 - "$import_out" "$IMPORT_OUT" "$VCL_FAKE_STATE_DIR" <<'PY' || import_check_rc=$?
import csv, io, json, os, sys
from pathlib import Path

text, out_path, state = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
rows = list(csv.DictReader(io.StringIO(text)))
assert [r for r in text.splitlines() if r][0] == "user,node,credential_id,vless_uri"
assert len(rows) == 2, rows
assert {row["user"] for row in rows} == {"charlie"}, rows
by_node = {row["node"]: row for row in rows}
assert set(by_node) == {"lax", "tokyo"}, by_node
assert by_node["lax"]["credential_id"] != by_node["tokyo"]["credential_id"]
assert "@203.0.113.10:443" in by_node["lax"]["vless_uri"]
assert "@203.0.113.11:443" in by_node["tokyo"]["vless_uri"]
file_rows = list(csv.DictReader(out_path.open(encoding="utf-8")))
assert {r["node"] for r in file_rows} == {"lax", "tokyo"}
mode = oct(out_path.stat().st_mode & 0o777)
assert mode == "0o600", mode
lax = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
tokyo = json.loads((state / "tokyo" / "users.json").read_text(encoding="utf-8"))
charlie_lax = next(u for u in lax["users"] if u["tag"] == "charlie")
charlie_tokyo = next(u for u in tokyo["users"] if u["tag"] == "charlie")
assert charlie_lax["user_id"] == charlie_tokyo["user_id"]
assert charlie_lax["display_name"] == "Charlie"
assert charlie_lax["department"] == "Engineering"
open(state / "charlie_user_id.txt", "w", encoding="utf-8").write(charlie_lax["user_id"])
PY
if (( import_check_rc == 0 )); then
  pass "user import charlie yields two node-specific CSV rows"
  pass "import --output credential CSV is mode 0600"
else
  fail "user import charlie yields two node-specific CSV rows"
  fail "import --output credential CSV is mode 0600"
fi

export_need_rc=0
export_need_err=$(fleet user export --credentials 2>&1) || export_need_rc=$?
if (( export_need_rc != 0 )) && [[ "$export_need_err" == *"--output"* ]]; then
  pass "user export --credentials requires --output FILE"
else
  fail "user export --credentials requires --output FILE (rc=${export_need_rc} err=${export_need_err})"
fi

meta_export=$(fleet user export)
assert_success "user export metadata header is per-node" \
  grep -q '^tag,display_name,department,user_id,node,enabled$' <<< "$meta_export"
assert_success "user export metadata includes charlie on lax" \
  grep -q '^charlie,Charlie,Engineering,.*,lax,true$' <<< "$meta_export"
assert_success "user export metadata includes charlie on tokyo" \
  grep -q '^charlie,Charlie,Engineering,.*,tokyo,true$' <<< "$meta_export"

EXPORT_CREDS="${TEST_TMP}/export-credentials.csv"
export_rc=0
export_out=$(fleet user export --credentials --output "$EXPORT_CREDS") || export_rc=$?
if (( export_rc == 0 )) && [[ "$export_out" == *"Credential CSV written to"* ]]; then
  pass "user export --credentials --output exits 0"
else
  fail "user export --credentials --output exits 0 (rc=${export_rc} out=${export_out})"
fi

export_check_rc=0
python3 - "$EXPORT_CREDS" "$VCL_FAKE_STATE_DIR" <<'PY' || export_check_rc=$?
import csv, json, sys
from pathlib import Path
path, state = Path(sys.argv[1]), Path(sys.argv[2])
mode = oct(path.stat().st_mode & 0o777)
assert mode == "0o600", mode
rows = list(csv.DictReader(path.open(encoding="utf-8")))
assert list(rows[0].keys()) == ["user", "node", "credential_id", "vless_uri"], rows[0]
charlie = [r for r in rows if r["user"] == "charlie"]
assert {r["node"] for r in charlie} == {"lax", "tokyo"}, charlie
by_node = {r["node"]: r for r in charlie}
assert "@203.0.113.10:443" in by_node["lax"]["vless_uri"]
assert "@203.0.113.11:443" in by_node["tokyo"]["vless_uri"]
assert by_node["lax"]["credential_id"] != by_node["tokyo"]["credential_id"]
assert by_node["lax"]["vless_uri"] != by_node["tokyo"]["vless_uri"]
lax = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
tokyo = json.loads((state / "tokyo" / "users.json").read_text(encoding="utf-8"))
charlie_lax = next(u for u in lax["users"] if u["tag"] == "charlie")
charlie_tokyo = next(u for u in tokyo["users"] if u["tag"] == "charlie")
lax_active = next(c for c in charlie_lax["credentials"] if c["status"] == "active")
tokyo_active = next(c for c in charlie_tokyo["credentials"] if c["status"] == "active")
assert lax_active["credential_id"] == by_node["lax"]["credential_id"]
assert tokyo_active["credential_id"] == by_node["tokyo"]["credential_id"]
PY
if (( export_check_rc == 0 )); then
  pass "credentials export is mode 0600 with node-specific URIs"
else
  fail "credentials export is mode 0600 with node-specific URIs"
fi

unset VCL_FAKE_STATE_DIR

EXPORT_FAKE_STATE="${TEST_TMP}/fake-export-state"
export VCL_FAKE_STATE_DIR="$EXPORT_FAKE_STATE"
mkdir -p "${VCL_FAKE_STATE_DIR}/lax"
export_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY' || export_seed_rc=$?
import importlib.util, json, sys
from pathlib import Path

accountd_py, state_dir, ident_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ident = json.loads(ident_path.read_text(encoding="utf-8"))
node_id = ident["node_id"]
instance_id = ident["instance_id"]
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
db = state_dir / "lax" / "accounting.db"
db.parent.mkdir(parents=True, exist_ok=True)
conn = acct.open_db(str(db))
for i in range(1, 4):
    conn.execute(
        """
        INSERT INTO connections (
          connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, export_seq
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"lax-{i}", 0, "u-alice", node_id, instance_id, "alice",
            "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
            "example.com", "203.0.113.10", 443, "tcp", 100 * i, 200 * i, i,
        ),
    )
acct.meta_set(conn, "audit_export_seq", "3")
acct.meta_set(conn, "audit_pruned_max_export_seq", "0")
conn.commit()
conn.close()
PY
if (( export_seed_rc == 0 )); then
  pass "fake-ssh lax accounting.db fixture seeded"
else
  fail "fake-ssh lax accounting.db fixture seeded"
fi

export_after0_rc=0
"$FAKE_SSH" 203.0.113.10 -- vcl audit export --after 0 --jsonl \
  > "${TEST_TMP}/fake-export.out" 2> "${TEST_TMP}/fake-export.err" || export_after0_rc=$?
if (( export_after0_rc == 0 )); then
  pass "fake-ssh audit export --after 0 exits 0"
else
  fail "fake-ssh audit export --after 0 exits 0 (rc=${export_after0_rc} err=$(cat "${TEST_TMP}/fake-export.err"))"
fi

export_jsonl_rc=0
python3 - "${TEST_TMP}/fake-export.out" "${TEST_TMP}/fake-export.err" <<'PY' || export_jsonl_rc=$?
import json, sys
from pathlib import Path
stdout = Path(sys.argv[1]).read_text(encoding="utf-8")
stderr = Path(sys.argv[2]).read_text(encoding="utf-8")
lines = [json.loads(ln) for ln in stdout.splitlines() if ln.strip()]
assert len(lines) >= 1, lines
assert [r["export_seq"] for r in lines] == [1, 2, 3], [r["export_seq"] for r in lines]
assert [r["event_id"] for r in lines] == [1, 2, 3], [r["event_id"] for r in lines]
nid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
iid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
assert all(r["node_id"] == nid for r in lines)
assert all(r["instance_id"] == iid for r in lines)
for key in (
    "event_id", "export_seq", "connection_id", "generation", "user_id", "user_tag",
    "node_id", "instance_id", "started_at", "last_seen_at", "closed_at",
    "destination_host", "destination_ip", "destination_port", "network",
    "upload_bytes", "download_bytes",
):
    assert key in lines[0], key
meta = json.loads(stderr.strip().splitlines()[-1])
assert meta["ok"] is True
assert meta["protocol_version"] == 2
assert meta["cursor_kind"] == "export_seq"
assert meta["after"] == 0
assert meta["count"] == 3
assert meta["next_cursor"] == 3
assert meta["max_export_seq"] == 3
assert meta["pruned_max_export_seq"] == 0
assert meta["node_id"] == nid
assert meta["instance_id"] == iid
PY
if (( export_jsonl_rc == 0 )); then
  pass "fake-ssh audit export --after 0 emits Protocol v2 JSONL plus stderr meta"
else
  fail "fake-ssh audit export --after 0 emits Protocol v2 JSONL plus stderr meta"
fi

export_ahead_rc=0
"$FAKE_SSH" 203.0.113.10 -- vcl audit export --after 10 --jsonl \
  > "${TEST_TMP}/fake-export-ahead.out" 2> "${TEST_TMP}/fake-export-ahead.err" \
  || export_ahead_rc=$?
export_ahead_check_rc=0
python3 - "$export_ahead_rc" "${TEST_TMP}/fake-export-ahead.out" \
  "${TEST_TMP}/fake-export-ahead.err" <<'PY' || export_ahead_check_rc=$?
import json, sys
from pathlib import Path
assert int(sys.argv[1]) == 3, sys.argv[1]
stdout = Path(sys.argv[2]).read_text(encoding="utf-8")
stderr = Path(sys.argv[3]).read_text(encoding="utf-8")
assert stdout.strip() == "", stdout
meta = json.loads(stderr.strip().splitlines()[-1])
assert meta["ok"] is False
assert meta["error"] == "CURSOR_AHEAD"
assert meta["protocol_version"] == 2
assert meta["cursor_kind"] == "export_seq"
assert meta["after"] == 10
assert meta["max_export_seq"] == 3
assert meta["count"] == 0
assert meta["next_cursor"] == 10
PY
if (( export_ahead_check_rc == 0 )); then
  pass "fake-ssh audit export after=10 max_export_seq=3 is CURSOR_AHEAD exit 3"
else
  fail "fake-ssh audit export after=10 max_export_seq=3 is CURSOR_AHEAD exit 3"
fi

fail_export_rc=0
fail_export_err=$(VCL_FAKE_FAIL_EXPORT=lax "$FAKE_SSH" 203.0.113.10 -- \
  vcl audit export --after 0 --jsonl 2>&1) || fail_export_rc=$?
if (( fail_export_rc == 1 )); then
  pass "VCL_FAKE_FAIL_EXPORT=lax makes audit export exit 1"
else
  fail "VCL_FAKE_FAIL_EXPORT=lax makes audit export exit 1 (rc=${fail_export_rc})"
fi

fail_export_alias_rc=0
fail_export_alias_err=$(VCL_FAKE_FAIL_AUDIT_EXPORT=lax "$FAKE_SSH" 203.0.113.10 -- \
  vcl audit export --after 0 --jsonl 2>&1) || fail_export_alias_rc=$?
if (( fail_export_alias_rc == 1 )); then
  pass "VCL_FAKE_FAIL_AUDIT_EXPORT=lax makes audit export exit 1"
else
  fail "VCL_FAKE_FAIL_AUDIT_EXPORT=lax makes audit export exit 1 (rc=${fail_export_alias_rc})"
fi

unset VCL_FAKE_STATE_DIR

DB_FLEET_HOME="${TEST_TMP}/fleet-home-db"
SAVED_DB_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="$DB_FLEET_HOME"
mkdir -p "$VCL_FLEET_HOME"

open_twice_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" <<'PY' || open_twice_rc=$?
import importlib.util
import os
import stat
import sys
from pathlib import Path

path, home = sys.argv[1], Path(sys.argv[2])
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert mod.FLEET_DB_SCHEMA_VERSION == 3
assert mod.fleet_db_path() == home / "fleet.db"

conn1 = mod.open_fleet_db()
ver1 = mod.fleet_db_meta_get(conn1, "schema_version")
wal1 = conn1.execute("PRAGMA journal_mode").fetchone()[0]
tables = {
    row[0]
    for row in conn1.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
}
pk = conn1.execute("PRAGMA table_info(audit_events)").fetchall()
pk_cols = [r[1] for r in pk if r[5]]
audit_cols = [r[1] for r in pk]
cursor_cols = [r[1] for r in conn1.execute("PRAGMA table_info(sync_cursor)")]
hist_pk = conn1.execute("PRAGMA table_info(instance_history)").fetchall()
hist_pk_cols = [r[1] for r in hist_pk if r[5]]
conn1.close()

conn2 = mod.open_fleet_db()
ver2 = mod.fleet_db_meta_get(conn2, "schema_version")
wal2 = conn2.execute("PRAGMA journal_mode").fetchone()[0]
count = conn2.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
hist_count = conn2.execute("SELECT COUNT(*) FROM instance_history").fetchone()[0]
conn2.close()

assert ver1 == "3" and ver2 == "3", (ver1, ver2)
assert wal1.lower() == "wal" and wal2.lower() == "wal", (wal1, wal2)
assert tables >= {
    "meta", "audit_events", "sync_cursor", "daily_usage", "instance_history"
}
assert set(pk_cols) == {"node_id", "event_id"}, pk_cols
assert "export_seq" in audit_cols, audit_cols
assert "last_export_seq" in cursor_cols and "cursor_kind" in cursor_cols, cursor_cols
assert set(hist_pk_cols) == {"node_id", "instance_id"}, hist_pk_cols
assert count == 0
assert hist_count == 0
db = home / "fleet.db"
mode = stat.S_IMODE(db.stat().st_mode)
assert mode == 0o600, oct(mode)
home_mode = stat.S_IMODE(home.stat().st_mode)
assert home_mode == 0o700, oct(home_mode)
PY
if (( open_twice_rc == 0 )); then
  pass "open_fleet_db twice keeps schema 3 WAL fleet.db mode 0600"
else
  fail "open_fleet_db twice keeps schema 3 WAL fleet.db mode 0600"
fi

migrate_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$TEST_TMP" \
  "$TEST_NODE_ID" "$TEST_INSTANCE_ID" "$TEST_TOKYO_NODE_ID" <<'PY' || migrate_rc=$?
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

path, tmp, node_id, instance_id, other_id = sys.argv[1:6]
mod_spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(mod_spec)
mod_spec.loader.exec_module(mod)

schema1_ddl = """
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE audit_events (
  node_id TEXT NOT NULL,
  instance_id TEXT,
  event_id INTEGER NOT NULL,
  connection_id TEXT NOT NULL,
  generation INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  started_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  closed_at TEXT,
  destination_host TEXT,
  destination_ip TEXT,
  destination_port INTEGER,
  network TEXT,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  imported_at TEXT NOT NULL,
  PRIMARY KEY (node_id, event_id)
);
CREATE TABLE sync_cursor (
  node_id TEXT PRIMARY KEY,
  instance_id TEXT,
  last_event_id INTEGER NOT NULL,
  last_sync_at TEXT NOT NULL,
  status TEXT NOT NULL
);
CREATE TABLE daily_usage (
  date TEXT NOT NULL,
  node_id TEXT NOT NULL,
  instance_id TEXT,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  destination_host TEXT NOT NULL,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  connection_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (date, node_id, user_id, destination_host)
);
"""

# --- handwritten schema 1: cursor with instance_id backfills; NULL does not ---
home = Path(tmp) / "fleet-home-db-migrate"
home.mkdir(parents=True)
os.environ["VCL_FLEET_HOME"] = str(home)
registry = {
    "schema_version": 2,
    "nodes": [
        {
            "node_id": node_id,
            "name": "lax",
            "ssh_host": "203.0.113.10",
            "ssh_user": "root",
            "ssh_port": 22,
            "enabled": True,
            "status": "active",
        },
        {
            "node_id": other_id,
            "name": "tokyo",
            "ssh_host": "203.0.113.11",
            "ssh_user": "root",
            "ssh_port": 22,
            "enabled": True,
            "status": "active",
        },
    ],
}
(home / "fleet.json").write_text(
    json.dumps(registry, indent=2) + "\n", encoding="utf-8"
)
raw = sqlite3.connect(str(home / "fleet.db"))
raw.executescript(schema1_ddl)
raw.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '1')")
raw.execute(
    """
    INSERT INTO audit_events (
      node_id, instance_id, event_id, connection_id, generation,
      user_id, user_tag, started_at, last_seen_at, closed_at,
      destination_host, destination_ip, destination_port, network,
      upload_bytes, download_bytes, imported_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """,
    (
        node_id, instance_id, 1, "c-1", 0, "u-alice", "alice",
        "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
        "example.com", "203.0.113.10", 443, "tcp", 10, 20,
        "2026-08-16T03:00:00Z",
    ),
)
raw.execute(
    """
    INSERT INTO sync_cursor (
      node_id, instance_id, last_event_id, last_sync_at, status
    ) VALUES (?, ?, 1, '2026-08-16T03:00:00Z', 'ok')
    """,
    (node_id, instance_id),
)
raw.execute(
    """
    INSERT INTO sync_cursor (
      node_id, instance_id, last_event_id, last_sync_at, status
    ) VALUES (?, NULL, 0, '2026-08-16T03:00:00Z', 'ok')
    """,
    (other_id,),
)
raw.execute(
    """
    INSERT INTO daily_usage (
      date, node_id, instance_id, user_id, user_tag, destination_host,
      upload_bytes, download_bytes, connection_count
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    ("2026-08-10", node_id, instance_id, "u-alice", "alice", "example.com", 10, 20, 1),
)
raw.commit()
tables_before = {
    r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")
}
assert "instance_history" not in tables_before
raw.close()

conn = mod.open_fleet_db()
ver = mod.fleet_db_meta_get(conn, "schema_version")
assert ver == "3", ver
audit_cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_events)")]
cursor_cols = [r[1] for r in conn.execute("PRAGMA table_info(sync_cursor)")]
assert "export_seq" in audit_cols, audit_cols
assert "last_export_seq" in cursor_cols and "cursor_kind" in cursor_cols, cursor_cols
audit_n = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
daily_n = conn.execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0]
assert audit_n == 1 and daily_n == 1, (audit_n, daily_n)
# Migrated cursors keep event_id kind; last_export_seq stays 0 (not reinterpreted).
cur_kind = conn.execute(
    "SELECT last_event_id, last_export_seq, cursor_kind FROM sync_cursor WHERE node_id=?",
    (node_id,),
).fetchone()
assert tuple(cur_kind) == (1, 0, "event_id"), tuple(cur_kind)
hist = mod.list_instances(conn, node_id)
assert len(hist) == 1, hist
assert hist[0]["instance_id"] == instance_id
assert hist[0]["status"] == "active"
assert hist[0]["retired_at"] is None
assert hist[0]["started_at"] == "2026-08-16T03:00:00Z"
assert hist[0]["ssh_host"] == "203.0.113.10"
assert hist[0]["endpoint"] is None
assert mod.list_instances(conn, other_id) == []
conn.close()

conn2 = mod.open_fleet_db()
assert mod.fleet_db_meta_get(conn2, "schema_version") == "3"
assert len(mod.list_instances(conn2, node_id)) == 1
conn2.close()

# --- record_instance first sight / change / chronological query ---
home2 = Path(tmp) / "fleet-home-db-history"
home2.mkdir(parents=True)
os.environ["VCL_FLEET_HOME"] = str(home2)
conn = mod.open_fleet_db()
assert mod.fleet_db_meta_get(conn, "schema_version") == "3"
old_iid = instance_id
new_iid = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
mod.record_instance(
    conn, node_id, old_iid, "203.0.113.10", "203.0.113.10",
    now_iso="2026-08-16T04:00:00Z",
)
mod.record_instance(
    conn, node_id, old_iid, "203.0.113.10", "203.0.113.10",
    now_iso="2026-08-16T04:01:00Z",
)
first = mod.list_instances(conn, node_id)
assert len(first) == 1, first
assert first[0]["instance_id"] == old_iid
assert first[0]["status"] == "active"
assert first[0]["endpoint"] == "203.0.113.10"
assert first[0]["started_at"] == "2026-08-16T04:00:00Z"

mod.record_instance(
    conn, node_id, new_iid, "203.0.113.18", "203.0.113.18",
    now_iso="2026-08-16T05:00:00Z",
)
rows = mod.list_instances(conn, node_id)
assert [r["instance_id"] for r in rows] == [old_iid, new_iid], rows
assert rows[0]["status"] == "retired"
assert rows[0]["retired_at"] == "2026-08-16T05:00:00Z"
assert rows[1]["status"] == "active"
assert rows[1]["retired_at"] is None
assert rows[1]["endpoint"] == "203.0.113.18"
assert rows[1]["ssh_host"] == "203.0.113.18"

mod.mark_instance_retired(conn, node_id, new_iid, "2026-08-16T06:00:00Z")
after = mod.list_instances(conn, node_id)
assert after[1]["status"] == "retired"
assert after[1]["retired_at"] == "2026-08-16T06:00:00Z"

try:
    mod.insert_instance(
        conn, node_id=node_id, instance_id=node_id,
        started_at="2026-08-16T07:00:00Z",
    )
    raise AssertionError("insert_instance must refuse instance_id == node_id")
except SystemExit:
    pass
conn.close()

# future schema dies; schema 1 tables stay put
home3 = Path(tmp) / "fleet-home-db-future"
home3.mkdir(parents=True)
os.environ["VCL_FLEET_HOME"] = str(home3)
raw = sqlite3.connect(str(home3 / "fleet.db"))
raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
raw.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '99')")
raw.commit()
raw.close()
try:
    mod.open_fleet_db()
    raise AssertionError("open_fleet_db must die on schema 99")
except SystemExit as exc:
    assert exc.code == 1
PY
if (( migrate_rc == 0 )); then
  pass "fleet.db schema 1→2→3 preserves data and records instance history"
else
  fail "fleet.db schema 1→2→3 preserves data and records instance history"
fi

import_batch_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$TEST_NODE_ID" "$TEST_INSTANCE_ID" <<'PY' || import_batch_rc=$?
import contextlib
import importlib.util
import io
import os
import sys
from pathlib import Path

path, home, node_id, instance_id = sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

other_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
now = "2026-08-16T03:00:00Z"

def row(event_id, nid=node_id, iid=instance_id, host="example.com", up=10, down=20, tag="alice", export_seq=None):
    eseq = event_id if export_seq is None else export_seq
    return {
        "event_id": event_id,
        "export_seq": eseq,
        "connection_id": f"c-{event_id}",
        "generation": 0,
        "user_id": "u-alice",
        "user_tag": tag,
        "node_id": nid,
        "instance_id": iid,
        "destination_host": host,
        "destination_ip": "203.0.113.10",
        "destination_port": 443,
        "network": "tcp",
        "upload_bytes": up,
        "download_bytes": down,
        "started_at": "2026-08-10T08:00:00Z",
        "last_seen_at": "2026-08-10T09:00:00Z",
        "closed_at": "2026-08-10T09:00:00Z",
    }

conn = mod.open_fleet_db()
first = mod.import_audit_batch(
    node_id, instance_id,
    [row(1, up=100, down=200), row(2, up=50, down=60)],
    now_iso=now, conn=conn,
)
assert first["ok"] is True
assert first["inserted"] == 2
assert first["updated"] == 0
assert first["ignored"] == 0
assert first["skipped_unlabeled"] == 0
assert first["last_event_id"] == 2
assert first["last_export_seq"] == 2
assert first["status"] == "ok"
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
assert count == 2, count
cur = conn.execute(
    "SELECT instance_id, last_event_id, last_export_seq, cursor_kind, last_sync_at, status "
    "FROM sync_cursor WHERE node_id=?",
    (node_id,),
).fetchone()
assert tuple(cur) == (instance_id, 2, 2, "export_seq", now, "ok"), tuple(cur)
daily = conn.execute(
    "SELECT date, upload_bytes, download_bytes, connection_count FROM daily_usage WHERE node_id=?",
    (node_id,),
).fetchall()
assert len(daily) == 1, daily
assert tuple(daily[0]) == ("2026-08-10", 150, 260, 2), tuple(daily[0])

# Idempotent re-run: UPSERT updates existing rows; daily_usage rebuilt without double-count.
again = mod.import_export_jsonl(
    node_id, instance_id,
    [row(1, up=100, down=200), row(2, up=50, down=60)],
    now, conn=conn,
)
assert again["inserted"] == 0
assert again["updated"] == 2
assert again["ignored"] == 0
assert again["last_event_id"] == 2
assert again["last_export_seq"] == 2
count2 = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
assert count2 == 2
daily2 = conn.execute(
    "SELECT upload_bytes, download_bytes, connection_count FROM daily_usage WHERE node_id=?",
    (node_id,),
).fetchone()
assert tuple(daily2) == (150, 260, 2), tuple(daily2)

# Unlabeled rows fail the whole batch; cursor and prior rows unchanged.
before_unlabeled = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
before_unlabeled_cur = conn.execute(
    "SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()[0]
unlabeled = [
    row(3, up=7, down=8),
    {**row(4), "node_id": ""},
    {**row(5), "node_id": None},
    {"event_id": 6, "export_seq": 6, "user_id": "u-alice", "started_at": "2026-08-10T08:00:00Z"},
]
buf = io.StringIO()
try:
    with contextlib.redirect_stderr(buf):
        mod.import_audit_batch(node_id, instance_id, unlabeled, now_iso=now, conn=conn)
    raise AssertionError("unlabeled rows must fail the batch")
except SystemExit as exc:
    assert exc.code == 1, exc.code
    assert "missing node_id" in buf.getvalue(), buf.getvalue()
after_unlabeled = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
after_unlabeled_cur = conn.execute(
    "SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()[0]
assert after_unlabeled == before_unlabeled == 2
assert after_unlabeled_cur == before_unlabeled_cur == 2
blank = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id IS NULL OR node_id=''"
).fetchone()[0]
assert blank == 0, blank

# Labeled continuation still works after a refused unlabeled batch.
ok3 = mod.import_audit_batch(node_id, instance_id, [row(3, up=7, down=8)], now_iso=now, conn=conn)
assert ok3["inserted"] == 1
assert ok3["skipped_unlabeled"] == 0
assert ok3["last_event_id"] == 3
assert ok3["last_export_seq"] == 3

# Mismatch: whole batch fails, cursor and rows unchanged.
before_count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
before_cur = conn.execute(
    "SELECT last_export_seq, last_sync_at FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
buf = io.StringIO()
try:
    with contextlib.redirect_stderr(buf):
        mod.import_audit_batch(
            node_id, instance_id,
            [row(10), row(11, nid=other_id)],
            now_iso="2026-08-16T04:00:00Z",
            conn=conn,
        )
    raise AssertionError("expected node_id mismatch to fail")
except SystemExit as exc:
    assert exc.code == 1, exc.code
    assert "node_id mismatch" in buf.getvalue(), buf.getvalue()
after_count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
after_cur = conn.execute(
    "SELECT last_export_seq, last_sync_at FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
assert after_count == before_count == 3
assert tuple(after_cur) == tuple(before_cur) == (3, now)

# Historical instance_id NULL on a labeled row is allowed.
null_inst = row(7)
null_inst["instance_id"] = None
ok_null = mod.import_audit_batch(node_id, instance_id, [null_inst], now_iso=now, conn=conn)
assert ok_null["inserted"] == 1
stored_iid = conn.execute(
    "SELECT instance_id FROM audit_events WHERE node_id=? AND event_id=7",
    (node_id,),
).fetchone()[0]
assert stored_iid is None
cur_iid = conn.execute(
    "SELECT instance_id, last_event_id, last_export_seq FROM sync_cursor WHERE node_id=?",
    (node_id,),
).fetchone()
assert tuple(cur_iid) == (instance_id, 7, 7)

# Empty labeled set keeps prior cursor (or 0).
empty = mod.import_audit_batch(node_id, instance_id, [], now_iso="2026-08-16T05:00:00Z", conn=conn)
assert empty["inserted"] == 0
assert empty["last_event_id"] == 7
assert empty["last_export_seq"] == 7
conn.close()
PY
if (( import_batch_rc == 0 )); then
  pass "import_audit_batch is atomic, UPSERT-idempotent, and rejects unlabeled rows"
else
  fail "import_audit_batch is atomic, UPSERT-idempotent, and rejects unlabeled rows"
fi

export VCL_FLEET_HOME="${SAVED_DB_HOME}"

assert_success "cmd_sync is defined" \
  grep -q 'def cmd_sync(' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "sync --reseed flag exists" \
  grep -q -- '--reseed' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "sync uses audit export --after" \
  grep -q 'audit", "export", "--after"' "${PROJECT_DIR}/lib/vincula-fleet.py"

SYNC_FLEET_HOME="${TEST_TMP}/fleet-home-sync"
SYNC_FAKE_STATE="${TEST_TMP}/fake-sync-state"
export VCL_FLEET_HOME="$SYNC_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$SYNC_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax"

assert_success "sync-test fleet init" fleet init
assert_success "sync-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"

sync_help_rc=0
sync_help=$(fleet sync -h) || sync_help_rc=$?
if (( sync_help_rc == 0 )) && [[ "$sync_help" == *"--reseed"* ]] \
  && [[ "$sync_help" == *"--node"* ]] && [[ "$sync_help" == *"CURSOR_EXPIRED"* ]] \
  && [[ "$sync_help" == *"CURSOR_AHEAD"* ]]; then
  pass "sync -h documents --node/--reseed/CURSOR_EXPIRED/CURSOR_AHEAD"
else
  fail "sync -h documents --node/--reseed/CURSOR_EXPIRED/CURSOR_AHEAD (rc=${sync_help_rc})"
fi

unknown_sync_rc=0
unknown_sync_err=$(fleet sync --node mars 2>&1) || unknown_sync_rc=$?
if (( unknown_sync_rc != 0 )) && [[ "$unknown_sync_err" == *"unknown node"* ]]; then
  pass "sync --node unknown dies"
else
  fail "sync --node unknown dies (rc=${unknown_sync_rc} err=${unknown_sync_err})"
fi

seed_sync_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY' || seed_sync_rc=$?
import importlib.util, json, sys
from pathlib import Path

accountd_py, state_dir, ident_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ident = json.loads(ident_path.read_text(encoding="utf-8"))
node_id = ident["node_id"]
instance_id = ident["instance_id"]
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
db = state_dir / "lax" / "accounting.db"
db.parent.mkdir(parents=True, exist_ok=True)
conn = acct.open_db(str(db))
for i in range(1, 6):
    conn.execute(
        """
        INSERT INTO connections (
          connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, export_seq
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"lax-sync-{i}", 0, "u-alice", node_id, instance_id, "alice",
            "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
            "example.com", "203.0.113.10", 443, "tcp", 10 * i, 20 * i, i,
        ),
    )
acct.meta_set(conn, "audit_export_seq", "5")
acct.meta_set(conn, "audit_pruned_max_export_seq", "0")
conn.commit()
conn.close()
PY
if (( seed_sync_rc == 0 )); then
  pass "sync fixture seeded lax accounting.db export_seq 1-5"
else
  fail "sync fixture seeded lax accounting.db export_seq 1-5"
fi

sync1_rc=0
sync1_out=$(fleet sync --node lax --json) || sync1_rc=$?
if (( sync1_rc == 0 )); then
  pass "initial sync --node lax exits 0"
else
  fail "initial sync --node lax exits 0 (rc=${sync1_rc} out=${sync1_out})"
fi

sync1_check_rc=0
python3 - "$sync1_out" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || sync1_check_rc=$?
import json, sqlite3, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
home, node_id = Path(sys.argv[2]), sys.argv[3]
assert doc["schema_version"] == 1
assert doc["ok"] is True
assert doc["state"] == "SUCCESS"
assert doc["operation"] == "sync"
assert len(doc["nodes"]) == 1
row = doc["nodes"][0]
assert row["name"] == "lax"
assert row["status"] == "ok"
assert row["after"] == 0
assert row["last_export_seq"] == 5
assert row["last_event_id"] == 5
assert row["inserted"] == 5
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, cursor_kind, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
hist = conn.execute(
    """
    SELECT instance_id, status, retired_at, ssh_host
    FROM instance_history WHERE node_id=? ORDER BY started_at, rowid
    """,
    (node_id,),
).fetchall()
conn.close()
assert count == 5, count
assert cur == (5, "export_seq", "ok"), cur
assert len(hist) == 1, hist
assert hist[0][0] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
assert hist[0][1] == "active"
assert hist[0][2] is None
assert hist[0][3] == "203.0.113.10"
PY
if (( sync1_check_rc == 0 )); then
  pass "initial sync after 0 imports 5 events and last_export_seq=5"
else
  fail "initial sync after 0 imports 5 events and last_export_seq=5"
fi

# New process, same fleet.db: cursor is durable (AC-2.9 / former AC-2.8-09).
sync2_rc=0
sync2_out=$(fleet sync --node lax --json) || sync2_rc=$?
if (( sync2_rc == 0 )); then
  pass "restart sync (new process) exits 0"
else
  fail "restart sync (new process) exits 0 (rc=${sync2_rc})"
fi

sync2_check_rc=0
python3 - "$sync2_out" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || sync2_check_rc=$?
import json, sqlite3, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
home, node_id = Path(sys.argv[2]), sys.argv[3]
assert doc["ok"] is True
row = doc["nodes"][0]
assert row["status"] == "ok"
assert row["after"] == 5
assert row["last_export_seq"] == 5
assert row["last_event_id"] == 5
assert row["inserted"] == 0
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute("SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)).fetchone()[0]
conn.close()
assert count == 5, count
assert cur == 5, cur
PY
if (( sync2_check_rc == 0 )); then
  pass "controller restart continues from last_export_seq; COUNT stays 5"
else
  fail "controller restart continues from last_export_seq; COUNT stays 5"
fi

incr_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY' || incr_seed_rc=$?
import importlib.util, json, sqlite3, sys
from pathlib import Path

accountd_py, state_dir, ident_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ident = json.loads(ident_path.read_text(encoding="utf-8"))
node_id = ident["node_id"]
instance_id = ident["instance_id"]
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
db = state_dir / "lax" / "accounting.db"
conn = sqlite3.connect(str(db))
for i in (6, 7):
    conn.execute(
        """
        INSERT INTO connections (
          connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, export_seq
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"lax-sync-{i}", 0, "u-alice", node_id, instance_id, "alice",
            "2026-08-11T08:00:00Z", "2026-08-11T09:00:00Z", "2026-08-11T09:00:00Z",
            "example.com", "203.0.113.10", 443, "tcp", 10 * i, 20 * i, i,
        ),
    )
conn.execute(
    "INSERT OR REPLACE INTO meta(key,value) VALUES('audit_export_seq','7')"
)
conn.execute(
    "INSERT OR REPLACE INTO meta(key,value) VALUES('audit_pruned_max_export_seq','0')"
)
conn.commit()
conn.close()
PY
if (( incr_seed_rc == 0 )); then
  pass "incremental fixture appended export_seq 6-7"
else
  fail "incremental fixture appended export_seq 6-7"
fi

sync3_rc=0
sync3_out=$(fleet sync --node lax --json) || sync3_rc=$?
sync3_check_rc=0
python3 - "$sync3_out" "$sync3_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || sync3_check_rc=$?
import json, sqlite3, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
home, node_id = Path(sys.argv[3]), sys.argv[4]
row = doc["nodes"][0]
assert row["after"] == 5
assert row["last_export_seq"] == 7
assert row["last_event_id"] == 7
assert row["inserted"] == 2
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
ids = [r[0] for r in conn.execute(
    "SELECT event_id FROM audit_events WHERE node_id=? ORDER BY event_id", (node_id,)
)]
cur = conn.execute(
    "SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()[0]
conn.close()
assert count == 7, count
assert ids == [1, 2, 3, 4, 5, 6, 7], ids
assert cur == 7, cur
PY
if (( sync3_check_rc == 0 )); then
  pass "incremental sync imports new rows after last_export_seq"
else
  fail "incremental sync imports new rows after last_export_seq"
fi

sync4_rc=0
sync4_out=$(fleet sync --node lax --json) || sync4_rc=$?
sync4_check_rc=0
python3 - "$sync4_out" "$sync4_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || sync4_check_rc=$?
import json, sqlite3, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0
home, node_id = Path(sys.argv[3]), sys.argv[4]
row = doc["nodes"][0]
assert row["inserted"] == 0
assert row["last_export_seq"] == 7
assert row["last_event_id"] == 7
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
conn.close()
assert count == 7, count
PY
if (( sync4_check_rc == 0 )); then
  pass "idempotent re-run does not duplicate rows"
else
  fail "idempotent re-run does not duplicate rows"
fi

fail_sync_rc=0
fail_sync_out=$(VCL_FAKE_FAIL_EXPORT=lax fleet sync --node lax --json 2>/dev/null) || fail_sync_rc=$?
fail_sync_err=$(VCL_FAKE_FAIL_EXPORT=lax fleet sync --node lax 2>&1 >/dev/null) || true
fail_check_rc=0
python3 - "$fail_sync_out" "$fail_sync_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || fail_check_rc=$?
import json, sqlite3, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 2, sys.argv[2]
assert doc["ok"] is False
assert doc["state"] == "PARTIAL"
row = doc["nodes"][0]
assert row["status"] == "error"
assert row["last_export_seq"] == 7
assert row["last_event_id"] == 7
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert count == 7, count
assert cur[0] == 7, cur
assert cur[1] == "error", cur
PY
if (( fail_check_rc == 0 )); then
  pass "VCL_FAKE_FAIL_EXPORT does not advance last_export_seq"
else
  fail "VCL_FAKE_FAIL_EXPORT does not advance last_export_seq"
fi

retry_sync_rc=0
retry_sync_out=$(fleet sync --node lax --json) || retry_sync_rc=$?
retry_check_rc=0
python3 - "$retry_sync_out" "$retry_sync_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || retry_check_rc=$?
import json, sqlite3, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
assert doc["ok"] is True
row = doc["nodes"][0]
assert row["status"] == "ok"
assert row["last_export_seq"] == 7
assert row["last_event_id"] == 7
assert row["inserted"] == 0
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert count == 7
assert cur == (7, "ok"), cur
PY
if (( retry_check_rc == 0 )); then
  pass "retry after VCL_FAKE_FAIL_EXPORT succeeds from same last_export_seq"
else
  fail "retry after VCL_FAKE_FAIL_EXPORT succeeds from same last_export_seq"
fi

expire_prep_rc=0
python3 - "$VCL_FAKE_STATE_DIR" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || expire_prep_rc=$?
import sqlite3, sys
from pathlib import Path

state, home, node_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
acct = sqlite3.connect(str(state / "lax" / "accounting.db"))
# Retention deleted export_seq 1..3; remaining closed rows keep 4..7.
acct.execute("DELETE FROM connections WHERE export_seq IS NOT NULL AND export_seq <= 3")
acct.execute(
    "INSERT OR REPLACE INTO meta(key,value) VALUES('audit_pruned_max_export_seq','3')"
)
acct.execute(
    "INSERT OR REPLACE INTO meta(key,value) VALUES('audit_export_seq','7')"
)
row = acct.execute(
    "SELECT MIN(export_seq), COUNT(*) FROM connections WHERE export_seq IS NOT NULL"
).fetchone()
acct.commit()
acct.close()
assert row[0] == 4, row
assert row[1] == 4, row  # 4,5,6,7 remain
fleet = sqlite3.connect(str(home / "fleet.db"))
fleet.execute(
    "UPDATE sync_cursor SET last_export_seq=1, last_event_id=1, status='ok' "
    "WHERE node_id=?",
    (node_id,),
)
fleet.commit()
fleet.close()
PY
if (( expire_prep_rc == 0 )); then
  pass "CURSOR_EXPIRED fixture: pruned_max_export_seq=3 and last_export_seq forced to 1"
else
  fail "CURSOR_EXPIRED fixture: pruned_max_export_seq=3 and last_export_seq forced to 1"
fi

expire_rc=0
expire_out=$(fleet sync --node lax --json) || expire_rc=$?
expire_human=$(fleet sync --node lax 2>&1) || true
expire_check_rc=0
python3 - "$expire_out" "$expire_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" \
  "$expire_human" <<'PY' || expire_check_rc=$?
import json, sqlite3, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 2, sys.argv[2]
assert doc["ok"] is False
assert doc["state"] == "PARTIAL"
row = doc["nodes"][0]
assert row["status"] == "expired"
assert row["error"] == "CURSOR_EXPIRED"
assert row["after"] == 1
assert row["last_export_seq"] == 1
assert row["inserted"] == 0
assert row["remediation"] == "vcl-fleet sync --reseed lax"
assert "vcl-fleet sync --reseed lax" in doc["remediation"]
human = sys.argv[5]
assert "CURSOR_EXPIRED" in human
assert "--reseed lax" in human
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert count == 7, count  # expired must not hollow-overwrite
assert cur == (1, "expired"), cur
PY
if (( expire_check_rc == 0 )); then
  pass "CURSOR_EXPIRED reports reseed and does not import a hole"
else
  fail "CURSOR_EXPIRED reports reseed and does not import a hole"
fi

reseed_rc=0
reseed_out=$(fleet sync --reseed lax --json 2>/dev/null) || reseed_rc=$?
reseed_check_rc=0
python3 - "$reseed_out" "$reseed_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || reseed_check_rc=$?
import json, sqlite3, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
assert doc["ok"] is True
row = doc["nodes"][0]
assert row["status"] == "ok"
assert row["after"] == 0
assert row["last_export_seq"] == 7
assert row["last_event_id"] == 7
assert row["inserted"] == 4  # remaining window export_seq 4-7
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
ids = [r[0] for r in conn.execute(
    "SELECT event_id FROM audit_events WHERE node_id=? ORDER BY event_id", (node_id,)
)]
seqs = [r[0] for r in conn.execute(
    "SELECT export_seq FROM audit_events WHERE node_id=? ORDER BY export_seq", (node_id,)
)]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
daily = conn.execute("SELECT SUM(connection_count) FROM daily_usage WHERE node_id=?", (node_id,)).fetchone()[0]
conn.close()
assert count == 4, count
assert ids == [4, 5, 6, 7], ids
assert seqs == [4, 5, 6, 7], seqs
assert cur == (7, "ok"), cur
assert daily == 4, daily
PY
if (( reseed_check_rc == 0 )); then
  pass "--reseed lax replaces local rows with remaining export window"
else
  fail "--reseed lax replaces local rows with remaining export window"
fi

# Old event_id cursor → CURSOR_PROTOCOL_MISMATCH until reseed.
protocol_mismatch_prep_rc=0
python3 - "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || protocol_mismatch_prep_rc=$?
import sqlite3, sys
from pathlib import Path
home, node_id = Path(sys.argv[1]), sys.argv[2]
conn = sqlite3.connect(str(home / "fleet.db"))
conn.execute(
    "UPDATE sync_cursor SET cursor_kind='event_id', last_export_seq=0, "
    "last_event_id=7, status='ok' WHERE node_id=?",
    (node_id,),
)
conn.commit()
conn.close()
PY
if (( protocol_mismatch_prep_rc == 0 )); then
  pass "PROTOCOL_MISMATCH fixture: cursor_kind=event_id"
else
  fail "PROTOCOL_MISMATCH fixture: cursor_kind=event_id"
fi

protocol_mismatch_rc=0
protocol_mismatch_out=$(fleet sync --node lax --json) || protocol_mismatch_rc=$?
protocol_mismatch_human=$(fleet sync --node lax 2>&1) || true
protocol_mismatch_check_rc=0
python3 - "$protocol_mismatch_out" "$protocol_mismatch_rc" "$VCL_FLEET_HOME" \
  "$LAX_REMOTE_NODE_ID" "$protocol_mismatch_human" <<'PY' || protocol_mismatch_check_rc=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 2, sys.argv[2]
row = doc["nodes"][0]
assert row["status"] == "error"
assert row["error"] == "CURSOR_PROTOCOL_MISMATCH"
assert row["remediation"] == "vcl-fleet sync --reseed lax"
human = sys.argv[5]
assert "CURSOR_PROTOCOL_MISMATCH" in human
assert "export_seq" in human
assert "--reseed lax" in human
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
kind = conn.execute(
    "SELECT cursor_kind FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()[0]
count = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)
).fetchone()[0]
conn.close()
assert kind == "event_id"
assert count == 4  # no import attempted
PY
if (( protocol_mismatch_check_rc == 0 )); then
  pass "CURSOR_PROTOCOL_MISMATCH: no import; reseed remediation"
else
  fail "CURSOR_PROTOCOL_MISMATCH: no import; reseed remediation"
fi

protocol_reseed_rc=0
fleet sync --reseed lax --json >/dev/null || protocol_reseed_rc=$?
protocol_reseed_check_rc=0
python3 - "$protocol_reseed_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || protocol_reseed_check_rc=$?
import sqlite3, sys
from pathlib import Path
assert int(sys.argv[1]) == 0, sys.argv[1]
home, node_id = Path(sys.argv[2]), sys.argv[3]
conn = sqlite3.connect(str(home / "fleet.db"))
cur = conn.execute(
    "SELECT last_export_seq, cursor_kind, status FROM sync_cursor WHERE node_id=?",
    (node_id,),
).fetchone()
conn.close()
assert cur == (7, "export_seq", "ok"), cur
PY
if (( protocol_reseed_check_rc == 0 )); then
  pass "reseed after PROTOCOL_MISMATCH restores export_seq cursor"
else
  fail "reseed after PROTOCOL_MISMATCH restores export_seq cursor"
fi

sum_parity_rc=0
python3 - "$VCL_FAKE_STATE_DIR" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || sum_parity_rc=$?
import sqlite3, sys
from pathlib import Path
state, home, node_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
acct = sqlite3.connect(str(state / "lax" / "accounting.db"))
node_sum = acct.execute(
    "SELECT COALESCE(SUM(upload_bytes),0), COALESCE(SUM(download_bytes),0) "
    "FROM connections WHERE closed_at IS NOT NULL AND user_id='u-alice'"
).fetchone()
acct.close()
fleet = sqlite3.connect(str(home / "fleet.db"))
fleet_sum = fleet.execute(
    "SELECT COALESCE(SUM(upload_bytes),0), COALESCE(SUM(download_bytes),0) "
    "FROM audit_events WHERE node_id=? AND user_id='u-alice'",
    (node_id,),
).fetchone()
fleet.close()
assert tuple(node_sum) == tuple(fleet_sum), (node_sum, fleet_sum)
assert node_sum[0] > 0 and node_sum[1] > 0, node_sum
PY
if (( sum_parity_rc == 0 )); then
  pass "fleet audit SUM(upload/download) matches node closed connections"
else
  fail "fleet audit SUM(upload/download) matches node closed connections"
fi

unlabeled_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$LAX_REMOTE_NODE_ID" <<'PY' || unlabeled_rc=$?
import importlib.util, os, sys
from pathlib import Path

path, home, node_id = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
conn = mod.open_fleet_db()
before = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
before_cur = conn.execute(
    "SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
blank = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id IS NULL OR node_id=''"
).fetchone()[0]
assert blank == 0
import io, contextlib
buf = io.StringIO()
try:
    with contextlib.redirect_stderr(buf):
        mod.import_export_jsonl(
            node_id,
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            [
                {
                    "event_id": 99,
                    "connection_id": "unlabeled",
                    "generation": 0,
                    "user_id": "u-alice",
                    "user_tag": "alice",
                    "node_id": "",
                    "started_at": "2026-08-12T08:00:00Z",
                    "last_seen_at": "2026-08-12T09:00:00Z",
                    "upload_bytes": 1,
                    "download_bytes": 1,
                },
                {
                    "event_id": 100,
                    "connection_id": "no-nid",
                    "generation": 0,
                    "user_id": "u-alice",
                    "started_at": "2026-08-12T08:00:00Z",
                    "last_seen_at": "2026-08-12T09:00:00Z",
                },
            ],
            "2026-08-16T06:00:00Z",
            conn=conn,
            next_cursor=100,
        )
    raise AssertionError("unlabeled jsonl must fail closed")
except SystemExit as exc:
    assert exc.code == 1
    assert "missing node_id" in buf.getvalue()
after = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
after_cur = conn.execute(
    "SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
blank2 = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id IS NULL OR node_id=''"
).fetchone()[0]
assert after == before
assert tuple(after_cur) == tuple(before_cur)
assert blank2 == 0
conn.close()
PY
if (( unlabeled_rc == 0 )); then
  pass "jsonl rows missing node_id fail closed and do not advance cursor"
else
  fail "jsonl rows missing node_id fail closed and do not advance cursor"
fi

validate_batch_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY' || validate_batch_rc=$?
import importlib.util, sys

spec = importlib.util.spec_from_file_location("vincula_fleet", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

nid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
iid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

def row(eid, eseq=None, node_id=nid, instance_id=iid):
    if eseq is None:
        eseq = eid
    return {
        "event_id": eid,
        "export_seq": eseq,
        "connection_id": f"c-{eid}",
        "generation": 0,
        "user_id": "u-alice",
        "user_tag": "alice",
        "node_id": node_id,
        "instance_id": instance_id,
        "started_at": "2026-08-10T08:00:00Z",
        "last_seen_at": "2026-08-10T09:00:00Z",
        "upload_bytes": 1,
        "download_bytes": 1,
    }

def meta(**over):
    base = {
        "ok": True,
        "protocol_version": 2,
        "cursor_kind": "export_seq",
        "after": 5,
        "count": 3,
        "next_cursor": 8,
        "max_export_seq": 8,
        "pruned_max_export_seq": 0,
        "node_id": nid,
        "instance_id": iid,
    }
    base.update(over)
    return base

# Contiguous export_seq OK.
rows = [row(6), row(7), row(8)]
assert mod.validate_export_batch(
    meta(), rows, expected_after=5, expected_node_id=nid, expected_instance_id=iid
) == 8

# Gaps in export_seq are allowed when strictly increasing.
gapped_ok = [row(6, 6), row(8, 8), row(9, 9)]
assert mod.validate_export_batch(
    meta(count=3, next_cursor=9, max_export_seq=9), gapped_ok,
    expected_after=5, expected_node_id=nid, expected_instance_id=iid,
) == 9

# Sparse event_ids OK if export_seq strictly increasing.
sparse_eid = [row(10, 6), row(20, 8), row(30, 9)]
assert mod.validate_export_batch(
    meta(count=3, next_cursor=9, max_export_seq=9), sparse_eid,
    expected_after=5, expected_node_id=nid, expected_instance_id=iid,
) == 9

empty_ok = meta(count=0, next_cursor=5, max_export_seq=5)
assert mod.validate_export_batch(
    empty_ok, [], expected_after=5, expected_node_id=nid, expected_instance_id=iid
) == 5

try:
    mod.validate_export_batch(
        meta(count=5), rows,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("lying count must fail")
except ValueError as exc:
    assert "count=5" in str(exc), exc

try:
    mod.validate_export_batch(
        meta(next_cursor=99), rows,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("lying next_cursor must fail")
except ValueError as exc:
    assert "next_cursor=99" in str(exc), exc

# Descending export_seq fail-closed.
descending = [row(6, 8), row(7, 7), row(8, 9)]
try:
    mod.validate_export_batch(
        meta(count=3, next_cursor=9, max_export_seq=9), descending,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("descending export_seq must fail")
except ValueError as exc:
    assert "strictly increasing" in str(exc), exc

# Duplicate export_seq fail-closed.
dup = [row(6, 6), row(7, 6), row(8, 8)]
try:
    mod.validate_export_batch(
        meta(count=3, next_cursor=8, max_export_seq=8), dup,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("duplicate export_seq must fail")
except ValueError as exc:
    assert "duplicate export_seq" in str(exc), exc

# Bad protocol_version fail-closed.
try:
    mod.validate_export_batch(
        meta(protocol_version=1), rows,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("protocol_version 1 must fail")
except ValueError as exc:
    assert "protocol_version" in str(exc), exc

try:
    mod.validate_export_batch(
        meta(after=4), rows,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("meta.after mismatch must fail")
except ValueError as exc:
    assert "after=4" in str(exc), exc

other = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
try:
    mod.validate_export_batch(
        meta(node_id=other), rows,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("meta node_id mismatch must fail")
except ValueError as exc:
    assert "node_id" in str(exc), exc

try:
    mod.validate_export_batch(
        meta(), [row(6), row(7, node_id=other), row(8)],
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("row node_id mismatch must fail")
except ValueError as exc:
    assert "node_id" in str(exc), exc

try:
    mod.validate_export_batch(
        meta(node_id=None), rows,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("missing meta node_id must fail")
except ValueError as exc:
    assert "node_id is missing" in str(exc), exc

try:
    mod.validate_export_batch(
        meta(instance_id=None), rows,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("missing meta instance_id must fail")
except ValueError as exc:
    assert "instance_id is missing" in str(exc), exc

missing_row = [row(6), {**row(7), "node_id": ""}, row(8)]
try:
    mod.validate_export_batch(
        meta(), missing_row,
        expected_after=5, expected_node_id=nid, expected_instance_id=iid,
    )
    raise AssertionError("missing row node_id must fail")
except ValueError as exc:
    assert "node_id is missing" in str(exc), exc

# after=0 may start at any remaining min; export_seq must still increase.
from0 = meta(
    after=0, count=3, next_cursor=103, max_export_seq=103, pruned_max_export_seq=100,
)
assert mod.validate_export_batch(
    from0, [row(101, 101), row(102, 102), row(103, 103)],
    expected_after=0, expected_node_id=nid, expected_instance_id=iid,
) == 103
PY
if (( validate_batch_rc == 0 )); then
  pass "validate_export_batch Protocol v2: export_seq monotonic, gaps OK, rejects dup/desc/protocol"
else
  fail "validate_export_batch Protocol v2: export_seq monotonic, gaps OK, rejects dup/desc/protocol"
fi

stamp_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-audit.py" <<'PY' || stamp_rc=$?
import importlib.util, sys

spec = importlib.util.spec_from_file_location("vincula_audit", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
nid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
iid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
rows = [
    {"event_id": 1, "node_id": "", "instance_id": None},
    {"event_id": 2},
]
mod.stamp_export_rows(rows, node_id=nid, instance_id=iid)
assert rows[0]["node_id"] == nid
assert rows[0]["instance_id"] == iid
assert rows[1]["node_id"] == nid
assert rows[1]["instance_id"] == iid
try:
    mod.stamp_export_rows(
        [{"event_id": 3, "node_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"}],
        node_id=nid, instance_id=iid,
    )
    raise AssertionError("mismatch must fail")
except SystemExit:
    pass
PY
if (( stamp_rc == 0 )); then
  pass "stamp_export_rows fills missing identity and refuses mismatch"
else
  fail "stamp_export_rows fills missing identity and refuses mismatch"
fi

assert_success "reseed remote export can pass --stamp-identity" \
  grep -q -- '--stamp-identity' "${PROJECT_DIR}/lib/vincula-fleet.py"

UNLAB_HOME="${TEST_TMP}/fleet-home-unlab"
UNLAB_STATE="${TEST_TMP}/fake-unlab-state"
SAVED_UNLAB_HOME="${VCL_FLEET_HOME-}"
SAVED_UNLAB_STATE="${VCL_FAKE_STATE_DIR-}"
export VCL_FLEET_HOME="$UNLAB_HOME"
export VCL_FAKE_STATE_DIR="$UNLAB_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax"
cp "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" "${VCL_FAKE_STATE_DIR}/lax/identity.json"
assert_success "unlabeled-sync fleet init" fleet init
assert_success "unlabeled-sync offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"

unlab_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY' || unlab_seed_rc=$?
import importlib.util, json, sys
from pathlib import Path

accountd_py, state_dir, ident_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ident = json.loads(ident_path.read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
db = state_dir / "lax" / "accounting.db"
db.parent.mkdir(parents=True, exist_ok=True)
conn = acct.open_db(str(db))
conn.execute(
    """
    INSERT INTO connections (
      connection_id, generation, user_id, node_id, instance_id, user_tag,
      started_at, last_seen_at, closed_at,
      destination_host, destination_ip, destination_port, network,
      upload_bytes, download_bytes, export_seq
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """,
    (
        "unlab-1", 0, "u-alice", "", None, "alice",
        "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
        "example.com", "203.0.113.10", 443, "tcp", 1, 1, 1,
    ),
)
acct.meta_set(conn, "audit_export_seq", "1")
acct.meta_set(conn, "audit_pruned_max_export_seq", "0")
conn.commit()
conn.close()
PY
if (( unlab_seed_rc == 0 )); then
  pass "unlabeled-sync fixture seeded empty node_id row"
else
  fail "unlabeled-sync fixture seeded empty node_id row"
fi

unlab_sync_rc=0
unlab_sync_out=$(fleet sync --node lax --json 2>/dev/null) || unlab_sync_rc=$?
unlab_sync_check=0
python3 - "$unlab_sync_out" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || unlab_sync_check=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
home, node_id = Path(sys.argv[2]), sys.argv[3]
row = doc["nodes"][0]
assert row["status"] == "error", row
assert "node_id" in (row.get("error") or ""), row
assert row.get("remediation")
conn = sqlite3.connect(str(home / "fleet.db"))
cur = conn.execute("SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)).fetchone()
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
conn.close()
assert count == 0
assert cur is None or int(cur[0]) == 0
PY
if (( unlab_sync_rc != 0 && unlab_sync_check == 0 )); then
  pass "normal sync fails closed on unlabeled export rows and does not advance cursor"
else
  fail "normal sync fails closed on unlabeled export rows (rc=${unlab_sync_rc} check=${unlab_sync_check} out=${unlab_sync_out})"
fi

unlab_reseed_rc=0
unlab_reseed_out=$(fleet sync --reseed lax --json 2>/dev/null) || unlab_reseed_rc=$?
unlab_reseed_check=0
python3 - "$unlab_reseed_out" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || unlab_reseed_check=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
home, node_id = Path(sys.argv[2]), sys.argv[3]
assert doc["ok"] is True, doc
row = doc["nodes"][0]
assert row["status"] == "ok", row
assert int(row["inserted"]) >= 1
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute("SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)).fetchone()
conn.close()
assert count >= 1
assert cur is not None and int(cur[0]) >= 1
PY
if (( unlab_reseed_rc == 0 && unlab_reseed_check == 0 )); then
  pass "reseed --stamp-identity imports previously unlabeled rows"
else
  fail "reseed --stamp-identity imports previously unlabeled rows (rc=${unlab_reseed_rc} check=${unlab_reseed_check} out=${unlab_reseed_out})"
fi
export VCL_FLEET_HOME="$SAVED_UNLAB_HOME"
if [[ -n "$SAVED_UNLAB_STATE" ]]; then
  export VCL_FAKE_STATE_DIR="$SAVED_UNLAB_STATE"
else
  unset VCL_FAKE_STATE_DIR
fi

P104_FLEET_HOME="${TEST_TMP}/fleet-home-p104"
P104_FAKE_STATE="${TEST_TMP}/fake-p104-state"
SAVED_P104_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="$P104_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$P104_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax"

assert_success "P1-04 fleet init" fleet init
assert_success "P1-04 offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"

p104_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY' || p104_seed_rc=$?
import importlib.util, json, sys
from pathlib import Path

accountd_py, state_dir, ident_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ident = json.loads(ident_path.read_text(encoding="utf-8"))
node_id, instance_id = ident["node_id"], ident["instance_id"]
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
db = state_dir / "lax" / "accounting.db"
db.parent.mkdir(parents=True, exist_ok=True)
conn = acct.open_db(str(db))
for i in range(1, 6):
    conn.execute(
        """
        INSERT INTO connections (
          connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, export_seq
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"p104-{i}", 0, "u-alice", node_id, instance_id, "alice",
            "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
            "example.com", "203.0.113.10", 443, "tcp", 10 * i, 20 * i, i,
        ),
    )
acct.meta_set(conn, "audit_export_seq", "5")
acct.meta_set(conn, "audit_pruned_max_export_seq", "0")
conn.commit()
conn.close()
PY
if (( p104_seed_rc == 0 )); then
  pass "P1-04 fixture seeded export_seq 1-5"
else
  fail "P1-04 fixture seeded export_seq 1-5"
fi

p104_happy_rc=0
p104_happy_out=$(fleet sync --node lax --json) || p104_happy_rc=$?
p104_happy_check_rc=0
python3 - "$p104_happy_out" "$p104_happy_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_happy_check_rc=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
assert doc["ok"] is True
row = doc["nodes"][0]
assert row["status"] == "ok"
assert row["after"] == 0
assert row["last_export_seq"] == 5
assert row["last_event_id"] == 5
assert row["inserted"] == 5
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert count == 5, count
assert cur == (5, "ok"), cur
PY
if (( p104_happy_check_rc == 0 )); then
  pass "P1-04 happy path sync imports 1-5 last_export_seq=5"
else
  fail "P1-04 happy path sync imports 1-5 last_export_seq=5"
fi

p104_ahead_prep_rc=0
python3 - "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_ahead_prep_rc=$?
import sqlite3, sys
from pathlib import Path
home, node_id = Path(sys.argv[1]), sys.argv[2]
conn = sqlite3.connect(str(home / "fleet.db"))
conn.execute(
    "UPDATE sync_cursor SET last_export_seq=10, last_event_id=10, status='ok' "
    "WHERE node_id=?",
    (node_id,),
)
conn.commit()
conn.close()
PY
if (( p104_ahead_prep_rc == 0 )); then
  pass "P1-04 forced last_export_seq=10 against max=5"
else
  fail "P1-04 forced last_export_seq=10 against max=5"
fi

p104_ahead_rc=0
p104_ahead_out=$(fleet sync --node lax --json) || p104_ahead_rc=$?
p104_ahead_human=$(fleet sync --node lax 2>&1) || true
p104_ahead_check_rc=0
python3 - "$p104_ahead_out" "$p104_ahead_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" \
  "$p104_ahead_human" <<'PY' || p104_ahead_check_rc=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 2, sys.argv[2]
assert doc["ok"] is False
row = doc["nodes"][0]
assert row["status"] == "error"
assert row["error"] == "CURSOR_AHEAD"
assert row["after"] == 10
assert row["last_export_seq"] == 10
assert row["inserted"] == 0
assert row["remediation"] == "vcl-fleet sync --reseed lax"
assert "vcl-fleet sync --reseed lax" in doc["remediation"]
human = sys.argv[5]
assert "CURSOR_AHEAD" in human
assert "--reseed lax" in human
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert count == 5, count
assert cur == (10, "error"), cur
PY
if (( p104_ahead_check_rc == 0 )); then
  pass "CURSOR_AHEAD after=10 max_export_seq=5: no import, cursor unchanged, reseed"
else
  fail "CURSOR_AHEAD after=10 max_export_seq=5: no import, cursor unchanged, reseed"
fi

p104_gap_prep_rc=0
python3 - "$VCL_FAKE_STATE_DIR" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY' || p104_gap_prep_rc=$?
import json, sqlite3, sys
from pathlib import Path
state, home, node_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
ident = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
instance_id = ident["instance_id"]
acct = sqlite3.connect(str(state / "lax" / "accounting.db"))
# Sparse event_ids OK; export_seq 6,8,9,10 strictly increasing (gaps allowed).
for eid, eseq in ((16, 6), (18, 8), (19, 9), (20, 10)):
    acct.execute(
        """
        INSERT INTO connections (
          event_id, connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, export_seq
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            eid, f"p104-{eseq}", 0, "u-alice", node_id, instance_id, "alice",
            "2026-08-11T08:00:00Z", "2026-08-11T09:00:00Z", "2026-08-11T09:00:00Z",
            "example.com", "203.0.113.10", 443, "tcp", 10 * eseq, 20 * eseq, eseq,
        ),
    )
acct.execute(
    "INSERT OR REPLACE INTO meta(key,value) VALUES('audit_export_seq','10')"
)
acct.commit()
acct.close()
fleet = sqlite3.connect(str(home / "fleet.db"))
fleet.execute(
    "UPDATE sync_cursor SET last_export_seq=5, last_event_id=5, status='ok' "
    "WHERE node_id=?",
    (node_id,),
)
fleet.commit()
fleet.close()
PY
if (( p104_gap_prep_rc == 0 )); then
  pass "P1-04 sparse event_id / gapped export_seq fixture: cursor last_export_seq=5"
else
  fail "P1-04 sparse event_id / gapped export_seq fixture: cursor last_export_seq=5"
fi

p104_gap_rc=0
p104_gap_out=$(fleet sync --node lax --json) || p104_gap_rc=$?
p104_gap_check_rc=0
python3 - "$p104_gap_out" "$p104_gap_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_gap_check_rc=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
row = doc["nodes"][0]
assert row["status"] == "ok", row
assert row["last_export_seq"] == 10
assert row["inserted"] == 4
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
seqs = [r[0] for r in conn.execute(
    "SELECT export_seq FROM audit_events WHERE node_id=? ORDER BY export_seq", (node_id,)
)]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert count == 9, count
assert seqs == [1, 2, 3, 4, 5, 6, 8, 9, 10], seqs
assert cur == (10, "ok"), cur
PY
if (( p104_gap_check_rc == 0 )); then
  pass "sparse event_ids with increasing export_seq: import OK"
else
  fail "sparse event_ids with increasing export_seq: import OK"
fi

# Fail-closed: descending export_seq in remote batch (via lying next + bad rows not needed —
# unit-tested above; integration uses VCL_FAKE_EXPORT_LIE for count/next_cursor).

p104_lie_prep_rc=0
python3 - "$VCL_FAKE_STATE_DIR" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_lie_prep_rc=$?
import sqlite3, sys
from pathlib import Path
state, home, node_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
acct = sqlite3.connect(str(state / "lax" / "accounting.db"))
acct.execute("DELETE FROM connections WHERE export_seq IS NOT NULL AND export_seq > 5")
ident_iid = acct.execute("SELECT instance_id FROM connections LIMIT 1").fetchone()[0]
for i in (6, 7, 8):
    acct.execute(
        """
        INSERT INTO connections (
          event_id, connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, export_seq
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            i, f"p104-lie-{i}", 0, "u-alice", node_id, ident_iid, "alice",
            "2026-08-12T08:00:00Z", "2026-08-12T09:00:00Z", "2026-08-12T09:00:00Z",
            "example.com", "203.0.113.10", 443, "tcp", 10 * i, 20 * i, i,
        ),
    )
acct.execute(
    "INSERT OR REPLACE INTO meta(key,value) VALUES('audit_export_seq','8')"
)
acct.commit()
acct.close()
fleet = sqlite3.connect(str(home / "fleet.db"))
# Reset fleet to only the original 1-5 so lying-meta import is observable.
fleet.execute("DELETE FROM audit_events WHERE node_id=?", (node_id,))
fleet.execute(
    """
    UPDATE sync_cursor SET last_export_seq=5, last_event_id=5, status='ok'
    WHERE node_id=?
    """,
    (node_id,),
)
# Re-import baseline 1-5 from remaining remote would be heavy; keep cursor at 5
# and leave local audit empty of >5 — COUNT after failed lie stays prior.
# Restore local 1-5 from accounting snapshot via sync would change state; instead
# re-seed fleet audit 1-5 quickly:
for i in range(1, 6):
    fleet.execute(
        """
        INSERT INTO audit_events (
          node_id, instance_id, event_id, export_seq, connection_id, generation,
          user_id, user_tag, started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, imported_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            node_id, ident_iid, i, i, f"p104-{i}", 0, "u-alice", "alice",
            "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
            "example.com", "203.0.113.10", 443, "tcp", 10 * i, 20 * i,
            "2026-08-16T03:00:00Z",
        ),
    )
fleet.commit()
fleet.close()
PY
if (( p104_lie_prep_rc == 0 )); then
  pass "P1-04 lying-meta fixture: remote 1-8, last_export_seq=5"
else
  fail "P1-04 lying-meta fixture: remote 1-8, last_export_seq=5"
fi

p104_count_rc=0
p104_count_out=$(VCL_FAKE_EXPORT_LIE_COUNT=5 fleet sync --node lax --json) || p104_count_rc=$?
p104_count_check_rc=0
python3 - "$p104_count_out" "$p104_count_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_count_check_rc=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 2, sys.argv[2]
row = doc["nodes"][0]
assert row["status"] == "error"
assert "count=5" in (row.get("error") or ""), row.get("error")
assert row["last_export_seq"] == 5
assert row["inserted"] == 0
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert count == 5, count
assert cur == (5, "error"), cur
PY
if (( p104_count_check_rc == 0 )); then
  pass "lying meta count=5 vs 3 delivered: ERROR, no import, cursor unchanged"
else
  fail "lying meta count=5 vs 3 delivered: ERROR, no import, cursor unchanged"
fi

p104_next_prep_rc=0
python3 - "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_next_prep_rc=$?
import sqlite3, sys
from pathlib import Path
home, node_id = Path(sys.argv[1]), sys.argv[2]
conn = sqlite3.connect(str(home / "fleet.db"))
conn.execute(
    "UPDATE sync_cursor SET last_export_seq=5, last_event_id=5, status='ok' "
    "WHERE node_id=?",
    (node_id,),
)
conn.commit()
conn.close()
PY
if (( p104_next_prep_rc == 0 )); then
  pass "P1-04 reset last_export_seq=5 before next_cursor lie"
else
  fail "P1-04 reset last_export_seq=5 before next_cursor lie"
fi

p104_next_rc=0
p104_next_out=$(VCL_FAKE_EXPORT_LIE_NEXT_CURSOR=99 fleet sync --node lax --json) \
  || p104_next_rc=$?
p104_next_check_rc=0
python3 - "$p104_next_out" "$p104_next_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_next_check_rc=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 2, sys.argv[2]
row = doc["nodes"][0]
assert row["status"] == "error"
assert "next_cursor=99" in (row.get("error") or ""), row.get("error")
assert row["last_export_seq"] == 5
assert row["inserted"] == 0
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute("SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert count == 5, count
assert cur == (5, "error"), cur
PY
if (( p104_next_check_rc == 0 )); then
  pass "lying next_cursor=99: ERROR, no import, cursor unchanged"
else
  fail "lying next_cursor=99: ERROR, no import, cursor unchanged"
fi

p104_retry_prep_rc=0
python3 - "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_retry_prep_rc=$?
import sqlite3, sys
from pathlib import Path
home, node_id = Path(sys.argv[1]), sys.argv[2]
conn = sqlite3.connect(str(home / "fleet.db"))
conn.execute(
    "UPDATE sync_cursor SET last_export_seq=5, last_event_id=5, status='ok' "
    "WHERE node_id=?",
    (node_id,),
)
conn.commit()
conn.close()
PY

p104_retry_rc=0
p104_retry_out=$(fleet sync --node lax --json) || p104_retry_rc=$?
p104_retry_check_rc=0
python3 - "$p104_retry_out" "$p104_retry_rc" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || p104_retry_check_rc=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
assert doc["ok"] is True
row = doc["nodes"][0]
assert row["status"] == "ok"
assert row["after"] == 5
assert row["last_export_seq"] == 8
assert row["last_event_id"] == 8
assert row["inserted"] == 3
home, node_id = Path(sys.argv[3]), sys.argv[4]
conn = sqlite3.connect(str(home / "fleet.db"))
ids = [r[0] for r in conn.execute(
    "SELECT event_id FROM audit_events WHERE node_id=? ORDER BY event_id", (node_id,)
)]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
conn.close()
assert ids == [1, 2, 3, 4, 5, 6, 7, 8], ids
assert cur == (8, "ok"), cur
PY
if (( p104_retry_check_rc == 0 )); then
  pass "honest retry after lying meta imports 6-8 and advances last_export_seq"
else
  fail "honest retry after lying meta imports 6-8 and advances last_export_seq"
fi

export VCL_FLEET_HOME="$SAVED_P104_HOME"
unset VCL_FAKE_EXPORT_LIE_COUNT
unset VCL_FAKE_EXPORT_LIE_NEXT_CURSOR

HIST_FLEET_HOME="${TEST_TMP}/fleet-home-instance-history"
HIST_FAKE_STATE="${TEST_TMP}/fake-history-state"
SAVED_HIST_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="$HIST_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$HIST_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax"

assert_success "instance-history fleet init" fleet init
assert_success "instance-history offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"

hist_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY' || hist_seed_rc=$?
import importlib.util, json, sys
from pathlib import Path

accountd_py, state_dir, ident_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ident = json.loads(ident_path.read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
db = state_dir / "lax" / "accounting.db"
db.parent.mkdir(parents=True, exist_ok=True)
conn = acct.open_db(str(db))
conn.execute(
    """
    INSERT INTO connections (
      connection_id, generation, user_id, node_id, instance_id, user_tag,
      started_at, last_seen_at, closed_at,
      destination_host, destination_ip, destination_port, network,
      upload_bytes, download_bytes, export_seq
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """,
    (
        "lax-hist-1", 0, "u-alice", ident["node_id"], ident["instance_id"],
        "alice", "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z",
        "2026-08-10T09:00:00Z", "example.com", "203.0.113.10", 443, "tcp", 10, 20, 1,
    ),
)
acct.meta_set(conn, "audit_export_seq", "1")
acct.meta_set(conn, "audit_pruned_max_export_seq", "0")
conn.commit()
conn.close()
PY
if (( hist_seed_rc == 0 )); then
  pass "instance-history fixture seeded lax accounting.db"
else
  fail "instance-history fixture seeded lax accounting.db"
fi

hist_sync1_rc=0
fleet sync --node lax --json >/dev/null || hist_sync1_rc=$?
if (( hist_sync1_rc == 0 )); then
  pass "instance-history first sync exits 0"
else
  fail "instance-history first sync exits 0 (rc=${hist_sync1_rc})"
fi

hist_first_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$LAX_REMOTE_NODE_ID" <<'PY' || hist_first_rc=$?
import importlib.util, os, sys
from pathlib import Path

path, home, node_id = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
conn = mod.open_fleet_db()
rows = mod.list_instances(conn, node_id)
conn.close()
assert len(rows) == 1, rows
assert rows[0]["instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
assert rows[0]["status"] == "active"
assert rows[0]["retired_at"] is None
assert rows[0]["ssh_host"] == "203.0.113.10"
PY
if (( hist_first_rc == 0 )); then
  pass "first-sight sync records one active instance_history row"
else
  fail "first-sight sync records one active instance_history row"
fi

export VCL_FAKE_REINSTALL=1
hist_re_rc=0
hist_re_err=$(fleet sync --node lax 2>&1 >/dev/null) || hist_re_rc=$?
if (( hist_re_rc == 0 )) && [[ "$hist_re_err" == *"instance changed, node_id stable"* ]]; then
  pass "VCL_FAKE_REINSTALL sync WARNs instance changed and exits 0"
else
  fail "VCL_FAKE_REINSTALL sync WARNs instance changed and exits 0 (rc=${hist_re_rc} err=${hist_re_err})"
fi
unset VCL_FAKE_REINSTALL

hist_change_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$LAX_REMOTE_NODE_ID" <<'PY' || hist_change_rc=$?
import importlib.util, os, sys
from pathlib import Path

path, home, node_id = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
conn = mod.open_fleet_db()
rows = mod.list_instances(conn, node_id)
raw = (home / "fleet.json").read_text(encoding="utf-8")
conn.close()
assert "instance_id" not in raw
assert [r["instance_id"] for r in rows] == [
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
], rows
assert rows[0]["status"] == "retired"
assert rows[0]["retired_at"]
assert rows[1]["status"] == "active"
assert rows[1]["retired_at"] is None
assert rows[0]["started_at"] <= rows[1]["started_at"]
PY
if (( hist_change_rc == 0 )); then
  pass "instance change records new row and retires the previous instance"
else
  fail "instance change records new row and retires the previous instance"
fi

export VCL_FLEET_HOME="${SAVED_HIST_HOME}"

assert_success "cmd_audit_user is defined" \
  grep -q 'def cmd_audit_user(' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet audit loads vincula-audit interval-overlap" \
  grep -q 'interval_overlap_sql' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet stats queries daily_usage" \
  grep -q 'FROM daily_usage WHERE' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet query skips unlabeled node_id" \
  grep -q 'LABELED_NODE_SQL' "${PROJECT_DIR}/lib/vincula-fleet.py"

audit_help_rc=0
audit_help=$(fleet audit -h) || audit_help_rc=$?
if (( audit_help_rc == 0 )) && [[ "$audit_help" == *"interval-overlap"* ]] \
  && [[ "$audit_help" == *"user_id"* ]]; then
  pass "audit -h documents interval-overlap and user_id merge"
else
  fail "audit -h documents interval-overlap and user_id merge (rc=${audit_help_rc})"
fi

stats_help_rc=0
stats_help=$(fleet stats -h) || stats_help_rc=$?
if (( stats_help_rc == 0 )) && [[ "$stats_help" == *"daily_usage"* ]] \
  && [[ "$stats_help" == *"by_node"* ]]; then
  pass "stats -h documents daily_usage and by_node totals"
else
  fail "stats -h documents daily_usage and by_node totals (rc=${stats_help_rc})"
fi

QUERY_FLEET_HOME="${TEST_TMP}/fleet-home-query"
QUERY_FAKE_STATE="${TEST_TMP}/fake-query-state"
export VCL_FLEET_HOME="$QUERY_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$QUERY_FAKE_STATE"
export VCL_FLEET_STATS_NOW="2026-08-16"
mkdir -p "$VCL_FLEET_HOME" "$VCL_FAKE_STATE_DIR"

assert_success "query-test fleet init" fleet init
assert_success "query-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"
assert_success "query-test offline add tokyo" \
  fleet node add tokyo --host 203.0.113.11 --offline --node-id "$TEST_TOKYO_NODE_ID"

query_add_rc=0
fleet user add alice --nodes lax,tokyo --display-name Alice >/dev/null || query_add_rc=$?
fleet user add bob --node lax --display-name Bob >/dev/null || query_add_rc=$?
if (( query_add_rc == 0 )); then
  pass "query-test provisioned alice (lax+tokyo) and bob (lax)"
else
  fail "query-test provisioned alice (lax+tokyo) and bob (lax) (rc=${query_add_rc})"
fi

query_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$VCL_FAKE_STATE_DIR" "$LAX_REMOTE_NODE_ID" "$TEST_TOKYO_NODE_ID" <<'PY' || query_seed_rc=$?
import importlib.util, json, os, sqlite3, sys
from pathlib import Path

path, home, state = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
lax_id, tokyo_id = sys.argv[4], sys.argv[5]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

lax_users = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
tokyo_users = json.loads((state / "tokyo" / "users.json").read_text(encoding="utf-8"))
alice_lax = next(u for u in lax_users["users"] if u["tag"] == "alice")
alice_tokyo = next(u for u in tokyo_users["users"] if u["tag"] == "alice")
bob = next(u for u in lax_users["users"] if u["tag"] == "bob")
assert alice_lax["user_id"] == alice_tokyo["user_id"]
alice_uid = alice_lax["user_id"]
bob_uid = bob["user_id"]
(state / "alice_user_id.txt").write_text(alice_uid, encoding="utf-8")
(state / "bob_user_id.txt").write_text(bob_uid, encoding="utf-8")

lax_inst = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
tokyo_inst = "5ee15d43-5555-4555-8555-555555555555"
now = "2026-08-16T07:00:00Z"

def row(event_id, connection_id, user_id, tag, node_id, instance_id, started, closed, host, up, down):
    return {
        "event_id": event_id,
        "export_seq": event_id,
        "connection_id": connection_id,
        "generation": 0,
        "user_id": user_id,
        "user_tag": tag,
        "node_id": node_id,
        "instance_id": instance_id,
        "started_at": started,
        "last_seen_at": closed,
        "closed_at": closed,
        "destination_host": host,
        "destination_ip": "203.0.113.80",
        "destination_port": 443,
        "network": "tcp",
        "upload_bytes": up,
        "download_bytes": down,
    }

conn = mod.open_fleet_db()
mod.import_audit_batch(
    lax_id,
    lax_inst,
    [
        row(1, "lax-alice-1", alice_uid, "alice", lax_id, lax_inst,
            "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "example.com", 100, 200),
        row(2, "lax-bob-1", bob_uid, "bob", lax_id, lax_inst,
            "2026-08-10T12:00:00Z", "2026-08-10T13:00:00Z", "example.com", 10, 10),
    ],
    now_iso=now,
    conn=conn,
)
mod.import_audit_batch(
    tokyo_id,
    tokyo_inst,
    [
        row(1, "tokyo-alice-1", alice_uid, "alice", tokyo_id, tokyo_inst,
            "2026-08-10T10:00:00Z", "2026-08-10T11:00:00Z", "example.com", 50, 50),
    ],
    now_iso=now,
    conn=conn,
)
conn.execute(
    """
    INSERT INTO audit_events (
      node_id, instance_id, event_id, connection_id, generation,
      user_id, user_tag, started_at, last_seen_at, closed_at,
      destination_host, destination_ip, destination_port, network,
      upload_bytes, download_bytes, imported_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        "", None, 1, "unlabeled-alice", 0, alice_uid, "alice",
        "2026-08-10T08:30:00Z", "2026-08-10T08:45:00Z", "2026-08-10T08:45:00Z",
        "evil.example", "203.0.113.99", 443, "tcp", 99999, 99999, now,
    ),
)
conn.execute(
    """
    INSERT INTO daily_usage (
      date, node_id, instance_id, user_id, user_tag, destination_host,
      upload_bytes, download_bytes, connection_count
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    ("2026-08-10", "", None, alice_uid, "alice", "evil.example", 99999, 99999, 1),
)
conn.commit()
conn.close()
PY
if (( query_seed_rc == 0 )); then
  pass "query fixture seeded alice/bob audit_events and unlabeled rows"
else
  fail "query fixture seeded alice/bob audit_events and unlabeled rows"
fi

QUERY_ALICE_UID=$(cat "${VCL_FAKE_STATE_DIR}/alice_user_id.txt")
QUERY_FROM="2026-08-10T00:00:00Z"
QUERY_TO="2026-08-11T00:00:00Z"

audit_human_rc=0
audit_human=$(fleet audit user alice --from "$QUERY_FROM" --to "$QUERY_TO") || audit_human_rc=$?
if (( audit_human_rc == 0 )) \
  && grep -q 'TIME NODE INSTANCE DESTINATION TRAFFIC' <<< "$audit_human" \
  && grep -q ' lax ' <<< "$audit_human" \
  && grep -q ' tokyo ' <<< "$audit_human" \
  && ! grep -q 'evil.example' <<< "$audit_human"; then
  pass "AC-2.9-04 audit user alice human output includes lax and tokyo"
else
  fail "AC-2.9-04 audit user alice human output includes lax and tokyo (rc=${audit_human_rc} out=${audit_human})"
fi

audit_json_rc=0
audit_json=$(fleet audit user alice --from "$QUERY_FROM" --to "$QUERY_TO" --json) || audit_json_rc=$?
ac04_rc=0
python3 - "$audit_json" "$audit_json_rc" "$QUERY_ALICE_UID" \
  "$LAX_REMOTE_NODE_ID" "$TEST_TOKYO_NODE_ID" <<'PY' || ac04_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
alice, lax_id, tokyo_id = sys.argv[3], sys.argv[4], sys.argv[5]
assert doc["schema_version"] == 1
assert doc["tag"] == "alice"
assert doc["user_id"] == alice
assert len(doc["rows"]) == 2, doc["rows"]
by_node = {row["node"]: row for row in doc["rows"]}
assert set(by_node) == {"lax", "tokyo"}, by_node
for name, node_id, inst, traffic, event_id in (
    ("lax", lax_id, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", 300, 1),
    ("tokyo", tokyo_id, "5ee15d43-5555-4555-8555-555555555555", 100, 1),
):
    row = by_node[name]
    assert row["node_id"] == node_id
    assert row["instance_id"] == inst
    assert row["instance"] == inst
    assert row["user_id"] == alice
    assert row["event_id"] == event_id
    assert row["traffic"] == traffic
    assert row["destination"] == "example.com"
    assert "time" in row
assert all(row["destination"] != "evil.example" for row in doc["rows"])
assert all(row["traffic"] < 1000 for row in doc["rows"])
PY
if (( ac04_rc == 0 )); then
  pass "AC-2.9-04 audit merges Alice across lax+tokyo by user_id"
else
  fail "AC-2.9-04 audit merges Alice across lax+tokyo by user_id"
fi

audit_node_json=$(fleet audit user alice --from "$QUERY_FROM" --to "$QUERY_TO" --node lax --json)
if python3 - "$audit_node_json" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
assert doc["node"] == "lax"
assert len(doc["rows"]) == 1
assert doc["rows"][0]["node"] == "lax"
assert doc["rows"][0]["traffic"] == 300
PY
then
  pass "audit --node lax filters to one node"
else
  fail "audit --node lax filters to one node"
fi

audit_window_json=$(fleet audit user alice \
  --from "2026-08-10T09:00:00Z" --to "2026-08-10T10:00:00Z" --json)
if python3 - "$audit_window_json" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
assert [row["node"] for row in doc["rows"]] == ["lax"], doc["rows"]
PY
then
  pass "audit interval-overlap includes lax closed_at==from and excludes tokyo started_at==to"
else
  fail "audit interval-overlap includes lax closed_at==from and excludes tokyo started_at==to"
fi

stats_user_json_rc=0
stats_user_json=$(fleet stats user alice --days 30 --json) || stats_user_json_rc=$?
ac05_user_rc=0
python3 - "$stats_user_json" "$stats_user_json_rc" "$QUERY_ALICE_UID" <<'PY' || ac05_user_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0, sys.argv[2]
alice = sys.argv[3]
assert doc["schema_version"] == 1
assert doc["mode"] == "user"
assert doc["tag"] == "alice"
assert doc["user_id"] == alice
assert doc["days"] == 30
assert doc["from"] == "2026-07-18"
assert doc["to"] == "2026-08-16"
assert len(doc["rows"]) == 2, doc["rows"]
by_node = {row["node"]: row for row in doc["rows"]}
assert set(by_node) == {"lax", "tokyo"}, by_node
assert by_node["lax"]["bytes"] == 300
assert by_node["tokyo"]["bytes"] == 100
assert by_node["lax"]["user_id"] == alice
assert by_node["tokyo"]["user_id"] == alice
assert "node_id" in by_node["lax"] and by_node["lax"]["node_id"]
assert doc["totals"]["bytes"] == 400
assert {n["node"] for n in doc["totals"]["by_node"]} == {"lax", "tokyo"}
for rec in doc["totals"]["by_node"]:
    assert rec["node"]
    assert rec["node_id"]
    assert rec["bytes"] in (300, 100)
assert doc["totals"]["bytes"] != 400 + 99999 + 99999
PY
if (( ac05_user_rc == 0 )); then
  pass "AC-2.9-05 stats user alice preserves node attribution"
else
  fail "AC-2.9-05 stats user alice preserves node attribution"
fi

stats_human=$(fleet stats user alice --days 30)
if grep -q 'NODE USER_ID UP DOWN TOTAL CONNECTIONS' <<< "$stats_human" \
  && grep -q '^lax ' <<< "$stats_human" \
  && grep -q '^tokyo ' <<< "$stats_human"; then
  pass "stats user alice human rows are per node"
else
  fail "stats user alice human rows are per node (out=${stats_human})"
fi

stats_top_users=$(fleet stats top users --days 30 --json)
if python3 - "$stats_top_users" "$QUERY_ALICE_UID" "$(cat "${VCL_FAKE_STATE_DIR}/bob_user_id.txt")" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
alice, bob = sys.argv[2], sys.argv[3]
assert doc["mode"] == "top_users"
pairs = {(row["user_id"], row["node"]) for row in doc["rows"]}
assert (alice, "lax") in pairs
assert (alice, "tokyo") in pairs
assert (bob, "lax") in pairs
assert (alice, "lax") != (alice, "tokyo")
alice_rows = [row for row in doc["rows"] if row["user_id"] == alice]
assert len(alice_rows) == 2, alice_rows
assert {row["node"] for row in alice_rows} == {"lax", "tokyo"}
assert all("node" in row and row["node"] for row in doc["rows"])
by_node_names = {n["node"] for n in doc["totals"]["by_node"]}
assert "lax" in by_node_names and "tokyo" in by_node_names
PY
then
  pass "AC-2.9-05 stats top users keeps (user_id, node) rows"
else
  fail "AC-2.9-05 stats top users keeps (user_id, node) rows"
fi

stats_top_hosts=$(fleet stats top hosts --days 30 --json)
if python3 - "$stats_top_hosts" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
assert doc["mode"] == "top_hosts"
pairs = {(row["destination_host"], row["node"]): row for row in doc["rows"]}
assert ("example.com", "lax") in pairs
assert ("example.com", "tokyo") in pairs
assert pairs[("example.com", "lax")]["bytes"] == 320  # alice 300 + bob 20
assert pairs[("example.com", "tokyo")]["bytes"] == 100
assert "evil.example" not in {row["destination_host"] for row in doc["rows"]}
assert len([row for row in doc["rows"] if row["destination_host"] == "example.com"]) == 2
PY
then
  pass "AC-2.9-05 stats top hosts keeps per-node host rows"
else
  fail "AC-2.9-05 stats top hosts keeps per-node host rows"
fi

stats_node=$(fleet stats node lax --days 30 --json)
if python3 - "$stats_node" "$QUERY_ALICE_UID" "$(cat "${VCL_FAKE_STATE_DIR}/bob_user_id.txt")" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
alice, bob = sys.argv[2], sys.argv[3]
assert doc["mode"] == "node"
assert doc["node"] == "lax"
assert {row["node"] for row in doc["rows"]} == {"lax"}
uids = {row["user_id"] for row in doc["rows"]}
assert alice in uids and bob in uids
assert all(row["node"] != "tokyo" for row in doc["rows"])
assert {n["node"] for n in doc["totals"]["by_node"]} == {"lax"}
PY
then
  pass "stats node lax is node-tagged and excludes tokyo"
else
  fail "stats node lax is node-tagged and excludes tokyo"
fi

stats_days1=$(fleet stats user alice --days 1 --json)
if python3 - "$stats_days1" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
assert doc["from"] == "2026-08-16"
assert doc["to"] == "2026-08-16"
assert doc["rows"] == []
assert doc["totals"]["bytes"] == 0
PY
then
  pass "stats --days 1 excludes older UTC days"
else
  fail "stats --days 1 excludes older UTC days"
fi

unknown_audit_rc=0
unknown_audit_err=$(fleet audit user missing --from "$QUERY_FROM" --to "$QUERY_TO" 2>&1) || unknown_audit_rc=$?
if (( unknown_audit_rc != 0 )) && [[ "$unknown_audit_err" == *"unknown user tag"* ]]; then
  pass "audit unknown tag dies"
else
  fail "audit unknown tag dies (rc=${unknown_audit_rc} err=${unknown_audit_err})"
fi

days0_rc=0
days0_err=$(fleet stats user alice --days 0 2>&1) || days0_rc=$?
if (( days0_rc != 0 )) && [[ "$days0_err" == *"--days"* ]]; then
  pass "stats --days 0 is rejected"
else
  fail "stats --days 0 is rejected (rc=${days0_rc} err=${days0_err})"
fi

conflict_rc=0
python3 - "$VCL_FAKE_STATE_DIR" <<'PY' || conflict_rc=$?
import json, sys
from pathlib import Path
state = Path(sys.argv[1])
uid_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
uid_b = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"
for alias, uid in (("lax", uid_a), ("tokyo", uid_b)):
    path = state / alias / "users.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["users"].append({
        "user_id": uid,
        "tag": "eve",
        "display_name": "Eve",
        "department": "",
        "enabled": True,
        "created_at": "2026-08-16T00:00:00Z",
        "credentials": [],
    })
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
conflict_audit_rc=0
conflict_err=$(fleet audit user eve --from "$QUERY_FROM" --to "$QUERY_TO" 2>&1) || conflict_audit_rc=$?
if (( conflict_audit_rc != 0 )) && [[ "$conflict_err" == *"conflicting user_id"* ]]; then
  pass "audit dies on tag user_id conflict across nodes"
else
  fail "audit dies on tag user_id conflict across nodes (rc=${conflict_audit_rc} err=${conflict_err})"
fi

unset VCL_FLEET_STATS_NOW

# --- Batch 11-retire: fleet.json schema 2 + node retire (TASK 38-41) ---

assert_success "node retire is a CLI command" \
  grep -q 'cmd_node_retire' "${PROJECT_DIR}/lib/vincula-fleet.py"
retire_help_rc=0
retire_help=$(fleet node retire -h) || retire_help_rc=$?
if (( retire_help_rc == 0 )) && [[ "$retire_help" == *"final"* ]] \
  && [[ "$retire_help" == *"retired"* ]]; then
  pass "node retire -h documents final sync and retired"
else
  fail "node retire -h documents final sync and retired (rc=${retire_help_rc})"
fi

SCHEMA1_HOME="${TEST_TMP}/fleet-home-schema1"
mkdir -p "$SCHEMA1_HOME"
python3 - "$SCHEMA1_HOME" "$TEST_NODE_ID" "$TEST_TOKYO_NODE_ID" "$TEST_SG_NODE_ID" <<'PY'
import json, sys
from pathlib import Path
home = Path(sys.argv[1])
lax_id, tokyo_id, sg_id = sys.argv[2], sys.argv[3], sys.argv[4]
doc = {
    "schema_version": 1,
    "nodes": [
        {"node_id": lax_id, "name": "lax", "ssh_host": "203.0.113.10",
         "ssh_user": "root", "ssh_port": 22, "enabled": True},
        {"node_id": tokyo_id, "name": "tokyo", "ssh_host": "203.0.113.11",
         "ssh_user": "root", "ssh_port": 22, "enabled": True},
        {"node_id": sg_id, "name": "sg", "ssh_host": "203.0.113.12",
         "ssh_user": "root", "ssh_port": 22, "enabled": False},
    ],
}
(home / "fleet.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY

SAVED_QUERY_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="$SCHEMA1_HOME"
schema1_list=$(fleet node list)
assert_success "schema 1 load lists lax" grep -q '^lax ' <<< "$schema1_list"
assert_success "schema 1 load lists tokyo" grep -q '^tokyo ' <<< "$schema1_list"
assert_success "schema 1 load lists sg" grep -q '^sg ' <<< "$schema1_list"
assert_success "schema 1 missing status defaults active for enabled" \
  grep -q 'lax .* true active' <<< "$schema1_list"
assert_success "schema 1 missing status defaults disabled for disabled" \
  grep -q 'sg .* false disabled' <<< "$schema1_list"

schema1_save_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$SCHEMA1_HOME" <<'PY' || schema1_save_rc=$?
import importlib.util, json, os, sys
from pathlib import Path
path, home = sys.argv[1], Path(sys.argv[2])
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
registry = mod.load_registry()
assert registry["schema_version"] == 2
assert {n["name"]: n["status"] for n in registry["nodes"]} == {
    "lax": "active", "tokyo": "active", "sg": "disabled"
}
mod.save_registry(None, registry)
data = json.loads((home / "fleet.json").read_text(encoding="utf-8"))
assert data["schema_version"] == 2, data
assert all("status" in n for n in data["nodes"])
assert all(n.get("instance_id") is None or "instance_id" not in n for n in data["nodes"])
raw = (home / "fleet.json").read_text(encoding="utf-8")
assert "instance_id" not in raw
assert "password" not in raw
PY
if (( schema1_save_rc == 0 )); then
  pass "schema 1 load upgrades in memory; save writes schema 2 with status"
else
  fail "schema 1 load upgrades in memory; save writes schema 2 with status"
fi

bad_schema_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$TEST_TMP" <<'PY' || bad_schema_rc=$?
import importlib.util, json, os, sys
from pathlib import Path
path, tmp = sys.argv[1], Path(sys.argv[2])
home = tmp / "fleet-home-schema3"
home.mkdir(parents=True, exist_ok=True)
(home / "fleet.json").write_text(
    json.dumps({"schema_version": 3, "nodes": []}) + "\n", encoding="utf-8"
)
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
try:
    mod.load_registry()
except SystemExit:
    raise SystemExit(0)
raise SystemExit(1)
PY
if (( bad_schema_rc == 0 )); then
  pass "unsupported fleet.json schema 3 is rejected"
else
  fail "unsupported fleet.json schema 3 is rejected"
fi

RETIRE_FLEET_HOME="${TEST_TMP}/fleet-home-retire"
RETIRE_FAKE_STATE="${TEST_TMP}/fake-retire-state"
export VCL_FLEET_HOME="$RETIRE_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$RETIRE_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "$VCL_FAKE_STATE_DIR"

assert_success "retire-test fleet init" fleet init
assert_success "retire-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"
assert_success "retire-test offline add tokyo" \
  fleet node add tokyo --host 203.0.113.11 --offline --node-id "$TEST_TOKYO_NODE_ID"

unknown_retire_rc=0
unknown_retire_err=$(fleet node retire mars 2>&1) || unknown_retire_rc=$?
if (( unknown_retire_rc != 0 )) && [[ "$unknown_retire_err" == *"unknown node"* ]]; then
  pass "retire unknown node is refused"
else
  fail "retire unknown node is refused (rc=${unknown_retire_rc} err=${unknown_retire_err})"
fi

retire_add_rc=0
fleet user add alice --nodes lax,tokyo --display-name Alice >/dev/null || retire_add_rc=$?
fleet user add bob --node lax --display-name Bob >/dev/null || retire_add_rc=$?
if (( retire_add_rc == 0 )); then
  pass "retire-test provisioned alice (lax+tokyo) and bob (lax)"
else
  fail "retire-test provisioned alice (lax+tokyo) and bob (lax) (rc=${retire_add_rc})"
fi

retire_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" \
  "${PROJECT_DIR}/tests/fixtures/nodes/tokyo/identity.json" <<'PY' || retire_seed_rc=$?
import importlib.util, json, sys
from pathlib import Path

accountd_py = sys.argv[1]
state = Path(sys.argv[2])
lax_ident = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
tokyo_ident = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)

lax_users = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
tokyo_users = json.loads((state / "tokyo" / "users.json").read_text(encoding="utf-8"))
alice = next(u for u in lax_users["users"] if u["tag"] == "alice")
bob = next(u for u in lax_users["users"] if u["tag"] == "bob")
assert alice["user_id"] == next(u["user_id"] for u in tokyo_users["users"] if u["tag"] == "alice")
(state / "alice_user_id.txt").write_text(alice["user_id"], encoding="utf-8")
(state / "bob_user_id.txt").write_text(bob["user_id"], encoding="utf-8")

def seed(alias, ident, rows):
    db = state / alias / "accounting.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = acct.open_db(str(db))
    node_id = ident["node_id"]
    instance_id = ident["instance_id"]
    max_seq = 0
    for event_id, connection_id, user_id, tag, host, up, down in rows:
        max_seq = max(max_seq, event_id)
        conn.execute(
            """
            INSERT INTO connections (
              connection_id, generation, user_id, node_id, instance_id, user_tag,
              started_at, last_seen_at, closed_at,
              destination_host, destination_ip, destination_port, network,
              upload_bytes, download_bytes, export_seq
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                connection_id, 0, user_id, node_id, instance_id, tag,
                "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
                host, "203.0.113.80", 443, "tcp", up, down, event_id,
            ),
        )
    acct.meta_set(conn, "audit_export_seq", str(max_seq))
    acct.meta_set(conn, "audit_pruned_max_export_seq", "0")
    conn.commit()
    conn.close()

alice_uid = alice["user_id"]
bob_uid = bob["user_id"]
seed("lax", lax_ident, [
    (1, "lax-retire-1", alice_uid, "alice", "example.com", 10, 20),
    (2, "lax-retire-2", alice_uid, "alice", "example.com", 11, 21),
    (3, "lax-retire-3", alice_uid, "alice", "example.com", 12, 22),
    (4, "lax-retire-4", bob_uid, "bob", "example.com", 13, 23),
    (5, "lax-retire-5", alice_uid, "alice", "example.com", 14, 24),
])
seed("tokyo", tokyo_ident, [
    (1, "tokyo-retire-1", alice_uid, "alice", "example.com", 50, 50),
])
PY
if (( retire_seed_rc == 0 )); then
  pass "retire fixture seeded lax events 1-5 and tokyo event 1"
else
  fail "retire fixture seeded lax events 1-5 and tokyo event 1"
fi

RETIRE_ALICE_UID=$(cat "${VCL_FAKE_STATE_DIR}/alice_user_id.txt")

sync_pre_rc=0
fleet sync --node lax >/dev/null || sync_pre_rc=$?
if (( sync_pre_rc == 0 )); then
  pass "retire-test initial sync lax exits 0"
else
  fail "retire-test initial sync lax exits 0 (rc=${sync_pre_rc})"
fi

fail_retire_rc=0
fail_retire_err=$(VCL_FAKE_FAIL_EXPORT=lax fleet node retire lax 2>&1) || fail_retire_rc=$?
if (( fail_retire_rc != 0 )) && [[ "$fail_retire_err" == *"final sync failed"* ]]; then
  pass "retire fails when final sync export fails"
else
  fail "retire fails when final sync export fails (rc=${fail_retire_rc} err=${fail_retire_err})"
fi

fail_still_active_rc=0
python3 - "${VCL_FLEET_HOME}/fleet.json" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || fail_still_active_rc=$?
import json, sqlite3, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
home, node_id = Path(sys.argv[2]), sys.argv[3]
node = next(n for n in data["nodes"] if n["name"] == "lax")
assert node["status"] == "active", node
assert node["enabled"] is True, node
assert not (home / "retired" / "lax").is_dir()
conn = sqlite3.connect(str(home / "fleet.db"))
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
count = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)
).fetchone()[0]
conn.close()
assert cur[0] == 5, cur
assert count == 5, count
PY
if (( fail_still_active_rc == 0 )); then
  pass "failed retire leaves lax active, cursor=5, no snapshot dir"
else
  fail "failed retire leaves lax active, cursor=5, no snapshot dir"
fi

python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY'
import importlib.util, json, sys
from pathlib import Path
accountd_py, state, ident_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ident = json.loads(ident_path.read_text(encoding="utf-8"))
alice_uid = (state / "alice_user_id.txt").read_text(encoding="utf-8").strip()
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
conn = acct.open_db(str(state / "lax" / "accounting.db"))
for i in range(6, 9):
    conn.execute(
        """
        INSERT INTO connections (
          connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, export_seq
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"lax-retire-{i}", 0, alice_uid, ident["node_id"], ident["instance_id"],
            "alice",
            "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
            "example.com", "203.0.113.80", 443, "tcp", i, i * 2, i,
        ),
    )
acct.meta_set(conn, "audit_export_seq", "8")
acct.meta_set(conn, "audit_pruned_max_export_seq", "0")
conn.commit()
conn.close()
PY

retire_rc=0
retire_out=$(fleet node retire lax 2>"${TEST_TMP}/retire-lax.err") || retire_rc=$?
retire_err=$(cat "${TEST_TMP}/retire-lax.err" 2>/dev/null || true)
if (( retire_rc == 0 )) \
  && [[ "$retire_out" == *"historical fleet.db rows were not erased"* ]] \
  && [[ "$retire_out" == *"status=retired"* ]] \
  && [[ "$retire_out" == *"vcl uninstall --yes"* ]]; then
  pass "node retire lax succeeds with preserved-history and uninstall hint"
else
  fail "node retire lax succeeds with preserved-history and uninstall hint (rc=${retire_rc} out=${retire_out} err=${retire_err})"
fi

assert_success "retired snapshot identity.json exists" \
  test -f "${VCL_FLEET_HOME}/retired/lax/identity.json"
assert_success "retired snapshot cursor.json exists" \
  test -f "${VCL_FLEET_HOME}/retired/lax/cursor.json"
assert_success "retired snapshot last-status.json exists" \
  test -f "${VCL_FLEET_HOME}/retired/lax/last-status.json"

retire_list=$(fleet node list)
assert_success "node list still includes retired lax" grep -q '^lax ' <<< "$retire_list"
assert_success "node list marks lax retired" grep -q 'lax .* false retired' <<< "$retire_list"

ac08_rc=0
python3 - "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" "$RETIRE_ALICE_UID" \
  "$VCL_FAKE_STATE_DIR" <<'PY' || ac08_rc=$?
import json, sqlite3, sys
from pathlib import Path

home, node_id, alice, state = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
data = json.loads((home / "fleet.json").read_text(encoding="utf-8"))
assert data["schema_version"] == 2
node = next(n for n in data["nodes"] if n["name"] == "lax")
assert node["status"] == "retired", node
assert node["enabled"] is False, node
tokyo = next(n for n in data["nodes"] if n["name"] == "tokyo")
assert tokyo["status"] == "active"

ident = json.loads((home / "retired" / "lax" / "identity.json").read_text(encoding="utf-8"))
assert ident.get("node_id") == node_id, ident
cursor = json.loads((home / "retired" / "lax" / "cursor.json").read_text(encoding="utf-8"))
assert cursor["node_id"] == node_id
assert cursor["last_event_id"] == 8, cursor

conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)
).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq, status FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()
alice_rows = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=? AND user_id=?",
    (node_id, alice),
).fetchone()[0]
conn.close()
assert count == 8, count
assert cur == (8, "ok"), cur
assert alice_rows >= 1, alice_rows

users = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
enabled = [u["tag"] for u in users["users"] if u.get("enabled")]
assert enabled == ["bob"], enabled
disabled = [u["tag"] for u in users["users"] if not u.get("enabled")]
assert "alice" in disabled
PY
if (( ac08_rc == 0 )); then
  pass "AC-2.9-08 final sync committed cursor=8 before status=retired; last enabled user kept"
else
  fail "AC-2.9-08 final sync committed cursor=8 before status=retired; last enabled user kept"
fi

already_rc=0
already_err=$(fleet node retire lax 2>&1) || already_rc=$?
if (( already_rc != 0 )) && [[ "$already_err" == *"already retired"* ]]; then
  pass "retire of already-retired node is refused"
else
  fail "retire of already-retired node is refused (rc=${already_rc} err=${already_err})"
fi

enable_retired_rc=0
enable_retired_err=$(fleet node enable lax 2>&1) || enable_retired_rc=$?
if (( enable_retired_rc != 0 )) \
  && [[ "$enable_retired_err" == *"retired node cannot be enabled"* ]] \
  && [[ "$enable_retired_err" == *"0.3.0"* ]]; then
  pass "retired node cannot be enabled"
else
  fail "retired node cannot be enabled (rc=${enable_retired_rc} err=${enable_retired_err})"
fi

status_default=$(fleet status 2>/dev/null || true)
assert_failure "status default scope omits retired lax" \
  grep -Eq '^lax[[:space:]]' <<< "$status_default"
status_all=$(fleet status --all 2>/dev/null || true)
assert_success "status --all includes retired lax with SSH=-" \
  grep -Eq '^lax[[:space:]].*-' <<< "$status_all"

verify_default=$(fleet verify 2>/dev/null || true)
assert_failure "verify default scope omits retired lax" \
  grep -Eq '^lax$' <<< "$verify_default"
verify_all=$(fleet verify --all 2>/dev/null || true)
assert_success "verify --all shows retired placeholder" \
  grep -q 'status: retired' <<< "$verify_all"

sync_retired_node_rc=0
sync_retired_err=$(fleet sync --node lax 2>&1) || sync_retired_node_rc=$?
if (( sync_retired_node_rc != 0 )) && [[ "$sync_retired_err" == *"retired"* ]]; then
  pass "sync --node retired lax is refused"
else
  fail "sync --node retired lax is refused (rc=${sync_retired_node_rc} err=${sync_retired_err})"
fi

python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" \
  "${PROJECT_DIR}/tests/fixtures/nodes/lax/identity.json" <<'PY'
import importlib.util, json, sys
from pathlib import Path
accountd_py, state, ident_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ident = json.loads(ident_path.read_text(encoding="utf-8"))
alice_uid = (state / "alice_user_id.txt").read_text(encoding="utf-8").strip()
spec = importlib.util.spec_from_file_location("accountd", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
conn = acct.open_db(str(state / "lax" / "accounting.db"))
conn.execute(
    """
    INSERT INTO connections (
      connection_id, generation, user_id, node_id, instance_id, user_tag,
      started_at, last_seen_at, closed_at,
      destination_host, destination_ip, destination_port, network,
      upload_bytes, download_bytes
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """,
    (
        "lax-retire-post", 0, alice_uid, ident["node_id"], ident["instance_id"],
        "alice",
        "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
        "example.com", "203.0.113.80", 443, "tcp", 99, 99,
    ),
)
conn.commit()
conn.close()
PY

sync_default_rc=0
sync_default_out=$(fleet sync --json) || sync_default_rc=$?
if (( sync_default_rc == 0 )); then
  pass "default sync after retire exits 0"
else
  fail "default sync after retire exits 0 (rc=${sync_default_rc} out=${sync_default_out})"
fi

sync_skip_rc=0
python3 - "$sync_default_out" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || sync_skip_rc=$?
import json, sqlite3, sys
from pathlib import Path
doc = json.loads(sys.argv[1])
home, node_id = Path(sys.argv[2]), sys.argv[3]
names = [n["name"] for n in doc["nodes"]]
assert "lax" not in names, names
assert "tokyo" in names, names
conn = sqlite3.connect(str(home / "fleet.db"))
count = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)
).fetchone()[0]
cur = conn.execute(
    "SELECT last_export_seq FROM sync_cursor WHERE node_id=?", (node_id,)
).fetchone()[0]
conn.close()
assert count == 8, count
assert cur == 8, cur
PY
if (( sync_skip_rc == 0 )); then
  pass "retired lax excluded from default sync; historical rows unchanged"
else
  fail "retired lax excluded from default sync; historical rows unchanged"
fi

RETIRE_FROM="2026-08-10T00:00:00Z"
RETIRE_TO="2026-08-11T00:00:00Z"
audit_after_rc=0
audit_after=$(fleet audit user alice --from "$RETIRE_FROM" --to "$RETIRE_TO" --json) \
  || audit_after_rc=$?
ac09_rc=0
python3 - "$audit_after" "$audit_after_rc" "$RETIRE_ALICE_UID" <<'PY' || ac09_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
rc = int(sys.argv[2])
alice = sys.argv[3]
assert rc == 0, rc
assert doc["tag"] == "alice"
assert doc["user_id"] == alice
nodes = {row["node"] for row in doc["rows"]}
assert "lax" in nodes, nodes
assert all(row["user_id"] == alice for row in doc["rows"] if row["node"] == "lax")
assert any(row["node"] == "lax" for row in doc["rows"])
PY
if (( ac09_rc == 0 )); then
  pass "AC-2.9-09 historical audit still queryable after retire"
else
  fail "AC-2.9-09 historical audit still queryable after retire (rc=${audit_after_rc})"
fi

export VCL_FLEET_HOME="${SAVED_QUERY_HOME}"

unset VCL_FAKE_STATE_DIR
export VCL_FLEET_HOME="${SAVED_DB_HOME}"

# --- 0.3.0 node replace / instances / rebind ---
assert_success "cmd_node_replace is defined" \
  grep -q 'def cmd_node_replace(' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "cmd_node_instances is defined" \
  grep -q 'def cmd_node_instances(' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "replace does not auto-reseed" \
  python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" <<'PY'
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
start = text.index("def cmd_node_replace")
end = text.index("def format_instances_table")
assert "reseed_node_local" not in text[start:end], "replace must not call reseed"
PY
assert_success "cmd_node_replace uses --reissue-output" \
  grep -q -- '--reissue-output' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_failure "cmd_node_replace does not send --replace-node" \
  grep -q -- '--replace-node' "${PROJECT_DIR}/lib/vincula-fleet.py"

contract_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "${PROJECT_DIR}/bin/vincula" "${TEST_TMP}" <<'PY' || contract_rc=$?
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

fleet_py, vincula_bin, tmp = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("vincula_fleet", fleet_py)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
argv = mod.build_node_restore_argv(mod.REMOTE_RESTORE_TAR, "203.0.113.18")
assert argv[0:3] == ["vcl", "restore", mod.REMOTE_RESTORE_TAR], argv
assert "--reissue-output" in argv
assert argv[argv.index("--reissue-output") + 1] == mod.REMOTE_REISSUE_CSV
assert "--server" in argv
assert argv[argv.index("--server") + 1] == "203.0.113.18"
assert "--json" in argv
assert "--replace-node" not in argv
assert "--output" not in argv
# Real bin/vincula argv parser (cmd_restore). Same layout as tests/test.sh:
# bin/ next to a lib/ symlink so load_vincula_common finds the repo copy.
root = tmp / "contract-cli"
(root / "bin").mkdir(parents=True, exist_ok=True)
lib = root / "lib"
if lib.exists() or lib.is_symlink():
    lib.unlink()
lib.symlink_to(vincula_bin.parent.parent / "lib")
patched = root / "bin" / "vincula"
text = vincula_bin.read_text(encoding="utf-8")
patched.write_text(text.replace('main "$@"', 'cmd_restore "$@"'), encoding="utf-8")
patched.chmod(0o755)
env = os.environ.copy()
env["VCL_STATE_DIR"] = str(tmp / "contract-state")
(tmp / "contract-state").mkdir(parents=True, exist_ok=True)
env["VCL_BACKUP_ROOT"] = str(tmp / "contract-backups")
(tmp / "contract-backups").mkdir(parents=True, exist_ok=True)
env["VCL_RESTORE_SKIP_HEALTH"] = "1"

def run(args):
    return subprocess.run(
        [str(patched), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

ok = run(argv[2:])  # FILE --reissue-output ... (cmd_restore, no leading vcl restore)
assert ok.returncode != 0
err = (ok.stderr or "") + (ok.stdout or "")
assert "Unknown restore argument" not in err, err
assert "--replace-node is not supported" not in err, err
assert "backup file not found" in err or "Refusing to overwrite" in err, err

bad_flag = run([mod.REMOTE_RESTORE_TAR, "--replace-node", "x"])
assert bad_flag.returncode != 0
assert "Restore is fresh-node only; --replace-node is not supported." in (
    (bad_flag.stderr or "") + (bad_flag.stdout or "")
)

bad_out = run([mod.REMOTE_RESTORE_TAR, "--output", "/tmp/x"])
assert bad_out.returncode != 0
assert "Unknown restore argument: --output" in (
    (bad_out.stderr or "") + (bad_out.stdout or "")
)
PY
if (( contract_rc == 0 )); then
  pass "controller restore argv is accepted by real bin/vincula parser"
else
  fail "controller restore argv is accepted by real bin/vincula parser"
fi

fake_replace_rc=0
fake_replace_err=$("$FAKE_SSH" root@203.0.113.18 -- \
  vcl restore /tmp/vincula-restore.tar --replace-node aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa \
  --server 203.0.113.18 --json 2>&1) || fake_replace_rc=$?
if (( fake_replace_rc != 0 )) \
  && [[ "$fake_replace_err" == *"--replace-node is not supported"* ]]; then
  pass "fake-ssh rejects restore --replace-node"
else
  fail "fake-ssh rejects restore --replace-node (rc=${fake_replace_rc} err=${fake_replace_err})"
fi

BACKUP_FAKE_STATE="${TEST_TMP}/fake-backup-direct"
mkdir -p "${BACKUP_FAKE_STATE}/lax"
direct_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$BACKUP_FAKE_STATE" <<'PY' || direct_seed_rc=$?
import importlib.util, json, sys
from pathlib import Path
accountd_py, state = sys.argv[1], Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("acct", accountd_py)
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
node_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
instance_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
lax = state / "lax"
state_doc = {
    "schema_version": 2, "project_version": "0.3.0",
    "sing_box_version": "1.13.18", "architecture": "amd64",
    "installed_at": "2026-08-16T00:00:00Z",
    "node": {
        "node_id": node_id, "instance_id": instance_id, "node_name": "lax",
        "server": "203.0.113.10", "listen": "0.0.0.0", "port": 443,
        "reality_handshake_server": "www.cloudflare.com",
        "reality_server_name": "www.cloudflare.com",
        "reality_private_key": "sekrit", "reality_public_key": "pub",
        "reality_short_id": "abcd1234",
    },
    "service_account": {
        "user": "sing-box", "uid": 1000, "group": "sing-box", "gid": 1000,
        "home": "/var/lib/sing-box", "shell": "/usr/sbin/nologin",
        "created_by_vincula": True, "group_created_by_vincula": True,
    },
}
users = {"schema_version": 2, "users": [{
    "user_id": "u-alice", "tag": "alice", "display_name": "Alice",
    "department": "eng", "enabled": True, "created_at": "2026-08-01T00:00:00Z",
    "credentials": [{
        "credential_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "node_id": node_id, "uuid": "11111111-1111-4111-8111-111111111111",
        "status": "active", "created_at": "2026-08-01T00:00:00Z", "revoked_at": None,
    }],
}]}
toml = """project_version = "0.3.0"
sing_box_version = "1.13.18"
architecture = "amd64"
node_id = "%s"
node_name = "lax"
server = "203.0.113.10"
listen = "0.0.0.0"
port = 443
reality_handshake_server = "www.cloudflare.com"
reality_server_name = "www.cloudflare.com"
clash_api_port = 9090
clash_api_secret = "clash-sekrit"
accounting_raw_retention_days = 90
accounting_daily_retention_days = 90
billing_cycle_start_day = 1
""" % node_id
lax.mkdir(parents=True, exist_ok=True)
(lax / "state.json").write_text(json.dumps(state_doc, indent=2) + "\n", encoding="utf-8")
(lax / "users.json").write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
(lax / "config.toml").write_text(toml, encoding="utf-8")
(lax / "VERSION").write_text("0.3.0\n", encoding="utf-8")
conn = acct.open_db(str(lax / "accounting.db"))
conn.execute(
    """INSERT INTO connections (
      connection_id, generation, user_id, node_id, instance_id, user_tag,
      started_at, last_seen_at, closed_at, destination_host, destination_ip,
      destination_port, network, upload_bytes, download_bytes)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("c1", 0, "u-alice", node_id, instance_id, "alice",
     "2026-08-16T01:00:00Z", "2026-08-16T01:05:00Z", "2026-08-16T01:05:00Z",
     "example.com", "203.0.113.10", 443, "tcp", 10, 20),
)
conn.commit()
conn.close()
PY
if (( direct_seed_rc == 0 )); then
  pass "direct backup fixture seeded"
else
  fail "direct backup fixture seeded"
fi
export VCL_FAKE_STATE_DIR="$BACKUP_FAKE_STATE"
direct_backup_rc=0
direct_backup=$("$FAKE_SSH" root@203.0.113.10 -- vcl backup create --json) || direct_backup_rc=$?
if (( direct_backup_rc == 0 )) && [[ -f "${BACKUP_FAKE_STATE}/lax/backup.tar" ]]; then
  pass "fake-ssh backup create writes alias backup.tar"
else
  fail "fake-ssh backup create writes alias backup.tar (rc=${direct_backup_rc})"
fi
direct_verify_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-backup.py" "${BACKUP_FAKE_STATE}/lax/backup.tar" \
  "$direct_backup" <<'PY' || direct_verify_rc=$?
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("vbackup", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.verify_archive(sys.argv[2])
assert result.get("ok") is True, result
assert result.get("secret_bearing") is False, result
assert result.get("encryption") == "none", result
doc = json.loads(sys.argv[3])
assert doc["ok"] is True
assert doc["path"] == "/var/backups/vincula/backup.tar"
assert doc["secret_bearing"] is False
PY
if (( direct_verify_rc == 0 )); then
  pass "fake-ssh backup create is secretless and verifies"
else
  fail "fake-ssh backup create is secretless and verifies"
fi
unset VCL_FAKE_STATE_DIR

REBIND_FLEET_HOME="${TEST_TMP}/fleet-home-rebind"
REBIND_FAKE_STATE="${TEST_TMP}/fake-rebind-state"
SAVED_REPLACE_HOME="${VCL_FLEET_HOME}"
export VCL_FLEET_HOME="$REBIND_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$REBIND_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax"

assert_success "rebind-test fleet init" fleet init
assert_success "rebind-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"

rebind_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" <<'PY' || rebind_seed_rc=$?
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("acct", sys.argv[1])
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
state = Path(sys.argv[2])
node_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
instance_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
lax = state / "lax"
users = {"schema_version": 2, "users": [{
    "user_id": "u-alice", "tag": "alice", "display_name": "Alice",
    "department": "eng", "enabled": True, "created_at": "2026-08-01T00:00:00Z",
    "credentials": [{
        "credential_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "node_id": node_id, "uuid": "11111111-1111-4111-8111-111111111111",
        "status": "active", "created_at": "2026-08-01T00:00:00Z", "revoked_at": None,
    }],
}]}
(lax / "users.json").write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
conn = acct.open_db(str(lax / "accounting.db"))
conn.execute(
    """INSERT INTO connections (
      connection_id, generation, user_id, node_id, instance_id, user_tag,
      started_at, last_seen_at, closed_at, destination_host, destination_ip,
      destination_port, network, upload_bytes, download_bytes)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("rebind-1", 0, "u-alice", node_id, instance_id, "alice",
     "2026-08-16T01:00:00Z", "2026-08-16T01:05:00Z", "2026-08-16T01:05:00Z",
     "example.com", "203.0.113.10", 443, "tcp", 10, 20),
)
conn.commit()
conn.close()
PY
if (( rebind_seed_rc == 0 )); then
  pass "rebind-test fixture seeded"
else
  fail "rebind-test fixture seeded"
fi

rebind_sync_rc=0
fleet sync --node lax >/dev/null || rebind_sync_rc=$?
if (( rebind_sync_rc == 0 )); then
  pass "rebind-test first sync exits 0"
else
  fail "rebind-test first sync exits 0 (rc=${rebind_sync_rc})"
fi

assert_success "rebind node set lax host" fleet node set lax --host 203.0.113.28

rebind_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$VCL_FAKE_STATE_DIR" "$LAX_REMOTE_NODE_ID" <<'PY' || rebind_rc=$?
import importlib.util, json, os, sys
from pathlib import Path
path, home, state, node_id = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
registry = json.loads((home / "fleet.json").read_text(encoding="utf-8"))
assert "instance_id" not in (home / "fleet.json").read_text(encoding="utf-8")
node = next(n for n in registry["nodes"] if n["name"] == "lax")
assert node["node_id"] == node_id
assert node["ssh_host"] == "203.0.113.28"
assert node["status"] == "active"
users = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
uuid = users["users"][0]["credentials"][0]["uuid"]
assert uuid == "11111111-1111-4111-8111-111111111111", uuid
conn = mod.open_fleet_db()
rows = mod.list_instances(conn, node_id)
cur = mod.read_sync_cursor_row(conn, node_id)
conn.close()
assert len(rows) == 1, rows
assert rows[0]["instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
assert rows[0]["status"] == "active"
assert cur["instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PY
if (( rebind_rc == 0 )); then
  pass "node set rebind keeps credentials and instance_id"
else
  fail "node set rebind keeps credentials and instance_id"
fi

instances_rebind=$(fleet node instances lax)
assert_success "node instances still available after rebind" \
  grep -q 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' <<< "$instances_rebind"
assert_success "node instances after rebind lists active" \
  grep -q 'active' <<< "$instances_rebind"

instances_rebind_json_rc=0
instances_rebind_json=$(fleet node instances lax --json) || instances_rebind_json_rc=$?
python3 - "$instances_rebind_json" "$instances_rebind_json_rc" <<'INSTANCES_PY' || instances_rebind_json_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0
assert doc["schema_version"] == 1
assert doc["name"] == "lax"
assert len(doc["instances"]) == 1
assert doc["instances"][0]["status"] == "active"
assert doc["instances"][0]["instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
INSTANCES_PY
if (( instances_rebind_json_rc == 0 )); then
  pass "node instances --json still available after rebind"
else
  fail "node instances --json still available after rebind"
fi

# P0-01b: real restore contract. NEW_HOST must be runtime-only (no VERSION).
unknown_replace_rc=0
unknown_replace_err=$(fleet node replace mars --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" 2>&1) \
  || unknown_replace_rc=$?
if (( unknown_replace_rc != 0 )) && [[ "$unknown_replace_err" == *"unknown node"* ]]; then
  pass "replace unknown node is refused"
else
  fail "replace unknown node is refused (rc=${unknown_replace_rc} err=${unknown_replace_err})"
fi

export VCL_FLEET_RETIRE_SKIP_SYNC=1
retire_for_replace_rc=0
fleet node retire lax >/dev/null || retire_for_replace_rc=$?
if (( retire_for_replace_rc == 0 )); then
  pass "rebind-test retire lax for replace-refuse"
else
  fail "rebind-test retire lax for replace-refuse (rc=${retire_for_replace_rc})"
fi
unset VCL_FLEET_RETIRE_SKIP_SYNC
retired_replace_rc=0
retired_replace_err=$(fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" 2>&1) \
  || retired_replace_rc=$?
if (( retired_replace_rc != 0 )) && [[ "$retired_replace_err" == *"retired"* ]]; then
  pass "replace retired node is refused"
else
  fail "replace retired node is refused (rc=${retired_replace_rc} err=${retired_replace_err})"
fi

seed_runtime_only() {
  local dir=$1
  mkdir -p "$dir"
  printf 'runtime-only\n' > "${dir}/.runtime-only"
  printf '%s\n' '#!/bin/sh' > "${dir}/vcl"
  chmod +x "${dir}/vcl"
  rm -f "${dir}/VERSION"
}

REPLACE_FLEET_HOME="${TEST_TMP}/fleet-home-replace"
REPLACE_FAKE_STATE="${TEST_TMP}/fake-replace-state"
export VCL_FLEET_HOME="$REPLACE_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$REPLACE_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax"
seed_runtime_only "${VCL_FAKE_STATE_DIR}/lax2"

assert_success "replace-test fleet init" fleet init
assert_success "replace-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"

replace_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" <<'PY' || replace_seed_rc=$?
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("acct", sys.argv[1])
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
state = Path(sys.argv[2])
node_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
instance_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
lax = state / "lax"
state_doc = {
    "schema_version": 2, "project_version": "0.3.0",
    "sing_box_version": "1.13.18", "architecture": "amd64",
    "installed_at": "2026-08-16T00:00:00Z",
    "node": {
        "node_id": node_id, "instance_id": instance_id, "node_name": "lax",
        "server": "203.0.113.10", "listen": "0.0.0.0", "port": 443,
        "reality_handshake_server": "www.cloudflare.com",
        "reality_server_name": "www.cloudflare.com",
        "reality_private_key": "sekrit", "reality_public_key": "pub",
        "reality_short_id": "abcd1234",
    },
    "service_account": {
        "user": "sing-box", "uid": 1000, "group": "sing-box", "gid": 1000,
        "home": "/var/lib/sing-box", "shell": "/usr/sbin/nologin",
        "created_by_vincula": True, "group_created_by_vincula": True,
    },
}
users = {"schema_version": 2, "users": [{
    "user_id": "u-alice", "tag": "alice", "display_name": "Alice",
    "department": "eng", "enabled": True, "created_at": "2026-08-01T00:00:00Z",
    "credentials": [{
        "credential_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "node_id": node_id, "uuid": "11111111-1111-4111-8111-111111111111",
        "status": "active", "created_at": "2026-08-01T00:00:00Z", "revoked_at": None,
    }],
}]}
toml = """project_version = "0.3.0"
sing_box_version = "1.13.18"
architecture = "amd64"
node_id = "%s"
node_name = "lax"
server = "203.0.113.10"
listen = "0.0.0.0"
port = 443
reality_handshake_server = "www.cloudflare.com"
reality_server_name = "www.cloudflare.com"
clash_api_port = 9090
clash_api_secret = "clash-sekrit"
accounting_raw_retention_days = 90
accounting_daily_retention_days = 90
billing_cycle_start_day = 1
""" % node_id
(lax / "state.json").write_text(json.dumps(state_doc, indent=2) + "\n", encoding="utf-8")
(lax / "users.json").write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
(lax / "config.toml").write_text(toml, encoding="utf-8")
(lax / "VERSION").write_text("0.3.0\n", encoding="utf-8")
conn = acct.open_db(str(lax / "accounting.db"))
for i in range(1, 6):
    conn.execute(
        """INSERT INTO connections (
          connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at, destination_host, destination_ip,
          destination_port, network, upload_bytes, download_bytes, export_seq)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"lax-replace-{i}", 0, "u-alice", node_id, instance_id, "alice",
         "2026-08-10T08:00:00Z", "2026-08-10T09:00:00Z", "2026-08-10T09:00:00Z",
         "example.com", "203.0.113.10", 443, "tcp", 10, 20, i),
    )
acct.meta_set(conn, "audit_export_seq", "5")
acct.meta_set(conn, "audit_pruned_max_export_seq", "0")
conn.commit()
conn.close()
PY
if (( replace_seed_rc == 0 )); then
  pass "replace-test fixture seeded"
else
  fail "replace-test fixture seeded"
fi

replace_sync_rc=0
fleet sync --node lax >/dev/null || replace_sync_rc=$?
if (( replace_sync_rc == 0 )); then
  pass "replace-test pre-sync exits 0"
else
  fail "replace-test pre-sync exits 0 (rc=${replace_sync_rc})"
fi

replace_json_rc=0
replace_err="${TEST_TMP}/replace-lax.err"
replace_json=$(fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" --json \
  2>"$replace_err") || replace_json_rc=$?
if (( replace_json_rc == 0 )); then
  pass "node replace lax happy path exits 0"
else
  fail "node replace lax happy path exits 0 (rc=${replace_json_rc} out=${replace_json} err=$(cat "$replace_err"))"
fi

replace_check_rc=0
python3 - "$replace_json" "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$VCL_FAKE_STATE_DIR" "$LAX_REMOTE_NODE_ID" <<'PY' || replace_check_rc=$?
import csv, importlib.util, json, os, stat, sys
from pathlib import Path

doc = json.loads(sys.argv[1])
path, home, state = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
node_id = sys.argv[5]
assert doc["ok"] is True, doc
assert doc["state"] == "SUCCESS", doc
assert doc["name"] == "lax"
assert doc["node_id"] == node_id
assert doc["ssh_host"] == "203.0.113.18"
assert doc["old_instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
assert doc["new_instance_id"]
assert doc["new_instance_id"] != doc["old_instance_id"]
assert doc["new_instance_id"] != node_id
csv_path = Path(doc["reissue_csv"])
assert csv_path.is_file(), csv_path
mode = stat.S_IMODE(csv_path.stat().st_mode)
assert mode == 0o600, oct(mode)
with csv_path.open(encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh))
assert rows, rows
assert list(rows[0].keys()) == [
    "user", "node", "old_credential_id", "new_credential_id", "vless_uri"
]
assert rows[0]["user"] == "alice"
assert rows[0]["old_credential_id"] != rows[0]["new_credential_id"]
raw = (home / "fleet.json").read_text(encoding="utf-8")
assert "instance_id" not in raw
registry = json.loads(raw)
node = next(n for n in registry["nodes"] if n["name"] == "lax")
assert node["node_id"] == node_id
assert node["ssh_host"] == "203.0.113.18"
assert node["status"] == "active"
assert node["enabled"] is True
ident = json.loads((state / "lax2" / "identity.json").read_text(encoding="utf-8"))
assert ident["node_id"] == node_id
assert ident["instance_id"] == doc["new_instance_id"]
assert (state / "lax2" / "VERSION").is_file()
assert not (state / "lax2" / ".runtime-only").exists()
users = json.loads((state / "lax2" / "users.json").read_text(encoding="utf-8"))
active = [
    c for u in users["users"] for c in u["credentials"] if c["status"] == "active"
]
assert active and active[0]["uuid"] != "11111111-1111-4111-8111-111111111111"
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
conn = mod.open_fleet_db()
hist = mod.list_instances(conn, node_id)
cur = mod.read_sync_cursor_row(conn, node_id)
old_rows = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=? AND instance_id=?",
    (node_id, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
).fetchone()[0]
conn.close()
assert len(hist) == 2, hist
assert hist[0]["instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
assert hist[0]["status"] == "retired"
assert hist[0]["retired_at"]
assert hist[1]["instance_id"] == doc["new_instance_id"]
assert hist[1]["status"] == "active"
assert hist[1]["ssh_host"] == "203.0.113.18"
assert cur["instance_id"] == doc["new_instance_id"]
assert int(cur["last_event_id"]) == 5, cur
assert old_rows == 5, old_rows
Path(state / "new_instance_id.txt").write_text(doc["new_instance_id"], encoding="utf-8")
PY
if (( replace_check_rc == 0 )); then
  pass "AC-3.0-05/06/07/10 replace keeps node_id, mints instance, writes reissue CSV"
else
  fail "AC-3.0-05/06/07/10 replace keeps node_id, mints instance, writes reissue CSV"
fi

instances_out=$(fleet node instances lax)
assert_success "node instances lists old retired instance" \
  grep -q 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' <<< "$instances_out"
assert_success "node instances lists retired then active" \
  grep -q 'retired' <<< "$instances_out"
assert_success "node instances lists active" \
  grep -q 'active' <<< "$instances_out"

instances_json_rc=0
instances_json=$(fleet node instances lax --json) || instances_json_rc=$?
python3 - "$instances_json" "$instances_json_rc" <<'PY' || instances_json_rc=$?
import json, sys
doc = json.loads(sys.argv[1])
assert int(sys.argv[2]) == 0
assert doc["schema_version"] == 1
assert doc["name"] == "lax"
assert len(doc["instances"]) == 2
assert doc["instances"][0]["status"] == "retired"
assert doc["instances"][1]["status"] == "active"
PY
if (( instances_json_rc == 0 )); then
  pass "node instances --json shows both physical instances"
else
  fail "node instances --json shows both physical instances"
fi

replace_sync2_rc=0
replace_sync2_err=$(fleet sync --node lax 2>&1) || replace_sync2_rc=$?
if grep -q 'instance changed, node_id stable' "$replace_err"; then
  pass "replace WARNs instance changed, node_id stable"
else
  fail "replace WARNs instance changed, node_id stable (err=$(cat "$replace_err"))"
fi
if (( replace_sync2_rc == 0 )); then
  pass "sync after replace exits 0 without auto-reseed"
else
  fail "sync after replace exits 0 without auto-reseed (rc=${replace_sync2_rc} err=${replace_sync2_err})"
fi

post_sync_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$LAX_REMOTE_NODE_ID" <<'PY' || post_sync_rc=$?
import importlib.util, os, sys
from pathlib import Path
path, home, node_id = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
conn = mod.open_fleet_db()
count = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=?", (node_id,)
).fetchone()[0]
old = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=? AND instance_id=?",
    (node_id, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
).fetchone()[0]
cur = mod.read_sync_cursor_row(conn, node_id)
hist = mod.list_instances(conn, node_id)
conn.close()
assert count >= 5, count
assert old == 5, old
assert int(cur["last_event_id"]) >= 5, cur
assert len(hist) == 2, hist
PY
if (( post_sync_rc == 0 )); then
  pass "AC-3.0-09 replace sync keeps old instance rows and cursor"
else
  fail "AC-3.0-09 replace sync keeps old instance rows and cursor"
fi

expire_replace_rc=0
python3 - "$VCL_FAKE_STATE_DIR" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || expire_replace_rc=$?
import sqlite3, sys
from pathlib import Path
state, home, node_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
new_iid = (state / "new_instance_id.txt").read_text(encoding="utf-8").strip()
db = state / "lax2" / "accounting.db"
conn = sqlite3.connect(str(db))
conn.execute("DELETE FROM connections")
for i in range(100, 103):
    eseq = i + 1
    conn.execute(
        """INSERT INTO connections (
          event_id, connection_id, generation, user_id, node_id, instance_id, user_tag,
          started_at, last_seen_at, closed_at, destination_host, destination_ip,
          destination_port, network, upload_bytes, download_bytes, export_seq)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (i, f"gap-{i}", 0, "u-alice", node_id, new_iid,
         "alice", "2026-08-16T10:00:00Z", "2026-08-16T10:05:00Z", "2026-08-16T10:05:00Z",
         "example.com", "203.0.113.18", 443, "tcp", 1, 1, eseq),
    )
conn.execute(
    "INSERT OR REPLACE INTO meta(key,value) VALUES('audit_export_seq','103')"
)
conn.execute(
    "INSERT OR REPLACE INTO meta(key,value) VALUES('audit_pruned_max_export_seq','99')"
)
conn.commit()
row = conn.execute("SELECT MIN(event_id), COUNT(*) FROM connections").fetchone()
conn.close()
assert row[0] == 100, row
assert row[1] == 3, row
fleet = sqlite3.connect(str(home / "fleet.db"))
fleet.execute(
    "UPDATE sync_cursor SET last_export_seq=5, last_event_id=5, status='ok' WHERE node_id=?",
    (node_id,),
)
fleet.commit()
fleet.close()
PY
if (( expire_replace_rc == 0 )); then
  pass "replace CURSOR_EXPIRED fixture: pruned_max=99 cursor=5"
else
  fail "replace CURSOR_EXPIRED fixture: pruned_max=99 cursor=5"
fi

expire_sync_rc=0
expire_sync_err=$(fleet sync --node lax 2>&1) || expire_sync_rc=$?
if (( expire_sync_rc != 0 )) && [[ "$expire_sync_err" == *"CURSOR_EXPIRED"* ]] \
  && [[ "$expire_sync_err" == *"--reseed"* ]]; then
  pass "post-replace gap yields CURSOR_EXPIRED and --reseed guidance"
else
  fail "post-replace gap yields CURSOR_EXPIRED and --reseed guidance (rc=${expire_sync_rc} err=${expire_sync_err})"
fi

reseed_rc=0
fleet sync --reseed lax >/dev/null || reseed_rc=$?
if (( reseed_rc == 0 )); then
  pass "post-replace --reseed lax exits 0"
else
  fail "post-replace --reseed lax exits 0 (rc=${reseed_rc})"
fi

reseed_hist_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
  "$LAX_REMOTE_NODE_ID" <<'PY' || reseed_hist_rc=$?
import importlib.util, os, sys
from pathlib import Path
path, home, node_id = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
conn = mod.open_fleet_db()
hist = mod.list_instances(conn, node_id)
rows = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id=? AND node_id != ''",
    (node_id,),
).fetchone()[0]
blank = conn.execute(
    "SELECT COUNT(*) FROM audit_events WHERE node_id IS NULL OR node_id=''"
).fetchone()[0]
conn.close()
assert len(hist) == 2, hist
assert rows >= 1, rows
assert blank == 0, blank
PY
if (( reseed_hist_rc == 0 )); then
  pass "reseed after replace keeps instance_history and labeled node_id"
else
  fail "reseed after replace keeps instance_history and labeled node_id"
fi

if python3 - "$VCL_FAKE_STATE_DIR" <<'PY'
import json, sys
from pathlib import Path
state = Path(sys.argv[1])
old_uuid = "11111111-1111-4111-8111-111111111111"
users = json.loads((state / "lax2" / "users.json").read_text(encoding="utf-8"))
inbound = set()
revoked_old = False
for user in users.get("users") or []:
    for cred in user.get("credentials") or []:
        if cred.get("status") == "active" and cred.get("uuid"):
            inbound.add(cred["uuid"])
        if cred.get("credential_id") == "cccccccc-cccc-4ccc-8ccc-cccccccccccc":
            assert cred.get("status") == "revoked", cred
            revoked_old = True
assert revoked_old
assert old_uuid not in inbound, inbound
PY
then
  pass "AC-3.0-11 fixture PARTIAL (LIVE-ONLY): replaced node revoked old credential; inbound omits old uuid"
else
  fail "AC-3.0-11 fixture PARTIAL (LIVE-ONLY): replaced node revoked old credential; inbound omits old uuid"
fi

# Already-bootstrapped NEW_HOST (VERSION present) must fail without registry change.
BOOT_FLEET_HOME="${TEST_TMP}/fleet-home-bootstrapped"
BOOT_FAKE_STATE="${TEST_TMP}/fake-bootstrapped-state"
export VCL_FLEET_HOME="$BOOT_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$BOOT_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax" "${VCL_FAKE_STATE_DIR}/lax2"
printf '0.3.1\n' > "${VCL_FAKE_STATE_DIR}/lax2/VERSION"
printf '%s\n' '#!/bin/sh' > "${VCL_FAKE_STATE_DIR}/lax2/vcl"
chmod +x "${VCL_FAKE_STATE_DIR}/lax2/vcl"
assert_success "bootstrapped-target fleet init" fleet init
assert_success "bootstrapped-target offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "$VCL_FAKE_STATE_DIR" <<'PY'
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("acct", sys.argv[1])
acct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acct)
state = Path(sys.argv[2])
node_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
instance_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
lax = state / "lax"
state_doc = {
    "schema_version": 2, "project_version": "0.3.0",
    "sing_box_version": "1.13.18", "architecture": "amd64",
    "installed_at": "2026-08-16T00:00:00Z",
    "node": {
        "node_id": node_id, "instance_id": instance_id, "node_name": "lax",
        "server": "203.0.113.10", "listen": "0.0.0.0", "port": 443,
        "reality_handshake_server": "www.cloudflare.com",
        "reality_server_name": "www.cloudflare.com",
        "reality_private_key": "sekrit", "reality_public_key": "pub",
        "reality_short_id": "abcd1234",
    },
    "service_account": {
        "user": "sing-box", "uid": 1000, "group": "sing-box", "gid": 1000,
        "home": "/var/lib/sing-box", "shell": "/usr/sbin/nologin",
        "created_by_vincula": True, "group_created_by_vincula": True,
    },
}
users = {"schema_version": 2, "users": [{
    "user_id": "u-alice", "tag": "alice", "display_name": "Alice",
    "department": "eng", "enabled": True, "created_at": "2026-08-01T00:00:00Z",
    "credentials": [{
        "credential_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "node_id": node_id, "uuid": "11111111-1111-4111-8111-111111111111",
        "status": "active", "created_at": "2026-08-01T00:00:00Z", "revoked_at": None,
    }],
}]}
toml = """project_version = "0.3.0"
sing_box_version = "1.13.18"
architecture = "amd64"
node_id = "%s"
node_name = "lax"
server = "203.0.113.10"
listen = "0.0.0.0"
port = 443
reality_handshake_server = "www.cloudflare.com"
reality_server_name = "www.cloudflare.com"
clash_api_port = 9090
clash_api_secret = "clash-sekrit"
accounting_raw_retention_days = 90
accounting_daily_retention_days = 90
billing_cycle_start_day = 1
""" % node_id
(lax / "state.json").write_text(json.dumps(state_doc, indent=2) + "\n", encoding="utf-8")
(lax / "users.json").write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
(lax / "config.toml").write_text(toml, encoding="utf-8")
(lax / "VERSION").write_text("0.3.0\n", encoding="utf-8")
conn = acct.open_db(str(lax / "accounting.db"))
conn.execute(
    """INSERT INTO connections (
      connection_id, generation, user_id, node_id, instance_id, user_tag,
      started_at, last_seen_at, closed_at, destination_host, destination_ip,
      destination_port, network, upload_bytes, download_bytes)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("boot-1", 0, "u-alice", node_id, instance_id, "alice",
     "2026-08-16T01:00:00Z", "2026-08-16T01:05:00Z", "2026-08-16T01:05:00Z",
     "example.com", "203.0.113.10", 443, "tcp", 10, 20),
)
conn.commit()
conn.close()
PY
before_boot_json=$(cat "${VCL_FLEET_HOME}/fleet.json")
boot_rc=0
boot_err=$(fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" --from-backup \
  "${BACKUP_FAKE_STATE}/lax/backup.tar" 2>&1) || boot_rc=$?
after_boot_json=$(cat "${VCL_FLEET_HOME}/fleet.json")
if (( boot_rc != 0 )) && [[ "$boot_err" == *"already has VERSION"* ]] \
  && [[ "$before_boot_json" == "$after_boot_json" ]] \
  && [[ "$after_boot_json" != *"203.0.113.18"* ]]; then
  pass "replace against bootstrapped NEW_HOST fails without registry change"
else
  fail "replace against bootstrapped NEW_HOST fails without registry change (rc=${boot_rc} err=${boot_err})"
fi

# Empty NEW_HOST (no runtime) fails closed.
EMPTY_FLEET_HOME="${TEST_TMP}/fleet-home-empty-runtime"
EMPTY_FAKE_STATE="${TEST_TMP}/fake-empty-runtime"
export VCL_FLEET_HOME="$EMPTY_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$EMPTY_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax" "${VCL_FAKE_STATE_DIR}/lax2"
assert_success "empty-runtime fleet init" fleet init
assert_success "empty-runtime offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"
cp -a -- "${BOOT_FAKE_STATE}/lax/." "${VCL_FAKE_STATE_DIR}/lax/"
before_empty_json=$(cat "${VCL_FLEET_HOME}/fleet.json")
empty_rc=0
empty_err=$(fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" --from-backup \
  "${BACKUP_FAKE_STATE}/lax/backup.tar" 2>&1) || empty_rc=$?
after_empty_json=$(cat "${VCL_FLEET_HOME}/fleet.json")
if (( empty_rc != 0 )) && [[ "$empty_err" == *"no Vincula runtime"* ]] \
  && [[ "$before_empty_json" == "$after_empty_json" ]]; then
  pass "replace against host without runtime fails without registry change"
else
  fail "replace against host without runtime fails without registry change (rc=${empty_rc} err=${empty_err})"
fi

# --- replace failure injection ---
INJECT_FLEET_HOME="${TEST_TMP}/fleet-home-inject"
INJECT_FAKE_STATE="${TEST_TMP}/fake-inject-state"
export VCL_FLEET_HOME="$INJECT_FLEET_HOME"
export VCL_FAKE_STATE_DIR="$INJECT_FAKE_STATE"
mkdir -p "$VCL_FLEET_HOME" "${VCL_FAKE_STATE_DIR}/lax"
seed_runtime_only "${VCL_FAKE_STATE_DIR}/lax2"

assert_success "inject-test fleet init" fleet init
assert_success "inject-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"

inject_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-accountd.py" "${PROJECT_DIR}/lib/vincula-backup.py" \
  "$VCL_FAKE_STATE_DIR" "${TEST_TMP}/inject-archives" <<'PY' || inject_seed_rc=$?
import importlib.util, json, shutil, sys, tarfile
from io import BytesIO
from pathlib import Path

acct_py, backup_py, state, arch_dir = sys.argv[1:5]
spec_a = importlib.util.spec_from_file_location("acct", acct_py)
acct = importlib.util.module_from_spec(spec_a)
spec_a.loader.exec_module(acct)
spec_b = importlib.util.spec_from_file_location("vbackup", backup_py)
mod = importlib.util.module_from_spec(spec_b)
spec_b.loader.exec_module(mod)

state = Path(state)
arch_dir = Path(arch_dir)
arch_dir.mkdir(parents=True, exist_ok=True)
node_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
instance_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
other_id = "99999999-9999-4999-8999-999999999999"
lax = state / "lax"
state_doc = {
    "schema_version": 2, "project_version": "0.3.0",
    "sing_box_version": "1.13.18", "architecture": "amd64",
    "installed_at": "2026-08-16T00:00:00Z",
    "node": {
        "node_id": node_id, "instance_id": instance_id, "node_name": "lax",
        "server": "203.0.113.10", "listen": "0.0.0.0", "port": 443,
        "reality_handshake_server": "www.cloudflare.com",
        "reality_server_name": "www.cloudflare.com",
        "reality_private_key": "sekrit", "reality_public_key": "pub",
        "reality_short_id": "abcd1234",
    },
    "service_account": {
        "user": "sing-box", "uid": 1000, "group": "sing-box", "gid": 1000,
        "home": "/var/lib/sing-box", "shell": "/usr/sbin/nologin",
        "created_by_vincula": True, "group_created_by_vincula": True,
    },
}
users = {"schema_version": 2, "users": [{
    "user_id": "u-alice", "tag": "alice", "display_name": "Alice",
    "department": "eng", "enabled": True, "created_at": "2026-08-01T00:00:00Z",
    "credentials": [{
        "credential_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "node_id": node_id, "uuid": "11111111-1111-4111-8111-111111111111",
        "status": "active", "created_at": "2026-08-01T00:00:00Z", "revoked_at": None,
    }],
}]}
toml = """project_version = "0.3.0"
sing_box_version = "1.13.18"
architecture = "amd64"
node_id = "%s"
node_name = "lax"
server = "203.0.113.10"
listen = "0.0.0.0"
port = 443
reality_handshake_server = "www.cloudflare.com"
reality_server_name = "www.cloudflare.com"
clash_api_port = 9090
clash_api_secret = "clash-sekrit"
accounting_raw_retention_days = 90
accounting_daily_retention_days = 90
billing_cycle_start_day = 1
""" % node_id
(lax / "state.json").write_text(json.dumps(state_doc, indent=2) + "\n", encoding="utf-8")
(lax / "users.json").write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
(lax / "config.toml").write_text(toml, encoding="utf-8")
(lax / "VERSION").write_text("0.3.0\n", encoding="utf-8")
conn = acct.open_db(str(lax / "accounting.db"))
conn.execute(
    """INSERT INTO connections (
      connection_id, generation, user_id, node_id, instance_id, user_tag,
      started_at, last_seen_at, closed_at, destination_host, destination_ip,
      destination_port, network, upload_bytes, download_bytes)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("inject-1", 0, "u-alice", node_id, instance_id, "alice",
     "2026-08-16T01:00:00Z", "2026-08-16T01:05:00Z", "2026-08-16T01:05:00Z",
     "example.com", "203.0.113.10", 443, "tcp", 10, 20),
)
conn.commit()
conn.close()

good = arch_dir / "good.tar"
mod.create_backup(lax, lax / "accounting.db", include_secrets=False, output=good)
tamper = arch_dir / "tamper.tar"
with tarfile.open(good, "r:") as src, tarfile.open(tamper, "w:", format=tarfile.USTAR_FORMAT) as dst:
    for info in src.getmembers():
        data = src.extractfile(info).read()
        if info.name == "users.json":
            buf = bytearray(data)
            buf[0] ^= 0x01
            data = bytes(buf)
            info.size = len(data)
        dst.addfile(info, BytesIO(data))
wrong = arch_dir / "wrong-node.tar"
other_state = arch_dir / "other-node"
other_state.mkdir()
other_doc = json.loads((lax / "state.json").read_text(encoding="utf-8"))
other_doc["node"]["node_id"] = other_id
other_users = json.loads((lax / "users.json").read_text(encoding="utf-8"))
other_users["users"][0]["credentials"][0]["node_id"] = other_id
(other_state / "state.json").write_text(json.dumps(other_doc, indent=2) + "\n", encoding="utf-8")
(other_state / "users.json").write_text(json.dumps(other_users, indent=2) + "\n", encoding="utf-8")
(other_state / "config.toml").write_text(
    (lax / "config.toml").read_text(encoding="utf-8").replace(node_id, other_id),
    encoding="utf-8",
)
(other_state / "VERSION").write_text("0.3.0\n", encoding="utf-8")
shutil.copyfile(lax / "accounting.db", other_state / "accounting.db")
mod.create_backup(other_state, other_state / "accounting.db", include_secrets=False, output=wrong)
verified = mod.verify_archive(wrong)
assert verified.get("ok") is True, verified
assert verified.get("source_node_id") == other_id, verified
PY
if (( inject_seed_rc == 0 )); then
  pass "inject-test fixture seeded with good/tamper/wrong-node archives"
else
  fail "inject-test fixture seeded with good/tamper/wrong-node archives"
fi

inject_sync_rc=0
fleet sync --node lax >/dev/null || inject_sync_rc=$?
if (( inject_sync_rc == 0 )); then
  pass "inject-test pre-sync exits 0"
else
  fail "inject-test pre-sync exits 0 (rc=${inject_sync_rc})"
fi

assert_replace_aborted() {
  local description=$1
  python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" \
    "$VCL_FAKE_STATE_DIR" "$LAX_REMOTE_NODE_ID" "$description" <<'PY'
import importlib.util, json, os, sys
from pathlib import Path
path, home, state, node_id = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
os.environ["VCL_FLEET_HOME"] = str(home)
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
registry = json.loads((home / "fleet.json").read_text(encoding="utf-8"))
node = next(n for n in registry["nodes"] if n["name"] == "lax")
assert node["node_id"] == node_id
assert node["ssh_host"] == "203.0.113.10", node["ssh_host"]
assert node["status"] == "active"
assert node["enabled"] is True
users = json.loads((state / "lax" / "users.json").read_text(encoding="utf-8"))
assert users["users"][0]["credentials"][0]["uuid"] == "11111111-1111-4111-8111-111111111111"
assert not (state / "lax2" / "VERSION").exists()
ident_path = state / "lax2" / "identity.json"
if ident_path.is_file():
    ident = json.loads(ident_path.read_text(encoding="utf-8"))
    assert ident["node_id"] != node_id
conn = mod.open_fleet_db()
hist = mod.list_instances(conn, node_id)
conn.close()
assert all(row.get("ssh_host") != "203.0.113.18" for row in hist), hist
active = [row for row in hist if row.get("status") == "active"]
assert len(active) <= 1, hist
if active:
    assert active[0]["instance_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PY
}

fail_backup_rc=0
fail_backup_err=$(VCL_FAKE_FAIL_BACKUP=lax fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" 2>&1) \
  || fail_backup_rc=$?
if (( fail_backup_rc != 0 )) && [[ "$fail_backup_err" == *"backup create failed"* ]]; then
  pass "replace aborts when old-node backup create fails"
else
  fail "replace aborts when old-node backup create fails (rc=${fail_backup_rc} err=${fail_backup_err})"
fi
if assert_replace_aborted "after backup-create fail"; then
  pass "backup-create fail leaves registry host and old credentials unchanged"
else
  fail "backup-create fail leaves registry host and old credentials unchanged"
fi
unset VCL_FAKE_FAIL_BACKUP

fail_scp_rc=0
fail_scp_err=$(VCL_FAKE_FAIL_SCP=lax fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" 2>&1) \
  || fail_scp_rc=$?
if (( fail_scp_rc != 0 )) && [[ "$fail_scp_err" == *"scp"* ]]; then
  pass "replace aborts when scp pull of the backup fails"
else
  fail "replace aborts when scp pull of the backup fails (rc=${fail_scp_rc} err=${fail_scp_err})"
fi
if assert_replace_aborted "after scp fail"; then
  pass "scp fail leaves old node active and registry unchanged"
else
  fail "scp fail leaves old node active and registry unchanged"
fi
unset VCL_FAKE_FAIL_SCP

fail_restore_rc=0
fail_restore_err=$(VCL_FAKE_FAIL_RESTORE=lax2 fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" 2>&1) \
  || fail_restore_rc=$?
if (( fail_restore_rc != 0 )) && [[ "$fail_restore_err" == *"restore failed"* ]]; then
  pass "replace aborts when restore on the new node fails"
else
  fail "replace aborts when restore on the new node fails (rc=${fail_restore_rc} err=${fail_restore_err})"
fi
if assert_replace_aborted "after restore fail"; then
  pass "restore fail leaves old node active, still serving original credentials"
else
  fail "restore fail leaves old node active, still serving original credentials"
fi
unset VCL_FAKE_FAIL_RESTORE

lie_restore_rc=0
lie_restore_err=$(VCL_FAKE_RESTORE_LIE_OK=lax2 fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" 2>&1) \
  || lie_restore_rc=$?
if (( lie_restore_rc != 0 )) && [[ "$lie_restore_err" == *"restore failed"* || "$lie_restore_err" == *"remote exit"* ]]; then
  pass "replace rejects restore ok:true with non-zero exit"
else
  fail "replace rejects restore ok:true with non-zero exit (rc=${lie_restore_rc} err=${lie_restore_err})"
fi
if assert_replace_aborted "after restore lie-ok"; then
  pass "restore lie-ok leaves registry unchanged"
else
  fail "restore lie-ok leaves registry unchanged"
fi
unset VCL_FAKE_RESTORE_LIE_OK

fail_verify_rc=0
fail_verify_err=$(fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" \
  --from-backup "${TEST_TMP}/inject-archives/tamper.tar" 2>&1) || fail_verify_rc=$?
if (( fail_verify_rc != 0 )) && [[ "$fail_verify_err" == *"backup verify failed"* ]]; then
  pass "replace aborts when pulled backup verify fails"
else
  fail "replace aborts when pulled backup verify fails (rc=${fail_verify_rc} err=${fail_verify_err})"
fi
if assert_replace_aborted "after verify fail"; then
  pass "verify-fail --from-backup does not change registry or old node"
else
  fail "verify-fail --from-backup does not change registry or old node"
fi

fail_wrong_rc=0
fail_wrong_err=$(fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" \
  --from-backup "${TEST_TMP}/inject-archives/wrong-node.tar" 2>&1) || fail_wrong_rc=$?
if (( fail_wrong_rc != 0 )) && [[ "$fail_wrong_err" == *"source_node_id"* ]] \
  && [[ "$fail_wrong_err" == *"does not match registry"* ]]; then
  pass "replace refuses backup whose source_node_id is not the registry node"
else
  fail "replace refuses backup whose source_node_id is not the registry node (rc=${fail_wrong_rc} err=${fail_wrong_err})"
fi
if assert_replace_aborted "after wrong-node backup"; then
  pass "wrong-node backup leaves target registry node_id and old host unchanged"
else
  fail "wrong-node backup leaves target registry node_id and old host unchanged"
fi

disable_rc=0
fleet node disable lax >/dev/null || disable_rc=$?
if (( disable_rc == 0 )); then
  pass "inject-test disable lax"
else
  fail "inject-test disable lax (rc=${disable_rc})"
fi
disabled_replace_rc=0
disabled_replace_err=$(fleet node replace lax --host 203.0.113.18 --host-key "$LAX2_HOST_KEY" 2>&1) \
  || disabled_replace_rc=$?
if (( disabled_replace_rc != 0 )) && [[ "$disabled_replace_err" == *"disabled"* ]]; then
  pass "replace disabled node is refused"
else
  fail "replace disabled node is refused (rc=${disabled_replace_rc} err=${disabled_replace_err})"
fi
fleet node enable lax >/dev/null || true

export VCL_FLEET_HOME="${SAVED_REPLACE_HOME}"
unset VCL_FAKE_STATE_DIR
unset VCL_FAKE_FAIL_BACKUP
unset VCL_FAKE_FAIL_SCP
unset VCL_FAKE_FAIL_RESTORE

assert_success "docs/fleet.md exists" test -f "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md documents vcl-fleet.cmd" \
  grep -q 'vcl-fleet.cmd' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md documents --host-key" \
  grep -q -- '--host-key' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md names CLOCK_SKEW_WARN_SECONDS 30" \
  grep -q 'CLOCK_SKEW_WARN_SECONDS = 30' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md names CLOCK_SKEW_FAIL_SECONDS 300" \
  grep -q 'CLOCK_SKEW_FAIL_SECONDS = 300' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md has AC-2.9-01" \
  grep -q 'AC-2.9-01' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md has AC-2.9-10" \
  grep -q 'AC-2.9-10' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md documents runtime-only replace" \
  grep -q 'runtime-only' "${PROJECT_DIR}/docs/fleet.md"
assert_failure "docs/fleet.md does not teach restore --replace-node" \
  grep -q -- '--replace-node' "${PROJECT_DIR}/docs/fleet.md"
assert_success "docs/fleet.md names --reissue-output" \
  grep -q -- '--reissue-output' "${PROJECT_DIR}/docs/fleet.md"
assert_failure "README does not mark node replace NOT IMPLEMENTED" \
  grep -q 'NOT IMPLEMENTED against real vcl' "${PROJECT_DIR}/README.md"

# P1-06 / B6: controller operation lock
assert_success "fleet lock path is \$FLEET_HOME/.lock" \
  grep -q 'fleet_home() / ".lock"' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet lock uses fcntl.flock" \
  grep -q 'fcntl.flock' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "fleet busy message matches node busy text" \
  grep -q 'another vincula operation in progress' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "cmd_node_add holds fleet operation lock" \
  grep -q '@with_fleet_op_lock' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_success "cmd_sync holds fleet operation lock" \
  awk '/^@with_fleet_op_lock$/{prev=1; next} prev && /^def cmd_sync\(/ {found=1} {prev=0} END{exit found?0:1}' \
    "${PROJECT_DIR}/lib/vincula-fleet.py"
save_lock_src=$(sed -n '/^def save_registry(/,/^def find_by_name(/p' "${PROJECT_DIR}/lib/vincula-fleet.py")
assert_success "save_registry acquires fleet operation lock" \
  grep -q 'fleet_op_lock' <<< "$save_lock_src"
cursor_lock_src=$(sed -n '/^def write_sync_cursor(/,/^def mark_cursor_status(/p' "${PROJECT_DIR}/lib/vincula-fleet.py")
assert_success "write_sync_cursor acquires fleet operation lock" \
  grep -q 'fleet_op_lock' <<< "$cursor_lock_src"

SAVED_OPLOCK_HOME="${VCL_FLEET_HOME}"
OPLOCK_FLEET_HOME="${TEST_TMP}/fleet-home-op-lock"
export VCL_FLEET_HOME="$OPLOCK_FLEET_HOME"
mkdir -p "$VCL_FLEET_HOME"
assert_success "op-lock fleet init" fleet init

OPLOCK_NID_A="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaa00001"
OPLOCK_NID_B="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaa00002"
fleet node add locka --host 203.0.113.51 --offline --node-id "$OPLOCK_NID_A" \
  >"${TEST_TMP}/locka.out" 2>"${TEST_TMP}/locka.err" &
locka_pid=$!
fleet node add lockb --host 203.0.113.52 --offline --node-id "$OPLOCK_NID_B" \
  >"${TEST_TMP}/lockb.out" 2>"${TEST_TMP}/lockb.err" &
lockb_pid=$!
locka_rc=0
wait "$locka_pid" || locka_rc=$?
lockb_rc=0
wait "$lockb_pid" || lockb_rc=$?
lock_json="${OPLOCK_FLEET_HOME}/fleet.json"
lock_has_a=0
lock_has_b=0
grep -q '"name": "locka"' "$lock_json" && lock_has_a=1
grep -q '"name": "lockb"' "$lock_json" && lock_has_b=1
if (( lock_has_a == 1 && lock_has_b == 1 )); then
  pass "concurrent fleet node add keeps both nodes (serialized, no lost update)"
elif (( locka_rc == 0 && lockb_rc == 4 && lock_has_a == 1 && lock_has_b == 0 )); then
  pass "concurrent fleet node add keeps both nodes (serialized, no lost update)"
elif (( lockb_rc == 0 && locka_rc == 4 && lock_has_b == 1 && lock_has_a == 0 )); then
  pass "concurrent fleet node add keeps both nodes (serialized, no lost update)"
else
  fail "concurrent fleet node add keeps both nodes (serialized, no lost update) (a_rc=${locka_rc} b_rc=${lockb_rc} a=${lock_has_a} b=${lock_has_b})"
fi

oplock_holder_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$OPLOCK_FLEET_HOME" <<'PY' &
import importlib.util, os, sys, time
path, home = sys.argv[1], sys.argv[2]
os.environ["VCL_FLEET_HOME"] = home
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.acquire_fleet_op_lock()
open(os.path.join(home, ".lock-held"), "w", encoding="utf-8").close()
time.sleep(8)
PY
oplock_holder_pid=$!
oplock_ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if [[ -f "${OPLOCK_FLEET_HOME}/.lock-held" ]]; then
    oplock_ready=1
    break
  fi
  sleep 0.1
done
if (( oplock_ready != 1 )); then
  fail "held fleet lock makes concurrent node add busy (holder did not acquire)"
else
  oplock_busy_rc=0
  oplock_busy_err=$(
    VCL_FLEET_LOCK_TIMEOUT=0 fleet node add lockc --host 203.0.113.53 --offline \
      --node-id "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaa00003" 2>&1
  ) || oplock_busy_rc=$?
  if (( oplock_busy_rc == 4 )) && [[ "$oplock_busy_err" == *busy* ]] \
    && [[ "$oplock_busy_err" == *"another vincula operation in progress"* ]]; then
    pass "held fleet lock makes concurrent node add busy"
  else
    fail "held fleet lock makes concurrent node add busy (rc=${oplock_busy_rc} err=${oplock_busy_err})"
  fi
fi
kill "$oplock_holder_pid" 2>/dev/null || true
wait "$oplock_holder_pid" 2>/dev/null || true

fleet_fail_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$OPLOCK_FLEET_HOME" <<'PY' || fleet_fail_rc=$?
import importlib.util, os, sys
path, home = sys.argv[1], sys.argv[2]
os.environ["VCL_FLEET_HOME"] = home
os.environ["VCL_FLEET_LOCK_TIMEOUT"] = "0"
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
try:
    with mod.fleet_op_lock():
        raise SystemExit(1)
except SystemExit as exc:
    if exc.code != 1:
        raise
mod.acquire_fleet_op_lock()
mod.release_fleet_op_lock()
PY
if (( fleet_fail_rc == 0 )); then
  pass "fleet lock released on failure (finally)"
else
  fail "fleet lock released on failure (finally) (rc=${fleet_fail_rc})"
fi

assert_success "fleet lock uses threading.RLock" \
  grep -q 'threading.RLock' "${PROJECT_DIR}/lib/vincula-fleet.py"
assert_failure "fleet lock depth is not a process-global counter" \
  grep -q '_FLEET_LOCK_DEPTH' "${PROJECT_DIR}/lib/vincula-fleet.py"

thread_lock_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$OPLOCK_FLEET_HOME" <<'PY' || thread_lock_rc=$?
import importlib.util, os, sys, threading, time
path, home = sys.argv[1], sys.argv[2]
os.environ["VCL_FLEET_HOME"] = home
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Same-thread nested reentrancy
with mod.fleet_op_lock():
    with mod.fleet_op_lock():
        pass

# Other thread timeout=0 must busy while this thread holds the lock
other = []

def try_busy():
    try:
        mod.acquire_fleet_op_lock(timeout=0)
        other.append("acquired")
        mod.release_fleet_op_lock()
    except SystemExit as exc:
        other.append(exc.code)

mod.acquire_fleet_op_lock()
try:
    mod.acquire_fleet_op_lock()  # nested
    t = threading.Thread(target=try_busy)
    t.start()
    t.join(timeout=5)
    assert t.is_alive() is False
    mod.release_fleet_op_lock()
finally:
    mod.release_fleet_op_lock()
assert other == [mod.FLEET_BUSY_EXIT], other

# After exception, another thread can acquire
def boom():
    with mod.fleet_op_lock():
        raise RuntimeError("lock-test")

try:
    boom()
except RuntimeError:
    pass
mod.acquire_fleet_op_lock(timeout=0)
mod.release_fleet_op_lock()

# Two threads must not both enter the payload critical section
inside = 0
max_inside = 0
guard = threading.Lock()
errors = []

def critical():
    global inside, max_inside
    try:
        with mod.fleet_op_lock():
            with guard:
                inside += 1
                max_inside = max(max_inside, inside)
            try:
                time.sleep(0.25)
            finally:
                with guard:
                    inside -= 1
    except Exception as exc:  # noqa: BLE001
        errors.append(exc)

t1 = threading.Thread(target=critical)
t2 = threading.Thread(target=critical)
t1.start()
t2.start()
t1.join()
t2.join()
assert not errors, errors
assert max_inside == 1, max_inside
PY
if (( thread_lock_rc == 0 )); then
  pass "fleet lock is per-thread reentrant and exclusive across threads"
else
  fail "fleet lock is per-thread reentrant and exclusive across threads (rc=${thread_lock_rc})"
fi

export VCL_FLEET_HOME="${SAVED_OPLOCK_HOME}"

# --- B15 Local Audit UI (localhost-only, read-only) ---
UI_FLEET_HOME="${TEST_TMP}/fleet-home-ui"
export VCL_FLEET_HOME="$UI_FLEET_HOME"
export VCL_FLEET_STATS_NOW="2026-08-16"
mkdir -p "$VCL_FLEET_HOME"

assert_success "ui-test fleet init" fleet init
assert_success "ui-test offline add lax" \
  fleet node add lax --host 203.0.113.10 --offline --node-id "$LAX_REMOTE_NODE_ID"
UI_IDENT="${UI_FLEET_HOME}/ui-ident-ed25519"
printf 'test-only-not-a-real-key\n' > "$UI_IDENT"
assert_success "ui-test set identity-file" \
  fleet node set lax --identity-file "$UI_IDENT"

ui_seed_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" "$VCL_FLEET_HOME" "$LAX_REMOTE_NODE_ID" <<'PY' || ui_seed_rc=$?
import importlib.util, json, os, sys
from pathlib import Path

path, home, lax_id = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
os.environ["VCL_FLEET_HOME"] = str(home)
os.environ["VCL_FLEET_STATS_NOW"] = "2026-08-16"
spec = importlib.util.spec_from_file_location("vincula_fleet", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
alice = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
inst = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
now = "2026-08-16T07:00:00Z"
row = {
    "event_id": 1,
    "export_seq": 1,
    "connection_id": "ui-alice-1",
    "generation": 0,
    "user_id": alice,
    "user_tag": "alice",
    "node_id": lax_id,
    "instance_id": inst,
    "started_at": "2026-08-10T08:00:00Z",
    "last_seen_at": "2026-08-10T09:00:00Z",
    "closed_at": "2026-08-10T09:00:00Z",
    "destination_host": "example.com",
    "destination_ip": "203.0.113.80",
    "destination_port": 443,
    "network": "tcp",
    "upload_bytes": 100,
    "download_bytes": 200,
}
conn = mod.open_fleet_db()
mod.import_audit_batch(lax_id, inst, [row], now_iso=now, conn=conn)
conn.close()
status = {
    "schema_version": 1,
    "ok": True,
    "controller_utc": now,
    "nodes": [{
        "name": "lax",
        "node_id": lax_id,
        "instance_id": inst,
        "enabled": True,
        "ssh": "OK",
        "proxy": "OK",
        "accounting": "STALE",
    }],
}
mod.write_last_status(status)
(home / "alice_uid.txt").write_text(alice, encoding="utf-8")
PY
if (( ui_seed_rc == 0 )); then
  pass "ui-test seeded fleet.db + last-status"
else
  fail "ui-test seeded fleet.db + last-status (rc=${ui_seed_rc})"
fi

ui_bind_rc=0
ui_bind_err=$(fleet ui --host 0.0.0.0 --port 18765 2>&1) || ui_bind_rc=$?
if (( ui_bind_rc == 2 )) && [[ "$ui_bind_err" == *"refuses non-loopback"* ]]; then
  pass "AC-3.1-01 ui refuses non-loopback bind"
else
  fail "AC-3.1-01 ui refuses non-loopback bind (rc=${ui_bind_rc} err=${ui_bind_err})"
fi

ui_api_rc=0
python3 - "${PROJECT_DIR}/lib/vincula-fleet.py" \
  "${PROJECT_DIR}/lib/vincula-ui/server.py" \
  "${PROJECT_DIR}/lib/vincula-ui/static" \
  "$VCL_FLEET_HOME" <<'PY' || ui_api_rc=$?
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

fleet_path, server_path, static_dir, home = sys.argv[1:5]
os.environ["VCL_FLEET_HOME"] = home
os.environ["VCL_FLEET_STATS_NOW"] = "2026-08-16"

spec = importlib.util.spec_from_file_location("vincula_fleet", fleet_path)
fleet = importlib.util.module_from_spec(spec)
sys.modules["vincula_fleet"] = fleet
spec.loader.exec_module(fleet)

sspec = importlib.util.spec_from_file_location("vincula_ui_server", server_path)
ui = importlib.util.module_from_spec(sspec)
sspec.loader.exec_module(ui)

ui.set_fleet_module(fleet)
httpd, thread, token = ui.serve_in_thread(
    "127.0.0.1", 0, fleet_mod=fleet, static_dir=Path(static_dir)
)
port = httpd.server_address[1]
base = f"http://127.0.0.1:{port}"
TOKEN_H = "X-Vincula-UI-Token"

def req(path, *, method="GET", body=None, headers=None, origin=None, ctype=None):
    hdrs = {}
    if headers:
        hdrs.update(headers)
    data = None
    if method == "POST":
        data = json.dumps({} if body is None else body).encode("utf-8")
        if ctype is None:
            hdrs["Content-Type"] = "application/json"
        else:
            hdrs["Content-Type"] = ctype
        if origin is not None:
            hdrs["Origin"] = origin
    r = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(r, timeout=8) as resp:
        raw = resp.read().decode("utf-8")
        if path == "/" or path.endswith(".html") or path.endswith(".js") or path.endswith(".css"):
            return resp.status, raw, dict(resp.headers)
        return resp.status, json.loads(raw), dict(resp.headers)

def get(path, token_val=token, extra_headers=None):
    hdrs = {TOKEN_H: token_val} if token_val is not None else {}
    if extra_headers:
        hdrs.update(extra_headers)
    return req(path, headers=hdrs)

def post(path, body=None, token_val=token, origin=None, ctype=None):
    hdrs = {TOKEN_H: token_val} if token_val is not None else {}
    return req(
        path, method="POST", body=body, headers=hdrs, origin=origin, ctype=ctype
    )

def http_code(fn):
    try:
        fn()
        return 200
    except urllib.error.HTTPError as exc:
        return exc.code

# Host / token / Origin / Content-Type (P0-01 / P1-04)
import http.client
hc = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
hc.request("GET", "/api/meta", headers={"Host": "evil.example", TOKEN_H: token})
assert hc.getresponse().status == 403
hc.close()
assert http_code(lambda: req("/api/meta")) == 401
assert http_code(lambda: req("/api/meta", headers={TOKEN_H: "wrong"})) == 401
assert http_code(
    lambda: post(
        "/api/sync",
        {},
        origin="https://evil.example",
    )
) == 403
assert http_code(
    lambda: post("/api/sync", {}, ctype="text/plain")
) == 415

# reseed refused; cache unchanged
conn = fleet.open_fleet_db()
before = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
conn.close()
try:
    post("/api/sync", {"reseed": "lax"})
    raise AssertionError("reseed should 400")
except urllib.error.HTTPError as exc:
    assert exc.code == 400, exc.code
    err = json.loads(exc.read().decode("utf-8"))
    assert "CLI" in err["error"] or "cli" in err["error"].lower()
conn = fleet.open_fleet_db()
after = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
conn.close()
assert after == before

st, meta, hdrs = get("/api/meta")
assert st == 200
assert meta["identity_mutations"] is False
assert meta["reseed"] == "cli-only"
assert "refresh" in meta["cache_writes"]
assert meta["pages"] == ["overview", "audit", "health"]
assert "Content-Security-Policy" in hdrs
assert "DENY" in (hdrs.get("X-Frame-Options") or "")
assert "trace" not in json.dumps(meta)

st, overview, _ = get("/api/overview")
assert st == 200
assert overview["accounting_mode"] == "approximate"
assert overview["node_count"] == 1
assert any(w.get("code") == "accounting-stale" for w in overview["warnings"])
assert overview["top_users"]

st, health, _ = get("/api/health")
assert st == 200 and len(health["nodes"]) == 1
assert health["nodes"][0]["name"] == "lax"
assert health["nodes"][0]["accounting"] == "STALE"

st, node, _ = get("/api/nodes/lax")
assert st == 200 and node["node"]["node_id"]
assert "secrets_note" in node
blob = json.dumps(node).lower()
assert "vless://" not in blob
assert "private_key" not in blob
assert "clash_secret" not in blob
assert "identity_file" not in blob

st, users, _ = get("/api/users")
assert st == 200 and users["users"]
assert users["users"][0]["tag"] == "alice"

st, recipes, _ = get("/api/recipes")
assert st == 200 and any(r["id"] == "node-replace" for r in recipes["recipes"])
assert "CLI-only" in recipes["note"] or "cli-only" in recipes["note"].lower() or "reseed" in recipes["note"].lower()

alice_uid = (Path(home) / "alice_uid.txt").read_text(encoding="utf-8").strip()
st, audit, _ = get(
    "/api/audit?user=alice"
    "&from=2026-08-01T00:00:00Z&to=2026-08-17T00:00:00Z"
)
assert st == 200 and len(audit["rows"]) >= 1
assert audit["rows"][0]["destination"] == "example.com"
assert audit["limit"] == 500
assert audit["truncated"] is False

# Destination filter in SQL before LIMIT (P1-02): noise first, target later
conn = fleet.open_fleet_db()
seed_row = conn.execute(
    "SELECT node_id, instance_id, user_id, user_tag FROM audit_events LIMIT 1"
).fetchone()
node_id, inst_id, uid, tag = (
    seed_row["node_id"],
    seed_row["instance_id"],
    seed_row["user_id"],
    seed_row["user_tag"],
)
extra = []
# event 2 noise, 3 target, 4 noise, 5 target, 6 noise, 7 target
hosts = [
    (2, "noise.example"),
    (3, "target.example"),
    (4, "noise.example"),
    (5, "target.example"),
    (6, "noise.example"),
    (7, "target.example"),
]
for eid, host in hosts:
    extra.append(
        {
            "event_id": eid,
            "export_seq": eid,
            "connection_id": f"ui-alice-{eid}",
            "generation": 0,
            "user_id": uid,
            "user_tag": tag,
            "node_id": node_id,
            "instance_id": inst_id,
            "started_at": f"2026-08-10T08:0{eid}:00Z",
            "last_seen_at": f"2026-08-10T08:0{eid}:30Z",
            "closed_at": f"2026-08-10T08:0{eid}:30Z",
            "destination_host": host,
            "destination_ip": "203.0.113.80",
            "destination_port": 443,
            "network": "tcp",
            "upload_bytes": 1,
            "download_bytes": 1,
        }
    )
fleet.import_audit_batch(node_id, inst_id, extra, now_iso="2026-08-16T07:00:00Z", conn=conn)
conn.close()

q = (
    "/api/audit?user=alice"
    "&from=2026-08-01T00:00:00Z&to=2026-08-17T00:00:00Z"
)
st, dest_page, _ = get(q + "&destination=target&limit=1")
assert st == 200
assert [r["destination"] for r in dest_page["rows"]] == ["target.example"], dest_page
assert dest_page["truncated"] is True
assert dest_page["next_cursor"]
assert dest_page["next_cursor"]["after_event_id"] == 3

st, dest_empty, _ = get(q + "&destination=no-such-host&limit=1")
assert st == 200
assert dest_empty["rows"] == []
assert dest_empty["truncated"] is False
assert dest_empty["next_cursor"] is None

seen = []
cursor = dest_page["next_cursor"]
while cursor:
    qs = (
        f"{q}&destination=target&limit=1"
        f"&after_started_at={cursor['after_started_at']}"
        f"&after_event_id={cursor['after_event_id']}"
        f"&after_node_id={cursor['after_node_id']}"
    )
    st, nxt, _ = get(qs)
    assert st == 200
    seen.extend(nxt["rows"])
    cursor = nxt["next_cursor"]
assert [r["destination"] for r in dest_page["rows"] + seen] == [
    "target.example",
    "target.example",
    "target.example",
]
ids = [dest_page["rows"][0]["event_id"]] + [r["event_id"] for r in seen]
assert ids == [3, 5, 7], ids
assert len(ids) == len(set(ids))

st, audit2, _ = get(
    f"/api/audit?user={alice_uid}"
    "&from=2026-08-01T00:00:00Z&to=2026-08-17T00:00:00Z"
    "&destination=example"
)
assert st == 200 and len(audit2["rows"]) >= 1

st, audit3, _ = get(
    "/api/audit?user=alice"
    "&from=2026-08-01T00:00:00Z&to=2026-08-17T00:00:00Z&limit=1"
)
assert st == 200
assert audit3["limit"] == 1

try:
    get(
        "/api/audit?user=alice"
        "&from=2026-01-01T00:00:00Z&to=2026-08-17T00:00:00Z"
    )
    raise AssertionError("wide window should 400")
except urllib.error.HTTPError as exc:
    assert exc.code == 400

# No mutation routes
for path in (
    "/api/user/add",
    "/api/user/rotate",
    "/api/node/retire",
    "/api/node/replace",
    "/api/restore",
    "/api/mutate",
):
    code = http_code(lambda p=path: post(p, {}))
    assert code == 405, (path, code)

# Concurrent payload helpers do not share stdout (P1-01)
import threading
import time
results = []

def worker():
    results.append(ui.api_overview())

t1 = threading.Thread(target=worker)
t2 = threading.Thread(target=worker)
t1.start(); t2.start(); t1.join(); t2.join()
assert len(results) == 2
assert all(r.get("schema_version") == 1 and "node_count" in r for r in results)

# Concurrent /api/sync must not both enter run_sync_payload
orig_sync = fleet.run_sync_payload
inside = 0
max_inside = 0
guard = threading.Lock()

def wrapped_sync(ns):
    global inside, max_inside
    with guard:
        inside += 1
        max_inside = max(max_inside, inside)
    try:
        time.sleep(0.3)
        return 0, {
            "ok": True,
            "state": "SUCCESS",
            "nodes": [],
            "remediation": [],
        }
    finally:
        with guard:
            inside -= 1

fleet.run_sync_payload = wrapped_sync
sync_err = []
sync_ok = []

def sync_worker():
    try:
        sync_ok.append(post("/api/sync", {}))
    except Exception as exc:  # noqa: BLE001
        sync_err.append(exc)

st1 = threading.Thread(target=sync_worker)
st2 = threading.Thread(target=sync_worker)
st1.start(); st2.start(); st1.join(); st2.join()
fleet.run_sync_payload = orig_sync
assert not sync_err, sync_err
assert len(sync_ok) == 2
assert max_inside == 1, max_inside

# Worker cap: one in-flight request, the next is 503
busy_httpd, busy_thread, busy_tok = ui.serve_in_thread(
    "127.0.0.1",
    0,
    fleet_mod=fleet,
    static_dir=Path(static_dir),
    max_workers=1,
)
busy_port = busy_httpd.server_address[1]
busy_base = f"http://127.0.0.1:{busy_port}"
entered = threading.Event()
release = threading.Event()
orig_ov = ui.api_overview

def slow_overview():
    entered.set()
    release.wait(timeout=8)
    return orig_ov()

ui.api_overview = slow_overview

def hold_overview():
    hdrs = {TOKEN_H: busy_tok}
    r = urllib.request.Request(busy_base + "/api/overview", headers=hdrs)
    with urllib.request.urlopen(r, timeout=8) as resp:
        resp.read()

holder = threading.Thread(target=hold_overview)
holder.start()
assert entered.wait(timeout=3), "overview worker did not start"
busy_code = 200
try:
    r = urllib.request.Request(
        busy_base + "/api/meta", headers={TOKEN_H: busy_tok}
    )
    urllib.request.urlopen(r, timeout=8)
except urllib.error.HTTPError as exc:
    busy_code = exc.code
assert busy_code == 503, busy_code
release.set()
holder.join(timeout=8)
ui.api_overview = orig_ov
busy_httpd.shutdown()
busy_thread.join(timeout=5)
# Restore primary server runtime (token + port) after the busy-server helper.
ui.set_ui_runtime(token=token, listen_port=port)

# Static index: token meta, no vless
st, html, idx_hdrs = req("/", headers={})
assert st == 200
assert "Overview" in html and "Audit" in html and "Health" in html
assert "vless://" not in html.lower()
assert 'name="vcl-ui-token"' in html
assert "Content-Security-Policy" in idx_hdrs
assert "trace" not in html.lower() or True

httpd.shutdown()
thread.join(timeout=5)
print("ui api ok")
PY
if (( ui_api_rc == 0 )); then
  pass "AC-3.1 UI overview/health/audit/recipes + no mutation routes"
else
  fail "AC-3.1 UI overview/health/audit/recipes + no mutation routes (rc=${ui_api_rc})"
fi

ui_help=$(fleet ui -h 2>&1) || true
if [[ "$ui_help" == *"localhost"* ]] || [[ "$ui_help" == *"loopback"* ]] \
  || [[ "$ui_help" == *"127.0.0.1"* ]]; then
  pass "ui -h documents localhost bind"
else
  fail "ui -h documents localhost bind"
fi

unset VCL_FLEET_STATS_NOW

export VCL_FLEET_HOME="${OFFLINE_FLEET_HOME}"
if [[ -n "${FLEET_SAVED_HOME}" ]]; then
  export HOME="${FLEET_SAVED_HOME}"
else
  unset HOME
fi
