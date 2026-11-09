"""Minimal unprivileged-accounting input contract; no host configuration writes."""
import copy
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("accountd_runtime", ROOT / "lib/accountd_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
NODE_ID = "11111111-1111-4111-8111-111111111111"
INSTANCE_ID = "22222222-2222-4222-8222-222222222222"
USER_ID = "33333333-3333-4333-8333-333333333333"


def projection():
    return runtime.project(
        {"node": {"node_id": NODE_ID, "instance_id": INSTANCE_ID}, "reality_private_key": "FORBIDDEN_PRIVATE_KEY"},
        {"users": [{"tag": "alice", "user_id": USER_ID, "credentials": [{"uuid": "FORBIDDEN_USER_CREDENTIAL"}]}]},
        {"node_id": NODE_ID, "clash_api_secret": "restricted-clash-token", "uri": "FORBIDDEN_URI"},
    )


class RuntimeTests(unittest.TestCase):
    def test_projection_drops_proxy_and_user_secrets(self):
        doc = projection()
        self.assertNotIn("FORBIDDEN", json.dumps(doc))
        self.assertEqual(doc["users"], [{"tag": "alice", "user_id": USER_ID}])
        self.assertEqual(doc["node"]["instance_id"], INSTANCE_ID)

    def test_invalid_contracts_fail_closed(self):
        for patch in ({"schema": "accountd-runtime/v2"}, {"extra": "secret"}, {"clash_api_secret": ""},
                      {"raw_retention_days": -1}, {"clash_api_port": True}, {"users": []}):
            with self.assertRaises(ValueError):
                runtime.validate({**projection(), **patch})
        doc = projection()
        doc["users"][0]["uuid"] = "do-not-accept"
        with self.assertRaises(ValueError):
            runtime.validate(doc)
        doc = projection()
        doc["users"].append(copy.deepcopy(doc["users"][0]))
        with self.assertRaises(ValueError):
            runtime.validate(doc)

    def test_atomic_publication_and_no_partial_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "runtime.json"
            uid = os.getuid() if hasattr(os, "getuid") else 0
            gid = os.getgid() if hasattr(os, "getgid") else 0
            runtime.write(path, projection(), uid=uid, gid=gid)
            before = path.read_bytes()
            self.assertEqual(runtime.read(path, check_permissions=False), projection())
            with mock.patch.object(runtime.os, "replace", side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    runtime.write(path, {**projection(), "raw_retention_days": 30}, uid=uid, gid=gid)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in Path(root).iterdir()], ["runtime.json"])
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_oversize_bad_json_and_permissions(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "runtime.json"
            for data in (b'{"secret":"sensitive-content"', b"x" * (runtime.MAX_BYTES + 1)):
                path.write_bytes(data)
                with self.assertRaises(ValueError) as exc:
                    runtime.read(path, check_permissions=False)
                self.assertNotIn("sensitive-content", str(exc.exception))
            path.write_text(json.dumps(projection()))
            if os.name != "nt":
                path.chmod(0o666)
                with self.assertRaises(ValueError):
                    runtime.read(path)

    def test_restricted_reload_preserves_last_mapping_on_bad_identity(self):
        spec = importlib.util.spec_from_file_location("accountd_runtime_test_daemon", ROOT / "lib/vincula-accountd.py")
        accountd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(accountd)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "runtime.json"
            path.write_text(json.dumps(projection()))
            accountd.NODE_ID, accountd.INSTANCE_ID = NODE_ID, INSTANCE_ID
            daemon = accountd.AccountDaemon(db_path=str(Path(root) / "accounting.db"), users_path=str(path))
            daemon.runtime_loader = lambda: runtime.read(path, check_permissions=False)
            daemon._reload_tag_map_if_changed()
            self.assertEqual(accountd.TAG_TO_USER_ID, {"alice": USER_ID})
            daemon._users_mtime = None
            bad = projection()
            bad["node"]["instance_id"] = "44444444-4444-4444-8444-444444444444"
            path.write_text(json.dumps(bad))
            with mock.patch.object(accountd, "load_tag_to_user_id", side_effect=AssertionError("no canonical fallback")):
                daemon._reload_tag_map_if_changed()
            self.assertEqual(accountd.TAG_TO_USER_ID, {"alice": USER_ID})


if __name__ == "__main__":
    unittest.main()
