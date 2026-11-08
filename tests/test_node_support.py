"""Runtime support floor must not prevent explicit migration or fake health."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


caps = load("support_caps", "lib/observation/capabilities.py")
telemetry = load("support_telemetry", "lib/observation/telemetry.py")
health = load("support_health", "lib/observation/health.py")
upgrade = load("support_upgrade", "lib/node_upgrade.py")
inspection = load("support_inspection", "lib/observation/inspection.py")
verification = load("support_verification", "lib/observation/verification.py")


class NodeSupportTests(unittest.TestCase):
    def result(self, version):
        raw = {"schema": "capabilities/v1", "node_version": version,
               "capabilities": ["telemetry/v1", "inspect/v1", "verify/v2"]}
        ssh = Mock(return_value=("OK", raw, ""))
        result = caps.fetch_capabilities({"name": "canary"}, ssh_json=ssh)
        self.assertEqual(ssh.call_count, 1)
        self.assertEqual(result["node_version"], version)
        self.assertEqual(result["raw"], raw)
        return result

    def test_current_release_supported(self):
        result = self.result("0.5.5")
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["support"]["minimum_node_version"], "0.5.5")
        self.assertTrue(caps.node_declares_capability(result, "inspect/v1"))

    def test_old_prerelease_unknown_and_future_do_not_negotiate(self):
        for version in ("0.3.1", "0.3.1-rc2", "0.5.0", "0.5.3", "0.5.4",
                        "0.5.5-rc1", "0.5.6", "0.6.0"):
            with self.subTest(version=version):
                result = self.result(version)
                self.assertEqual(result["state"], "UNSUPPORTED")
                self.assertEqual(result["reason"], "NODE_VERSION_UNSUPPORTED")
                self.assertFalse(caps.node_declares_capability(result, "inspect/v1"))
                ssh = Mock(side_effect=AssertionError("must not fetch old telemetry"))
                tel = telemetry.fetch_telemetry({}, capabilities=result, ssh_json=ssh)
                self.assertEqual(tel["state"], "UNSUPPORTED")
                self.assertEqual(tel["reason"], "NODE_VERSION_UNSUPPORTED")
                self.assertEqual(tel["support"], result["support"])
                ssh.assert_not_called()

    def test_invalid_version_is_protocol_error(self):
        for version in ("unknown", "0.5.5+local", ""):
            raw = {"schema": "capabilities/v1", "node_version": version,
                   "capabilities": ["telemetry/v1"]}
            result = caps.fetch_capabilities({}, ssh_json=Mock(return_value=("OK", raw, "")))
            self.assertEqual(result["state"], "ERROR")

    def test_old_node_inspection_and_verify_make_no_remote_calls(self):
        result = self.result("0.5.3")
        ssh = Mock(side_effect=AssertionError("old Node command must not run"))
        for module in (inspection, verification):
            self.assertEqual(module.fetch({}, capabilities=result, ssh_json=ssh)["state"], "UNSUPPORTED")
        ssh.assert_not_called()

    def test_support_failure_not_unreachable_or_proxy_success(self):
        result = self.result("0.5.0")
        record = health.build({"name": "canary", "node_id": "n"}, result, {}, 100)
        self.assertEqual(record["health"]["observation"]["state"], "UNKNOWN")
        self.assertEqual(record["health"]["proxy"]["state"], "UNKNOWN")
        self.assertNotEqual(record["health"]["node"]["state"], "UNREACHABLE")

    def test_authentication_error_keeps_its_meaning(self):
        result = caps.fetch_capabilities({}, ssh_json=Mock(return_value=("AUTH_FAILED", None, "denied")))
        self.assertEqual(result["state"], "AUTH_FAILED")
        self.assertNotIn("support", result)

    def test_ingress_plan_preserves_real_versions_and_identity(self):
        node = {"name": "canary", "node_id": "n"}
        for version, expected in (("0.5.0", "PLANNED"), ("0.3.1", "PLANNED"),
                                  ("0.3.1-rc2", "REFUSED"), ("0.5.6", "REFUSED"),
                                  ("0.5.5", "SKIPPED")):
            with self.subTest(version=version):
                ssh = Mock(return_value=("OK", {"node_id": "n", "instance_id": "i",
                                                "vincula_version": version}, ""))
                upgrade.bind(SimpleNamespace(
                    load_provision_module=lambda: SimpleNamespace(NODE_PAYLOAD_VERSION="0.5.5"),
                    observation_ssh_json=ssh))
                plan = upgrade.run_upgrade_plan(node, credential_class="admin")
                self.assertEqual(plan["state"], expected)
                self.assertEqual(plan["current_version"], version)
                self.assertEqual(plan["credential_class"], "admin")
                self.assertEqual(ssh.call_count, 1)
                self.assertEqual(ssh.call_args.args[1], ["vcl", "identity", "--json"])
                self.assertEqual(ssh.call_args.kwargs["credential_class"], "admin")


if __name__ == "__main__":
    unittest.main()
