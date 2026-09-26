"""Linux root-only permission tests, confined to one TemporaryDirectory.

No system users, units or /etc files are created. Child processes drop to a
numeric UID/GID to verify the actual filesystem boundary. Run separately from
the ordinary non-root suite; this is local integration, not a VPS Live result.
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime_privileges", ROOT / "lib/accountd_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
NODE = "11111111-1111-4111-8111-111111111111"
INSTANCE = "22222222-2222-4222-8222-222222222222"
USER = "33333333-3333-4333-8333-333333333333"


class PrivilegeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vcl-accountd-permissions-")
        self.root = Path(self.temp.name)
        self.root.chmod(0o755)
        self.state = self.root / "canonical"
        self.state.mkdir(mode=0o700)
        self.data = self.root / "accounting"
        self.target = self.root / "restricted" / "runtime.json"
        (self.state / "state.json").write_text(json.dumps({"node": {"node_id": NODE, "instance_id": INSTANCE}, "reality_private_key": "DO_NOT_READ_REALITY"}))
        (self.state / "users.json").write_text(json.dumps({"users": [{"tag": "alice", "user_id": USER, "uuid": "DO_NOT_READ_USER_UUID"}]}))
        (self.state / "config.toml").write_text(f'node_id = "{NODE}"\nclash_api_secret = "PRIVATE_CLASH_TOKEN"\nclash_api_port = 9090\n')
        for path in self.state.iterdir():
            path.chmod(0o600)
        self.account = types.SimpleNamespace(pw_uid=998, pw_gid=998, pw_shell="/usr/sbin/nologin")

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        import pwd
        with mock.patch.object(pwd, "getpwnam", return_value=self.account):
            runtime.prepare(self.state, self.data, self.target)

    def test_unprivileged_daemon_can_read_minimum_and_write_db_only(self):
        self.data.mkdir(mode=0o700)
        with sqlite3.connect(self.data / "accounting.db") as conn:
            conn.execute("CREATE TABLE preserved(value TEXT)")
            conn.execute("INSERT INTO preserved VALUES('history')")
        self.prepare()
        payload = self.target.read_text()
        self.assertNotIn("DO_NOT_READ", payload)
        self.assertEqual(self.target.stat().st_uid, 0)
        self.assertEqual(self.target.stat().st_gid, 998)
        self.assertEqual(self.data.stat().st_uid, 998)
        script = '''
import importlib.util, json, pathlib, sqlite3, sys
root, library = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location("accountd", library / "vincula-accountd.py")
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
daemon=module.build_daemon_from_runtime(str(root / "restricted/runtime.json"))
assert daemon.clash_secret == "PRIVATE_CLASH_TOKEN"
assert module.TAG_TO_USER_ID == {"alice": "33333333-3333-4333-8333-333333333333"}
for path in (root / "canonical/state.json", root / "canonical/users.json", root / "canonical/config.toml"):
    try: path.read_text()
    except PermissionError: pass
    else: raise AssertionError("canonical secret readable")
try: (root / "restricted/runtime.json").write_text("tamper")
except PermissionError: pass
else: raise AssertionError("runtime writable")
with sqlite3.connect(root / "accounting/accounting.db") as conn:
    assert conn.execute("SELECT value FROM preserved").fetchone()[0] == "history"
    conn.execute("INSERT INTO preserved VALUES('new')")
print("BOUNDARY PASS")
'''
        def drop():
            os.setgroups([])
            os.setgid(998)
            os.setuid(998)
        result = subprocess.run([sys.executable, "-c", script, str(self.root), str(ROOT / "lib")],
                                preexec_fn=drop, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "BOUNDARY PASS")

    def test_data_symlink_is_rejected_without_chowning_target(self):
        self.data.mkdir()
        victim = self.root / "protected"
        victim.write_text("unchanged")
        victim.chmod(0o600)
        (self.data / "accounting.db").symlink_to(victim)
        with self.assertRaises((ValueError, OSError)):
            self.prepare()
        self.assertEqual(victim.stat().st_uid, 0)
        self.assertEqual(victim.read_text(), "unchanged")

    def test_data_hardlink_is_rejected(self):
        self.data.mkdir()
        victim = self.root / "protected"
        victim.write_text("unchanged")
        os.link(victim, self.data / "accounting.db")
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(victim.stat().st_uid, 0)

    def test_restore_regenerates_projection_and_database_owner(self):
        self.prepare()
        db = self.data / "accounting.db"
        db.write_bytes(b"restored accounting fixture")
        os.chown(db, 0, 0)
        state = json.loads((self.state / "state.json").read_text())
        state["node"]["instance_id"] = "44444444-4444-4444-8444-444444444444"
        (self.state / "state.json").write_text(json.dumps(state))
        self.prepare()
        self.assertEqual(db.stat().st_uid, 998)
        self.assertEqual(runtime.read(self.target)["node"]["instance_id"], state["node"]["instance_id"])
        self.assertEqual(db.read_bytes(), b"restored accounting fixture")

    def test_observer_unix_socket_group_boundary(self):
        import socket
        observer_spec = importlib.util.spec_from_file_location("observer_permissions", ROOT / "lib/observer.py")
        observer = importlib.util.module_from_spec(observer_spec)
        observer_spec.loader.exec_module(observer)
        socket_path = self.root / "observer.sock"
        script = '''
import json, socket, sys
try:
    with socket.socket(socket.AF_UNIX) as client:
        client.connect(sys.argv[1])
        client.sendall(b'{"args":["identity","--json"]}\\n')
        reply=json.loads(client.recv(4096))
        assert reply["exit_code"] == 0
        print("ALLOWED")
except PermissionError:
    print("DENIED")
'''
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(socket_path))
            os.chown(socket_path, 0, 998)
            socket_path.chmod(0o660)
            listener.listen(2)
            listener.settimeout(5)
            for uid, expected in ((999, "DENIED"), (998, "ALLOWED")):
                def drop():
                    os.setgroups([])
                    os.setgid(uid)
                    os.setuid(uid)
                child = subprocess.Popen([sys.executable, "-c", script, str(socket_path)], preexec_fn=drop,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    if uid == 998:
                        channel, _ = listener.accept()
                        with channel:
                            observer.broker(channel, expected_uid=998,
                                            execute=lambda args: {"exit_code": 0, "payload": {"schema_version": 1}})
                    out, err = child.communicate(timeout=5)
                    self.assertEqual(child.returncode, 0, err)
                    self.assertEqual(out.strip(), expected)
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait()


if __name__ == "__main__":
    if os.name != "posix" or os.geteuid() != 0:
        raise SystemExit("requires a Linux root test process; no host users/services are modified")
    unittest.main()
