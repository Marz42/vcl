#!/usr/bin/env python3
"""vincula-fleet — workstation fleet controller (registry CLI).

Stdlib only: argparse, json, pathlib, os, sys, re, tempfile (OpenSSH
subprocess comes in Phase 6). No pip, no paramiko, no cryptography
package. No root, no systemd, no /etc/vincula.

User-local fleet.json is the node registry. SSH passwords are never
stored. Targets Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

VCL_FLEET_VERSION = "0.2.8-dev"
FLEET_SCHEMA_VERSION = 1
CLOCK_SKEW_WARN_SECONDS = 30
CLOCK_SKEW_FAIL_SECONDS = 300
CLOCK_SKEW_FAIL_CHECK = "audit-clock-health"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
# Same contract as is_valid_user_tag: lowercase alnum / . _ - ; max 32.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
FORBIDDEN_NODE_KEYS = ("password", "passwd", "ssh_password")
NODE_KEYS = ("node_id", "name", "ssh_host", "ssh_user", "ssh_port", "enabled")
SSH_ADD_NOT_WIRED = "SSH add not wired; use --offline or wait for 0.2.8 Phase 6"
STATUS_NOT_WIRED = "SSH status not wired; wait for 0.2.8 Phase 7"
VERIFY_NOT_WIRED = "SSH verify not wired; wait for 0.2.8 Phase 7"


def die(message: str, code: int = 1) -> None:
    sys.stderr.write(f"vcl-fleet: {message}\n")
    raise SystemExit(code)


def fleet_home() -> Path:
    override = os.environ.get("VCL_FLEET_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "vincula"
        return Path.home() / "AppData" / "Roaming" / "vincula"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "vincula"
    return Path.home() / ".config" / "vincula"


def fleet_registry_path() -> Path:
    return fleet_home() / "fleet.json"


def ssh_bin() -> str:
    env = os.environ.get("VCL_FLEET_SSH")
    if env:
        return env
    return "ssh.exe" if sys.platform == "win32" else "ssh"


def empty_registry() -> dict[str, Any]:
    return {"schema_version": FLEET_SCHEMA_VERSION, "nodes": []}


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in FORBIDDEN_NODE_KEYS or lowered.endswith("password")


def parse_ssh_target(
    host: str,
    user: Optional[str] = None,
    port: Optional[int] = None,
) -> tuple[str, str, int]:
    """Split optional user@host; return (ssh_host, ssh_user, ssh_port)."""
    raw = (host or "").strip()
    if not raw:
        die("ssh_host must be non-empty")
    ssh_user = (user or "").strip() or "root"
    if "@" in raw:
        maybe_user, maybe_host = raw.rsplit("@", 1)
        if maybe_user and user is None:
            ssh_user = maybe_user
        raw = maybe_host.strip()
    if raw.startswith("[") and raw.endswith("]") and len(raw) > 2:
        raw = raw[1:-1]
    if not raw:
        die("ssh_host must be non-empty")
    ssh_port = 22 if port is None else port
    if not isinstance(ssh_port, int) or isinstance(ssh_port, bool) or not (1 <= ssh_port <= 65535):
        die(f"invalid ssh_port: {port}")
    return raw, ssh_user, ssh_port


def validate_node_id(node_id: str) -> None:
    if not isinstance(node_id, str) or not UUID_RE.fullmatch(node_id):
        die(f"invalid node_id: {node_id}")


def validate_name(name: str) -> None:
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        die(f"invalid name: {name}")


def normalize_node(raw: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        die(f"nodes[{index}] must be an object")
    for key in raw:
        if _is_forbidden_key(str(key)):
            die(f"nodes[{index}] must not store SSH passwords")
    node_id = raw.get("node_id")
    name = raw.get("name")
    ssh_host = raw.get("ssh_host")
    ssh_user = raw.get("ssh_user", "root")
    ssh_port = raw.get("ssh_port", 22)
    enabled = raw.get("enabled", True)
    if not isinstance(node_id, str) or not UUID_RE.fullmatch(node_id):
        die(f"invalid node_id: {node_id}")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        die(f"invalid name: {name}")
    if not isinstance(ssh_host, str) or not ssh_host.strip():
        die(f"invalid ssh_host: {ssh_host}")
    if not isinstance(ssh_user, str) or not ssh_user.strip():
        die(f"invalid ssh_user: {ssh_user}")
    if isinstance(ssh_port, bool) or not isinstance(ssh_port, int) or not (1 <= ssh_port <= 65535):
        die(f"invalid ssh_port: {ssh_port}")
    if not isinstance(enabled, bool):
        die(f"invalid enabled: {enabled}")
    return {
        "node_id": node_id,
        "name": name,
        "ssh_host": ssh_host.strip(),
        "ssh_user": ssh_user.strip(),
        "ssh_port": ssh_port,
        "enabled": enabled,
    }


def validate_registry(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        die("fleet.json must be a JSON object")
    for key in data:
        if _is_forbidden_key(str(key)):
            die("fleet.json must not store SSH passwords")
    ver = data.get("schema_version")
    if ver != FLEET_SCHEMA_VERSION:
        die(f"unsupported fleet.json schema_version: {ver}")
    nodes_raw = data.get("nodes", [])
    if not isinstance(nodes_raw, list):
        die("fleet.json nodes must be a list")
    nodes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for i, raw in enumerate(nodes_raw):
        node = normalize_node(raw, index=i)
        if node["node_id"] in seen_ids:
            die(f"duplicate node_id: {node['node_id']}")
        if node["name"] in seen_names:
            die(f"duplicate name: {node['name']}")
        seen_ids.add(node["node_id"])
        seen_names.add(node["name"])
        nodes.append(node)
    return {"schema_version": FLEET_SCHEMA_VERSION, "nodes": nodes}


def load_registry(path: Optional[Path] = None) -> dict[str, Any]:
    path = fleet_registry_path() if path is None else Path(path)
    if not path.is_file():
        return empty_registry()
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        die(f"invalid fleet.json: {exc}")
    except OSError as exc:
        die(f"cannot read {path}: {exc}")
    return validate_registry(data)


def save_registry(path: Optional[Path], registry: dict[str, Any]) -> None:
    path = fleet_registry_path() if path is None else Path(path)
    payload = validate_registry(registry)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=".fleet.json.", suffix=".tmp", dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def find_by_name(registry: dict[str, Any], name: str) -> Optional[dict[str, Any]]:
    for node in registry.get("nodes") or []:
        if node.get("name") == name:
            return node
    return None


def find_by_node_id(registry: dict[str, Any], node_id: str) -> Optional[dict[str, Any]]:
    for node in registry.get("nodes") or []:
        if node.get("node_id") == node_id:
            return node
    return None


def require_node(registry: dict[str, Any], name: str) -> dict[str, Any]:
    node = find_by_name(registry, name)
    if node is None:
        die(f"unknown node: {name}")
    return node


def add_node(
    registry: dict[str, Any],
    *,
    node_id: str,
    name: str,
    ssh_host: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    enabled: bool = True,
) -> dict[str, Any]:
    validate_node_id(node_id)
    validate_name(name)
    if find_by_node_id(registry, node_id) is not None:
        die(f"duplicate node_id: {node_id}")
    if find_by_name(registry, name) is not None:
        die(f"duplicate name: {name}")
    record = normalize_node(
        {
            "node_id": node_id,
            "name": name,
            "ssh_host": ssh_host,
            "ssh_user": ssh_user,
            "ssh_port": ssh_port,
            "enabled": enabled,
        },
        index=len(registry.get("nodes") or []),
    )
    registry.setdefault("nodes", []).append(record)
    registry["schema_version"] = FLEET_SCHEMA_VERSION
    return record


def set_host(
    registry: dict[str, Any],
    name: str,
    host: str,
    *,
    user: Optional[str] = None,
    port: Optional[int] = None,
) -> dict[str, Any]:
    node = require_node(registry, name)
    parsed_host, parsed_user, parsed_port = parse_ssh_target(
        host, user=user, port=port if port is not None else node.get("ssh_port")
    )
    node["ssh_host"] = parsed_host
    if user is not None or "@" in (host or ""):
        node["ssh_user"] = parsed_user
    if port is not None:
        node["ssh_port"] = parsed_port
    return node


def set_enabled(registry: dict[str, Any], name: str, enabled: bool) -> dict[str, Any]:
    node = require_node(registry, name)
    node["enabled"] = bool(enabled)
    return node


def cmd_init() -> int:
    path = fleet_registry_path()
    if path.is_file():
        existing = load_registry(path)
        if existing.get("nodes"):
            die(f"fleet registry already exists with nodes: {path}")
    save_registry(path, empty_registry())
    sys.stdout.write(f"Initialized fleet registry at {path}\n")
    return 0


def cmd_node_add(args: argparse.Namespace) -> int:
    if not args.offline:
        die(SSH_ADD_NOT_WIRED, 2)
    if not args.node_id:
        die("--offline requires --node-id UUID", 2)
    ssh_host, ssh_user, ssh_port = parse_ssh_target(args.host, args.user, args.port)
    registry = load_registry()
    add_node(
        registry,
        node_id=args.node_id,
        name=args.name,
        ssh_host=ssh_host,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
    )
    save_registry(None, registry)
    sys.stdout.write(f"Registered {args.name}\n")
    return 0


def cmd_node_list() -> int:
    registry = load_registry()
    sys.stdout.write("NAME NODE_ID SSH_HOST USER ENABLED\n")
    for node in registry.get("nodes") or []:
        enabled = "true" if node["enabled"] else "false"
        sys.stdout.write(
            f"{node['name']} {node['node_id']} {node['ssh_host']} "
            f"{node['ssh_user']} {enabled}\n"
        )
    return 0


def cmd_node_show(name: str) -> int:
    node = require_node(load_registry(), name)
    for key in NODE_KEYS:
        value = node[key]
        if isinstance(value, bool):
            value = "true" if value else "false"
        sys.stdout.write(f"{key}={value}\n")
    return 0


def cmd_node_set(args: argparse.Namespace) -> int:
    registry = load_registry()
    set_host(registry, args.name, args.host, user=args.user, port=args.port)
    save_registry(None, registry)
    sys.stdout.write(f"Updated {args.name}\n")
    return 0


def cmd_node_enable(name: str, enabled: bool) -> int:
    registry = load_registry()
    set_enabled(registry, name, enabled)
    save_registry(None, registry)
    state = "enabled" if enabled else "disabled"
    sys.stdout.write(f"{name} {state}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vcl-fleet",
        description=(
            "Vincula fleet controller. User-local registry only in this "
            "milestone; SSH add/status/verify land in later 0.2.8 phases."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="create a user-local fleet.json registry")

    node = sub.add_parser("node", help="register and update fleet nodes")
    node_sub = node.add_subparsers(dest="node_command")

    p_add = node_sub.add_parser("add", help="register a node (Phase 5: --offline)")
    p_add.add_argument("name", help="short name (same charset as user tags)")
    p_add.add_argument("--host", required=True, help="SSH hostname or IP")
    p_add.add_argument("--user", help="SSH user (default: root, or user@host)")
    p_add.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    p_add.add_argument("--node-id", dest="node_id", help="logical node UUID")
    p_add.add_argument(
        "--instance-id",
        dest="instance_id",
        help="ignored; instance_id is not stored in fleet.json",
    )
    p_add.add_argument(
        "--offline",
        action="store_true",
        help="register without SSH (requires --node-id)",
    )

    node_sub.add_parser("list", help="list registered nodes")

    p_show = node_sub.add_parser("show", help="show one registered node")
    p_show.add_argument("name")

    p_set = node_sub.add_parser("set", help="change ssh_host (node_id stays)")
    p_set.add_argument("name")
    p_set.add_argument("--host", required=True, help="new SSH hostname or IP")
    p_set.add_argument("--user", help="optional new SSH user")
    p_set.add_argument("--port", type=int, help="optional new SSH port")

    p_disable = node_sub.add_parser("disable", help="disable a registered node")
    p_disable.add_argument("name")
    p_enable = node_sub.add_parser("enable", help="enable a registered node")
    p_enable.add_argument("name")

    sub.add_parser("status", help="remote status over SSH (Phase 7)")
    sub.add_parser(
        "verify",
        help="remote verify over SSH (Phase 7)",
        description=(
            f"Clock skew: WARN if drift exceeds {CLOCK_SKEW_WARN_SECONDS}s; "
            f"FAIL check {CLOCK_SKEW_FAIL_CHECK} if drift exceeds "
            f"{CLOCK_SKEW_FAIL_SECONDS}s (5 minutes)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub.add_parser("version", help="print vcl-fleet version")
    sub.add_parser("help", help="show this help")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command
    if command in (None, "help"):
        parser.print_help()
        return 0 if command == "help" else 2
    if command == "version":
        sys.stdout.write(f"vcl-fleet {VCL_FLEET_VERSION}\n")
        return 0
    if command == "init":
        return cmd_init()
    if command == "status":
        die(STATUS_NOT_WIRED, 2)
    if command == "verify":
        die(VERIFY_NOT_WIRED, 2)
    if command == "node":
        sub = args.node_command
        if sub is None:
            parser.parse_args(["node", "--help"])
            return 2
        if sub == "add":
            return cmd_node_add(args)
        if sub == "list":
            return cmd_node_list()
        if sub == "show":
            return cmd_node_show(args.name)
        if sub == "set":
            return cmd_node_set(args)
        if sub == "disable":
            return cmd_node_enable(args.name, False)
        if sub == "enable":
            return cmd_node_enable(args.name, True)
        die(f"unknown node command: {sub}", 2)
    die(f"unknown command: {command}", 2)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
