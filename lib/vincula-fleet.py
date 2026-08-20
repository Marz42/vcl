#!/usr/bin/env python3
"""vincula-fleet — workstation fleet controller (registry CLI).

Stdlib only: argparse, json, pathlib, os, sys, re, tempfile, subprocess,
hashlib, base64, datetime, csv, uuid, sqlite3, importlib, shlex, ipaddress,
time, threading, functools, contextlib, fcntl (POSIX) / msvcrt (Windows).
OpenSSH via the system ssh/ssh.exe binary (injectable with VCL_FLEET_SSH),
ssh-keyscan (VCL_FLEET_SSH_KEYSCAN), and scp (VCL_FLEET_SCP). No pip, no
paramiko, no cryptography package. No root, no systemd, no /etc/vincula.
Local Audit UI lives in lib/vincula-ui/ (loopback-only stdlib HTTP).

User-local fleet.json is the node registry. SSH passwords are never
stored. Targets Python 3.10+.
"""

from __future__ import annotations

import argparse
import base64
import csv
import functools
import hashlib
import importlib.machinery
import importlib.util
import io
import ipaddress
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

VCL_FLEET_VERSION = "0.3.1"
FLEET_REGISTRY_SCHEMA_VERSION = 2
FLEET_SCHEMA_VERSIONS_READ = (1, 2)
FLEET_CACHE_SCHEMA_VERSION = 3
WORKSPACE_SCHEMA_VERSION = 1
AUDIT_ARCHIVE_SCHEMA_VERSION = 1
TELEMETRY_SCHEMA_VERSION = 1
FLEET_SCHEMA_VERSION = FLEET_REGISTRY_SCHEMA_VERSION
FLEET_DB_SCHEMA_VERSION = FLEET_CACHE_SCHEMA_VERSION
NODE_STATUS_ACTIVE = "active"
NODE_STATUS_DISABLED = "disabled"
NODE_STATUS_RETIRED = "retired"
NODE_STATUSES = (NODE_STATUS_ACTIVE, NODE_STATUS_DISABLED, NODE_STATUS_RETIRED)
INSTANCE_STATUS_ACTIVE = "active"
INSTANCE_STATUS_RETIRED = "retired"
INSTANCE_STATUSES = (INSTANCE_STATUS_ACTIVE, INSTANCE_STATUS_RETIRED)
RETIRE_SKIP_SYNC_ENV = "VCL_FLEET_RETIRE_SKIP_SYNC"
SYNC_STATUS_OK = "ok"
SYNC_STATUS_EXPIRED = "expired"
SYNC_STATUS_ERROR = "error"
CURSOR_KIND_EVENT_ID = "event_id"
CURSOR_KIND_EXPORT_SEQ = "export_seq"
EXPORT_PROTOCOL_VERSION = 2

# Controller-local cache (audit/cursor) plus instance_history SoT.
# fleet.json does not store instance_id. Plan §0.8.
INSTANCE_HISTORY_DDL = """
CREATE TABLE instance_history (
  node_id TEXT NOT NULL,
  instance_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  retired_at TEXT,
  endpoint TEXT,
  ssh_host TEXT,
  status TEXT NOT NULL,
  PRIMARY KEY (node_id, instance_id)
);
CREATE INDEX idx_instance_history_node
  ON instance_history(node_id, started_at);
"""

FLEET_DB_DDL = """
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE audit_events (
  node_id TEXT NOT NULL,
  instance_id TEXT,
  event_id INTEGER NOT NULL,
  export_seq INTEGER,
  connection_id TEXT NOT NULL,
  generation INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  started_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  closed_at TEXT,
  destination_host TEXT,
  destination_ip TEXT,
  destination_port INTEGER,
  network TEXT,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  imported_at TEXT NOT NULL,
  PRIMARY KEY (node_id, event_id)
);

CREATE INDEX idx_audit_user_started
  ON audit_events(user_id, started_at);
CREATE INDEX idx_audit_node_event
  ON audit_events(node_id, event_id);

CREATE TABLE sync_cursor (
  node_id TEXT PRIMARY KEY,
  instance_id TEXT,
  last_event_id INTEGER NOT NULL,
  last_export_seq INTEGER NOT NULL DEFAULT 0,
  cursor_kind TEXT NOT NULL DEFAULT 'export_seq',
  last_sync_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE daily_usage (
  date TEXT NOT NULL,
  node_id TEXT NOT NULL,
  instance_id TEXT,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  destination_host TEXT NOT NULL,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  connection_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (date, node_id, user_id, destination_host)
);
""" + INSTANCE_HISTORY_DDL

INSERT_AUDIT_EVENT_SQL = """
INSERT INTO audit_events (
  node_id, instance_id, event_id, export_seq, connection_id, generation,
  user_id, user_tag, started_at, last_seen_at, closed_at,
  destination_host, destination_ip, destination_port, network,
  upload_bytes, download_bytes, imported_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(node_id, event_id) DO UPDATE SET
  instance_id = excluded.instance_id,
  export_seq = excluded.export_seq,
  connection_id = excluded.connection_id,
  generation = excluded.generation,
  user_id = excluded.user_id,
  user_tag = excluded.user_tag,
  started_at = excluded.started_at,
  last_seen_at = excluded.last_seen_at,
  closed_at = excluded.closed_at,
  destination_host = excluded.destination_host,
  destination_ip = excluded.destination_ip,
  destination_port = excluded.destination_port,
  network = excluded.network,
  upload_bytes = excluded.upload_bytes,
  download_bytes = excluded.download_bytes,
  imported_at = excluded.imported_at
"""
CLOCK_SKEW_WARN_SECONDS = 30
CLOCK_SKEW_FAIL_SECONDS = 300
CLOCK_SKEW_FAIL_CHECK = "audit-clock-health"
FLEET_OP_LOCK_TIMEOUT = 30
FLEET_BUSY_EXIT = 4
FLEET_BUSY_MSG = "busy: another vincula operation in progress"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
# Same contract as is_valid_user_tag: lowercase alnum / . _ - ; max 32.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
# OpenSSH-safe POSIX username: starts with [a-z_], then [a-z0-9_-]; max 32.
USER_METADATA_MAX = 128
FORBIDDEN_NODE_KEYS = ("password", "passwd", "ssh_password")
NODE_KEYS = (
    "node_id",
    "name",
    "ssh_host",
    "ssh_user",
    "ssh_port",
    "identity_file",
    "enabled",
    "status",
)
REMOTE_BACKUP_TAR = "/var/backups/vincula/backup.tar"
REMOTE_RESTORE_TAR = "/tmp/vincula-restore.tar"
REMOTE_REISSUE_CSV = "/tmp/reissue.csv"
REMOTE_VCL_BIN = "/usr/local/bin/vcl"
REMOTE_VERSION_FILE = "/etc/vincula/VERSION"
CSV_CREDENTIAL_HEADER = ("user", "node", "credential_id", "vless_uri")
CSV_IMPORT_HEADER = ("tag", "display_name", "department", "nodes")
CSV_EXPORT_META_HEADER = (
    "tag",
    "display_name",
    "department",
    "user_id",
    "node",
    "enabled",
)
CREDENTIAL_WARN_TAIL = "contains authentication credentials."
STATUS_JSON_SCHEMA_VERSION = 1
VERIFY_JSON_SCHEMA_VERSION = 1
SYNC_JSON_SCHEMA_VERSION = 1
AUDIT_JSON_SCHEMA_VERSION = 1
STATS_JSON_SCHEMA_VERSION = 1
REPLACE_JSON_SCHEMA_VERSION = 1
INSTANCE_JSON_SCHEMA_VERSION = 1
LABELED_NODE_SQL = "node_id IS NOT NULL AND node_id != ''"
# Same display as destination_display(): host, else IP, else "-".
AUDIT_DESTINATION_SQL = (
    "LOWER(COALESCE(NULLIF(destination_host, ''), "
    "NULLIF(destination_ip, ''), '-'))"
)
# D15 fleet mutation: PLANNED → APPLYING → SUCCESS | PARTIAL (PARTIAL includes all-failed).
OP_PLANNED = "PLANNED"
OP_APPLYING = "APPLYING"
OP_SUCCESS, OP_FAILED = "SUCCESS", "FAILED"
OP_PARTIAL = "PARTIAL"
MUTATION_SCHEMA_VERSION = 1
MUTATION_EXIT_SUCCESS = 0
MUTATION_EXIT_PARTIAL = 2
def die(message: str, code: int = 1) -> None:
    sys.stderr.write(f"vcl-fleet: {message}\n")
    raise SystemExit(code)


def _controller_lib_dir() -> Path:
    """Directory that holds this file and sibling runtime modules.

    Zip unpack, repo checkout, and ``python3 bin/vcl-fleet`` all resolve
    ``vincula-fleet.py`` to a real path; audit/backup must load from that
    same ``lib/`` directory. Never cwd, never ``PYTHONPATH``, never a
    sibling checkout the operator is not running.
    """
    here = Path(__file__).resolve()
    parent = here.parent
    if parent.name == "__pycache__":
        parent = parent.parent
    return parent


