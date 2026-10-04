"""0.5.2 M1: local findings lifecycle, uncertainty, cache safety and integration."""
import concurrent.futures
import copy
import importlib.util
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


findings = load("findings_test", "lib/observation/findings.py")
monitor = load("findings_monitor_test", "lib/observation/monitor.py")
BASE = json.loads((ROOT / "tests/fixtures/schemas/telemetry/v1-valid.json").read_text())
NOW = monitor.store_module.health.timestamp(BASE["observed_at"])
NODE = {"name": "test", "node_id": BASE["node_id"], "enabled": True}


def record(at=NOW, **metrics):
    snap = copy.deepcopy(BASE)
    snap["observed_at"] = findings.utc(at)
    snap["accountd"]["active"] = True
    snap["accountd"]["last_poll_age_seconds"] = 1
    result = monitor.store_module.health.build(NODE, {"state": "OK", "snapshot": snap}, {}, at)
    result["metrics"].update(metrics)
    return result


def cursor(at=NOW, **changes):
    return {"instance_id": BASE["instance_id"], "cursor_kind": "export_seq", "status": "ok",
            "last_export_seq": 10, "last_sync_at": findings.utc(at), **changes}


class DetectorTests(unittest.TestCase):
    def test_stall_not_idle_export_and_last_event_age(self):
        doc = record(export_seq=10, last_event_age_seconds=86400)
        self.assertFalse(findings.detect(doc, cursor(), NOW)["AUDIT_STALLED"][0])
        doc["metrics"]["last_poll_age_seconds"] = 91
        self.assertTrue(findings.detect(doc, cursor(), NOW)["AUDIT_STALLED"][0])
        doc["metrics"]["last_poll_age_seconds"] = None
        self.assertIsNone(findings.detect(doc, cursor(), NOW)["AUDIT_STALLED"][0])
        doc["services"]["accountd_active"] = False
        self.assertTrue(findings.detect(doc, cursor(), NOW)["AUDIT_STALLED"][0])
        self.assertTrue(findings.detect(record(last_poll_age_seconds=80), {}, NOW + 11)["AUDIT_STALLED"][0])

    def test_gap_is_expiry_not_sequence_holes(self):
        doc = record(export_seq=1000)
        self.assertFalse(findings.detect(doc, cursor(), NOW)["EXPORT_GAP"][0])
        self.assertTrue(findings.detect(doc, cursor(status="expired"), NOW)["EXPORT_GAP"][0])
        for changes in ({"instance_id": "new"}, {"cursor_kind": "event_id"}, {"status": "error"}):
            self.assertIsNone(findings.detect(doc, cursor(**changes), NOW)["EXPORT_GAP"][0])

    def test_sync_lag_requires_backlog_and_successful_cursor(self):
        doc = record(export_seq=11)
        self.assertTrue(findings.detect(doc, cursor(NOW - 301), NOW)["SYNC_LAG"][0])
        self.assertFalse(findings.detect(doc, cursor(NOW - 300), NOW)["SYNC_LAG"][0])
        self.assertFalse(findings.detect(doc, cursor(NOW - 1000, last_export_seq=11), NOW)["SYNC_LAG"][0])
        for changes in ({"last_export_seq": 12}, {"status": "error"}, {"last_sync_at": None}, {"cursor_kind": "event_id"}):
            self.assertIsNone(findings.detect(doc, cursor(NOW - 1000, **changes), NOW)["SYNC_LAG"][0])

    def test_pressure_hysteresis_and_missing_ratio(self):
        for typ, prefix in (("DISK_PRESSURE", "disk"), ("MEMORY_PRESSURE", "memory")):
            for used, active, expected in ((90, (), True), (89, (), False), (89, (typ,), True), (84, (typ,), False)):
                with self.subTest(typ=typ, used=used, active=active):
                    doc = record(**{prefix + "_total_bytes": 100, prefix + "_used_bytes": used})
                    self.assertEqual(findings.detect(doc, {}, NOW, active)[typ][0], expected)
            for total, used in ((0, 0), (100, None), (100, 101), (True, 1), (float("nan"), 1)):
                doc = record(**{prefix + "_total_bytes": total, prefix + "_used_bytes": used})
                self.assertIsNone(findings.detect(doc, {}, NOW)[typ][0])

    def test_stale_clock_missing_and_transport_uncertainty(self):
        doc = record(last_poll_age_seconds=1000)
        for now in (NOW + 91, NOW - 31):
            signals = findings.detect(doc, cursor(), now)
            self.assertTrue(signals["TELEMETRY_STALE"][0])
            self.assertIsNone(signals["AUDIT_STALLED"][0])
        doc["health"]["observation"]["reason"] = "TELEMETRY_STALE"
        self.assertTrue(findings.detect(doc, cursor(), NOW)["TELEMETRY_STALE"][0])
        self.assertTrue(all(value[0] is None for value in findings.detect({}, {}, NOW).values()))

    def test_detectors_are_pure_and_do_not_echo_secrets(self):
        doc = record(last_poll_age_seconds=91)
        doc["secret"] = "vless://credential; ssh sudo reboot"
        before = copy.deepcopy(doc)
        with mock.patch("subprocess.run", side_effect=AssertionError("no mutation")):
            signals = findings.detect(doc, cursor(), NOW)
        self.assertEqual(doc, before)
        self.assertNotIn("vless", json.dumps(signals))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = findings.Store(Path(self.tmp.name) / "findings.db")

    def evaluate(self, at, **metrics):
        self.store.evaluate(NODE, record(at, **metrics), cursor(at), at)

    def test_dedupe_unknown_resolve_reopen_and_first_seen(self):
        for n in range(10):
            self.evaluate(NOW + n, last_poll_age_seconds=100)
        doc = self.store.read()
        self.assertEqual(len(doc["findings"]), 1)
        item = doc["findings"][0]
        self.assertEqual(item["first_seen"], NOW)
        self.assertEqual(item["last_seen"], NOW + 9)
        self.assertEqual(len([e for e in doc["events"] if e["kind"] == "FINDING_OPEN"]), 1)
        self.store.evaluate(NODE, {}, {}, NOW + 10)
        self.assertEqual(self.store.read()["findings"][0]["state"], "ACTIVE")
        self.assertEqual(self.store.read()["evaluations"][0]["checks"]["AUDIT_STALLED"], "UNKNOWN")
        self.evaluate(NOW + 11, last_poll_age_seconds=1)
        self.assertEqual(self.store.read()["findings"][0]["state"], "RESOLVED")
        self.evaluate(NOW + 12, last_poll_age_seconds=100)
        item2 = self.store.read()["findings"][0]
        self.assertEqual(item["finding_id"], item2["finding_id"])
        self.assertEqual(item2["first_seen"], NOW)

    def test_replayed_evaluation_cannot_rewind_or_resolve(self):
        self.evaluate(NOW + 2, last_poll_age_seconds=100)
        before = self.store.path.read_bytes()
        self.evaluate(NOW + 1, last_poll_age_seconds=1)
        self.evaluate(NOW + 2, last_poll_age_seconds=1)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_rename_filters_by_stable_identity(self):
        self.evaluate(NOW, last_poll_age_seconds=100)
        renamed = {**NODE, "name": "renamed"}
        self.assertEqual(self.store.read(nodes=[renamed])["findings"][0]["subject"]["name"], "renamed")
        another = {**NODE, "node_id": "33333333-3333-4333-8333-333333333333"}
        self.assertEqual(self.store.read(nodes=[another])["findings"], [])

    def test_corrupt_rows_isolated_and_replaced_without_sensitive_echo(self):
        self.evaluate(NOW, last_poll_age_seconds=100)
        with closing(self.store.writer()) as conn:
            conn.execute("INSERT INTO findings VALUES(?,?,?)", ("broken", NOW + 1, "vless://secret"))
            conn.execute("INSERT INTO timeline VALUES(?,?,?)", ("broken", NOW + 1, "[" * 1100 + "0" + "]" * 1100))
            fid = self.store.read()["findings"][0]["finding_id"]
            conn.execute("UPDATE findings SET payload=? WHERE id=?", ('{"secret":"credential"}', fid))
            conn.commit()
        doc = self.store.read()
        self.assertEqual(doc["cache_state"], "PARTIAL")
        self.assertNotIn("credential", json.dumps(doc))
        self.evaluate(NOW + 2, last_poll_age_seconds=100)
        self.assertEqual(len(self.store.read()["findings"]), 1)

    def test_schema_corruption_read_only_empty_and_whole_db(self):
        self.assertEqual(self.store.read()["cache_state"], "EMPTY")
        self.assertFalse(self.store.path.exists())
        self.store.path.write_bytes(b"not SQLite")
        before = self.store.path.read_bytes()
        self.assertEqual(self.store.read()["cache_state"], "CACHE_CORRUPT")
        with self.assertRaises(sqlite3.Error):
            self.evaluate(NOW)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_locked_write_and_failure_rollback_preserve_old_state(self):
        self.evaluate(NOW, last_poll_age_seconds=100)
        before = self.store.path.read_bytes()
        with closing(self.store.writer()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                self.evaluate(NOW + 1)
            conn.rollback()
        self.assertEqual(self.store.path.read_bytes(), before)
        with mock.patch.object(self.store, "prune", side_effect=sqlite3.OperationalError("database or disk is full")):
            with self.assertRaises(sqlite3.OperationalError):
                self.evaluate(NOW + 2)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.evaluate(NOW + 3)
        self.assertEqual(self.store.read()["findings"][0]["state"], "RESOLVED")

    def test_concurrent_open_has_single_finding_and_transition(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self.evaluate, NOW + n, last_poll_age_seconds=100) for n in range(16)]
            for future in futures:
                future.result()
        doc = self.store.read()
        self.assertEqual(len(doc["findings"]), 1)
        self.assertEqual(len([e for e in doc["events"] if e["kind"] == "FINDING_OPEN"]), 1)
        self.assertEqual(doc["findings"][0]["last_seen"], NOW + 15)

    def test_retention_cap_truncation_and_corrupt_expired_rows(self):
        # Every supported monitor target can retain every active detector without eviction flood.
        self.assertGreaterEqual(findings.FINDING_CAP, findings.SUBJECT_CAP * len(findings.TYPES))
        self.evaluate(NOW, last_poll_age_seconds=100)
        self.evaluate(NOW + 1)
        with closing(self.store.writer()) as conn:
            conn.execute("INSERT INTO findings VALUES(?,?,?)", ("broken", NOW, "bad json"))
            conn.commit()
        self.evaluate(NOW + findings.RETENTION + 2)
        self.assertEqual(self.store.read()["findings"], [])
        with mock.patch.object(findings, "FINDING_CAP", 2), mock.patch.object(findings, "EVENT_CAP", 3), mock.patch.object(findings, "SUBJECT_CAP", 2):
            for n in range(4):
                node = {**NODE, "name": "n" + str(n), "node_id": f"{n+4:08d}-3333-4333-8333-333333333333"}
                self.store.evaluate(node, record(NOW + n, last_poll_age_seconds=100), cursor(), NOW + n)
            with closing(self.store.writer()) as conn:
                self.assertLessEqual(conn.execute("SELECT count(*) FROM timeline").fetchone()[0], 3)
                self.assertLessEqual(conn.execute("SELECT count(*) FROM evaluations").fetchone()[0], 2)
                self.assertLessEqual(conn.execute("SELECT count(*) FROM findings").fetchone()[0], 2)
            self.assertIn("timeline", self.store.read()["truncated"])
            self.assertIn("findings", self.store.read()["truncated"])

    def test_service_and_probe_changes_only_emit_transitions(self):
        doc = record()
        self.store.evaluate(NODE, doc, cursor(), NOW)
        self.store.evaluate(NODE, doc, cursor(), NOW + 1)
        doc["services"]["sing_box_active"] = False
        doc["probe"] = {"success": False, "reason": "TLS_FAILED"}
        self.store.evaluate(NODE, doc, cursor(), NOW + 2)
        events = self.store.read()["events"]
        self.assertEqual(len([e for e in events if e["kind"] == "SERVICE_CHANGE"]), 2)
        self.assertEqual(len([e for e in events if e["kind"] == "PROBE_RESULT"]), 1)


