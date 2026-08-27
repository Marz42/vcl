#!/usr/bin/env python3
"""Localhost-only Fleet Audit UI (stdlib HTTP + static files).

Bound to loopback only. GET APIs are local-cache only. Explicit POST
refresh/sync write the workstation cache (not identity mutations).
UI Sync uses ``sync --full`` (D53 / 0.4.4). No add/rotate/retire/replace/
restore/import/reseed via UI.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import mimetypes
import re
import secrets
import shlex
import sys
import threading
import traceback
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

UI_SCHEMA_VERSION = 1
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
UI_TOKEN_HEADER = "X-Vincula-UI-Token"
AUDIT_DEFAULT_LIMIT = 500
AUDIT_MAX_LIMIT = 1000
AUDIT_MAX_WINDOW_DAYS = 31
UI_MAX_WORKERS = 8
UI_REQUEST_TIMEOUT = 30.0
UI_BUSY_WAIT_SECONDS = 0.2
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

_FLEET: Any = None
_STATIC_DIR: Path = Path(__file__).resolve().parent / "static"
_UI_TOKEN: str = ""
_LISTEN_PORT: int = DEFAULT_PORT


def set_fleet_module(mod: Any) -> None:
    global _FLEET
    _FLEET = mod


def fleet() -> Any:
    if _FLEET is None:
        raise RuntimeError("fleet module not bound")
    return _FLEET


def ui_token() -> str:
    return _UI_TOKEN


def set_ui_runtime(*, token: str, listen_port: int) -> None:
    global _UI_TOKEN, _LISTEN_PORT
    _UI_TOKEN = token
    _LISTEN_PORT = int(listen_port)


def assert_loopback_host(host: str) -> str:
    """Fail-closed: only loopback bind addresses (AC-3.1-01)."""
    raw = (host or "").strip()
    if not raw:
        raise ValueError("ui host is required")
    if raw.lower() == "localhost":
        return "127.0.0.1"
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise ValueError(
            f"ui refuses non-loopback bind: {host} "
            "(use 127.0.0.1 or ::1)"
        ) from exc
    if not ip.is_loopback:
        raise ValueError(
            f"ui refuses non-loopback bind: {host} "
            "(use 127.0.0.1 or ::1)"
        )
    return raw


def users_cache_path(*, create: bool = False) -> Path:
    """Local UI users cache — always under ui-runtime (never Fleet Home / workspace)."""
    return _ui_runtime_dir(create=create) / "users-cache.json"


def legacy_users_cache_path() -> Path:
    """Pre-0.4.4 path (Fleet Home root). Must not remain after migrate."""
    return fleet().fleet_home() / "users-cache.json"


def _ui_runtime_dir(*, create: bool = False) -> Path:
    """Resolve ui-runtime; delegates to fleet helper (workspace fail-closed)."""
    return fleet().ui_runtime_dir(create=create)


def operations_log_path(*, create: bool = False) -> Path:
    return fleet().operation_journal_path(create=create)


def append_ui_operation(
    *,
    operation: str,
    target: str = "",
    state: str,
    exit_code: int,
    ok: bool,
    detail: str = "",
) -> None:
    """Append one UI-triggered operation via the shared fleet journal."""
    f = fleet()
    now = f.format_utc(datetime.now(timezone.utc))
    f.append_operation_journal(
        operation=operation,
        target=target,
        state=state,
        exit_code=int(exit_code),
        started_at=now,
        finished_at=now,
        detail=detail,
        ok=bool(ok),
    )


def read_ui_operations(*, limit: int = 100) -> list[dict[str, Any]]:
    return fleet().read_operation_journal(limit=limit)


def load_last_status_doc() -> Optional[dict[str, Any]]:
    """UI GET status plane: same cached payload as `fleet status` (P1-3).

    Primary source is node_snapshot; last-status.json is 0.4.1 fallback only
    (handled inside run_cached_status_payload). Returns None when no useful
    observation exists yet (pre-sync / empty fallback).
    """
    f = fleet()
    payload = f.run_cached_status_payload(include_all=True)
    payload = dict(payload)
    payload.pop("_rows", None)
    if _status_cache_empty(payload):
        return None
    return payload


def _status_cache_empty(doc: Optional[dict[str, Any]]) -> bool:
    """True when cache has no snapshot/legacy health observation."""
    if not doc:
        return True
    for node in doc.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        synced = node.get("synced_at")
        if isinstance(synced, str) and synced and synced != "-":
            return False
        ssh = str(node.get("ssh") or "")
        if ssh and ssh not in ("UNKNOWN", "-", "DISABLED"):
            return False
        if node.get("vincula_version"):
            return False
        proxy = str(node.get("proxy") or "")
        accounting = str(node.get("accounting") or "")
        if proxy not in ("", "UNKNOWN") or accounting not in ("", "UNKNOWN"):
            return False
    return True


def _node_has_active_credential(node: dict[str, Any]) -> Optional[bool]:
    """Bool when known; None when credential state is unavailable (audit fallback)."""
    if "has_active_credential" in node:
        val = node.get("has_active_credential")
        if val is None:
            return None
        return bool(val)
    if "active_credential_id" in node:
        return bool(node.get("active_credential_id"))
    return None


def sanitize_user_node_for_ui(node: dict[str, Any]) -> dict[str, Any]:
    """UI-safe node assignment: never expose VLESS credential UUID (NN #4)."""
    out: dict[str, Any] = {
        "name": node.get("name"),
        "tag": node.get("tag"),
        "enabled": node.get("enabled"),
        "status": node.get("status"),
        "has_active_credential": _node_has_active_credential(node),
    }
    if "node_id" in node:
        out["node_id"] = node.get("node_id")
    return out


def sanitize_users_for_ui(users: Any) -> list[dict[str, Any]]:
    """Strip credential UUIDs from user list (refresh write + legacy cache read)."""
    out: list[dict[str, Any]] = []
    if not isinstance(users, list):
        return out
    for user in users:
        if not isinstance(user, dict):
            continue
        nodes_raw = user.get("nodes") or []
        nodes_out = [
            sanitize_user_node_for_ui(n)
            for n in nodes_raw
            if isinstance(n, dict)
        ]
        rec: dict[str, Any] = {
            "tag": user.get("tag"),
            "user_id": user.get("user_id"),
            "display_name": user.get("display_name"),
            "department": user.get("department"),
            "source": user.get("source"),
            "nodes": nodes_out,
        }
        out.append(rec)
    return out


def migrate_users_cache() -> None:
    """Move Fleet Home users-cache.json → ui-runtime; rewrite sanitized; delete legacy.

    Call **only** from UI serve/start (not from GET ``load_users_cache``).
    Never leaves credential UUID on disk. Does not mkdir when there is nothing
    to migrate. Fail closed if workspace.json is unusable (via ``_ui_runtime_dir``).
    """
    f = fleet()
    legacy = legacy_users_cache_path()
    try:
        dest = users_cache_path(create=False)
    except RuntimeError as exc:
        f.die(str(exc), 2)
    if not legacy.is_file() and not dest.is_file():
        return
    payload: Optional[dict[str, Any]] = None
    for candidate in (dest, legacy):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            payload = data
            break
    if payload is None:
        if legacy.is_file():
            try:
                legacy.unlink()
            except OSError:
                pass
        return
    safe = dict(payload)
    safe["users"] = sanitize_users_for_ui(payload.get("users"))
    dest_write = users_cache_path(create=True)
    f._atomic_write_json(dest_write, safe)
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass
    try:
        disk = dest_write.read_text(encoding="utf-8")
    except OSError:
        return
    if "active_credential_id" in disk:
        f._atomic_write_json(
            dest_write,
            {
                "schema_version": int(safe.get("schema_version") or UI_SCHEMA_VERSION),
                "ok": safe.get("ok"),
                "refreshed_at": safe.get("refreshed_at"),
                "users": safe.get("users") or [],
                "unreachable": safe.get("unreachable") or [],
            },
        )


def load_users_cache() -> Optional[dict[str, Any]]:
    """Read users cache (sanitized). Does not migrate or mkdir.

    Prefer ui-runtime path; fall back to legacy Fleet Home file read-only so
    GET works until the next UI start migrates it.
    """
    try:
        runtime = users_cache_path(create=False)
    except RuntimeError:
        runtime = None
    candidates = [p for p in (runtime, legacy_users_cache_path()) if p is not None]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        sanitized = dict(data)
        sanitized["users"] = sanitize_users_for_ui(data.get("users"))
        return sanitized
    return None


def write_users_cache(payload: dict[str, Any]) -> None:
    safe = dict(payload)
    safe["users"] = sanitize_users_for_ui(payload.get("users"))
    fleet()._atomic_write_json(users_cache_path(create=True), safe)
    legacy = legacy_users_cache_path()
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass


def _human_bytes(n: int) -> str:
    value = float(max(0, int(n)))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{int(n)} B"


def _parse_rfc3339_utc(value: Optional[str]) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cache_age_seconds(last_iso: Optional[str]) -> Optional[int]:
    dt = _parse_rfc3339_utc(last_iso)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, int((now - dt).total_seconds()))


def _usage_aggregate(
    conn: Any,
    *,
    start: str,
    end: str,
    group_by: tuple[str, ...],
    extra_where: Optional[list[str]] = None,
    extra_params: Optional[list[Any]] = None,
) -> list[dict[str, Any]]:
    f = fleet()
    registry = f.load_registry()
    raw = f.query_daily_grouped(
        conn,
        start=start,
        end=end,
        group_by=group_by,
        extra_where=extra_where,
        extra_params=extra_params,
    )
    return [f._stats_row_from_sql(registry, r) for r in raw]


