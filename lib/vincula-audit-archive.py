#!/usr/bin/env python3
"""vincula-audit-archive — audit-archive/v1 .vclaudit format (D37/D38/D45).

Offline archive of audit_events + attribution for a time range. Not part of
Workspace; never carries sync_cursor, last_export_seq, credentials, or SSH
state. Restore into fleet-cache is additive with (node_id, event_id) dedupe
and ARCHIVE_CONFLICT rollback; it must not touch sync cursors (AC-4.1-05).

Canonical event equality uses remote event fields only — never imported_at
(P1-4). Stdlib only. Targets Python 3.10+.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

ARCHIVE_NAMESPACE, ARCHIVE_SCHEMA_VERSION = "audit-archive", "1"  # D45 → audit-archive/v1
ARCHIVE_SCHEMA_LABEL = f"{ARCHIVE_NAMESPACE}/v{ARCHIVE_SCHEMA_VERSION}"

ARCHIVE_DDL = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE audit_events(
  node_id TEXT NOT NULL, instance_id TEXT, event_id INTEGER NOT NULL, export_seq INTEGER,
  connection_id TEXT NOT NULL, generation INTEGER NOT NULL, user_id TEXT NOT NULL, user_tag TEXT,
  started_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, closed_at TEXT,
  destination_host TEXT, destination_ip TEXT, destination_port INTEGER, network TEXT,
  upload_bytes INTEGER NOT NULL DEFAULT 0, download_bytes INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(node_id, event_id));
CREATE TABLE node_attribution(node_id TEXT PRIMARY KEY, name TEXT, instance_id TEXT, payload_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE user_attribution(node_id TEXT NOT NULL, user_id TEXT NOT NULL, tag TEXT, payload_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(node_id,user_id));
CREATE TABLE instance_attribution(node_id TEXT NOT NULL, instance_id TEXT NOT NULL, first_seen_at TEXT, last_seen_at TEXT, payload_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(node_id,instance_id));
"""

# FORBIDDEN tables/cols: sync_cursor, last_export_seq (as table), ssh_*, credential*, secret*
# imported_at is cache-local only — never a canonical archive event field (P1-4).

_ARCHIVE_TABLES = (
    "meta",
    "audit_events",
    "node_attribution",
    "user_attribution",
    "instance_attribution",
)

# Canonical remote event fields (excludes cache-local imported_at).
_EVENT_COLS = (
    "node_id",
    "instance_id",
    "event_id",
    "export_seq",
    "connection_id",
    "generation",
    "user_id",
    "user_tag",
    "started_at",
    "last_seen_at",
    "closed_at",
    "destination_host",
    "destination_ip",
    "destination_port",
    "network",
    "upload_bytes",
    "download_bytes",
)

_INSERT_EVENT_SQL = (
    "INSERT INTO audit_events ("
    + ", ".join(_EVENT_COLS)
    + ") VALUES ("
    + ", ".join("?" * len(_EVENT_COLS))
    + ")"
)

# Cache audit_events still requires imported_at (fleet-cache local stamp).
_INSERT_CACHE_EVENT_SQL = (
    "INSERT INTO audit_events ("
    + ", ".join(_EVENT_COLS)
    + ", imported_at) VALUES ("
    + ", ".join("?" * (len(_EVENT_COLS) + 1))
    + ")"
)


class ArchiveConflict(Exception):
    """Same (node_id, event_id) with a different payload; restore must roll back."""


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _event_values(row: Mapping[str, Any] | Any) -> tuple[Any, ...]:
    return tuple(_row_get(row, c) for c in _EVENT_COLS)


def _payload_equal(existing: Any, incoming: Any) -> bool:
    """Canonical equality: remote event fields only (excludes imported_at)."""
    for col in _EVENT_COLS:
        if _row_get(existing, col) != _row_get(incoming, col):
            return False
    return True


def _meta_map(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(k): str(v)
        for k, v in conn.execute("SELECT key, value FROM meta").fetchall()
    }


def _open_archive_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _sync_cursor_snapshot(conn: sqlite3.Connection) -> dict[str, int]:
    try:
        rows = conn.execute(
            "SELECT node_id, last_export_seq FROM sync_cursor"
        ).fetchall()
    except sqlite3.Error:
        return {}
    out: dict[str, int] = {}
    for row in rows:
        nid = row[0] if not isinstance(row, sqlite3.Row) else row["node_id"]
        seq = row[1] if not isinstance(row, sqlite3.Row) else row["last_export_seq"]
        out[str(nid)] = int(seq)
    return out


