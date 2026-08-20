"""Workspace path and fleet registry seam (0.4.0 B3).

Loaded as a controller sibling via _load_controller_sibling — never import
this module from sys.path. Call bind(host) before use so die / schema /
normalize_node resolve from the fleet host module.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

_host: Any = None


def bind(host: Any) -> None:
    global _host
    _host = host


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

def last_status_path() -> Path:
    return fleet_home() / "last-status.json"

def fleet_db_path() -> Path:
    return fleet_home() / "fleet.db"

def _chmod_private(path: Path, mode: int = 0o600) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass

def _ensure_fleet_home() -> Path:
    home = fleet_home()
    home.mkdir(parents=True, exist_ok=True)
    _chmod_private(home, 0o700)
    return home

def empty_registry() -> dict[str, Any]:
    return {"schema_version": _host.FLEET_SCHEMA_VERSION, "nodes": []}


def validate_registry(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        _host.die("fleet.json must be a JSON object")
    for key in data:
        if _host._is_forbidden_key(str(key)):
            _host.die("fleet.json must not store SSH passwords")
    ver = data.get("schema_version")
    if ver not in _host.FLEET_SCHEMA_VERSIONS_READ:
        _host.die(f"unsupported fleet-registry schema: {ver}")
    nodes_raw = data.get("nodes", [])
    if not isinstance(nodes_raw, list):
        _host.die("fleet.json nodes must be a list")
    nodes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for i, raw in enumerate(nodes_raw):
        node = _host.normalize_node(raw, index=i)
        if node["node_id"] in seen_ids:
            _host.die(f"duplicate node_id: {node['node_id']}")
        if node["name"] in seen_names:
            _host.die(f"duplicate name: {node['name']}")
        seen_ids.add(node["node_id"])
        seen_names.add(node["name"])
        nodes.append(node)
    return {"schema_version": _host.FLEET_SCHEMA_VERSION, "nodes": nodes}

def load_registry(path: Optional[Path] = None) -> dict[str, Any]:
    path = fleet_registry_path() if path is None else Path(path)
    if not path.is_file():
        return empty_registry()
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        _host.die(f"invalid fleet.json: {exc}")
    except OSError as exc:
        _host.die(f"cannot read {path}: {exc}")
    return validate_registry(data)

def _save_registry_unlocked(path: Optional[Path], registry: dict[str, Any]) -> None:
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