def _traffic_totals_for_window(
    conn: Any, *, start: str, end: str
) -> dict[str, Any]:
    rows = _usage_aggregate(conn, start=start, end=end, group_by=("node_id",))
    upload = sum(int(r.get("upload_bytes") or 0) for r in rows)
    download = sum(int(r.get("download_bytes") or 0) for r in rows)
    conns = sum(int(r.get("connection_count") or 0) for r in rows)
    return {
        "upload_bytes": upload,
        "download_bytes": download,
        "bytes": upload + download,
        "connection_count": conns,
        "upload_human": _human_bytes(upload),
        "download_human": _human_bytes(download),
        "bytes_human": _human_bytes(upload + download),
    }


def _traffic_trend(
    conn: Any,
    *,
    days: int = 7,
    extra_where: Optional[list[str]] = None,
    extra_params: Optional[list[Any]] = None,
) -> list[dict[str, Any]]:
    f = fleet()
    start, end = f.stats_date_window(days)
    raw = f.query_daily_grouped(
        conn,
        start=start,
        end=end,
        group_by=("date",),
        extra_where=extra_where,
        extra_params=extra_params,
    )
    out: list[dict[str, Any]] = []
    for row in raw:
        keys = set(row.keys())
        upload = f._row_int(row, "upload_bytes")
        download = f._row_int(row, "download_bytes")
        date = str(row["date"]) if "date" in keys else ""
        out.append(
            {
                "date": date,
                "upload_bytes": upload,
                "download_bytes": download,
                "bytes": upload + download,
                "connection_count": f._row_int(row, "connection_count"),
                "bytes_human": _human_bytes(upload + download),
            }
        )
    out.sort(key=lambda r: r["date"])
    return out


def _user_bytes_map(conn: Any, *, days: int) -> dict[str, dict[str, int]]:
    f = fleet()
    start, end = f.stats_date_window(days)
    raw = f.query_daily_grouped(
        conn, start=start, end=end, group_by=("user_id",)
    )
    out: dict[str, dict[str, int]] = {}
    for row in raw:
        uid = str(row["user_id"] or "")
        if not uid:
            continue
        upload = f._row_int(row, "upload_bytes")
        download = f._row_int(row, "download_bytes")
        out[uid] = {
            "upload_bytes": upload,
            "download_bytes": download,
            "bytes": upload + download,
            "connection_count": f._row_int(row, "connection_count"),
        }
    return out


def _node_bytes_map(conn: Any, *, days: int) -> dict[str, dict[str, int]]:
    f = fleet()
    start, end = f.stats_date_window(days)
    raw = f.query_daily_grouped(
        conn, start=start, end=end, group_by=("node_id",)
    )
    out: dict[str, dict[str, int]] = {}
    for row in raw:
        nid = str(row["node_id"] or "")
        if not nid:
            continue
        upload = f._row_int(row, "upload_bytes")
        download = f._row_int(row, "download_bytes")
        out[nid] = {
            "upload_bytes": upload,
            "download_bytes": download,
            "bytes": upload + download,
            "connection_count": f._row_int(row, "connection_count"),
        }
    return out


def _node_user_counts(conn: Any) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT node_id, COUNT(DISTINCT user_id) AS n
        FROM user_snapshot
        WHERE user_id IS NOT NULL AND user_id != ''
        GROUP BY node_id
        """
    ).fetchall()
    return {str(r["node_id"]): int(r["n"]) for r in rows}


def _users_from_snapshot(conn: Any, registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer user_snapshot (sync --full) for department / enabled."""
    f = fleet()
    rows = conn.execute(
        """
        SELECT node_id, user_id, tag, enabled, status, payload_json,
          CASE
            WHEN active_credential_id IS NOT NULL
             AND active_credential_id != ''
            THEN 1 ELSE 0
          END AS has_active_credential
        FROM user_snapshot
        WHERE user_id IS NOT NULL AND user_id != ''
        ORDER BY tag, user_id, node_id
        """
    ).fetchall()
    if not rows:
        return _users_from_db(conn, registry)
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        uid = str(row["user_id"])
        tag = f._optional_text(row["tag"]) or uid
        nid = str(row["node_id"])
        dept = None
        display = None
        try:
            payload = json.loads(row["payload_json"] or "{}")
            if isinstance(payload, dict):
                dept = payload.get("department") or None
                display = payload.get("display_name") or None
        except (json.JSONDecodeError, TypeError):
            pass
        if uid not in grouped:
            grouped[uid] = {
                "tag": tag,
                "user_id": uid,
                "display_name": display,
                "department": dept,
                "source": "user_snapshot",
                "nodes": [],
            }
            order.append(uid)
        rec = grouped[uid]
        if tag and rec["tag"] == uid:
            rec["tag"] = tag
        if not rec.get("department") and dept:
            rec["department"] = dept
        if not rec.get("display_name") and display:
            rec["display_name"] = display
        node_name = f.node_display_name(registry, nid)
        enabled = bool(int(row["enabled"] or 0))
        has_cred = bool(int(row["has_active_credential"] or 0))
        if not any(n.get("node_id") == nid for n in rec["nodes"]):
            rec["nodes"].append(
                {
                    "name": node_name,
                    "node_id": nid,
                    "tag": tag,
                    "enabled": enabled,
                    "status": f._optional_text(row["status"])
                    or ("active" if enabled else "disabled"),
                    "has_active_credential": has_cred,
                }
            )
    return [grouped[k] for k in order]


def _enabled_state_summary(nodes: list[dict[str, Any]]) -> str:
    if not nodes:
        return "—"
    flags = [n.get("enabled") for n in nodes]
    if all(f is True for f in flags):
        return "enabled"
    if all(f is False for f in flags):
        return "disabled"
    if any(f is None for f in flags):
        known = [f for f in flags if f is not None]
        if not known:
            return "unknown"
        return "mixed"
    return "mixed"


def _enrich_users_traffic(
    users: list[dict[str, Any]], conn: Any
) -> list[dict[str, Any]]:
    today = _user_bytes_map(conn, days=1)
    month = _user_bytes_map(conn, days=30)
    out: list[dict[str, Any]] = []
    for u in users:
        rec = dict(u)
        uid = str(u.get("user_id") or "")
        t = today.get(uid) or {}
        m = month.get(uid) or {}
        rec["today_bytes"] = int(t.get("bytes") or 0)
        rec["today_human"] = _human_bytes(rec["today_bytes"])
        rec["bytes_30d"] = int(m.get("bytes") or 0)
        rec["bytes_30d_human"] = _human_bytes(rec["bytes_30d"])
        rec["enabled_state"] = _enabled_state_summary(list(u.get("nodes") or []))
        nodes = list(u.get("nodes") or [])
        rec["node_count"] = len(nodes)
        rec["node_names"] = ", ".join(
            str(n.get("name") or "") for n in nodes if n.get("name")
        )
        out.append(rec)
    return out


COMMAND_BUILDER_OPS: dict[str, dict[str, Any]] = {
    "adopt": {
        "title": "Adopt node",
        "fields": [
            {"name": "name", "label": "Node name", "required": True},
            {"name": "host", "label": "Host", "required": True},
            {"name": "host_key", "label": "Host key (SHA256:…)", "required": True},
        ],
        "template": (
            "vcl-fleet node adopt {name} --host {host} --host-key {host_key}"
        ),
    },
    "provision": {
        "title": "Provision node",
        "fields": [
            {"name": "name", "label": "Node name", "required": True},
            {"name": "host", "label": "Host", "required": True},
            {"name": "host_key", "label": "Host key (SHA256:…)", "required": True},
        ],
        "template": (
            "vcl-fleet node provision {name} --host {host} --host-key {host_key}"
        ),
    },
    "user_add": {
        "title": "Add user",
        "fields": [
            {"name": "tag", "label": "User tag", "required": True},
            {"name": "nodes", "label": "Nodes (comma-separated)", "required": True},
            {"name": "display_name", "label": "Display name", "required": False},
            {"name": "department", "label": "Department", "required": False},
        ],
        "template": "vcl-fleet user add {tag} --nodes {nodes}",
    },
    "rotate": {
        "title": "Rotate credential",
        "fields": [
            {"name": "tag", "label": "User tag", "required": True},
            {"name": "node", "label": "Node", "required": True},
        ],
        "template": "vcl-fleet user rotate {tag} --node {node}",
    },
    "replace": {
        "title": "Replace node",
        "fields": [
            {"name": "name", "label": "Node name", "required": True},
            {"name": "host", "label": "New host", "required": True},
            {"name": "host_key", "label": "Host key (SHA256:…)", "required": True},
        ],
        "template": (
            "vcl-fleet node replace {name} --host {host} --host-key {host_key}"
        ),
    },
    "restore": {
        "title": "Restore audit archive",
        "fields": [
            {"name": "file", "label": "Archive file (.vclaudit)", "required": True},
        ],
        "template": "vcl-fleet audit archive restore {file}",
    },
    "reseed": {
        "title": "Reseed sync cursor (CLI-only)",
        "fields": [
            {"name": "name", "label": "Node name", "required": True},
        ],
        "template": "vcl-fleet sync --reseed {name}",
    },
}


