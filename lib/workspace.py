"""Workspace path and fleet registry seam (0.4.0 B3).

Loaded as a controller sibling via _load_controller_sibling — never import
this module from sys.path. Call bind(host) before use so die / schema /
normalize_node resolve from the fleet host module.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_host: Any = None

WORKSPACE_MANIFEST_NAME = "workspace.json"
MACHINE_LOCAL_DIRNAME = "machine-local"
WORKSPACE_VIEW_NAME = "workspace-view.json"
WORKSPACE_VIEW_SCHEMA_VERSION = 1
PORTABLE_DIGEST_NAMES = ("fleet.json", "workspace.json", "trust/known_hosts")
WS_ERR_ROLLBACK, WS_ERR_DIVERGED, WS_ERR_INCONSISTENT = (
    "WORKSPACE_ROLLBACK",
    "WORKSPACE_DIVERGED",
    "WORKSPACE_INCONSISTENT",
)
WS_ERR_CAS = "WORKSPACE_CAS_REJECTED"
_ZERO_STATE_DIGEST = "sha256:" + ("0" * 64)
_MANIFEST_REQUIRED_KEYS = (
    "schema_version",
    "fleet_id",
    "name",
    "revision",
    "write_id",
    "parent_revision",
    "parent_write_id",
    "state_digest",
    "last_writer_controller_id",
    "created_at",
    "updated_at",
)


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


def workspace_manifest_path() -> Path:
    return fleet_home() / WORKSPACE_MANIFEST_NAME


def machine_local_dir() -> Path:
    return fleet_home() / MACHINE_LOCAL_DIRNAME


def workspace_view_path() -> Path:
    return machine_local_dir() / WORKSPACE_VIEW_NAME


def trust_dir() -> Path:
    return fleet_home() / "trust"


def known_hosts_path() -> Path:
    return trust_dir() / "known_hosts"


def workspace_trust_active() -> bool:
    return workspace_manifest_path().is_file()


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


def mint_fleet_id() -> str:
    return str(uuid.uuid4())


def empty_workspace_manifest(
    *,
    name: str = "main",
    fleet_id: str | None = None,
    controller_id: str | None = None,
) -> dict[str, Any]:
    fid = fleet_id or mint_fleet_id()
    wid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cid = controller_id or str(uuid.uuid4())
    return {
        "schema_version": _host.WORKSPACE_SCHEMA_VERSION,
        "fleet_id": fid,
        "name": name,
        "revision": 0,
        "write_id": wid,
        "parent_revision": None,
        "parent_write_id": None,
        "state_digest": _ZERO_STATE_DIGEST,
        "last_writer_controller_id": cid,
        "created_at": now,
        "updated_at": now,
    }


def validate_workspace_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        _host.die("workspace.json must be a JSON object")
    for key in _MANIFEST_REQUIRED_KEYS:
        if key not in data:
            _host.die(f"workspace.json missing key: {key}")
    ver = data.get("schema_version")
    if ver != _host.WORKSPACE_SCHEMA_VERSION:
        _host.die(f"unsupported workspace schema: {ver}")
    for key in ("fleet_id", "write_id", "last_writer_controller_id"):
        val = data.get(key)
        if not isinstance(val, str) or not _host.UUID_RE.fullmatch(val):
            _host.die(f"workspace.json {key} must be a UUID")
    revision = data.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        _host.die("workspace.json revision must be an int >= 0")
    digest = data.get("state_digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        _host.die("workspace.json state_digest must start with sha256:")
    parent_rev = data.get("parent_revision")
    if parent_rev is not None and (
        not isinstance(parent_rev, int)
        or isinstance(parent_rev, bool)
        or parent_rev < 0
    ):
        _host.die("workspace.json parent_revision must be int >= 0 or null")
    parent_wid = data.get("parent_write_id")
    if parent_wid is not None and (
        not isinstance(parent_wid, str) or not _host.UUID_RE.fullmatch(parent_wid)
    ):
        _host.die("workspace.json parent_write_id must be a UUID or null")
    return data


def load_workspace_manifest(path: Optional[Path] = None) -> dict[str, Any]:
    path = workspace_manifest_path() if path is None else Path(path)
    if not path.is_file():
        _host.die(f"workspace manifest not found: {path}")
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        _host.die(f"invalid workspace.json: {exc}")
    except OSError as exc:
        _host.die(f"cannot read {path}: {exc}")
    return validate_workspace_manifest(data)


def save_workspace_manifest(
    manifest: dict[str, Any], path: Optional[Path] = None
) -> None:
    path = workspace_manifest_path() if path is None else Path(path)
    payload = validate_workspace_manifest(manifest)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(
        prefix=".workspace.json.", suffix=".tmp", dir=str(parent)
    )
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


def _manifest_digest_bytes(manifest: dict[str, Any]) -> bytes:
    payload = dict(manifest)
    payload["state_digest"] = _ZERO_STATE_DIGEST
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def compute_state_digest(
    home: Path | None = None, *, manifest: dict[str, Any] | None = None
) -> str:
    """Digest over PORTABLE_DIGEST_NAMES.

    workspace.json is hashed with state_digest zeroed so the digest is
    stable when stored inside that same file.
    """
    root = fleet_home() if home is None else Path(home)
    h = hashlib.sha256()
    for name in PORTABLE_DIGEST_NAMES:
        if name == WORKSPACE_MANIFEST_NAME:
            if manifest is not None:
                data = _manifest_digest_bytes(manifest)
            else:
                path = root / name
                if not path.is_file():
                    continue
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, UnicodeError):
                    data = path.read_bytes()
                else:
                    if isinstance(loaded, dict):
                        data = _manifest_digest_bytes(loaded)
                    else:
                        data = path.read_bytes()
            h.update(name.encode() + b"\0" + data)
            continue
        path = root / name
        if path.is_file():
            h.update(name.encode() + b"\0" + path.read_bytes())
    return "sha256:" + h.hexdigest()


def refresh_manifest_digest(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest["state_digest"] = compute_state_digest(manifest=manifest)
    return manifest


def create_workspace_manifest(
    *,
    name: str = "main",
    fleet_id: str | None = None,
    controller_id: str | None = None,
) -> dict[str, Any]:
    path = workspace_manifest_path()
    if path.is_file():
        _host.die(f"workspace manifest already exists: {path}")
    _ensure_fleet_home()
    manifest = empty_workspace_manifest(
        name=name, fleet_id=fleet_id, controller_id=controller_id
    )
    save_workspace_manifest(manifest, path)
    refresh_manifest_digest(manifest)
    save_workspace_manifest(manifest, path)
    return manifest


def validate_workspace_view(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        _host.die("workspace-view.json must be a JSON object")
    ver = data.get("schema_version")
    if ver != WORKSPACE_VIEW_SCHEMA_VERSION:
        _host.die(f"unsupported workspace-view schema: {ver}")
    for key in (
        "fleet_id",
        "last_seen_revision",
        "last_seen_write_id",
        "last_seen_state_digest",
    ):
        if key not in data:
            _host.die(f"workspace-view.json missing key: {key}")
    fid = data.get("fleet_id")
    if not isinstance(fid, str) or not _host.UUID_RE.fullmatch(fid):
        _host.die("workspace-view.json fleet_id must be a UUID")
    rev = data.get("last_seen_revision")
    if not isinstance(rev, int) or isinstance(rev, bool) or rev < 0:
        _host.die("workspace-view.json last_seen_revision must be an int >= 0")
    wid = data.get("last_seen_write_id")
    if not isinstance(wid, str) or not _host.UUID_RE.fullmatch(wid):
        _host.die("workspace-view.json last_seen_write_id must be a UUID")
    digest = data.get("last_seen_state_digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        _host.die("workspace-view.json last_seen_state_digest must start with sha256:")
    return data


def load_workspace_view(path: Optional[Path] = None) -> dict[str, Any] | None:
    path = workspace_view_path() if path is None else Path(path)
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        _host.die(f"invalid workspace-view.json: {exc}")
    except OSError as exc:
        _host.die(f"cannot read {path}: {exc}")
    return validate_workspace_view(data)


def save_workspace_view(
    view: dict[str, Any], path: Optional[Path] = None
) -> None:
    path = workspace_view_path() if path is None else Path(path)
    payload = validate_workspace_view(view)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(
        prefix=".workspace-view.json.", suffix=".tmp", dir=str(parent)
    )
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


def remember_workspace_view(manifest: dict[str, Any]) -> dict[str, Any]:
    view = {
        "schema_version": WORKSPACE_VIEW_SCHEMA_VERSION,
        "fleet_id": manifest["fleet_id"],
        "last_seen_revision": manifest["revision"],
        "last_seen_write_id": manifest["write_id"],
        "last_seen_state_digest": manifest["state_digest"],
    }
    save_workspace_view(view)
    return view


def detect_workspace_conflict(
    manifest: dict[str, Any], view: dict[str, Any] | None = None
) -> str | None:
    if manifest.get("state_digest") != compute_state_digest():
        return WS_ERR_INCONSISTENT
    if view is None:
        view = load_workspace_view()
    if view is None:
        return None
    last_rev = view["last_seen_revision"]
    if manifest["revision"] < last_rev:
        return WS_ERR_ROLLBACK
    if (
        manifest["revision"] == last_rev
        and manifest["write_id"] != view["last_seen_write_id"]
    ):
        return WS_ERR_DIVERGED
    return None


def cas_mutate_workspace(
    mutator: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    manifest = load_workspace_manifest()
    conflict = detect_workspace_conflict(manifest)
    if conflict is not None:
        _host.die(conflict)
    view = remember_workspace_view(manifest)
    mutated = mutator(copy.deepcopy(manifest))
    reread = load_workspace_manifest()
    if (reread["revision"], reread["write_id"]) != (
        view["last_seen_revision"],
        view["last_seen_write_id"],
    ):
        _host.die(WS_ERR_CAS)
    save_workspace_manifest(mutated)
    remember_workspace_view(mutated)
    return mutated


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
        "credential_refs_future": [
            {
                "name": n["name"],
                "node_id": n["node_id"],
                "identity_file": n.get("identity_file"),
                **planned_credential_refs(n),
            }
            for n in nodes
        ],
        "d57": "0.4 reserved; runtime observe=admin; SSH still identity_file until 0.5",
    }


def open_cache_readonly():
    """0.4.0 query seam; still open_fleet_db (RW+WAL). True mode=ro ≥0.4.2."""
    return _host.open_fleet_db()


def open_cache_for_sync():
    """0.4.0 sync/migrate RW seam; same backing until 0.4.2."""
    return _host.open_fleet_db()


ADMIN_CREDENTIAL_REF_KEY = "admin_credential_ref"
OBSERVE_CREDENTIAL_REF_KEY = "observe_credential_ref"
RESERVED_NODE_CREDENTIAL_KEYS = (ADMIN_CREDENTIAL_REF_KEY, OBSERVE_CREDENTIAL_REF_KEY)
DEFAULT_ADMIN_CREDENTIAL_REF = "admin-default"


def planned_credential_refs(node):
    admin = node.get(ADMIN_CREDENTIAL_REF_KEY) or DEFAULT_ADMIN_CREDENTIAL_REF
    observe = node.get(OBSERVE_CREDENTIAL_REF_KEY) or admin  # observe=admin
    return {
        ADMIN_CREDENTIAL_REF_KEY: admin,
        OBSERVE_CREDENTIAL_REF_KEY: observe,
    }


def node_schema_field_names():
    return tuple(_host.NODE_KEYS) + RESERVED_NODE_CREDENTIAL_KEYS
