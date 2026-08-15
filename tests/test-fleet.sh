#!/usr/bin/env bash
# Sourced by tests/test.sh. Requires PROJECT_DIR, TEST_TMP, TEST_NODE_ID,
# TEST_INSTANCE_ID, and the assert_* helpers.

readonly TEST_TOKYO_NODE_ID="8bb18c32-3333-4333-8333-333333333333"
readonly TEST_SG_NODE_ID="9cc29d43-4444-4444-8444-444444444444"

export VCL_FLEET_HOME="${TEST_TMP}/fleet-home"
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
if (( ssh_add_rc == 2 )); then
  pass "node add without --offline exits 2"
else
  fail "node add without --offline exits 2 (rc=${ssh_add_rc})"
fi
assert_success "node add without --offline names Phase 6" \
  grep -q 'SSH add not wired' <<< "$ssh_add_err"

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
