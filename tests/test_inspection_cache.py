"""Explicit baselines, bounded persistence, drift and cache-only Controller surfaces."""
import copy
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import test_inspect as inventory
import test_monitor as monitoring
import test_findings as finding_support
import test_findings_schema as schemas

ROOT = inventory.ROOT
cache = monitoring.load("inspection_cache_tests", "lib/observation/inspection_cache.py")
NODE = {"name": "test", "node_id": inventory.NODE_ID, "ssh_host": "example.test", "ssh_port": 22, "ssh_user": "root", "observe_ssh_user": "vincula-observer", "observe_credential_ref": "local-observer"}
INSTANCE = inventory.INSTANCE_ID
NOW = time.time()


def sample(at=NOW):
    doc = json.loads((ROOT / "tests/fixtures/schemas/inspect/v1-valid.json").read_text(encoding="utf-8"))
    doc.update(node_id=NODE["node_id"], instance_id=INSTANCE, observed_at=monitoring.health.utc(at))
    return doc


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "inspection.db"
        self.store = cache.Store(self.path)
        self.doc = sample()

    def record(self, doc=None, at=NOW, **kw):
        self.store.record(NODE, {"state": "OK", "snapshot": doc or self.doc}, at, kw.get("instance", INSTANCE))

    def view(self, at=NOW, **kw):
        return self.store.read([kw.get("node", NODE)], at, {NODE["node_id"]: kw.get("instance", INSTANCE)}, detail=True)["nodes"][0]

    def accept(self):
        return self.store.accept(NODE, cache.sha(self.doc), NOW, INSTANCE)

    def test_empty_read_and_failed_accept_do_not_create_files(self):
        self.assertEqual(self.view()["reason"], "EMPTY")
        with self.assertRaisesRegex(ValueError, "EMPTY"):
            self.accept()
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_first_sample_never_accepts_and_baseline_source_event_is_explicit(self):
        self.record()
        self.assertEqual(self.view()["reason"], "NO_BASELINE")
        event = self.accept()
        self.assertEqual(event["kind"], "BASELINE_ACCEPTED")
        self.assertEqual(self.view()["drift"]["state"], "MATCH")
        self.assertEqual(self.view()["baseline"]["source"], "LOCAL_ACCEPTED")
        before = self.path.read_bytes()
        self.store.events([NODE], 100)
        self.view()
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaisesRegex(ValueError, "BASELINE_CHANGED"):
            self.store.accept(NODE, "0" * 64, NOW + 1, INSTANCE, True)
        self.store.accept(NODE, event["detail"]["baseline_sha256"], NOW + 1, INSTANCE, True)
        self.assertEqual(self.view()["reason"], "NO_BASELINE")

    def test_cas_rechecks_latest_in_transaction_and_failed_accept_does_not_write(self):
        self.record()
        newer = sample(NOW + 1)
        self.record(newer, NOW + 1)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_CHANGED"):
            self.accept()
        self.assertEqual(before, self.path.read_bytes())

    def test_stale_future_replay_and_failed_transport_never_match_or_autoaccept(self):
        self.record()
        self.accept()
        self.assertEqual(self.view(NOW + 601)["reason"], "STALE")
        for result, expected in (({"state": "OK", "snapshot": self.doc}, "REPLAYED"),
                ({"state": "OK", "snapshot": sample(NOW + 40)}, "CLOCK_SKEW"), ({"state": "AUTH_FAILED"}, "AUTH_FAILED")):
            self.store.record(NODE, result, NOW + 1, INSTANCE)
            self.assertEqual(self.view(NOW + 1)["reason"], expected)
            self.assertEqual(self.view(NOW + 1)["drift"]["state"], "UNKNOWN")
            with self.assertRaises(ValueError):
                self.store.accept(NODE, cache.sha(self.doc), NOW + 1, INSTANCE)
        self.record(sample(NOW + 2), NOW + 2)
        self.assertEqual(self.view(NOW + 2)["drift"]["state"], "MATCH")

    def test_current_instance_and_endpoint_binding_invalidate_old_baseline(self):
        self.record()
        self.accept()
        self.assertEqual(self.view(instance="33333333-3333-4333-8333-333333333333")["reason"], "IDENTITY")
        self.assertEqual(self.view(node={**NODE, "observe_credential_ref": "new-ref"})["reason"], "ENDPOINT")
        self.assertEqual(self.view(instance=None)["drift"]["state"], "UNKNOWN")
        doc = sample(NOW + 1)
        doc["instance_id"] = "33333333-3333-4333-8333-333333333333"
        self.record(doc, NOW + 1, instance=doc["instance_id"])
        self.assertEqual(self.view(NOW + 1, instance=doc["instance_id"])["reason"], "IDENTITY")

    def test_partial_coverage_unknown_restart_count_excluded_and_actual_drift(self):
        self.record()
        self.accept()
        doc = sample(NOW + 1)
        for row in doc["services"]["items"]:
            row["restart_count"] += 100
        self.record(doc, NOW + 1)
        self.assertEqual(self.view(NOW + 1)["drift"]["state"], "MATCH")
        doc = sample(NOW + 2)
        doc["state"] = "PARTIAL"
        doc["listeners"].update(state="PARTIAL", reason="LIMIT", truncated=True)
        doc["fingerprints"]["items"][0]["sha256"] = "f" * 64
        self.record(doc, NOW + 2)
        result = self.view(NOW + 2)
        self.assertEqual(result["drift"]["checks"]["listeners"]["state"], "UNKNOWN")
        self.assertEqual(result["drift"]["state"], "DRIFT")
        with self.assertRaisesRegex(ValueError, "COVERAGE"):
            self.store.accept(NODE, cache.sha(doc), NOW + 2, INSTANCE)

    def test_duplicate_or_missing_fingerprints_and_services_cannot_be_baseline(self):
        for section in ("services", "fingerprints"):
            doc = sample()
            doc[section]["items"][-1] = copy.deepcopy(doc[section]["items"][0])
            self.record(doc)
            with self.assertRaisesRegex(ValueError, "COVERAGE"):
                self.store.accept(NODE, cache.sha(doc), NOW, INSTANCE)
            self.path.unlink()

    def test_corrupt_and_secret_injected_rows_are_isolated_read_only(self):
        self.record()
        with closing(sqlite3.connect(self.path)) as conn, conn:
            raw = json.loads(conn.execute("SELECT payload FROM latest").fetchone()[0])
            raw["snapshot"]["secret"] = "never-echo"
            conn.execute("UPDATE latest SET payload=?", (json.dumps(raw),))
        before = self.path.read_bytes()
        result = self.store.read([NODE], NOW, {NODE["node_id"]: INSTANCE}, True)
        self.assertEqual(result["cache_state"], "PARTIAL")
        self.assertNotIn("never-echo", json.dumps(result))
        self.assertEqual(before, self.path.read_bytes())
        self.path.write_bytes(b"bad database")
        self.assertEqual(self.store.read([NODE], NOW)["cache_state"], "CACHE_CORRUPT")

    def test_capacity_and_locked_writer_do_not_evict_accepted_baseline(self):
        self.record()
        self.accept()
        other = {**NODE, "name": "other", "node_id": "33333333-3333-4333-8333-333333333333"}
        doc = sample()
        doc["node_id"] = other["node_id"]
        with mock.patch.object(cache, "CAP", 1), self.assertRaisesRegex(ValueError, "CAPACITY"):
            self.store.record(other, {"state": "OK", "snapshot": doc}, NOW, INSTANCE)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                self.record(sample(NOW + 1), NOW + 1)
            conn.rollback()
        self.assertEqual(self.view()["drift"]["state"], "MATCH")

    def test_drift_findings_unknown_retains_active_match_resolves_stable_id(self):
        store = finding_support.findings.Store(self.path.with_name("findings.db"))
        rec = finding_support.record()
        rec["inspection"] = {"drift": {"checks": {"config": {"state": "DRIFT", "changed_count": 1}}}}
        store.evaluate(NODE, rec, {}, NOW)
        row = next(r for r in store.read()["findings"] if r["type"] == "DRIFT_CONFIG")
        rec["inspection"] = {"drift": {"checks": {}}}
        store.evaluate(NODE, rec, {}, NOW + 1)
        self.assertEqual(next(r for r in store.read()["findings"] if r["type"] == "DRIFT_CONFIG")["state"], "ACTIVE")
        rec["inspection"] = {"drift": {"checks": {"config": {"state": "MATCH", "changed_count": 0}}}}
        store.evaluate(NODE, rec, {}, NOW + 2)
        resolved = next(r for r in store.read()["findings"] if r["type"] == "DRIFT_CONFIG")
        self.assertEqual(resolved["state"], "RESOLVED")
        self.assertEqual(row["finding_id"], resolved["finding_id"])
        schemas.validate(store.read(), "findings")

    def test_monitor_cadence_inspection_write_failure_and_shared_rpc_deadline(self):
        now = [0]
        requests = []
        def fetch(n, **kw):
            requests.append(kw)
            out = monitoring.ok(NOW, node_id=NODE["node_id"], instance_id=INSTANCE)
            if kw.get("with_inspection"):
                out["inspection"] = {"state": "OK", "snapshot": sample()}
            return out
        service = monitoring.monitor.Monitor([NODE], monitoring.monitor.Store(self.path.with_name("observation.db")), fetch,
            inspection_store=self.store, clock=lambda: now[0], wall_clock=lambda: NOW)
        service.collect(NODE)
        now[0] = 30
        service.collect(NODE)
        now[0] = 301
        service.collect(NODE)
        self.assertEqual([bool(r.get("with_inspection")) for r in requests], [True, False, True])
        with mock.patch.object(self.store, "record", side_effect=sqlite3.OperationalError("full")):
            result = service.run(once=True)
        # Reset cadence so this round actually writes an inspection.
        now[0] = 602
        service.due[NODE["node_id"]] = 602
        with mock.patch.object(self.store, "record", side_effect=sqlite3.OperationalError("full")):
            result = service.run(once=True)
        self.assertEqual(result["inspection_write_errors"], 1)
        self.assertEqual(result["cache_write_errors"], 0)
        fleet = monitoring.load("inspection_fleet", "lib/vincula-fleet.py")
        elapsed = [0]
        caps = {"state": "OK", "capabilities": ["telemetry/v1", "inspect/v1"]}
        def rpc(node, cmd, **kw):
            self.assertEqual(kw["credential_class"], "observe")
            self.assertLessEqual(kw["timeout"], 5 - elapsed[0])
            elapsed[0] += 2
            if cmd[1] == "telemetry":
                return "OK", monitoring.ok(NOW, node_id=NODE["node_id"], instance_id=INSTANCE)["snapshot"], ""
            if cmd[1] == "identity":
                return "OK", {"node_id": NODE["node_id"], "instance_id": INSTANCE}, ""
            return "OK", sample(), ""
        with mock.patch.object(fleet, "observation_ssh_json", side_effect=rpc), mock.patch("time.monotonic", side_effect=lambda: elapsed[0]):
            result = fleet.fetch_node_telemetry(NODE, capabilities=caps, timeout=5, with_inspection=True)
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["inspection"]["state"], "TIMEOUT")

    def test_controller_cli_and_api_read_empty_cache_without_ssh_or_database_creation(self):
        fleet = monitoring.load("cache_only_fleet", "lib/vincula-fleet.py")
        with mock.patch.object(fleet, "load_registry", return_value={"nodes": [NODE]}), mock.patch.object(fleet, "node_is_active", return_value=True), mock.patch.object(fleet, "fleet_db_path", return_value=self.path.with_name("fleet.db")), mock.patch.object(fleet, "ssh_run", side_effect=AssertionError("SSH forbidden")):
            self.assertEqual(fleet.cached_inspection()["nodes"][0]["reason"], "EMPTY")
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        env = dict(__import__("os").environ, VCL_FLEET_HOME=self.tmp.name, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-B", str(ROOT / "lib/vincula-fleet.py"), "inspect", "--json"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["schema"], "inspect-cache/v1")
        self.assertFalse(self.path.exists())

    def test_real_managed_files_secret_rotation_drift_and_recovery(self):
        root = Path(self.tmp.name) / "node"
        options = inventory.fixture(root)
        with mock.patch.object(inventory.inspect.os, "statvfs", create=True, return_value=SimpleNamespace(f_blocks=100, f_frsize=4096, f_bavail=50)):
            def collect(at):
                doc = inventory.inspect.build_snapshot(**options, runner=inventory.runner)
                doc["observed_at"] = monitoring.health.utc(at)
                self.record(doc, at)
                return doc
            original = collect(NOW)
            self.store.accept(NODE, cache.sha(original), NOW, INSTANCE)
            cfg = inventory.config()
            cfg["experimental"]["clash_api"]["secret"] = "rotated-private"
            cfg["inbounds"][0]["tls"]["reality"]["private_key"] = "rotated-reality"
            options["config_path"].write_text(json.dumps(cfg), encoding="utf-8")
            collect(NOW + 1)
            self.assertEqual(self.view(NOW + 1)["drift"]["checks"]["config"]["state"], "MATCH")
            cfg["inbounds"][0]["listen_port"] = 444
            options["config_path"].write_text(json.dumps(cfg), encoding="utf-8")
            collect(NOW + 2)
            self.assertEqual(self.view(NOW + 2)["drift"]["checks"]["config"]["state"], "DRIFT")
            options["config_path"].write_text(json.dumps(inventory.config()), encoding="utf-8")
            collect(NOW + 3)
            self.assertEqual(self.view(NOW + 3)["drift"]["state"], "MATCH")

    def test_baseline_event_failure_rolls_back_baseline_in_same_transaction(self):
        self.record()
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TRIGGER full_events BEFORE INSERT ON events BEGIN SELECT RAISE(FAIL,'disk full'); END")
        before = self.path.read_bytes()
        with self.assertRaises(sqlite3.IntegrityError):
            self.accept()
        self.assertEqual(before, self.path.read_bytes())
        self.assertIsNone(self.view()["baseline"])

    def test_http_inspect_get_remains_local_and_accept_requires_fresh_telemetry_identity(self):
        import urllib.request
        fleet = monitoring.load("inspection_http_fleet", "lib/vincula-fleet.py")
        ui = monitoring.load("inspection_http_ui", "lib/vincula-ui/server.py")
        host = SimpleNamespace(fleet_db_path=lambda: self.path.with_name("fleet.db"))
        self.record()
        with self.assertRaisesRegex(ValueError, "IDENTITY"):
            cache.baseline(host, NODE, cache.sha(self.doc))
        monitoring.monitor.Store(self.path.with_name("observation.db")).record(NODE, monitoring.ok(NOW, node_id=NODE["node_id"], instance_id=INSTANCE), NOW)
        event = cache.baseline(host, NODE, cache.sha(self.doc))
        self.assertEqual(event["kind"], "BASELINE_ACCEPTED")
        with mock.patch.object(fleet, "load_registry", return_value={"nodes": [NODE]}), mock.patch.object(fleet, "node_is_active", return_value=True), mock.patch.object(fleet, "fleet_db_path", return_value=host.fleet_db_path()), mock.patch.object(fleet, "ssh_run", side_effect=AssertionError("SSH forbidden")), mock.patch.object(ui, "migrate_users_cache"):
            server, thread, token = ui.serve_in_thread("127.0.0.1", 0, fleet_mod=fleet)
            try:
                before = {p.name: p.read_bytes() for p in self.path.parent.glob("*.db")}
                req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/api/inspect?node=test", headers={ui.UI_TOKEN_HEADER: token})
                with urllib.request.urlopen(req, timeout=3) as response:
                    doc = json.load(response)
                self.assertEqual(doc["nodes"][0]["drift"]["state"], "MATCH")
                schemas.validate(doc, "inspect-cache")
                self.assertEqual(before, {p.name: p.read_bytes() for p in self.path.parent.glob("*.db")})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)

    def test_new_formal_contract_positive_negative_fixtures(self):
        for kind in ("inspect-cache", "baseline", "verify", "fleet-verify", "findings", "timeline", "monitor"):
            for p in (ROOT / "tests/fixtures/schemas" / kind).glob("*.json"):
                version = p.name.split("-")[0]
                if (kind in ("findings", "timeline", "verify", "fleet-verify") and version != "v2") or (kind == "monitor" and version != "v3"):
                    continue
                doc = json.loads(p.read_text(encoding="utf-8"))
                with self.subTest(path=str(p)):
                    if "invalid" in p.name:
                        with self.assertRaises(AssertionError):
                            schemas.validate(doc, kind, version)
                    else:
                        schemas.validate(doc, kind, version)


if __name__ == "__main__":
    unittest.main()
