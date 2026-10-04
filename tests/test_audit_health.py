"""M2 bounded audit diagnostics, identity, uncertainty and public contract safety."""
import copy
import importlib.util
import io
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


node_module = load("audit_node_test", "lib/telemetry_snapshot.py")
daemon_module = load("audit_daemon_test", "lib/vincula-accountd.py")
audit = load("audit_transport_test", "lib/observation/audit_health.py")
findings = load("audit_findings_test", "lib/observation/findings.py")
monitor = load("audit_monitor_test", "lib/observation/monitor.py")
BASE = json.loads((ROOT / "tests/fixtures/schemas/telemetry/v1-valid.json").read_text())
NODE = {"name": "test", "node_id": BASE["node_id"], "enabled": True}
NOW = monitor.store_module.health.timestamp(BASE["observed_at"])


def diagnostic(at=NOW, **changes):
    return {"schema": "audit-health/v1", "node_id": BASE["node_id"], "instance_id": BASE["instance_id"],
            "observed_at": findings.utc(at), "accountd_active": True, "db_state": "OK", "db_schema": 4,
            "heartbeat_age_seconds": 1, "last_poll_age_seconds": 1, "last_event_age_seconds": None,
            "export_seq": 100, "min_retained_export_seq": 81, "pruned_max_export_seq": 80, **changes}


class NodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config.toml").write_text(f'node_id = "{BASE["node_id"]}"\nclash_api_secret = "private-secret"\n')
        (self.root / "state.json").write_text(json.dumps({"instance_id": BASE["instance_id"], "private_key": "secret"}))
        self.db = self.root / "accounting.db"

    def create_db(self):
        conn = daemon_module.open_db(str(self.db))
        for key, value in (("heartbeat_at", node_module._utc_now()), ("last_success_at", node_module._utc_now()),
                           ("audit_export_seq", "100"), ("audit_pruned_max_export_seq", "80"), ("secret", "private-secret")):
            daemon_module.meta_set(conn, key, value)
        conn.commit()
        conn.close()

    def snapshot(self, **kw):
        with mock.patch.object(node_module, "_systemd_active", return_value=True):
            return node_module.build_audit_snapshot(state_dir=self.root, accounting_db=self.db, **kw)

    def test_readonly_valid_db_and_no_secret_fields(self):
        self.create_db()
        before = (self.db.read_bytes(), self.db.stat().st_mtime_ns)
        doc = self.snapshot()
        self.assertEqual(doc["db_state"], "OK")
        self.assertEqual(doc["export_seq"], 100)
        self.assertEqual(doc["pruned_max_export_seq"], 80)
        self.assertIsNone(doc["last_event_age_seconds"])
        self.assertFalse(audit.validator.validate_audit_health_v1(doc))
        self.assertNotIn("private-secret", json.dumps(doc))
        self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))

    def test_missing_schema_corrupt_and_unreadable_are_distinct(self):
        self.assertEqual(self.snapshot()["db_state"], "MISSING")
        self.assertFalse(self.db.exists())
        self.create_db()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE meta SET value='3' WHERE key='schema_version'")
            conn.commit()
        self.assertEqual(self.snapshot()["db_state"], "SCHEMA_MISMATCH")
        self.db.write_bytes(b"not SQLite secret")
        self.assertEqual(self.snapshot()["db_state"], "CORRUPT")
        with mock.patch.object(node_module.sqlite3, "connect", side_effect=PermissionError("secret")):
            doc = self.snapshot()
            self.assertEqual(doc["db_state"], "UNREADABLE")
            self.assertNotIn("secret", json.dumps(doc))

    def test_schema_marker_alone_does_not_prove_structural_health(self):
        self.create_db()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("DROP TABLE poll_baseline")
            conn.commit()
        self.assertEqual(self.snapshot()["db_state"], "SCHEMA_MISMATCH")

    def test_deadline_interrupt_is_unknown_not_corruption(self):
        self.create_db()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executemany("INSERT INTO poll_baseline VALUES(?,?,?,?,?,?,?)", [(str(n), 0, 0, 0, 0, 0, node_module._utc_now()) for n in range(1000)])
            conn.commit()
        with mock.patch.object(node_module.time, "monotonic", side_effect=lambda: time.perf_counter() + 100):
            # A fixed false deadline is injected directly rather than relying on machine speed.
            with mock.patch.object(node_module.time, "monotonic", side_effect=[0] + [100] * 3000):
                self.assertEqual(self.snapshot()["db_state"], "UNKNOWN")

    def test_failed_poll_updates_loop_heartbeat_but_not_success_time(self):
        self.create_db()
        with closing(daemon_module.open_db(str(self.db))) as conn:
            daemon_module.meta_set(conn, "last_success_at", BASE["observed_at"])
            conn.commit()
            daemon = daemon_module.AccountDaemon(db_path=str(self.db), clash_url="http://127.0.0.1:1")
            daemon._cycles = 2
            with mock.patch.object(daemon, "_collect", return_value=(False, None)), mock.patch.object(daemon, "_reload_tag_map_if_changed"):
                daemon._tick(conn)
            self.assertEqual(daemon_module.meta_get(conn, "last_success_at"), BASE["observed_at"])
            self.assertTrue(daemon_module.meta_get(conn, "heartbeat_at"))
            self.assertFalse(conn.in_transaction)


