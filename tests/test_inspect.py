"""Node inventory, failure coverage, canonical fingerprints and read-only CLI."""
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("inspect_tests", ROOT / "lib/inspect_snapshot.py")
inspect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect)
NODE_ID = "11111111-1111-4111-8111-111111111111"
INSTANCE_ID = "22222222-2222-4222-8222-222222222222"


def config():
    return {"log": {"level": "info", "timestamp": True}, "inbounds": [{"type": "vless", "tag": "vless-reality-in",
        "listen": "0.0.0.0", "listen_port": 443, "users": [{"name": "alice", "uuid": NODE_ID, "flow": "xtls-rprx-vision"}],
        "tls": {"enabled": True, "server_name": "example.org", "reality": {"enabled": True,
            "handshake": {"server": "example.org", "server_port": 443}, "private_key": "private-reality", "short_id": "01234567"}}}],
        "outbounds": [{"type": "direct", "tag": "direct"}, {"type": "direct", "tag": "acct/alice"}],
        "route": {"rules": [{"inbound": ["vless-reality-in"], "action": "sniff"},
            {"auth_user": ["alice"], "action": "route", "outbound": "acct/alice"}], "final": "direct"},
        "experimental": {"clash_api": {"external_controller": "127.0.0.1:9090", "secret": "private-clash"}}}