def _builder_validate_name(kind: str, raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError(f"missing required field: {kind}")
    if not NAME_RE.fullmatch(text):
        raise ValueError(f"invalid {kind}: {text}")
    return text


def _builder_validate_host(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("missing required field: host")
    f = fleet()
    try:
        return f.validate_ssh_host(text)
    except SystemExit as exc:
        raise ValueError(f"invalid host: {text}") from exc


def _builder_validate_host_key(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("missing required field: host_key")
    f = fleet()
    try:
        return f.normalize_fingerprint(text)
    except SystemExit as exc:
        raise ValueError(f"invalid host_key: {text}") from exc


def _builder_validate_nodes_csv(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("missing required field: nodes")
    parts = [p.strip() for p in text.split(",")]
    names: list[str] = []
    for part in parts:
        if not part:
            raise ValueError("invalid nodes: empty entry")
        if not NAME_RE.fullmatch(part):
            raise ValueError(f"invalid node name: {part}")
        names.append(part)
    return ",".join(names)


def _builder_validate_file(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("missing required field: file")
    if "\x00" in text or "\n" in text or "\r" in text:
        raise ValueError("invalid file path")
    return text


def api_command_builder_meta() -> dict[str, Any]:
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "operations": [
            {
                "id": oid,
                "title": spec["title"],
                "fields": spec["fields"],
            }
            for oid, spec in COMMAND_BUILDER_OPS.items()
        ],
        "note": (
            "Command Builder copies CLI only — no UI mutations (D53). "
            "Fill fields to generate a complete command (shell-safe via shlex)."
        ),
    }


def api_command_build(body: dict[str, Any]) -> dict[str, Any]:
    """Build a shell-safe CLI string from an argv list (never raw concat)."""
    op = str((body or {}).get("operation") or "").strip()
    if op not in COMMAND_BUILDER_OPS:
        raise ValueError(f"unknown operation: {op or '(empty)'}")
    spec = COMMAND_BUILDER_OPS[op]
    fields_in = (body or {}).get("fields") or {}
    if not isinstance(fields_in, dict):
        raise ValueError("fields must be an object")
    values: dict[str, str] = {}
    for field in spec["fields"]:
        name = str(field["name"])
        raw = str(fields_in.get(name) or "").strip()
        if field.get("required") and not raw:
            raise ValueError(f"missing required field: {name}")
        if not raw:
            values[name] = ""
            continue
        if name in ("name", "tag", "node"):
            values[name] = _builder_validate_name(name, raw)
        elif name == "host":
            values[name] = _builder_validate_host(raw)
        elif name == "host_key":
            values[name] = _builder_validate_host_key(raw)
        elif name == "nodes":
            values[name] = _builder_validate_nodes_csv(raw)
        elif name == "file":
            values[name] = _builder_validate_file(raw)
        else:
            # display_name / department — free text; escaped by shlex.join
            if "\x00" in raw or "\n" in raw or "\r" in raw:
                raise ValueError(f"invalid {name}")
            values[name] = raw

    argv: list[str]
    if op == "adopt":
        argv = [
            "vcl-fleet",
            "node",
            "adopt",
            values["name"],
            "--host",
            values["host"],
            "--host-key",
            values["host_key"],
        ]
    elif op == "provision":
        argv = [
            "vcl-fleet",
            "node",
            "provision",
            values["name"],
            "--host",
            values["host"],
            "--host-key",
            values["host_key"],
        ]
    elif op == "user_add":
        argv = [
            "vcl-fleet",
            "user",
            "add",
            values["tag"],
            "--nodes",
            values["nodes"],
        ]
        if values.get("display_name"):
            argv.extend(["--display-name", values["display_name"]])
        if values.get("department"):
            argv.extend(["--department", values["department"]])
    elif op == "rotate":
        argv = [
            "vcl-fleet",
            "user",
            "rotate",
            values["tag"],
            "--node",
            values["node"],
        ]
    elif op == "replace":
        argv = [
            "vcl-fleet",
            "node",
            "replace",
            values["name"],
            "--host",
            values["host"],
            "--host-key",
            values["host_key"],
        ]
    elif op == "restore":
        argv = [
            "vcl-fleet",
            "audit",
            "archive",
            "restore",
            values["file"],
        ]
    elif op == "reseed":
        argv = ["vcl-fleet", "sync", "--reseed", values["name"]]
    else:
        raise ValueError(f"unknown operation: {op}")

    return {
        "schema_version": UI_SCHEMA_VERSION,
        "operation": op,
        "command": shlex.join(argv),
        "argv": argv,
        "copy_ready": True,
    }


def _parse_host_header(host_header: str) -> tuple[str, Optional[int]]:
    raw = (host_header or "").strip()
    if not raw:
        raise ValueError("missing Host")
    if raw.startswith("["):
        end = raw.find("]")
        if end < 0:
            raise ValueError("invalid Host")
        name = raw[1:end]
        rest = raw[end + 1 :]
        if rest.startswith(":"):
            return name, int(rest[1:])
        if rest:
            raise ValueError("invalid Host")
        return name, None
    if raw.count(":") == 1:
        name, port_s = raw.rsplit(":", 1)
        return name, int(port_s)
    return raw, None


def host_header_allowed(host_header: str, listen_port: int) -> bool:
    try:
        name, port = _parse_host_header(host_header)
    except (ValueError, TypeError):
        return False
    name_l = name.lower()
    if name_l not in ("127.0.0.1", "localhost", "::1"):
        return False
    if port is None:
        return True
    return int(port) == int(listen_port)


def allowed_origins(listen_port: int) -> set[str]:
    p = int(listen_port)
    return {
        f"http://127.0.0.1:{p}",
        f"http://localhost:{p}",
        f"http://[::1]:{p}",
    }


def content_type_is_json(header: Optional[str]) -> bool:
    if not header:
        return False
    main = header.split(";", 1)[0].strip().lower()
    return main == "application/json"


def recipes_payload() -> dict[str, Any]:
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "note": (
            "Copy-paste CLI only. No identity/node mutations via UI. "
            "UI Sync runs vcl-fleet sync --full (cache write). "
            "vcl-fleet sync --reseed is CLI-only (UI refuses reseed)."
        ),
        "recipes": [
            {
                "id": "init",
                "title": "Init fleet registry",
                "command": "vcl-fleet init",
            },
            {
                "id": "workspace-init",
                "title": "Workspace init",
                "command": "vcl-fleet workspace init",
            },
            {
                "id": "workspace-verify",
                "title": "Workspace verify (digest / conflict)",
                "command": "vcl-fleet workspace verify",
            },
            {
                "id": "workspace-export",
                "title": "Workspace export",
                "command": "vcl-fleet workspace export fleet.tgz",
            },
            {
                "id": "workspace-import",
                "title": "Workspace import",
                "command": "vcl-fleet workspace import fleet.tgz",
            },
            {
                "id": "node-adopt",
                "title": "Adopt installed node (SSH identity + register)",
                "command": (
                    "vcl-fleet node adopt NAME --host HOST "
                    "--host-key SHA256:..."
                ),
            },
            {
                "id": "node-provision",
                "title": "Provision fresh VPS (pinned node 0.3.2)",
                "command": (
                    "vcl-fleet node provision NAME --host HOST "
                    "--host-key SHA256:..."
                ),
            },
            {
                "id": "node-register",
                "title": "Register registry-only (no SSH)",
                "command": (
                    "vcl-fleet node register NAME --host HOST "
                    "--node-id UUID"
                ),
            },
            {
                "id": "node-add",
                "title": "Legacy alias: node add ≡ adopt",
                "command": (
                    "vcl-fleet node add NAME --host HOST "
                    "--host-key SHA256:..."
                ),
            },
            {
                "id": "node-add-offline",
                "title": "Legacy alias: add --offline ≡ register",
                "command": (
                    "vcl-fleet node add NAME --host HOST --offline "
                    "--node-id UUID"
                ),
            },
            {
                "id": "node-set",
                "title": "Rebind endpoint (credentials stay)",
                "command": "vcl-fleet node set NAME --host NEW_HOST",
            },
            {
                "id": "node-replace",
                "title": "Physical replace (runtime-only NEW)",
                "command": (
                    "vcl-fleet node replace NAME --host NEW_HOST "
                    "--host-key SHA256:..."
                ),
            },
            {
                "id": "node-retire",
                "title": "Retire node (final sync required)",
                "command": "vcl-fleet node retire NAME",
            },
            {
                "id": "node-enable",
                "title": "Enable / disable node",
                "command": "vcl-fleet node enable|disable NAME",
            },
            {
                "id": "node-instances",
                "title": "List physical instances",
                "command": "vcl-fleet node instances NAME --json",
            },
            {
                "id": "user-add",
                "title": "Add user (--node / --nodes required)",
                "command": (
                    "vcl-fleet user add TAG --nodes NODE1,NODE2 "
                    "[--display-name NAME] [--department DEPT]"
                ),
            },
            {
                "id": "user-import",
                "title": "Import users CSV",
                "command": "vcl-fleet user import users.csv [--dry-run]",
            },
            {
                "id": "user-export",
                "title": "Export user metadata",
                "command": "vcl-fleet user export [--output FILE]",
            },
            {
                "id": "user-rotate",
                "title": "Rotate credential (--node required)",
                "command": (
                    "vcl-fleet user rotate TAG --node NAME [--output FILE]"
                ),
            },
            {
                "id": "user-enable",
                "title": "Enable / disable user on one node",
                "command": "vcl-fleet user enable|disable TAG --node NAME",
            },
            {
                "id": "user-link",
                "title": "Live single-node VLESS URI (CLI only; not shown in UI)",
                "command": "vcl-fleet user link TAG --node NAME",
            },
            {
                "id": "backup-restore",
                "title": "Backup / restore (node CLI; see docs/backup.md)",
                "command": (
                    "vcl backup / vcl restore FILE --reissue-output FILE "
                    "--server HOST  # never via UI"
                ),
            },
            {
                "id": "audit-archive-create",
                "title": "Create audit archive (.vclaudit)",
                "command": (
                    "vcl-fleet audit archive create --from RFC3339 "
                    "--to RFC3339 --output out.vclaudit"
                ),
            },
            {
                "id": "audit-archive-restore",
                "title": "Restore audit archive (never touches sync cursor)",
                "command": "vcl-fleet audit archive restore out.vclaudit",
            },
            {
                "id": "sync",
                "title": "Sync --full (UI Sync button) / reseed (CLI only)",
                "command": (
                    "vcl-fleet sync --full [--node NAME]\n"
                    "vcl-fleet sync --reseed NAME   # CLI only; wipes local audit"
                ),
            },
            {
                "id": "status-verify",
                "title": "Status (cache) / probe (live) / verify",
                "command": (
                    "vcl-fleet status|probe|verify [--json] [--all]"
                ),
            },
        ],
    }


def _sync_cursors(conn: Any, registry: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in registry.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("node_id") or "")
        if not nid:
            continue
        row = fleet().read_sync_cursor_row(conn, nid)
        item: dict[str, Any] = {
            "name": node.get("name"),
            "node_id": nid,
            "lifecycle": fleet().node_lifecycle_status(node),
            "last_event_id": None,
            "last_sync_at": None,
            "cursor_status": None,
            "instance_id": None,
        }
        if row is not None:
            item["last_event_id"] = int(row["last_event_id"])
            item["last_sync_at"] = row["last_sync_at"]
            item["cursor_status"] = row["status"]
            item["instance_id"] = fleet()._optional_text(row["instance_id"])
        out.append(item)
    return out


def _workspace_surface() -> dict[str, Any]:
    """Read-only workspace strip for Overview/Nodes (strict, no writes)."""
    return fleet().read_only_workspace_surface()


def _warnings_from_status(doc: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if not doc:
        warnings.append(
            {
                "level": "amber",
                "code": "no-status-cache",
                "message": (
                    "No cached node health yet. Run sync --full "
                    "(or Refresh / Verify for a live check)."
                ),
            }
        )
        return warnings
    if doc.get("ok") is False:
        warnings.append(
            {
                "level": "red",
                "code": "fleet-not-ok",
                "message": "Last probe reported fleet not OK.",
            }
        )
    for node in doc.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        name = node.get("name") or "?"
        for key in ("ssh", "proxy", "accounting"):
            state = str(node.get(key) or "")
            if state == "FAIL":
                warnings.append(
                    {
                        "level": "red",
                        "code": f"{key}-fail",
                        "message": f"{name}: {key.upper()}={state}",
                        "node": name,
                    }
                )
            elif state == "STALE":
                warnings.append(
                    {
                        "level": "amber",
                        "code": f"{key}-stale",
                        "message": f"{name}: {key.upper()}={state}",
                        "node": name,
                    }
                )
        clock = str(node.get("clock") or "")
        if clock == "FAIL":
            warnings.append(
                {
                    "level": "red",
                    "code": "clock-fail",
                    "message": f"{name}: clock FAIL",
                    "node": name,
                }
            )
        elif clock == "WARN":
            warnings.append(
                {
                    "level": "amber",
                    "code": "clock-warn",
                    "message": f"{name}: clock WARN",
                    "node": name,
                }
            )
        for w in node.get("warnings") or []:
            warnings.append(
                {
                    "level": "amber",
                    "code": "node-warning",
                    "message": f"{name}: {w}",
                    "node": name,
                }
            )
    return warnings


_RECENT_PROBLEM_CODES = frozenset(
    {
        "fleet-not-ok",
        "workspace-conflict",
        "ssh-fail",
        "proxy-fail",
        "accounting-fail",
        "clock-fail",
    }
)


def _recent_problems_from_warnings(
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Actionable FAIL / red items only — not the full warning strip."""
    out: list[dict[str, Any]] = []
    for w in warnings:
        code = str(w.get("code") or "")
        level = str(w.get("level") or "")
        if level == "red" or code in _RECENT_PROBLEM_CODES:
            out.append(w)
    return out[:12]


def _node_health_rows(
    registry: dict[str, Any],
    status_doc: Optional[dict[str, Any]],
    cursors: list[dict[str, Any]],
    *,
    user_counts: Optional[dict[str, int]] = None,
    traffic_today: Optional[dict[str, dict[str, int]]] = None,
) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for node in status_doc.get("nodes") or [] if status_doc else []:
        if isinstance(node, dict) and node.get("name"):
            by_name[str(node["name"])] = node
    by_id = {c["node_id"]: c for c in cursors}
    rows: list[dict[str, Any]] = []
    for node in registry.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        name = str(node.get("name") or "")
        nid = str(node.get("node_id") or "")
        probe = by_name.get(name) or {}
        cur = by_id.get(nid) or {}
        host = str(node.get("ssh_host") or "")
        user = str(node.get("ssh_user") or "root")
        port = int(node.get("ssh_port") or 22)
        endpoint = f"{user}@{host}:{port}" if host else "—"
        today = (traffic_today or {}).get(nid) or {}
        today_bytes = int(today.get("bytes") or 0)
        rows.append(
            {
                "name": name,
                "node_id": nid,
                "lifecycle": fleet().node_lifecycle_status(node),
                "enabled": bool(node.get("enabled")),
                "ssh_host": node.get("ssh_host"),
                "ssh_user": node.get("ssh_user"),
                "ssh_port": node.get("ssh_port"),
                "endpoint": endpoint,
                "ssh": probe.get("ssh", "-"),
                "proxy": probe.get("proxy", "-"),
                "accounting": probe.get("accounting", "-"),
                "health": (
                    "FAIL"
                    if probe.get("ssh") == "FAIL"
                    or probe.get("proxy") == "FAIL"
                    or probe.get("accounting") == "FAIL"
                    else probe.get("ssh")
                    or probe.get("proxy")
                    or "—"
                ),
                "version": probe.get("vincula_version"),
                "clock": probe.get("clock"),
                "clock_skew_seconds": probe.get("clock_skew_seconds"),
                "instance_id": probe.get("instance_id") or cur.get("instance_id"),
                "last_sync_at": cur.get("last_sync_at"),
                "cursor_status": cur.get("cursor_status"),
                "last_event_id": cur.get("last_event_id"),
                "registry": probe.get("registry"),
                "user_count": int((user_counts or {}).get(nid) or 0),
                "traffic_today_bytes": today_bytes,
                "traffic_today_human": _human_bytes(today_bytes),
                "warnings": list(probe.get("warnings") or []),
                "checks": list(probe.get("checks") or []),
            }
        )
    return rows


def api_overview() -> dict[str, Any]:
    f = fleet()
    registry = f.load_registry()
    status_doc = load_last_status_doc()
    conn = f.open_cache_readonly()
    try:
        cursors = _sync_cursors(conn, registry)
        start, end = f.stats_date_window(7)
        today_start, today_end = f.stats_date_window(1)
        top_users_raw = f.query_daily_grouped(
            conn,
            start=start,
            end=end,
            group_by=("user_id", "node_id"),
        )
        top_hosts_raw = f.query_daily_grouped(
            conn,
            start=start,
            end=end,
            group_by=("destination_host", "node_id"),
        )
        top_users = [
            f._stats_row_from_sql(registry, r) for r in top_users_raw[:10]
        ]
        top_hosts = [
            f._stats_row_from_sql(registry, r) for r in top_hosts_raw[:10]
        ]
        traffic_today = _traffic_totals_for_window(
            conn, start=today_start, end=today_end
        )
        traffic_trend = _traffic_trend(conn, days=7)
        user_counts = _node_user_counts(conn)
        node_today = _node_bytes_map(conn, days=1)
        snap_users = _users_from_snapshot(conn, registry)
        user_count = len(snap_users)
        recent_conns = int(traffic_today.get("connection_count") or 0)
    finally:
        conn.close()

    health_rows = _node_health_rows(
        registry,
        status_doc,
        cursors,
        user_counts=user_counts,
        traffic_today=node_today,
    )
    active = [
        r
        for r in health_rows
        if r["lifecycle"] == f.NODE_STATUS_ACTIVE
    ]
    healthy = 0
    unhealthy = 0
    for row in active:
        if row["ssh"] == "FAIL" or row["proxy"] == "FAIL" or row["accounting"] == "FAIL":
            unhealthy += 1
        elif row["ssh"] in ("OK", "-") and row["proxy"] in ("OK", "STALE", "-"):
            if row["accounting"] in ("OK", "STALE", "-"):
                healthy += 1
            else:
                unhealthy += 1
        else:
            if row["ssh"] == "-" and row["proxy"] == "-" and not status_doc:
                pass
            else:
                unhealthy += 1
    if status_doc is None:
        healthy = 0
        unhealthy = len(active)

    warnings = _warnings_from_status(status_doc)
    workspace = _workspace_surface()
    if workspace.get("conflict") not in (None, "ok", "absent"):
        warnings = list(warnings) + [
            {
                "level": "red",
                "code": "workspace-conflict",
                "message": (
                    f"Workspace conflict: {workspace['conflict']} "
                    f"(fleet_id={workspace.get('fleet_id') or '—'})"
                ),
            }
        ]
    elif not workspace.get("active"):
        warnings = list(warnings) + [
            {
                "level": "amber",
                "code": "workspace-absent",
                "message": (
                    "No portable workspace yet. Run "
                    "`vcl-fleet workspace init` (or adopt/provision a node)."
                ),
            }
        ]

    last_sync_candidates = [
        c.get("last_sync_at")
        for c in cursors
        if c.get("last_sync_at")
    ]
    last_sync_at = None
    if last_sync_candidates:
        last_sync_at = max(str(x) for x in last_sync_candidates)
    cache_age = _cache_age_seconds(last_sync_at)
    recent_problems = _recent_problems_from_warnings(warnings)

    return {
        "schema_version": UI_SCHEMA_VERSION,
        "version": f.VCL_FLEET_VERSION,
        "accounting_mode": "approximate",
        "accounting_note": (
            "Fleet accounting is approximate (Clash polling). "
            "Totals are not byte-identical with node vcl stats."
        ),
        "fleet_health": "OK" if unhealthy == 0 and active else (
            "DEGRADED" if active else "EMPTY"
        ),
        "node_count": len(registry.get("nodes") or []),
        "active_node_count": len(active),
        "healthy": healthy,
        "unhealthy": unhealthy,
        "offline": unhealthy,
        "user_count": user_count,
        "active_connections_today": recent_conns,
        "traffic_today": traffic_today,
        "last_sync_at": last_sync_at,
        "cache_age_seconds": cache_age,
        "last_status_at": (status_doc or {}).get("controller_utc"),
        "last_status_ok": (status_doc or {}).get("ok"),
        "cursors": cursors,
        "traffic_trend": traffic_trend,
        "node_health": health_rows,
        "top_users": top_users,
        "top_hosts": top_hosts,
        "recent_problems": recent_problems,
        "stats_window": {"days": 7, "from": start, "to": end},
        "warnings": warnings,
        "workspace": workspace,
    }


def api_nodes(*, live_overlay: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Node health table (cache + optional live probe overlay)."""
    f = fleet()
    registry = f.load_registry()
    status_doc = load_last_status_doc()
    if live_overlay:
        status_doc = dict(live_overlay)
    conn = f.open_cache_readonly()
    try:
        cursors = _sync_cursors(conn, registry)
        user_counts = _node_user_counts(conn)
        node_today = _node_bytes_map(conn, days=1)
    finally:
        conn.close()
    workspace = _workspace_surface()
    warnings = _warnings_from_status(status_doc)
    if workspace.get("conflict") not in (None, "ok", "absent"):
        warnings = list(warnings) + [
            {
                "level": "red",
                "code": "workspace-conflict",
                "message": (
                    f"Workspace conflict: {workspace['conflict']} "
                    f"(fleet_id={workspace.get('fleet_id') or '—'})"
                ),
            }
        ]
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "accounting_mode": "approximate",
        "data_source": "live-probe" if live_overlay else "cache",
        "last_status_at": (status_doc or {}).get("controller_utc"),
        "last_status_ok": (status_doc or {}).get("ok"),
        "nodes": _node_health_rows(
            registry,
            status_doc,
            cursors,
            user_counts=user_counts,
            traffic_today=node_today,
        ),
        "warnings": warnings,
        "workspace": workspace,
    }


def api_health() -> dict[str, Any]:
    """Legacy alias for ``api_nodes`` (AC-3.1 fixtures)."""
    return api_nodes()


def api_operations(*, limit: int = 100) -> dict[str, Any]:
    lim = max(1, min(int(limit), 500))
    rows = read_ui_operations(limit=lim)
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "limit": lim,
        "rows": rows,
        "note": "Local fleet operation journal (CLI + UI); secrets redacted.",
    }


def api_node(name: str) -> dict[str, Any]:
    f = fleet()
    validate = f.validate_name
    validate(name)
    registry = f.load_registry()
    node = f.require_node(registry, name)
    status_doc = load_last_status_doc()
    probe = None
    for n in (status_doc or {}).get("nodes") or []:
        if isinstance(n, dict) and n.get("name") == name:
            probe = n
            break
    conn = f.open_cache_readonly()
    try:
        instances = f.list_instances(conn, node["node_id"])
        cursor = f.read_sync_cursor_row(conn, node["node_id"])
        start, end = f.stats_date_window(7)
        usage_raw = f.query_daily_grouped(
            conn,
            start=start,
            end=end,
            group_by=("user_id", "node_id", "destination_host"),
            extra_where=["node_id = ?"],
            extra_params=[node["node_id"]],
        )
        usage = [f._stats_row_from_sql(registry, r) for r in usage_raw[:20]]
        users_on_node = []
        for u in _users_from_snapshot(conn, registry):
            for n in u.get("nodes") or []:
                if n.get("node_id") == node["node_id"] or n.get("name") == name:
                    users_on_node.append(
                        {
                            "tag": u.get("tag"),
                            "user_id": u.get("user_id"),
                            "department": u.get("department"),
                            "enabled": n.get("enabled"),
                            "status": n.get("status"),
                            "has_active_credential": n.get(
                                "has_active_credential"
                            ),
                        }
                    )
                    break
        node_today = _node_bytes_map(conn, days=1).get(str(node["node_id"])) or {}
        traffic_today = {
            "upload_bytes": int(node_today.get("upload_bytes") or 0),
            "download_bytes": int(node_today.get("download_bytes") or 0),
            "bytes": int(node_today.get("bytes") or 0),
            "connection_count": int(node_today.get("connection_count") or 0),
            "bytes_human": _human_bytes(int(node_today.get("bytes") or 0)),
        }
    finally:
        conn.close()
    cursor_doc = None
    if cursor is not None:
        cursor_doc = {
            "instance_id": f._optional_text(cursor["instance_id"]),
            "last_event_id": int(cursor["last_event_id"]),
            "last_sync_at": cursor["last_sync_at"],
            "status": cursor["status"],
        }
    host = str(node.get("ssh_host") or "")
    endpoint = (
        f"{node.get('ssh_user') or 'root'}@{host}:{int(node.get('ssh_port') or 22)}"
        if host
        else "—"
    )
    last_ops = [
        r
        for r in read_ui_operations(limit=50)
        if str(r.get("target") or "") in ("", name)
        or name in str(r.get("target") or "")
    ][:20]
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "node": {
            "name": node["name"],
            "node_id": node["node_id"],
            "ssh_host": node["ssh_host"],
            "ssh_user": node["ssh_user"],
            "ssh_port": node["ssh_port"],
            "endpoint": endpoint,
            "enabled": node["enabled"],
            "status": f.node_lifecycle_status(node),
        },
        "probe": probe,
        "cursor": cursor_doc,
        "instances": instances,
        "users": users_on_node,
        "traffic_today": traffic_today,
        "recent_usage": usage,
        "last_operations": last_ops,
        "stats_window": {"days": 7, "from": start, "to": end},
        "secrets_note": (
            "URI / credential UUID / Reality keys / Clash secret are never shown."
        ),
    }


def _users_from_db(conn: Any, registry: dict[str, Any]) -> list[dict[str, Any]]:
    f = fleet()
    rows = conn.execute(
        """
        SELECT user_id, MAX(user_tag) AS user_tag, node_id
        FROM (
          SELECT user_id, user_tag, node_id FROM audit_events
          WHERE user_id IS NOT NULL AND user_id != ''
            AND node_id IS NOT NULL AND node_id != ''
          UNION ALL
          SELECT user_id, user_tag, node_id FROM daily_usage
          WHERE user_id IS NOT NULL AND user_id != ''
            AND node_id IS NOT NULL AND node_id != ''
        )
        GROUP BY user_id, node_id
        ORDER BY MAX(user_tag), user_id, node_id
        """
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        uid = str(row["user_id"])
        tag = f._optional_text(row["user_tag"]) or uid
        nid = str(row["node_id"])
        if uid not in grouped:
            grouped[uid] = {
                "tag": tag,
                "user_id": uid,
                "display_name": None,
                "department": None,
                "source": "fleet.db",
                "nodes": [],
            }
            order.append(uid)
        rec = grouped[uid]
        if tag and rec["tag"] == uid:
            rec["tag"] = tag
        node_name = f.node_display_name(registry, nid)
        if not any(n.get("node_id") == nid for n in rec["nodes"]):
            rec["nodes"].append(
                {
                    "name": node_name,
                    "node_id": nid,
                    "tag": tag,
                    "enabled": None,
                    "status": "seen-in-sync",
                    "has_active_credential": None,
                }
            )
    return [grouped[k] for k in order]


def _merge_users_snapshot_cache(
    snapshot: list[dict[str, Any]],
    cache: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Snapshot is authoritative for who exists; cache overlays live enabled state."""
    if not snapshot:
        return cache
    if not cache:
        return snapshot
    by_uid: dict[str, dict[str, Any]] = {}
    by_tag: dict[str, dict[str, Any]] = {}
    for u in cache:
        uid = str(u.get("user_id") or "")
        tag = str(u.get("tag") or "")
        if uid:
            by_uid[uid] = u
        if tag:
            by_tag[tag] = u
    out: list[dict[str, Any]] = []
    seen_uids: set[str] = set()
    for su in snapshot:
        rec = dict(su)
        uid = str(su.get("user_id") or "")
        tag = str(su.get("tag") or "")
        cu = by_uid.get(uid) or by_tag.get(tag)
        if cu:
            if not rec.get("department") and cu.get("department"):
                rec["department"] = cu["department"]
            if not rec.get("display_name") and cu.get("display_name"):
                rec["display_name"] = cu["display_name"]
            cache_nodes = {
                str(n.get("name") or ""): n
                for n in (cu.get("nodes") or [])
                if isinstance(n, dict) and n.get("name")
            }
            merged_nodes: list[dict[str, Any]] = []
            for sn in rec.get("nodes") or []:
                if not isinstance(sn, dict):
                    continue
                mn = dict(sn)
                cn = cache_nodes.get(str(sn.get("name") or ""))
                if cn:
                    if cn.get("enabled") is not None:
                        mn["enabled"] = cn["enabled"]
                    if cn.get("status"):
                        mn["status"] = cn["status"]
                    if cn.get("has_active_credential") is not None:
                        mn["has_active_credential"] = cn["has_active_credential"]
                merged_nodes.append(mn)
            rec["nodes"] = merged_nodes
            rec["source"] = "user_snapshot+refresh"
        out.append(rec)
        if uid:
            seen_uids.add(uid)
    for cu in cache:
        uid = str(cu.get("user_id") or "")
        if uid and uid not in seen_uids:
            extra = dict(cu)
            extra["source"] = cu.get("source") or "users-cache"
            out.append(extra)
    return out


def api_users() -> dict[str, Any]:
    f = fleet()
    registry = f.load_registry()
    cache = load_users_cache()
    conn = f.open_cache_readonly()
    try:
        snapshot_users = _users_from_snapshot(conn, registry)
        cache_users = (
            sanitize_users_for_ui(cache["users"])
            if cache and isinstance(cache.get("users"), list) and cache["users"]
            else []
        )
        if snapshot_users:
            users = _merge_users_snapshot_cache(snapshot_users, cache_users)
            if cache_users:
                source = "user_snapshot+users-cache"
                note = (
                    "User list from sync snapshot; enabled state merged from last "
                    "Refresh users (SSH). No VLESS URI, credential UUID, or secrets."
                )
                ok = cache.get("ok")
                refreshed_at = cache.get("refreshed_at")
                unreachable = cache.get("unreachable") or []
            else:
                source = snapshot_users[0].get("source") or "user_snapshot"
                note = (
                    "From user_snapshot / synced audit. "
                    "Refresh users over SSH for latest enabled state. "
                    "No VLESS URI, credential UUID, or secrets."
                )
                ok = True
                refreshed_at = None
                unreachable = []
        elif cache_users:
            users = cache_users
            source = "users-cache"
            note = (
                "Cached from last Refresh users (SSH). "
                "Run sync --full for full user list. "
                "No VLESS URI, credential UUID, or secrets."
            )
            ok = cache.get("ok")
            refreshed_at = cache.get("refreshed_at")
            unreachable = cache.get("unreachable") or []
        else:
            users = []
            source = "fleet.db"
            note = (
                "No users in snapshot or cache. "
                "Run sync --full or Refresh users."
            )
            ok = True
            refreshed_at = None
            unreachable = []
        users = _enrich_users_traffic(users, conn)
    finally:
        conn.close()
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "source": source,
        "ok": ok,
        "refreshed_at": refreshed_at,
        "users": users,
        "unreachable": unreachable,
        "note": note,
        "accounting_mode": "approximate",
    }


def api_user(tag: str) -> dict[str, Any]:
    f = fleet()
    f.validate_name(tag)
    registry = f.load_registry()
    users_doc = api_users()
    match = None
    for user in users_doc.get("users") or []:
        if str(user.get("tag") or "") == tag:
            match = user
            break
        if str(user.get("user_id") or "") == tag:
            match = user
            break
    conn = f.open_cache_readonly()
    try:
        uid = None
        if match and match.get("user_id"):
            uid = str(match["user_id"])
        else:
            uid = resolve_user_id_for_ui(conn, registry, tag, allow_ssh=False)
        recent: list[dict[str, Any]] = []
        destinations: list[dict[str, Any]] = []
        start = end = None
        if uid:
            start, end = f.stats_date_window(7)
            raw = f.query_daily_grouped(
                conn,
                start=start,
                end=end,
                group_by=("node_id", "user_id"),
                extra_where=["user_id = ?"],
                extra_params=[uid],
            )
            recent = [f._stats_row_from_sql(registry, r) for r in raw]
            dest_raw = f.query_daily_grouped(
                conn,
                start=start,
                end=end,
                group_by=("destination_host",),
                extra_where=["user_id = ?"],
                extra_params=[uid],
            )
            for row in dest_raw[:20]:
                upload = int(row["upload_bytes"] or 0)
                download = int(row["download_bytes"] or 0)
                host = f._optional_text(row["destination_host"]) or "(unknown)"
                destinations.append(
                    {
                        "destination_host": host,
                        "upload_bytes": upload,
                        "download_bytes": download,
                        "bytes": upload + download,
                        "connection_count": int(row["connection_count"] or 0),
                        "bytes_human": _human_bytes(upload + download),
                    }
                )
    finally:
        conn.close()
    if match is None and uid is None:
        raise KeyError(f"unknown user: {tag}")
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "user": match
        or {
            "tag": tag,
            "user_id": uid,
            "nodes": [],
            "source": "fleet.db",
        },
        "recent_usage": recent,
        "destinations": destinations,
        "stats_window": {"days": 7, "from": start, "to": end},
        "secrets_note": (
            "URI / credential UUID / Reality keys / Clash secret are never shown."
        ),
    }


def resolve_user_id_for_ui(
    conn: Any,
    registry: dict[str, Any],
    tag_or_id: str,
    *,
    allow_ssh: bool = False,
) -> Optional[str]:
    """Local Read Plane tag→user_id (user_snapshot → events/usage). Never SSH."""
    del registry, allow_ssh  # UI GET is cache-only; keep kwargs for callers.
    f = fleet()
    text = (tag_or_id or "").strip()
    if not text:
        return None
    if UUID_RE.fullmatch(text):
        return text
    f.validate_name(text)
    ids = f.local_user_ids_for_tag(conn, text)
    if len(ids) > 1:
        detail = ", ".join(sorted(ids))
        raise ValueError(
            f"LOCAL_USER_ID_CONFLICT: tag {text} maps to multiple user_ids: "
            f"{detail}"
        )
    if len(ids) == 1:
        return next(iter(ids))
    return None


def api_audit(params: dict[str, str]) -> dict[str, Any]:
    f = fleet()
    audit = f.load_audit_module()
    user = (params.get("user") or "").strip()
    if not user:
        raise ValueError("user is required (tag or user_id)")
    query_from_raw = (params.get("from") or "").strip()
    query_to_raw = (params.get("to") or "").strip()
    if not query_from_raw or not query_to_raw:
        raise ValueError("--from and --to (RFC3339) are required")
    query_from = audit.parse_rfc3339(query_from_raw)
    query_to = audit.parse_rfc3339(query_to_raw)
    if query_from > query_to:
        raise ValueError("--from must not be after --to")
    # RFC3339 strings → aware datetimes for window cap.
    from_dt = datetime.fromisoformat(query_from.replace("Z", "+00:00"))
    to_dt = datetime.fromisoformat(query_to.replace("Z", "+00:00"))
    if to_dt - from_dt > timedelta(days=AUDIT_MAX_WINDOW_DAYS):
        raise ValueError(
            f"audit window must be <= {AUDIT_MAX_WINDOW_DAYS} days "
            "(narrow --from/--to)"
        )
    node_name = (params.get("node") or "").strip() or None
    destination = (params.get("destination") or "").strip().lower() or None
    destination_ip = (params.get("destination_ip") or "").strip() or None
    network = (params.get("network") or "").strip().lower() or None
    port_raw = (params.get("port") or "").strip()
    destination_port: Optional[int] = None
    if port_raw:
        try:
            destination_port = int(port_raw)
        except ValueError as exc:
            raise ValueError("port must be an integer") from exc
        if destination_port < 1 or destination_port > 65535:
            raise ValueError("port must be 1..65535")
    limit_raw = (params.get("limit") or "").strip()
    if limit_raw:
        try:
            limit = int(limit_raw)
        except ValueError as exc:
            raise ValueError("limit must be an integer") from exc
    else:
        limit = AUDIT_DEFAULT_LIMIT
    if limit < 1 or limit > AUDIT_MAX_LIMIT:
        raise ValueError(f"limit must be 1..{AUDIT_MAX_LIMIT}")
    after_started = (params.get("after_started_at") or "").strip() or None
    after_event = (params.get("after_event_id") or "").strip() or None
    after_node = (params.get("after_node_id") or "").strip() or None
    after_event_id = None
    if after_started or after_event or after_node:
        if not (after_started and after_event and after_node):
            raise ValueError(
                "cursor requires after_started_at, after_event_id, after_node_id"
            )
        after_event_id = int(after_event)
    registry = f.load_registry()
    node_id = None
    if node_name:
        f.validate_name(node_name)
        node_id = f.require_node(registry, node_name)["node_id"]
    conn = f.open_cache_readonly()
    try:
        user_id = resolve_user_id_for_ui(
            conn, registry, user, allow_ssh=False
        )
        if not user_id:
            raise KeyError(
                f"unknown user in local cache: {user} "
                "(Sync / Refresh users, or pass user_id UUID)"
            )
        # Fetch limit+1 to detect truncation. Destination is in SQL so
        # LIMIT/cursor apply to matching rows, not a pre-filter page.
        raw_rows = f.query_fleet_audit(
            conn,
            user_id=user_id,
            query_from=query_from,
            query_to=query_to,
            node_id=node_id,
            destination_contains=destination,
            destination_ip=destination_ip,
            destination_port=destination_port,
            network=network,
            limit=limit + 1,
            after_started_at=after_started,
            after_event_id=after_event_id,
            after_node_id=after_node,
        )
    finally:
        conn.close()

    truncated = len(raw_rows) > limit
    if truncated:
        raw_rows = raw_rows[:limit]

    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        upload = f._row_int(raw, "upload_bytes")
        download = f._row_int(raw, "download_bytes")
        dest = f.destination_display(
            raw["destination_host"], raw["destination_ip"]
        )
        traffic = upload + download
        rows.append(
            {
                "time": raw["started_at"],
                "node": f.node_display_name(registry, raw["node_id"]),
                "instance": f.instance_display(
                    f._optional_text(raw["instance_id"])
                ),
                "destination": dest,
                "destination_host": f._optional_text(raw["destination_host"]),
                "destination_ip": f._optional_text(raw["destination_ip"]),
                "destination_port": raw["destination_port"],
                "network": f._optional_text(raw["network"]),
                "upload_bytes": upload,
                "download_bytes": download,
                "traffic": traffic,
                "traffic_human": _human_bytes(traffic),
                "upload_human": _human_bytes(upload),
                "download_human": _human_bytes(download),
                "node_id": raw["node_id"],
                "user_id": raw["user_id"],
                "user_tag": raw["user_tag"],
                "event_id": int(raw["event_id"]),
                "started_at": raw["started_at"],
                "last_seen_at": raw["last_seen_at"],
                "closed_at": raw["closed_at"],
            }
        )
    next_cursor = None
    if truncated and rows:
        last = rows[-1]
        next_cursor = {
            "after_started_at": last["started_at"],
            "after_event_id": last["event_id"],
            "after_node_id": last["node_id"],
        }
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "user": user,
        "user_id": user_id,
        "from": query_from,
        "to": query_to,
        "node": node_name,
        "destination": destination,
        "destination_ip": destination_ip,
        "port": destination_port,
        "network": network,
        "limit": limit,
        "truncated": truncated,
        "next_cursor": next_cursor,
        "rows": rows,
        "empty_hint": (
            "No rows. Sync audit first (Sync), then widen the time window."
            if not rows
            else None
        ),
    }


def api_stats_top(
    kind: str,
    days: int,
    *,
    node: Optional[str] = None,
    user: Optional[str] = None,
    department: Optional[str] = None,
    destination: Optional[str] = None,
) -> dict[str, Any]:
    f = fleet()
    if kind not in ("users", "hosts", "nodes"):
        raise ValueError("kind must be users, hosts, or nodes")
    if days < 1:
        raise ValueError("days must be >= 1")
    registry = f.load_registry()
    start, end = f.stats_date_window(days)
    if kind == "nodes":
        group_by: tuple[str, ...] = ("node_id",)
    elif kind == "users":
        group_by = ("user_id", "node_id")
    else:
        group_by = ("destination_host", "node_id")
    extra_where: list[str] = []
    extra_params: list[Any] = []
    if node:
        f.validate_name(node)
        nid = f.require_node(registry, node)["node_id"]
        extra_where.append("node_id = ?")
        extra_params.append(nid)
    if destination:
        extra_where.append("lower(destination_host) LIKE ? ESCAPE '\\'")
        extra_params.append(f._sql_like_contains(destination.lower()))
    conn = f.open_cache_readonly()
    try:
        allowed_uids: Optional[set[str]] = None
        if user or department:
            snap_users = _users_from_snapshot(conn, registry)
            # Also merge department from users-cache when present.
            cache = load_users_cache()
            by_uid: dict[str, dict[str, Any]] = {
                str(u.get("user_id")): u
                for u in snap_users
                if u.get("user_id")
            }
            if cache and isinstance(cache.get("users"), list):
                for u in sanitize_users_for_ui(cache["users"]):
                    uid = str(u.get("user_id") or "")
                    if not uid:
                        continue
                    if uid in by_uid:
                        if u.get("department") and not by_uid[uid].get(
                            "department"
                        ):
                            by_uid[uid]["department"] = u.get("department")
                        if u.get("tag"):
                            by_uid[uid]["tag"] = u.get("tag")
                    else:
                        by_uid[uid] = u
            allowed_uids = set()
            for u in by_uid.values():
                if user:
                    tag = str(u.get("tag") or "")
                    uid = str(u.get("user_id") or "")
                    if user not in (tag, uid):
                        continue
                if department:
                    dept = str(u.get("department") or "")
                    if dept.lower() != department.lower():
                        continue
                if u.get("user_id"):
                    allowed_uids.add(str(u["user_id"]))
            if not allowed_uids:
                # No matching users → empty table/totals/trend (same filter plane).
                return {
                    "schema_version": UI_SCHEMA_VERSION,
                    "mode": f"top-{kind}",
                    "days": days,
                    "from": start,
                    "to": end,
                    "accounting_mode": "approximate",
                    "filters": {
                        "node": node,
                        "user": user,
                        "department": department,
                        "destination": destination,
                    },
                    "rows": [],
                    "totals": {
                        **f._stats_totals([]),
                        "upload_human": _human_bytes(0),
                        "download_human": _human_bytes(0),
                        "bytes_human": _human_bytes(0),
                    },
                    "trend": [],
                }
        if allowed_uids is not None:
            placeholders = ",".join("?" for _ in allowed_uids)
            extra_where.append(f"user_id IN ({placeholders})")
            extra_params.extend(sorted(allowed_uids))
        raw = f.query_daily_grouped(
            conn,
            start=start,
            end=end,
            group_by=group_by,
            extra_where=extra_where or None,
            extra_params=extra_params or None,
        )
        rows = [f._stats_row_from_sql(registry, r) for r in raw]
        totals = f._stats_totals(rows)
        trend = _traffic_trend(
            conn,
            days=days,
            extra_where=extra_where or None,
            extra_params=list(extra_params) if extra_params else None,
        )
    finally:
        conn.close()
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "mode": f"top-{kind}",
        "days": days,
        "from": start,
        "to": end,
        "accounting_mode": "approximate",
        "filters": {
            "node": node,
            "user": user,
            "department": department,
            "destination": destination,
        },
        "rows": rows,
        "totals": {
            **totals,
            "upload_human": _human_bytes(int(totals.get("upload_bytes") or 0)),
            "download_human": _human_bytes(int(totals.get("download_bytes") or 0)),
            "bytes_human": _human_bytes(int(totals.get("bytes") or 0)),
        },
        "trend": trend,
    }


def api_refresh_probe() -> dict[str, Any]:
    """Live SSH probe (``cmd_probe`` path). Does not write last-status.json."""
    f = fleet()
    payload = f.run_status_payload(include_all=False)
    payload = dict(payload)
    payload.pop("_rows", None)
    code = 0 if payload.get("ok") else 1
    state = "SUCCESS" if code == 0 else "FAIL"
    append_ui_operation(
        operation="probe",
        state=state,
        exit_code=code,
        ok=code == 0,
    )
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "operation": "probe",
        "exit_code": code,
        "ok": code == 0,
        "result": payload,
    }


def api_refresh_verify() -> dict[str, Any]:
    """Live verify; writes last-status.json (same as CLI verify)."""
    f = fleet()
    payload = f.run_verify_payload(include_all=False)
    payload = dict(payload)
    payload.pop("_rows", None)
    code = 0 if payload.get("ok") else 1
    state = "SUCCESS" if code == 0 else "FAIL"
    append_ui_operation(
        operation="verify",
        state=state,
        exit_code=code,
        ok=code == 0,
    )
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "operation": "verify",
        "exit_code": code,
        "ok": code == 0,
        "result": payload,
    }


def api_refresh_status(*, verify: bool) -> dict[str, Any]:
    """Backward-compatible refresh routes."""
    if verify:
        return api_refresh_verify()
    return api_refresh_probe()


def api_sync(*, node: Optional[str] = None) -> dict[str, Any]:
    """UI Sync = CLI ``sync --full`` (D53). Never legacy bare sync."""
    f = fleet()
    ns = argparse.Namespace(
        node=node,
        all=False,
        reseed=None,
        as_json=True,
        full=True,
    )
    with f.fleet_op_lock():
        code, payload = f.run_sync_full_payload(ns)
    state = str((payload or {}).get("state") or ("SUCCESS" if code == 0 else "FAIL"))
    append_ui_operation(
        operation="sync_full",
        target=str(node or ""),
        state=state,
        exit_code=code,
        ok=code == 0,
    )
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "operation": "sync_full",
        "exit_code": code,
        "ok": code == 0,
        "result": payload,
    }


def api_refresh_users() -> dict[str, Any]:
    f = fleet()
    code, payload = f.run_user_list_payload()
    if not isinstance(payload, dict):
        raise RuntimeError("user list did not return JSON")
    users_raw: list[dict[str, Any]] = []
    for user in payload.get("users") or []:
        if not isinstance(user, dict):
            continue
        nodes_out = []
        for n in user.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            # Map SSH list → UI fields; sanitize drops active_credential_id.
            nodes_out.append(
                {
                    "name": n.get("name"),
                    "tag": n.get("tag"),
                    "enabled": n.get("enabled"),
                    "status": n.get("status"),
                    "active_credential_id": n.get("active_credential_id"),
                }
            )
        users_raw.append(
            {
                "tag": user.get("tag"),
                "user_id": user.get("user_id"),
                "display_name": user.get("display_name"),
                "department": user.get("department"),
                "source": "ssh-refresh",
                "nodes": nodes_out,
            }
        )
    users_out = sanitize_users_for_ui(users_raw)
    cache = {
        "schema_version": UI_SCHEMA_VERSION,
        "ok": bool(payload.get("ok")),
        "state": payload.get("state"),
        "refreshed_at": f.format_utc(datetime.now(timezone.utc)),
        "users": users_out,
        "unreachable": payload.get("unreachable") or [],
    }
    write_users_cache(cache)
    append_ui_operation(
        operation="refresh_users",
        state=str(payload.get("state") or ("SUCCESS" if code == 0 else "FAIL")),
        exit_code=code,
        ok=code == 0,
    )
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "operation": "refresh-users",
        "exit_code": code,
        "ok": code == 0,
        "result": cache,
    }


class FleetUIHandler(BaseHTTPRequestHandler):
    def version_string(self) -> str:
        return f"VinculaFleetUI/{fleet().VCL_FLEET_VERSION}"

    def setup(self) -> None:
        super().setup()
        timeout = getattr(self.server, "request_timeout", None)
        if timeout:
            try:
                self.connection.settimeout(float(timeout))
            except OSError:
                pass

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(
            f"[ui] {self.address_string()} - {fmt % args}\n"
        )

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; "
            "form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: Any) -> None:
        body = (
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _send_error_id(self, code: int, message: str) -> None:
        error_id = uuid.uuid4().hex[:12]
        sys.stderr.write(f"[ui] error_id={error_id} {message}\n")
        self._send_json(code, {"error": message, "error_id": error_id})

    def _send_fleet_exit(self, exc: SystemExit) -> None:
        code = exc.code
        f = fleet()
        if code == getattr(f, "FLEET_BUSY_EXIT", 4):
            self._send_json(
                409, {"error": getattr(f, "FLEET_BUSY_MSG", "busy")}
            )
            return
        self._send_json(400, {"error": f"fleet error (exit {code})"})

    def _listen_port(self) -> int:
        try:
            return int(self.server.server_address[1])
        except (AttributeError, TypeError, IndexError, ValueError):
            return _LISTEN_PORT

    def _check_request_guards(self, *, for_api: bool, is_post: bool) -> bool:
        """Return False if a response was already sent."""
        listen_port = self._listen_port()
        host = self.headers.get("Host") or ""
        if not host_header_allowed(host, listen_port):
            self._send_json(403, {"error": "forbidden Host"})
            return False
        if for_api:
            token = self.headers.get(UI_TOKEN_HEADER) or ""
            if not _UI_TOKEN or not secrets.compare_digest(token, _UI_TOKEN):
                self._send_json(401, {"error": "missing or invalid UI token"})
                return False
        if is_post:
            if not content_type_is_json(self.headers.get("Content-Type")):
                self._send_json(
                    415,
                    {"error": "Content-Type must be application/json"},
                )
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin != "":
                if origin not in allowed_origins(listen_port):
                    self._send_json(403, {"error": "forbidden Origin"})
                    return False
            # Missing Origin is allowed (same-machine tools). Token +
            # loopback Host remain required. Browsers send Origin on POST.
        return True

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._handle_get()
        except Exception:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc() + "\n")
            self._send_error_id(500, "internal error")

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._handle_post()
        except Exception:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc() + "\n")
            self._send_error_id(500, "internal error")

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def _handle_get(self) -> None:
        if not self._check_request_guards(for_api=False, is_post=False):
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path.startswith("/api/"):
            if not self._check_request_guards(for_api=True, is_post=False):
                return
            self._handle_api_get(path, qs)
            return

        self._serve_static(path)

    def _handle_api_get(self, path: str, qs: dict[str, list[str]]) -> None:
        def one(key: str) -> str:
            vals = qs.get(key) or []
            return vals[0] if vals else ""

        try:
            if path == "/api/overview":
                self._send_json(200, api_overview())
                return
            if path in ("/api/health", "/api/nodes"):
                self._send_json(200, api_nodes())
                return
            if path == "/api/operations":
                lim_raw = one("limit") or "100"
                try:
                    lim = int(lim_raw)
                except ValueError as exc:
                    raise ValueError("limit must be an integer") from exc
                self._send_json(200, api_operations(limit=lim))
                return
            if path == "/api/recipes":
                self._send_json(200, recipes_payload())
                return
            if path == "/api/users":
                self._send_json(200, api_users())
                return
            m = re.fullmatch(r"/api/nodes/([a-z0-9][a-z0-9._-]{0,31})", path)
            if m:
                self._send_json(200, api_node(m.group(1)))
                return
            m = re.fullmatch(r"/api/users/([a-z0-9][a-z0-9._-]{0,31})", path)
            if m:
                self._send_json(200, api_user(m.group(1)))
                return
            if path == "/api/audit":
                self._send_json(
                    200,
                    api_audit(
                        {
                            "user": one("user"),
                            "from": one("from"),
                            "to": one("to"),
                            "node": one("node"),
                            "destination": one("destination"),
                            "destination_ip": one("destination_ip"),
                            "port": one("port"),
                            "network": one("network"),
                            "limit": one("limit"),
                            "after_started_at": one("after_started_at"),
                            "after_event_id": one("after_event_id"),
                            "after_node_id": one("after_node_id"),
                        }
                    ),
                )
                return
            if path == "/api/stats/top":
                kind = one("kind") or "users"
                days_raw = one("days") or "7"
                try:
                    days = int(days_raw)
                except ValueError as exc:
                    raise ValueError("days must be an integer") from exc
                self._send_json(
                    200,
                    api_stats_top(
                        kind,
                        days,
                        node=one("node") or None,
                        user=one("user") or None,
                        department=one("department") or None,
                        destination=one("destination") or None,
                    ),
                )
                return
            if path == "/api/command-builder":
                self._send_json(200, api_command_builder_meta())
                return
            if path == "/api/meta":
                self._send_json(
                    200,
                    {
                        "schema_version": UI_SCHEMA_VERSION,
                        "version": fleet().VCL_FLEET_VERSION,
                        "pages": [
                            "overview",
                            "nodes",
                            "users",
                            "traffic",
                            "audit",
                            "operations",
                        ],
                        "identity_mutations": False,
                        "cache_writes": ["refresh", "sync_full"],
                        "sync": "full",
                        "reseed": "cli-only",
                        "bind": "loopback-only",
                        "ui_contract": "D53-rev1",
                        "auth": {
                            "token_header": UI_TOKEN_HEADER,
                            "host_loopback_only": True,
                        },
                    },
                )
                return
            self._send_json(404, {"error": f"unknown api: {path}"})
        except KeyError as exc:
            self._send_json(404, {"error": str(exc)})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except SystemExit as exc:
            self._send_fleet_exit(exc)

    def _handle_post(self) -> None:
        if not self._check_request_guards(for_api=False, is_post=False):
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self._send_json(404, {"error": "not found"})
            return
        if not self._check_request_guards(for_api=True, is_post=True):
            return
        forbidden = (
            "/api/user/add",
            "/api/user/rotate",
            "/api/user/import",
            "/api/node/add",
            "/api/node/retire",
            "/api/node/replace",
            "/api/restore",
        )
        if path in forbidden or path.startswith("/api/mutate"):
            self._send_json(
                405,
                {
                    "error": (
                        "mutation APIs are not available; use CLI recipes"
                    ),
                },
            )
            return
        try:
            body = self._read_json_body()
            if path == "/api/refresh/probe":
                self._send_json(200, api_refresh_probe())
                return
            if path == "/api/refresh/verify":
                self._send_json(200, api_refresh_verify())
                return
            if path == "/api/refresh/status":
                self._send_json(200, api_refresh_probe())
                return
            if path == "/api/refresh/users":
                self._send_json(200, api_refresh_users())
                return
            if path == "/api/command-builder":
                self._send_json(200, api_command_build(body))
                return
            if path == "/api/sync":
                if "reseed" in body and body.get("reseed") not in (None, ""):
                    self._send_json(
                        400,
                        {
                            "error": (
                                "reseed is CLI-only; use "
                                "`vcl-fleet sync --reseed NAME`"
                            ),
                        },
                    )
                    return
                node = body.get("node")
                if node is not None and not isinstance(node, str):
                    raise ValueError("node must be a string")
                if node:
                    fleet().validate_name(node)
                self._send_json(200, api_sync(node=(node or None)))
                return
            self._send_json(404, {"error": f"unknown api: {path}"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except SystemExit as exc:
            self._send_fleet_exit(exc)

    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            rel = "index.html"
        else:
            rel = path.lstrip("/")
        if ".." in rel.split("/") or rel.startswith("/"):
            self._send_json(404, {"error": "not found"})
            return
        target = (_STATIC_DIR / rel).resolve()
        try:
            target.relative_to(_STATIC_DIR.resolve())
        except ValueError:
            self._send_json(404, {"error": "not found"})
            return
        if not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in (
            "application/javascript",
            "application/json",
        ):
            ctype = f"{ctype}; charset=utf-8"
        data = target.read_bytes()
        if rel == "index.html":
            meta = (
                f'<meta name="vcl-ui-token" content="{_UI_TOKEN}" />\n'
            ).encode("utf-8")
            head = b"</head>"
            if head in data:
                data = data.replace(head, meta + head, 1)
            else:
                data = meta + data
        self._send(200, data, ctype)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server with a worker cap and per-request socket timeout."""

    def __init__(
        self,
        server_address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        max_workers: int = UI_MAX_WORKERS,
        request_timeout: float = UI_REQUEST_TIMEOUT,
    ) -> None:
        super().__init__(server_address, handler)
        self.max_workers = max(1, int(max_workers))
        self.request_timeout = float(request_timeout)
        self._sema = threading.BoundedSemaphore(self.max_workers)

    def process_request(self, request: Any, client_address: Any) -> None:
        try:
            request.settimeout(self.request_timeout)
        except OSError:
            pass
        if not self._sema.acquire(timeout=UI_BUSY_WAIT_SECONDS):
            self._reject_busy(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            try:
                self._sema.release()
            except ValueError:
                pass
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            try:
                self._sema.release()
            except ValueError:
                pass

    def _reject_busy(self, request: Any) -> None:
        body = b'{"error":"too many workers"}\n'
        header = (
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n"
            b"Retry-After: 1\r\n"
            b"\r\n"
        )
        try:
            request.sendall(header + body)
        except OSError:
            pass
        try:
            request.close()
        except OSError:
            pass


def make_server(
    host: str,
    port: int,
    *,
    max_workers: int = UI_MAX_WORKERS,
    request_timeout: float = UI_REQUEST_TIMEOUT,
) -> BoundedThreadingHTTPServer:
    bind = assert_loopback_host(host)
    return BoundedThreadingHTTPServer(
        (bind, port),
        FleetUIHandler,
        max_workers=max_workers,
        request_timeout=request_timeout,
    )


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    fleet_mod: Any,
    static_dir: Optional[Path] = None,
    ready_callback: Optional[Callable[[ThreadingHTTPServer], None]] = None,
) -> int:
    set_fleet_module(fleet_mod)
    global _STATIC_DIR
    if static_dir is not None:
        _STATIC_DIR = Path(static_dir)
    if not _STATIC_DIR.is_dir():
        fleet_mod.die(f"ui static directory missing: {_STATIC_DIR}")
    migrate_users_cache()
    try:
        httpd = make_server(host, port)
    except ValueError as exc:
        fleet_mod.die(str(exc), 2)
        return 2
    bind_host = httpd.server_address[0]
    bind_port = httpd.server_address[1]
    set_ui_runtime(token=secrets.token_urlsafe(32), listen_port=bind_port)
    display = bind_host if ":" not in bind_host else f"[{bind_host}]"
    sys.stdout.write(f"Listening on http://{display}:{bind_port}\n")
    sys.stdout.write(
        "Local Audit UI (no identity mutations; Sync/Refresh write local "
        "cache; reseed is CLI-only). Ctrl+C to stop. "
        "Stopping does not affect VPS nodes.\n"
    )
    sys.stdout.flush()
    if ready_callback is not None:
        ready_callback(httpd)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write("\nShutting down UI.\n")
    finally:
        httpd.server_close()
    return 0


def serve_in_thread(
    host: str,
    port: int,
    *,
    fleet_mod: Any,
    static_dir: Optional[Path] = None,
    token: Optional[str] = None,
    max_workers: int = UI_MAX_WORKERS,
    request_timeout: float = UI_REQUEST_TIMEOUT,
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    """Test helper: start UI briefly without blocking forever.

    Returns ``(httpd, thread, ui_token)``.
    """
    set_fleet_module(fleet_mod)
    global _STATIC_DIR
    if static_dir is not None:
        _STATIC_DIR = Path(static_dir)
    migrate_users_cache()
    httpd = make_server(
        host, port, max_workers=max_workers, request_timeout=request_timeout
    )
    bind_port = httpd.server_address[1]
    tok = token or secrets.token_urlsafe(32)
    set_ui_runtime(token=tok, listen_port=bind_port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, tok