class PipelineTests(unittest.TestCase):
    def test_export_progression_idle_replay_regression_failure_and_instance_reset(self):
        baseline = None
        for n, seq, expected in ((0, 100, "COLD"), (1, 100, "STATIONARY"), (2, 105, "ADVANCING"),
                                 (3, 99, "REGRESSED"), (4, 105, "STATIONARY")):
            result = {"state": "OK", "snapshot": diagnostic(NOW + n, export_seq=seq, last_event_age_seconds=0)}
            progress, baseline = audit.progression(result, baseline, NOW + n)
            self.assertEqual(progress["state"], expected)
            if expected == "REGRESSED":
                self.assertEqual(baseline["export_seq"], 105)
        saved = copy.deepcopy(baseline)
        progress, baseline = audit.progression({"state": "ERROR"}, baseline, NOW + 5)
        self.assertEqual(progress["state"], "UNKNOWN")
        self.assertEqual(baseline, saved)
        for at in (NOW + 3, NOW + 4):
            progress, baseline = audit.progression({"state": "OK", "snapshot": diagnostic(at, export_seq=999)}, baseline, NOW + 5)
            self.assertEqual(progress["state"], "REPLAYED")
            self.assertEqual(baseline, saved)
        progress, baseline = audit.progression({"state": "OK", "snapshot": diagnostic(NOW + 6, export_seq=0,
            instance_id="33333333-3333-4333-8333-333333333333")}, baseline, NOW + 6)
        self.assertEqual(progress["state"], "COLD")
        self.assertEqual(baseline["export_seq"], 0)

    def test_regression_finding_survives_replay_and_closes_on_known_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = monitor.Store(Path(tmp) / "observation.db")
            alert_store = findings.Store(Path(tmp) / "findings.db")
            samples = ((0, 100, NOW, "COLD"), (1, 90, NOW + 1, "REGRESSED"),
                       (2, 100, NOW, "REPLAYED"), (3, 101, NOW + 3, "ADVANCING"))
            for n, seq, audit_at, expected in samples:
                snap = copy.deepcopy(BASE)
                snap["observed_at"] = findings.utc(NOW + n)
                result = {"state": "OK", "snapshot": snap,
                          "audit_health": {"state": "OK", "snapshot": diagnostic(audit_at, export_seq=seq)}}
                record = store.record(NODE, result, NOW + n)
                self.assertEqual(record["audit_progress"]["state"], expected)
                alert_store.evaluate(NODE, record, {}, NOW + n)
                if n in (1, 2):
                    self.assertEqual(record["health"]["accounting"]["state"], "UNKNOWN")
                    item = next(f for f in alert_store.read()["findings"] if f["type"] == "EXPORT_SEQUENCE_REGRESSION")
                    self.assertEqual(item["state"], "ACTIVE")
                public = store.read([NODE], NOW + n)["nodes"][0]
                self.assertFalse({"audit_health", "audit_progress", "audit_baseline"} & set(public))
            self.assertEqual(next(f for f in alert_store.read()["findings"] if f["type"] == "EXPORT_SEQUENCE_REGRESSION")["state"], "RESOLVED")
            pipeline = alert_store.read()["evaluations"][0]["audit"]
            self.assertEqual(pipeline["progression"], "ADVANCING")
            self.assertNotIn(BASE["instance_id"], json.dumps(pipeline))

    def test_corrupt_and_regressed_samples_advance_replay_watermark(self):
        _, baseline = audit.progression({"state": "OK", "snapshot": diagnostic()}, None, NOW)
        for n, changes in ((2, {"db_state": "CORRUPT"}), (4, {"export_seq": 50})):
            _, baseline = audit.progression({"state": "OK", "snapshot": diagnostic(NOW + n, **changes)}, baseline, NOW + n)
            self.assertEqual(baseline["observed_at"], findings.utc(NOW + n))
            result, after = audit.progression({"state": "OK", "snapshot": diagnostic(NOW + n - 1)}, baseline, NOW + n + 1)
            self.assertEqual(result["state"], "REPLAYED")
            self.assertEqual(after, baseline)

    def test_stale_or_missing_diagnostic_cannot_resolve_active_audit_findings(self):
        record = {"instance_id": BASE["instance_id"], "observed_at": findings.utc(NOW),
                  "observation_state": "OK", "health": {}, "services": {"accountd_active": True},
                  "metrics": {"last_poll_age_seconds": 1, "export_seq": 100},
                  "audit_health": {"state": "OK", "snapshot": diagnostic(NOW - 100)}}
        cursor = {"instance_id": BASE["instance_id"], "cursor_kind": "export_seq", "last_export_seq": 80,
                  "status": "ok", "last_sync_at": findings.utc(NOW)}
        for diag in ({"state": "OK", "snapshot": diagnostic(NOW - 100)},
                     {"state": "OK", "snapshot": diagnostic(db_state="UNKNOWN")}, {"state": "TIMEOUT"}):
            record["audit_health"] = diag
            signals = findings.detect(record, cursor, NOW)
            for typ in ("AUDIT_STALLED", "SYNC_LAG", "EXPORT_GAP", "SCHEMA_MISMATCH", "ACCOUNTING_DB_CORRUPT"):
                self.assertIsNone(signals[typ][0], typ)
        record["audit_health"] = {"state": "OK", "snapshot": diagnostic(export_seq=81)}
        record["metrics"]["export_seq"] = 80
        cursor["last_sync_at"] = findings.utc(NOW - 301)
        self.assertTrue(findings.detect(record, cursor, NOW)["SYNC_LAG"][0])

    def test_schema_positive_negative_and_json_shape(self):
        schema_test = load("audit_json_schema_test", "tests/test_monitor_schema.py")
        schema = json.loads((ROOT / "schemas/audit-health/v1.schema.json").read_text())
        schema_test.SCHEMA = schema
        schema_test.validate(diagnostic(), schema)
        for changes in ({"db_schema": 3}, {"export_seq": True}, {"heartbeat_age_seconds": -1}, {"secret": "x"}, {"db_state": []}):
            doc = diagnostic(**changes)
            self.assertTrue(audit.validator.validate_audit_health_v1(doc))
            with self.assertRaises(AssertionError):
                schema_test.validate(doc, schema)
        for path in sorted((ROOT / "tests/fixtures/schemas/audit-health").glob("*.json")):
            doc = json.loads(path.read_text())
            if "-invalid" in path.name:
                self.assertTrue(audit.validator.validate_audit_health_v1(doc), path.name)
                with self.assertRaises(AssertionError, msg=path.name):
                    schema_test.validate(doc, schema)
            else:
                self.assertFalse(audit.validator.validate_audit_health_v1(doc), path.name)
                schema_test.validate(doc, schema)

    def test_capability_identity_and_failure_never_echo_payload(self):
        ssh = mock.Mock(return_value=("OK", diagnostic(), "private-error"))
        caps = {"state": "OK", "capabilities": ["audit-health/v1"]}
        self.assertEqual(audit.fetch(NODE, capabilities=caps, instance_id=BASE["instance_id"], ssh_json=ssh)["state"], "OK")
        self.assertEqual(audit.fetch(NODE, capabilities=caps, instance_id="wrong", ssh_json=ssh), {"state": "ERROR"})
        self.assertEqual(audit.fetch(NODE, capabilities={"state": "OK"}, instance_id=None, ssh_json=ssh), {"state": "UNSUPPORTED"})
        ssh.return_value = ("AUTH_FAILED", {"secret": "private"}, "private-error")
        self.assertEqual(audit.fetch(NODE, capabilities=caps, instance_id=BASE["instance_id"], ssh_json=ssh), {"state": "AUTH_FAILED"})

    def test_diagnostic_failure_preserves_valid_telemetry_and_same_deadline(self):
        fleet = load("audit_fleet_test", "lib/vincula-fleet.py")
        calls = []
        def ssh(node, command, **kw):
            calls.append((command, kw["timeout"]))
            if command == ["vcl", "identity", "--json"]:
                return "OK", BASE, ""
            if command == ["vcl", "telemetry", "audit", "--json"]:
                raise TimeoutError("secret")
            return "OK", BASE, ""
        fleet.observation_ssh_json = ssh
        result = fleet.fetch_node_telemetry(NODE, capabilities={"state": "OK", "capabilities": ["telemetry/v1", "audit-health/v1"]}, timeout=5)
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["audit_health"], {"state": "ERROR"})
        self.assertTrue(all(0 < deadline <= 5 for _, deadline in calls))
        self.assertEqual(len(calls), 3)

    def test_private_diagnostic_cache_public_v1_and_finding_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = monitor.Store(Path(tmp) / "observation.db")
            alert_store = findings.Store(Path(tmp) / "findings.db")
            states = (("CORRUPT", "DEGRADED", "ACTIVE"), ("UNKNOWN", "UNKNOWN", "ACTIVE"),
                      ("CORRUPT", "DEGRADED", "ACTIVE"), ("OK", "RECOVERING", "RESOLVED"), ("OK", "HEALTHY", "RESOLVED"))
            for n, (state, expected_health, expected_finding) in enumerate(states):
                snap = copy.deepcopy(BASE)
                at = NOW + n
                snap["observed_at"] = findings.utc(at)
                result = {"state": "OK", "snapshot": snap, "audit_health": {"state": "OK", "snapshot": diagnostic(at, db_state=state)}}
                record = store.record(NODE, result, at)
                alert_store.evaluate(NODE, record, {}, at)
                self.assertNotIn("audit_health", store.read([NODE], at)["nodes"][0])
                self.assertIn("audit_health", store.read([NODE], at, include_audit=True)["nodes"][0])
                self.assertEqual(next(f for f in alert_store.read()["findings"] if f["type"] == "ACCOUNTING_DB_CORRUPT")["state"], expected_finding)
                self.assertEqual(record["health"]["accounting"]["state"], expected_health)

    def test_watermark_gap_schema_and_heartbeat_unknown(self):
        record = {"instance_id": BASE["instance_id"], "audit_health": {"state": "OK", "snapshot": diagnostic()}}
        cursor = {"instance_id": BASE["instance_id"], "cursor_kind": "export_seq", "last_export_seq": 79, "status": "ok"}
        self.assertTrue(findings.detect(record, cursor, NOW)["EXPORT_GAP"][0])
        cursor["last_export_seq"] = 80
        self.assertFalse(findings.detect(record, cursor, NOW)["EXPORT_GAP"][0])
        record["audit_health"]["snapshot"] = diagnostic(db_state="SCHEMA_MISMATCH", db_schema=3)
        self.assertTrue(findings.detect(record, cursor, NOW)["SCHEMA_MISMATCH"][0])
        self.assertIsNone(findings.detect(record, cursor, NOW)["ACCOUNTING_DB_CORRUPT"][0])
        record["audit_health"]["snapshot"] = diagnostic(heartbeat_age_seconds=None)
        self.assertIsNone(findings.detect(record, cursor, NOW)["AUDIT_STALLED"][0])

    def test_monitor_run_json_obeys_new_schema_and_cache_stays_v1(self):
        schema_test = load("audit_monitor_schema", "tests/test_monitor_schema.py")
        schema_test.SCHEMA = json.loads((ROOT / "schemas/monitor/v2.schema.json").read_text())
        fleet = load("audit_monitor_fleet", "lib/vincula-fleet.py")
        with tempfile.TemporaryDirectory() as tmp:
            fleet.fleet_db_path = lambda: Path(tmp) / "fleet.db"
            fleet.load_registry = lambda: {"nodes": [NODE]}
            snap = copy.deepcopy(BASE)
            snap["observed_at"] = findings.utc(time.time())
            fleet.fetch_node_telemetry = lambda *a, **kw: {"state": "OK", "snapshot": snap}
            args = SimpleNamespace(name=None, interval=30, timeout=5, concurrency=1, once=True, as_json=True, probe_profiles=None)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(fleet.load_monitor_module().run_cli(fleet._FLEET_HOST, args), 0)
            doc = json.loads(output.getvalue())
            self.assertEqual(doc["schema"], "monitor/v2")
            schema_test.validate(doc, schema_test.SCHEMA)
            self.assertEqual(fleet.monitor_cached_health()["schema"], "monitor/v1")


if __name__ == "__main__":
    unittest.main()
