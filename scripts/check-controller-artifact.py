#!/usr/bin/env python3
"""Exercise the distributed 0.5.x ZIP away from the checkout (stdlib only)."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

SCHEMAS = (
    "capabilities/v1", "telemetry/v1", "monitor/v1", "monitor/v2", "monitor/v3",
    "audit-health/v1", "user-traffic/v1", "findings/v1", "findings/v2",
    "timeline/v1", "timeline/v2", "inspect/v1", "inspect-cache/v1",
    "baseline/v1", "verify/v2", "fleet-verify/v2",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member_path(name):
    parts = PurePosixPath(name)
    require(not parts.is_absolute() and ".." not in parts.parts and "\\" not in name and ":" not in name, "unsafe archive member")
    return Path(*parts.parts)


def check_lock(root, name):
    members = set()
    for line in (root / name).read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = member_path(relative)
        require(relative not in members and digest(root / path) == expected, "artifact lock mismatch")
        members.add(relative)
    require(bool(members), "empty artifact lock")
    return members


def load(root, relative, name):
    spec = importlib.util.spec_from_file_location(name, root / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(root):
    return {str(p.relative_to(root)): (digest(p), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def smoke(root):
    """This entry point runs from a copied script with isolated Python paths."""
    fleet = load(root, "lib/vincula-fleet.py", "artifact_fleet")
    provision = fleet.load_provision_module()
    manifest = provision.verify_local_payload(provision.resolve_node_payload())
    version = fleet.VCL_FLEET_VERSION
    require(version == provision.NODE_PAYLOAD_VERSION == manifest["controller_version"], "artifact version mismatch")
    locked = check_lock(root, "controller.lock")
    for schema in SCHEMAS:
        relative = "schemas/" + schema + ".schema.json"
        require(relative in locked, "public schema missing from controller.lock: " + schema)
        doc = json.loads((root / relative).read_text(encoding="utf-8"))
        require(doc.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "invalid schema draft")
    inspection = fleet.load_inspection_module()
    verification = load(root, "lib/observation/verification.py", "artifact_verification")
    require(inspection.contract.contract() == json.loads((root / "schemas/inspect/v1.schema.json").read_text()), "Inspect contract mismatch")
    verify_schema = verification.contract.contract()
    # The schema generator replaces the descriptive runtime title with its
    # public namespace; all validation rules must still be identical.
    verify_schema["title"] = "verify/v2"
    require(verify_schema == json.loads((root / "schemas/verify/v2.schema.json").read_text()), "Verify contract mismatch")
    fleet.load_monitor_module()
    fleet.load_findings_module()
    fleet.load_observation_telemetry_module()
    fleet.load_node_upgrade_module()
    fleet.load_ui_server_module()

    def cli(*args):
        result = subprocess.run([sys.executable, "-I", "-B", str(root / "bin/vcl-fleet"), *args],
                                capture_output=True, text=True, timeout=15)
        require(result.returncode == 0, "packaged CLI failed: " + " ".join(args))
        return result.stdout
    require(cli("version").strip() == "vcl-fleet " + version, "packaged CLI version mismatch")
    cli("init")
    cli("node", "register", "test", "--host", "192.0.2.1", "--node-id", "11111111-1111-4111-8111-111111111111")
    # All cached queries have a real registered subject. Forbid every SSH path.
    def no_ssh(*args, **kwargs):
        raise AssertionError("cache-only query attempted SSH")
    fleet.ssh_run = fleet.observation_ssh_json = fleet.fetch_node_capabilities = no_ssh
    home = Path(os.environ["VCL_FLEET_HOME"])
    before = files(home)
    surfaces = (("health", "monitor/v1", fleet.monitor_cached_health),
                ("findings", "findings/v2", fleet.cached_findings),
                ("timeline", "timeline/v2", fleet.cached_timeline),
                ("inspect", "inspect-cache/v1", fleet.cached_inspection))
    for command, schema, surface in surfaces:
        require(surface("test")["schema"] == schema, "packaged cache surface mismatch")
        # CLI queries also run with an SSH tripwire first on PATH.
        require(json.loads(cli(command, "test", "--json"))["schema"] == schema, "packaged CLI schema mismatch")
    require(not Path(os.environ["VCL_ARTIFACT_SSH_MARKER"]).exists(), "packaged CLI attempted SSH")
    require(files(home) == before, "cached reads changed Fleet files")

    node_parent = root.parent / "node"
    node_parent.mkdir()
    with tarfile.open(root / "payload" / provision.NODE_TARBALL_NAME) as archive:
        for member in archive.getmembers():
            path = member_path(member.name)
            require(member.isfile() or member.isdir(), "non-regular Node archive member")
            target = node_parent / path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
                target.chmod(member.mode)
    node_root = node_parent / ("vincula-node-" + provision.NODE_PAYLOAD_VERSION)
    node_locked = check_lock(node_root, "release.lock")
    require({"lib/inspect_snapshot.py", "lib/verify_snapshot.py", "lib/accountd_runtime.py", "lib/observer.py"} <= node_locked, "Node observation payload incomplete")
    node_cli = sys.platform == "linux" and os.geteuid() == 0
    if node_cli:
        fixture = root.parent / "node-fixture"
        fixture.mkdir()
        (fixture / "state").mkdir()
        (fixture / "state/VERSION").write_text(version + "\n")
        (fixture / "config.json").write_text("{}\n")
        binary = fixture / "binary"
        binary.write_text('#!/bin/sh\nprintf executed > "$VCL_ARTIFACT_BINARY_MARKER"\nexit 99\n')
        binary.chmod(0o755)
        env = dict(os.environ, VCL_STATE_DIR=str(fixture / "state"), VCL_CONFIG_FILE=str(fixture / "config.json"),
                   VCL_SING_BOX_BIN=str(binary), VCL_ACCOUNTING_DB_FILE=str(fixture / "missing.db"),
                   VCL_ARTIFACT_BINARY_MARKER=str(fixture / "binary-executed"))
        before = files(fixture)
        for args, validator in ((("inspect", "--json"), inspection.contract.validate),
                                (("verify", "--extended", "--json"), verification.contract.validate)):
            result = subprocess.run(["bash", str(node_root / "bin/vincula"), *args], env=env, capture_output=True, text=True, timeout=12)
            require(result.returncode in (0, 1), "packaged Node observation CLI failed")
            require(bool(result.stdout.strip()), "packaged Node returned no JSON: " + args[0])
            doc = json.loads(result.stdout)
            require(not validator(doc), "packaged Node observation contract failed")
            require(doc["node_id"] is None and doc["instance_id"] is None, "fixture unexpectedly used installed identity")
        require(files(fixture) == before, "Node observation wrote missing fixture artifacts")
    print(json.dumps({"state": "PASS OFFLINE", "version": version, "schemas": len(SCHEMAS),
                      "cache_only_surfaces": len(surfaces), "node_cli": "PASS" if node_cli else "NOT RUN"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--unpacked", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.unpacked:
        smoke(args.archive.resolve())
        return
    archive = args.archive.resolve()
    require(digest(archive) == Path(str(archive) + ".sha256").read_text().split()[0], "ZIP sidecar mismatch")
    with tempfile.TemporaryDirectory(prefix="vcl-artifact-") as temp:
        stage = Path(temp)
        with zipfile.ZipFile(archive) as package:
            roots, names = set(), set()
            for member in package.infolist():
                path = member_path(member.filename)
                require(member.filename not in names, "duplicate ZIP member")
                names.add(member.filename)
                roots.add(path.parts[0])
                require((member.external_attr >> 16) & 0o170000 != 0o120000, "symlink ZIP member")
            require(len(roots) == 1, "ambiguous Controller ZIP root")
            package.extractall(stage)
        root = stage / roots.pop()
        runner = stage / "artifact-check.py"
        shutil.copyfile(__file__, runner)
        for name in ("cwd", "home", "fleet", "tripwire"):
            (stage / name).mkdir()
        marker = stage / "ssh-attempted"
        tripwire = stage / "tripwire/ssh"
        tripwire.write_text('#!/bin/sh\nprintf attempted > "$VCL_ARTIFACT_SSH_MARKER"\nexit 99\n')
        tripwire.chmod(0o755)
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME") and not k.startswith("VCL_")}
        env.update(HOME=str(stage / "home"), USERPROFILE=str(stage / "home"), XDG_CONFIG_HOME=str(stage / "home"),
                   VCL_FLEET_HOME=str(stage / "fleet"), VCL_ARTIFACT_SSH_MARKER=str(marker), PYTHONDONTWRITEBYTECODE="1",
                   PATH=str(stage / "tripwire") + os.pathsep + os.environ.get("PATH", ""))
        subprocess.run([sys.executable, "-I", "-B", str(runner), "--unpacked", str(root)], cwd=stage / "cwd", env=env, check=True, timeout=90)


if __name__ == "__main__":
    main()