def fixture(root):
    def write(path, text):
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    write("etc/os-release", 'ID=ubuntu\nVERSION_ID="24.04"\nNAME="DO_NOT_ECHO"\n')
    write("proc/sys/kernel/osrelease", "6.8.0-fixture\n")
    write("proc/stat", "cpu 1 2 3\ncpu0 1 2 3\ncpu1 1 2 3\n")
    write("proc/meminfo", "MemTotal: 1024 kB\nMemAvailable: 512 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
    write("proc/self/mountinfo", "1 0 8:0 / / rw - ext4 /dev/private rw\n")
    for mount in ("var", "run", "tmp"):
        (root / mount).mkdir(exist_ok=True)
    for key, (kind, _) in inspect.SYSCTLS.items():
        write("proc/sys/" + key.replace(".", "/"), "cubic" if "congestion" in key else "fq" if kind == "word" else "1")
    write("proc/sys/fs/file-max", "100000\n")
    for name, flags in (("lo", "0x9\n"), ("eth0", "0x1003\n")):
        write("sys/class/net/" + name + "/mtu", "1500\n")
        write("sys/class/net/" + name + "/flags", flags)
    write("var/lib/update-notifier/updates-available", "2 packages can be updated.\n1 of these updates is a security update.\n")
    write("etc/vincula/config.toml", f'node_id = "{NODE_ID}"\nclash_api_secret="private-clash"\n')
    write("etc/vincula/state.json", json.dumps({"instance_id": INSTANCE_ID, "uuid": NODE_ID, "private_key": "private-reality"}))
    write("etc/vincula/VERSION", "0.5.2\n")
    write("etc/sing-box/config.json", json.dumps(config()))
    write("usr/local/bin/sing-box", "NEVER_EXECUTE_PRIVATE_BINARY")
    write("usr/local/bin/vincula", "fixture helper")
    lib = root / "usr/local/lib/vincula"
    for name in inspect.ARTIFACTS.values():
        write("usr/local/lib/vincula/" + name, "fixture " + name)
    for name in inspect.UNITS.values():
        write("etc/systemd/system/" + name, "[Service]\nUser=fixture\n")
    digest = hashlib.sha256((root / "usr/local/bin/sing-box").read_bytes()).hexdigest()
    write("usr/local/lib/vincula/sing-box.lock", f"sing_box_version=1.13.18\nbinary_sha256={digest}\n")
    return dict(root=root, state_dir=root / "etc/vincula", config_path=root / "etc/sing-box/config.json",
                binary_path=root / "usr/local/bin/sing-box", lib_dir=lib)


def runner(argv, **limits):
    assert 0 < limits["timeout"] <= 1 and 0 < limits["limit"] <= inspect.MAX_BYTES
    if argv[0] == "timedatectl":
        return "OK", "NONE", "NTPSynchronized=yes\nNTP=yes\nTimezone=UTC\n"
    if argv[0] == "systemctl":
        return "OK", "NONE", "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\nNRestarts=1\nUser=sing-box\nGroup=sing-box\nLimitNOFILE=65536\nLimitNOFILESoft=65536\n"
    if argv[0] == "tc":
        return "OK", "NONE", '[{"dev":"eth0","kind":"fq","root":true}]'
    if argv[0] == "ss":
        return "OK", "NONE", "tcp LISTEN 0 128 0.0.0.0:443 0.0.0.0:*\ntcp LISTEN 0 128 127.0.0.1:9090 0.0.0.0:*\n"
    if argv[0] == "nft":
        return "OK", "NONE", '{"nftables":[{"chain":{"family":"inet","table":"filter","name":"input","hook":"input","policy":"drop"}},{"rule":{"comment":"private-clash"}}]}'
    raise AssertionError("unexpected or mutating command: " + repr(argv))


class InspectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.options = fixture(self.root)
        patch = mock.patch.object(inspect.os, "statvfs", create=True, return_value=SimpleNamespace(f_blocks=100, f_frsize=4096, f_bavail=50))
        patch.start()
        self.addCleanup(patch.stop)

    def build(self, **changes):
        return inspect.build_snapshot(**self.options, runner=runner, **changes)

    def test_full_inventory_and_nonsecret_fingerprints_do_not_write_or_execute_binary(self):
        before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.rglob("*") if path.is_file()}
        doc = self.build()
        self.assertEqual(inspect.validate(doc), [])
        # Windows has no native resource limits; the inventory remains partial there.
        self.assertEqual(doc["cpu"]["count"], 2)
        self.assertEqual(doc["memory"]["available_bytes"], 512 * 1024)
        self.assertEqual(doc["versions"]["sing_box"], "1.13.18")
        self.assertEqual(doc["versions"]["sing_box_source"], "INSTALLED_MANIFEST")
        self.assertEqual(doc["services"]["items"][0]["limit_nofile_soft"], 65536)
        self.assertEqual(doc["interfaces"]["items"][0]["up"], True)
        self.assertEqual(len(doc["fingerprints"]["items"]), 16)
        self.assertEqual(doc["firewall"]["rule_count"], 1)
        for secret in ("private-reality", "private-clash", "DO_NOT_ECHO", "NEVER_EXECUTE", "/dev/private", self.tmp.name):
            self.assertNotIn(secret, json.dumps(doc))
        self.assertEqual(before, {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.rglob("*") if path.is_file()})

    def test_supported_os_matrix_and_unsupported_do_not_infer_support(self):
        for distro, version, supported in (("debian", "12", True), ("debian", "13", True),
                ("ubuntu", "22.04", True), ("ubuntu", "24.04", True), ("ubuntu", "26.04", True),
                ("ubuntu", "20.04", False), ("arch", "2026", False)):
            (self.root / "etc/os-release").write_text(f'ID={distro}\nVERSION_ID="{version}"\n')
            doc = self.build()
            self.assertFalse(inspect.validate(doc))
            self.assertEqual(doc["os"]["supported"], supported)
            if not supported:
                self.assertEqual(doc["os"]["state"], "UNSUPPORTED")

    def test_missing_invalid_memory_source_and_budget_do_not_make_healthy_zeroes(self):
        (self.root / "proc/meminfo").write_text("MemTotal: 1 kB\nMemAvailable: 999 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
        doc = self.build()
        self.assertIsNone(doc["memory"]["available_bytes"])
        self.assertEqual(doc["memory"]["state"], "PARTIAL")
        (self.root / "proc/stat").unlink()
        doc = self.build()
        self.assertIsNone(doc["cpu"]["count"])
        self.assertEqual(doc["cpu"]["reason"], "MISSING")
        with mock.patch.object(inspect.time, "monotonic", side_effect=[0] + [100] * 300):
            doc = self.build(seconds=.01)
        self.assertFalse(inspect.validate(doc))
        self.assertEqual(doc["state"], "UNKNOWN")
        self.assertEqual(doc["clock"]["reason"], "TIMEOUT")

    def test_command_failures_permission_and_missing_tools_preserve_unknown(self):
        for state, reason in (("UNKNOWN", "TIMEOUT"), ("UNKNOWN", "COMMAND_FAILED"), ("UNSUPPORTED", "MISSING_TOOL"), ("UNREADABLE", "PERMISSION")):
            with self.subTest(state=state, reason=reason):
                doc = inspect.build_snapshot(**self.options, runner=lambda *a, **kw: (state, reason, None))
                self.assertFalse(inspect.validate(doc))
                self.assertEqual(doc["listeners"]["items"], [])
                self.assertEqual(doc["listeners"]["state"], state)
                self.assertIsNone(doc["clock"]["synchronized"])
                self.assertEqual(doc["firewall"]["state"], state)
        reader = inspect.Reader()
        with mock.patch.object(reader, "open_file", side_effect=PermissionError("private-error")):
            self.assertEqual(reader.read(self.root / "proc/stat"), ("UNREADABLE", "PERMISSION", None))

    def test_config_hash_excludes_credentials_reality_and_clash_but_detects_effective_change(self):
        original = config()
        digest = inspect.config_hash(json.dumps(original))
        changed = copy.deepcopy(original)
        changed["inbounds"][0]["users"][0]["uuid"] = INSTANCE_ID
        changed["inbounds"][0]["tls"]["reality"].update(private_key="rotated-secret", short_id=["new-secret"])
        changed["experimental"]["clash_api"]["secret"] = "new-auth"
        self.assertEqual(digest, inspect.config_hash(json.dumps(changed, indent=4)))
        projected = inspect.config_projection(changed)
        for secret in (INSTANCE_ID, "rotated-secret", "new-secret", "new-auth"):
            self.assertNotIn(secret, json.dumps(projected))
        for mutate in (lambda value: value["inbounds"][0].update(listen_port=8443),
                       lambda value: value["experimental"]["clash_api"].update(external_controller="0.0.0.0:9090"),
                       lambda value: value["route"].update(final="acct/alice"),
                       lambda value: value["route"]["rules"].reverse()):
            value = copy.deepcopy(original)
            mutate(value)
            self.assertNotEqual(digest, inspect.config_hash(json.dumps(value)))
        self.assertIsNone(inspect.config_hash('{"log":{},"log":{}}'))
        changed["inbounds"][0]["tls"]["reality"]["extra_secret"] = "private"
        self.assertIsNone(inspect.config_hash(json.dumps(changed)))
        large = copy.deepcopy(original)
        large["inbounds"][0]["users"] = [{"name": "user" + str(n), "uuid": NODE_ID,
            "flow": "xtls-rprx-vision"} for n in range(10000)]
        text = json.dumps(large, indent=4)
        self.assertGreater(len(text), inspect.MAX_FILE)
        self.options["config_path"].write_text(text, encoding="utf-8")
        row = next(row for row in self.build()["fingerprints"]["items"] if row["name"] == "config_nonsecret")
        self.assertEqual(row["sha256"], inspect.config_hash(text))
        self.assertEqual(row["state"], "OK")
        self.options["config_path"].write_text(" " * (inspect.MAX_CONFIG + 1), encoding="utf-8")
        row = next(row for row in self.build()["fingerprints"]["items"] if row["name"] == "config_nonsecret")
        self.assertEqual((row["state"], row["reason"], row["sha256"]), ("UNKNOWN", "LIMIT", None))

    def test_changed_binary_is_hashed_without_execute_or_trusted_version(self):
        before = self.build()
        self.options["binary_path"].write_bytes(b"DRIFTED_BINARY")
        after = self.build()
        self.assertNotEqual(next(row for row in before["fingerprints"]["items"] if row["name"] == "binary")["sha256"],
                            next(row for row in after["fingerprints"]["items"] if row["name"] == "binary")["sha256"])
        self.assertIsNone(after["versions"]["sing_box"])
        self.assertEqual(after["versions"]["sing_box_source"], "UNKNOWN")
        self.assertFalse(inspect.validate(after))

    def test_ipv4_ipv6_scope_bad_lines_and_bounded_truncation(self):
        text = "udp UNCONN 0 0 [::1]:53 [::]:*\ntcp LISTEN 0 1 [fe80::1%eth0]:443 [::]:*\ntcp LISTEN 0 1 *:8443 *:*\nBAD PRIVATE\n"
        doc = self.build()
        doc["listeners"] = inspect.parse_listeners(text)
        doc["state"] = "PARTIAL"
        self.assertFalse(inspect.validate(doc))
        self.assertEqual(doc["listeners"]["state"], "PARTIAL")
        self.assertEqual({row["scope"] for row in doc["listeners"]["items"]}, {"LOOPBACK", "LINK_LOCAL", "NON_LOOPBACK"})
        doc["listeners"] = inspect.parse_listeners("\n".join(f"tcp LISTEN 0 1 0.0.0.0:{n+1} *:*" for n in range(65)))
        self.assertEqual(len(doc["listeners"]["items"]), 64)
        self.assertTrue(doc["listeners"]["truncated"])
        doc["listeners"]["items"][0]["scope"] = "LOOPBACK"
        self.assertTrue(inspect.validate(doc))
        def bounded_names():
            for n in range(65):
                yield self.root / "sys/class/net" / ("veth" + str(n))
            self.fail("interface enumeration exceeded its admission budget")
        with mock.patch.object(Path, "iterdir", side_effect=bounded_names):
            value = self.build()
        self.assertFalse(inspect.validate(value))
        self.assertTrue(value["interfaces"]["truncated"])
        self.assertEqual(value["interfaces"]["reason"], "LIMIT")

    def test_firewall_legacy_partial_family_and_invalid_text_are_explicit(self):
        def commands(argv, **kwargs):
            if argv[0] in ("nft", "ip6tables-save"):
                return "UNSUPPORTED", "MISSING_TOOL", None
            return "OK", "NONE", "*filter\n:INPUT DROP [0:0]\n-A INPUT -p tcp --dport 443 -j ACCEPT\nCOMMIT\n"
        doc = inspect.firewall(inspect.Reader(runner=commands))
        self.assertEqual(doc["backend"], "IPTABLES")
        self.assertEqual(doc["state"], "PARTIAL")
        self.assertTrue(doc["ipv4_available"])
        self.assertIsNone(doc["ipv6_available"])
        self.assertEqual(doc["rule_count"], 1)
        bad = inspect.firewall(inspect.Reader(runner=lambda argv, **kw: ("UNSUPPORTED", "MISSING_TOOL", None) if argv[0] == "nft" else ("OK", "NONE", "private-error")))
        self.assertEqual(bad["state"], "UNKNOWN")
        self.assertIsNone(bad["rule_count"])

    def test_contract_fixture_and_schema_are_consistent_and_reject_secrets(self):
        import test_monitor_schema as evaluator
        schema = json.loads((ROOT / "schemas/inspect/v1.schema.json").read_text())
        self.assertEqual(schema, inspect.contract())
        previous = evaluator.SCHEMA
        evaluator.SCHEMA = schema
        try:
            evaluator.validate(self.build(), schema)
            for path in (ROOT / "tests/fixtures/schemas/inspect").glob("*.json"):
                value = json.loads(path.read_text())
                if "invalid" in path.name:
                    self.assertTrue(inspect.validate(value), path.name)
                    with self.assertRaises(AssertionError):
                        evaluator.validate(value, schema)
                else:
                    self.assertFalse(inspect.validate(value), path.name)
                    evaluator.validate(value, schema)
            full = json.loads((ROOT / "tests/fixtures/schemas/inspect/v1-valid.json").read_text())
            for mutate in (lambda value: value["clock"].update(state="UNKNOWN", reason="TIMEOUT"),
                           lambda value: value["fingerprints"]["items"][0].update(sha256=None),
                           lambda value: value.update(node_id=None)):
                value = copy.deepcopy(full)
                mutate(value)
                self.assertTrue(inspect.validate(value))
                with self.assertRaises(AssertionError):
                    evaluator.validate(value, schema)
        finally:
            evaluator.SCHEMA = previous
        value = self.build()
        value["fingerprints"]["items"][0]["private_key"] = "private"
        self.assertTrue(inspect.validate(value))

    def test_observe_fetch_capability_identity_errors_and_timeout_never_fall_back(self):
        spec = importlib.util.spec_from_file_location("inspection_transport_test", ROOT / "lib/observation/inspection.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        doc = self.build()
        node = {"node_id": NODE_ID}
        caps = {"state": "OK", "capabilities": ["inspect/v1"]}
        calls = []
        def ssh(**kwargs):
            calls.append(kwargs)
            if kwargs["remote_cmd"] == module.REMOTE_CMD:
                return "OK", doc, "private-error"
            return "OK", {"node_id": NODE_ID, "instance_id": INSTANCE_ID}, ""
        self.assertEqual(module.fetch(node, capabilities=caps, ssh_json=ssh)["state"], "OK")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call["credential_class"] == "observe" for call in calls))
        self.assertEqual(calls[0]["max_stdout_bytes"], 65536)
        self.assertEqual(calls[1]["max_stdout_bytes"], 4096)
        calls.clear()
        for state in ("UNSUPPORTED", "AUTH_FAILED", "TIMEOUT", "ERROR"):
            self.assertEqual(module.fetch(node, capabilities={"state": state}, ssh_json=ssh), {"state": state})
        self.assertEqual(module.fetch(node, capabilities={"state": "OK", "capabilities": ["telemetry/v1"]}, ssh_json=ssh), {"state": "UNSUPPORTED"})
        self.assertEqual(calls, [])
        self.assertEqual(module.fetch(node, capabilities=caps, ssh_json=lambda **kw: ("AUTH_FAILED", None, "private-error")), {"state": "AUTH_FAILED"})
        self.assertEqual(module.fetch(node, capabilities=caps, ssh_json=mock.Mock(side_effect=subprocess.TimeoutExpired("private-argv", 1))), {"state": "TIMEOUT"})
        changed = copy.deepcopy(doc)
        changed["instance_id"] = "33333333-3333-4333-8333-333333333333"
        self.assertEqual(module.clean({"state": "OK", "snapshot": changed}, NODE_ID, INSTANCE_ID), {"state": "ERROR"})
        changed = copy.deepcopy(doc)
        changed["os"]["secret"] = "private-clash"
        self.assertEqual(module.clean({"state": "OK", "snapshot": changed}, NODE_ID, INSTANCE_ID), {"state": "ERROR"})

    @unittest.skipUnless(os.name == "posix", "Process pipe bounds and FIFO safety run on Linux")
    def test_process_output_flood_timeout_missing_tool_and_fifo_are_bounded(self):
        start = time.monotonic()
        state, reason, value = inspect.Reader().command([sys.executable, "-c", "import sys;sys.stdout.write('x'*1000000)"], limit=4096)
        self.assertEqual((state, reason, value), ("UNKNOWN", "LIMIT", None))
        self.assertLess(time.monotonic() - start, 2)
        with mock.patch.object(inspect.os, "killpg", wraps=os.killpg) as kill_group:
            value = inspect.Reader().command([sys.executable, "-c",
                "import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])"])
        self.assertEqual(value[1], "TIMEOUT")
        kill_group.assert_called_once()
        self.assertEqual(inspect.Reader().command(["vcl-nonexistent-inspect-tool"])[0], "UNSUPPORTED")
        start = time.monotonic()
        self.assertEqual(inspect.Reader().command([sys.executable, "-c", "import time;time.sleep(10)"])[1], "TIMEOUT")
        self.assertLess(time.monotonic() - start, 2)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        self.assertEqual(inspect.Reader().read(fifo)[1], "INVALID")
        self.assertEqual(inspect.Reader().hash_file(fifo)["reason"], "INVALID")
        link = self.root / "link"
        link.symlink_to(self.root / "etc/vincula/state.json")
        self.assertEqual(inspect.Reader().read(link, no_symlink=True)[1], "SYMLINK")

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0, "Installed Node CLI requires Linux root")
    def test_real_node_cli_and_observer_exact_arguments_are_readonly(self):
        import test_observer
        binary = self.options["binary_path"]
        binary.write_text("#!/bin/sh\nexit 86\n")
        binary.chmod(0o755)
        env = {**os.environ, "VCL_STATE_DIR": str(self.options["state_dir"]), "VCL_CONFIG_FILE": str(self.options["config_path"]), "VCL_SING_BOX_BIN": str(binary)}
        before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.rglob("*") if path.is_file()}
        command = ["bash", str(ROOT / "bin/vincula"), "inspect", "--json"]
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(inspect.validate(json.loads(result.stdout)))
        self.assertEqual(before, {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.rglob("*") if path.is_file()})
        self.assertEqual(test_observer.observer.parse_command("vcl inspect --json"), ["inspect", "--json"])
        for extra in (("--file", "/etc/shadow"), ("--refresh",), (";id",)):
            result = subprocess.run(command + list(extra), env=env, text=True, capture_output=True, timeout=12)
            self.assertNotEqual(result.returncode, 0)
            with self.assertRaises(ValueError):
                test_observer.observer.parse_command("vcl inspect --json " + " ".join(extra))


if __name__ == "__main__":
    unittest.main()