def _format_imported_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def attribution_from_events(
    events: Sequence[Mapping[str, Any]],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build node/user/instance attribution from event fields + registry names.

    Never includes sync_cursor, SSH, or credential material (D37/D38).
    """
    name_by_nid: dict[str, str] = {}
    if registry is not None:
        for node in registry.get("nodes") or []:
            if not isinstance(node, Mapping):
                continue
            nid = node.get("node_id")
            name = node.get("name")
            if isinstance(nid, str) and isinstance(name, str) and nid:
                name_by_nid[nid] = name

    nodes: dict[str, dict[str, Any]] = {}
    users: dict[tuple[str, str], dict[str, Any]] = {}
    instances: dict[tuple[str, str], dict[str, Any]] = {}

    for ev in events:
        nid = _row_get(ev, "node_id")
        if not isinstance(nid, str) or not nid:
            continue
        iid = _row_get(ev, "instance_id")
        iid_s = iid if isinstance(iid, str) and iid else None
        if nid not in nodes:
            nodes[nid] = {
                "node_id": nid,
                "name": name_by_nid.get(nid),
                "instance_id": iid_s,
                "payload_json": "{}",
            }
        elif iid_s and not nodes[nid].get("instance_id"):
            nodes[nid]["instance_id"] = iid_s

        uid = _row_get(ev, "user_id")
        if isinstance(uid, str) and uid:
            ukey = (nid, uid)
            tag = _row_get(ev, "user_tag")
            if ukey not in users:
                users[ukey] = {
                    "node_id": nid,
                    "user_id": uid,
                    "tag": tag if isinstance(tag, str) else None,
                    "payload_json": "{}",
                }

        if iid_s:
            ikey = (nid, iid_s)
            started = _row_get(ev, "started_at")
            last_seen = _row_get(ev, "last_seen_at")
            if ikey not in instances:
                instances[ikey] = {
                    "node_id": nid,
                    "instance_id": iid_s,
                    "first_seen_at": started if isinstance(started, str) else None,
                    "last_seen_at": last_seen if isinstance(last_seen, str) else None,
                    "payload_json": "{}",
                }
            else:
                cur = instances[ikey]
                if isinstance(started, str) and (
                    cur["first_seen_at"] is None or started < cur["first_seen_at"]
                ):
                    cur["first_seen_at"] = started
                if isinstance(last_seen, str) and (
                    cur["last_seen_at"] is None or last_seen > cur["last_seen_at"]
                ):
                    cur["last_seen_at"] = last_seen

    return list(nodes.values()), list(users.values()), list(instances.values())


def create_archive(
    *,
    fleet_id: str,
    created_at: str,
    time_from: str,
    time_to: str,
    events: list[dict],
    nodes: list[dict],
    users: list[dict],
    instances: list[dict],
    dest: Path,
) -> Path:
    dest = Path(dest)
    if dest.exists():
        raise SystemExit(f"archive exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(dest), timeout=30)
    try:
        conn.executescript(ARCHIVE_DDL)
        for k, v in (
            ("schema_version", ARCHIVE_SCHEMA_LABEL),
            ("fleet_id", fleet_id),
            ("created_at", created_at),
            ("time_from", time_from),
            ("time_to", time_to),
        ):
            conn.execute("INSERT INTO meta(key,value) VALUES(?,?)", (k, v))
        for ev in events:
            conn.execute(_INSERT_EVENT_SQL, _event_values(ev))
        for n in nodes:
            conn.execute(
                "INSERT INTO node_attribution(node_id,name,instance_id,payload_json) "
                "VALUES(?,?,?,?)",
                (
                    n.get("node_id"),
                    n.get("name"),
                    n.get("instance_id"),
                    n.get("payload_json") or "{}",
                ),
            )
        for u in users:
            conn.execute(
                "INSERT INTO user_attribution(node_id,user_id,tag,payload_json) "
                "VALUES(?,?,?,?)",
                (
                    u.get("node_id"),
                    u.get("user_id"),
                    u.get("tag"),
                    u.get("payload_json") or "{}",
                ),
            )
        for inst in instances:
            conn.execute(
                "INSERT INTO instance_attribution("
                "node_id,instance_id,first_seen_at,last_seen_at,payload_json) "
                "VALUES(?,?,?,?,?)",
                (
                    inst.get("node_id"),
                    inst.get("instance_id"),
                    inst.get("first_seen_at"),
                    inst.get("last_seen_at"),
                    inst.get("payload_json") or "{}",
                ),
            )
        conn.commit()
    finally:
        conn.close()
    os.chmod(dest, 0o600)
    return dest


def verify_archive(path: Path) -> dict:
    """Open RO; require meta schema_version==audit-archive/v1; return counts."""
    path = Path(path)
    try:
        conn = _open_archive_ro(path)
    except sqlite3.Error as exc:
        return {"ok": False, "error": f"cannot open archive: {exc}"}
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for required in _ARCHIVE_TABLES:
            if required not in names:
                return {
                    "ok": False,
                    "error": f"missing table: {required}",
                    "schema_version": None,
                }
        meta = _meta_map(conn)
        schema = meta.get("schema_version")
        if schema != ARCHIVE_SCHEMA_LABEL:
            return {
                "ok": False,
                "error": f"unsupported schema_version: {schema}",
                "schema_version": schema,
            }
        tables = [t for t in _ARCHIVE_TABLES if t in names]
        return {
            "ok": True,
            "schema_version": schema,
            "tables": tables,
            "fleet_id": meta.get("fleet_id", ""),
            "created_at": meta.get("created_at", ""),
            "time_from": meta.get("time_from", ""),
            "time_to": meta.get("time_to", ""),
            "event_count": _count(conn, "audit_events"),
            "node_count": _count(conn, "node_attribution"),
            "user_count": _count(conn, "user_attribution"),
            "instance_count": _count(conn, "instance_attribution"),
        }
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        conn.close()


def inspect_archive(path: Path) -> dict:
    """fleet_id, created_at, time range, event/node/user/instance counts."""
    info = verify_archive(path)
    if not info.get("ok"):
        raise SystemExit(info.get("error") or "inspect failed")
    return {
        "fleet_id": info.get("fleet_id", ""),
        "created_at": info.get("created_at", ""),
        "time_from": info.get("time_from", ""),
        "time_to": info.get("time_to", ""),
        "event_count": int(info.get("event_count") or 0),
        "node_count": int(info.get("node_count") or 0),
        "user_count": int(info.get("user_count") or 0),
        "instance_count": int(info.get("instance_count") or 0),
    }


def restore_archive_into_cache(
    archive: Path,
    cache_conn: sqlite3.Connection,
    *,
    rebuild_daily_usage_for_node: Optional[
        Callable[[sqlite3.Connection, str], None]
    ] = None,
) -> dict:
    """Import archive audit_events into cache with (node_id, event_id) dedupe.

    verify schema → verify fleet_id (if known) → BEGIN IMMEDIATE →
    import/dedupe → rebuild daily_usage for touched nodes → assert sync_cursor
    unchanged → COMMIT. Equal canonical payload → dedupe; same key different
    payload → ArchiveConflict("ARCHIVE_CONFLICT") + full rollback. Never reads
    or writes sync_cursor / last_export_seq (AC-4.1-05 / D37/D38).
    """
    archive = Path(archive)
    info = verify_archive(archive)
    if not info.get("ok"):
        raise SystemExit(info.get("error") or "archive verify failed")

    arch_fid = str(info.get("fleet_id") or "")
    cache_fid_row = cache_conn.execute(
        "SELECT value FROM meta WHERE key='fleet_id'"
    ).fetchone()
    cache_fid = (
        str(cache_fid_row[0])
        if cache_fid_row is not None and cache_fid_row[0] is not None
        else ""
    )
    if arch_fid and cache_fid and arch_fid != cache_fid:
        raise SystemExit(
            "ARCHIVE_FLEET_MISMATCH: archive fleet_id mismatch"
        )

    arch = _open_archive_ro(archive)
    inserted = 0
    deduped = 0
    touched: set[str] = set()
    try:
        before_cursor = _sync_cursor_snapshot(cache_conn)
        cache_conn.execute("BEGIN IMMEDIATE")
        try:
            imported_at = _format_imported_at()
            for row in arch.execute("SELECT * FROM audit_events"):
                nid = row["node_id"]
                eid = int(row["event_id"])
                existing = cache_conn.execute(
                    "SELECT * FROM audit_events WHERE node_id=? AND event_id=?",
                    (nid, eid),
                ).fetchone()
                if existing is not None:
                    if _payload_equal(existing, row):
                        deduped += 1
                        continue
                    raise ArchiveConflict("ARCHIVE_CONFLICT")
                cache_conn.execute(
                    _INSERT_CACHE_EVENT_SQL,
                    _event_values(row) + (imported_at,),
                )
                inserted += 1
                if isinstance(nid, str) and nid:
                    touched.add(nid)
            if rebuild_daily_usage_for_node is not None:
                for node_id in sorted(touched):
                    rebuild_daily_usage_for_node(cache_conn, node_id)
            after_cursor = _sync_cursor_snapshot(cache_conn)
            if after_cursor != before_cursor:
                raise SystemExit(
                    "ARCHIVE_CURSOR_TOUCHED: restore must not change sync_cursor"
                )
            cache_conn.commit()
        except BaseException:
            try:
                cache_conn.rollback()
            except sqlite3.Error:
                pass
            raise
    finally:
        arch.close()
    return {
        "inserted": inserted,
        "deduped": deduped,
        "aggregated": len(touched),
    }
