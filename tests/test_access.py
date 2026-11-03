"""Unit tests for the machine-local SSH credential seam (0.5.4)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
ACCESS = ROOT / "lib" / "access.py"
FAKE_ADD = ROOT / "tests" / "fixtures" / "fake-ssh-add.py"
FAKE_SSH = ROOT / "tests" / "fixtures" / "fake-ssh"


class HostStub:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.fid = "11111111-1111-4111-8111-111111111111"
        self.registry: dict[str, object] = {"schema_version": 2, "nodes": []}
        self.messages: list[str] = []

    def workspace_trust_active(self) -> bool:
        return True

    def load_workspace_manifest(self) -> dict[str, str]:
        return {"fleet_id": self.fid}

    def migrate_legacy_bindings_if_needed(self, _fid: str) -> Path:
        return self.bindings_path

    @property
    def config_dir(self) -> Path:
        return self.root / "config" / "vincula" / "controllers" / self.fid

    @property
    def bindings_path(self) -> Path:
        return self.config_dir / "credential-bindings.json"

    def load_registry(self) -> dict[str, object]:
        return self.registry

    def die(self, message: str, code: int = 1) -> None:
        self.messages.append(str(message))
        raise SystemExit(code)

    def _optional_text(self, value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _has_ascii_control(self, value: str) -> bool:
        return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)

    def known_hosts_path(self) -> Path:
        return self.root / "known_hosts"

    def default_known_hosts_path(self) -> Path:
        return self.known_hosts_path()


class AccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key = self.root / "id_ed25519"
        self.key.write_text("test-only-not-a-real-key\n", encoding="utf-8")
        self.host = HostStub(self.root)
        env = {
            "VCL_FLEET_SSH": str(FAKE_SSH),
            "VCL_FLEET_SSH_ADD": str(FAKE_ADD),
            "VCL_FLEET_HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "xdg"),
            "VCL_FLEET_LOCAL_STATE": str(self.root / "state"),
        }
        self.env_patch = mock.patch.dict(os.environ, env, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        spec = importlib.util.spec_from_file_location(
            f"vcl_access_test_{id(self)}", ACCESS
        )
        assert spec is not None and spec.loader is not None
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.mod.bind(self.host)

    def _agent_count(self, count: int) -> None:
        os.environ["VCL_FAKE_AGENT_COUNT"] = str(count)
        os.environ.pop("VCL_FAKE_AGENT_KEYS", None)

    def test_agent_list_and_fingerprint(self) -> None:
        self._agent_count(12)
        snapshot = self.mod.read_agent_keys()
        self.assertEqual(snapshot["state"], "OK")
        self.assertEqual(len(snapshot["keys"]), 12)
        first = snapshot["keys"][0]
        self.assertTrue(first["fingerprint"].startswith("SHA256:"))
        self.assertEqual(
            first["fingerprint"],
            self.mod.fingerprint_public_key_line(first["public_key"]),
        )
        self.assertEqual(
            first["fingerprint"],
            self.mod.normalize_fingerprint(first["fingerprint"]),
        )
        with self.assertRaises(ValueError):
            self.mod.normalize_fingerprint("SHA256:not-base64!")

    def test_bind_agent_and_identity_file_schema_v2(self) -> None:
        self._agent_count(3)
        fingerprint = self.mod.read_agent_keys()["keys"][0]["fingerprint"]
        binding = self.mod.bind_agent("agent-test", fingerprint)
        self.assertEqual(binding["type"], "agent")
        self.assertEqual(binding["fingerprint"], fingerprint)
        self.assertRegex(binding["public_key_file"], r"^keys/[0-9a-f]{64}\.pub$")
        selector = self.host.bindings_path.parent / binding["public_key_file"]
        self.assertTrue(selector.is_file())
        self.assertNotIn("PRIVATE KEY", selector.read_text(encoding="utf-8"))
        self.mod.bind_identity_file("file-test", str(self.key))
        self.assertEqual(
            self.mod.binding_public_key_path(binding),
            selector.resolve(),
        )
        doc = json.loads(self.host.bindings_path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], 2)
        self.assertEqual(doc["bindings"]["agent-test"]["type"], "agent")
        self.assertEqual(doc["bindings"]["file-test"]["type"], "identity_file")

    def test_v1_bindings_normalize_and_persist_v2(self) -> None:
        self.host.bindings_path.parent.mkdir(parents=True, exist_ok=True)
        self.host.bindings_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "bindings": {
                        "old-file": {"type": "identity_file", "path": str(self.key)},
                        "old-default": {"type": "openssh-default"},
                    },
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.mod.bindings_file_schema_version(), 1)
        data = self.mod.load_bindings()
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(data["bindings"]["old-file"]["type"], "identity_file")
        self.assertEqual(
            data["bindings"]["old-default"]["type"], "migration_required"
        )
        self.mod.save_bindings(data)
        self.assertEqual(self.mod.bindings_file_schema_version(), 2)
        persisted = json.loads(self.host.bindings_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["schema_version"], 2)

    def test_resolve_identity_states_and_legacy(self) -> None:
        self._agent_count(2)
        fingerprint = self.mod.read_agent_keys()["keys"][0]["fingerprint"]
        self.mod.bind_agent("agent-test", fingerprint)
        self.mod.bind_identity_file("file-test", str(self.key))
        agent_node = {
            "name": "agent-node",
            "admin_credential_ref": "agent-test",
            "observe_credential_ref": "agent-test",
        }
        self.assertEqual(self.mod.node_credential_state(agent_node), "OK")
        result = self.mod.resolve_identity(agent_node, "admin")
        self.assertEqual(result["state"], "OK")
        self.assertRegex(Path(result["path"]).name, r"^[0-9a-f]{64}\.pub$")
        self.assertEqual(Path(result["path"]).parent.name, "keys")

        file_node = {
            "name": "file-node",
            "admin_credential_ref": "file-test",
            "observe_credential_ref": "file-test",
        }
        self.assertEqual(
            self.mod.resolve_identity(file_node, "observe")["path"],
            str(self.key.resolve()),
        )

        legacy_node = {"name": "legacy", "identity_file": str(self.key)}
        legacy = self.mod.resolve_identity(legacy_node, "admin")
        self.assertEqual(legacy["state"], "OK")
        self.assertTrue(legacy["migration_required"])
        self.assertEqual(
            self.mod.node_credential_state(legacy_node),
            "CREDENTIAL_MIGRATION_REQUIRED",
        )

        bare = {"name": "bare"}
        bare_result = self.mod.resolve_identity(bare, "admin")
        self.assertEqual(bare_result["state"], "ERROR")
        self.assertEqual(bare_result["code"], "CREDENTIAL_UNBOUND")
        self.assertEqual(
            bare_result["credential_state"], "CREDENTIAL_MIGRATION_REQUIRED"
        )
        self.assertEqual(
            self.mod.node_credential_state(bare),
            "CREDENTIAL_MIGRATION_REQUIRED",
        )

    def test_strict_ssh_and_scp_argv(self) -> None:
        self._agent_count(1)
        fingerprint = self.mod.read_agent_keys()["keys"][0]["fingerprint"]
        self.mod.bind_agent("agent-test", fingerprint)
        node = {
            "name": "node",
            "admin_credential_ref": "agent-test",
            "observe_credential_ref": "agent-test",
        }
        identity = self.mod.node_identity_file_for_class(node, "admin")
        argv = self.mod.ssh_argv(
            "203.0.113.10",
            "root",
            22,
            ["vcl", "identity", "--json"],
            batch=True,
            identity_file=identity,
        )
        self.assertIn("-F", argv)
        self.assertIn(os.devnull, argv)
        self.assertIn("-i", argv)
        self.assertEqual(
            Path(argv[argv.index("-i") + 1]).resolve(),
            Path(identity).resolve(),
        )
        self.assertIn("IdentitiesOnly=yes", argv)
        self.assertIn("PreferredAuthentications=publickey", argv)
        self.assertNotIn("IdentitiesOnly=no", argv)
        bare_argv = self.mod.ssh_argv(
            "203.0.113.10", "root", 22, ["vcl", "identity"], batch=True
        )
        self.assertNotIn("-i", bare_argv)
        self.assertIn("IdentitiesOnly=yes", bare_argv)
        scp = self.mod.scp_argv(port=22, src="a", dest="b", identity_file=identity)
        self.assertIn("-F", scp)
        self.assertIn("IdentitiesOnly=yes", scp)
        self.assertIn("PreferredAuthentications=publickey", scp)

    def test_agent_unavailable_and_missing_key(self) -> None:
        os.environ["VCL_FAKE_AGENT_MODE"] = "unavailable"
        self.assertEqual(
            self.mod.read_agent_keys()["state"], "AGENT_UNAVAILABLE"
        )
        with self.assertRaises(SystemExit):
            self.mod.bind_agent("agent-test", "SHA256:" + "A" * 43)
        os.environ["VCL_FAKE_AGENT_MODE"] = "empty"
        snapshot = self.mod.read_agent_keys()
        self.assertEqual(snapshot["state"], "OK")
        self.assertEqual(snapshot["keys"], [])
        os.environ.pop("VCL_FAKE_AGENT_MODE", None)
        self._agent_count(1)
        fingerprint = self.mod.read_agent_keys()["keys"][0]["fingerprint"]
        with self.assertRaises(SystemExit):
            self.mod.bind_agent("agent-test", "SHA256:" + "B" * 43)
        self.assertNotEqual(fingerprint, "")

    def test_verify_report(self) -> None:
        self._agent_count(1)
        fingerprint = self.mod.read_agent_keys()["keys"][0]["fingerprint"]
        self.mod.bind_agent("agent-test", fingerprint)
        self.mod.bind_identity_file("file-test", str(self.key))
        self.host.registry = {
            "schema_version": 2,
            "nodes": [
                {
                    "name": "good",
                    "admin_credential_ref": "agent-test",
                    "observe_credential_ref": "file-test",
                },
                {"name": "bare"},
            ],
        }
        report = self.mod.verify_bindings_report()
        self.assertFalse(report["ok"])
        self.assertTrue(
            any(
                item["node"] == "bare" and item["purpose"] == "admin"
                for item in report["problems"]
            )
        )
        self.host.registry["nodes"] = [self.host.registry["nodes"][0]]
        report = self.mod.verify_bindings_report()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["on_disk_bindings_schema_version"], 2)


    def test_ref_selectors_are_isolated_and_failed_publish_keeps_old(self) -> None:
        self._agent_count(3)
        keys = self.mod.read_agent_keys()["keys"]
        refs = ["node.admin", ".node.admin", "Admin", "admin", "中文", "文中"]
        paths = []
        for index, ref in enumerate(refs):
            key = keys[index % len(keys)]
            binding = self.mod.bind_agent(ref, key["fingerprint"])
            paths.append(binding["public_key_file"])
        self.assertEqual(len(set(paths)), len(refs))
        for ref in refs:
            self.assertEqual(self.mod._resolve_ref(ref)["state"], "OK")
        before = self.mod._resolve_ref(refs[0])
        with mock.patch.object(self.mod, "save_bindings", side_effect=OSError("injected publish failure")):
            with self.assertRaises(OSError):
                self.mod.bind_agent(refs[0], keys[1]["fingerprint"])
        self.assertEqual(self.mod._resolve_ref(refs[0]), before)

    def test_concurrent_binding_updates_keep_all_refs(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: self.mod.bind_identity_file(f"parallel-{i}", str(self.key)), range(12)))
        self.assertEqual(len(self.mod.list_bindings()), 12)


if __name__ == "__main__":
    unittest.main()
