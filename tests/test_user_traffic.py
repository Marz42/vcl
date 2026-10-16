"""User-specific traffic samples, uncertainty, identities and lifecycle."""
import copy
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load("user_finding_support", "tests/test_findings.py")
node_module = load("user_node", "lib/telemetry_snapshot.py")
daemon = load("user_daemon", "lib/vincula-accountd.py")
users, findings, monitor = support.findings.user_traffic, support.findings, support.monitor
NOW, NODE, BASE = support.NOW, support.NODE, support.BASE
USER_ID = "66666666-6666-4666-8666-666666666666"
KEY = hashlib.sha256(USER_ID.encode()).hexdigest()


def snapshot(at=NOW, total=0, connections=2, **changes):
    return {"schema": "user-traffic/v1", "node_id": BASE["node_id"], "instance_id": BASE["instance_id"],
            "observed_at": findings.utc(at), "sampled_at": findings.utc(at), "heartbeat_age_seconds": 1,
            "pruned_max_export_seq": 0, "state": "OK", "truncated": False,
            "users": [{"user_key": KEY, "tag": "alice", "retained_bytes": total, "connections": connections}], **changes}


def record(at, total=0, connections=2, **changes):
    doc = support.record(at)
    doc["user_traffic"] = {"state": "OK", "snapshot": snapshot(at, total, connections, **changes)}
    return doc


class NodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "accounting.db"
        (self.root / "config.toml").write_text(f'node_id = "{BASE["node_id"]}"\nclash_api_secret="private-clash"\n')
        (self.root / "state.json").write_text(json.dumps({"instance_id": BASE["instance_id"], "private_key": "private-reality"}))
        with closing(daemon.open_db(str(self.db))) as conn:
            for key in ("heartbeat_at", "last_success_at"):
                daemon.meta_set(conn, key, node_module._utc_now())
            conn.commit()

    def add(self, conn, cid, total=100, closed=None, uid=USER_ID, tag="alice"):
        conn.execute("INSERT INTO connections(connection_id,generation,user_id,node_id,user_tag,started_at,last_seen_at,"
            "closed_at,upload_bytes,download_bytes,destination_host) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (str(cid), 0, uid, NODE["node_id"], tag, findings.utc(NOW), findings.utc(NOW), closed, total, 20, "private.example"))

    def read(self, **kw):
        return node_module.build_user_snapshot(state_dir=self.root, accounting_db=self.db, **kw)

    def test_long_open_and_closed_rows_are_accounted_readonly_without_secret(self):
        with closing(sqlite3.connect(self.db)) as conn:
            self.add(conn, "private-cid", 100)
            self.add(conn, "closed-cid", 200, findings.utc(NOW))
            conn.commit()
        before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        doc = self.read()
        self.assertFalse(users.validator.validate_user_traffic_v1(doc))
        self.assertEqual(doc["users"], [{"user_key": KEY, "tag": "alice", "retained_bytes": 340, "connections": 1}])
        for secret in (USER_ID, "private-clash", "private-reality", "private-cid", "private.example"):
            self.assertNotIn(secret, json.dumps(doc))
        self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))

    def test_limit_partial_invalid_row_and_overflow_are_not_healthy_zeroes(self):
        with closing(sqlite3.connect(self.db)) as conn:
            for n in range(65):
                self.add(conn, n, uid=f"{n:08d}-6666-4666-8666-666666666666")
            conn.commit()
        doc = self.read()
        self.assertEqual(doc["state"], "PARTIAL")
        self.assertEqual(len(doc["users"]), 64)
        self.assertLess(len(json.dumps(doc).encode()), 32768)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE connections SET user_tag='vless://private',upload_bytes=-1 WHERE connection_id='0'")
            conn.commit()
        doc = self.read()
        self.assertEqual(doc["state"], "PARTIAL")
        self.assertEqual(len(doc["users"]), 63)
        self.assertNotIn("vless", json.dumps(doc))
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE connections SET user_id=?,upload_bytes=?", (USER_ID, 2**63 - 1))
            conn.commit()
        self.assertEqual(self.read()["state"], "UNKNOWN")  # SQLite aggregate overflow is not schema corruption.

    def test_missing_corrupt_schema_permissions_and_budget_are_distinct(self):
        with mock.patch.object(node_module.sqlite3, "connect", side_effect=PermissionError("private-error")):
            self.assertEqual(self.read()["state"], "UNREADABLE")
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("DROP TABLE connections")
            conn.commit()
        self.assertEqual(self.read()["state"], "SCHEMA_MISMATCH")
        self.db.write_bytes(b"private-not-sqlite")
        self.assertEqual(self.read()["state"], "CORRUPT")
        self.db.unlink()
        self.assertEqual(self.read()["state"], "MISSING")
        self.assertFalse(self.db.exists())

    def test_failed_poll_freezes_successful_source_time_and_query_is_bounded(self):
        with closing(daemon.open_db(str(self.db))) as conn:
            daemon.meta_set(conn, "last_success_at", findings.utc(NOW))
            self.add(conn, "live")
            conn.commit()
        doc = self.read()
        self.assertEqual(doc["sampled_at"], findings.utc(NOW))
        self.assertEqual(doc["users"][0]["connections"], 1)
        with mock.patch.object(node_module.time, "monotonic", side_effect=[0] + [100] * 3000):
            # Make a query large enough to invoke the progress handler.
            with closing(sqlite3.connect(self.db)) as conn:
                for n in range(1000):
                    self.add(conn, "large-" + str(n))
                conn.commit()
            self.assertEqual(self.read()["state"], "UNKNOWN")

    @unittest.skipUnless(os.name == "posix" and getattr(os, "geteuid", lambda: -1)() == 0, "actual Node Bash CLI requires the Linux root fixture")
    def test_real_readonly_node_command_and_extra_arguments_denied(self):
        with closing(sqlite3.connect(self.db)) as conn:
            self.add(conn, "live")
            conn.commit()
        (self.root / "VERSION").write_text("0.5.2\n")
        config = self.root / "sing-box.json"
        config.write_text("{}")
        binary = self.root / "sing-box"
        binary.write_text("#!/bin/sh\nexit 86\n")
        binary.chmod(0o755)
        env = {**os.environ, "VCL_STATE_DIR": str(self.root), "VCL_ACCOUNTING_DB_FILE": str(self.db),
               "VCL_CONFIG_FILE": str(config), "VCL_SING_BOX_BIN": str(binary)}
        before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        result = subprocess.run(["bash", str(ROOT / "bin/vincula"), "telemetry", "users", "--json"], env=env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["schema"], "user-traffic/v1")
        self.assertEqual(doc["users"][0]["connections"], 1)
        self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))
        denied = subprocess.run(["bash", str(ROOT / "bin/vincula"), "telemetry", "users", "--json", "--file", "/etc/shadow"],
                                env=env, text=True, capture_output=True, timeout=10)
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))


