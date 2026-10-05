"""Enhanced verification, compatibility and read-only evidence boundaries."""
import copy
import hashlib
import json
import os
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

import test_inspect as support
import test_monitor as modules
import test_findings_schema as schemas

verify = modules.load("verify_tests", "lib/verify_snapshot.py")
transport = modules.load("verification_tests", "lib/observation/verification.py")


def runner(argv, **kwargs):
    state, reason, text = support.runner(argv, **kwargs)
    if argv[0] == "systemctl" and "vincula-accountd.service" in argv:
        text = text.replace("User=sing-box", "User=vincula-accountd").replace("Group=sing-box", "Group=vincula-accountd")
    return state, reason, text


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.options = support.fixture(self.root)
        self.options["binary_path"].chmod(0o755)
        state_dir = self.options["state_dir"]
        self.settings = {"node_id": support.NODE_ID, "listen": "0.0.0.0", "port": "443", "clash_api_port": "9090", "clash_api_secret": "private-clash", "reality_server_name": "example.org"}
        self.state = {"node": {"node_id": support.NODE_ID, "instance_id": support.INSTANCE_ID, "port": 443, "reality_server_name": "example.org", "reality_private_key": "private-reality", "reality_short_id": "01234567"}}
        self.users = {"users": [{"enabled": True, "tag": "alice", "credentials": [{"status": "active", "uuid": support.NODE_ID}]}]}
        (state_dir / "config.toml").write_text('\n'.join(k + ' = "' + v + '"' for k, v in self.settings.items()), encoding="utf-8")
        (state_dir / "state.json").write_text(json.dumps(self.state), encoding="utf-8")
        (state_dir / "users.json").write_text(json.dumps(self.users), encoding="utf-8")
        for path in (state_dir / "config.toml", state_dir / "state.json", state_dir / "users.json", self.options["config_path"]):
            path.chmod(0o600)
        self.db = self.root / "accounting.db"
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.executescript("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE connections(node_id TEXT,instance_id TEXT,export_seq INTEGER,upload_bytes INTEGER,download_bytes INTEGER,user_id TEXT,event_id TEXT,last_seen_at TEXT,connection_id TEXT,generation INTEGER,user_tag TEXT,started_at TEXT,closed_at TEXT,destination_host TEXT,destination_ip TEXT,destination_port INTEGER,network TEXT); CREATE TABLE poll_baseline(connection_id TEXT,generation INTEGER,last_upload_counter INTEGER,last_download_counter INTEGER,accounted_upload INTEGER,accounted_download INTEGER,last_seen_at TEXT); CREATE TABLE daily_usage(date TEXT,user_id TEXT,user_tag TEXT,destination_host TEXT,upload_bytes INTEGER,download_bytes INTEGER,connection_count INTEGER);")
            conn.executemany("INSERT INTO meta VALUES(?,?)", [("schema_version", "4"), ("heartbeat_at", modules.health.utc(time.time())), ("last_success_at", modules.health.utc(time.time()))])
        patch = mock.patch.object(verify.inspect.os, "statvfs", create=True, return_value=SimpleNamespace(f_blocks=100, f_frsize=4096, f_bavail=50))
        patch.start()
        self.addCleanup(patch.stop)

    def build(self, **kw):
        return verify.build_snapshot(**self.options, accounting_db=self.db, runner=kw.get("runner", runner))

    def test_nested_installer_identity_and_eight_checks_readonly_no_data_plane_inference(self):
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        doc = self.build()
        self.assertEqual(verify.validate(doc), [])
        self.assertEqual(doc["instance_id"], support.INSTANCE_ID)
        for key in ("identity", "configuration", "integrity", "services", "listeners", "accounting"):
            self.assertEqual(doc["checks"][key]["state"], "PASS", key)
        self.assertEqual(doc["checks"]["data_plane"], verify.check("UNKNOWN", "NO_PROBE"))
        self.assertEqual(doc["state"], "UNKNOWN")
        self.assertNotIn("private-", json.dumps(doc))
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()})
        schemas.validate(doc, "verify")

    def test_configuration_checks_canonical_credentials_and_behavior_without_exposure(self):
        original = support.config()
        for mutate in (lambda d: d["inbounds"][0]["users"][0].update(uuid=support.INSTANCE_ID),
                       lambda d: d["route"].update(final="acct/alice"),
                       lambda d: d["experimental"]["clash_api"].update(secret="wrong-secret")):
            doc = copy.deepcopy(original)
            mutate(doc)
            self.options["config_path"].write_text(json.dumps(doc), encoding="utf-8")
            result = self.build()
            self.assertEqual(result["checks"]["configuration"]["state"], "FAIL")
            self.assertNotIn("wrong-secret", json.dumps(result))
        self.options["config_path"].unlink()
        self.assertEqual(self.build()["checks"]["configuration"]["state"], "UNKNOWN")

    def test_binary_drift_does_not_execute_replacement(self):
        self.options["binary_path"].write_text("#!/bin/sh\nexit 86\n", encoding="utf-8")
        doc = self.build()
        self.assertEqual(doc["checks"]["integrity"], verify.check("FAIL", "MISMATCH", 1))

    def test_clash_custom_port_loopback_exposure_and_missing_listener(self):
        doc = support.config()
        doc["experimental"]["clash_api"]["external_controller"] = "127.0.0.1:19090"
        self.options["config_path"].write_text(json.dumps(doc), encoding="utf-8")
        def custom(argv, **kw):
            state, reason, text = runner(argv, **kw)
            return state, reason, text.replace(":9090", ":19090") if argv[0] == "ss" else text
        self.assertEqual(self.build(runner=custom)["checks"]["listeners"]["state"], "PASS")
        doc["experimental"]["clash_api"]["external_controller"] = "0.0.0.0:19090"
        self.options["config_path"].write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(self.build(runner=custom)["checks"]["listeners"]["reason"], "EXPOSED")
        self.assertEqual(self.build(runner=lambda *a, **kw: ("UNREADABLE", "PERMISSION", None))["checks"]["listeners"]["state"], "UNKNOWN")

    def test_accounting_stale_corrupt_and_locked_do_not_pass(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("ALTER TABLE connections DROP COLUMN destination_port")
        self.assertEqual(self.build()["checks"]["accounting"]["state"], "FAIL")
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("ALTER TABLE connections ADD COLUMN destination_port INTEGER")
            conn.execute("UPDATE meta SET value=? WHERE key='last_success_at'", (modules.health.utc(time.time() - 120),))
        self.assertEqual(self.build()["checks"]["accounting"]["reason"], "STALE")
        self.db.write_bytes(b"not a database")
        self.assertNotEqual(self.build()["checks"]["accounting"]["state"], "PASS")

    @unittest.skipUnless(sys.platform == "linux" and os.geteuid() == 0, "Linux root permissions fixture")
    def test_secret_permissions_and_runtime_writeability_fail(self):
        self.assertEqual(self.build()["checks"]["permissions"]["state"], "PASS")
        self.options["config_path"].chmod(0o644)
        self.assertEqual(self.build()["checks"]["permissions"]["state"], "FAIL")
        self.options["config_path"].chmod(0o600)
        self.options["config_path"].chmod(0o640)
        with mock.patch("grp.getgrnam", return_value=SimpleNamespace(gr_gid=123456)):
            self.assertEqual(self.build()["checks"]["permissions"]["state"], "FAIL")
        self.options["config_path"].chmod(0o600)
        (self.options["lib_dir"] / "vincula-common.sh").chmod(0o666)
        self.assertEqual(self.build()["checks"]["permissions"]["state"], "FAIL")

    def test_observe_fetch_downgrade_identity_time_and_secret_rejection(self):
        doc = self.build()
        calls = []
        def rpc(**kw):
            calls.append(kw)
            return ("OK", doc, "private-error") if kw["remote_cmd"] == transport.REMOTE_CMD else ("OK", {"node_id": support.NODE_ID, "instance_id": support.INSTANCE_ID}, "")
        node = {"node_id": support.NODE_ID}
        caps = {"state": "OK", "capabilities": ["verify/v2"]}
        self.assertEqual(transport.fetch(node, capabilities=caps, ssh_json=rpc)["state"], "OK")
        self.assertTrue(all(k["credential_class"] == "observe" for k in calls))
        for capabilities in ({"state": "OK", "capabilities": []}, {"state": "AUTH_FAILED"}):
            previous = len(calls)
            self.assertIn(transport.fetch(node, capabilities=capabilities, ssh_json=rpc)["state"], ("UNSUPPORTED", "AUTH_FAILED"))
            self.assertEqual(len(calls), previous)
        doc["secret"] = "must-not-echo"
        self.assertEqual(transport.fetch(node, capabilities=caps, ssh_json=rpc), {"state": "ERROR", "snapshot": None})
        doc.pop("secret")
        doc["observed_at"] = modules.health.utc(time.time() - 100)
        self.assertEqual(transport.fetch(node, capabilities=caps, ssh_json=rpc)["state"], "ERROR")

    def test_contract_does_not_accept_fake_pass_data_plane_or_additional_fields(self):
        doc = self.build()
        for fixture in (dict(doc, secret="no"), dict(doc, state="PASS")):
            self.assertTrue(verify.validate(fixture))
        doc["checks"]["data_plane"] = verify.check("PASS", "OK", 1)
        self.assertTrue(verify.validate(doc))

    def test_controller_data_plane_requires_explicit_probe_and_post_probe_identity(self):
        import io
        from contextlib import redirect_stdout
        node = {"name": "test", "node_id": support.NODE_ID, "enabled": True}
        args = SimpleNamespace(name=None, probe_profiles=str(self.root / "private-profiles.json"), probe_sing_box="pinned", timeout=15, as_json=True)
        wire = self.build()
        host = SimpleNamespace(load_registry=lambda: {"nodes": [node]}, require_node=lambda reg, name: node,
            node_is_active=lambda n: True, workspace_manifest_path=lambda: self.root / "missing-manifest", fleet_home=lambda: self.root / "workspace",
            fetch_node_capabilities=lambda *a, **kw: {"state": "OK", "capabilities": ["verify/v2"]})
        for probe_result, changed, expected in (({"success": True, "reason": "OK"}, False, "PASS"),
                ({"success": False, "reason": "TLS_FAILED"}, False, "FAIL"),
                ({"success": True, "reason": "OK"}, True, "UNKNOWN"),
                ({"success": None, "reason": "RUNTIME_UNAVAILABLE"}, False, "UNKNOWN")):
            calls = []
            def rpc(n, cmd, **kw):
                self.assertEqual(kw["credential_class"], "observe")
                calls.append(cmd)
                if cmd == transport.REMOTE_CMD:
                    return "OK", copy.deepcopy(wire), ""
                identity = {"node_id": support.NODE_ID, "instance_id": support.INSTANCE_ID}
                if len(calls) >= 3 and changed:
                    identity["instance_id"] = "33333333-3333-4333-8333-333333333333"
                return "OK", identity, ""
            host.observation_ssh_json = rpc
            probe = mock.Mock(return_value=probe_result)
            stub = SimpleNamespace(read_profiles=lambda p: {}, ProxyProbe=lambda *a, **kw: probe)
            with mock.patch.object(transport.monitor_module.store_module, "sibling", return_value=stub), redirect_stdout(io.StringIO()) as out:
                transport.run_cli(host, args)
            result = json.loads(out.getvalue())["nodes"][0]["snapshot"]
            self.assertEqual(result["checks"]["data_plane"]["state"], expected)
            self.assertFalse(verify.validate(result))
        args.probe_profiles = None
        with redirect_stdout(io.StringIO()) as out:
            transport.run_cli(host, args)
        self.assertEqual(json.loads(out.getvalue())["nodes"][0]["snapshot"]["checks"]["data_plane"]["state"], "UNKNOWN")

    @unittest.skipUnless(sys.platform == "linux", "Bash Node CLI")
    def test_packaged_style_extended_cli_argv_and_legacy_dispatch_are_separate(self):
        env = dict(os.environ, VCL_STATE_DIR=str(self.options["state_dir"]), VCL_CONFIG_FILE=str(self.options["config_path"]), VCL_SING_BOX_BIN=str(self.options["binary_path"]), VCL_ACCOUNTING_DB_FILE=str(self.db))
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        result = subprocess.run(["bash", str(support.ROOT / "bin/vincula"), "verify", "--extended", "--json"], env=env, capture_output=True, text=True, timeout=12)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertTrue(result.stdout.strip(), result.stderr)
        self.assertFalse(verify.validate(json.loads(result.stdout)))
        denied = subprocess.run(["bash", str(support.ROOT / "bin/vincula"), "verify", "--extended", "--json", "extra"], env=env, capture_output=True, text=True)
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()})
        self.options["binary_path"].unlink()
        missing = subprocess.run(["bash", str(support.ROOT / "bin/vincula"), "verify", "--extended", "--json"], env=env, capture_output=True, text=True, timeout=12)
        self.assertIn(missing.returncode, (0, 1), missing.stderr)
        self.assertEqual(json.loads(missing.stdout)["checks"]["integrity"]["state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
