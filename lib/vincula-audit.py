#!/usr/bin/env python3
"""vincula-audit — connection-level RFC3339 interval queries and cursor export.

Approximate accounting visibility (Clash polling). Not billing-grade.
Window is interval-overlap (D11), not UTC day granularity (that is stats).

  started_at < query_to
  AND COALESCE(closed_at, last_seen_at) >= query_from

JSONL export (`--after SEQ --jsonl`) streams *closed* connections ordered by
`export_seq` (Export Protocol v2). Open rows are never durable-exported.
Retention that deleted unconsumed export_seq returns CURSOR_EXPIRED (exit 3).
A cursor past meta audit_export_seq returns CURSOR_AHEAD (exit 3).
`--after 0` always succeeds for the remaining window.

Reads accounting schema 4 (export_seq). Opens accounting.db read-only.
Stdlib only. Targets Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

EXPORT_PROTOCOL_VERSION = 2
CURSOR_KIND_EXPORT_SEQ = "export_seq"

ROW_KEYS = (
    "event_id",
    "export_seq",
    "connection_id",
    "generation",
    "user_id",
    "user_tag",
    "node_id",
    "instance_id",
    "destination_host",
    "destination_ip",
    "destination_port",
    "network",
    "upload_bytes",
    "download_bytes",
    "started_at",
    "last_seen_at",
    "closed_at",
)

def parse_rfc3339(s: str) -> str:
    """Parse an RFC3339 timestamp with timezone; return UTC `...Z`.

    Accepts `2026-08-10T09:00:00Z` and offsets such as `+00:00` / `+08:00`.
    Naive, date-only, and other invalid input → SystemExit with stderr.
    """
    if not isinstance(s, str) or not s.strip():
        print("ERROR: invalid RFC3339 timestamp", file=sys.stderr)
        raise SystemExit(1)
    raw = s.strip()
    if "T" not in raw and "t" not in raw:
        print(f"ERROR: invalid RFC3339 timestamp: {s}", file=sys.stderr)
        raise SystemExit(1)
    candidate = raw.replace("Z", "+00:00").replace("z", "+00:00")
    try:
        when = datetime.fromisoformat(candidate)
    except ValueError:
        print(f"ERROR: invalid RFC3339 timestamp: {s}", file=sys.stderr)
        raise SystemExit(1)
    if when.tzinfo is None:
        print(f"ERROR: RFC3339 timestamp must include a timezone: {s}", file=sys.stderr)
        raise SystemExit(1)
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def interval_overlap_sql() -> str:
    """SQL predicate: connection interval intersects [query_from, query_to).

    Bind order: query_to, query_from.
    started_at == query_to is excluded (<).
    COALESCE(closed_at, last_seen_at) == query_from is included (>=).
    """
    return "started_at < ? AND COALESCE(closed_at, last_seen_at) >= ?"


def normalize_destination_host(host: Optional[str]) -> Optional[str]:
    if host is None or not isinstance(host, str):
        return None
    value = host.strip().lower().rstrip(".")
    return value or None


def load_tag_to_user_id(users_path: str) -> Dict[str, str]:
    """Same mapping rule as accountd: tag → user_id from users.json."""
    mapping: Dict[str, str] = {}
    try:
        with open(users_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return mapping
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load users.json: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    for user in data.get("users", []) or []:
        if not isinstance(user, dict):
            continue
        tag = user.get("tag")
        user_id = user.get("user_id")
        if tag and user_id:
            mapping[str(tag)] = str(user_id)
    return mapping


def open_db_readonly(path: str) -> sqlite3.Connection:
    """Read-only SQLite connection. Does not migrate or write poll_baseline."""
    abs_path = str(Path(path).resolve())
    if not Path(abs_path).is_file():
        print(f"ERROR: accounting database not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    uri = "file:" + quote(abs_path, safe="/") + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        print(f"ERROR: cannot open accounting DB: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _meta_int(conn: sqlite3.Connection, key: str, default: int = 0) -> int:
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
    except sqlite3.Error:
        return default
    if row is None:
        return default
    raw = row["value"] if isinstance(row, sqlite3.Row) else row[0]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _require_schema_4(conn: sqlite3.Connection) -> None:
    """Fail closed unless connections are schema 4 (export_seq)."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.Error as exc:
        print(
            f"ERROR: accounting database is not readable as schema 4: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    ver = None
    if row is not None:
        ver = row["value"] if isinstance(row, sqlite3.Row) else row[0]
    if ver != "4":
        print(
            f"ERROR: accounting database schema_version={ver!r} is not 4 "
            "(Export Protocol v2 requires schema 4)",
            file=sys.stderr,
        )
        raise SystemExit(1)


def query_audit(
    conn: sqlite3.Connection,
    *,
    query_from: str,
    query_to: str,
    user_id: Optional[str] = None,
    user_tag: Optional[str] = None,
    dest_host: Optional[str] = None,
    dest_ip: Optional[str] = None,
    node_id: Optional[str] = None,
    users_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return overlapping connection rows, oldest first.

    user_tag is resolved to user_id via users.json when users_path is set
    (same tag map as accountd). Unknown tag → SystemExit.
    """
    q_from = parse_rfc3339(query_from)
    q_to = parse_rfc3339(query_to)
    if q_from > q_to:
        print("ERROR: --from must not be after --to", file=sys.stderr)
        raise SystemExit(1)

    _require_schema_4(conn)

    uid = _optional(user_id)
    tag = _optional(user_tag)
    if tag:
        if not users_path:
            print("ERROR: --users is required to resolve --user", file=sys.stderr)
            raise SystemExit(1)
        mapping = load_tag_to_user_id(users_path)
        resolved = mapping.get(tag)
        if not resolved:
            print(f"ERROR: unknown user tag '{tag}'", file=sys.stderr)
            raise SystemExit(1)
        if uid and uid != resolved:
            print("ERROR: --user and --user-id refer to different users", file=sys.stderr)
            raise SystemExit(1)
        uid = resolved

    host = normalize_destination_host(_optional(dest_host))
    ip = _optional(dest_ip)
    node = _optional(node_id)

    where = [interval_overlap_sql()]
    params: List[Any] = [q_to, q_from]
    if uid:
        where.append("user_id = ?")
        params.append(uid)
    if host:
        where.append("destination_host = ?")
        params.append(host)
    if ip:
        where.append("destination_ip = ?")
        params.append(ip)
    if node:
        where.append("node_id = ?")
        params.append(node)

    cols = ", ".join(ROW_KEYS)
    sql = (
        f"SELECT {cols} FROM connections WHERE "
        + " AND ".join(where)
        + " ORDER BY started_at ASC, event_id ASC"
    )
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        print(f"ERROR: audit query failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    return [_row_dict(row) for row in rows]


def _row_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in ROW_KEYS}


def _export_meta(
    *,
    ok: bool,
    after: int,
    max_export_seq: int,
    pruned_max_export_seq: int,
    count: int,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "ok": ok,
        "protocol_version": EXPORT_PROTOCOL_VERSION,
        "cursor_kind": CURSOR_KIND_EXPORT_SEQ,
    }
    if error:
        meta["error"] = error
    meta["after"] = after
    meta["max_export_seq"] = max_export_seq
    meta["pruned_max_export_seq"] = pruned_max_export_seq
    meta["count"] = count
    meta["node_id"] = None
    meta["instance_id"] = None
    return meta


def export_after(
    conn: sqlite3.Connection,
    after: int,
    limit: Optional[int] = None,
) -> tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Export closed connections with export_seq > after (Protocol v2).

    Returns (status, rows, meta). status is "ok", "CURSOR_EXPIRED",
    or "CURSOR_AHEAD".
    CURSOR_EXPIRED when after > 0 and after < pruned_max_export_seq
    (Fleet missed deleted durable rows).
    CURSOR_AHEAD when after > 0 and after > audit_export_seq
    (cursor from a newer/other DB). next_cursor does not advance.
    after=0 always succeeds. Open rows never appear.
    Does not write the database.
    """
    if isinstance(after, bool) or not isinstance(after, int) or after < 0:
        print("ERROR: --after must be an integer >= 0", file=sys.stderr)
        raise SystemExit(1)
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        print("ERROR: --limit must be an integer >= 1", file=sys.stderr)
        raise SystemExit(1)

    _require_schema_4(conn)
    max_export_seq = _meta_int(conn, "audit_export_seq", 0)
    pruned_max = _meta_int(conn, "audit_pruned_max_export_seq", 0)

    expired = after > 0 and after < pruned_max
    if expired:
        meta = _export_meta(
            ok=False,
            after=after,
            max_export_seq=max_export_seq,
            pruned_max_export_seq=pruned_max,
            count=0,
            error="CURSOR_EXPIRED",
        )
        meta["next_cursor"] = after
        return ("CURSOR_EXPIRED", [], meta)

    ahead = after > 0 and after > max_export_seq
    if ahead:
        meta = _export_meta(
            ok=False,
            after=after,
            max_export_seq=max_export_seq,
            pruned_max_export_seq=pruned_max,
            count=0,
            error="CURSOR_AHEAD",
        )
        meta["next_cursor"] = after
        return ("CURSOR_AHEAD", [], meta)

    cols = ", ".join(ROW_KEYS)
    sql = (
        f"SELECT {cols} FROM connections "
        "WHERE export_seq > ? AND closed_at IS NOT NULL "
        "AND export_seq IS NOT NULL "
        "ORDER BY export_seq ASC"
    )
    params: List[Any] = [after]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        print(f"ERROR: audit export failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    out = [_row_dict(row) for row in rows]
    meta = _export_meta(
        ok=True,
        after=after,
        max_export_seq=max_export_seq,
        pruned_max_export_seq=pruned_max,
        count=len(out),
    )
    meta["next_cursor"] = out[-1]["export_seq"] if out else after
    return ("ok", out, meta)


def build_query_meta(
    *,
    query_from: str,
    query_to: str,
    user_id: Optional[str] = None,
    user_tag: Optional[str] = None,
    dest_host: Optional[str] = None,
    dest_ip: Optional[str] = None,
    node_id: Optional[str] = None,
) -> Dict[str, str]:
    return {
        "from": query_from,
        "to": query_to,
        "user": _optional(user_tag) or "",
        "user_id": _optional(user_id) or "",
        "host": _optional(dest_host) or "",
        "ip": _optional(dest_ip) or "",
        "node": _optional(node_id) or "",
    }


def render_json(rows: Sequence[Dict[str, Any]], query: Dict[str, str]) -> None:
    print(json.dumps({"rows": list(rows), "query": query}, indent=2))


def _cell(value: Any, width: int) -> str:
    if value is None:
        text = "-"
    else:
        text = str(value)
    if len(text) > width:
        text = text[: max(1, width - 1)] + "."
    return f"{text:<{width}}"


def render_table(rows: Sequence[Dict[str, Any]], query: Dict[str, str]) -> None:
    print("Vincula Audit")
    print()
    print(f"Window: {query['from']} → {query['to']} (interval-overlap, UTC)")
    extras = []
    if query.get("user"):
        extras.append(f"user={query['user']}")
    if query.get("user_id"):
        extras.append(f"user_id={query['user_id']}")
    if query.get("host"):
        extras.append(f"host={query['host']}")
    if query.get("ip"):
        extras.append(f"ip={query['ip']}")
    if query.get("node"):
        extras.append(f"node={query['node']}")
    if extras:
        print("Filters: " + " ".join(extras))
    print()
    print(
        f"{'EVENT':<8} {'SEQ':<8} {'CID':<16} {'GEN':<4} {'USER':<12} {'TAG':<10} "
        f"{'HOST':<20} {'UP':>10} {'DOWN':>10} {'STARTED':<20} {'CLOSED':<20}"
    )
    for r in rows:
        print(
            f"{_cell(r.get('event_id'), 8)} "
            f"{_cell(r.get('export_seq'), 8)} "
            f"{_cell(r.get('connection_id'), 16)} "
            f"{_cell(r.get('generation'), 4)} "
            f"{_cell(r.get('user_id'), 12)} "
            f"{_cell(r.get('user_tag'), 10)} "
            f"{_cell(r.get('destination_host'), 20)} "
            f"{_cell(r.get('upload_bytes'), 10)} "
            f"{_cell(r.get('download_bytes'), 10)} "
            f"{_cell(r.get('started_at'), 20)} "
            f"{_cell(r.get('closed_at'), 20)}"
        )
    if not rows:
        print("(no connections in window)")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Vincula connection audit "
            "(RFC3339 interval-overlap / export_seq cursor export)"
        )
    )
    p.add_argument("--db", required=True, help="path to accounting.db")
    p.add_argument("--users", required=True, help="path to users.json")
    p.add_argument("--from", dest="from_ts", default="", metavar="RFC3339")
    p.add_argument("--to", dest="to_ts", default="", metavar="RFC3339")
    p.add_argument("--user", default="", help="user tag (resolved via users.json)")
    p.add_argument("--user-id", dest="user_id", default="")
    p.add_argument("--host", default="", help="destination host filter")
    p.add_argument("--ip", default="", help="destination IP filter")
    p.add_argument("--node", default="", help="node_id filter")
    p.add_argument("--format", choices=("table", "json"), default="table")
    p.add_argument("--json", dest="json_flag", action="store_true", help="same as --format json")
    p.add_argument(
        "--after",
        dest="after",
        default=None,
        metavar="EXPORT_SEQ",
        help="exclusive export_seq cursor for JSONL export (0 = from beginning)",
    )
    p.add_argument(
        "--jsonl",
        dest="jsonl",
        action="store_true",
        help="export closed connections as JSONL (requires --after)",
    )
    p.add_argument(
        "--limit",
        dest="limit",
        default=None,
        metavar="N",
        help="max JSONL rows to return (pagination)",
    )
    p.add_argument(
        "--node-id",
        dest="meta_node_id",
        default="",
        help="node_id overlay for export stderr meta",
    )
    p.add_argument(
        "--instance-id",
        dest="meta_instance_id",
        default="",
        help="instance_id overlay for export stderr meta",
    )
    p.add_argument(
        "--stamp-identity",
        dest="stamp_identity",
        action="store_true",
        help="fill missing JSONL node_id/instance_id from overlay (reseed only)",
    )
    return p.parse_args(argv)


def _apply_export_identity(meta: Dict[str, Any], args: argparse.Namespace) -> None:
    node_id = _optional(args.meta_node_id)
    instance_id = _optional(args.meta_instance_id)
    if node_id is not None:
        meta["node_id"] = node_id
    if instance_id is not None:
        meta["instance_id"] = instance_id


def stamp_export_rows(
    rows: List[Dict[str, Any]],
    *,
    node_id: Optional[str],
    instance_id: Optional[str],
) -> None:
    """Fill missing row identity from overlay. Mismatch fails closed.

    Does not write the accounting database. Used by --stamp-identity (reseed).
    """
    if not node_id:
        print("ERROR: --stamp-identity requires --node-id", file=sys.stderr)
        raise SystemExit(1)
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            print(f"ERROR: JSONL row {i} is not an object", file=sys.stderr)
            raise SystemExit(1)
        raw_nid = row.get("node_id")
        row_nid = _optional(None if raw_nid is None else str(raw_nid))
        if row_nid is None:
            row["node_id"] = node_id
        elif row_nid != node_id:
            print(
                f"ERROR: JSONL row {i} node_id={row_nid} != {node_id}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        if instance_id:
            raw_iid = row.get("instance_id")
            row_iid = _optional(None if raw_iid is None else str(raw_iid))
            if row_iid is None:
                row["instance_id"] = instance_id
            elif row_iid != instance_id:
                print(
                    f"ERROR: JSONL row {i} instance_id={row_iid} != {instance_id}",
                    file=sys.stderr,
                )
                raise SystemExit(1)


def _emit_export_meta(meta: Dict[str, Any]) -> None:
    print(json.dumps(meta, separators=(",", ":")), file=sys.stderr)


def main_export(args: argparse.Namespace) -> int:
    if not args.jsonl or args.after is None:
        print("ERROR: --after and --jsonl must be used together", file=sys.stderr)
        return 1
    interval_flags = (
        args.from_ts,
        args.to_ts,
        args.user,
        args.user_id,
        args.host,
        args.ip,
        args.node,
    )
    if any(interval_flags) or args.json_flag:
        print(
            "ERROR: --jsonl export is mutually exclusive with interval query flags",
            file=sys.stderr,
        )
        return 1
    try:
        after = int(args.after)
    except (TypeError, ValueError):
        print("ERROR: --after must be an integer >= 0", file=sys.stderr)
        return 1
    limit: Optional[int] = None
    if args.limit is not None and str(args.limit).strip() != "":
        try:
            limit = int(args.limit)
        except (TypeError, ValueError):
            print("ERROR: --limit must be an integer >= 1", file=sys.stderr)
            return 1

    conn = open_db_readonly(args.db)
    try:
        status, rows, meta = export_after(conn, after, limit=limit)
    finally:
        conn.close()

    _apply_export_identity(meta, args)
    if bool(getattr(args, "stamp_identity", False)):
        stamp_export_rows(
            rows,
            node_id=_optional(args.meta_node_id),
            instance_id=_optional(args.meta_instance_id),
        )
    _emit_export_meta(meta)
    if status in ("CURSOR_EXPIRED", "CURSOR_AHEAD"):
        return 3
    for row in rows:
        print(json.dumps(row, separators=(",", ":")))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.jsonl or args.after is not None:
        return main_export(args)
    if not args.from_ts or not args.to_ts:
        print("ERROR: --from and --to are required for interval audit", file=sys.stderr)
        return 1
    q_from = parse_rfc3339(args.from_ts)
    q_to = parse_rfc3339(args.to_ts)
    conn = open_db_readonly(args.db)
    try:
        rows = query_audit(
            conn,
            query_from=q_from,
            query_to=q_to,
            user_id=args.user_id or None,
            user_tag=args.user or None,
            dest_host=args.host or None,
            dest_ip=args.ip or None,
            node_id=args.node or None,
            users_path=args.users,
        )
    finally:
        conn.close()

    query = build_query_meta(
        query_from=q_from,
        query_to=q_to,
        user_id=args.user_id or None,
        user_tag=args.user or None,
        dest_host=args.host or None,
        dest_ip=args.ip or None,
        node_id=args.node or None,
    )
    fmt = "json" if args.json_flag else args.format
    if fmt == "json":
        render_json(rows, query)
    else:
        render_table(rows, query)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
