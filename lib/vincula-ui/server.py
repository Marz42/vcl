#!/usr/bin/env python3
"""Localhost-only Fleet Audit UI (stdlib HTTP + static files).

Bound to loopback only. GET APIs are local-cache only. Explicit POST
refresh/sync write the workstation cache (not identity mutations).
No add/rotate/retire/replace/restore/import/reseed via UI.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import mimetypes
import re
import secrets
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


def users_cache_path() -> Path:
    return fleet().fleet_home() / "users-cache.json"


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


def load_users_cache() -> Optional[dict[str, Any]]:
    path = users_cache_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_users_cache(payload: dict[str, Any]) -> None:
    fleet()._atomic_write_json(users_cache_path(), payload)


def _human_bytes(n: int) -> str:
    value = float(max(0, int(n)))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{int(n)} B"


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
            "Sync/Refresh write local cache only. "
            "vcl-fleet sync --reseed is CLI-only (UI refuses reseed)."
        ),
        "recipes": [
            {
                "id": "init",
                "title": "Init fleet registry",
                "command": "vcl-fleet init",
            },
            {
                "id": "node-add",
                "title": "Add node (online)",
                "command": (
                    "vcl-fleet node add NAME --host HOST "
                    "--host-key SHA256:..."
                ),
            },
            {
                "id": "node-add-offline",
                "title": "Add node (offline)",
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
                "id": "backup-restore",
                "title": "Backup / restore (node CLI; see docs/backup.md)",
                "command": (
                    "vcl backup / vcl restore FILE --reissue-output FILE "
                    "--server HOST  # never via UI"
                ),
            },
            {
                "id": "sync",
                "title": "Sync (UI Sync button) / reseed (CLI only)",
                "command": (
                    "vcl-fleet sync [--node NAME]\n"
                    "vcl-fleet sync --reseed NAME   # CLI only; wipes local audit"
                ),
            },
            {
                "id": "status-verify",
                "title": "Status / verify (also UI Refresh)",
                "command": "vcl-fleet status|verify [--json] [--all]",
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


def _node_health_rows(
    registry: dict[str, Any],
    status_doc: Optional[dict[str, Any]],
    cursors: list[dict[str, Any]],
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
        rows.append(
            {
                "name": name,
                "node_id": nid,
                "lifecycle": fleet().node_lifecycle_status(node),
                "enabled": bool(node.get("enabled")),
                "ssh_host": node.get("ssh_host"),
                "ssh_user": node.get("ssh_user"),
                "ssh_port": node.get("ssh_port"),
                "ssh": probe.get("ssh", "-"),
                "proxy": probe.get("proxy", "-"),
                "accounting": probe.get("accounting", "-"),
                "version": probe.get("vincula_version"),
                "clock": probe.get("clock"),
                "clock_skew_seconds": probe.get("clock_skew_seconds"),
                "instance_id": probe.get("instance_id") or cur.get("instance_id"),
                "last_sync_at": cur.get("last_sync_at"),
                "cursor_status": cur.get("cursor_status"),
                "last_event_id": cur.get("last_event_id"),
                "registry": probe.get("registry"),
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
    finally:
        conn.close()

    health_rows = _node_health_rows(registry, status_doc, cursors)
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

    return {
        "schema_version": UI_SCHEMA_VERSION,
        "version": f.VCL_FLEET_VERSION,
        "accounting_mode": "approximate",
        "accounting_note": (
            "Fleet accounting is approximate (Clash polling). "
            "Totals are not byte-identical with node vcl stats."
        ),
        "node_count": len(registry.get("nodes") or []),
        "active_node_count": len(active),
        "healthy": healthy,
        "unhealthy": unhealthy,
        "last_status_at": (status_doc or {}).get("controller_utc"),
        "last_status_ok": (status_doc or {}).get("ok"),
        "cursors": cursors,
        "top_users": top_users,
        "top_hosts": top_hosts,
        "stats_window": {"days": 7, "from": start, "to": end},
        "warnings": _warnings_from_status(status_doc),
    }


def api_health() -> dict[str, Any]:
    f = fleet()
    registry = f.load_registry()
    status_doc = load_last_status_doc()
    conn = f.open_cache_readonly()
    try:
        cursors = _sync_cursors(conn, registry)
    finally:
        conn.close()
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "accounting_mode": "approximate",
        "last_status_at": (status_doc or {}).get("controller_utc"),
        "last_status_ok": (status_doc or {}).get("ok"),
        "nodes": _node_health_rows(registry, status_doc, cursors),
        "warnings": _warnings_from_status(status_doc),
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
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "node": {
            "name": node["name"],
            "node_id": node["node_id"],
            "ssh_host": node["ssh_host"],
            "ssh_user": node["ssh_user"],
            "ssh_port": node["ssh_port"],
            "enabled": node["enabled"],
            "status": f.node_lifecycle_status(node),
        },
        "probe": probe,
        "cursor": cursor_doc,
        "instances": instances,
        "recent_usage": usage,
        "stats_window": {"days": 7, "from": start, "to": end},
        "secrets_note": "URI / Reality keys / Clash secret are never shown.",
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
                    "active_credential_id": None,
                }
            )
    return [grouped[k] for k in order]


def api_users() -> dict[str, Any]:
    f = fleet()
    registry = f.load_registry()
    cache = load_users_cache()
    if cache and isinstance(cache.get("users"), list):
        return {
            "schema_version": UI_SCHEMA_VERSION,
            "source": "users-cache",
            "ok": cache.get("ok"),
            "refreshed_at": cache.get("refreshed_at"),
            "users": cache["users"],
            "unreachable": cache.get("unreachable") or [],
            "note": (
                "Cached from last Refresh users (SSH). "
                "No VLESS URI or secrets."
            ),
        }
    conn = f.open_cache_readonly()
    try:
        users = _users_from_db(conn, registry)
    finally:
        conn.close()
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "source": "fleet.db",
        "ok": True,
        "refreshed_at": None,
        "users": users,
        "unreachable": [],
        "note": (
            "Derived from synced audit/daily_usage. "
            "Refresh users over SSH for enabled/credential status. "
            "No VLESS URI or secrets."
        ),
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
        "stats_window": {"days": 7, "from": start, "to": end},
        "secrets_note": (
            "credential_id may appear when users-cache was refreshed; "
            "URI / Reality keys / Clash secret are never shown."
        ),
    }


def resolve_user_id_for_ui(
    conn: Any,
    registry: dict[str, Any],
    tag_or_id: str,
    *,
    allow_ssh: bool,
) -> Optional[str]:
    f = fleet()
    text = (tag_or_id or "").strip()
    if not text:
        return None
    if UUID_RE.fullmatch(text):
        return text
    f.validate_name(text)
    rows = conn.execute(
        """
        SELECT DISTINCT user_id FROM audit_events
        WHERE user_tag = ? AND user_id IS NOT NULL AND user_id != ''
        UNION
        SELECT DISTINCT user_id FROM daily_usage
        WHERE user_tag = ? AND user_id IS NOT NULL AND user_id != ''
        """,
        (text, text),
    ).fetchall()
    ids = {str(r[0]) for r in rows if r[0]}
    if len(ids) == 1:
        return next(iter(ids))
    if len(ids) > 1:
        raise ValueError(f"tag {text} has conflicting user_id in local cache")
    cache = load_users_cache()
    if cache:
        for user in cache.get("users") or []:
            if str(user.get("tag") or "") == text and user.get("user_id"):
                return str(user["user_id"])
    if allow_ssh:
        return f.resolve_fleet_user_id(registry, text)
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


def api_stats_top(kind: str, days: int) -> dict[str, Any]:
    f = fleet()
    if kind not in ("users", "hosts"):
        raise ValueError("kind must be users or hosts")
    if days < 1:
        raise ValueError("days must be >= 1")
    registry = f.load_registry()
    start, end = f.stats_date_window(days)
    group_by = (
        ("user_id", "node_id") if kind == "users" else ("destination_host", "node_id")
    )
    conn = f.open_cache_readonly()
    try:
        raw = f.query_daily_grouped(
            conn, start=start, end=end, group_by=group_by
        )
        rows = [f._stats_row_from_sql(registry, r) for r in raw]
        totals = f._stats_totals(rows)
    finally:
        conn.close()
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "mode": f"top-{kind}",
        "days": days,
        "from": start,
        "to": end,
        "accounting_mode": "approximate",
        "rows": rows,
        "totals": totals,
    }


def api_refresh_status(*, verify: bool) -> dict[str, Any]:
    f = fleet()
    if verify:
        payload = f.run_verify_payload(include_all=False)
        op = "verify"
    else:
        payload = f.run_status_payload(include_all=False)
        op = "status"
    payload = dict(payload)
    payload.pop("_rows", None)
    code = 0 if payload.get("ok") else 1
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "operation": op,
        "exit_code": code,
        "ok": code == 0,
        "result": payload,
    }


def api_sync(*, node: Optional[str] = None) -> dict[str, Any]:
    f = fleet()
    ns = argparse.Namespace(
        node=node,
        all=False,
        reseed=None,
        as_json=True,
    )
    with f.fleet_op_lock():
        code, payload = f.run_sync_payload(ns)
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "operation": "sync",
        "exit_code": code,
        "ok": code == 0,
        "result": payload,
    }


def api_refresh_users() -> dict[str, Any]:
    f = fleet()
    code, payload = f.run_user_list_payload()
    if not isinstance(payload, dict):
        raise RuntimeError("user list did not return JSON")
    users_out: list[dict[str, Any]] = []
    for user in payload.get("users") or []:
        if not isinstance(user, dict):
            continue
        nodes_out = []
        for n in user.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            nodes_out.append(
                {
                    "name": n.get("name"),
                    "tag": n.get("tag"),
                    "enabled": n.get("enabled"),
                    "status": n.get("status"),
                    "active_credential_id": n.get("active_credential_id"),
                }
            )
        users_out.append(
            {
                "tag": user.get("tag"),
                "user_id": user.get("user_id"),
                "display_name": user.get("display_name"),
                "department": user.get("department"),
                "source": "ssh-refresh",
                "nodes": nodes_out,
            }
        )
    cache = {
        "schema_version": UI_SCHEMA_VERSION,
        "ok": bool(payload.get("ok")),
        "state": payload.get("state"),
        "refreshed_at": f.format_utc(datetime.now(timezone.utc)),
        "users": users_out,
        "unreachable": payload.get("unreachable") or [],
    }
    write_users_cache(cache)
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
            if path == "/api/health":
                self._send_json(200, api_health())
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
                self._send_json(200, api_stats_top(kind, days))
                return
            if path == "/api/meta":
                self._send_json(
                    200,
                    {
                        "schema_version": UI_SCHEMA_VERSION,
                        "version": fleet().VCL_FLEET_VERSION,
                        "pages": ["overview", "audit", "health"],
                        "identity_mutations": False,
                        "cache_writes": ["refresh", "sync"],
                        "reseed": "cli-only",
                        "bind": "loopback-only",
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
            if path == "/api/refresh/status":
                self._send_json(200, api_refresh_status(verify=False))
                return
            if path == "/api/refresh/verify":
                self._send_json(200, api_refresh_status(verify=True))
                return
            if path == "/api/refresh/users":
                self._send_json(200, api_refresh_users())
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
    httpd = make_server(
        host, port, max_workers=max_workers, request_timeout=request_timeout
    )
    bind_port = httpd.server_address[1]
    tok = token or secrets.token_urlsafe(32)
    set_ui_runtime(token=tok, listen_port=bind_port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, tok
