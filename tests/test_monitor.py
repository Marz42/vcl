"""0.5.1 monitoring contracts and failure isolation (stdlib unittest)."""
import concurrent.futures
from contextlib import closing
import copy
import importlib.util
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


monitor = load("monitor_test", "lib/observation/monitor.py")
store_mod = monitor.store_module
health = store_mod.health
BASE = json.loads((ROOT / "tests/fixtures/schemas/telemetry/v1-valid.json").read_text())
NOW = health.timestamp(BASE["observed_at"])
NODE = {"name": "test", "node_id": BASE["node_id"], "enabled": True}


def ok(at=NOW, **changes):
    snap = copy.deepcopy(BASE)
    snap["observed_at"] = health.utc(at)
    snap.update(changes)
    return {"state": "OK", "snapshot": snap}


class HealthTests(unittest.TestCase):
    def test_transport_failure_and_recovery(self):
        previous = {}
        for expected in ("SUSPECT", "SUSPECT", "UNREACHABLE"):
            previous = health.build(NODE, {"state": "TIMEOUT"}, previous, NOW)
            self.assertEqual(previous["health"]["node"]["state"], expected)
        for expected in ("RECOVERING", "HEALTHY"):
            previous = health.build(NODE, ok(), previous, NOW)
            self.assertEqual(previous["health"]["node"]["state"], expected)

    def test_alive_is_not_proxy_usable(self):
        record = health.build(NODE, ok(), {}, NOW)
        self.assertEqual(record["health"]["node"]["state"], "HEALTHY")
        self.assertEqual(record["health"]["proxy"]["state"], "UNKNOWN")
        self.assertEqual(record["overall"], "UNKNOWN")
        record = health.build(NODE, ok(), {}, NOW, {"success": False, "reason": "TLS_FAILED"})
        self.assertEqual(record["health"]["proxy"]["state"], "DEGRADED")

    def test_accounting_failure_is_separate(self):
        result = ok()
        result["snapshot"]["accountd"]["active"] = False
        record = health.build(NODE, result, {}, NOW, {"success": True, "reason": "OK"})
        self.assertEqual(record["health"]["proxy"]["state"], "HEALTHY")
        self.assertEqual(record["health"]["accounting"]["state"], "DEGRADED")

    def test_unsupported_is_not_node_failure(self):
        record = health.build(NODE, {"state": "UNSUPPORTED"}, {}, NOW)
        self.assertEqual(record["health"]["node"]["state"], "HEALTHY")
        self.assertEqual(record["health"]["observation"]["state"], "UNKNOWN")

    def test_stale_clock_and_cache_never_healthy(self):
        for at in (NOW - 100, NOW + 40):
            record = health.build(NODE, ok(at), {}, NOW)
            self.assertEqual(record["health"]["observation"]["state"], "DEGRADED")
        record = health.build(NODE, ok(), {}, NOW)
        viewed = health.present(record, NOW + 100)
        self.assertEqual(viewed["overall"], "UNKNOWN")
        self.assertEqual(record["health"]["node"]["state"], "HEALTHY")

    def test_counter_reset_and_instance_change(self):
        first = health.build(NODE, ok(), {}, NOW)
        result = ok(NOW + 30)
        result["snapshot"]["network"]["rx_bytes"] += 300
        record = health.build(NODE, result, first, NOW + 30)
        self.assertEqual(record["metrics"]["rx_bytes_per_second"], 10)
        result["snapshot"]["network"]["rx_bytes"] = 1
        self.assertIsNone(health.build(NODE, result, first, NOW + 30)["metrics"]["rx_bytes_per_second"])
        result["snapshot"]["instance_id"] = "33333333-3333-4333-8333-333333333333"
        self.assertIsNone(health.build(NODE, result, first, NOW + 30)["metrics"]["tx_bytes_per_second"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "private" / "observation.db"
        self.store = monitor.Store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_read_is_readonly(self):
        doc = self.store.read([NODE], NOW)
        self.assertEqual(doc["cache_state"], "EMPTY")
        self.assertEqual(doc["nodes"][0]["overall"], "UNKNOWN")
        self.assertFalse(self.path.parent.exists())

    def test_restart_and_transactional_health(self):
        for i in range(3):
            monitor.Store(self.path).record(NODE, {"state": "TIMEOUT"}, NOW + i)
        record = self.store.read([NODE], NOW + 3)["nodes"][0]
        self.assertEqual(record["health"]["node"]["state"], "UNREACHABLE")
        self.store.record(NODE, ok(NOW + 4), NOW + 4)
        self.assertEqual(self.store.read([NODE], NOW + 4)["nodes"][0]["health"]["node"]["state"], "RECOVERING")

    def test_secret_fields_do_not_persist(self):
        result = ok()
        result["snapshot"]["filesystem"]["mount"] = "socks://secret-password"
        result["detail"] = "vless://private-credential"
        self.store.record(NODE, result, NOW, {"success": True, "reason": "OK", "token": "hidden"})
        self.assertNotIn(b"secret-password", self.path.read_bytes())
        self.assertNotIn(b"private-credential", self.path.read_bytes())
        self.assertNotIn("token", json.dumps(self.store.read([NODE], NOW)))

    def test_malformed_and_identity_mismatch_rejected(self):
        for i, result in enumerate(({"state": "OK", "snapshot": {}}, ok(node_id="44444444-4444-4444-8444-444444444444"))):
            record = self.store.record(NODE, result, NOW + i)
            self.assertEqual(record["observation_state"], "ERROR")

    def test_corrupt_row_and_db_fail_closed_readonly(self):
        self.store.record(NODE, ok(), NOW)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE health_latest SET payload=?", ('{"name":"secret"}',))
        before = self.path.read_bytes()
        self.assertEqual(self.store.read([NODE], NOW)["cache_state"], "PARTIAL")
        self.assertEqual(self.path.read_bytes(), before)
        self.path.write_bytes(b"not a sqlite database")
        self.assertEqual(self.store.read([NODE], NOW)["cache_state"], "CACHE_CORRUPT")
        self.assertEqual(self.path.read_bytes(), b"not a sqlite database")

    def test_rollup_retention_and_global_cap(self):
        self.store.record(NODE, ok(), NOW)
        self.store.record(NODE, {"state": "TIMEOUT"}, NOW + 1)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            count, payload = conn.execute("SELECT samples,payload FROM telemetry_rollup_5m").fetchone()
            self.assertEqual(count, 2)
            self.assertEqual(json.loads(payload)["connections"]["count"], 1)
            store_mod.Store.prune(conn, NOW + 86402)
            self.assertEqual(conn.execute("SELECT count(*) FROM telemetry_samples").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM telemetry_rollup_5m").fetchone()[0], 1)
            store_mod.Store.prune(conn, NOW + 91 * 86400)
            for table in store_mod.TABLES:
                self.assertEqual(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        original = store_mod.TABLES["telemetry_samples"]
        try:
            store_mod.TABLES["telemetry_samples"] = (86400, 2)
            for i in range(4):
                self.store.record(NODE, ok(NOW + 2 + i), NOW + 2 + i)
            with closing(sqlite3.connect(self.path)) as conn, conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM telemetry_samples").fetchone()[0], 2)
                self.assertIsNotNone(conn.execute("SELECT value FROM metadata WHERE key='truncated_telemetry_samples'").fetchone())
        finally:
            store_mod.TABLES["telemetry_samples"] = original

    def test_concurrent_read_write_and_older_sample(self):
        self.store.record(NODE, ok(), NOW)
        before = self.path.read_bytes()
        self.store.record(NODE, {"state": "ERROR"}, NOW - 1)
        self.assertEqual(self.path.read_bytes(), before)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(self.store.record, NODE, ok(NOW + i), NOW + i) for i in range(1, 10)]
            for future in futures:
                future.result()
        self.assertEqual(self.store.read([NODE], NOW + 10)["nodes"][0]["received_at"], health.utc(NOW + 9))

    def test_monitor_lock_is_exclusive(self):
        with monitor.MonitorLock(self.path.with_suffix(".lock")):
            with self.assertRaisesRegex(ValueError, "MONITOR_BUSY"):
                with monitor.MonitorLock(self.path.with_suffix(".lock")):
                    pass
        with monitor.MonitorLock(self.path.with_suffix(".lock")):
            pass

    def test_corrupt_optional_services_and_rollup_are_isolated(self):
        self.store.record(NODE, ok(), NOW)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            row = json.loads(conn.execute("SELECT payload FROM health_latest").fetchone()[0])
            row["services"] = ["bad-shape"]
            conn.execute("UPDATE health_latest SET payload=?", (json.dumps(row),))
            conn.execute("UPDATE telemetry_rollup_5m SET payload=?", ('{"connections":{"sum":3,"count":"secret"}}',))
        viewed = self.store.read([NODE], NOW)["nodes"][0]
        self.assertIsNone(viewed["services"]["sing_box_active"])
        self.store.record(NODE, ok(NOW + 1), NOW + 1)
        self.assertEqual(self.store.read([NODE], NOW + 1)["nodes"][0]["observation_state"], "OK")


class SchedulerTests(unittest.TestCase):
    def test_bounded_concurrency_and_one_node_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            nodes = [{"name": f"n{i}", "node_id": f"{i:08d}-1111-4111-8111-111111111111"} for i in range(12)]
            lock, active, peak, calls = threading.Lock(), 0, 0, []
            def fetch(node, *, timeout):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(active, peak)
                    calls.append(node["name"])
                try:
                    time.sleep(.04 if node["name"] == "n0" else .002)
                    if node["name"] == "n0":
                        raise subprocess.TimeoutExpired("secret-argv", timeout)
                    return ok(node_id=node["node_id"])
                finally:
                    with lock:
                        active -= 1
            store = monitor.Store(Path(tmp) / "obs.db")
            service = monitor.Monitor(nodes, store, fetch, concurrency=3, wall_clock=lambda: NOW)
            result = service.run(once=True)
            self.assertEqual(result, {"sampled_nodes": 12, "cache_write_errors": 0})
            self.assertEqual(len(set(calls)), 12)
            self.assertLessEqual(peak, 3)
            self.assertGreater(peak, 1)
            docs = store.read(nodes, NOW)["nodes"]
            self.assertEqual(docs[0]["observation_state"], "TIMEOUT")
            self.assertTrue(all(doc["observation_state"] == "OK" for doc in docs[1:]))
            self.assertNotIn(b"secret-argv", store.path.read_bytes())

    def test_jitter_backoff_and_bounds(self):
        service = monitor.Monitor([NODE], None, None)
        for _ in range(20):
            self.assertLessEqual(service.delay(NODE["node_id"], {"state": "ERROR"}), 300)
        delay = service.delay(NODE["node_id"], {"state": "OK"})
        self.assertTrue(27 <= delay <= 33)
        for config in ({"interval": float("nan")}, {"timeout": 0}, {"concurrency": 0}):
            with self.assertRaises(ValueError):
                monitor.Monitor([NODE], None, None, **config)

    def test_cache_write_failure_does_not_abort_other_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = monitor.Store(Path(tmp) / "obs.db")
            store.path.write_bytes(b"broken database")
            service = monitor.Monitor([NODE], store, lambda node, **kwargs: ok())
            self.assertEqual(service.run(once=True)["cache_write_errors"], 1)
            self.assertEqual(store.path.read_bytes(), b"broken database")


class IntegrationTests(unittest.TestCase):
    def test_cli_service_and_ui_get_share_cache_without_ssh(self):
        fleet = load("monitor_fleet", "lib/vincula-fleet.py")
        ui = load("monitor_ui", "lib/vincula-ui/server.py")
        ui.set_fleet_module(fleet)
        with tempfile.TemporaryDirectory() as tmp:
            fleet.fleet_db_path = lambda: Path(tmp) / "fleet.db"
            fleet.load_registry = lambda: {"nodes": [NODE]}
            fleet.ssh_run = mock.Mock(side_effect=AssertionError("GET must never SSH"))
            fleet.fetch_node_telemetry = lambda node, **kw: ok(time.time())
            args = type("Args", (), dict(name=None, interval=30, timeout=5, concurrency=2,
                                         once=True, as_json=False, probe_profiles=None))()
            with mock.patch("builtins.print"):
                self.assertEqual(fleet.load_monitor_module().run_cli(fleet._FLEET_HOST, args), 0)
            self.assertTrue((Path(tmp) / "observation.db").exists())
            before = (Path(tmp) / "observation.db").read_bytes()
            fake_handler = type("Handler", (), {"_send_json": mock.Mock()})()
            ui.FleetUIHandler._handle_api_get(fake_handler, "/api/monitor", {})
            code, doc = fake_handler._send_json.call_args.args
            self.assertEqual(code, 200)
            self.assertEqual(doc["nodes"][0]["observation_state"], "OK")
            fleet.ssh_run.assert_not_called()
            self.assertEqual((Path(tmp) / "observation.db").read_bytes(), before)

    def test_total_telemetry_deadline_covers_multiple_ssh_calls(self):
        fleet = load("monitor_deadline_fleet", "lib/vincula-fleet.py")
        calls = []
        clock = iter((10, 12, 16))
        def ssh(node, command, **kw):
            calls.append(kw["timeout"])
            return "OK", BASE, ""
        fleet.observation_ssh_json = ssh
        with mock.patch.object(fleet.time, "monotonic", side_effect=lambda: next(clock)):
            with self.assertRaises(subprocess.TimeoutExpired):
                fleet.fetch_node_telemetry(NODE, timeout=5, capabilities={"state": "OK", "capabilities": ["telemetry/v1"]})
        self.assertEqual(calls, [3])


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.probe = load("monitor_probe", "lib/observation/probe.py")
        self.profile = {"node_id": NODE["node_id"], "purpose": "synthetic-probe", "user_tag": "vcl-probe-health",
                        "server": "192.0.2.10", "server_port": 443, "uuid": "44444444-4444-4444-8444-444444444444",
                        "server_name": "example.org", "public_key": "A" * 43, "short_id": "abcd", "url": "https://example.org/"}

    def test_config_only_has_proxy_and_loopback_listener(self):
        config = self.probe.client_config(self.profile, 12345)
        self.assertEqual(config["route"]["final"], "probe")
        self.assertEqual([x["type"] for x in config["outbounds"]], ["vless"])
        self.assertEqual(config["inbounds"][0]["listen"], "127.0.0.1")
        for updates in ({"purpose": "user"}, {"user_tag": "alice"}, {"url": "http://example.org/"},
                        {"url": "https://user:password@example.org/"}, {"password": "secret"}):
            with self.assertRaises(ValueError):
                self.probe.validate_profile({**self.profile, **updates})

    def test_missing_runtime_is_unknown_not_success(self):
        with mock.patch.object(self.probe.shutil, "which", return_value=None):
            result = self.probe.ProxyProbe({NODE["name"]: self.profile})(NODE, timeout=1)
        self.assertIsNone(result["success"])
        self.assertEqual(result["reason"], "RUNTIME_UNAVAILABLE")

    def test_probe_never_leaks_credentials_or_bypasses_proxy(self):
        child = mock.Mock()
        child.poll.return_value = None
        curl_result = subprocess.CompletedProcess([], 0, "204 0.1 0.2 0.3")
        with mock.patch.object(self.probe.shutil, "which", side_effect=lambda x: x), \
             mock.patch.object(self.probe.subprocess, "Popen", return_value=child) as popen, \
             mock.patch.object(self.probe.socket, "create_connection"), \
             mock.patch.object(self.probe.subprocess, "run", return_value=curl_result) as run, \
             mock.patch.dict(os.environ, {"NO_PROXY": "*", "HTTPS_PROXY": "http://untrusted"}):
            result = self.probe.ProxyProbe({NODE["name"]: self.profile})(NODE, timeout=2)
        self.assertTrue(result["success"])
        self.assertEqual(result["ttfb_ms"], 200)
        self.assertNotIn(self.profile["uuid"], repr(popen.call_args))
        self.assertNotIn(self.profile["uuid"], repr(run.call_args))
        argv = run.call_args.args[0]
        self.assertEqual(argv[1], "-q")
        self.assertEqual(argv[argv.index("--noproxy") + 1], "")
        self.assertTrue(argv[argv.index("--proxy") + 1].startswith("socks5h://127.0.0.1:"))
        self.assertNotIn("NO_PROXY", run.call_args.kwargs["env"])
        child.terminate.assert_called_once()
        path = Path(popen.call_args.args[0][-1])
        self.assertFalse(path.exists())

    def test_timeout_terminates_child_and_sanitizes_result(self):
        child = mock.Mock()
        child.poll.return_value = None
        with mock.patch.object(self.probe.shutil, "which", side_effect=lambda x: x), \
             mock.patch.object(self.probe.subprocess, "Popen", return_value=child), \
             mock.patch.object(self.probe.socket, "create_connection"), \
             mock.patch.object(self.probe.subprocess, "run", side_effect=subprocess.TimeoutExpired("private-argv", 1)):
            result = self.probe.ProxyProbe({NODE["name"]: self.profile})(NODE, timeout=1)
        self.assertEqual(result, {"success": False, "reason": "TIMEOUT"})
        child.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