class IntegrationTests(unittest.TestCase):
    def test_monitor_finding_failure_keeps_telemetry_and_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = monitor.Store(Path(tmp) / "observation.db")
            service = monitor.Monitor([NODE], store, lambda node, **kw: {"state": "OK", "snapshot": BASE},
                                      wall_clock=lambda: NOW, on_record=mock.Mock(side_effect=ValueError("sensitive error")))
            result = service.run(once=True)
            self.assertEqual(result["cache_write_errors"], 0)
            self.assertEqual(result["finding_write_errors"], 1)
            self.assertEqual(store.read([NODE], NOW)["nodes"][0]["observation_state"], "OK")

    def test_cache_only_cli_ui_get_and_empty_reads_do_not_write_or_ssh(self):
        fleet = load("finding_fleet_integration", "lib/vincula-fleet.py")
        ui = load("finding_ui_integration", "lib/vincula-ui/server.py")
        ui.set_fleet_module(fleet)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fleet.fleet_db_path = lambda: root / "fleet.db"
            fleet.operation_journal_path = lambda **kw: root / "operations.jsonl"
            fleet.load_registry = lambda: {"nodes": [NODE]}
            fleet.ssh_run = mock.Mock(side_effect=AssertionError("display must not SSH"))
            fleet.fetch_node_telemetry = mock.Mock(side_effect=AssertionError("display must not sample"))
            for path in ("/api/findings", "/api/timeline"):
                handler = SimpleNamespace(_send_json=mock.Mock())
                ui.FleetUIHandler._handle_api_get(handler, path, {})
                self.assertEqual(handler._send_json.call_args.args[0], 200)
            self.assertEqual(list(root.iterdir()), [])
            findings.Store(root / "findings.db").evaluate(NODE, record(), cursor(), NOW)
            before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
            for path in ("/api/findings", "/api/timeline"):
                handler = SimpleNamespace(_send_json=mock.Mock())
                ui.FleetUIHandler._handle_api_get(handler, path, {})
                self.assertEqual(handler._send_json.call_args.args[0], 200)
            for args in (["findings", "--json"], ["timeline", "--json"]):
                with mock.patch("sys.stdout"):
                    self.assertEqual(fleet.main(args), 0)
            self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()})
            fleet.ssh_run.assert_not_called()
            fleet.fetch_node_telemetry.assert_not_called()

    def test_explicit_refresh_reads_cursor_and_telemetry_without_modifying_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host = SimpleNamespace(fleet_db_path=lambda: root / "fleet.db")
            with closing(sqlite3.connect(root / "fleet.db")) as conn:
                conn.executescript("CREATE TABLE sync_cursor(node_id TEXT,instance_id TEXT,last_export_seq INTEGER,cursor_kind TEXT,last_sync_at TEXT,status TEXT);")
                conn.execute("INSERT INTO sync_cursor VALUES(?,?,?,?,?,?)", (NODE["node_id"], BASE["instance_id"], 10, "export_seq", findings.utc(NOW), "expired"))
                conn.commit()
            snap = copy.deepcopy(BASE)
            snap["observed_at"] = findings.utc(NOW)
            monitor.Store(root / "observation.db").record(NODE, {"state": "OK", "snapshot": snap}, NOW)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            self.assertEqual(findings.refresh(host, [NODE], NOW + 1), "OK")
            self.assertTrue(any(f["type"] == "EXPORT_GAP" for f in findings.cached(host, [NODE])["findings"]))
            for name, data in before.items():
                self.assertEqual((root / name).read_bytes(), data)

    def test_timeline_sorted_corrupt_tolerant_and_secret_allowlisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host = SimpleNamespace(fleet_db_path=lambda: root / "fleet.db", operation_journal_path=lambda **kw: root / "operations.jsonl")
            findings.Store(root / "findings.db").evaluate(NODE, record(last_poll_age_seconds=100), cursor(), NOW)
            journal = {"operation": "verify", "state": "FAILED", "target": "test", "time": findings.utc(NOW),
                       "exit_code": 2, "operation_id": "secret-uuid", "detail": "vless://credential ssh sudo reboot"}
            host.operation_journal_path().write_text(json.dumps(journal) + "\n{bad json\n[]\n", encoding="utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            doc = findings.timeline(host, [NODE])
            self.assertEqual(doc["cache_state"], "PARTIAL")
            self.assertTrue(any(e["kind"] == "OPERATION" for e in doc["events"]))
            self.assertEqual(doc["events"], sorted(doc["events"], key=lambda e: (-e["at"], e["id"])))
            for secret in ("credential", "secret-uuid", "sudo", "vless://"):
                self.assertNotIn(secret, json.dumps(doc))
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            self.assertEqual(doc, findings.timeline(host, [NODE]))


if __name__ == "__main__":
    unittest.main()