def _load_controller_sibling(modname: str, filename: str) -> Any:
    path = _controller_lib_dir() / filename
    if not path.is_file():
        die(f"{filename} not found: {path}")
    existing = sys.modules.get(modname)
    if existing is not None:
        existing_file = getattr(existing, "__file__", None)
        if existing_file is None or Path(existing_file).resolve() != path:
            del sys.modules[modname]
    loader = importlib.machinery.SourceFileLoader(modname, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        die(f"cannot load {filename}")
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class _FleetHostProxy:
    """Attribute host for seam bind(); works under importlib without sys.modules."""

    __slots__ = ("_g",)

    def __init__(self, g: dict[str, Any]) -> None:
        object.__setattr__(self, "_g", g)

    def __getattr__(self, name: str) -> Any:
        g = object.__getattribute__(self, "_g")
        try:
            return g[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


_FLEET_HOST = _FleetHostProxy(globals())

_WS = _load_controller_sibling("vcl_workspace", "workspace.py")
_WS.bind(_FLEET_HOST)


def fleet_home() -> Path:
    return _WS.fleet_home()


def fleet_registry_path() -> Path:
    return _WS.fleet_registry_path()


def last_status_path() -> Path:
    return _WS.last_status_path()


def fleet_db_path() -> Path:
    return _WS.fleet_db_path()


workspace_manifest_path = _WS.workspace_manifest_path
machine_local_dir = _WS.machine_local_dir
workspace_view_path = _WS.workspace_view_path
trust_dir = _WS.trust_dir
known_hosts_path = _WS.known_hosts_path
workspace_trust_active = _WS.workspace_trust_active
history_dir = _WS.history_dir
instances_history_path = _WS.instances_history_path
append_instance_history_line = _WS.append_instance_history_line
parse_instance_history_jsonl = _WS.parse_instance_history_jsonl
export_instance_history_from_db = _WS.export_instance_history_from_db
mint_fleet_id = _WS.mint_fleet_id
empty_workspace_manifest = _WS.empty_workspace_manifest
validate_workspace_manifest = _WS.validate_workspace_manifest
load_workspace_manifest = _WS.load_workspace_manifest
save_workspace_manifest = _WS.save_workspace_manifest
create_workspace_manifest = _WS.create_workspace_manifest
compute_state_digest = _WS.compute_state_digest
refresh_manifest_digest = _WS.refresh_manifest_digest
load_workspace_view = _WS.load_workspace_view
save_workspace_view = _WS.save_workspace_view
remember_workspace_view = _WS.remember_workspace_view
detect_workspace_conflict = _WS.detect_workspace_conflict
cas_mutate_workspace = _WS.cas_mutate_workspace
execute_migrate = _WS.execute_migrate
PORTABLE_DIGEST_NAMES = _WS.PORTABLE_DIGEST_NAMES
INSTANCE_HISTORY_SCHEMA = _WS.INSTANCE_HISTORY_SCHEMA
WORKSPACE_VIEW_SCHEMA_VERSION = _WS.WORKSPACE_VIEW_SCHEMA_VERSION
WS_ERR_ROLLBACK = _WS.WS_ERR_ROLLBACK
WS_ERR_DIVERGED = _WS.WS_ERR_DIVERGED
WS_ERR_INCONSISTENT = _WS.WS_ERR_INCONSISTENT
WS_ERR_CAS = _WS.WS_ERR_CAS


def _chmod_private(path: Path, mode: int = 0o600) -> None:
    return _WS._chmod_private(path, mode)


def _ensure_fleet_home() -> Path:
    return _WS._ensure_fleet_home()


def open_cache_readonly():
    return _WS.open_cache_readonly()


def open_cache_for_sync():
    return _WS.open_cache_for_sync()


planned_credential_refs = _WS.planned_credential_refs
node_schema_field_names = _WS.node_schema_field_names
RESERVED_NODE_CREDENTIAL_KEYS = _WS.RESERVED_NODE_CREDENTIAL_KEYS


_AC = _load_controller_sibling("vcl_access", "access.py")
_AC.bind(_FLEET_HOST)

SSH_USER_RE = _AC.SSH_USER_RE
SSH_USER_MAX = _AC.SSH_USER_MAX
SSH_HOST_MAX = _AC.SSH_HOST_MAX
SSH_REMOTE_CMD_MAX_BYTES = _AC.SSH_REMOTE_CMD_MAX_BYTES
SSH_TIMEOUT_SECONDS = 20
SSH_MUTATION_TIMEOUT_SECONDS = 60
SSH_BACKUP_TIMEOUT_SECONDS = 120
SSH_KEYSCAN_TIMEOUT_SECONDS = 10
SCP_TIMEOUT_SECONDS = 60


def ssh_bin() -> str:
    return _AC.ssh_bin()


def scp_bin() -> str:
    return _AC.scp_bin()


def ssh_keyscan_bin() -> str:
    return _AC.ssh_keyscan_bin()


def stdin_is_tty() -> bool:
    return _AC.stdin_is_tty()


def _ssh_option_text(arg: str) -> str:
    return _AC._ssh_option_text(arg)


def _reject_forbidden_ssh_options(argv: list[str]) -> None:
    return _AC._reject_forbidden_ssh_options(argv)


def validate_identity_file(path: str, *, must_exist: bool = True) -> str:
    return _AC.validate_identity_file(path, must_exist=must_exist)


def ssh_identity_args(identity_file: Optional[str]) -> list[str]:
    return _AC.ssh_identity_args(identity_file)


def _node_identity_file(node: dict[str, Any]) -> Optional[str]:
    return _AC._node_identity_file(node)


BINDINGS_SCHEMA_VERSION = _AC.BINDINGS_SCHEMA_VERSION
credential_bindings_path = _AC.credential_bindings_path
empty_bindings = _AC.empty_bindings
load_bindings = _AC.load_bindings
save_bindings = _AC.save_bindings
bind_identity_file = _AC.bind_identity_file
bind_openssh_default = _AC.bind_openssh_default
resolve_binding = _AC.resolve_binding
list_bindings = _AC.list_bindings
verify_bindings = _AC.verify_bindings


def ssh_argv(
    host: str,
    user: str,
    port: int,
    remote_cmd: list[str],
    *,
    batch: bool,
    extra: list[str] | None = None,
    identity_file: Optional[str] = None,
) -> list[str]:
    """Build OpenSSH argv; remote operand is shlex.join'd in access.ssh_argv."""
    return _AC.ssh_argv(
        host,
        user,
        port,
        remote_cmd,
        batch=batch,
        extra=extra,
        identity_file=identity_file,
    )


def ssh_run(
    host: str,
    user: str,
    port: int,
    remote_cmd: list[str],
    *,
    batch: bool = True,
    extra: list[str] | None = None,
    identity_file: Optional[str] = None,
    timeout: float = SSH_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return _AC.ssh_run(
        host,
        user,
        port,
        remote_cmd,
        batch=batch,
        extra=extra,
        identity_file=identity_file,
        timeout=timeout,
    )


def scp_argv(
    *,
    port: int,
    src: str,
    dest: str,
    batch: bool = True,
    extra: list[str] | None = None,
    identity_file: Optional[str] = None,
) -> list[str]:
    return _AC.scp_argv(
        port=port,
        src=src,
        dest=dest,
        batch=batch,
        extra=extra,
        identity_file=identity_file,
    )


def scp_run(
    *,
    port: int,
    src: str,
    dest: str,
    batch: bool = True,
    extra: list[str] | None = None,
    identity_file: Optional[str] = None,
    timeout: float = SCP_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return _AC.scp_run(
        port=port,
        src=src,
        dest=dest,
        batch=batch,
        extra=extra,
        identity_file=identity_file,
        timeout=timeout,
    )


def _scp_remote_spec(node: dict[str, Any], remote_path: str) -> str:
    return _AC._scp_remote_spec(node, remote_path)


def scp_pull(
    node: dict[str, Any],
    remote_path: str,
    local_path: Path,
    *,
    extra: list[str] | None = None,
    timeout: float = SCP_TIMEOUT_SECONDS,
) -> None:
    return _AC.scp_pull(
        node, remote_path, local_path, extra=extra, timeout=timeout
    )


def scp_push(
    node: dict[str, Any],
    local_path: Path,
    remote_path: str,
    *,
    extra: list[str] | None = None,
    timeout: float = SCP_TIMEOUT_SECONDS,
) -> None:
    return _AC.scp_push(
        node, local_path, remote_path, extra=extra, timeout=timeout
    )


def validate_ssh_user(user: str) -> str:
    return _AC.validate_ssh_user(user)


def validate_ssh_host(host: str) -> str:
    return _AC.validate_ssh_host(host)


_TR = _load_controller_sibling("vcl_trust", "trust.py")
_TR.bind(_FLEET_HOST)

HOST_KEY_TYPES = _TR.HOST_KEY_TYPES
HOST_KEY_FP_BODY_RE = _TR.HOST_KEY_FP_BODY_RE
NONINTERACTIVE_HOST_KEY_MSG = _TR.NONINTERACTIVE_HOST_KEY_MSG

default_known_hosts_path = _TR.default_known_hosts_path
normalize_fingerprint = _TR.normalize_fingerprint
_key_blob_from_line = _TR._key_blob_from_line
fingerprint_sha256 = _TR.fingerprint_sha256
candidate_host_keys = _TR.candidate_host_keys
append_known_hosts = _TR.append_known_hosts
pin_host_key = _TR.pin_host_key
prepare_ssh_host_key = _TR.prepare_ssh_host_key
TRUST_MIGRATION_REQUIRED = _TR.TRUST_MIGRATION_REQUIRED
extract_fleet_host_trust = _TR.extract_fleet_host_trust


def fleet_lock_path() -> Path:
    override = os.environ.get("VCL_FLEET_LOCK_FILE")
    if override:
        return Path(override)
    return fleet_home() / ".lock"


def _fleet_lock_timeout(timeout: Optional[float] = None) -> float:
    if timeout is not None:
        return float(timeout)
    env = os.environ.get("VCL_FLEET_LOCK_TIMEOUT")
    if env is not None and env != "":
        try:
            return float(env)
        except ValueError:
            die(f"invalid VCL_FLEET_LOCK_TIMEOUT: {env}")
    return float(FLEET_OP_LOCK_TIMEOUT)


def _flock_exclusive(fd: int, timeout: float) -> bool:
    """Acquire an exclusive flock/fcntl lock, polling until timeout."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            if timeout <= 0 or time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


# In-process mutex first, then cross-process flock. Reentrancy depth is
# per-thread (threading.local); a global depth would let HTTP worker
# threads skip the flock while another thread holds it.
_FLEET_THREAD_LOCK = threading.RLock()
_FLEET_LOCK_STATE = threading.local()
_FLEET_LOCK_FH: Any = None


def _thread_lock_depth() -> int:
    return int(getattr(_FLEET_LOCK_STATE, "depth", 0) or 0)


def _acquire_thread_lock(wait: float) -> bool:
    if wait > 0:
        return bool(_FLEET_THREAD_LOCK.acquire(timeout=wait))
    return bool(_FLEET_THREAD_LOCK.acquire(blocking=False))


def acquire_fleet_op_lock(timeout: Optional[float] = None) -> None:
    """Exclusive lock on $FLEET_HOME/.lock (shared by registry + fleet.db).

    Same thread may nest. A different thread in this process must wait or
    get busy; it must not treat another thread's hold as reentrant.
    """
    global _FLEET_LOCK_FH
    wait = _fleet_lock_timeout(timeout)
    started = time.monotonic()
    if not _acquire_thread_lock(wait):
        die(FLEET_BUSY_MSG, FLEET_BUSY_EXIT)
    depth = _thread_lock_depth()
    if depth > 0:
        _FLEET_LOCK_STATE.depth = depth + 1
        return
    remaining = 0.0
    if wait > 0:
        remaining = max(0.0, wait - (time.monotonic() - started))
    try:
        _ensure_fleet_home()
        path = fleet_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fh = open(path, "a+b")
        except OSError as exc:
            die(f"cannot open lock file {path}: {exc}")
        _chmod_private(path, 0o600)
        if not _flock_exclusive(fh.fileno(), remaining):
            try:
                fh.close()
            except OSError:
                pass
            die(FLEET_BUSY_MSG, FLEET_BUSY_EXIT)
        _FLEET_LOCK_FH = fh
        _FLEET_LOCK_STATE.depth = 1
    except BaseException:
        if _thread_lock_depth() == 0:
            try:
                _FLEET_THREAD_LOCK.release()
            except RuntimeError:
                pass
        raise


def release_fleet_op_lock() -> None:
    global _FLEET_LOCK_FH
    depth = _thread_lock_depth()
    if depth <= 0:
        return
    if depth > 1:
        _FLEET_LOCK_STATE.depth = depth - 1
        _FLEET_THREAD_LOCK.release()
        return
    _FLEET_LOCK_STATE.depth = 0
    fh = _FLEET_LOCK_FH
    _FLEET_LOCK_FH = None
    if fh is not None:
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            fh.close()
        except OSError:
            pass
    try:
        _FLEET_THREAD_LOCK.release()
    except RuntimeError:
        pass


@contextmanager
def fleet_op_lock(timeout: Optional[float] = None) -> Any:
    acquire_fleet_op_lock(timeout=timeout)
    try:
        yield
    finally:
        release_fleet_op_lock()


def with_fleet_op_lock(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        with fleet_op_lock():
            return fn(*args, **kwargs)

    return wrapped


def _has_meta_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    return row is not None


def fleet_db_meta_get(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row[0])


def fleet_db_meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        (key, value),
    )


def open_fleet_db() -> sqlite3.Connection:
    """Open ~/.config/vincula/fleet.db (or VCL_FLEET_HOME), creating schema 3."""
    _ensure_fleet_home()
    path = fleet_db_path()
    try:
        conn = sqlite3.connect(str(path), timeout=30)
    except sqlite3.Error as exc:
        die(f"cannot open fleet.db: {exc}")
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL").fetchone()
        conn.execute("PRAGMA synchronous=NORMAL")
        if not _has_meta_table(conn):
            conn.executescript(FLEET_DB_DDL)
            fleet_db_meta_set(
                conn, "schema_version", str(FLEET_DB_SCHEMA_VERSION)
            )
            conn.commit()
        else:
            ver = fleet_db_meta_get(conn, "schema_version")
            if ver == "1":
                _migrate_fleet_db_1_to_2(conn)
                ver = "2"
            if ver == "2":
                _migrate_fleet_db_2_to_3(conn)
            elif ver != str(FLEET_DB_SCHEMA_VERSION):
                conn.close()
                die(f"unsupported fleet-cache schema: {ver}")
        _chmod_private(path, 0o600)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(path) + suffix)
            if sidecar.is_file():
                _chmod_private(sidecar, 0o600)
        return conn
    except SystemExit:
        raise
    except sqlite3.Error as exc:
        try:
            conn.close()
        except Exception:
            pass
        die(f"cannot initialize fleet.db: {exc}")


def _migrate_fleet_db_1_to_2(conn: sqlite3.Connection) -> None:
    """CREATE instance_history only; do not rebuild schema 1 tables."""
    conn.executescript(INSTANCE_HISTORY_DDL)
    backfill_instance_history(conn, load_registry())
    fleet_db_meta_set(conn, "schema_version", "2")
    conn.commit()


def _fleet_table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in rows]


def _migrate_fleet_db_2_to_3(conn: sqlite3.Connection) -> None:
    """Add export_seq / cursor_kind. Do not reinterpret last_event_id as export_seq."""
    audit_cols = _fleet_table_columns(conn, "audit_events")
    if "export_seq" not in audit_cols:
        conn.execute("ALTER TABLE audit_events ADD COLUMN export_seq INTEGER")
    cursor_cols = _fleet_table_columns(conn, "sync_cursor")
    if "last_export_seq" not in cursor_cols:
        conn.execute(
            "ALTER TABLE sync_cursor ADD COLUMN last_export_seq "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "cursor_kind" not in cursor_cols:
        # Existing cursors stay event_id until operator reseeds.
        conn.execute(
            "ALTER TABLE sync_cursor ADD COLUMN cursor_kind "
            "TEXT NOT NULL DEFAULT 'event_id'"
        )
    fleet_db_meta_set(conn, "schema_version", str(FLEET_DB_SCHEMA_VERSION))
    conn.commit()

def insert_instance(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    instance_id: str,
    started_at: str,
    endpoint: Optional[str] = None,
    ssh_host: Optional[str] = None,
    status: str = INSTANCE_STATUS_ACTIVE,
    retired_at: Optional[str] = None,
) -> None:
    validate_node_id(node_id)
    if not isinstance(instance_id, str) or not UUID_RE.fullmatch(instance_id):
        die(f"invalid instance_id: {instance_id}")
    if instance_id == node_id:
        die("instance_id must not equal node_id")
    if status not in INSTANCE_STATUSES:
        die(f"invalid instance_history status: {status}")
    conn.execute(
        """
        INSERT INTO instance_history (
          node_id, instance_id, started_at, retired_at, endpoint, ssh_host, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            node_id,
            instance_id,
            started_at,
            retired_at,
            _optional_text(endpoint),
            _optional_text(ssh_host),
            status,
        ),
    )


def retire_active_instance(
    conn: sqlite3.Connection,
    node_id: str,
    retired_at: Optional[str] = None,
    now: Optional[str] = None,
) -> None:
    """Mark every active instance for node_id as retired."""
    validate_node_id(node_id)
    ts = retired_at or now or format_utc(datetime.now(timezone.utc))
    rows = conn.execute(
        """
        SELECT node_id, instance_id, started_at, endpoint
        FROM instance_history
        WHERE node_id = ? AND status = ?
        """,
        (node_id, INSTANCE_STATUS_ACTIVE),
    ).fetchall()
    conn.execute(
        """
        UPDATE instance_history
        SET status = ?, retired_at = ?
        WHERE node_id = ? AND status = ?
        """,
        (INSTANCE_STATUS_RETIRED, ts, node_id, INSTANCE_STATUS_ACTIVE),
    )
    for row in rows:
        append_instance_history_line(
            {
                "node_id": row["node_id"],
                "instance_id": row["instance_id"],
                "started_at": row["started_at"],
                "retired_at": ts,
                "endpoint": row["endpoint"],
                "reason": "retired",
            }
        )


def mark_instance_retired(
    conn: sqlite3.Connection,
    node_id: str,
    instance_id: str,
    retired_at: Optional[str] = None,
) -> None:
    """Retire one (node_id, instance_id) row if it is still active."""
    validate_node_id(node_id)
    ts = retired_at or format_utc(datetime.now(timezone.utc))
    row = conn.execute(
        """
        SELECT node_id, instance_id, started_at, endpoint
        FROM instance_history
        WHERE node_id = ? AND instance_id = ? AND status = ?
        """,
        (node_id, instance_id, INSTANCE_STATUS_ACTIVE),
    ).fetchone()
    conn.execute(
        """
        UPDATE instance_history
        SET status = ?, retired_at = ?
        WHERE node_id = ? AND instance_id = ? AND status = ?
        """,
        (INSTANCE_STATUS_RETIRED, ts, node_id, instance_id, INSTANCE_STATUS_ACTIVE),
    )
    if row is not None:
        append_instance_history_line(
            {
                "node_id": row["node_id"],
                "instance_id": row["instance_id"],
                "started_at": row["started_at"],
                "retired_at": ts,
                "endpoint": row["endpoint"],
                "reason": "retired",
            }
        )


def record_instance(
    conn: sqlite3.Connection,
    node_id: str,
    instance_id: str,
    endpoint: Optional[str] = None,
    ssh_host: Optional[str] = None,
    *,
    now_iso: Optional[str] = None,
) -> None:
    """INSERT on first sight. A new instance retires the previous active row."""
    iid = _optional_text(instance_id)
    if iid is None:
        return
    if not UUID_RE.fullmatch(iid):
        return
    if iid == node_id:
        die("instance_id must not equal node_id")
    existing = conn.execute(
        """
        SELECT 1 FROM instance_history
        WHERE node_id = ? AND instance_id = ?
        """,
        (node_id, iid),
    ).fetchone()
    if existing is not None:
        return
    ts = now_iso or format_utc(datetime.now(timezone.utc))
    retire_active_instance(conn, node_id, retired_at=ts)
    insert_instance(
        conn,
        node_id=node_id,
        instance_id=iid,
        started_at=ts,
        endpoint=endpoint,
        ssh_host=ssh_host,
        status=INSTANCE_STATUS_ACTIVE,
    )
    append_instance_history_line(
        {
            "node_id": node_id,
            "instance_id": iid,
            "started_at": ts,
            "retired_at": None,
            "endpoint": _optional_text(endpoint) or _optional_text(ssh_host),
            "reason": "sync-first-sight",
        }
    )


def list_instances(
    conn: sqlite3.Connection, node_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT node_id, instance_id, started_at, retired_at,
               endpoint, ssh_host, status
        FROM instance_history
        WHERE node_id = ?
        ORDER BY started_at ASC, rowid ASC
        """,
        (node_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def backfill_instance_history(
    conn: sqlite3.Connection, registry: dict[str, Any]
) -> None:
    """Schema 1→2: one active row per sync_cursor with a real instance_id."""
    now = format_utc(datetime.now(timezone.utc))
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in registry.get("nodes") or []:
        if isinstance(node, dict) and node.get("node_id"):
            nodes_by_id[str(node["node_id"])] = node
    cursors = conn.execute(
        "SELECT node_id, instance_id, last_sync_at FROM sync_cursor"
    ).fetchall()
    for row in cursors:
        node_id = str(row["node_id"])
        instance_id = _optional_text(row["instance_id"])
        if instance_id is None:
            continue
        if not UUID_RE.fullmatch(node_id) or not UUID_RE.fullmatch(instance_id):
            continue
        if instance_id == node_id:
            continue
        started = _optional_text(row["last_sync_at"]) or now
        ssh_host = _optional_text((nodes_by_id.get(node_id) or {}).get("ssh_host"))
        insert_instance(
            conn,
            node_id=node_id,
            instance_id=instance_id,
            started_at=started,
            ssh_host=ssh_host,
            status=INSTANCE_STATUS_ACTIVE,
        )


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_default(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _row_node_id(row: Any) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    return _optional_text(row.get("node_id"))


def _audit_insert_params(
    row: dict[str, Any], node_id: str, now_iso: str
) -> tuple[Any, ...]:
    event_id = row.get("event_id")
    connection_id = _optional_text(row.get("connection_id"))
    user_id = _optional_text(row.get("user_id"))
    started_at = _optional_text(row.get("started_at"))
    last_seen_at = _optional_text(row.get("last_seen_at"))
    if event_id is None or event_id == "":
        die("audit import row missing event_id")
    if not connection_id:
        die("audit import row missing connection_id")
    if not user_id:
        die("audit import row missing user_id")
    if not started_at:
        die("audit import row missing started_at")
    if not last_seen_at:
        die("audit import row missing last_seen_at")
    try:
        event_id_i = int(event_id)
        generation = _int_or_default(row.get("generation"), 0)
        dest_port = _int_or_none(row.get("destination_port"))
        upload_bytes = _int_or_default(row.get("upload_bytes"), 0)
        download_bytes = _int_or_default(row.get("download_bytes"), 0)
        export_seq = row.get("export_seq")
        if export_seq is None or export_seq == "":
            die("audit import row missing export_seq")
        export_seq_i = int(export_seq)
    except (TypeError, ValueError) as exc:
        die(f"audit import row has invalid numeric field: {exc}")
    return (
        node_id,
        _optional_text(row.get("instance_id")),
        event_id_i,
        export_seq_i,
        connection_id,
        generation,
        user_id,
        _optional_text(row.get("user_tag")),
        started_at,
        last_seen_at,
        _optional_text(row.get("closed_at")),
        _optional_text(row.get("destination_host")),
        _optional_text(row.get("destination_ip")),
        dest_port,
        _optional_text(row.get("network")),
        upload_bytes,
        download_bytes,
        now_iso,
    )


def rebuild_daily_usage_for_node(conn: sqlite3.Connection, node_id: str) -> None:
    """Rebuild daily_usage for one node from its audit_events (durable imports)."""
    conn.execute("DELETE FROM daily_usage WHERE node_id = ?", (node_id,))
    conn.execute(
        """
        INSERT INTO daily_usage (
          date, node_id, instance_id, user_id, user_tag, destination_host,
          upload_bytes, download_bytes, connection_count
        )
        SELECT
          substr(started_at, 1, 10) AS date,
          node_id,
          MAX(instance_id),
          user_id,
          MAX(user_tag),
          CASE
            WHEN destination_host IS NOT NULL AND destination_host != ''
              THEN destination_host
            WHEN destination_ip IS NOT NULL AND destination_ip != ''
              THEN destination_ip
            ELSE '(unknown)'
          END AS destination_host,
          SUM(upload_bytes),
          SUM(download_bytes),
          COUNT(*)
        FROM audit_events
        WHERE node_id = ?
          AND node_id IS NOT NULL
          AND node_id != ''
        GROUP BY
          substr(started_at, 1, 10),
          node_id,
          user_id,
          CASE
            WHEN destination_host IS NOT NULL AND destination_host != ''
              THEN destination_host
            WHEN destination_ip IS NOT NULL AND destination_ip != ''
              THEN destination_ip
            ELSE '(unknown)'
          END
        """,
        (node_id,),
    )


def _cursor_last_export_seq(conn: sqlite3.Connection, node_id: str) -> int:
    row = conn.execute(
        "SELECT last_export_seq FROM sync_cursor WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def _cursor_last_event_id(conn: sqlite3.Connection, node_id: str) -> int:
    row = conn.execute(
        "SELECT last_event_id FROM sync_cursor WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _cursor_kind(conn: sqlite3.Connection, node_id: str) -> Optional[str]:
    row = conn.execute(
        "SELECT cursor_kind FROM sync_cursor WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    if row is None:
        return None
    return _optional_text(row[0])


def import_audit_batch(
    node_id: str,
    instance_id: Optional[str],
    rows: Sequence[Any],
    now_iso: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    next_cursor: Optional[int] = None,
) -> dict[str, Any]:
    """Atomically import audit rows for one node. UPSERT on (node_id, event_id).

    Every row must carry a node_id that matches the batch node_id. Unlabeled
    rows fail the whole import and leave the cursor unchanged. A labeled
    row whose node_id does not match also fails closed. When next_cursor is
    set (sync path), last_export_seq is written to that remote-declared value.
    """
    validate_node_id(node_id)
    inst = _optional_text(instance_id)
    if inst is not None:
        if not UUID_RE.fullmatch(inst):
            die(f"invalid instance_id: {inst}")
        if inst == node_id:
            die("refusing audit import: instance_id equals node_id")
    if now_iso is None:
        now_iso = format_utc(datetime.now(timezone.utc))

    labeled: list[dict[str, Any]] = []
    for row in rows:
        row_nid = _row_node_id(row)
        if row_nid is None:
            die("refusing audit import: row missing node_id")
        if row_nid != node_id:
            die(
                "audit import node_id mismatch: "
                f"expected {node_id}, got {row_nid}"
            )
        labeled.append(row)

    own = conn is None
    if own:
        conn = open_fleet_db()
    assert conn is not None
    try:
        existing_ids: set[int] = set()
        if labeled:
            eids = []
            for row in labeled:
                try:
                    eids.append(int(row.get("event_id")))
                except (TypeError, ValueError):
                    die("audit import row has invalid event_id")
            q = ",".join("?" * len(eids))
            found = conn.execute(
                f"SELECT event_id FROM audit_events "
                f"WHERE node_id = ? AND event_id IN ({q})",
                (node_id, *eids),
            ).fetchall()
            existing_ids = {int(r[0]) for r in found}
        prior_cursor = _cursor_last_export_seq(conn, node_id)
        prior_event = _cursor_last_event_id(conn, node_id)
        params = [
            _audit_insert_params(row, node_id, now_iso) for row in labeled
        ]
        if next_cursor is not None and (
            isinstance(next_cursor, bool)
            or not isinstance(next_cursor, int)
            or next_cursor < 0
        ):
            die("invalid next_cursor")
        try:
            conn.execute("BEGIN IMMEDIATE")
            if params:
                conn.executemany(INSERT_AUDIT_EVENT_SQL, params)
            rebuild_daily_usage_for_node(conn, node_id)
            if next_cursor is not None:
                last_export_seq = next_cursor
            else:
                max_row = conn.execute(
                    "SELECT MAX(export_seq) FROM audit_events WHERE node_id = ?",
                    (node_id,),
                ).fetchone()
                if max_row is None or max_row[0] is None:
                    last_export_seq = prior_cursor
                else:
                    last_export_seq = int(max_row[0])
            max_eid_row = conn.execute(
                "SELECT MAX(event_id) FROM audit_events WHERE node_id = ?",
                (node_id,),
            ).fetchone()
            if max_eid_row is None or max_eid_row[0] is None:
                last_event_id = prior_event
            else:
                last_event_id = int(max_eid_row[0])
            conn.execute(
                """
                INSERT OR REPLACE INTO sync_cursor (
                  node_id, instance_id, last_event_id, last_export_seq,
                  cursor_kind, last_sync_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    inst,
                    last_event_id,
                    last_export_seq,
                    CURSOR_KIND_EXPORT_SEQ,
                    now_iso,
                    SYNC_STATUS_OK,
                ),
            )
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        inserted = 0
        updated = 0
        for row in labeled:
            eid = int(row.get("event_id"))
            if eid in existing_ids:
                updated += 1
            else:
                inserted += 1
        return {
            "ok": True,
            "inserted": inserted,
            "updated": updated,
            "ignored": 0,
            "skipped_unlabeled": 0,
            "last_event_id": last_event_id,
            "last_export_seq": last_export_seq,
            "status": SYNC_STATUS_OK,
        }
    finally:
        if own:
            conn.close()


def import_export_jsonl(
    node_id: str,
    instance_id: Optional[str],
    rows: Sequence[Any],
    now_iso: str,
    conn: Optional[sqlite3.Connection] = None,
    next_cursor: Optional[int] = None,
) -> dict[str, Any]:
    """Import a node audit-export JSONL batch and advance the sync cursor."""
    return import_audit_batch(
        node_id,
        instance_id,
        rows,
        now_iso=now_iso,
        conn=conn,
        next_cursor=next_cursor,
    )


def parse_export_jsonl(text: str) -> list[dict[str, Any]]:
    """Parse audit-export JSONL (one object per line). Blank lines skipped."""
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate((text or "").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSONL line {lineno} is not JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"JSONL line {lineno} is not an object")
        rows.append(obj)
    return rows


def parse_export_meta(stderr: str) -> Optional[dict[str, Any]]:
    """Last JSON object on stderr is the export meta contract."""
    for line in reversed((stderr or "").splitlines()):
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and (
            "after" in obj or "error" in obj or "ok" in obj
        ):
            return obj
    return None


def _require_export_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"export meta {name} is not an int")
    return value


def validate_export_batch(
    meta: Optional[dict[str, Any]],
    rows: Sequence[Any],
    *,
    expected_after: int,
    expected_node_id: str,
    expected_instance_id: Optional[str] = None,
) -> int:
    """Validate Protocol v2 export meta against delivered JSONL.

    Returns the remote next_cursor (export_seq). Any mismatch raises
    ValueError; the caller must not import or advance the cursor.
    Requires strictly increasing unique export_seq (gaps allowed).
    """
    if not isinstance(meta, dict):
        raise ValueError("missing export meta")
    if meta.get("ok") is not True:
        raise ValueError("export meta ok is not true")
    err = meta.get("error")
    if err:
        raise ValueError(f"export meta error={err}")

    protocol = meta.get("protocol_version")
    if protocol != EXPORT_PROTOCOL_VERSION:
        raise ValueError(
            f"export protocol_version={protocol!r} != {EXPORT_PROTOCOL_VERSION}"
        )
    cursor_kind = _optional_text(meta.get("cursor_kind"))
    if cursor_kind != CURSOR_KIND_EXPORT_SEQ:
        raise ValueError(
            f"export cursor_kind={cursor_kind!r} != {CURSOR_KIND_EXPORT_SEQ}"
        )

    meta_after = _require_export_int(meta.get("after"), "after")
    if meta_after != expected_after:
        raise ValueError(
            f"export meta after={meta_after} != cursor {expected_after}"
        )

    delivered = list(rows)
    count = _require_export_int(meta.get("count"), "count")
    if count != len(delivered):
        raise ValueError(
            f"export meta count={count} != delivered {len(delivered)}"
        )
    if count < 0:
        raise ValueError("export meta count is negative")

    meta_nid = _optional_text(meta.get("node_id"))
    if meta_nid is None:
        raise ValueError("export meta node_id is missing")
    if meta_nid != expected_node_id:
        raise ValueError(
            f"export meta node_id={meta_nid} != {expected_node_id}"
        )
    meta_iid = _optional_text(meta.get("instance_id"))
    if expected_instance_id:
        if meta_iid is None:
            raise ValueError("export meta instance_id is missing")
        if meta_iid != expected_instance_id:
            raise ValueError(
                f"export meta instance_id={meta_iid} != {expected_instance_id}"
            )

    export_seqs: list[int] = []
    seen_seqs: set[int] = set()
    for i, row in enumerate(delivered):
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row {i} is not an object")
        eid = row.get("event_id")
        if isinstance(eid, bool) or not isinstance(eid, int):
            raise ValueError(f"JSONL row {i} event_id is not an int")
        eseq = row.get("export_seq")
        if isinstance(eseq, bool) or not isinstance(eseq, int):
            raise ValueError(f"JSONL row {i} export_seq is not an int")
        if eseq <= expected_after:
            raise ValueError(
                f"JSONL row {i} export_seq={eseq} <= after {expected_after}"
            )
        if eseq in seen_seqs:
            raise ValueError(f"duplicate export_seq {eseq}")
        seen_seqs.add(eseq)
        if export_seqs and eseq <= export_seqs[-1]:
            raise ValueError(
                f"export_seq not strictly increasing: {export_seqs[-1]} → {eseq}"
            )
        export_seqs.append(eseq)

        row_nid = _row_node_id(row)
        if row_nid is None:
            raise ValueError(f"JSONL row {i} node_id is missing")
        if row_nid != expected_node_id:
            raise ValueError(
                f"JSONL row {i} node_id={row_nid} != {expected_node_id}"
            )

    if export_seqs:
        max_export_seq = meta.get("max_export_seq")
        if max_export_seq is not None:
            max_i = _require_export_int(max_export_seq, "max_export_seq")
            if export_seqs[-1] > max_i:
                raise ValueError("row export_seq exceeds meta max_export_seq")

    next_cursor = _require_export_int(meta.get("next_cursor"), "next_cursor")
    if export_seqs:
        if next_cursor != export_seqs[-1]:
            raise ValueError(
                f"export meta next_cursor={next_cursor} != "
                f"last export_seq {export_seqs[-1]}"
            )
    elif next_cursor != expected_after:
        raise ValueError(
            f"export meta next_cursor={next_cursor} != after "
            f"{expected_after} (empty batch)"
        )
    return next_cursor


def read_sync_cursor_row(
    conn: sqlite3.Connection, node_id: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT instance_id, last_event_id, last_export_seq, cursor_kind,
               last_sync_at, status
        FROM sync_cursor WHERE node_id = ?
        """,
        (node_id,),
    ).fetchone()


def write_sync_cursor(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    instance_id: Optional[str],
    last_event_id: int,
    status: str,
    now_iso: str,
    last_export_seq: Optional[int] = None,
    cursor_kind: Optional[str] = None,
) -> None:
    kind = cursor_kind or CURSOR_KIND_EXPORT_SEQ
    export_seq = 0 if last_export_seq is None else int(last_export_seq)
    with fleet_op_lock():
        conn.execute(
            """
            INSERT OR REPLACE INTO sync_cursor (
              node_id, instance_id, last_event_id, last_export_seq,
              cursor_kind, last_sync_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                instance_id,
                last_event_id,
                export_seq,
                kind,
                now_iso,
                status,
            ),
        )


def mark_cursor_status(
    conn: sqlite3.Connection,
    node_id: str,
    *,
    instance_id: Optional[str],
    status: str,
    now_iso: str,
) -> int:
    """Set cursor status without advancing last_export_seq. Returns that seq."""
    last_export_seq = _cursor_last_export_seq(conn, node_id)
    last_event_id = _cursor_last_event_id(conn, node_id)
    row = read_sync_cursor_row(conn, node_id)
    inst = instance_id
    kind = CURSOR_KIND_EXPORT_SEQ
    if inst is None and row is not None:
        inst = row["instance_id"]
    if row is not None:
        kind = _optional_text(row["cursor_kind"]) or kind
    write_sync_cursor(
        conn,
        node_id=node_id,
        instance_id=inst,
        last_event_id=last_event_id,
        last_export_seq=last_export_seq,
        cursor_kind=kind,
        status=status,
        now_iso=now_iso,
    )
    return last_export_seq


def reseed_node_local(
    conn: sqlite3.Connection,
    node_id: str,
    *,
    instance_id: Optional[str] = None,
    now_iso: Optional[str] = None,
) -> None:
    """Drop local audit/daily rows for node_id and reset export_seq cursor to 0."""
    validate_node_id(node_id)
    if now_iso is None:
        now_iso = format_utc(datetime.now(timezone.utc))
    with fleet_op_lock():
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM audit_events WHERE node_id = ?", (node_id,))
            conn.execute("DELETE FROM daily_usage WHERE node_id = ?", (node_id,))
            write_sync_cursor(
                conn,
                node_id=node_id,
                instance_id=instance_id,
                last_event_id=0,
                last_export_seq=0,
                cursor_kind=CURSOR_KIND_EXPORT_SEQ,
                status=SYNC_STATUS_OK,
                now_iso=now_iso,
            )
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise


def remediation_sync_reseed(name: str) -> str:
    return f"vcl-fleet sync --reseed {name}"


def remediation_protocol_mismatch(name: str) -> str:
    return (
        f"CURSOR_PROTOCOL_MISMATCH: event_id → export_seq; "
        f"run: {remediation_sync_reseed(name)}"
    )

def _is_host_key_failure(detail: str) -> bool:
    text = detail.lower()
    return (
        "authenticity of host" in text
        or "host key verification failed" in text
        or "remote host identification has changed" in text
    )


def _host_key_guidance(user: str, host: str) -> str:
    return (
        f"first connect to {user}@{host} requires interactive confirmation "
        f"(run: ssh {user}@{host}) or --host-key SHA256:..."
    )


def parse_identity_json(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        die(f"remote identity is not JSON: {exc}")
    if not isinstance(data, dict):
        die("remote identity JSON must be an object")
    node_id = data.get("node_id")
    if not isinstance(node_id, str) or not UUID_RE.fullmatch(node_id):
        die(f"invalid node_id: {node_id}")
    instance_id = data.get("instance_id")
    if instance_id not in (None, ""):
        if not isinstance(instance_id, str) or not UUID_RE.fullmatch(instance_id):
            die(f"invalid instance_id: {instance_id}")
        if instance_id == node_id:
            die("refusing to register: instance_id equals node_id")
    return data


def _ssh_failure_detail(proc: subprocess.CompletedProcess[str]) -> str:
    err = (proc.stderr or "").strip()
    if err:
        return err
    out = (proc.stdout or "").strip()
    if out:
        return out
    return f"exit {proc.returncode}"


def empty_registry() -> dict[str, Any]:
    return _WS.empty_registry()


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in FORBIDDEN_NODE_KEYS or lowered.endswith("password")


def _has_ascii_control(value: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in value)


def _user_metadata_error(value: str, field: str) -> Optional[str]:
    if not isinstance(value, str):
        return f"invalid {field}: must be a string"
    if _has_ascii_control(value):
        return f"invalid {field}: control characters are not allowed"
    if len(value) > USER_METADATA_MAX:
        return f"invalid {field}: exceeds {USER_METADATA_MAX} characters"
    return None


def validate_display_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    err = _user_metadata_error(value, "display_name")
    if err:
        die(err)
    return value


def validate_department(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    err = _user_metadata_error(value, "department")
    if err:
        die(err)
    return value


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
    validate_ssh_user(ssh_user)
    validate_ssh_host(raw)
    return raw, ssh_user, ssh_port


def validate_node_id(node_id: str) -> None:
    if not isinstance(node_id, str) or not UUID_RE.fullmatch(node_id):
        die(f"invalid node_id: {node_id}")


def validate_name(name: str) -> None:
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        die(f"invalid name: {name}")


def node_lifecycle_status(node: dict[str, Any]) -> str:
    """Return active|disabled|retired. Schema 1 records have no status."""
    status = node.get("status")
    if status in NODE_STATUSES:
        return str(status)
    return NODE_STATUS_ACTIVE if node.get("enabled", True) else NODE_STATUS_DISABLED


def node_is_active(node: dict[str, Any]) -> bool:
    return node_lifecycle_status(node) == NODE_STATUS_ACTIVE


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
    ssh_host = validate_ssh_host(ssh_host.strip())
    ssh_user = validate_ssh_user(ssh_user.strip())
    if isinstance(ssh_port, bool) or not isinstance(ssh_port, int) or not (1 <= ssh_port <= 65535):
        die(f"invalid ssh_port: {ssh_port}")
    if not isinstance(enabled, bool):
        die(f"invalid enabled: {enabled}")
    status = raw.get("status")
    if status is None:
        status = NODE_STATUS_ACTIVE if enabled else NODE_STATUS_DISABLED
    if not isinstance(status, str) or status not in NODE_STATUSES:
        die(f"invalid status: {status}")
    enabled = status == NODE_STATUS_ACTIVE
    identity_file = None
    identity_raw = raw.get("identity_file")
    if identity_raw is not None and identity_raw != "":
        if not isinstance(identity_raw, str):
            die(f"invalid identity_file: {identity_raw}")
        identity_file = validate_identity_file(identity_raw, must_exist=False)
    record = {
        "node_id": node_id,
        "name": name,
        "ssh_host": ssh_host,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
        "enabled": enabled,
        "status": status,
    }
    if identity_file:
        record["identity_file"] = identity_file
    ar, obr = raw.get("admin_credential_ref"), raw.get("observe_credential_ref")
    if ar is not None and ar != "":
        if not isinstance(ar, str) or not ar.strip():
            die(f"nodes[{index}] invalid admin_credential_ref: {ar}")
        record["admin_credential_ref"] = ar.strip()
    if obr is not None and obr != "":
        if not isinstance(obr, str) or not obr.strip():
            die(f"nodes[{index}] invalid observe_credential_ref: {obr}")
        record["observe_credential_ref"] = obr.strip()
    elif record.get("admin_credential_ref"):
        record["observe_credential_ref"] = record["admin_credential_ref"]  # observe=admin
    return record


def validate_registry(data: Any) -> dict[str, Any]:
    return _WS.validate_registry(data)


def load_registry(path: Optional[Path] = None) -> dict[str, Any]:
    return _WS.load_registry(path)


def save_registry(path: Optional[Path], registry: dict[str, Any]) -> None:
    with fleet_op_lock():
        return _WS._save_registry_unlocked(path, registry)


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
    identity_file: Optional[str] = None,
    enabled: bool = True,
) -> dict[str, Any]:
    validate_node_id(node_id)
    validate_name(name)
    if find_by_node_id(registry, node_id) is not None:
        die(f"duplicate node_id: {node_id}")
    if find_by_name(registry, name) is not None:
        die(f"duplicate name: {name}")
    payload: dict[str, Any] = {
        "node_id": node_id,
        "name": name,
        "ssh_host": ssh_host,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
        "enabled": enabled,
    }
    if identity_file:
        payload["identity_file"] = identity_file
    record = normalize_node(
        payload,
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
    if node_lifecycle_status(node) == NODE_STATUS_RETIRED:
        if enabled:
            die("retired node cannot be enabled; replacement is 0.3.0")
        die(f"node is retired: {name}")
    if enabled:
        node["status"] = NODE_STATUS_ACTIVE
        node["enabled"] = True
    else:
        node["status"] = NODE_STATUS_DISABLED
        node["enabled"] = False
    return node


@with_fleet_op_lock
def cmd_init() -> int:
    path = fleet_registry_path()
    if path.is_file():
        existing = load_registry(path)
        if existing.get("nodes"):
            die(f"fleet registry already exists with nodes: {path}")
    save_registry(path, empty_registry())
    sys.stdout.write(f"Initialized fleet registry at {path}\n")
    return 0


@with_fleet_op_lock
def cmd_node_add(args: argparse.Namespace) -> int:
    ssh_host, ssh_user, ssh_port = parse_ssh_target(args.host, args.user, args.port)
    identity_file = None
    raw_ident = _optional_text(getattr(args, "identity_file", None))
    if raw_ident:
        identity_file = validate_identity_file(raw_ident, must_exist=True)
    if args.offline:
        if not args.node_id:
            die("--offline requires --node-id UUID", 2)
        node_id = args.node_id
    else:
        extra, batch = prepare_ssh_host_key(
            ssh_host, ssh_port, getattr(args, "host_key", None)
        )
        proc = ssh_run(
            ssh_host,
            ssh_user,
            ssh_port,
            ["vcl", "identity", "--json"],
            batch=batch,
            extra=extra,
            identity_file=identity_file,
        )
        if proc.returncode != 0:
            detail = _ssh_failure_detail(proc)
            if _is_host_key_failure(detail):
                die(
                    f"SSH host key not accepted for {ssh_user}@{ssh_host}: "
                    f"{detail}\n{_host_key_guidance(ssh_user, ssh_host)}"
                )
            die(f"SSH failed for {ssh_user}@{ssh_host}: {detail}")
        ident = parse_identity_json(proc.stdout)
        node_id = ident["node_id"]
        if args.node_id and args.node_id != node_id:
            die(f"remote node_id {node_id} does not match --node-id {args.node_id}")
    registry = load_registry()
    add_node(
        registry,
        node_id=node_id,
        name=args.name,
        ssh_host=ssh_host,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
        identity_file=identity_file,
    )
    save_registry(None, registry)
    sys.stdout.write(f"Registered {args.name}\n")
    return 0


def cmd_node_list() -> int:
    registry = load_registry()
    sys.stdout.write("NAME NODE_ID SSH_HOST USER ENABLED STATUS\n")
    for node in registry.get("nodes") or []:
        enabled = "true" if node["enabled"] else "false"
        status = node_lifecycle_status(node)
        sys.stdout.write(
            f"{node['name']} {node['node_id']} {node['ssh_host']} "
            f"{node['ssh_user']} {enabled} {status}\n"
        )
    return 0


def cmd_node_show(name: str) -> int:
    node = require_node(load_registry(), name)
    for key in NODE_KEYS:
        value = node.get(key)
        if value is None or value == "":
            if key == "identity_file":
                continue
            value = "-"
        if isinstance(value, bool):
            value = "true" if value else "false"
        sys.stdout.write(f"{key}={value}\n")
    return 0


@with_fleet_op_lock
def cmd_node_set(args: argparse.Namespace) -> int:
    """Endpoint rebind and/or local SSH identity_file."""
    identity_raw = _optional_text(getattr(args, "identity_file", None))
    clear_identity = bool(getattr(args, "clear_identity_file", False))
    host = _optional_text(getattr(args, "host", None))
    if identity_raw and clear_identity:
        die("use either --identity-file or --clear-identity-file")
    if not host and not identity_raw and not clear_identity:
        die("node set requires --host and/or --identity-file/--clear-identity-file")
    registry = load_registry()
    if host:
        set_host(registry, args.name, host, user=args.user, port=args.port)
    node = require_node(registry, args.name)
    if clear_identity:
        node.pop("identity_file", None)
    elif identity_raw:
        node["identity_file"] = validate_identity_file(identity_raw, must_exist=True)
    save_registry(None, registry)
    sys.stdout.write(f"Updated {args.name}\n")
    return 0


@with_fleet_op_lock
def cmd_node_enable(name: str, enabled: bool) -> int:
    registry = load_registry()
    set_enabled(registry, name, enabled)
    save_registry(None, registry)
    node = require_node(registry, name)
    state = "enabled" if enabled else "disabled"
    sys.stdout.write(f"{name} {state} status={node_lifecycle_status(node)}\n")
    return 0


def _retire_skip_sync() -> bool:
    return os.environ.get(RETIRE_SKIP_SYNC_ENV, "").strip() == "1"


def retired_snapshot_dir(name: str) -> Path:
    return fleet_home() / "retired" / name


def ssh_uninstall_hint(node: dict[str, Any]) -> str:
    user = node["ssh_user"]
    host = node["ssh_host"]
    port = int(node.get("ssh_port") or 22)
    if port == 22:
        return f"ssh {user}@{host} -- sudo vcl uninstall --yes"
    return f"ssh -p {port} {user}@{host} -- sudo vcl uninstall --yes"


def _cursor_snapshot(node: dict[str, Any]) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "node_id": node["node_id"],
        "instance_id": None,
        "last_event_id": 0,
        "last_export_seq": 0,
        "cursor_kind": CURSOR_KIND_EXPORT_SEQ,
        "last_sync_at": None,
        "status": None,
    }
    conn = open_fleet_db()
    try:
        row = read_sync_cursor_row(conn, node["node_id"])
    finally:
        conn.close()
    if row is None:
        return doc
    doc["instance_id"] = row["instance_id"]
    doc["last_event_id"] = int(row["last_event_id"])
    doc["last_export_seq"] = int(row["last_export_seq"] or 0)
    doc["cursor_kind"] = (
        _optional_text(row["cursor_kind"]) or CURSOR_KIND_EXPORT_SEQ
    )
    doc["last_sync_at"] = row["last_sync_at"]
    doc["status"] = row["status"]
    return doc


def _last_status_slice(name: str) -> Optional[dict[str, Any]]:
    path = last_status_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for rec in data.get("nodes") or []:
        if isinstance(rec, dict) and rec.get("name") == name:
            return rec
    return None


def write_retire_snapshot(
    node: dict[str, Any],
    *,
    identity: Optional[dict[str, Any]],
    last_status: Optional[dict[str, Any]],
) -> Path:
    dest = retired_snapshot_dir(node["name"])
    dest.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(dest.parent, 0o700)
    except OSError:
        pass
    try:
        os.chmod(dest, 0o700)
    except OSError:
        pass
    write_private_file(
        dest / "identity.json",
        json.dumps(
            identity if isinstance(identity, dict) else {},
            indent=2,
            ensure_ascii=False,
        ),
    )
    write_private_file(
        dest / "cursor.json",
        json.dumps(_cursor_snapshot(node), indent=2, ensure_ascii=False),
    )
    slice_doc = last_status if isinstance(last_status, dict) else {}
    write_private_file(
        dest / "last-status.json",
        json.dumps(slice_doc, indent=2, ensure_ascii=False),
    )
    hint = ssh_uninstall_hint(node)
    readme = (
        f"Node {node['name']} ({node['node_id']}) was retired by vcl-fleet.\n"
        "The node was not uninstalled. Historical audit rows remain in fleet.db.\n"
        "This directory is a final-state record (identity, sync cursor, last status),\n"
        "not a 0.3.0 backup/snapshot.\n"
        "\n"
        f"Optional uninstall on the node:\n"
        f"  {hint}\n"
    )
    write_private_file(dest / "README.txt", readme)
    return dest


def disable_remote_users_except_last(
    node: dict[str, Any],
) -> tuple[list[str], Optional[str], Optional[str]]:
    """Disable every enabled user except the last (tag-sorted). Node invariant."""
    users, err = _list_users_on_node(node)
    if err is not None:
        return [], None, err
    enabled = sorted(
        [u for u in (users or []) if u.get("enabled")],
        key=lambda u: str(u.get("tag") or ""),
    )
    if not enabled:
        return [], None, None
    keep_tag = str(enabled[-1].get("tag") or "") or None
    disabled: list[str] = []
    errors: list[str] = []
    for user in enabled[:-1]:
        tag = str(user.get("tag") or "")
        if not tag:
            continue
        ssh_state, payload, detail = ssh_remote_json(
            node,
            ["vcl", "user", "disable", tag, "--json"],
            timeout=SSH_MUTATION_TIMEOUT_SECONDS,
            require_exit_0=True,
        )
        ok = (
            ssh_state == "OK"
            and isinstance(payload, dict)
            and payload.get("ok") is True
        )
        if ok:
            disabled.append(tag)
            continue
        errors.append(f"{tag}: {detail or 'disable failed'}")
    err_s = "; ".join(errors) if errors else None
    return disabled, keep_tag, err_s


def _run_final_sync(node: dict[str, Any], *, write_table: bool = True) -> dict[str, Any]:
    """Same machinery as `vcl-fleet sync --node NAME` for one node."""
    now_iso = format_utc(datetime.now(timezone.utc))
    conn = open_fleet_db()
    try:
        row = sync_one_node(conn, node, now_iso=now_iso)
    finally:
        conn.close()
    if write_table:
        sys.stdout.write(format_sync_table([row]))
    return row


@with_fleet_op_lock
def cmd_node_retire(name: str) -> int:
    validate_name(name)
    registry = load_registry()
    node = require_node(registry, name)
    if node_lifecycle_status(node) == NODE_STATUS_RETIRED:
        die(f"node already retired: {name}")

    skip_sync = _retire_skip_sync()
    identity: Optional[dict[str, Any]] = None
    if skip_sync:
        sys.stderr.write(
            f"WARNING: skipping final sync for {name} "
            f"({RETIRE_SKIP_SYNC_ENV}=1); AC-2.9-08 is not satisfied "
            "on this path\n"
        )
        ssh_state, ident, _detail = ssh_remote_json(
            node, ["vcl", "identity", "--json"]
        )
        if ssh_state == "OK" and isinstance(ident, dict):
            identity = ident
    else:
        if not node_is_active(node):
            die(
                f"cannot retire {name}: final sync requires an active node "
                "(unreachable or disabled nodes cannot be retired)"
            )
        ssh_state, ident, ident_detail = ssh_remote_json(
            node, ["vcl", "identity", "--json"]
        )
        if ssh_state != "OK" or not isinstance(ident, dict):
            die(
                f"cannot retire {name}: SSH identity failed "
                f"({ident_detail or 'unreachable'}); final sync required"
            )
        remote_id = ident.get("node_id")
        if remote_id != node["node_id"]:
            die(
                f"cannot retire {name}: remote node_id {remote_id} does not "
                f"match registry {node['node_id']}"
            )
        identity = ident
        sync_row = _run_final_sync(node)
        status = sync_row.get("status")
        if status == SYNC_STATUS_EXPIRED:
            die(
                f"cannot retire {name}: CURSOR_EXPIRED; "
                f"run: vcl-fleet sync --reseed {name}"
            )
        if status != SYNC_STATUS_OK:
            die(
                f"cannot retire {name}: final sync failed "
                f"({sync_row.get('error') or status}); not marking retired"
            )

    last_status = _last_status_slice(name)
    if last_status is None:
        probe = probe_node(
            node,
            controller_utc=datetime.now(timezone.utc),
            want_verify=False,
        )
        last_status = _status_json_node(probe)

    write_retire_snapshot(node, identity=identity, last_status=last_status)

    _disabled, kept, disable_err = disable_remote_users_except_last(node)
    if disable_err:
        sys.stderr.write(
            f"WARNING: {name}: remote user disable was best-effort: "
            f"{disable_err}\n"
        )

    registry = load_registry()
    node = require_node(registry, name)
    node["status"] = NODE_STATUS_RETIRED
    node["enabled"] = False
    save_registry(None, registry)

    hint = ssh_uninstall_hint(node)
    sys.stdout.write(f"Retired {name} (status=retired, enabled=false).\n")
    sys.stdout.write("historical fleet.db rows were not erased\n")
    if kept:
        sys.stderr.write(
            f"WARNING: last enabled user {kept} remains on the node "
            "(node invariant; credentials were not revoked)\n"
        )
    sys.stdout.write(f"Uninstall hint: {hint}\n")
    sys.stdout.write(f"Snapshot: {retired_snapshot_dir(name)}\n")
    return 0


def _node_view(
    node: dict[str, Any],
    *,
    ssh_host: Optional[str] = None,
    ssh_user: Optional[str] = None,
    ssh_port: Optional[int] = None,
) -> dict[str, Any]:
    view = dict(node)
    if ssh_host is not None:
        view["ssh_host"] = ssh_host
    if ssh_user is not None:
        view["ssh_user"] = ssh_user
    if ssh_port is not None:
        view["ssh_port"] = ssh_port
    return view


def _replace_result(
    *,
    ok: bool,
    name: str,
    node_id: str,
    old_instance_id: Optional[str],
    new_instance_id: Optional[str],
    ssh_host: str,
    reissue_csv: Optional[str],
    state: str,
    error: Optional[str] = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": REPLACE_JSON_SCHEMA_VERSION,
        "ok": ok,
        "name": name,
        "node_id": node_id,
        "old_instance_id": old_instance_id,
        "new_instance_id": new_instance_id,
        "ssh_host": ssh_host,
        "reissue_csv": reissue_csv,
        "state": state,
    }
    if error:
        doc["error"] = error
    return doc


def _emit_replace_result(doc: dict[str, Any], as_json: bool) -> int:
    if as_json:
        sys.stdout.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        return 0 if doc.get("ok") else 1
    if not doc.get("ok"):
        die(str(doc.get("error") or "replace failed"))
    sys.stdout.write(
        f"Replaced {doc['name']} (node_id={doc['node_id']} still active).\n"
    )
    sys.stdout.write(f"old instance_id: {doc.get('old_instance_id') or '-'}\n")
    sys.stdout.write(f"new instance_id: {doc.get('new_instance_id') or '-'}\n")
    sys.stdout.write(f"ssh_host: {doc['ssh_host']}\n")
    if doc.get("reissue_csv"):
        sys.stdout.write(f"reissue_csv: {doc['reissue_csv']}\n")
    return 0


def _cursor_instance_id(node_id: str) -> Optional[str]:
    conn = open_fleet_db()
    try:
        row = read_sync_cursor_row(conn, node_id)
    finally:
        conn.close()
    if row is None:
        return None
    return _optional_text(row["instance_id"])


def build_node_restore_argv(archive: str, server: str) -> list[str]:
    """Remote argv for ``vcl restore`` on a runtime-only host.

    Must be accepted by real ``bin/vincula cmd_restore``: ``--reissue-output``,
    no replace-node flag, no restore ``--output``.
    """
    return [
        "vcl",
        "restore",
        archive,
        "--reissue-output",
        REMOTE_REISSUE_CSV,
        "--server",
        server,
        "--json",
    ]


def preflight_replace_target(
    node: dict[str, Any],
    extra: Optional[list[str]] = None,
) -> None:
    """New host must have runtime (vcl) and must not have VERSION."""
    host = str(node["ssh_host"])
    runtime = ssh_run(
        host,
        node["ssh_user"],
        int(node["ssh_port"]),
        ["test", "-x", REMOTE_VCL_BIN],
        batch=True,
        extra=extra,
        identity_file=_node_identity_file(node),
    )
    if runtime.returncode != 0:
        die(
            f"cannot replace: {host} has no Vincula runtime; "
            "install with: sudo bash vincula.sh --runtime-only"
        )
    version = ssh_run(
        host,
        node["ssh_user"],
        int(node["ssh_port"]),
        ["test", "!", "-f", REMOTE_VERSION_FILE],
        batch=True,
        extra=extra,
        identity_file=_node_identity_file(node),
    )
    if version.returncode != 0:
        die(
            f"cannot replace: {host} already has VERSION; "
            "restore is fresh-node only (runtime-only install required)"
        )


@with_fleet_op_lock
def cmd_node_replace(args: argparse.Namespace) -> int:
    """Physical instance replacement: secretless backup, restore, rotate.

    Real node contract (P0-01b): ``vcl restore FILE --reissue-output FILE
    --server HOST --json`` on a runtime-only host (no VERSION).
    """
    validate_name(args.name)
    as_json = bool(getattr(args, "as_json", False))
    registry = load_registry()
    node = require_node(registry, args.name)
    life = node_lifecycle_status(node)
    if life == NODE_STATUS_RETIRED:
        die(f"cannot replace retired node: {args.name}")
    if life != NODE_STATUS_ACTIVE or not node.get("enabled", True):
        die(f"cannot replace disabled node: {args.name}; enable it first")

    new_host, new_user, new_port = parse_ssh_target(
        args.host, None, int(node.get("ssh_port") or 22)
    )
    host_key = _optional_text(getattr(args, "host_key", None))
    if not host_key:
        die("node replace requires --host-key SHA256:...")
    extra, _batch = prepare_ssh_host_key(new_host, new_port, host_key)
    old_node = _node_view(node)
    new_node = _node_view(
        node, ssh_host=new_host, ssh_user=new_user, ssh_port=new_port
    )
    ident_path = _optional_text(getattr(args, "identity_file", None))
    if ident_path:
        new_node["identity_file"] = validate_identity_file(ident_path, must_exist=True)
    old_instance_id = _cursor_instance_id(node["node_id"])
    from_backup = _optional_text(getattr(args, "from_backup", None))

    if from_backup:
        sys.stderr.write(
            "WARNING: --from-backup skips final sync; the audit tail may be lost\n"
        )
        local_archive = Path(from_backup)
        if not local_archive.is_file():
            die(f"backup file not found: {local_archive}")
    else:
        ssh_state, ident, ident_detail = ssh_remote_json(
            old_node, ["vcl", "identity", "--json"]
        )
        if ssh_state != "OK" or not isinstance(ident, dict):
            die(
                f"cannot replace {args.name}: SSH identity failed "
                f"({ident_detail or 'unreachable'}); final sync required"
            )
        remote_id = ident.get("node_id")
        if remote_id != node["node_id"]:
            die(
                f"cannot replace {args.name}: remote node_id {remote_id} does "
                f"not match registry {node['node_id']}"
            )
        old_instance_id = _optional_text(ident.get("instance_id")) or old_instance_id
        sync_row = _run_final_sync(old_node, write_table=not as_json)
        status = sync_row.get("status")
        if status == SYNC_STATUS_EXPIRED:
            die(
                f"cannot replace {args.name}: CURSOR_EXPIRED; "
                f"run: {remediation_sync_reseed(args.name)}"
            )
        if status != SYNC_STATUS_OK:
            die(
                f"cannot replace {args.name}: final sync failed "
                f"({sync_row.get('error') or status}); not creating backup"
            )
        ssh_state, backup_doc, backup_detail = ssh_remote_json(
            old_node,
            ["vcl", "backup", "create", "--json"],
            timeout=SSH_BACKUP_TIMEOUT_SECONDS,
            require_exit_0=True,
        )
        if (
            ssh_state != "OK"
            or not isinstance(backup_doc, dict)
            or backup_doc.get("ok") is not True
        ):
            die(
                f"cannot replace {args.name}: backup create failed "
                f"({backup_detail or 'remote backup failed'})"
            )
        remote_path = str(backup_doc.get("path") or REMOTE_BACKUP_TAR)
        backups = fleet_home() / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        _chmod_private(backups, 0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        local_archive = backups / f"node-{node['node_id']}-{stamp}.tar"
        scp_pull(old_node, remote_path, local_archive)

    backup_mod = load_backup_module()
    verified = backup_mod.verify_archive(local_archive)
    if not verified.get("ok"):
        die(f"backup verify failed: {verified.get('error') or 'failed'}")
    if verified.get("secret_bearing"):
        die("node replace requires a secretless backup")
    source_id = verified.get("source_node_id")
    if source_id != node["node_id"]:
        die(
            f"cannot replace {args.name}: backup source_node_id {source_id} "
            f"does not match registry {node['node_id']}"
        )

    preflight_replace_target(new_node, extra=extra)
    scp_push(new_node, local_archive, REMOTE_RESTORE_TAR, extra=extra)
    restore_cmd = build_node_restore_argv(REMOTE_RESTORE_TAR, new_host)
    ssh_state, restore_doc, restore_detail = ssh_remote_json(
        new_node,
        restore_cmd,
        extra=extra,
        timeout=SSH_BACKUP_TIMEOUT_SECONDS,
        require_exit_0=True,
    )
    if (
        ssh_state != "OK"
        or not isinstance(restore_doc, dict)
        or restore_doc.get("ok") is not True
    ):
        die(
            f"cannot replace {args.name}: restore failed on {new_host} "
            f"({restore_detail or 'restore failed'})"
        )

    ssh_state, new_ident, ident_detail = ssh_remote_json(
        new_node, ["vcl", "identity", "--json"], extra=extra
    )
    failed_reason = None
    new_instance_id = None
    if ssh_state != "OK" or not isinstance(new_ident, dict):
        failed_reason = ident_detail or "identity unreachable after restore"
    else:
        if new_ident.get("node_id") != node["node_id"]:
            failed_reason = (
                f"restored node_id {new_ident.get('node_id')} does not match "
                f"registry {node['node_id']}"
            )
        else:
            new_instance_id = _optional_text(new_ident.get("instance_id"))
            if not new_instance_id:
                failed_reason = "restored instance_id missing"
            elif new_instance_id == node["node_id"]:
                failed_reason = "restored instance_id equals node_id"
            elif old_instance_id and new_instance_id == old_instance_id:
                failed_reason = "restored instance_id was not rotated"

    if failed_reason is None:
        ssh_state, verify_doc, verify_detail = ssh_remote_json(
            new_node, ["vcl", "verify", "--json"], extra=extra
        )
        if ssh_state != "OK" or not isinstance(verify_doc, dict):
            failed_reason = verify_detail or "verify unreachable after restore"
        elif verify_doc.get("ok") is not True:
            failed_reason = "vcl verify --json is not ok after restore"

    if failed_reason is not None:
        sys.stderr.write(
            f"WARNING: restore committed on {new_host} but replace did not "
            f"update the registry ({failed_reason}). "
            f"Remediation: vcl-fleet node set {args.name} --host {node['ssh_host']}\n"
        )
        return _emit_replace_result(
            _replace_result(
                ok=False,
                name=args.name,
                node_id=node["node_id"],
                old_instance_id=old_instance_id,
                new_instance_id=new_instance_id,
                ssh_host=node["ssh_host"],
                reissue_csv=None,
                state=OP_FAILED,
                error=failed_reason,
            ),
            as_json,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_dest = Path(args.output) if getattr(args, "output", None) else (
        fleet_home() / f"reissue-{args.name}-{stamp}.csv"
    )
    csv_dest.parent.mkdir(parents=True, exist_ok=True)
    csv_proc = scp_run(
        port=int(new_node.get("ssh_port") or 22),
        src=_scp_remote_spec(new_node, REMOTE_REISSUE_CSV),
        dest=str(csv_dest),
        extra=extra,
        identity_file=_node_identity_file(new_node),
    )
    reissue_csv: Optional[str]
    if csv_proc.returncode == 0 and csv_dest.is_file():
        _chmod_private(csv_dest, 0o600)
        warn_credentials(str(csv_dest))
        reissue_csv = str(csv_dest)
    else:
        sys.stderr.write(
            f"WARNING: {args.name}: could not collect reissue CSV "
            f"({_ssh_failure_detail(csv_proc)})\n"
        )
        reissue_csv = None

    now_iso = format_utc(datetime.now(timezone.utc))
    conn = open_fleet_db()
    try:
        retire_active_instance(conn, node["node_id"], retired_at=now_iso)
        insert_instance(
            conn,
            node_id=node["node_id"],
            instance_id=str(new_instance_id),
            started_at=now_iso,
            endpoint=new_host,
            ssh_host=new_host,
            status=INSTANCE_STATUS_ACTIVE,
        )
        cursor = read_sync_cursor_row(conn, node["node_id"])
        last_event_id = int(cursor["last_event_id"]) if cursor is not None else 0
        last_export_seq = (
            int(cursor["last_export_seq"] or 0) if cursor is not None else 0
        )
        cursor_kind = CURSOR_KIND_EXPORT_SEQ
        if cursor is not None:
            cursor_kind = (
                _optional_text(cursor["cursor_kind"]) or CURSOR_KIND_EXPORT_SEQ
            )
        cursor_status = (
            str(cursor["status"])
            if cursor is not None and cursor["status"]
            else SYNC_STATUS_OK
        )
        write_sync_cursor(
            conn,
            node_id=node["node_id"],
            instance_id=new_instance_id,
            last_event_id=last_event_id,
            last_export_seq=last_export_seq,
            cursor_kind=cursor_kind,
            status=cursor_status,
            now_iso=now_iso,
        )
        conn.commit()
    finally:
        conn.close()

    registry = load_registry()
    stored = require_node(registry, args.name)
    stored["ssh_host"] = new_host
    stored["ssh_user"] = new_user
    stored["ssh_port"] = new_port
    if new_node.get("identity_file"):
        stored["identity_file"] = new_node["identity_file"]
    stored["status"] = NODE_STATUS_ACTIVE
    stored["enabled"] = True
    save_registry(None, registry)

    _disabled, kept, disable_err = disable_remote_users_except_last(old_node)
    if disable_err:
        sys.stderr.write(
            f"WARNING: {args.name}: remote user disable on old host was "
            f"best-effort: {disable_err}\n"
        )
    if kept:
        sys.stderr.write(
            f"WARNING: last enabled user {kept} remains on the old host "
            "(node invariant; credentials were not revoked)\n"
        )
    if old_instance_id and new_instance_id and old_instance_id != new_instance_id:
        sys.stderr.write(
            f"WARNING: {args.name}: instance changed, node_id stable "
            f"({old_instance_id} → {new_instance_id})\n"
        )

    return _emit_replace_result(
        _replace_result(
            ok=True,
            name=args.name,
            node_id=node["node_id"],
            old_instance_id=old_instance_id,
            new_instance_id=new_instance_id,
            ssh_host=new_host,
            reissue_csv=reissue_csv,
            state=OP_SUCCESS,
        ),
        as_json,
    )


def format_instances_table(rows: list[dict[str, Any]]) -> str:
    lines = ["INSTANCE_ID STARTED RETIRED ENDPOINT SSH STATUS"]
    for row in rows:
        lines.append(
            f"{row.get('instance_id') or '-'} {row.get('started_at') or '-'} "
            f"{row.get('retired_at') or '-'} {row.get('endpoint') or '-'} "
            f"{row.get('ssh_host') or '-'} {row.get('status') or '-'}"
        )
    return "\n".join(lines) + "\n"


def cmd_node_instances(name: str, as_json: bool = False) -> int:
    validate_name(name)
    node = require_node(load_registry(), name)
    conn = open_fleet_db()
    try:
        rows = list_instances(conn, node["node_id"])
    finally:
        conn.close()
    if as_json:
        payload = {
            "schema_version": INSTANCE_JSON_SCHEMA_VERSION,
            "name": node["name"],
            "node_id": node["node_id"],
            "instances": [
                {
                    "instance_id": row.get("instance_id"),
                    "started_at": row.get("started_at"),
                    "retired_at": row.get("retired_at"),
                    "endpoint": row.get("endpoint"),
                    "ssh_host": row.get("ssh_host"),
                    "status": row.get("status"),
                }
                for row in rows
            ],
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0
    sys.stdout.write(format_instances_table(rows))
    return 0


def format_utc(dt: datetime) -> str:
    return _as_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_rfc3339_utc(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("empty utc_now")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return _as_utc(datetime.fromisoformat(raw))


def clock_skew_result(
    controller_utc: datetime, remote_utc: datetime
) -> tuple[str, str]:
    """Compare controller UTC vs remote UTC. Returns (OK|WARN|FAIL, detail)."""
    delta = abs((_as_utc(controller_utc) - _as_utc(remote_utc)).total_seconds())
    if delta > CLOCK_SKEW_FAIL_SECONDS:
        return (
            "FAIL",
            (
                f"{CLOCK_SKEW_FAIL_CHECK}: drift {delta:.0f}s exceeds "
                f"{CLOCK_SKEW_FAIL_SECONDS}s"
            ),
        )
    if delta > CLOCK_SKEW_WARN_SECONDS:
        return (
            "WARN",
            f"clock drift {delta:.0f}s exceeds {CLOCK_SKEW_WARN_SECONDS}s",
        )
    return ("OK", f"clock drift {delta:.0f}s")


def clock_skew_from_identity(
    controller_utc: datetime, ident: Optional[dict[str, Any]]
) -> tuple[str, str, Optional[float]]:
    if not ident or ident.get("utc_now") in (None, ""):
        return (
            "FAIL",
            f"{CLOCK_SKEW_FAIL_CHECK}: remote utc_now missing",
            None,
        )
    try:
        remote = parse_rfc3339_utc(str(ident.get("utc_now")))
    except (ValueError, TypeError):
        return (
            "FAIL",
            f"{CLOCK_SKEW_FAIL_CHECK}: remote utc_now unreadable",
            None,
        )
    state, detail = clock_skew_result(controller_utc, remote)
    delta = abs((_as_utc(controller_utc) - remote).total_seconds())
    return (state, detail, delta)


def short_id(value: Optional[str]) -> str:
    if not value:
        return "-"
    return value[:8] if len(value) > 8 else value


def _stdout_json(proc: subprocess.CompletedProcess[str]) -> Optional[Any]:
    text = (proc.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def ssh_remote_json(
    node: dict[str, Any],
    remote_cmd: list[str],
    *,
    timeout: float = SSH_TIMEOUT_SECONDS,
    extra: list[str] | None = None,
    require_exit_0: bool = False,
) -> tuple[str, Optional[dict[str, Any]], str]:
    """SSH a remote vcl --json command.

    SSH unreachable (exit 255 / timeout / connect failure) → ssh FAIL.
    Remote vcl status/verify may exit 1 with valid JSON; that is SSH OK.
    Mutation commands (restore, backup create, user add/rotate/disable)
    pass require_exit_0=True: any non-zero remote exit is FAIL even if
    stdout is valid JSON.
    """
    proc = ssh_run(
        node["ssh_host"],
        node["ssh_user"],
        node["ssh_port"],
        remote_cmd,
        batch=True,
        extra=extra,
        identity_file=_node_identity_file(node),
        timeout=timeout,
    )
    detail = _ssh_failure_detail(proc)
    if proc.returncode == 255:
        return "FAIL", None, detail
    payload = _stdout_json(proc)
    if require_exit_0 and proc.returncode != 0:
        return (
            "FAIL",
            payload if isinstance(payload, dict) else None,
            detail or f"remote exit {proc.returncode}",
        )
    if not isinstance(payload, dict):
        return "OK", None, detail or "remote JSON missing or invalid"
    return "OK", payload, detail if proc.returncode != 0 else ""


def ssh_remote_text(
    node: dict[str, Any],
    remote_cmd: list[str],
    *,
    timeout: float = SSH_TIMEOUT_SECONDS,
) -> tuple[str, str, str]:
    """SSH a remote command expecting text stdout (e.g. vcl user link).

    FAIL = unreachable (exit 255 / timeout). OK = host reached; stdout may
    still be empty if the remote command failed (detail then has stderr).
    """
    proc = ssh_run(
        node["ssh_host"],
        node["ssh_user"],
        node["ssh_port"],
        remote_cmd,
        batch=True,
        identity_file=_node_identity_file(node),
        timeout=timeout,
    )
    detail = _ssh_failure_detail(proc)
    stdout = proc.stdout or ""
    if proc.returncode == 255:
        return "FAIL", "", detail
    if proc.returncode != 0:
        return "OK", stdout, detail
    return "OK", stdout, ""


def classify_proxy(status_doc: Optional[dict[str, Any]]) -> str:
    if status_doc is None:
        return "UNKNOWN"
    proxy = status_doc.get("proxy")
    if not isinstance(proxy, dict):
        return "FAIL"
    return "OK" if proxy.get("ok") is True else "FAIL"


def classify_accounting(status_doc: Optional[dict[str, Any]]) -> str:
    if status_doc is None:
        return "UNKNOWN"
    acct = status_doc.get("accounting")
    if not isinstance(acct, dict):
        return "FAIL"
    if acct.get("heartbeat") == "stale":
        return "STALE"
    return "OK" if acct.get("ok") is True else "FAIL"


def status_is_fail(row: dict[str, Any]) -> bool:
    return row.get("ssh") == "FAIL" or row.get("proxy") == "FAIL" or row.get(
        "accounting"
    ) == "FAIL"


def verify_is_fail(row: dict[str, Any]) -> bool:
    return status_is_fail(row) or row.get("registry") == "FAIL" or row.get("clock") == "FAIL"


def _empty_probe_row(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": node["name"],
        "node_id": node["node_id"],
        "instance_id": None,
        "enabled": bool(node.get("enabled", True)),
        "vincula_version": None,
        "ssh": "OK",
        "proxy": "UNKNOWN",
        "accounting": "UNKNOWN",
        "registry": "UNKNOWN",
        "clock": "UNKNOWN",
        "clock_detail": "",
        "clock_skew_seconds": None,
        "ssh_detail": "",
        "warnings": [],
        "checks": [],
        "ok": True,
    }


def probe_node(
    node: dict[str, Any],
    *,
    controller_utc: datetime,
    want_verify: bool,
    previous_instances: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    row = _empty_probe_row(node)
    life = node_lifecycle_status(node)
    if life == NODE_STATUS_RETIRED:
        row["ssh"] = "-"
        row["proxy"] = "-"
        row["accounting"] = "-"
        row["registry"] = "-"
        row["clock"] = "-"
        row["ok"] = True
        return row
    if life == NODE_STATUS_DISABLED or not node.get("enabled", True):
        row["ssh"] = "DISABLED"
        row["proxy"] = "DISABLED"
        row["accounting"] = "DISABLED"
        row["registry"] = "DISABLED"
        row["clock"] = "DISABLED"
        row["ok"] = True
        return row

    ssh_state, ident, ident_detail = ssh_remote_json(
        node, ["vcl", "identity", "--json"]
    )
    if ssh_state != "OK":
        row["ssh"] = "FAIL"
        row["ssh_detail"] = ident_detail
        row["ok"] = False
        return row
    if ident is None:
        row["ssh"] = "OK"
        row["proxy"] = "FAIL"
        row["accounting"] = "FAIL"
        row["ssh_detail"] = ident_detail
        row["clock"] = "FAIL"
        row["clock_detail"] = f"{CLOCK_SKEW_FAIL_CHECK}: remote utc_now missing"
        row["ok"] = False
        return row

    row["instance_id"] = ident.get("instance_id") or None
    row["vincula_version"] = ident.get("vincula_version")
    clock_state, clock_detail, skew = clock_skew_from_identity(controller_utc, ident)
    row["clock"] = clock_state
    row["clock_detail"] = clock_detail
    row["clock_skew_seconds"] = skew
    if clock_state == "WARN":
        row["warnings"].append(clock_detail)
    if clock_state == "FAIL":
        row["checks"].append(
            {
                "name": CLOCK_SKEW_FAIL_CHECK,
                "ok": False,
                "detail": clock_detail,
            }
        )

    remote_nid = ident.get("node_id")
    if isinstance(remote_nid, str) and remote_nid == node["node_id"]:
        row["registry"] = "OK"
        prev = (previous_instances or {}).get(node["name"])
        if prev and row["instance_id"] and prev != row["instance_id"]:
            row["warnings"].append("instance changed, node_id stable")
    else:
        row["registry"] = "FAIL"

    ssh_state, status_doc, status_detail = ssh_remote_json(
        node, ["vcl", "status", "--json"]
    )
    if ssh_state != "OK":
        row["ssh"] = "FAIL"
        row["ssh_detail"] = status_detail
        row["proxy"] = "UNKNOWN"
        row["accounting"] = "UNKNOWN"
        row["ok"] = False
        return row
    if status_doc is None:
        row["proxy"] = "FAIL"
        row["accounting"] = "FAIL"
        row["ssh_detail"] = status_detail
    else:
        row["proxy"] = classify_proxy(status_doc)
        row["accounting"] = classify_accounting(status_doc)

    if want_verify:
        v_ssh, verify_doc, v_detail = ssh_remote_json(
            node, ["vcl", "verify", "--json"]
        )
        if v_ssh != "OK":
            row["ssh"] = "FAIL"
            row["ssh_detail"] = v_detail
            row["proxy"] = "UNKNOWN"
            row["accounting"] = "UNKNOWN"
            row["ok"] = False
            return row
        if isinstance(verify_doc, dict):
            acct = verify_doc.get("accounting")
            if isinstance(acct, dict):
                for check in acct.get("checks") or []:
                    if isinstance(check, dict):
                        row["checks"].append(
                            {
                                "name": check.get("name"),
                                "ok": bool(check.get("ok")),
                                "detail": check.get("detail"),
                            }
                        )

    row["ok"] = not verify_is_fail(row)
    return row


def format_status_table(rows: list[dict[str, Any]]) -> str:
    lines = [f"{'NAME':<8} {'NODE_ID':<8} {'INSTANCE':<8} {'SSH':<7} {'PROXY':<7} ACCOUNTING"]
    for row in rows:
        instance = "-"
        if row.get("ssh") not in ("FAIL", "DISABLED", "-") and row.get("instance_id"):
            instance = short_id(row.get("instance_id"))
        lines.append(
            f"{row['name']:<8} {short_id(row.get('node_id')):<8} {instance:<8} "
            f"{row['ssh']:<7} {row['proxy']:<7} {row['accounting']}"
        )
    return "\n".join(lines) + "\n"


def format_verify_report(rows: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for row in rows:
        parts.append(row["name"])
        if row.get("ssh") == "-":
            parts.append("  status: retired")
            parts.append("")
            continue
        if row.get("ssh") == "DISABLED":
            parts.append("  enabled: false")
            parts.append("")
            continue
        parts.append(f"  version: {row.get('vincula_version') or '-'}")
        parts.append(f"  node_id: {row.get('node_id') or '-'}")
        parts.append(f"  instance_id: {row.get('instance_id') or '-'}")
        parts.append(f"  ssh: {row['ssh']}")
        parts.append(f"  proxy: {row['proxy']}")
        parts.append(f"  accounting: {row['accounting']}")
        parts.append(f"  registry: {row['registry']}")
        parts.append(f"  clock: {row['clock']}")
        if row.get("clock_detail"):
            parts.append(f"  clock_detail: {row['clock_detail']}")
        if row.get("ssh_detail") and row["ssh"] == "FAIL":
            parts.append(f"  ssh_detail: {row['ssh_detail']}")
        for warning in row.get("warnings") or []:
            parts.append(f"  WARN: {warning}")
        if row["ssh"] == "FAIL":
            parts.append("  FAIL: SSH unreachable")
        if row["proxy"] == "FAIL":
            parts.append("  FAIL: PROXY")
        if row["accounting"] == "FAIL":
            parts.append("  FAIL: ACCOUNTING")
        if row["registry"] == "FAIL":
            parts.append("  FAIL: registry node_id mismatch")
        if row["clock"] == "FAIL":
            parts.append(f"  FAIL: {row.get('clock_detail') or CLOCK_SKEW_FAIL_CHECK}")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _status_json_node(row: dict[str, Any]) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "name": row["name"],
        "node_id": row["node_id"],
        "instance_id": row.get("instance_id"),
        "enabled": row.get("enabled", True),
        "ssh": row["ssh"],
        "proxy": row["proxy"],
        "accounting": row["accounting"],
    }
    if row.get("ssh_detail"):
        doc["ssh_detail"] = row["ssh_detail"]
    return doc


def _verify_json_node(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "ok": bool(row.get("ok")),
        "vincula_version": row.get("vincula_version"),
        "node_id": row["node_id"],
        "instance_id": row.get("instance_id"),
        "enabled": row.get("enabled", True),
        "ssh": row["ssh"],
        "proxy": row["proxy"],
        "accounting": row["accounting"],
        "registry": row["registry"],
        "clock": row["clock"],
        "clock_skew_seconds": row.get("clock_skew_seconds"),
        "warnings": list(row.get("warnings") or []),
        "checks": list(row.get("checks") or []),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=".last-status.", suffix=".tmp", dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
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


def write_last_status(payload: dict[str, Any]) -> None:
    _atomic_write_json(last_status_path(), payload)


def load_previous_instance_ids() -> dict[str, str]:
    path = last_status_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for node in data.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        name = node.get("name")
        instance_id = node.get("instance_id")
        if isinstance(name, str) and isinstance(instance_id, str) and instance_id:
            out[name] = instance_id
    return out


def _selected_nodes(registry: dict[str, Any], include_all: bool) -> list[dict[str, Any]]:
    nodes = list(registry.get("nodes") or [])
    if include_all:
        return nodes
    return [node for node in nodes if node_is_active(node)]


def run_status_payload(*, include_all: bool = False) -> dict[str, Any]:
    """Probe status and write last-status.json; return payload (no stdout)."""
    registry = load_registry()
    controller_utc = datetime.now(timezone.utc)
    rows = [
        probe_node(node, controller_utc=controller_utc, want_verify=False)
        for node in _selected_nodes(registry, include_all)
    ]
    payload = {
        "schema_version": STATUS_JSON_SCHEMA_VERSION,
        "ok": not any(status_is_fail(row) for row in rows),
        "controller_utc": format_utc(controller_utc),
        "nodes": [_status_json_node(row) for row in rows],
    }
    write_last_status(payload)
    payload["_rows"] = rows  # CLI table only; strip before JSON emit
    return payload


def run_verify_payload(*, include_all: bool = False) -> dict[str, Any]:
    """Probe verify and write last-status.json; return payload (no stdout)."""
    registry = load_registry()
    controller_utc = datetime.now(timezone.utc)
    previous = load_previous_instance_ids()
    rows = [
        probe_node(
            node,
            controller_utc=controller_utc,
            want_verify=True,
            previous_instances=previous,
        )
        for node in _selected_nodes(registry, include_all)
    ]
    payload = {
        "schema_version": VERIFY_JSON_SCHEMA_VERSION,
        "ok": not any(verify_is_fail(row) for row in rows),
        "controller_utc": format_utc(controller_utc),
        "nodes": [_verify_json_node(row) for row in rows],
    }
    write_last_status(payload)
    payload["_rows"] = rows
    return payload


def cmd_status(*, as_json: bool, include_all: bool) -> int:
    payload = run_status_payload(include_all=include_all)
    rows = payload.pop("_rows")
    if as_json:
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(format_status_table(rows))
    return 0 if payload["ok"] else 1


def cmd_verify(*, as_json: bool, include_all: bool) -> int:
    payload = run_verify_payload(include_all=include_all)
    rows = payload.pop("_rows")
    if as_json:
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(format_verify_report(rows))
    return 0 if payload["ok"] else 1


def _node_name(node: Any) -> str:
    if isinstance(node, dict):
        return str(node.get("name") or node.get("node") or "")
    return str(node)


def _node_status(row: dict[str, Any]) -> str:
    status = row.get("status")
    if status in (OP_SUCCESS, OP_FAILED):
        return str(status)
    if "ok" in row:
        return OP_SUCCESS if row["ok"] else OP_FAILED
    return OP_FAILED


def _node_result_row(node: Any, ok: bool, detail: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": _node_name(node),
        "status": OP_SUCCESS if ok else OP_FAILED,
        "credential_id": None,
        "vless_uri": None,
        "error": None,
    }
    extra = detail if isinstance(detail, dict) else {}
    if extra:
        if extra.get("credential_id") is not None:
            row["credential_id"] = extra.get("credential_id")
        if extra.get("vless_uri") is not None:
            row["vless_uri"] = extra.get("vless_uri")
    if ok:
        return row
    if extra:
        err = extra.get("error")
        row["error"] = str(err) if err is not None else "failed"
        return row
    if detail is None:
        row["error"] = "failed"
        return row
    row["error"] = str(detail)
    return row


def plan_mutation(
    nodes: list[Any],
    *,
    operation: str = "user.add",
    tag: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    """Return a mutation document in PLANNED (no SSH)."""
    return {
        "schema_version": MUTATION_SCHEMA_VERSION,
        "operation": operation,
        "tag": tag,
        "user_id": user_id,
        "state": OP_PLANNED,
        "planned_nodes": [_node_name(node) for node in nodes],
        "nodes": [],
        "remediation": [],
    }


def record_result(
    results: Optional[list[dict[str, Any]]],
    node: Any,
    ok: bool,
    detail: Any = None,
) -> list[dict[str, Any]]:
    """Append one per-node SUCCESS/FAILED row; does not mutate *results*."""
    acc = list(results or [])
    acc.append(_node_result_row(node, ok, detail))
    return acc


def plan_state(node_results: list[dict[str, Any]]) -> str:
    """Empty → PLANNED; all SUCCESS → SUCCESS; else PARTIAL (including all-failed)."""
    if not node_results:
        return OP_PLANNED
    if all(_node_status(row) == OP_SUCCESS for row in node_results):
        return OP_SUCCESS
    return OP_PARTIAL


def final_state(results: list[dict[str, Any]]) -> str:
    """Terminal state: SUCCESS only if every node succeeded; else PARTIAL."""
    return plan_state(results)


def mark_applying(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out["state"] = OP_APPLYING
    return out


def remediation_user_add(tag: str, user_id: str, failed_names: list[str]) -> list[str]:
    return [
        f"vcl-fleet user add {tag} --nodes {name} --user-id {user_id}"
        for name in failed_names
    ]


def mutation_report(
    results: list[dict[str, Any]],
    *,
    tag: str = "",
    user_id: str = "",
    operation: str = "user.add",
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    for row in results:
        item = dict(row)
        item["name"] = _node_name(item)
        item["status"] = _node_status(item)
        item.setdefault("credential_id", None)
        item.setdefault("vless_uri", None)
        item.setdefault("error", None)
        nodes.append(item)
    state = plan_state(nodes)
    failed_names = [row["name"] for row in nodes if row["status"] != OP_SUCCESS]
    remediation: list[str] = []
    if state == OP_PARTIAL:
        remediation = remediation_user_add(tag, user_id, failed_names)
    return {
        "schema_version": MUTATION_SCHEMA_VERSION,
        "operation": operation,
        "tag": tag,
        "user_id": user_id,
        "state": state,
        "nodes": nodes,
        "remediation": remediation,
    }


def format_partial_report(doc: dict[str, Any]) -> str:
    """Human table: STATE, per-node SUCCESS|FAILED, optional Remediation block."""
    state = str(doc.get("state") or plan_state(list(doc.get("nodes") or [])))
    lines = [f"STATE {state}"]
    operation = doc.get("operation")
    if operation:
        lines.append(f"operation: {operation}")
    tag = doc.get("tag") or ""
    if tag:
        lines.append(f"tag: {tag}")
    user_id = doc.get("user_id") or ""
    if user_id:
        lines.append(f"user_id: {user_id}")
    lines.append("")
    lines.append(f"{'NODE':<12} STATUS")
    nodes = list(doc.get("nodes") or [])
    for row in nodes:
        name = _node_name(row)
        status = _node_status(row)
        extra = ""
        if status == OP_FAILED and row.get("error"):
            extra = f"  {row['error']}"
        lines.append(f"{name:<12} {status}{extra}")
    rem = list(doc.get("remediation") or [])
    if not rem and state == OP_PARTIAL:
        rem = remediation_user_add(
            tag,
            user_id,
            [_node_name(row) for row in nodes if _node_status(row) != OP_SUCCESS],
        )
    if rem:
        lines.append("")
        lines.append("Remediation:")
        for cmd in rem:
            lines.append(f"  {cmd}")
    return "\n".join(lines) + "\n"


def render_partial_report(
    results: list[dict[str, Any]],
    *,
    tag: str = "",
    user_id: str = "",
    operation: str = "user.add",
) -> str:
    return format_partial_report(
        mutation_report(results, tag=tag, user_id=user_id, operation=operation)
    )


def never_report_full_success(doc: dict[str, Any]) -> int:
    """Exit 0 only for SUCCESS; PARTIAL (including all-failed) is 2."""
    return MUTATION_EXIT_SUCCESS if doc.get("state") == OP_SUCCESS else MUTATION_EXIT_PARTIAL


def parse_nodes_cell(raw: str) -> tuple[list[str], Optional[str]]:
    """Parse a CSV nodes cell (`lax` or `lax,tokyo`). Empty / invalid → error string."""
    parts = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if not parts:
        return [], "empty nodes"
    seen: set[str] = set()
    names: list[str] = []
    for name in parts:
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            return [], f"invalid node name: {name}"
        if name in seen:
            return [], f"duplicate node in list: {name}"
        seen.add(name)
        names.append(name)
    return names, None


def parse_nodes_csv(raw: str) -> list[str]:
    names, err = parse_nodes_cell(raw)
    if err:
        if err == "empty nodes":
            die("nodes list is empty")
        die(err)
    return names


def node_importable(node: Optional[dict[str, Any]], name: str) -> Optional[str]:
    """None if the node may be targeted; otherwise a validation error."""
    if node is None:
        return f"unknown node: {name}"
    if node.get("status") == "retired":
        return f"node is retired: {name}"
    if not node.get("enabled", True):
        return f"node is disabled: {name}"
    return None


def target_names_from_add_args(args: argparse.Namespace) -> list[str]:
    one = getattr(args, "node_one", None)
    many = getattr(args, "nodes_csv", None)
    if one and many:
        die("--node and --nodes are mutually exclusive")
    raw = many or one
    if not raw:
        die("user add requires --node or --nodes")
    return parse_nodes_csv(str(raw))


def require_enabled_node(registry: dict[str, Any], name: str) -> dict[str, Any]:
    node = require_node(registry, name)
    life = node_lifecycle_status(node)
    if life == NODE_STATUS_RETIRED:
        die(f"node is retired: {name}")
    if life != NODE_STATUS_ACTIVE or not node.get("enabled", True):
        die(f"node is disabled: {name}")
    return node


def write_private_file(path: Path, text: str) -> None:
    path = Path(path)
    parent = path.parent
    if str(parent) not in (".", ""):
        parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass
    payload = text if text.endswith("\n") else text + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def warn_credentials(target: str) -> None:
    sys.stderr.write(
        f"WARNING: {target} {CREDENTIAL_WARN_TAIL}\n"
        "Store and distribute it securely.\n"
    )


def format_credential_entries(entries: list[tuple[str, dict[str, Any]]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_CREDENTIAL_HEADER)
    for tag, row in entries:
        writer.writerow(
            (
                tag,
                _node_name(row),
                row.get("credential_id") or "",
                row.get("vless_uri") or "",
            )
        )
    return buf.getvalue()


def format_credential_csv(tag: str, nodes: list[dict[str, Any]]) -> str:
    return format_credential_entries([(tag, row) for row in nodes])


def _first_vless_uri(text: str) -> Optional[str]:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("vless://"):
            return stripped
    stripped = (text or "").strip()
    return stripped or None


def _active_credential_id(shown: dict[str, Any]) -> Optional[str]:
    for cred in shown.get("credentials") or []:
        if isinstance(cred, dict) and cred.get("status") == "active":
            cid = cred.get("credential_id")
            if isinstance(cid, str) and cid:
                return cid
    return None


def ssh_user_link_uri(node: dict[str, Any], tag: str) -> Optional[str]:
    ssh_state, stdout, _detail = ssh_remote_text(
        node,
        ["vcl", "user", "link", tag],
        timeout=SSH_MUTATION_TIMEOUT_SECONDS,
    )
    if ssh_state != "OK":
        return None
    return _first_vless_uri(stdout)


def _ssh_error(prefix_rc: int, detail: str) -> str:
    text = (detail or "failed").strip() or "failed"
    if text.startswith("ssh exit "):
        return text
    return f"ssh exit {prefix_rc}: {text}"


def provision_user_on_node(
    node: dict[str, Any],
    *,
    tag: str,
    user_id: str,
    display_name: Optional[str] = None,
    department: Optional[str] = None,
) -> dict[str, Any]:
    """Idempotent per-node add (D16). Returns a SUCCESS/FAILED node row."""
    display_name = validate_display_name(display_name)
    department = validate_department(department)
    ssh_state, shown, show_detail = ssh_remote_json(
        node,
        ["vcl", "user", "show", tag, "--json"],
        timeout=SSH_MUTATION_TIMEOUT_SECONDS,
    )
    if ssh_state != "OK":
        return _node_result_row(node, False, _ssh_error(255, show_detail))

    if isinstance(shown, dict) and shown.get("tag") == tag:
        remote_uid = shown.get("user_id") or ""
        if remote_uid != user_id:
            return _node_result_row(
                node,
                False,
                (
                    f"identity conflict: tag {tag} has user_id {remote_uid}, "
                    f"expected {user_id}"
                ),
            )
        cred_id = _active_credential_id(shown)
        uri = ssh_user_link_uri(node, tag)
        return _node_result_row(
            node,
            True,
            {"credential_id": cred_id, "vless_uri": uri},
        )

    remote = ["vcl", "user", "add", tag, "--user-id", user_id, "--json"]
    if display_name:
        remote.extend(["--display-name", display_name])
    if department:
        remote.extend(["--department", department])
    ssh_state, payload, detail = ssh_remote_json(
        node, remote, timeout=SSH_MUTATION_TIMEOUT_SECONDS, require_exit_0=True
    )
    if ssh_state != "OK":
        return _node_result_row(node, False, _ssh_error(255, detail))
    if not isinstance(payload, dict):
        return _node_result_row(node, False, _ssh_error(1, detail))
    if payload.get("ok") is not True:
        err = payload.get("error") or detail or "failed"
        return _node_result_row(node, False, _ssh_error(1, str(err)))
    return _node_result_row(
        node,
        True,
        {
            "credential_id": payload.get("credential_id"),
            "vless_uri": payload.get("vless_uri"),
        },
    )


def cmd_user_add(args: argparse.Namespace) -> int:
    tag = args.tag
    validate_name(tag)
    display_name = validate_display_name(getattr(args, "display_name", None))
    department = validate_department(getattr(args, "department", None))
    user_id = (getattr(args, "user_id", None) or "").strip()
    if user_id:
        if not UUID_RE.fullmatch(user_id):
            die(f"invalid user_id: {user_id}")
    else:
        user_id = str(uuid.uuid4())

    names = target_names_from_add_args(args)
    registry = load_registry()
    nodes = [require_enabled_node(registry, name) for name in names]
    as_json = bool(getattr(args, "as_json", False))

    if not as_json:
        sys.stderr.write(
            f"user.add {tag} {OP_PLANNED} nodes={','.join(n['name'] for n in nodes)}\n"
        )

    results: list[dict[str, Any]] = []
    for node in nodes:
        if not as_json:
            sys.stderr.write(f"user.add {tag} {OP_APPLYING} {node['name']}\n")
        results.append(
            provision_user_on_node(
                node,
                tag=tag,
                user_id=user_id,
                display_name=display_name,
                department=department,
            )
        )

    doc = mutation_report(results, tag=tag, user_id=user_id, operation="user.add")
    success_nodes = [row for row in doc["nodes"] if row.get("status") == OP_SUCCESS]
    csv_text = format_credential_csv(tag, success_nodes) if success_nodes else ""

    output = getattr(args, "output", None)
    if output and csv_text:
        write_private_file(Path(output), csv_text)
        warn_credentials(str(output))

    if as_json:
        sys.stdout.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        return never_report_full_success(doc)

    if doc["state"] == OP_SUCCESS:
        warn_credentials("stdout")
        sys.stdout.write(csv_text)
        sys.stderr.write(f"STATE {OP_SUCCESS}\n")
        sys.stderr.write(f"user_id: {user_id}\n")
        return MUTATION_EXIT_SUCCESS

    sys.stdout.write(format_partial_report(doc))
    if csv_text:
        warn_credentials("stdout")
        sys.stdout.write(csv_text)
    return MUTATION_EXIT_PARTIAL


def _list_users_on_node(
    node: dict[str, Any],
) -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
    ssh_state, payload, detail = ssh_remote_json(
        node, ["vcl", "user", "list", "--json"]
    )
    if ssh_state != "OK":
        return None, _ssh_error(255, detail)
    if not isinstance(payload, dict):
        return None, _ssh_error(1, detail)
    users = payload.get("users") or []
    if not isinstance(users, list):
        return None, "remote list JSON users is not a list"
    return [u for u in users if isinstance(u, dict)], None


def run_user_list_payload() -> tuple[int, dict[str, Any]]:
    """Aggregate user list over SSH; return (exit_code, payload) without stdout."""
    registry = load_registry()
    nodes = _selected_nodes(registry, include_all=False)
    unreachable: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for node in nodes:
        users, err = _list_users_on_node(node)
        if err is not None:
            unreachable.append({"name": node["name"], "error": err})
            continue
        for user in users or []:
            uid = str(user.get("user_id") or "")
            tag = str(user.get("tag") or "")
            key = uid or f"tag:{tag}@{node['name']}"
            if key not in grouped:
                grouped[key] = {
                    "tag": tag,
                    "user_id": uid,
                    "nodes": [],
                }
                order.append(key)
            rec = grouped[key]
            if tag and rec["tag"] and tag != rec["tag"]:
                rec["tag"] = f"{rec['tag']},{tag}"
            elif tag and not rec["tag"]:
                rec["tag"] = tag
            rec["nodes"].append(
                {
                    "name": node["name"],
                    "tag": tag,
                    "enabled": bool(user.get("enabled")),
                    "status": "active" if user.get("enabled") else "disabled",
                    "active_credential_id": user.get("active_credential_id"),
                }
            )

    ok = not unreachable
    payload = {
        "schema_version": MUTATION_SCHEMA_VERSION,
        "ok": ok,
        "state": OP_SUCCESS if ok else OP_PARTIAL,
        "users": [
            {
                "tag": grouped[key]["tag"],
                "user_id": grouped[key]["user_id"],
                "nodes": grouped[key]["nodes"],
            }
            for key in order
        ],
        "unreachable": unreachable,
    }
    return (0 if ok else MUTATION_EXIT_PARTIAL), payload


def cmd_user_list(args: argparse.Namespace) -> int:
    as_json = bool(getattr(args, "as_json", False))
    code, payload = run_user_list_payload()
    if as_json:
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return code

    sys.stdout.write("TAG USER_ID NODES\n")
    for user in payload["users"]:
        node_names = ",".join(n["name"] for n in user["nodes"])
        sys.stdout.write(f"{user['tag']} {user['user_id'] or '-'} {node_names}\n")
    for row in payload["unreachable"]:
        sys.stdout.write(f"UNREACHABLE {row['name']}\n")
    if not payload["ok"]:
        sys.stdout.write(f"STATE {OP_PARTIAL}\n")
    return code


def cmd_user_show(args: argparse.Namespace) -> int:
    tag = args.tag
    validate_name(tag)
    registry = load_registry()
    nodes = _selected_nodes(registry, include_all=False)
    as_json = bool(getattr(args, "as_json", False))
    rows: list[dict[str, Any]] = []
    user_ids: set[str] = set()
    unreachable = False

    for node in nodes:
        ssh_state, payload, detail = ssh_remote_json(
            node, ["vcl", "user", "show", tag, "--json"]
        )
        if ssh_state != "OK":
            unreachable = True
            rows.append(
                {
                    "name": node["name"],
                    "status": "UNREACHABLE",
                    "enabled": None,
                    "user_id": None,
                    "credential_id": None,
                    "error": _ssh_error(255, detail),
                }
            )
            continue
        if not isinstance(payload, dict) or payload.get("tag") != tag:
            rows.append(
                {
                    "name": node["name"],
                    "status": "MISSING",
                    "enabled": None,
                    "user_id": None,
                    "credential_id": None,
                    "error": None,
                }
            )
            continue
        uid = payload.get("user_id") or ""
        if uid:
            user_ids.add(str(uid))
        cred_id = _active_credential_id(payload)
        enabled = bool(payload.get("enabled"))
        cred_status = "active" if cred_id else "none"
        rows.append(
            {
                "name": node["name"],
                "status": cred_status if enabled else "disabled",
                "enabled": enabled,
                "user_id": uid or None,
                "credential_id": cred_id,
                "error": None,
            }
        )

    conflict = len(user_ids) > 1
    global_uid = next(iter(user_ids)) if len(user_ids) == 1 else None
    found = any(row.get("user_id") for row in rows)
    payload = {
        "schema_version": MUTATION_SCHEMA_VERSION,
        "ok": (not conflict) and (not unreachable) and found,
        "tag": tag,
        "user_id": global_uid,
        "conflict": conflict,
        "nodes": rows,
    }

    if conflict:
        if as_json:
            sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        else:
            sys.stderr.write(
                f"vcl-fleet: tag {tag} has conflicting user_id across nodes\n"
            )
            for row in rows:
                if row.get("user_id"):
                    sys.stderr.write(f"  {row['name']}: {row['user_id']}\n")
        return 1

    if as_json:
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        if unreachable:
            return MUTATION_EXIT_PARTIAL
        return 0 if found else 1

    if not found and not unreachable:
        die(f"user not found: {tag}")

    sys.stdout.write(f"TAG {tag}\n")
    if global_uid:
        sys.stdout.write(f"USER_ID {global_uid}\n")
    sys.stdout.write("NODE CREDENTIAL_ID ENABLED STATUS\n")
    for row in rows:
        enabled = row.get("enabled")
        if enabled is True:
            enabled_s = "true"
        elif enabled is False:
            enabled_s = "false"
        else:
            enabled_s = "-"
        sys.stdout.write(
            f"{row['name']} {row.get('credential_id') or '-'} "
            f"{enabled_s} {row['status']}\n"
        )
    if unreachable:
        sys.stdout.write(f"STATE {OP_PARTIAL}\n")
        return MUTATION_EXIT_PARTIAL
    return 0


def _require_single_node_flag(args: argparse.Namespace, action: str) -> str:
    name = getattr(args, "node", None)
    if not name:
        if action == "disable":
            die("refusing fleet-wide disable; pass --node")
        die(f"refusing fleet-wide {action}; pass --node")
    return str(name)


def cmd_user_enable_disable(args: argparse.Namespace, *, enabled: bool) -> int:
    action = "enable" if enabled else "disable"
    tag = args.tag
    validate_name(tag)
    node_name = _require_single_node_flag(args, action)
    node = require_enabled_node(load_registry(), node_name)
    as_json = bool(getattr(args, "as_json", False))
    ssh_state, payload, detail = ssh_remote_json(
        node,
        ["vcl", "user", action, tag, "--json"],
        timeout=SSH_MUTATION_TIMEOUT_SECONDS,
        require_exit_0=True,
    )
    if ssh_state != "OK":
        die(_ssh_error(255, detail))
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        err = ""
        if isinstance(payload, dict):
            err = str(payload.get("error") or "")
        die(err or detail or f"user {action} failed on {node_name}")
    doc = {
        "schema_version": MUTATION_SCHEMA_VERSION,
        "ok": True,
        "tag": tag,
        "node": node_name,
        "user_id": payload.get("user_id"),
        "enabled": bool(payload.get("enabled", enabled)),
    }
    if as_json:
        sys.stdout.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        return 0
    state = "enabled" if doc["enabled"] else "disabled"
    sys.stdout.write(f"{tag} {state} on {node_name}\n")
    return 0


def cmd_user_rotate(args: argparse.Namespace) -> int:
    tag = args.tag
    validate_name(tag)
    node_name = _require_single_node_flag(args, "rotate")
    node = require_enabled_node(load_registry(), node_name)
    as_json = bool(getattr(args, "as_json", False))
    ssh_state, payload, detail = ssh_remote_json(
        node,
        ["vcl", "user", "rotate", tag, "--json"],
        timeout=SSH_MUTATION_TIMEOUT_SECONDS,
        require_exit_0=True,
    )
    if ssh_state != "OK":
        die(_ssh_error(255, detail))
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        err = ""
        if isinstance(payload, dict):
            err = str(payload.get("error") or "")
        die(err or detail or f"user rotate failed on {node_name}")
    cred_id = payload.get("credential_id")
    uri = payload.get("vless_uri")
    doc = {
        "schema_version": MUTATION_SCHEMA_VERSION,
        "ok": True,
        "tag": tag,
        "node": node_name,
        "user_id": payload.get("user_id"),
        "credential_id": cred_id,
        "vless_uri": uri,
        "status": payload.get("status") or "active",
        "enabled": payload.get("enabled"),
    }
    if as_json:
        warn_credentials("stdout")
        sys.stdout.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        return 0
    row = {
        "name": node_name,
        "credential_id": cred_id,
        "vless_uri": uri,
    }
    csv_text = format_credential_csv(tag, [row])
    output = getattr(args, "output", None)
    if output:
        write_private_file(Path(output), csv_text)
        warn_credentials(str(output))
    warn_credentials("stdout")
    sys.stdout.write(csv_text)
    return 0


def load_import_csv(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read the import CSV. Returns (rows, errors). Does not SSH."""
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            raw_fields = list(reader.fieldnames or [])
            fieldnames = tuple(h.strip() for h in raw_fields if h and str(h).strip())
            if fieldnames != CSV_IMPORT_HEADER:
                got = ",".join(fieldnames) if fieldnames else "(empty)"
                return [], [
                    "CSV header must be tag,display_name,department,nodes "
                    f"(got {got})"
                ]
            for i, raw in enumerate(reader, start=2):
                if None in raw:
                    extras = raw.get(None)
                    extra_s = (
                        ",".join(str(x) for x in extras)
                        if isinstance(extras, (list, tuple))
                        else str(extras or "")
                    )
                    errors.append(
                        f"line {i}: extra CSV fields ({extra_s}); "
                        'quote multi-node cells like "lax,tokyo"'
                    )
                    continue
                row = {
                    (k.strip() if isinstance(k, str) else k): (
                        v.strip() if isinstance(v, str) else (v or "")
                    )
                    for k, v in raw.items()
                    if k
                }
                tag = str(row.get("tag") or "")
                display_name = str(row.get("display_name") or "")
                department = str(row.get("department") or "")
                nodes_raw = str(row.get("nodes") or "")
                if not tag and not display_name and not department and not nodes_raw:
                    continue
                rows.append(
                    {
                        "line": i,
                        "tag": tag,
                        "display_name": display_name,
                        "department": department,
                        "nodes_raw": nodes_raw,
                        "nodes": [],
                    }
                )
    except FileNotFoundError:
        die(f"import file not found: {path}")
    except OSError as exc:
        die(f"cannot read import file: {exc}")
    return rows, errors


def validate_import_rows(
    rows: list[dict[str, Any]], registry: dict[str, Any]
) -> list[str]:
    """Collect every row error. Mutates row['nodes'] on successful cell parse."""
    errors: list[str] = []
    seen: dict[str, int] = {}
    for row in rows:
        line = int(row["line"])
        tag = str(row.get("tag") or "")
        if not tag:
            errors.append(f"line {line}: missing tag")
        elif not NAME_RE.fullmatch(tag):
            errors.append(f'line {line}: invalid tag "{tag}"')
        elif tag in seen:
            errors.append(f"line {line}: duplicate tag {tag}")
        else:
            seen[tag] = line

        display_err = _user_metadata_error(
            str(row.get("display_name") or ""), "display_name"
        )
        if display_err:
            errors.append(f"line {line}: {display_err}")
        dept_err = _user_metadata_error(str(row.get("department") or ""), "department")
        if dept_err:
            errors.append(f"line {line}: {dept_err}")

        names, err = parse_nodes_cell(str(row.get("nodes_raw") or ""))
        if err:
            errors.append(f"line {line}: {err}")
            continue
        row["nodes"] = names
        for name in names:
            node = find_by_name(registry, name)
            msg = node_importable(node, name)
            if msg:
                errors.append(f"line {line}: {msg}")
    return errors


def format_import_plan(rows: list[dict[str, Any]]) -> str:
    lines = [
        "User import dry-run",
        "",
        f"Input rows:  {len(rows)}",
        "TAG DISPLAY_NAME DEPARTMENT NODES",
    ]
    for row in rows:
        display = row.get("display_name") or "-"
        dept = row.get("department") or "-"
        nodes = ",".join(row.get("nodes") or [])
        lines.append(f"{row['tag']} {display} {dept} {nodes}")
    lines.append("")
    lines.append("No changes were made.")
    return "\n".join(lines) + "\n"


def format_import_report(reports: list[dict[str, Any]]) -> str:
    """Human table for a multi-user import: STATE, per tag/node, remediation."""
    if reports and all(doc.get("state") == OP_SUCCESS for doc in reports):
        state = OP_SUCCESS
    elif not reports:
        state = OP_SUCCESS
    else:
        state = OP_PARTIAL
    lines = [f"STATE {state}", "operation: user.import", ""]
    lines.append(f"{'TAG':<12} {'NODE':<12} STATUS")
    rem: list[str] = []
    for doc in reports:
        tag = str(doc.get("tag") or "")
        user_id = str(doc.get("user_id") or "")
        for row in doc.get("nodes") or []:
            name = _node_name(row)
            status = _node_status(row)
            extra = ""
            if status == OP_FAILED and row.get("error"):
                extra = f"  {row['error']}"
            lines.append(f"{tag:<12} {name:<12} {status}{extra}")
            if status != OP_SUCCESS:
                rem.extend(remediation_user_add(tag, user_id, [name]))
    if rem:
        lines.append("")
        lines.append("Remediation:")
        for cmd in rem:
            lines.append(f"  {cmd}")
    return "\n".join(lines) + "\n"


def _print_import_errors(errors: list[str]) -> int:
    sys.stderr.write(
        "vcl-fleet: user import validation failed; no changes were made.\n"
    )
    for err in errors:
        sys.stderr.write(f"  {err}\n")
    return 1


def cmd_user_import(args: argparse.Namespace) -> int:
    path = Path(args.csv_file)
    registry = load_registry()
    rows, errors = load_import_csv(path)
    errors.extend(validate_import_rows(rows, registry))
    if errors:
        return _print_import_errors(errors)

    if bool(getattr(args, "dry_run", False)):
        sys.stdout.write(format_import_plan(rows))
        return 0

    reports: list[dict[str, Any]] = []
    cred_entries: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        tag = str(row["tag"])
        user_id = str(uuid.uuid4())
        nodes = [require_enabled_node(registry, name) for name in row["nodes"]]
        sys.stderr.write(
            f"user.import {tag} {OP_PLANNED} nodes={','.join(n['name'] for n in nodes)}\n"
        )
        results: list[dict[str, Any]] = []
        for node in nodes:
            sys.stderr.write(f"user.import {tag} {OP_APPLYING} {node['name']}\n")
            results.append(
                provision_user_on_node(
                    node,
                    tag=tag,
                    user_id=user_id,
                    display_name=row["display_name"] or None,
                    department=row["department"] or None,
                )
            )
        doc = mutation_report(
            results, tag=tag, user_id=user_id, operation="user.import"
        )
        reports.append(doc)
        for node_row in doc["nodes"]:
            if node_row.get("status") == OP_SUCCESS:
                cred_entries.append((tag, node_row))

    csv_text = format_credential_entries(cred_entries) if cred_entries else ""
    output = getattr(args, "output", None)
    if output and csv_text:
        write_private_file(Path(output), csv_text)
        warn_credentials(str(output))

    combined = (
        OP_SUCCESS
        if (not reports or all(doc.get("state") == OP_SUCCESS for doc in reports))
        else OP_PARTIAL
    )
    if combined == OP_SUCCESS:
        if csv_text:
            warn_credentials("stdout")
            sys.stdout.write(csv_text)
        sys.stderr.write(f"STATE {OP_SUCCESS}\n")
        return MUTATION_EXIT_SUCCESS

    sys.stdout.write(format_import_report(reports))
    if csv_text:
        warn_credentials("stdout")
        sys.stdout.write(csv_text)
    return MUTATION_EXIT_PARTIAL


def _write_csv_text(fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=list(fieldnames), lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def cmd_user_export(args: argparse.Namespace) -> int:
    credentials = bool(getattr(args, "credentials", False))
    output = getattr(args, "output", None)
    if credentials and not output:
        die("user export --credentials requires --output FILE")

    registry = load_registry()
    nodes = _selected_nodes(registry, include_all=False)
    unreachable: list[dict[str, Any]] = []
    meta_rows: list[dict[str, Any]] = []
    cred_entries: list[tuple[str, dict[str, Any]]] = []

    for node in nodes:
        users, err = _list_users_on_node(node)
        if err is not None:
            unreachable.append({"name": node["name"], "error": err})
            continue
        for user in users or []:
            tag = str(user.get("tag") or "")
            uid = str(user.get("user_id") or "")
            enabled = bool(user.get("enabled"))
            meta_rows.append(
                {
                    "tag": tag,
                    "display_name": user.get("display_name") or "",
                    "department": user.get("department") or "",
                    "user_id": uid,
                    "node": node["name"],
                    "enabled": "true" if enabled else "false",
                }
            )
            if not credentials or not tag:
                continue
            cred_id = user.get("active_credential_id") or ""
            uri = ssh_user_link_uri(node, tag)
            if not cred_id and not uri:
                continue
            cred_entries.append(
                (
                    tag,
                    {
                        "name": node["name"],
                        "credential_id": cred_id,
                        "vless_uri": uri or "",
                    },
                )
            )

    if credentials:
        csv_text = format_credential_entries(cred_entries)
        write_private_file(Path(str(output)), csv_text)
        warn_credentials(str(output))
        sys.stdout.write(f"Credential CSV written to {output}\n")
        if unreachable:
            for row in unreachable:
                sys.stderr.write(
                    f"vcl-fleet: UNREACHABLE {row['name']}: {row.get('error') or ''}\n"
                )
            return MUTATION_EXIT_PARTIAL
        return 0

    csv_text = _write_csv_text(CSV_EXPORT_META_HEADER, meta_rows)
    if output:
        Path(output).write_text(
            csv_text if csv_text.endswith("\n") else csv_text + "\n",
            encoding="utf-8",
        )
        sys.stdout.write(f"Users CSV written to {output}\n")
    else:
        sys.stdout.write(csv_text)
    if unreachable:
        for row in unreachable:
            sys.stderr.write(
                f"vcl-fleet: UNREACHABLE {row['name']}: {row.get('error') or ''}\n"
            )
        return MUTATION_EXIT_PARTIAL
    return 0


def _sync_result(
    node: dict[str, Any],
    *,
    status: str,
    after: int = 0,
    last_event_id: int = 0,
    last_export_seq: int = 0,
    inserted: int = 0,
    updated: int = 0,
    ignored: int = 0,
    skipped_unlabeled: int = 0,
    instance_id: Optional[str] = None,
    error: Optional[str] = None,
    earliest: Any = None,
    max_event_id: Any = None,
    max_export_seq: Any = None,
    pruned_max_export_seq: Any = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": node["name"],
        "node_id": node["node_id"],
        "instance_id": instance_id,
        "status": status,
        "after": after,
        "last_event_id": last_event_id,
        "last_export_seq": last_export_seq,
        "inserted": inserted,
        "updated": updated,
        "ignored": ignored,
        "skipped_unlabeled": skipped_unlabeled,
        "error": error,
        "earliest_available_event_id": earliest,
        "max_event_id": max_event_id,
        "max_export_seq": max_export_seq,
        "pruned_max_export_seq": pruned_max_export_seq,
        "remediation": None,
    }
    if status == SYNC_STATUS_EXPIRED or error in (
        "CURSOR_AHEAD",
        "CURSOR_PROTOCOL_MISMATCH",
    ):
        row["remediation"] = remediation_sync_reseed(node["name"])
    elif status == SYNC_STATUS_ERROR and error and (
        "node_id" in error or "instance_id" in error or "unlabeled" in error
        or "missing node_id" in error
    ):
        row["remediation"] = remediation_sync_reseed(node["name"])
    return row


def sync_target_nodes(
    registry: dict[str, Any],
    *,
    node_name: Optional[str],
    include_all: bool,
    reseed_name: Optional[str],
) -> list[dict[str, Any]]:
    if node_name and include_all:
        die("--node and --all are mutually exclusive")
    if reseed_name and node_name and reseed_name != node_name:
        die("--reseed must target the same node as --node")
    if node_name:
        validate_name(node_name)
        return [require_enabled_node(registry, node_name)]
    if reseed_name and not include_all:
        validate_name(reseed_name)
        return [require_enabled_node(registry, reseed_name)]
    return _selected_nodes(registry, include_all)


def ssh_audit_export(
    node: dict[str, Any],
    after: int,
    *,
    stamp_identity: bool = False,
) -> subprocess.CompletedProcess[str]:
    remote = ["vcl", "audit", "export", "--after", str(after), "--jsonl"]
    if stamp_identity:
        remote.append("--stamp-identity")
    return ssh_run(
        node["ssh_host"],
        node["ssh_user"],
        node["ssh_port"],
        remote,
        batch=True,
        identity_file=_node_identity_file(node),
        timeout=SSH_TIMEOUT_SECONDS,
    )


def sync_one_node(
    conn: sqlite3.Connection,
    node: dict[str, Any],
    *,
    now_iso: str,
    stamp_identity: bool = False,
) -> dict[str, Any]:
    """Sync one node. Cursor advances only after a successful import commit.

    Replace updates cursor.instance_id and keeps last_export_seq. This
    function never reseeds: an instance_id change emits WARN
    `instance changed, node_id stable` and continues from the existing
    cursor (plan §0.9). Auto-reseed is forbidden. CURSOR_AHEAD (stale
    cursor past remote MAX) and lying export meta fail closed: no import,
    cursor unchanged, operator is pointed at --reseed.
    Old event_id cursors fail with CURSOR_PROTOCOL_MISMATCH until reseed.
    """
    node_id = node["node_id"]
    cursor_row = read_sync_cursor_row(conn, node_id)
    after = int(cursor_row["last_export_seq"]) if cursor_row is not None else 0
    prior_event = int(cursor_row["last_event_id"]) if cursor_row is not None else 0
    prior_instance = None
    if cursor_row is not None:
        prior_instance = cursor_row["instance_id"]
        kind = _optional_text(cursor_row["cursor_kind"]) or CURSOR_KIND_EVENT_ID
        if kind != CURSOR_KIND_EXPORT_SEQ:
            return _sync_result(
                node,
                status=SYNC_STATUS_ERROR,
                after=after,
                last_event_id=prior_event,
                last_export_seq=after,
                instance_id=prior_instance,
                error="CURSOR_PROTOCOL_MISMATCH",
            )

    life = node_lifecycle_status(node)
    if life == NODE_STATUS_RETIRED:
        return _sync_result(
            node,
            status="RETIRED",
            after=after,
            last_event_id=prior_event,
            last_export_seq=after,
        )
    if life != NODE_STATUS_ACTIVE or not node.get("enabled", True):
        return _sync_result(
            node,
            status="DISABLED",
            after=after,
            last_event_id=prior_event,
            last_export_seq=after,
        )

    ssh_state, ident, ident_detail = ssh_remote_json(
        node, ["vcl", "identity", "--json"]
    )
    if ssh_state != "OK" or not isinstance(ident, dict):
        last_export_seq = mark_cursor_status(
            conn,
            node_id,
            instance_id=None,
            status=SYNC_STATUS_ERROR,
            now_iso=now_iso,
        )
        return _sync_result(
            node,
            status=SYNC_STATUS_ERROR,
            after=after,
            last_event_id=_cursor_last_event_id(conn, node_id),
            last_export_seq=last_export_seq,
            error=ident_detail or "identity unreachable",
        )

    remote_nid = ident.get("node_id")
    if not isinstance(remote_nid, str) or remote_nid != node_id:
        last_export_seq = mark_cursor_status(
            conn,
            node_id,
            instance_id=_optional_text(ident.get("instance_id")),
            status=SYNC_STATUS_ERROR,
            now_iso=now_iso,
        )
        return _sync_result(
            node,
            status=SYNC_STATUS_ERROR,
            after=after,
            last_event_id=_cursor_last_event_id(conn, node_id),
            last_export_seq=last_export_seq,
            instance_id=_optional_text(ident.get("instance_id")),
            error="registry node_id mismatch",
        )

    remote_iid = _optional_text(ident.get("instance_id"))
    if prior_instance and remote_iid and prior_instance != remote_iid:
        sys.stderr.write(
            f"WARNING: {node['name']}: instance changed, node_id stable "
            f"({prior_instance} → {remote_iid})\n"
        )
    if remote_iid:
        record_instance(
            conn,
            node_id,
            remote_iid,
            endpoint=None,
            ssh_host=_optional_text(node.get("ssh_host")),
            now_iso=now_iso,
        )

    proc = ssh_audit_export(node, after, stamp_identity=stamp_identity)
    detail = _ssh_failure_detail(proc)
    meta = parse_export_meta(proc.stderr or "")
    earliest = None if meta is None else meta.get("earliest_available_event_id")
    max_event_id = None if meta is None else meta.get("max_event_id")
    max_export_seq = None if meta is None else meta.get("max_export_seq")
    pruned_max = None if meta is None else meta.get("pruned_max_export_seq")
    meta_error = None
    if isinstance(meta, dict):
        raw_err = meta.get("error")
        if isinstance(raw_err, str) and raw_err.strip():
            meta_error = raw_err.strip()

    def _fail(
        status: str,
        error: Optional[str],
        *,
        cursor_status: str = SYNC_STATUS_ERROR,
    ) -> dict[str, Any]:
        last_export_seq = mark_cursor_status(
            conn,
            node_id,
            instance_id=remote_iid,
            status=cursor_status,
            now_iso=now_iso,
        )
        return _sync_result(
            node,
            status=status,
            after=after,
            last_event_id=_cursor_last_event_id(conn, node_id),
            last_export_seq=last_export_seq,
            instance_id=remote_iid,
            error=error,
            earliest=earliest,
            max_event_id=max_event_id,
            max_export_seq=max_export_seq,
            pruned_max_export_seq=pruned_max,
        )

    if proc.returncode == 255:
        return _fail(SYNC_STATUS_ERROR, detail or "ssh unreachable")

    if meta_error == "CURSOR_EXPIRED":
        return _fail(
            SYNC_STATUS_EXPIRED,
            "CURSOR_EXPIRED",
            cursor_status=SYNC_STATUS_EXPIRED,
        )

    if meta_error == "CURSOR_AHEAD":
        return _fail(SYNC_STATUS_ERROR, "CURSOR_AHEAD")

    if proc.returncode != 0:
        return _fail(
            SYNC_STATUS_ERROR,
            detail or f"audit export exit {proc.returncode}",
        )

    try:
        rows = parse_export_jsonl(proc.stdout or "")
    except ValueError as exc:
        return _fail(SYNC_STATUS_ERROR, str(exc))

    try:
        next_cursor = validate_export_batch(
            meta,
            rows,
            expected_after=after,
            expected_node_id=node_id,
            expected_instance_id=remote_iid,
        )
    except ValueError as exc:
        return _fail(SYNC_STATUS_ERROR, str(exc))

    try:
        imported = import_export_jsonl(
            node_id,
            remote_iid,
            rows,
            now_iso,
            conn=conn,
            next_cursor=next_cursor,
        )
    except SystemExit as exc:
        return _fail(
            SYNC_STATUS_ERROR,
            f"audit import failed (exit {exc.code})",
        )

    return _sync_result(
        node,
        status=SYNC_STATUS_OK,
        after=after,
        last_event_id=int(imported["last_event_id"]),
        last_export_seq=int(imported["last_export_seq"]),
        inserted=int(imported["inserted"]),
        updated=int(imported.get("updated", 0)),
        ignored=int(imported["ignored"]),
        skipped_unlabeled=int(imported["skipped_unlabeled"]),
        instance_id=remote_iid,
        earliest=earliest,
        max_event_id=max_event_id,
        max_export_seq=max_export_seq,
        pruned_max_export_seq=pruned_max,
    )


def format_sync_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        f"{'NAME':<8} {'STATUS':<8} {'AFTER':<8} {'CURSOR':<8} "
        f"{'INSERTED':<8} UPDATED"
    ]
    remediations: list[str] = []
    for row in rows:
        lines.append(
            f"{row['name']:<8} {row['status']:<8} {row.get('after', 0):<8} "
            f"{row.get('last_export_seq', row.get('last_event_id', 0)):<8} "
            f"{row.get('inserted', 0):<8} {row.get('updated', 0)}"
        )
        if row["status"] == SYNC_STATUS_EXPIRED:
            lines.append(
                f"  CURSOR_EXPIRED after={row.get('after')} "
                f"pruned_max_export_seq="
                f"{row.get('pruned_max_export_seq')}"
            )
            if row.get("remediation"):
                remediations.append(str(row["remediation"]))
        elif row.get("error") == "CURSOR_AHEAD":
            lines.append(
                f"  CURSOR_AHEAD after={row.get('after')} "
                f"max_export_seq={row.get('max_export_seq')}; "
                "stale cursor vs restored DB; reseed"
            )
            if row.get("remediation"):
                remediations.append(str(row["remediation"]))
        elif row.get("error") == "CURSOR_PROTOCOL_MISMATCH":
            lines.append(
                f"  {remediation_protocol_mismatch(row['name'])}"
            )
            if row.get("remediation"):
                remediations.append(str(row["remediation"]))
        elif row["status"] == SYNC_STATUS_ERROR and row.get("error"):
            lines.append(f"  ERROR: {row['error']}")
    if remediations:
        lines.append("Remediation:")
        for cmd in remediations:
            lines.append(f"  {cmd}")
    return "\n".join(lines) + "\n"


def sync_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [
        row
        for row in rows
        if row.get("status") in (SYNC_STATUS_EXPIRED, SYNC_STATUS_ERROR)
    ]
    state = OP_SUCCESS if not failed else OP_PARTIAL
    remediation = [
        row["remediation"]
        for row in rows
        if row.get("remediation")
    ]
    return {
        "schema_version": SYNC_JSON_SCHEMA_VERSION,
        "operation": "sync",
        "ok": state == OP_SUCCESS,
        "state": state,
        "nodes": rows,
        "remediation": remediation,
    }


def run_sync_payload(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    """Run sync (optional reseed); return (exit_code, report) without stdout.

    Callers that mutate the fleet must hold ``fleet_op_lock`` (``cmd_sync``
    and UI ``api_sync`` do).
    """
    registry = load_registry()
    node_name = (getattr(args, "node", None) or "").strip() or None
    reseed_name = (getattr(args, "reseed", None) or "").strip() or None
    include_all = bool(getattr(args, "all", False))
    as_json = bool(getattr(args, "as_json", False))
    now_iso = format_utc(datetime.now(timezone.utc))

    if reseed_name:
        validate_name(reseed_name)

    targets = sync_target_nodes(
        registry,
        node_name=node_name,
        include_all=include_all,
        reseed_name=reseed_name,
    )

    conn = open_fleet_db()
    try:
        if reseed_name:
            seed_node = require_enabled_node(registry, reseed_name)
            reseed_node_local(
                conn,
                seed_node["node_id"],
                now_iso=now_iso,
            )
            if not as_json:
                sys.stderr.write(
                    f"reseed {reseed_name}: local audit_events and "
                    "daily_usage deleted; cursor=0\n"
                )
        rows = [
            sync_one_node(
                conn,
                node,
                now_iso=now_iso,
                stamp_identity=bool(reseed_name and node.get("name") == reseed_name),
            )
            for node in targets
        ]
    finally:
        conn.close()

    doc = sync_report(rows)
    code = 0 if doc["state"] == OP_SUCCESS else MUTATION_EXIT_PARTIAL
    return code, doc


@with_fleet_op_lock
def cmd_sync(args: argparse.Namespace) -> int:
    as_json = bool(getattr(args, "as_json", False))
    code, doc = run_sync_payload(args)
    if as_json:
        sys.stdout.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(format_sync_table(doc["nodes"]))
    return code


_AUDIT_MOD: Optional[Any] = None
_BACKUP_MOD: Optional[Any] = None


def load_audit_module() -> Any:
    """Load lib/vincula-audit.py for parse_rfc3339 / interval-overlap SQL."""
    global _AUDIT_MOD
    if _AUDIT_MOD is not None:
        return _AUDIT_MOD
    _AUDIT_MOD = _load_controller_sibling("vincula_audit", "vincula-audit.py")
    return _AUDIT_MOD


def load_backup_module() -> Any:
    """Load lib/vincula-backup.py for local backup verify (no second parser)."""
    global _BACKUP_MOD
    if _BACKUP_MOD is not None:
        return _BACKUP_MOD
    _BACKUP_MOD = _load_controller_sibling("vincula_backup", "vincula-backup.py")
    return _BACKUP_MOD


def fleet_utc_today() -> date:
    """UTC calendar date. Tests inject VCL_FLEET_STATS_NOW=YYYY-MM-DD."""
    env = os.environ.get("VCL_FLEET_STATS_NOW", "").strip()
    if env:
        try:
            return date.fromisoformat(env)
        except ValueError:
            die(f"invalid VCL_FLEET_STATS_NOW: {env}")
    return datetime.now(timezone.utc).date()


def stats_date_window(days: int) -> tuple[str, str]:
    """Inclusive UTC day window ending today: [today-(days-1), today]."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        die("--days must be an integer >= 1")
    end = fleet_utc_today()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def node_display_name(registry: dict[str, Any], node_id: Optional[str]) -> str:
    if not node_id:
        return "-"
    node = find_by_node_id(registry, node_id)
    if node is not None:
        return str(node["name"])
    return str(node_id)


def instance_display(instance_id: Optional[str]) -> str:
    text = _optional_text(instance_id)
    return text if text else "-"


def destination_display(
    host: Optional[str], ip: Optional[str] = None
) -> str:
    return _optional_text(host) or _optional_text(ip) or "-"


def _sql_like_contains(needle: str) -> str:
    """LIKE pattern for substring match; `%` `_` `\\` are literals."""
    escaped = (
        needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def resolve_fleet_user_id(registry: dict[str, Any], tag: str) -> str:
    """Resolve TAG to one fleet-global user_id via per-node `vcl user list`.

    Conflicting user_ids across reachable nodes → die (no silent merge).
    """
    validate_name(tag)
    found: dict[str, list[str]] = {}
    reachable = False
    for node in _selected_nodes(registry, include_all=False):
        users, err = _list_users_on_node(node)
        if err is not None:
            continue
        reachable = True
        for user in users or []:
            if str(user.get("tag") or "") != tag:
                continue
            uid = _optional_text(user.get("user_id"))
            if not uid:
                continue
            found.setdefault(uid, []).append(str(node["name"]))
    if len(found) > 1:
        detail = "; ".join(
            f"{uid} on {','.join(names)}" for uid, names in found.items()
        )
        die(f"tag {tag} has conflicting user_id across nodes: {detail}")
    if len(found) == 1:
        return next(iter(found))
    if not reachable:
        die(f"cannot resolve user {tag}: nodes unreachable")
    die(f"unknown user tag: {tag}")
    raise SystemExit(1)


def _row_int(row: sqlite3.Row, key: str) -> int:
    value = row[key]
    if value is None:
        return 0
    return int(value)


def query_fleet_audit(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    query_from: str,
    query_to: str,
    node_id: Optional[str] = None,
    destination_contains: Optional[str] = None,
    limit: Optional[int] = None,
    after_started_at: Optional[str] = None,
    after_event_id: Optional[int] = None,
    after_node_id: Optional[str] = None,
) -> list[sqlite3.Row]:
    """Query audit_events with interval-overlap.

    Optional ``limit`` (+1 fetch for truncation detection) and keyset cursor
    ``(after_started_at, after_event_id, after_node_id)`` matching
    ORDER BY started_at, event_id, node_id.

    ``destination_contains`` is applied in SQL (same display as
    ``destination_display``) *before* ORDER BY / LIMIT so pagination is not
    a post-filter over a truncated page.
    """
    audit = load_audit_module()
    where = [
        audit.interval_overlap_sql(),
        "user_id = ?",
        LABELED_NODE_SQL,
    ]
    params: list[Any] = [query_to, query_from, user_id]
    if node_id:
        where.append("node_id = ?")
        params.append(node_id)
    dest = (destination_contains or "").strip().lower()
    if dest:
        where.append(f"{AUDIT_DESTINATION_SQL} LIKE ? ESCAPE '\\'")
        params.append(_sql_like_contains(dest))
    if after_started_at is not None:
        if after_event_id is None or not after_node_id:
            die("audit cursor requires after_started_at, after_event_id, after_node_id")
        where.append(
            "("
            "started_at > ? OR "
            "(started_at = ? AND event_id > ?) OR "
            "(started_at = ? AND event_id = ? AND node_id > ?)"
            ")"
        )
        params.extend(
            [
                after_started_at,
                after_started_at,
                int(after_event_id),
                after_started_at,
                int(after_event_id),
                after_node_id,
            ]
        )
    sql = (
        "SELECT event_id, node_id, instance_id, user_id, user_tag, "
        "destination_host, destination_ip, destination_port, network, "
        "upload_bytes, download_bytes, started_at, last_seen_at, closed_at "
        "FROM audit_events WHERE "
        + " AND ".join(where)
        + " ORDER BY started_at ASC, event_id ASC, node_id ASC"
    )
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            die("audit limit must be an integer >= 1")
        sql += " LIMIT ?"
        params.append(int(limit))
    try:
        return list(conn.execute(sql, params).fetchall())
    except sqlite3.Error as exc:
        die(f"fleet audit query failed: {exc}")
        raise SystemExit(1)


def format_audit_table(
    rows: list[dict[str, Any]], *, query_from: str, query_to: str, tag: str
) -> str:
    lines = [
        f"Window: {query_from} → {query_to} (interval-overlap, UTC)",
        f"User: {tag}",
        "TIME NODE INSTANCE DESTINATION TRAFFIC",
    ]
    for row in rows:
        lines.append(
            f"{row['time']} {row['node']} {row['instance']} "
            f"{row['destination']} {row['traffic']}"
        )
    if not rows:
        lines.append("(no connections in window)")
    return "\n".join(lines) + "\n"


def cmd_audit_user(args: argparse.Namespace) -> int:
    tag = args.tag
    validate_name(tag)
    registry = load_registry()
    audit = load_audit_module()
    query_from = audit.parse_rfc3339(args.query_from)
    query_to = audit.parse_rfc3339(args.query_to)
    if query_from > query_to:
        die("--from must not be after --to")
    user_id = resolve_fleet_user_id(registry, tag)
    node_name = (getattr(args, "node", None) or "").strip() or None
    node_id = None
    if node_name:
        validate_name(node_name)
        node_id = require_node(registry, node_name)["node_id"]
    conn = open_fleet_db()
    try:
        raw_rows = query_fleet_audit(
            conn,
            user_id=user_id,
            query_from=query_from,
            query_to=query_to,
            node_id=node_id,
        )
    finally:
        conn.close()

    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        upload = _row_int(raw, "upload_bytes")
        download = _row_int(raw, "download_bytes")
        inst = _optional_text(raw["instance_id"])
        rows.append(
            {
                "time": raw["started_at"],
                "node": node_display_name(registry, raw["node_id"]),
                "instance": instance_display(inst),
                "destination": destination_display(
                    raw["destination_host"], raw["destination_ip"]
                ),
                "traffic": upload + download,
                "node_id": raw["node_id"],
                "instance_id": inst,
                "user_id": raw["user_id"],
                "event_id": int(raw["event_id"]),
                "user_tag": raw["user_tag"],
                "upload_bytes": upload,
                "download_bytes": download,
                "started_at": raw["started_at"],
                "last_seen_at": raw["last_seen_at"],
                "closed_at": raw["closed_at"],
            }
        )
    if getattr(args, "as_json", False):
        payload = {
            "schema_version": AUDIT_JSON_SCHEMA_VERSION,
            "tag": tag,
            "user_id": user_id,
            "from": query_from,
            "to": query_to,
            "node": node_name,
            "rows": rows,
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0
    sys.stdout.write(
        format_audit_table(
            rows, query_from=query_from, query_to=query_to, tag=tag
        )
    )
    return 0


def _stats_row_from_sql(
    registry: dict[str, Any], raw: sqlite3.Row
) -> dict[str, Any]:
    keys = set(raw.keys())
    upload = _row_int(raw, "upload_bytes")
    download = _row_int(raw, "download_bytes")
    node_id = str(raw["node_id"])
    inst = _optional_text(raw["instance_id"]) if "instance_id" in keys else None
    tag = _optional_text(raw["user_tag"]) if "user_tag" in keys else None
    host = None
    if "destination_host" in keys:
        host = _optional_text(raw["destination_host"])
    user_id = _optional_text(raw["user_id"]) if "user_id" in keys else None
    out: dict[str, Any] = {
        "node": node_display_name(registry, node_id),
        "node_id": node_id,
        "instance_id": inst,
        "upload_bytes": upload,
        "download_bytes": download,
        "bytes": upload + download,
        "connection_count": _row_int(raw, "connection_count"),
    }
    if "user_id" in keys:
        out["user_id"] = user_id
    if "user_tag" in keys:
        out["user_tag"] = tag
    if "destination_host" in keys:
        out["destination_host"] = host or "(unknown)"
    return out


def _stats_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_node: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    upload = download = connections = 0
    for row in rows:
        nid = str(row["node_id"])
        upload += int(row["upload_bytes"])
        download += int(row["download_bytes"])
        connections += int(row["connection_count"])
        if nid not in by_node:
            by_node[nid] = {
                "node": row["node"],
                "node_id": nid,
                "upload_bytes": 0,
                "download_bytes": 0,
                "bytes": 0,
                "connection_count": 0,
            }
            order.append(nid)
        rec = by_node[nid]
        rec["upload_bytes"] += int(row["upload_bytes"])
        rec["download_bytes"] += int(row["download_bytes"])
        rec["bytes"] += int(row["bytes"])
        rec["connection_count"] += int(row["connection_count"])
    return {
        "upload_bytes": upload,
        "download_bytes": download,
        "bytes": upload + download,
        "connection_count": connections,
        "by_node": [by_node[nid] for nid in order],
    }


def query_daily_grouped(
    conn: sqlite3.Connection,
    *,
    start: str,
    end: str,
    group_by: Sequence[str],
    extra_where: Optional[list[str]] = None,
    extra_params: Optional[list[Any]] = None,
) -> list[sqlite3.Row]:
    where = [LABELED_NODE_SQL, "date >= ?", "date <= ?"]
    params: list[Any] = [start, end]
    if extra_where:
        where.extend(extra_where)
        params.extend(extra_params or [])
    grouped = ", ".join(group_by)
    select_cols = [
        grouped,
        "SUM(upload_bytes) AS upload_bytes",
        "SUM(download_bytes) AS download_bytes",
        "SUM(connection_count) AS connection_count",
        "MAX(user_tag) AS user_tag",
        "MAX(instance_id) AS instance_id",
    ]
    sql = (
        "SELECT "
        + ", ".join(select_cols)
        + " FROM daily_usage WHERE "
        + " AND ".join(where)
        + f" GROUP BY {grouped} "
        "ORDER BY SUM(upload_bytes + download_bytes) DESC, "
        + grouped
    )
    try:
        return list(conn.execute(sql, params).fetchall())
    except sqlite3.Error as exc:
        die(f"fleet stats query failed: {exc}")
        raise SystemExit(1)


def _emit_stats(
    *,
    mode: str,
    days: int,
    start: str,
    end: str,
    rows: list[dict[str, Any]],
    as_json: bool,
    human_header: str,
    human_line,
    extra: Optional[dict[str, Any]] = None,
) -> int:
    totals = _stats_totals(rows)
    if as_json:
        payload: dict[str, Any] = {
            "schema_version": STATS_JSON_SCHEMA_VERSION,
            "mode": mode,
            "days": days,
            "from": start,
            "to": end,
            "rows": rows,
            "totals": totals,
        }
        if extra:
            payload.update(extra)
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0
    lines = [
        f"Period: {start} → {end} (UTC days, from daily_usage)",
        human_header,
    ]
    for row in rows:
        lines.append(human_line(row))
    if not rows:
        lines.append("(no usage in window)")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def cmd_stats_user(args: argparse.Namespace) -> int:
    tag = args.tag
    validate_name(tag)
    days = args.days
    start, end = stats_date_window(days)
    registry = load_registry()
    user_id = resolve_fleet_user_id(registry, tag)
    conn = open_fleet_db()
    try:
        raw_rows = query_daily_grouped(
            conn,
            start=start,
            end=end,
            group_by=("node_id", "user_id"),
            extra_where=["user_id = ?"],
            extra_params=[user_id],
        )
    finally:
        conn.close()
    rows = [_stats_row_from_sql(registry, raw) for raw in raw_rows]
    rows.sort(key=lambda r: (r["node"], r["node_id"]))
    return _emit_stats(
        mode="user",
        days=days,
        start=start,
        end=end,
        rows=rows,
        as_json=bool(getattr(args, "as_json", False)),
        extra={"tag": tag, "user_id": user_id},
        human_header="NODE USER_ID UP DOWN TOTAL CONNECTIONS",
        human_line=lambda r: (
            f"{r['node']} {r['user_id']} {r['upload_bytes']} "
            f"{r['download_bytes']} {r['bytes']} {r['connection_count']}"
        ),
    )


def cmd_stats_top_users(args: argparse.Namespace) -> int:
    days = args.days
    start, end = stats_date_window(days)
    registry = load_registry()
    conn = open_fleet_db()
    try:
        raw_rows = query_daily_grouped(
            conn,
            start=start,
            end=end,
            group_by=("user_id", "node_id"),
        )
    finally:
        conn.close()
    rows = [_stats_row_from_sql(registry, raw) for raw in raw_rows]
    return _emit_stats(
        mode="top_users",
        days=days,
        start=start,
        end=end,
        rows=rows,
        as_json=bool(getattr(args, "as_json", False)),
        human_header="USER_ID NODE TAG UP DOWN TOTAL CONNECTIONS",
        human_line=lambda r: (
            f"{r['user_id']} {r['node']} {r['user_tag'] or '-'} "
            f"{r['upload_bytes']} {r['download_bytes']} {r['bytes']} "
            f"{r['connection_count']}"
        ),
    )


def cmd_stats_top_hosts(args: argparse.Namespace) -> int:
    days = args.days
    start, end = stats_date_window(days)
    registry = load_registry()
    conn = open_fleet_db()
    try:
        raw_rows = query_daily_grouped(
            conn,
            start=start,
            end=end,
            group_by=("destination_host", "node_id"),
        )
    finally:
        conn.close()
    rows = [_stats_row_from_sql(registry, raw) for raw in raw_rows]
    return _emit_stats(
        mode="top_hosts",
        days=days,
        start=start,
        end=end,
        rows=rows,
        as_json=bool(getattr(args, "as_json", False)),
        human_header="HOST NODE UP DOWN TOTAL CONNECTIONS",
        human_line=lambda r: (
            f"{r['destination_host']} {r['node']} {r['upload_bytes']} "
            f"{r['download_bytes']} {r['bytes']} {r['connection_count']}"
        ),
    )


def cmd_stats_node(args: argparse.Namespace) -> int:
    name = args.name
    validate_name(name)
    days = args.days
    start, end = stats_date_window(days)
    registry = load_registry()
    node = require_node(registry, name)
    conn = open_fleet_db()
    try:
        raw_rows = query_daily_grouped(
            conn,
            start=start,
            end=end,
            group_by=("user_id", "node_id", "destination_host"),
            extra_where=["node_id = ?"],
            extra_params=[node["node_id"]],
        )
    finally:
        conn.close()
    rows = [_stats_row_from_sql(registry, raw) for raw in raw_rows]
    return _emit_stats(
        mode="node",
        days=days,
        start=start,
        end=end,
        rows=rows,
        as_json=bool(getattr(args, "as_json", False)),
        extra={"node": name, "node_id": node["node_id"]},
        human_header="NODE USER_ID HOST UP DOWN TOTAL CONNECTIONS",
        human_line=lambda r: (
            f"{r['node']} {r['user_id']} {r['destination_host']} "
            f"{r['upload_bytes']} {r['download_bytes']} {r['bytes']} "
            f"{r['connection_count']}"
        ),
    )


def cmd_stats(args: argparse.Namespace) -> int:
    kind = getattr(args, "stats_command", None)
    if kind == "user":
        return cmd_stats_user(args)
    if kind == "top":
        top = getattr(args, "stats_top_command", None)
        if top == "users":
            return cmd_stats_top_users(args)
        if top == "hosts":
            return cmd_stats_top_hosts(args)
        die("stats top requires users or hosts", 2)
    if kind == "node":
        return cmd_stats_node(args)
    die("stats requires user, top, or node", 2)
    raise SystemExit(2)


def load_ui_server_module() -> Any:
    """Load lib/vincula-ui/server.py (Local Audit UI)."""
    path = _controller_lib_dir() / "vincula-ui" / "server.py"
    if not path.is_file():
        die(f"ui server not found: {path}")
    loader = importlib.machinery.SourceFileLoader("vincula_ui_server", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        die(f"cannot load ui server: {path}")
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def cmd_ui(args: argparse.Namespace) -> int:
    """Start localhost-only read-only Local Audit UI (AC-3.1 / D19)."""
    _load_controller_sibling("vcl_legacy", "legacy.py").apply_env_aliases()
    ui = load_ui_server_module()
    static_dir = _controller_lib_dir() / "vincula-ui" / "static"
    host = getattr(args, "host", None) or ui.DEFAULT_HOST
    port = int(getattr(args, "port", ui.DEFAULT_PORT))
    if isinstance(port, bool) or port < 1 or port > 65535:
        die("ui --port must be 1..65535", 2)
    # Prefer the live module object; fall back to a globals proxy so UI works
    # when this file was exec'd via importlib without sticking in sys.modules.
    fleet_mod = sys.modules.get(__name__)
    if fleet_mod is None or not hasattr(fleet_mod, "open_fleet_db"):
        fleet_mod = sys.modules.get("vincula_fleet")
    if fleet_mod is None or not hasattr(fleet_mod, "open_fleet_db"):
        import types

        fleet_mod = types.ModuleType("vincula_fleet_ui_host")
        fleet_mod.__dict__.update(globals())
    return int(
        ui.serve(
            host=str(host),
            port=port,
            fleet_mod=fleet_mod,
            static_dir=static_dir,
        )
    )


def cmd_workspace_migrate(args: argparse.Namespace) -> int:
    if getattr(args, "dry_run", False):
        sys.stdout.write(
            json.dumps(_WS.plan_migrate_dry_run(), indent=2, ensure_ascii=False)
            + "\n"
        )
        return 0
    sys.stdout.write(
        json.dumps(_WS.execute_migrate(), indent=2, ensure_ascii=False) + "\n"
    )
    return 0


def cmd_access_list(_args: argparse.Namespace) -> int:
    bindings = list_bindings()
    for ref in sorted(bindings):
        binding = bindings[ref]
        btype = binding.get("type") if isinstance(binding, dict) else ""
        if isinstance(binding, dict) and btype == "identity_file":
            path = binding.get("path") or "-"
        else:
            path = "-"
        sys.stdout.write(f"{ref}\t{btype}\t{path}\n")
    return 0


def cmd_access_bind(args: argparse.Namespace) -> int:
    ref = str(args.ref)
    if getattr(args, "openssh_default", False):
        bind_openssh_default(ref)
    else:
        bind_identity_file(ref, str(args.identity_file))
    return 0


def cmd_access_verify(_args: argparse.Namespace) -> int:
    problems = verify_bindings()
    if problems:
        die("\n".join(problems), 1)
    return 0


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )


def _add_days_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--days",
        type=int,
        required=True,
        metavar="N",
        help="inclusive UTC day window ending today (today-(N-1) … today)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vcl-fleet",
        description=(
            "Vincula fleet controller. Registers nodes over OpenSSH "
            "(vcl identity --json) or with --offline. status/verify probe "
            "enabled nodes over SSH using remote vcl --json contracts. "
            "user add provisions the same user_id on one or more nodes; "
            "any per-node failure is PARTIAL (exit 2). Distributed rollback "
            "is not promised."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="create a user-local fleet.json registry")

    node = sub.add_parser("node", help="register and update fleet nodes")
    node_sub = node.add_subparsers(dest="node_command")

    p_add = node_sub.add_parser(
        "add",
        help="register a node via SSH identity (or --offline)",
    )
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
    p_add.add_argument(
        "--host-key",
        dest="host_key",
        help="pin remote host-key fingerprint SHA256:... (writes Fleet known_hosts (workspace/trust or ~/.ssh))",
    )
    p_add.add_argument(
        "--identity-file",
        dest="identity_file",
        help="local SSH private key; passed as -i with IdentitiesOnly=yes",
    )

    node_sub.add_parser("list", help="list registered nodes")

    p_show = node_sub.add_parser("show", help="show one registered node")
    p_show.add_argument("name")

    p_set = node_sub.add_parser(
        "set",
        help="change ssh_host (endpoint rebind; credentials stay)",
        description=(
            "This is endpoint rebind; credentials stay. "
            "Physical replacement is node replace (secretless backup → "
            "restore on a runtime-only host)."
        ),
    )
    p_set.add_argument("name")
    p_set.add_argument("--host", help="new SSH hostname or IP")
    p_set.add_argument("--user", help="optional new SSH user")
    p_set.add_argument("--port", type=int, help="optional new SSH port")
    p_set.add_argument(
        "--identity-file",
        dest="identity_file",
        help="local SSH private key; passed as -i with IdentitiesOnly=yes",
    )
    p_set.add_argument(
        "--clear-identity-file",
        dest="clear_identity_file",
        action="store_true",
        help="stop passing -i (use agent / default keys again)",
    )

    p_disable = node_sub.add_parser("disable", help="disable a registered node")
    p_disable.add_argument("name")
    p_enable = node_sub.add_parser("enable", help="enable a registered node")
    p_enable.add_argument("name")
    p_retire = node_sub.add_parser(
        "retire",
        help="retire a node after final sync (history is kept)",
        description=(
            "Final-sync NAME, write $FLEET_HOME/retired/NAME/ (identity, "
            "cursor, last-status; not a 0.3.0 backup), disable remote users "
            "except the last enabled (node invariant), then mark "
            "status=retired enabled=false. Does not uninstall the node and "
            "does not erase fleet.db history. Unreachable nodes cannot be "
            "retired because final sync is required."
        ),
    )
    p_retire.add_argument("name")

    p_replace = node_sub.add_parser(
        "replace",
        help="physical replace onto a runtime-only host (secretless restore)",
        description=(
            "Physical replacement of the same logical node_id. Secretless "
            "backup of the old host, then vcl restore FILE --reissue-output "
            "FILE --server HOST --json on NEW_HOST. NEW_HOST must be "
            "runtime-only (vincula.sh --runtime-only): vcl present, no "
            "VERSION. A fully bootstrapped host is refused. This is not "
            "node set (endpoint rebind; credentials stay). Requires "
            "--host-key SHA256:..."
        ),
    )
    p_replace.add_argument("name")
    p_replace.add_argument("--host", required=True, help="new SSH hostname or IP")
    p_replace.add_argument(
        "--host-key",
        dest="host_key",
        required=True,
        help="pin new host-key fingerprint SHA256:... (required)",
    )
    p_replace.add_argument(
        "--output",
        help="write reissue CSV here (default: $FLEET_HOME/reissue-NAME-UTC.csv)",
    )
    p_replace.add_argument(
        "--from-backup",
        dest="from_backup",
        help="use an existing secretless backup FILE (skip final sync + remote backup)",
    )
    p_replace.add_argument(
        "--identity-file",
        dest="identity_file",
        help="local SSH private key for the new host (default: keep the old node's)",
    )
    p_replace.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )

    p_instances = node_sub.add_parser(
        "instances",
        help="list instance_history for NAME (physical instances over time)",
    )
    p_instances.add_argument("name")
    p_instances.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )

    p_status = sub.add_parser(
        "status",
        help="remote status table: NAME NODE_ID INSTANCE SSH PROXY ACCOUNTING",
        description=(
            "Probe enabled nodes over SSH (vcl identity --json and "
            "vcl status --json). Table columns: NAME NODE_ID INSTANCE "
            "SSH PROXY ACCOUNTING. States: OK / STALE / FAIL / UNKNOWN. "
            "SSH unreachable → SSH=FAIL, PROXY=UNKNOWN, ACCOUNTING=UNKNOWN. "
            "Exit 1 if any node is SSH/PROXY/ACCOUNTING FAIL; STALE is not FAIL."
        ),
    )
    p_status.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )
    p_status.add_argument(
        "--all",
        action="store_true",
        help="include disabled and retired nodes (retired SSH=-; no SSH)",
    )
    p_verify = sub.add_parser(
        "verify",
        help="aggregate remote identity/status/verify and clock skew",
        description=(
            f"Clock skew: WARN if drift exceeds {CLOCK_SKEW_WARN_SECONDS}s; "
            f"FAIL check {CLOCK_SKEW_FAIL_CHECK} if drift exceeds "
            f"{CLOCK_SKEW_FAIL_SECONDS}s (5 minutes)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_verify.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )
    p_verify.add_argument(
        "--all",
        action="store_true",
        help="include disabled and retired nodes (retired SSH=-; no SSH)",
    )
    user = sub.add_parser(
        "user",
        help="provision and inspect users across fleet nodes",
        description=(
            "The controller generates one fleet-global user_id (or accepts "
            "--user-id for remediation) and SSHes "
            "`vcl user add TAG --user-id UUID --json` to each target. "
            "All nodes SUCCESS → exit 0. Any FAILED (including all failed) "
            "→ PARTIAL, exit 2, per-node status, and a copy-paste "
            "remediation command. Distributed rollback is not promised "
            "and is not performed. enable/disable/rotate require --node "
            "(no fleet-wide disable). import validates the whole CSV "
            "before any SSH; export --credentials requires --output "
            "(mode 0600)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    user_sub = user.add_subparsers(dest="user_command")

    p_uadd = user_sub.add_parser(
        "add",
        help="provision TAG on --node / --nodes (PARTIAL exit 2)",
        description=(
            "Generate or reuse --user-id, then add the user on each target "
            "node. --node N is the same as --nodes N. Exit 0 on SUCCESS; "
            "exit 2 on PARTIAL. Distributed rollback is not promised."
        ),
    )
    p_uadd.add_argument("tag", help="user tag (same charset as node names)")
    uadd_nodes = p_uadd.add_mutually_exclusive_group(required=True)
    uadd_nodes.add_argument(
        "--node",
        dest="node_one",
        help="single target node (same as --nodes NAME)",
    )
    uadd_nodes.add_argument(
        "--nodes",
        dest="nodes_csv",
        help="comma-separated target nodes (e.g. lax,tokyo)",
    )
    p_uadd.add_argument("--display-name", dest="display_name")
    p_uadd.add_argument("--department", dest="department")
    p_uadd.add_argument(
        "--user-id",
        dest="user_id",
        help="fleet-global UUID (generated if omitted; required for PARTIAL remediation)",
    )
    p_uadd.add_argument(
        "--output",
        help="write credential CSV (user,node,credential_id,vless_uri) mode 0600",
    )
    p_uadd.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print mutation JSON (schema_version 1)",
    )

    p_ulist = user_sub.add_parser(
        "list",
        help="aggregate user list from enabled nodes",
    )
    p_ulist.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )

    p_ushow = user_sub.add_parser(
        "show",
        help="per-node credential status for TAG",
    )
    p_ushow.add_argument("tag")
    p_ushow.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )

    p_uenable = user_sub.add_parser(
        "enable",
        help="enable TAG on a single --node",
    )
    p_uenable.add_argument("tag")
    p_uenable.add_argument(
        "--node",
        dest="node",
        help="target node (required; no fleet-wide enable)",
    )
    p_uenable.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )

    p_udisable = user_sub.add_parser(
        "disable",
        help="disable TAG on a single --node (not fleet-wide)",
    )
    p_udisable.add_argument("tag")
    p_udisable.add_argument(
        "--node",
        dest="node",
        help="target node (required; refusing fleet-wide disable)",
    )
    p_udisable.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )

    p_urotate = user_sub.add_parser(
        "rotate",
        help="rotate TAG credential on a single --node",
    )
    p_urotate.add_argument("tag")
    p_urotate.add_argument(
        "--node",
        dest="node",
        help="target node (required)",
    )
    p_urotate.add_argument(
        "--output",
        help="write credential CSV mode 0600",
    )
    p_urotate.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )

    p_uimport = user_sub.add_parser(
        "import",
        help="batch-provision from CSV (validate all rows before any SSH)",
        description=(
            "CSV header must be exactly tag,display_name,department,nodes. "
            "nodes cells are a single name or a quoted comma list "
            '("lax,tokyo"). Every row is validated (tag, duplicates, '
            "registered enabled nodes) before any mutation. Validation "
            "failure → exit 1, zero SSH. Apply uses the same per-node "
            "add path as user add (one user_id per row). Any node "
            "FAILED → PARTIAL exit 2. Distributed rollback is not promised."
        ),
    )
    p_uimport.add_argument("csv_file", help="path to users.csv")
    p_uimport.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and make no changes",
    )
    p_uimport.add_argument(
        "--output",
        help="write credential CSV (user,node,credential_id,vless_uri) mode 0600",
    )

    p_uexport = user_sub.add_parser(
        "export",
        help="merged per-node user CSV from enabled nodes",
        description=(
            "Default: metadata CSV (tag,display_name,department,user_id,"
            "node,enabled) on stdout or --output. --credentials includes "
            "vless URIs (user,node,credential_id,vless_uri) and requires "
            "--output FILE written mode 0600."
        ),
    )
    p_uexport.add_argument(
        "--credentials",
        action="store_true",
        help="include vless URIs (requires --output FILE, mode 0600)",
    )
    p_uexport.add_argument(
        "--output",
        help="write CSV to FILE (required with --credentials; mode 0600)",
    )

    p_sync = sub.add_parser(
        "sync",
        help="incremental audit import from enabled nodes",
        description=(
            "For each enabled node (or --node NAME / --all), read the "
            "durable sync_cursor (0 if none), SSH "
            "`vcl audit export --after CURSOR --jsonl`, and import via "
            "INSERT OR IGNORE in one transaction. The cursor advances "
            "only after a successful import COMMIT. Remote CURSOR_EXPIRED "
            "(exit 3, meta.error=CURSOR_EXPIRED) does not import; "
            "status=expired and overall exit 2. Remote CURSOR_AHEAD "
            "(exit 3, meta.error=CURSOR_AHEAD: after > MAX(event_id)) "
            "does not import; status=error and overall exit 2. Lying "
            "export meta (count, next_cursor, event_id continuity, "
            "node/instance) is ERROR, cursor unchanged. Both cursor "
            "errors remediate with --reseed NAME: delete that node's local "
            "audit_events and daily_usage, reset cursor to 0, then pull "
            "the remaining window. Reseed is not a 0.3.0 snapshot. "
            "Any expired or error node → PARTIAL exit 2."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sync_sel = p_sync.add_mutually_exclusive_group()
    sync_sel.add_argument(
        "--node",
        dest="node",
        help="sync a single enabled node",
    )
    sync_sel.add_argument(
        "--all",
        action="store_true",
        help="include disabled nodes (marked DISABLED; no SSH). Retired nodes are skipped.",
    )
    p_sync.add_argument(
        "--reseed",
        metavar="NAME",
        help="wipe local audit for NAME, reset cursor to 0, then export --after 0",
    )
    p_sync.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print JSON (schema_version 1)",
    )

    p_audit = sub.add_parser(
        "audit",
        help="query synced fleet.db audit_events by user_id",
        description=(
            "Merge connection rows across nodes by stable user_id. "
            "Window is RFC3339 interval-overlap (same predicate as node "
            "`vcl audit`: started_at < --to AND COALESCE(closed_at, "
            "last_seen_at) >= --from). Output columns: time node instance "
            "destination traffic. Rows without node_id are never merged. "
            "TAG is resolved from per-node user list; conflicting user_id "
            "is refused."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    audit_sub = p_audit.add_subparsers(dest="audit_command")
    p_audit_user = audit_sub.add_parser(
        "user",
        help="connections for TAG in an RFC3339 window",
    )
    p_audit_user.add_argument("tag", help="user tag (resolved to user_id)")
    p_audit_user.add_argument(
        "--from",
        dest="query_from",
        required=True,
        metavar="RFC3339",
        help="window start (connection end inclusive)",
    )
    p_audit_user.add_argument(
        "--to",
        dest="query_to",
        required=True,
        metavar="RFC3339",
        help="window end (started_at exclusive)",
    )
    p_audit_user.add_argument(
        "--node",
        dest="node",
        help="limit to one registry node name",
    )
    _add_json_flag(p_audit_user)

    p_stats = sub.add_parser(
        "stats",
        help="node-tagged daily_usage totals from fleet.db",
        description=(
            "Read daily_usage derived from synced audit_events "
            "(UTC day of started_at). Not byte-identical with node "
            "`vcl stats`. Detail rows keep (user_id, node); unlabeled "
            "node_id is never merged. Combined totals exist only in "
            "--json totals.by_node."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    stats_sub = p_stats.add_subparsers(dest="stats_command")
    p_suser = stats_sub.add_parser(
        "user",
        help="per-node usage for TAG over --days N",
    )
    p_suser.add_argument("tag")
    _add_days_flag(p_suser)
    _add_json_flag(p_suser)

    p_stop = stats_sub.add_parser(
        "top",
        help="top users or hosts, split by node",
    )
    top_sub = p_stop.add_subparsers(dest="stats_top_command")
    p_top_users = top_sub.add_parser(
        "users",
        help="per (user_id, node) totals",
    )
    _add_days_flag(p_top_users)
    _add_json_flag(p_top_users)
    p_top_hosts = top_sub.add_parser(
        "hosts",
        help="per (host, node) totals",
    )
    _add_days_flag(p_top_hosts)
    _add_json_flag(p_top_hosts)

    p_snode = stats_sub.add_parser(
        "node",
        help="usage on one registry node over --days N",
    )
    p_snode.add_argument("name")
    _add_days_flag(p_snode)
    _add_json_flag(p_snode)

    p_ui = sub.add_parser(
        "ui",
        help="localhost-only read-only Local Audit UI (Overview/Audit/Health)",
        description=(
            "Serve a loopback-only read-only Local Audit UI over stdlib "
            "HTTP. Default bind 127.0.0.1 (optional ::1). Non-loopback "
            "binds are refused. Data comes from $FLEET_HOME cache; "
            "Refresh/Verify/Sync trigger existing SSH-backed controller "
            "commands. No add/rotate/retire/replace/restore/import in UI."
        ),
    )
    p_ui.add_argument(
        "--host",
        default="127.0.0.1",
        help="loopback bind address (default: 127.0.0.1; ::1 allowed)",
    )
    p_ui.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port (default: 8765)",
    )

    access = sub.add_parser(
        "access", help="machine-local credential bindings (D28)"
    )
    asub = access.add_subparsers(dest="access_command")
    asub.add_parser("list", help="list credential bindings")
    asub.add_parser("verify", help="verify bound identity files exist")
    pb = asub.add_parser("bind", help="bind a credential ref on this machine")
    pb.add_argument("ref", help="credential ref name")
    g = pb.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--identity-file",
        dest="identity_file",
        metavar="PATH",
        help="local SSH private key path",
    )
    g.add_argument(
        "--openssh-default",
        dest="openssh_default",
        action="store_true",
        help="use OpenSSH default identities (no -i)",
    )

    ws = sub.add_parser(
        "workspace", help="workspace lifecycle (migrate --dry-run or execute)"
    )
    ws_sub = ws.add_subparsers(dest="workspace_command")
    p_mig = ws_sub.add_parser(
        "migrate", help="legacy→workspace migrate (0.4.1)"
    )
    p_mig.add_argument(
        "--dry-run",
        action="store_true",
        help="plan only (AC-4.0-M06); omit to execute (0.4.1)",
    )

    sub.add_parser("version", help="print vcl-fleet version")
    sub.add_parser("help", help="show this help")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    _load_controller_sibling("vcl_legacy", "legacy.py").apply_env_aliases()
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
        return cmd_status(as_json=bool(args.as_json), include_all=bool(args.all))
    if command == "verify":
        return cmd_verify(as_json=bool(args.as_json), include_all=bool(args.all))
    if command == "sync":
        return cmd_sync(args)
    if command == "audit":
        sub = args.audit_command
        if sub is None:
            parser.parse_args(["audit", "--help"])
            return 2
        if sub == "user":
            return cmd_audit_user(args)
        die(f"unknown audit command: {sub}", 2)
    if command == "stats":
        sub = getattr(args, "stats_command", None)
        if sub is None:
            parser.parse_args(["stats", "--help"])
            return 2
        if sub == "top" and getattr(args, "stats_top_command", None) is None:
            parser.parse_args(["stats", "top", "--help"])
            return 2
        return cmd_stats(args)
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
        if sub == "retire":
            return cmd_node_retire(args.name)
        if sub == "replace":
            return cmd_node_replace(args)
        if sub == "instances":
            return cmd_node_instances(args.name, as_json=bool(getattr(args, "as_json", False)))
        die(f"unknown node command: {sub}", 2)
    if command == "user":
        sub = args.user_command
        if sub is None:
            parser.parse_args(["user", "--help"])
            return 2
        if sub == "add":
            return cmd_user_add(args)
        if sub == "list":
            return cmd_user_list(args)
        if sub == "show":
            return cmd_user_show(args)
        if sub == "enable":
            return cmd_user_enable_disable(args, enabled=True)
        if sub == "disable":
            return cmd_user_enable_disable(args, enabled=False)
        if sub == "rotate":
            return cmd_user_rotate(args)
        if sub == "import":
            return cmd_user_import(args)
        if sub == "export":
            return cmd_user_export(args)
        die(f"unknown user command: {sub}", 2)
    if command == "ui":
        return cmd_ui(args)
    if command == "access":
        sub = getattr(args, "access_command", None)
        if sub is None:
            parser.parse_args(["access", "--help"])
            return 2
        if sub == "list":
            return cmd_access_list(args)
        if sub == "bind":
            return cmd_access_bind(args)
        if sub == "verify":
            return cmd_access_verify(args)
        die(f"unknown access command: {sub}", 2)
    if command == "workspace":
        sub = getattr(args, "workspace_command", None)
        if sub is None:
            parser.parse_args(["workspace", "--help"])
            return 2
        if sub == "migrate":
            return cmd_workspace_migrate(args)
        die(f"unknown workspace command: {sub}", 2)
    die(f"unknown command: {command}", 2)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
