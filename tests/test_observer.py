"""Restricted observer command and credential routing contracts."""
import base64
import importlib.util
import json
import os
import socket
import subprocess
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observer = load("observer_test", "lib/observer.py")


class ObserverTests(unittest.TestCase):
    def test_only_exact_readonly_commands_are_accepted(self):
        for args in observer.ALLOWED:
            self.assertEqual(observer.parse_command("vcl " + " ".join(args)), list(args))
        for command in ("", "sh", "vcl link", "vcl user list --json", "vcl restart", "vcl telemetry snapshot --json; id",
                        "vcl identity --json && id", "vcl $(id)", "vcl identity --json\nid", "sudo vcl identity --json",
                        "vcl identity --json --file /etc/shadow", "PATH=x vcl identity --json", "'vcl", "x" * 1025):
            with self.assertRaises(ValueError, msg=command):
                observer.parse_command(command)

    def test_public_key_cannot_override_forced_command(self):
        blob = b"\0\0\0\x0bssh-ed25519\0\0\0\x20" + b"x" * 32
        key = "ssh-ed25519 " + base64.b64encode(blob).decode()
        self.assertEqual(observer.public_key(key + " comment"), key)
        for raw in ("command=evil " + key, key + "\n" + key, "ssh-rsa AAAA", "PRIVATE KEY", "ssh-ed25519 !!!!"):
            with self.assertRaises(ValueError):
                observer.public_key(raw)

    @unittest.skipUnless(hasattr(socket, "SO_PEERCRED"), "Unix peer credential protocol runs in Linux gate")
    def test_unix_broker_rejects_mutation_before_execute(self):
        for args in (["identity", "--json"], ["restart"], ["identity", "--json", ";id"]):
            server, client = socket.socketpair()
            calls, errors = [], []
            def serve():
                try:
                    observer.broker(server, expected_uid=os.getuid(), execute=lambda x: (calls.append(x) or {"exit_code": 0, "payload": {"schema_version": 1}}))
                except ValueError:
                    errors.append("denied")
                finally:
                    server.close()
            thread = threading.Thread(target=serve)
            thread.start()
            with client:
                client.sendall(json.dumps({"args": args}).encode() + b"\n")
                if args == ["identity", "--json"]:
                    self.assertEqual(observer.read_frame(client, 1024)["exit_code"], 0)
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(calls), 1 if args == ["identity", "--json"] else 0)
            self.assertEqual(len(errors), 0 if calls else 1)

    def test_observe_username_never_changes_admin_route(self):
        fleet = load("observer_fleet_test", "lib/vincula-fleet.py")
        transport = load("observer_transport_test", "lib/ssh_transport.py")
        node = {"name": "node", "node_id": "11111111-1111-4111-8111-111111111111", "ssh_host": "node.test",
                "ssh_user": "admin", "ssh_port": 22, "observe_ssh_user": "vincula-observer",
                "observe_credential_ref": "observe", "admin_credential_ref": "admin"}
        normalized = fleet.normalize_node(node, index=0)
        self.assertEqual(normalized["observe_ssh_user"], "vincula-observer")
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, '{"schema_version":1}', ""))
        for credential, user in (("observe", "vincula-observer"), ("admin", "admin")):
            transport.ssh_remote_json_for_class(node=node, remote_cmd=["vcl", "identity", "--json"],
                                               credential_class=credential, ssh_run=run, identity_for_class=lambda n, c: c,
                                               failure_detail=lambda p: "")
            self.assertEqual(run.call_args.args[1], user)
            self.assertEqual(run.call_args.kwargs["identity_file"], credential)
        fleet.ssh_run = run
        fleet.node_identity_file_for_class = lambda n, c: c
        fleet.ssh_remote_json(node, ["vcl", "status", "--json"], credential_class="observe")
        self.assertEqual(run.call_args.args[1], "vincula-observer")

    def test_separate_observe_user_requires_explicit_credential(self):
        fleet = load("observer_access_test", "lib/vincula-fleet.py")
        with self.assertRaises(SystemExit):
            fleet.node_identity_file_for_class({"observe_ssh_user": "vincula-observer", "identity_file": "/admin-key"}, "observe")

    def test_upgrade_allowlist_includes_previous_minor_patch_only(self):
        upgrade = load("upgrade_minor_test", "lib/node_upgrade.py")
        for source in ("0.3.1", "0.3.2", "0.5.0", "0.5.1"):
            self.assertTrue(upgrade.is_upgrade_allowed(source, "0.5.1"))
        for source in ("0.5.2", "0.6.0", "unknown", "0.4.0"):
            self.assertFalse(upgrade.is_upgrade_allowed(source, "0.5.1"))


if __name__ == "__main__":
    unittest.main()