class DetectorTests(unittest.TestCase):
    def baseline(self):
        state, total = None, 0
        for n in range(21):
            total += 100 * 30
            doc = snapshot(NOW + n * 30, total)
            checks, state, _ = users.evaluate(doc, doc["users"][0], state, NOW + n * 30)
            self.assertIsNone(checks["USER_TRAFFIC_SPIKE"][0])
        return state, total

    def test_user_spikes_sustained_duration_recovery_and_normal_variation(self):
        state, total = self.baseline()
        for n in range(11):
            total += 2 * 1024 * 1024 * 30
            doc = snapshot(NOW + 630 + n * 30, total, 25)
            checks, state, summaries = users.evaluate(doc, doc["users"][0], state, NOW + 630 + n * 30)
            self.assertTrue(checks["USER_TRAFFIC_SPIKE"][0])
            self.assertTrue(checks["USER_CONNECTION_SPIKE"][0])
            self.assertEqual(checks["SUSTAINED_TRAFFIC_ANOMALY"][0], n >= 10)
            self.assertEqual(summaries["USER_TRAFFIC_SPIKE"]["baseline_median"], 100)
        for n in range(40):
            total += (90 + n % 21) * 30
            doc = snapshot(NOW + 960 + n * 30, total)
            checks, state, _ = users.evaluate(doc, doc["users"][0], state, NOW + 960 + n * 30, active=users.TYPES)
            self.assertTrue(all(value[0] is False for value in checks.values()))
        with mock.patch("subprocess.run", side_effect=AssertionError("no mutation")):
            users.evaluate(doc, doc["users"][0], state, NOW + 2200)

    def test_no_new_poll_retention_reset_reinstall_and_missing_are_unknown(self):
        state, total = self.baseline()
        for changes, reason in (({"sampled_at": findings.utc(NOW + 600)}, "NO_NEW_SAMPLE"),
                                ({"pruned_max_export_seq": 1}, "RETENTION_CHANGED"),
                                ({"users": []}, "MISSING"), ({"heartbeat_age_seconds": 91}, "STALE")):
            doc = snapshot(NOW + 630, total + 1000, **changes)
            profile = doc["users"][0] if doc["users"] else None
            checks, after, summaries = users.evaluate(doc, profile, state, NOW + 630)
            self.assertTrue(all(value[0] is None for value in checks.values()))
            self.assertEqual(summaries["USER_TRAFFIC_SPIKE"]["reason"], reason)
        doc = snapshot(NOW + 630, 0)
        checks, after, summaries = users.evaluate(doc, doc["users"][0], state, NOW + 630)
        self.assertEqual(summaries["USER_TRAFFIC_SPIKE"]["reason"], "COUNTER_RESET")
        self.assertTrue(all(value[0] is None for value in checks.values()))
        doc["instance_id"] = "33333333-3333-4333-8333-333333333333"
        checks, after, _ = users.evaluate(doc, doc["users"][0], state, NOW + 630)
        self.assertIsNone(checks["USER_TRAFFIC_SPIKE"][0])
        self.assertIsNone(checks["USER_CONNECTION_SPIKE"][0])

    def test_evidence_gap_breaks_pending_duration_but_cached_refresh_does_not(self):
        state, total = self.baseline()
        for n in range(5):
            total += 2 * 1024 * 1024 * 30
            doc = snapshot(NOW + 630 + n * 30, total)
            checks, state, _ = users.evaluate(doc, doc["users"][0], state, NOW + 630 + n * 30)
        _, refreshed, _ = users.evaluate(doc, doc["users"][0], state, NOW + 751)
        self.assertEqual(refreshed, state)
        _, state, _ = users.evaluate(None, None, state, NOW + 760)
        for n in range(6):
            total += 2 * 1024 * 1024 * 30
            doc = snapshot(NOW + 780 + n * 30, total)
            checks, state, _ = users.evaluate(doc, doc["users"][0], state, NOW + 780 + n * 30)
            self.assertFalse(checks["SUSTAINED_TRAFFIC_ANOMALY"][0])


