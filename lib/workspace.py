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


MIGRATE_PIPELINE = (
    "lock legacy Fleet",
    "validate fleet.json (fleet-registry/v2)",
    "PRAGMA integrity_check fleet.db (fleet-cache/v3)",
    "inventory legacy files",
    "mint fleet_id",
    "create temporary Workspace",
    "migrate registry",
    "migrate identity_file → credential refs",
    "extract Fleet-only host trust",
    "export instance_history",
    "create machine-local credential bindings",
    "migrate fleet.db → local state",
    "migrate status/users cache as derived state",
    "verify new Workspace",
    "atomic commit",
    "preserve old tree as legacy backup",
)


def _open_db_inspect(path: Path) -> Optional[Any]:
    """SQLite URI mode=ro inspect only — never open_fleet_db (WAL/migrate/chmod)."""
    import sqlite3

    if not path.is_file():
        return None
    return sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)


def plan_migrate_dry_run() -> dict[str, Any]:
    """Plan legacy→workspace migration with zero side effects (AC-4.0-04 / D48)."""
    _home, reg, dbp = _host.fleet_home(), _host.load_registry(), _host.fleet_db_path()
    nodes = list(reg.get("nodes") or [])
    idents = sorted({n["identity_file"] for n in nodes if n.get("identity_file")})
    gaps: list[dict[str, Any]] = []
    conn = _open_db_inspect(dbp)
    try:
        for n in nodes:
            rows = (
                conn.execute(
                    "SELECT 1 FROM instance_history WHERE node_id=? LIMIT 1",
                    (n["node_id"],),
                ).fetchall()
                if conn
                else []
            )
            if not rows:
                gaps.append(
                    {
                        "name": n["name"],
                        "node_id": n["node_id"],
                        "gap": (
                            "instance_history empty "
                            "(never synced; node add does not write history)"
                        ),
                    }
                )
    finally:
        if conn:
            conn.close()
    warns = (
        ["TRUST_MIGRATION_REQUIRED"]
        if any(n.get("ssh_host") for n in nodes)
        else []
    )
    return {
        "dry_run": True,
        "side_effects": "none",
        "pipeline": list(MIGRATE_PIPELINE),
        "counts": {
            "nodes": len(nodes),
            "identity_files": len(idents),
            "history_gaps": len(gaps),
        },
        "identity_files": idents,
        "history_gaps": gaps,
        "warnings": warns,
        "note": "D48: migration will NOT SSH to fill history gaps",
    }


def open_cache_readonly():
    """0.4.0 query seam; still open_fleet_db (RW+WAL). True mode=ro ≥0.4.2."""
    return _host.open_fleet_db()


def open_cache_for_sync():
    """0.4.0 sync/migrate RW seam; same backing until 0.4.2."""
    return _host.open_fleet_db()
