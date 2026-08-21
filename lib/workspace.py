"""Workspace path and fleet registry seam (0.4.0 B3).

Loaded as a controller sibling via _load_controller_sibling — never import
this module from sys.path. Call bind(host) before use so die / schema /
normalize_node resolve from the fleet host module.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
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
PORTABLE_DIGEST_NAMES = (
    "fleet.json",
    "workspace.json",
    "trust/known_hosts",
    "history/instances.jsonl",
)
INSTANCE_HISTORY_SCHEMA = "instance-history/v1"  # D45 namespaced
_HISTORY_KEYS = (
    "node_id",
    "instance_id",
    "started_at",
    "retired_at",
    "endpoint",
    "reason",
)
_HISTORY_FORBIDDEN_SUBSTR = ("password", "identity", "key", "token")
WS_ERR_ROLLBACK, WS_ERR_DIVERGED, WS_ERR_INCONSISTENT = (
    "WORKSPACE_ROLLBACK",
    "WORKSPACE_DIVERGED",
    "WORKSPACE_INCONSISTENT",
)
WS_ERR_CAS = "WORKSPACE_CAS_REJECTED"
# Portable snapshot members only (D22/D28): never machine-local/, fleet.db, keys.
EXPORT_MEMBERS = (
    "workspace.json",
    "fleet.json",
    "trust/known_hosts",
    "history/instances.jsonl",
)
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


LOCAL_STATE_ARCHIVES, LOCAL_STATE_UI_RUNTIME = "archives", "ui-runtime"


def fleet_local_state_root() -> Path:
    o = os.environ.get("VCL_FLEET_LOCAL_STATE")
    if o:
        return Path(o)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "vincula"
    return Path(
        os.environ["XDG_STATE_HOME"]
        if os.environ.get("XDG_STATE_HOME")
        else Path.home() / ".local" / "state"
    ) / "vincula"


def fleet_local_state_dir(fleet_id: str) -> Path:
    return fleet_local_state_root() / fleet_id


def ensure_fleet_local_state(fleet_id: str) -> Path:
    root = fleet_local_state_dir(fleet_id)
    for d in (root, root / LOCAL_STATE_ARCHIVES, root / LOCAL_STATE_UI_RUNTIME):
        d.mkdir(parents=True, exist_ok=True)
        _chmod_private(d, 0o700)
    return root


def fleet_registry_path() -> Path:
    return fleet_home() / "fleet.json"


def last_status_path() -> Path:
    if workspace_trust_active():
        fid = load_workspace_manifest()["fleet_id"]
        return (
            fleet_local_state_dir(fid)
            / LOCAL_STATE_UI_RUNTIME
            / "last-status.json"
        )
    return fleet_home() / "last-status.json"


def fleet_db_path() -> Path:
    if workspace_trust_active():
        fid = load_workspace_manifest()["fleet_id"]
        return fleet_local_state_dir(fid) / "fleet.db"
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


def history_dir() -> Path:
    return fleet_home() / "history"


def instances_history_path() -> Path:
    return history_dir() / "instances.jsonl"


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
    out: dict[str, Any] = {
        "schema_version": _host.FLEET_SCHEMA_VERSION,
        "nodes": nodes,
    }
    fid = data.get("fleet_id")
    if fid is not None and fid != "":
        if not isinstance(fid, str) or not _host.UUID_RE.fullmatch(fid):
            _host.die(f"invalid fleet_id: {fid}")
        out["fleet_id"] = fid
    return out

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


def refresh_manifest_digest(
    manifest: dict[str, Any], *, home: Path | None = None
) -> dict[str, Any]:
    manifest["state_digest"] = compute_state_digest(home, manifest=manifest)
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


def append_instance_history_line(rec: dict[str, Any]) -> None:
    """Atomic append one portable instance-history/v1 JSONL record (no secrets)."""
    if not isinstance(rec, dict):
        _host.die("instance-history/v1 record must be an object")
    for k in rec:
        kl = str(k).lower()
        if any(s in kl for s in _HISTORY_FORBIDDEN_SUBSTR):
            _host.die(f"instance-history/v1 forbids secret field: {k}")
        if k not in _HISTORY_KEYS:
            _host.die(f"unsupported instance-history/v1 field: {k}")
    payload = {k: rec.get(k) for k in _HISTORY_KEYS}
    d = history_dir()
    d.mkdir(parents=True, exist_ok=True)
    _chmod_private(d, 0o700)
    path = instances_history_path()
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    _chmod_private(path, 0o600)


def parse_instance_history_jsonl(path: Path | None = None) -> list[dict[str, Any]]:
    path = instances_history_path() if path is None else Path(path)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _host.die(f"cannot read {path}: {exc}")
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            _host.die("invalid instance-history/v1 line")
        if not isinstance(obj, dict):
            _host.die("invalid instance-history/v1 line")
        out.append(obj)
    return out


def export_instance_history_from_db(
    conn: Any, dest: Path | None = None
) -> int:
    """Export DB instance_history rows to portable JSONL. Returns row count."""
    dest = instances_history_path() if dest is None else Path(dest)
    rows = conn.execute(
        """
        SELECT node_id, instance_id, started_at, retired_at, endpoint
        FROM instance_history
        ORDER BY started_at, rowid
        """
    ).fetchall()
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(
        prefix=".instances.jsonl.", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for row in rows:
                if hasattr(row, "keys"):
                    node_id = row["node_id"]
                    instance_id = row["instance_id"]
                    started_at = row["started_at"]
                    retired_at = row["retired_at"]
                    endpoint = row["endpoint"]
                else:
                    node_id, instance_id, started_at, retired_at, endpoint = row
                rec = {
                    "node_id": node_id,
                    "instance_id": instance_id,
                    "started_at": started_at,
                    "retired_at": retired_at,
                    "endpoint": endpoint,
                    "reason": (
                        "retired" if retired_at else "sync-first-sight"
                    ),
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
        os.chmod(dest, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(rows)


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
    """SQLite URI mode=ro inspect — never open_fleet_db (migrate/chmod/create).

    With rollback journal (DELETE), plain mode=ro reflects committed state (P1-2).
    Never returns a writer.
    """
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


MIGRATE_FAIL_AFTER_ENV = "VCL_WORKSPACE_MIGRATE_FAIL_AFTER"
_MIGRATE_STAGING_NAME = ".migrate-staging"
_COUNT_TABLES = (
    "instance_history",
    "audit_events",
    "sync_cursor",
    "node_snapshot",
    "user_snapshot",
)


def _migrate_fail_after(step: str) -> None:
    if os.environ.get(MIGRATE_FAIL_AFTER_ENV) == step:
        _host.die(f"migrate fail-inject: {step}", 2)


def execute_migrate() -> dict[str, Any]:
    """Run MIGRATE_PIPELINE for real. Holds fleet_op_lock for whole body. No SSH."""
    with _host.fleet_op_lock():
        return _execute_migrate_locked()


def _table_count(conn: Any, table: str) -> int:
    import sqlite3

    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if row is None:
            return 0
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return 0


def _copy_fleet_db_to_staging(src: Path, dest: Path) -> None:
    """Copy fleet.db into staging; checkpoint leftover WAL into main first (P1-2)."""
    import sqlite3

    try:
        conn = sqlite3.connect(str(src), timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=DELETE").fetchone()
            conn.close()
        except sqlite3.Error:
            try:
                conn.close()
            except Exception:
                pass
            raise
    except sqlite3.Error as exc:
        _host.die(f"cannot prepare fleet.db for staging copy: {exc}")
    shutil.copy2(src, dest)


def _open_staging_fleet_db(path: Path) -> Any:
    """Open a staging fleet.db copy RW and apply schema 1→2→3 (source untouched)."""
    import sqlite3

    try:
        conn = sqlite3.connect(str(path), timeout=30)
    except sqlite3.Error as exc:
        _host.die(f"cannot open staging fleet.db: {exc}")
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=DELETE").fetchone()
        conn.execute("PRAGMA synchronous=NORMAL")
        if not _host._has_meta_table(conn):
            conn.executescript(_host.FLEET_DB_DDL)
            _host.fleet_db_meta_set(
                conn, "schema_version", str(_host.FLEET_DB_SCHEMA_VERSION)
            )
            conn.commit()
        else:
            ver = _host.fleet_db_meta_get(conn, "schema_version")
            if ver == "1":
                _host._migrate_fleet_db_1_to_2(conn)
                ver = "2"
            if ver == "2":
                _host._migrate_fleet_db_2_to_3(conn)
            elif ver != str(_host.FLEET_DB_SCHEMA_VERSION):
                conn.close()
                _host.die(f"unsupported fleet-cache schema: {ver}")
        return conn
    except SystemExit:
        raise
    except sqlite3.Error as exc:
        try:
            conn.close()
        except Exception:
            pass
        _host.die(f"cannot initialize staging fleet.db: {exc}")


def _execute_migrate_locked() -> dict[str, Any]:
    """16-step legacy→workspace migrate. Source untouched until atomic commit."""
    home = fleet_home()
    staging: Path | None = None
    committed = False
    warnings: list[str] = []
    ref_map: dict[str, str] = {}
    history_exported = 0
    fleet_id = ""
    bak: Path | None = None

    try:
        # 1. lock legacy Fleet (already held by execute_migrate)
        _migrate_fail_after("lock legacy Fleet")

        # 2. validate fleet.json (fleet-registry/v2)
        reg = _host.load_registry()
        _migrate_fail_after("validate fleet.json (fleet-registry/v2)")

        # 3. PRAGMA integrity_check fleet.db (fleet-cache/v3)
        dbp = _host.fleet_db_path()
        src_counts: dict[str, int] = {t: 0 for t in _COUNT_TABLES}
        if dbp.is_file():
            conn = _open_db_inspect(dbp)
            if conn is None:
                _host.die("cannot inspect fleet.db")
            try:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                if row is None or str(row[0]) != "ok":
                    _host.die("fleet.db integrity_check failed")
                if _host._has_meta_table(conn):
                    ver = _host.fleet_db_meta_get(conn, "schema_version")
                    if ver not in ("1", "2", str(_host.FLEET_DB_SCHEMA_VERSION)):
                        _host.die(f"unsupported fleet-cache schema: {ver}")
                for table in _COUNT_TABLES:
                    src_counts[table] = _table_count(conn, table)
            finally:
                conn.close()
        _migrate_fail_after("PRAGMA integrity_check fleet.db (fleet-cache/v3)")

        # 4. inventory legacy files
        inventory = {
            p.name: p.stat().st_size for p in home.iterdir() if p.is_file()
        }
        del inventory  # observed only; keep zero side effects until staging
        _migrate_fail_after("inventory legacy files")

        # 5. mint fleet_id
        fleet_id = mint_fleet_id()
        _migrate_fail_after("mint fleet_id")

        # 6. create temporary Workspace
        staging = home / _MIGRATE_STAGING_NAME
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(mode=0o700, parents=True)
        _chmod_private(staging, 0o700)
        for sub in ("trust", "history", "machine-local"):
            d = staging / sub
            d.mkdir(mode=0o700, parents=True)
            _chmod_private(d, 0o700)
        _migrate_fail_after("create temporary Workspace")

        # 7–8. migrate registry + identity_file → credential refs
        new_reg: dict[str, Any] = {
            "schema_version": 2,
            "fleet_id": fleet_id,
            "nodes": [],
        }
        mapping: dict[str, str] = {}
        i = 0
        for node in reg.get("nodes") or []:
            n = dict(node)
            path = n.pop("identity_file", None)
            if path:
                if path not in mapping:
                    i += 1
                    mapping[path] = f"migrated-key-{i}"
                ref = mapping[path]
                n["admin_credential_ref"] = ref
                n["observe_credential_ref"] = ref
            new_reg["nodes"].append(n)
        _save_registry_unlocked(staging / "fleet.json", new_reg)
        _migrate_fail_after("migrate registry")
        _migrate_fail_after("migrate identity_file → credential refs")

        # 9. extract Fleet-only host trust (never keyscan)
        nodes_for_trust = list(new_reg["nodes"])
        trust_src = Path.home() / ".ssh" / "known_hosts"
        trust_dest = staging / "trust" / "known_hosts"
        trust_result = _host.extract_fleet_host_trust(
            nodes_for_trust, trust_src, trust_dest
        )
        for w in trust_result.get("warnings") or []:
            if w not in warnings:
                warnings.append(w)
        _migrate_fail_after("extract Fleet-only host trust")

        # 10. export instance_history (gaps stay gaps; D48)
        hist_dest = staging / "history" / "instances.jsonl"
        src_conn = _open_db_inspect(dbp) if dbp.is_file() else None
        try:
            if src_conn is not None:
                history_exported = export_instance_history_from_db(
                    src_conn, hist_dest
                )
            else:
                hist_dest.write_text("", encoding="utf-8")
                _chmod_private(hist_dest, 0o600)
                history_exported = 0
        finally:
            if src_conn is not None:
                src_conn.close()
        _migrate_fail_after("export instance_history")

        # 11. create machine-local credential bindings
        bindings = _host.empty_bindings()
        for path, ref in mapping.items():
            resolved = _host.validate_identity_file(path, must_exist=True)
            bindings["bindings"][ref] = {
                "type": "identity_file",
                "path": resolved,
            }
        _host.save_bindings(
            bindings, staging / "machine-local" / "credential-bindings.json"
        )
        ref_map = {ref: path for path, ref in mapping.items()}
        _migrate_fail_after("create machine-local credential bindings")

        # 12. migrate fleet.db → local state (source untouched until commit)
        if dbp.is_file():
            staging_db = staging / "fleet.db"
            _copy_fleet_db_to_staging(dbp, staging_db)
            st_conn = _open_staging_fleet_db(staging_db)
            try:
                row = st_conn.execute("PRAGMA integrity_check").fetchone()
                if row is None or str(row[0]) != "ok":
                    _host.die("staging fleet.db integrity_check failed")
                _host.fleet_db_meta_set(st_conn, "fleet_id", fleet_id)
                for table in _COUNT_TABLES:
                    got = _table_count(st_conn, table)
                    if got != src_counts[table]:
                        _host.die(
                            f"fleet.db {table} count mismatch: "
                            f"src={src_counts[table]} staging={got}"
                        )
            finally:
                st_conn.close()
        _migrate_fail_after("migrate fleet.db → local state")

        # 13. migrate status/users cache as derived state
        last_status = last_status_path()
        if last_status.is_file():
            shutil.copy2(last_status, staging / "last-status.json")
        _migrate_fail_after("migrate status/users cache as derived state")

        # 14. verify new Workspace
        manifest = empty_workspace_manifest(fleet_id=fleet_id)
        save_workspace_manifest(manifest, staging / WORKSPACE_MANIFEST_NAME)
        refresh_manifest_digest(manifest, home=staging)
        save_workspace_manifest(manifest, staging / WORKSPACE_MANIFEST_NAME)
        old_home_env = os.environ.get("VCL_FLEET_HOME")
        os.environ["VCL_FLEET_HOME"] = str(staging)
        try:
            conflict = detect_workspace_conflict(manifest, view=None)
        finally:
            if old_home_env is None:
                os.environ.pop("VCL_FLEET_HOME", None)
            else:
                os.environ["VCL_FLEET_HOME"] = old_home_env
        if conflict is not None:
            _host.die(conflict)
        _migrate_fail_after("verify new Workspace")

        # 15–16. legacy backup then atomic commit
        utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak = home / f"legacy-pre-workspace-{utc}"
        bak.mkdir(mode=0o700, parents=True)
        _chmod_private(bak, 0o700)
        for name in ("fleet.json", "fleet.db", "last-status.json"):
            src = home / name
            if src.is_file():
                shutil.copy2(src, bak / name)

        def _replace_into(src: Path, dest: Path) -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(dest.parent, 0o700)
            except OSError:
                pass
            os.replace(src, dest)

        _replace_into(staging / "fleet.json", home / "fleet.json")
        _replace_into(
            staging / WORKSPACE_MANIFEST_NAME, home / WORKSPACE_MANIFEST_NAME
        )
        fleet_db_dest: Path | None = None
        if (staging / "fleet.db").is_file():
            # Commit cache to local-state/<fleet_id>/ (D23); do not write
            # live home/fleet.db (legacy bak already copied above).
            ensure_fleet_local_state(fleet_id)
            fleet_db_dest = fleet_local_state_dir(fleet_id) / "fleet.db"
            _replace_into(staging / "fleet.db", fleet_db_dest)
            # Drop legacy home cache + any leftover WAL-era sidecars.
            for leftover in (
                home / "fleet.db",
                Path(str(home / "fleet.db") + "-wal"),
                Path(str(home / "fleet.db") + "-shm"),
            ):
                if leftover.is_file():
                    leftover.unlink()
        if (staging / "last-status.json").is_file():
            ensure_fleet_local_state(fleet_id)
            _replace_into(
                staging / "last-status.json",
                fleet_local_state_dir(fleet_id)
                / LOCAL_STATE_UI_RUNTIME
                / "last-status.json",
            )
            leg_status = home / "last-status.json"
            if leg_status.is_file():
                leg_status.unlink()
        _replace_into(
            staging / "trust" / "known_hosts",
            home / "trust" / "known_hosts",
        )
        _replace_into(
            staging / "history" / "instances.jsonl",
            home / "history" / "instances.jsonl",
        )
        bind_src = staging / "machine-local" / "credential-bindings.json"
        if bind_src.is_file():
            _replace_into(
                bind_src,
                home / MACHINE_LOCAL_DIRNAME / "credential-bindings.json",
            )

        committed = True
        remember_workspace_view(load_workspace_manifest())
        _migrate_fail_after("atomic commit")
        _migrate_fail_after("preserve old tree as legacy backup")

        result: dict[str, Any] = {
            "ok": True,
            "fleet_id": fleet_id,
            "ref_map": ref_map,
            "warnings": warnings,
            "legacy_backup": str(bak),
            "history_exported": history_exported,
        }
        if fleet_db_dest is not None:
            result["fleet_db"] = str(fleet_db_dest)
        return result
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def open_cache_readonly():
    """Query/UI GET: mode=ro + query_only; never migrate/chmod/create (D47/P1-2)."""
    import sqlite3

    path = _host.fleet_db_path()
    if not path.is_file():
        _host.die(f"cannot open fleet.db: {path}")
    try:
        conn = sqlite3.connect(
            f"file:{path.resolve()}?mode=ro",
            uri=True,
            timeout=30,
        )
    except sqlite3.Error as exc:
        _host.die(f"cannot open fleet.db: {exc}")
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _host.open_cache_check(conn)
    except SystemExit:
        conn.close()
        raise
    return conn


def open_cache_for_sync():
    """Sole normal writer (D24); RW + rollback journal + migrate."""
    return _host.open_fleet_db()


def _assert_portable_registry(registry: dict[str, Any]) -> None:
    """Reject secrets / machine absolute credential paths (D22/D28)."""
    for i, node in enumerate(registry.get("nodes") or []):
        if not isinstance(node, dict):
            _host.die(f"nodes[{i}] must be an object")
        for key in node:
            kl = str(key).lower()
            if kl == "identity_file" or "password" in kl or kl in (
                "passwd",
                "ssh_password",
            ):
                _host.die(
                    f"portable workspace forbids credential field: {key}"
                )
            if kl.endswith("_file") and isinstance(node.get(key), str):
                val = node[key]
                if val.startswith("/") or (len(val) > 1 and val[1] == ":"):
                    _host.die(
                        f"portable workspace forbids absolute path in {key}"
                    )


def _safe_export_member_name(name: str) -> str:
    n = str(name).replace("\\", "/").lstrip("./")
    if not n or n.startswith("/") or ".." in n.split("/"):
        _host.die(f"unsafe archive member: {name}")
    if n not in EXPORT_MEMBERS:
        _host.die(f"non-portable archive member: {n}")
    return n


def export_workspace(dest: Path) -> Path:
    """Write tar.gz of portable workspace members (no secrets / machine-local)."""
    dest = Path(dest).expanduser()
    if not dest.is_absolute():
        dest = dest.resolve()
    home = fleet_home()
    manifest = load_workspace_manifest()
    validate_workspace_manifest(manifest)
    reg = load_registry()
    _assert_portable_registry(reg)
    # Re-check raw fleet.json bytes for residual identity_file / passwords.
    fleet_path = fleet_registry_path()
    if not fleet_path.is_file():
        _host.die(f"fleet.json not found: {fleet_path}")
    raw = fleet_path.read_text(encoding="utf-8")
    if '"identity_file"' in raw or "'identity_file'" in raw:
        _host.die("portable workspace forbids identity_file in fleet.json")
    lowered = raw.lower()
    if '"password"' in lowered or "passwd" in lowered:
        _host.die("portable workspace forbids credentials in fleet.json")

    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".workspace-export.", suffix=".tgz", dir=str(parent)
    )
    os.close(fd)
    try:
        mtime = int(datetime.now(timezone.utc).timestamp())
        with tarfile.open(tmp, "w:gz") as tf:
            for name in EXPORT_MEMBERS:
                path = home / name
                if not path.is_file():
                    continue
                data = path.read_bytes()
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                info.mode = 0o600
                info.mtime = mtime
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                tf.addfile(info, io.BytesIO(data))
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
        os.chmod(dest, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return dest


def import_workspace(src: Path) -> dict[str, Any]:
    """Extract portable snapshot into fleet_home; never import bindings/secrets."""
    src = Path(src).expanduser()
    if not src.is_file():
        _host.die(f"workspace archive not found: {src}")
    home = _ensure_fleet_home()
    for dname in ("trust", "history", MACHINE_LOCAL_DIRNAME):
        d = home / dname
        d.mkdir(parents=True, exist_ok=True)
        _chmod_private(d, 0o700)

    extracted: set[str] = set()
    try:
        with tarfile.open(src, "r:gz") as tf:
            for member in tf.getmembers():
                if member.isdir():
                    continue
                if not member.isfile():
                    _host.die(f"unsupported archive member type: {member.name}")
                name = _safe_export_member_name(member.name)
                if member.size < 0:
                    _host.die(f"invalid archive member size: {name}")
                fh = tf.extractfile(member)
                if fh is None:
                    _host.die(f"cannot read archive member: {name}")
                data = fh.read()
                dest = home / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(
                    prefix=f".{dest.name}.",
                    suffix=".tmp",
                    dir=str(dest.parent),
                )
                try:
                    with os.fdopen(fd, "wb") as out:
                        out.write(data)
                    os.chmod(tmp, 0o600)
                    os.replace(tmp, dest)
                    os.chmod(dest, 0o600)
                except Exception:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    raise
                extracted.add(name)
    except tarfile.TarError as exc:
        _host.die(f"invalid workspace archive: {exc}")

    if "workspace.json" not in extracted:
        _host.die("workspace archive missing workspace.json")
    if "fleet.json" not in extracted:
        _host.die("workspace archive missing fleet.json")

    reg = load_registry()
    _assert_portable_registry(reg)
    raw = fleet_registry_path().read_text(encoding="utf-8")
    if '"identity_file"' in raw:
        _host.die("portable workspace forbids identity_file in fleet.json")

    manifest = load_workspace_manifest()
    refresh_manifest_digest(manifest)
    save_workspace_manifest(manifest)
    remember_workspace_view(manifest)
    return manifest


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