class IntegrationTests(unittest.TestCase):
    def test_identity_capability_failure_deadline_and_public_monitor_contract(self):
        fleet = load("user_fleet", "lib/vincula-fleet.py")
        calls = []
        def ssh(node, command, **kw):
            calls.append((command, kw["timeout"]))
            if command[-2:] == ["users", "--json"]:
                return "OK", snapshot(), "private-error"
            return "OK", BASE, ""
        fleet.observation_ssh_json = ssh
        result = fleet.fetch_node_telemetry(NODE, capabilities={"state": "OK", "capabilities": ["telemetry/v1", "user-traffic/v1"]}, timeout=5)
        self.assertEqual(result["user_traffic"]["state"], "OK")
        self.assertTrue(all(0 < timeout <= 5 for _, timeout in calls))
        self.assertEqual(users.clean(result["user_traffic"], NODE["node_id"], "wrong"), {"state": "ERROR"})
        self.assertEqual(users.fetch(NODE, capabilities={"state": "OK"}, instance_id=None, ssh_json=mock.Mock()), {"state": "UNSUPPORTED"})
        with tempfile.TemporaryDirectory() as tmp:
            store = monitor.Store(Path(tmp) / "observation.db")
            store.record(NODE, result, NOW)
            self.assertIn("user_traffic", store.read([NODE], NOW, include_audit=True)["nodes"][0])
            public = store.read([NODE], NOW)
            self.assertNotIn("user_traffic", public["nodes"][0])
            schema = load("user_monitor_schema", "tests/test_monitor_schema.py")
            schema.validate(public)
        fleet.observation_ssh_json = lambda *a, **kw: (_ for _ in ()).throw(TimeoutError("private")) if a[1][-2:] == ["users", "--json"] else ("OK", BASE, "")
        result = fleet.fetch_node_telemetry(NODE, capabilities={"state": "OK", "capabilities": ["telemetry/v1", "user-traffic/v1"]}, timeout=5)
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["user_traffic"], {"state": "ERROR"})

    def test_persistent_user_lifecycle_dedupe_filter_rename_and_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.db"
            total = 0
            for n in range(32):
                total += (100 if n < 21 else 2 * 1024 * 1024) * 30
                findings.Store(path).evaluate(NODE, record(NOW + n * 30, total, 2 if n < 21 else 25), {}, NOW + n * 30)
            doc = findings.Store(path).read(nodes=[NODE])
            alerts = [row for row in doc["findings"] if row["subject"]["kind"] == "user"]
            self.assertEqual(len(alerts), 3)
            self.assertTrue(all(row["state"] == "ACTIVE" for row in alerts))
            self.assertNotIn(USER_ID, json.dumps(doc))
            self.assertTrue(all("detector_state" not in row for row in doc["evaluations"]))
            findings.Store(path).evaluate(NODE, support.record(NOW + 960), {}, NOW + 960)
            self.assertTrue(all(row["state"] == "ACTIVE" for row in findings.Store(path).read()["findings"] if row["subject"]["kind"] == "user"))
            total += 100 * 60
            findings.Store(path).evaluate(NODE, record(NOW + 990, total), {}, NOW + 990)
            self.assertTrue(all(row["state"] == "RESOLVED" for row in findings.Store(path).read()["findings"] if row["subject"]["kind"] == "user"))
            renamed = {**NODE, "name": "renamed"}
            self.assertTrue(all(row["subject"]["name"] == "renamed" for row in findings.Store(path).read(nodes=[renamed])["findings"]))
            other = {**NODE, "node_id": "33333333-3333-4333-8333-333333333333"}
            self.assertEqual(findings.Store(path).read(nodes=[other])["findings"], [])
            self.assertEqual(len([row for row in doc["events"] if row["kind"] == "FINDING_OPEN" and row["subject"]["kind"] == "user"]), 3)

    def test_capacity_does_not_evict_current_users_and_marks_coverage(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(findings, "USER_CAP", 1):
            store = findings.Store(Path(tmp) / "findings.db")
            for n in range(3):
                snap = snapshot(NOW + n * 30)
                snap["users"].append({**snap["users"][0], "user_key": "f" * 64, "tag": "bob"})
                doc = support.record(NOW + n * 30)
                doc["user_traffic"] = {"state": "OK", "snapshot": snap}
                store.evaluate(NODE, doc, {}, NOW + n * 30)
            doc = store.read()
            self.assertIn("user_evaluations", doc["truncated"])
            self.assertEqual(len([row for row in doc["evaluations"] if row["subject"]["kind"] == "user"]), 1)
            coverage = next(row for row in doc["evaluations"] if row["subject"]["kind"] == "node")["user_coverage"]
            self.assertEqual(coverage["state"], "CAPACITY")
            self.assertEqual(coverage["capacity_skipped"], 1)
        self.assertGreaterEqual(findings.FINDING_CAP, findings.SUBJECT_CAP * (len(findings.TYPES) - 3) + findings.USER_CAP * 3)

    def test_schema1_migration_failure_rollback_and_cache_only_cli_ui(self):
        fleet = load("user_cache_fleet", "lib/vincula-fleet.py")
        ui = load("user_cache_ui", "lib/vincula-ui/server.py")
        ui.set_fleet_module(fleet)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "findings.db"
            with closing(sqlite3.connect(path)) as conn:
                conn.executescript(findings.DDL.split("CREATE TABLE IF NOT EXISTS user_evaluations")[0] + "\nPRAGMA user_version=1;")
            store = findings.Store(path)
            self.assertEqual(store.read()["cache_state"], "OK")
            store.evaluate(NODE, record(NOW), {}, NOW)
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            before = path.read_bytes()
            with mock.patch.object(store, "evaluate_users", side_effect=sqlite3.OperationalError("private-fault")):
                with self.assertRaises(sqlite3.OperationalError):
                    store.evaluate(NODE, record(NOW + 30), {}, NOW + 30)
            self.assertEqual(before, path.read_bytes())
            fleet.fleet_db_path = lambda: root / "fleet.db"
            fleet.operation_journal_path = lambda **kw: root / "operations.jsonl"
            fleet.load_registry = lambda: {"nodes": [NODE]}
            fleet.observation_ssh_json = mock.Mock(side_effect=AssertionError("display must not SSH"))
            before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
            for route in ("/api/findings", "/api/timeline"):
                handler = SimpleNamespace(_send_json=mock.Mock())
                ui.FleetUIHandler._handle_api_get(handler, route, {})
                self.assertEqual(handler._send_json.call_args.args[0], 200)
            for args in (["findings", "--json"], ["timeline", "--json"]):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(fleet.main(args), 0)
            self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()})
            fleet.observation_ssh_json.assert_not_called()

    def test_formal_schema_and_fixtures_fail_closed(self):
        schema_module = load("user_schema_test", "tests/test_monitor_schema.py")
        schema = json.loads((ROOT / "schemas/user-traffic/v1.schema.json").read_text())
        for path in sorted((ROOT / "tests/fixtures/schemas/user-traffic").glob("*.json")):
            doc = json.loads(path.read_text())
            if "-invalid" in path.name:
                self.assertTrue(users.validator.validate_user_traffic_v1(doc), path.name)
                with self.assertRaises(AssertionError, msg=path.name):
                    schema_module.validate(doc, schema)
            else:
                self.assertFalse(users.validator.validate_user_traffic_v1(doc), path.name)
                schema_module.validate(doc, schema)
        doc = snapshot()
        schema_module.validate(doc, schema)
        doc["users"].append({**doc["users"][0], "tag": "different"})
        self.assertTrue(users.validator.validate_user_traffic_v1(doc))  # Unique logical keys, not just unique objects.


if __name__ == "__main__":
    unittest.main()
