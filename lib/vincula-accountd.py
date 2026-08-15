#!/usr/bin/env python3
"""vincula-accountd — local traffic accounting for Vincula.

Approximate accounting, not byte-perfect billing.
-------------------------------------------------
Polls the stock sing-box Clash API (/connections). Short-lived
connections may be missed between polls; close times and final byte
counts are inferred from the last observed snapshot. Treat results as
operational visibility, not metering for invoices.

Clash API poll is the only production collector.

Daily rollups use the UTC calendar date of closed_at (or started_at if
still open during rebuild). Day boundaries are UTC.

Durable poll_baseline is the source of per-connection counters. The
in-memory known_open map is a cache: read DB → calculate delta → write
SQLite → COMMIT → then refresh the cache (D7). A counter decrease
starts a new generation (baseline only, never a negative delta). Closed
generations are never overwritten (D6/D8).

Stdlib only: sqlite3, json, urllib, datetime, logging, time, signal,
pathlib — no pip packages. Targets Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

DEFAULT_DB_PATH = "/var/lib/vincula/accounting.db"
DEFAULT_CLASH_URL = "http://127.0.0.1:9090/connections"
DEFAULT_SETTINGS = "/etc/vincula/config.toml"
DEFAULT_USERS = "/etc/vincula/users.json"
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_RAW_RETENTION_DAYS = 90
DEFAULT_DAILY_RETENTION_DAYS = 90
RETENTION_DELETE_BATCH = 2000
SCHEMA_VERSION = 3
INT64_MAX = 2**63 - 1
HEARTBEAT_MAX_AGE_SECONDS = 300

NODE_ID = "local"
TAG_TO_USER_ID: Dict[str, str] = {}

LOG = logging.getLogger("vincula-accountd")

# Schema 3 connections body (shared by empty-DB SCHEMA_SQL and 2→3 rewrite).
# INTEGER PRIMARY KEY AUTOINCREMENT is required (D9): deleted event_id values
# are not reused. instance_id is nullable; NULL means untracked (D5).
_CONNECTIONS_V3_COLUMNS = """
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  connection_id TEXT NOT NULL,
  generation INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  instance_id TEXT,
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
  UNIQUE (connection_id, generation)
"""

_CONNECTIONS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_connections_user_seen "
    "ON connections(user_id, last_seen_at)",
    "CREATE INDEX IF NOT EXISTS idx_connections_user_started "
    "ON connections(user_id, started_at)",
    "CREATE INDEX IF NOT EXISTS idx_connections_open "
    "ON connections(closed_at)",
)

_POLL_BASELINE_SQL = """
CREATE TABLE IF NOT EXISTS poll_baseline (
  connection_id TEXT PRIMARY KEY,
  generation INTEGER NOT NULL,
  last_upload_counter INTEGER NOT NULL,
  last_download_counter INTEGER NOT NULL,
  accounted_upload INTEGER NOT NULL,
  accounted_download INTEGER NOT NULL,
  last_seen_at TEXT NOT NULL
)
"""

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
{_CONNECTIONS_V3_COLUMNS}
);

{_CONNECTIONS_INDEX_SQL[0]};
{_CONNECTIONS_INDEX_SQL[1]};
{_CONNECTIONS_INDEX_SQL[2]};

{_POLL_BASELINE_SQL};

CREATE TABLE IF NOT EXISTS daily_usage (
  date TEXT NOT NULL,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  destination_host TEXT NOT NULL,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  connection_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (date, user_id, destination_host)
);

CREATE INDEX IF NOT EXISTS idx_daily_user_date
  ON daily_usage(user_id, date);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize_destination_host(host: Optional[str]) -> Optional[str]:
    """Lowercase and strip trailing dots. No reverse DNS."""
    if host is None:
        return None
    if not isinstance(host, str):
        return None
    value = host.strip().lower().rstrip(".")
    return value or None


def parse_toml_simple(path: str) -> Dict[str, str]:
    """Minimal TOML key = value reader (Vincula config.toml subset)."""
    out: Dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                out[key] = value
    except FileNotFoundError:
        pass
    return out


def settings_int(settings: Dict[str, str], key: str, default: int) -> int:
    raw = settings.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def clash_url_from_settings(settings: Dict[str, str]) -> str:
    port = settings_int(settings, "clash_api_port", 9090)
    return f"http://127.0.0.1:{port}/connections"


def load_tag_to_user_id(users_path: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    try:
        with open(users_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        LOG.warning("users.json not found at %s; tag→user_id mapping empty", users_path)
        return mapping
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot load users.json for accounting: {exc}") from exc
    for user in data.get("users", []):
        tag = user.get("tag")
        user_id = user.get("user_id")
        if tag and user_id:
            mapping[str(tag)] = str(user_id)
    return mapping


def resolve_user_id(user_tag: str) -> str:
    user_id = TAG_TO_USER_ID.get(user_tag)
    if not user_id:
        raise ValueError(f"cannot map user_tag={user_tag!r} to user_id via users.json")
    return user_id


def meta_get(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return row["value"] if isinstance(row, sqlite3.Row) else row[0]


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in rows]


def _table_names(conn: sqlite3.Connection) -> set:
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _ensure_schema_3_objects(conn: sqlite3.Connection) -> None:
    """Create poll_baseline and schema-3 indexes if missing. Do not rebuild tables."""
    conn.execute(_POLL_BASELINE_SQL)
    for stmt in _CONNECTIONS_INDEX_SQL:
        conn.execute(stmt)


def migrate_schema_2_to_3(conn: sqlite3.Connection) -> None:
    """Rewrite connections from schema 2 PK(connection_id) to schema 3.

    Existing rows get generation=0, event_id assigned by AUTOINCREMENT, and
    instance_id NULL (never copied from node_id). poll_baseline is created
    empty: Clash counters cannot be recovered, so the first poll is unknown
    (baseline-only, keep DB bytes). daily_usage is left unchanged.

    Schema 3 is irreversible: there is no automatic 3→2 rollback. Pre-upgrade
    backup is backup_existing_install; never silent-downgrade.
    """
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(f"CREATE TABLE connections_v3 ({_CONNECTIONS_V3_COLUMNS})")
        conn.execute(
            """
            INSERT INTO connections_v3 (
              connection_id, generation, instance_id, user_id, node_id, user_tag,
              started_at, last_seen_at, closed_at,
              destination_host, destination_ip, destination_port, network,
              upload_bytes, download_bytes
            )
            SELECT
              connection_id, 0, NULL, user_id, node_id, user_tag,
              started_at, last_seen_at, closed_at,
              destination_host, destination_ip, destination_port, network,
              upload_bytes, download_bytes
            FROM connections
            ORDER BY rowid
            """
        )
        conn.execute("DROP TABLE connections")
        conn.execute("ALTER TABLE connections_v3 RENAME TO connections")
        _ensure_schema_3_objects(conn)
        meta_set(conn, "schema_version", str(SCHEMA_VERSION))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Migrate schema 0/1 → 2 → 3. Fail closed on unknown or future versions."""
    tables = _table_names(conn)
    if "connections" not in tables and "daily_usage" not in tables:
        conn.executescript(SCHEMA_SQL)
        meta_set(conn, "schema_version", str(SCHEMA_VERSION))
        conn.commit()
        return

    if "meta" not in tables:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    raw = meta_get(conn, "schema_version", "")
    try:
        current = int(raw) if raw else 0
    except ValueError:
        raise SystemExit(
            f"accounting database corrupt or unreadable: schema_version={raw!r}"
        ) from None

    if current > SCHEMA_VERSION:
        raise SystemExit(
            f"accounting database schema_version={current} is newer than "
            f"supported {SCHEMA_VERSION}"
        )

    if current < 2:
        # Legacy 0/1 → 2: add user_id. Fail closed if user_tag cannot map.
        # Do not executescript SCHEMA_SQL against an existing v0/v1 connections
        # table: IF NOT EXISTS would leave the old PK, and new indexes reference
        # user_id before that column exists.
        tables = _table_names(conn)
        if "connections" not in tables:
            conn.executescript(SCHEMA_SQL)
            tables = _table_names(conn)
        conn_cols = _table_columns(conn, "connections")
        if "user_id" not in conn_cols:
            conn.execute("ALTER TABLE connections ADD COLUMN user_id TEXT")
            rows = conn.execute(
                "SELECT connection_id, user_tag FROM connections"
            ).fetchall()
            for row in rows:
                cid = row["connection_id"] if isinstance(row, sqlite3.Row) else row[0]
                tag = row["user_tag"] if isinstance(row, sqlite3.Row) else row[1]
                try:
                    uid = resolve_user_id(str(tag))
                except ValueError as exc:
                    raise SystemExit(
                        f"schema migrate fail-closed: {exc} (connection_id={cid})"
                    ) from exc
                conn.execute(
                    "UPDATE connections SET user_id = ? WHERE connection_id = ?",
                    (uid, cid),
                )
            nulls = conn.execute(
                "SELECT COUNT(*) FROM connections "
                "WHERE user_id IS NULL OR user_id = ''"
            ).fetchone()[0]
            if nulls:
                raise SystemExit(
                    "schema migrate fail-closed: unmapped connection rows remain"
                )

        daily_cols = (
            _table_columns(conn, "daily_usage") if "daily_usage" in tables else []
        )
        if daily_cols and "user_id" not in daily_cols:
            conn.execute("ALTER TABLE daily_usage ADD COLUMN user_id TEXT")
            if "user_tag" in daily_cols:
                rows = conn.execute(
                    "SELECT rowid, user_tag FROM daily_usage"
                ).fetchall()
                for row in rows:
                    rowid = row["rowid"] if isinstance(row, sqlite3.Row) else row[0]
                    tag = row["user_tag"] if isinstance(row, sqlite3.Row) else row[1]
                    try:
                        uid = resolve_user_id(str(tag))
                    except ValueError as exc:
                        raise SystemExit(
                            f"schema migrate fail-closed: {exc} "
                            f"(daily_usage rowid={rowid})"
                        ) from exc
                    conn.execute(
                        "UPDATE daily_usage SET user_id = ? WHERE rowid = ?",
                        (uid, rowid),
                    )
            nulls = conn.execute(
                "SELECT COUNT(*) FROM daily_usage "
                "WHERE user_id IS NULL OR user_id = ''"
            ).fetchone()[0]
            if nulls:
                raise SystemExit(
                    "schema migrate fail-closed: unmapped daily_usage rows remain"
                )

        daily_cols = _table_columns(conn, "daily_usage")
        if daily_cols and "user_tag" not in daily_cols:
            conn.execute("ALTER TABLE daily_usage ADD COLUMN user_tag TEXT")
        meta_set(conn, "schema_version", "2")
        conn.commit()
        current = 2

    conn_cols = _table_columns(conn, "connections")
    if conn_cols and "event_id" not in conn_cols:
        migrate_schema_2_to_3(conn)
        return

    _ensure_schema_3_objects(conn)
    meta_set(conn, "schema_version", str(SCHEMA_VERSION))
    conn.commit()


def open_db(path: str) -> sqlite3.Connection:
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass

    exists = Path(path).is_file() and Path(path).stat().st_size > 0
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        if exists:
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise SystemExit(f"accounting database corrupt: integrity_check={check}")

        migrate_schema(conn)
    except SystemExit:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        raise
    except sqlite3.Error as exc:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        raise SystemExit(f"accounting database corrupt or unreadable: {exc}") from exc

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return conn


def user_tag_from_outbound(tag: Optional[str]) -> Optional[str]:
    if not tag or not isinstance(tag, str):
        return None
    if tag.startswith("acct/"):
        rest = tag[5:]
        return rest or None
    return None


def user_tag_from_chains(chains: Any) -> Optional[str]:
    if not isinstance(chains, list):
        return None
    for item in chains:
        tag = user_tag_from_outbound(item if isinstance(item, str) else None)
        if tag:
            return tag
    return None


def parse_clash_connection(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a Clash API connection object into an internal event dict."""
    if not isinstance(item, dict):
        return None
    cid = item.get("id")
    if not cid:
        return None
    chains = item.get("chains") or item.get("chain") or []
    user_tag = user_tag_from_chains(chains)
    if not user_tag:
        meta = item.get("metadata") or {}
        user_tag = user_tag_from_outbound(meta.get("outboundName"))
    if not user_tag:
        return None

    meta = item.get("metadata") or {}
    host = normalize_destination_host(meta.get("host") or None)
    dest_ip = meta.get("destinationIP") or meta.get("destination_ip") or None
    if dest_ip == "":
        dest_ip = None
    port_raw = meta.get("destinationPort") or meta.get("destination_port")
    try:
        dest_port = int(port_raw) if port_raw not in (None, "") else None
    except (TypeError, ValueError):
        dest_port = None
    network = meta.get("network") or item.get("network") or None
    started = item.get("start") or utc_now_iso()
    if isinstance(started, (int, float)):
        started = datetime.fromtimestamp(started, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    try:
        user_id = resolve_user_id(user_tag)
    except ValueError:
        LOG.warning("skip connection %s: unknown user_tag %s", cid, user_tag)
        return None

    return {
        "event": "connection_update",
        "connection_id": str(cid),
        "node_id": NODE_ID,
        "user_id": user_id,
        "user_tag": user_tag,
        "destination_host": host,
        "destination_ip": dest_ip,
        "destination_port": dest_port,
        "network": network,
        "upload_bytes": int(item.get("upload") or 0),
        "download_bytes": int(item.get("download") or 0),
        "started_at": started,
        "ts": utc_now_iso(),
    }


def _row_get(row: Any, key: str, index: int) -> Any:
    if isinstance(row, sqlite3.Row):
        return row[key]
    return row[index]


def require_nonneg_int(value: Any, name: str) -> int:
    """Reject bool, non-int, negatives, and values above signed int64 (D8)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a non-negative int")
    if value < 0 or value > INT64_MAX:
        raise ValueError(f"{name} out of range")
    return value


def _event_counter(ev: Dict[str, Any], key: str) -> int:
    raw = ev.get(key)
    if raw is None:
        raw = 0
    return require_nonneg_int(raw, key)


def load_poll_baseline(conn: sqlite3.Connection, cid: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT connection_id, generation, last_upload_counter, last_download_counter,
               accounted_upload, accounted_download, last_seen_at
        FROM poll_baseline WHERE connection_id = ?
        """,
        (cid,),
    ).fetchone()
    if row is None:
        return None
    return {
        "connection_id": str(_row_get(row, "connection_id", 0)),
        "generation": int(_row_get(row, "generation", 1)),
        "raw_up": int(_row_get(row, "last_upload_counter", 2)),
        "raw_dn": int(_row_get(row, "last_download_counter", 3)),
        "acc_up": int(_row_get(row, "accounted_upload", 4)),
        "acc_dn": int(_row_get(row, "accounted_download", 5)),
        "last_seen_at": _row_get(row, "last_seen_at", 6),
    }


def upsert_poll_baseline(
    conn: sqlite3.Connection,
    cid: str,
    generation: int,
    raw_up: int,
    raw_dn: int,
    acc_up: int,
    acc_dn: int,
    last_seen_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO poll_baseline(
          connection_id, generation, last_upload_counter, last_download_counter,
          accounted_upload, accounted_download, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(connection_id) DO UPDATE SET
          generation = excluded.generation,
          last_upload_counter = excluded.last_upload_counter,
          last_download_counter = excluded.last_download_counter,
          accounted_upload = excluded.accounted_upload,
          accounted_download = excluded.accounted_download,
          last_seen_at = excluded.last_seen_at
        """,
        (cid, generation, raw_up, raw_dn, acc_up, acc_dn, last_seen_at),
    )


def delete_poll_baseline(conn: sqlite3.Connection, cid: str) -> None:
    conn.execute("DELETE FROM poll_baseline WHERE connection_id = ?", (cid,))


def prune_closed_poll_baselines(conn: sqlite3.Connection) -> None:
    """Drop baseline rows whose (connection_id, generation) is not open."""
    conn.execute(
        """
        DELETE FROM poll_baseline
        WHERE NOT EXISTS (
            SELECT 1 FROM connections c
            WHERE c.connection_id = poll_baseline.connection_id
              AND c.generation = poll_baseline.generation
              AND c.closed_at IS NULL
        )
        """
    )


def _make_cache_entry(
    ev: Dict[str, Any],
    *,
    raw_up: int,
    raw_dn: int,
    acc_up: int,
    acc_dn: int,
    generation: int,
) -> Dict[str, Any]:
    stored = dict(ev)
    stored["generation"] = generation
    return {
        "ev": stored,
        "raw_up": raw_up,
        "raw_dn": raw_dn,
        "acc_up": acc_up,
        "acc_dn": acc_dn,
        "generation": generation,
    }


def reload_known_open_from_db(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    """Rebuild the known_open cache from open poll_baseline generations."""
    rows = conn.execute(
        """
        SELECT
          b.connection_id AS connection_id,
          b.generation AS generation,
          b.last_upload_counter AS raw_up,
          b.last_download_counter AS raw_dn,
          b.accounted_upload AS acc_up,
          b.accounted_download AS acc_dn,
          b.last_seen_at AS last_seen_at,
          c.user_id AS user_id,
          c.node_id AS node_id,
          c.user_tag AS user_tag,
          c.started_at AS started_at,
          c.destination_host AS destination_host,
          c.destination_ip AS destination_ip,
          c.destination_port AS destination_port,
          c.network AS network
        FROM poll_baseline AS b
        INNER JOIN connections AS c
          ON c.connection_id = b.connection_id
         AND c.generation = b.generation
        WHERE c.closed_at IS NULL
        """
    ).fetchall()
    known: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        cid = str(_row_get(row, "connection_id", 0))
        generation = int(_row_get(row, "generation", 1))
        raw_up = int(_row_get(row, "raw_up", 2))
        raw_dn = int(_row_get(row, "raw_dn", 3))
        acc_up = int(_row_get(row, "acc_up", 4))
        acc_dn = int(_row_get(row, "acc_dn", 5))
        ev = {
            "connection_id": cid,
            "generation": generation,
            "node_id": _row_get(row, "node_id", 8),
            "user_id": _row_get(row, "user_id", 7),
            "user_tag": _row_get(row, "user_tag", 9),
            "destination_host": _row_get(row, "destination_host", 11),
            "destination_ip": _row_get(row, "destination_ip", 12),
            "destination_port": _row_get(row, "destination_port", 13),
            "network": _row_get(row, "network", 14),
            "upload_bytes": raw_up,
            "download_bytes": raw_dn,
            "started_at": _row_get(row, "started_at", 10),
            "ts": _row_get(row, "last_seen_at", 6),
        }
        known[cid] = _make_cache_entry(
            ev,
            raw_up=raw_up,
            raw_dn=raw_dn,
            acc_up=acc_up,
            acc_dn=acc_dn,
            generation=generation,
        )
    return known


def _max_generation(conn: sqlite3.Connection, cid: str) -> Optional[int]:
    row = conn.execute(
        "SELECT MAX(generation) FROM connections WHERE connection_id = ?",
        (cid,),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def _open_connection_row(conn: sqlite3.Connection, cid: str) -> Any:
    return conn.execute(
        """
        SELECT event_id, connection_id, generation, user_id, node_id, user_tag,
               started_at, last_seen_at, closed_at, destination_host, destination_ip,
               destination_port, network, upload_bytes, download_bytes
        FROM connections
        WHERE connection_id = ? AND closed_at IS NULL
        ORDER BY generation DESC
        LIMIT 1
        """,
        (cid,),
    ).fetchone()


def _durable_prev_state(conn: sqlite3.Connection, cid: str) -> Optional[Dict[str, Any]]:
    """Read poll_baseline only when its generation is still open (D7)."""
    baseline = load_poll_baseline(conn, cid)
    if baseline is None:
        return None
    row = conn.execute(
        """
        SELECT closed_at, user_id, node_id, user_tag, started_at,
               destination_host, destination_ip, destination_port, network
        FROM connections
        WHERE connection_id = ? AND generation = ?
        """,
        (cid, baseline["generation"]),
    ).fetchone()
    if row is None or _row_get(row, "closed_at", 0) is not None:
        return None
    ev = {
        "connection_id": cid,
        "generation": baseline["generation"],
        "user_id": _row_get(row, "user_id", 1),
        "node_id": _row_get(row, "node_id", 2),
        "user_tag": _row_get(row, "user_tag", 3),
        "started_at": _row_get(row, "started_at", 4),
        "destination_host": _row_get(row, "destination_host", 5),
        "destination_ip": _row_get(row, "destination_ip", 6),
        "destination_port": _row_get(row, "destination_port", 7),
        "network": _row_get(row, "network", 8),
        "upload_bytes": baseline["raw_up"],
        "download_bytes": baseline["raw_dn"],
        "ts": baseline["last_seen_at"],
    }
    return _make_cache_entry(
        ev,
        raw_up=baseline["raw_up"],
        raw_dn=baseline["raw_dn"],
        acc_up=baseline["acc_up"],
        acc_dn=baseline["acc_dn"],
        generation=baseline["generation"],
    )


def upsert_connection(
    conn: sqlite3.Connection,
    ev: Dict[str, Any],
    close: bool = False,
    *,
    accounted_upload: Optional[int] = None,
    accounted_download: Optional[int] = None,
    generation: Optional[int] = None,
) -> bool:
    """Insert or update one (connection_id, generation) row.

    Closed generations are never updated (D6). Returns False when the
    target generation already has closed_at set and this call would have
    been an UPDATE — caller should open a new generation.
    """
    now = ev.get("ts") or utc_now_iso()
    closed_at = ev.get("closed_at") if close or ev.get("event") in (
        "connection_close",
        "connection_closed",
        "close",
    ) else None
    if close and not closed_at:
        closed_at = now
    if not close:
        closed_at = None

    upload = (
        int(accounted_upload)
        if accounted_upload is not None
        else int(ev.get("upload_bytes") or 0)
    )
    download = (
        int(accounted_download)
        if accounted_download is not None
        else int(ev.get("download_bytes") or 0)
    )
    user_id = ev.get("user_id") or resolve_user_id(str(ev["user_tag"]))
    if generation is None:
        generation = int(ev.get("generation", 0))

    conn.execute(
        """
        INSERT INTO connections(
          connection_id, generation, instance_id, node_id, user_id, user_tag,
          destination_host, destination_ip, destination_port, network,
          upload_bytes, download_bytes, started_at, closed_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(connection_id, generation) DO UPDATE SET
          user_id = excluded.user_id,
          user_tag = excluded.user_tag,
          destination_host = COALESCE(excluded.destination_host, connections.destination_host),
          destination_ip = COALESCE(excluded.destination_ip, connections.destination_ip),
          destination_port = COALESCE(excluded.destination_port, connections.destination_port),
          network = COALESCE(excluded.network, connections.network),
          upload_bytes = excluded.upload_bytes,
          download_bytes = excluded.download_bytes,
          closed_at = excluded.closed_at,
          last_seen_at = excluded.last_seen_at
        WHERE connections.closed_at IS NULL
        """,
        (
            ev["connection_id"],
            generation,
            None,  # instance_id untracked (D5); never copy node_id
            ev.get("node_id") or NODE_ID,
            user_id,
            ev.get("user_tag"),
            ev.get("destination_host"),
            ev.get("destination_ip"),
            ev.get("destination_port"),
            ev.get("network"),
            upload,
            download,
            ev.get("started_at") or now,
            closed_at,
            now,
        ),
    )
    changed = conn.execute("SELECT changes()").fetchone()[0]
    return int(changed) > 0


def close_stale_open_connections(
    conn: sqlite3.Connection,
    live_ids: Optional[Iterable[str]] = None,
    now: Optional[str] = None,
) -> int:
    """Close open rows that are not in the live Clash set.

    If live_ids is None, keep the legacy behaviour of closing every open row
    (used by tests and callers that have no snapshot). An empty live set means
    the Clash snapshot is empty, so every open row is stale.
    """
    now = now or utc_now_iso()
    ids = None if live_ids is None else [str(cid) for cid in live_ids]
    if ids:
        placeholders = ",".join("?" * len(ids))
        cur = conn.execute(
            "UPDATE connections SET closed_at = ?, last_seen_at = ? "
            f"WHERE closed_at IS NULL AND connection_id NOT IN ({placeholders})",
            (now, now, *ids),
        )
    else:
        cur = conn.execute(
            "UPDATE connections SET closed_at = ?, last_seen_at = ? WHERE closed_at IS NULL",
            (now, now),
        )
    return cur.rowcount


def fetch_clash_connections(
    url: str,
    secret: str = "",
    timeout: float = 5.0,
) -> List[Dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    if isinstance(data, dict):
        items = data.get("connections") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    events: List[Dict[str, Any]] = []
    for item in items:
        ev = parse_clash_connection(item)
        if ev:
            events.append(ev)
    return events


def apply_poll_delta(
    conn: sqlite3.Connection,
    live: Iterable[Dict[str, Any]],
    known_open: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Write generation-aware deltas to SQLite; return the next cache snapshot.

    Does not mutate known_open and does not commit. Caller must COMMIT then
    assign the returned dict (D7). Counters come from durable poll_baseline,
    not from the in-memory cache.
    """
    live_map: Dict[str, Dict[str, Any]] = {ev["connection_id"]: ev for ev in live}
    new_known: Dict[str, Dict[str, Any]] = {}

    for cid, ev in live_map.items():
        try:
            raw_up = _event_counter(ev, "upload_bytes")
            raw_dn = _event_counter(ev, "download_bytes")
        except ValueError as exc:
            LOG.warning("skip connection %s: invalid counters (%s)", cid, exc)
            kept = _durable_prev_state(conn, cid) or known_open.get(cid)
            if kept is not None:
                new_known[cid] = kept
            continue

        now = ev.get("ts") or utc_now_iso()
        prev = _durable_prev_state(conn, cid)

        if prev is None:
            open_row = _open_connection_row(conn, cid)
            if open_row is not None:
                # Migrated / restart without baseline: keep DB bytes (1a).
                generation = int(_row_get(open_row, "generation", 2))
                acc_up = int(_row_get(open_row, "upload_bytes", 13))
                acc_dn = int(_row_get(open_row, "download_bytes", 14))
                new_known[cid] = _write_open_state(
                    conn,
                    ev,
                    cid,
                    generation=generation,
                    raw_up=raw_up,
                    raw_dn=raw_dn,
                    acc_up=acc_up,
                    acc_dn=acc_dn,
                    now=now,
                )
                continue
            max_gen = _max_generation(conn, cid)
            generation = 0 if max_gen is None else max_gen + 1
            # Unknown active (no open row): baseline only, accounted 0.
            new_known[cid] = _write_open_state(
                conn,
                ev,
                cid,
                generation=generation,
                raw_up=raw_up,
                raw_dn=raw_dn,
                acc_up=0,
                acc_dn=0,
                now=now,
            )
            continue

        generation = int(prev["generation"])
        prev_raw_up = int(prev["raw_up"])
        prev_raw_dn = int(prev["raw_dn"])
        acc_up = int(prev["acc_up"])
        acc_dn = int(prev["acc_dn"])

        if raw_up < prev_raw_up or raw_dn < prev_raw_dn:
            # D8: current < previous → close this generation, open the next.
            _close_generation(conn, prev, now)
            generation = generation + 1
            new_known[cid] = _write_open_state(
                conn,
                ev,
                cid,
                generation=generation,
                raw_up=raw_up,
                raw_dn=raw_dn,
                acc_up=0,
                acc_dn=0,
                now=now,
            )
            continue

        acc_up += raw_up - prev_raw_up
        acc_dn += raw_dn - prev_raw_dn
        new_known[cid] = _write_open_state(
            conn,
            ev,
            cid,
            generation=generation,
            raw_up=raw_up,
            raw_dn=raw_dn,
            acc_up=acc_up,
            acc_dn=acc_dn,
            now=now,
        )

    tracked = set(known_open)
    for row in conn.execute("SELECT connection_id FROM poll_baseline"):
        tracked.add(str(_row_get(row, "connection_id", 0)))
    now_close = utc_now_iso()
    for cid in tracked:
        if cid in live_map:
            continue
        state = _durable_prev_state(conn, cid) or known_open.get(cid)
        if state is None:
            delete_poll_baseline(conn, cid)
            continue
        _close_generation(conn, state, now_close)

    prune_closed_poll_baselines(conn)
    return new_known


def _write_open_state(
    conn: sqlite3.Connection,
    ev: Dict[str, Any],
    cid: str,
    *,
    generation: int,
    raw_up: int,
    raw_dn: int,
    acc_up: int,
    acc_dn: int,
    now: str,
) -> Dict[str, Any]:
    ev_w = dict(ev)
    ev_w["generation"] = generation
    ev_w["ts"] = now
    landed = upsert_connection(
        conn,
        ev_w,
        close=False,
        accounted_upload=acc_up,
        accounted_download=acc_dn,
        generation=generation,
    )
    if not landed:
        # Target generation is already closed: never overwrite (D6 sentinel).
        max_gen = _max_generation(conn, cid)
        generation = (0 if max_gen is None else max_gen) + 1
        ev_w["generation"] = generation
        acc_up = 0
        acc_dn = 0
        upsert_connection(
            conn,
            ev_w,
            close=False,
            accounted_upload=0,
            accounted_download=0,
            generation=generation,
        )
    upsert_poll_baseline(
        conn, cid, generation, raw_up, raw_dn, acc_up, acc_dn, now
    )
    return _make_cache_entry(
        ev_w,
        raw_up=raw_up,
        raw_dn=raw_dn,
        acc_up=acc_up,
        acc_dn=acc_dn,
        generation=generation,
    )


def _close_generation(
    conn: sqlite3.Connection,
    state: Dict[str, Any],
    now: str,
) -> None:
    last = dict(state["ev"])
    cid = str(last["connection_id"])
    generation = int(state["generation"])
    last["event"] = "connection_close"
    last["ts"] = now
    last["generation"] = generation
    upsert_connection(
        conn,
        last,
        close=True,
        accounted_upload=int(state["acc_up"]),
        accounted_download=int(state["acc_dn"]),
        generation=generation,
    )
    delete_poll_baseline(conn, cid)


def commit_accounting(
    conn: sqlite3.Connection,
    new_known: Dict[str, Dict[str, Any]],
    setter: Callable[[Dict[str, Dict[str, Any]]], None],
) -> None:
    """COMMIT durable writes, then refresh the in-memory cache (D7).

    On commit failure: ROLLBACK and reload known_open from poll_baseline.
    Never treat memory as committed before COMMIT succeeds.
    """
    try:
        conn.commit()
    except sqlite3.Error:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        setter(reload_known_open_from_db(conn))
        raise
    setter(new_known)


_DAILY_USAGE_AGGREGATE_SELECT = """
        SELECT
          substr(COALESCE(closed_at, started_at), 1, 10) AS date,
          user_id,
          user_tag,
          CASE
            WHEN destination_host IS NOT NULL AND destination_host != '' THEN destination_host
            WHEN destination_ip IS NOT NULL AND destination_ip != '' THEN destination_ip
            ELSE '(unknown)'
          END AS destination_host,
          SUM(upload_bytes),
          SUM(download_bytes),
          COUNT(*)
        FROM connections
        GROUP BY 1, 2, 3, 4
"""


def rollup_daily_usage(conn: sqlite3.Connection) -> None:
    """Rebuild daily_usage from connections (idempotent aggregate).

    Builds into a temp table first, then swaps inside a savepoint so a
    failed rebuild never leaves daily_usage empty. Uses UTC date of
    closed_at when present, else started_at.
    """
    conn.execute("SAVEPOINT rollup_daily_usage")
    try:
        conn.execute("DROP TABLE IF EXISTS temp.daily_usage_rebuild")
        conn.execute(
            """
            CREATE TEMP TABLE daily_usage_rebuild (
              date TEXT NOT NULL,
              user_id TEXT NOT NULL,
              user_tag TEXT,
              destination_host TEXT NOT NULL,
              upload_bytes INTEGER NOT NULL DEFAULT 0,
              download_bytes INTEGER NOT NULL DEFAULT 0,
              connection_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO daily_usage_rebuild(
              date, user_id, user_tag, destination_host,
              upload_bytes, download_bytes, connection_count
            )
            """
            + _DAILY_USAGE_AGGREGATE_SELECT
        )
        conn.execute("DELETE FROM daily_usage")
        conn.execute(
            """
            INSERT INTO daily_usage(
              date, user_id, user_tag, destination_host,
              upload_bytes, download_bytes, connection_count
            )
            SELECT
              date, user_id, user_tag, destination_host,
              upload_bytes, download_bytes, connection_count
            FROM daily_usage_rebuild
            """
        )
        conn.execute("DROP TABLE daily_usage_rebuild")
        conn.execute("RELEASE rollup_daily_usage")
    except Exception:
        conn.execute("ROLLBACK TO rollup_daily_usage")
        conn.execute("RELEASE rollup_daily_usage")
        raise


def _delete_expired_connections_batch(
    conn: sqlite3.Connection,
    cutoff_iso: str,
    limit: int = RETENTION_DELETE_BATCH,
) -> int:
    """Delete at most `limit` expired closed connection rows.

    SQLite has no portable DELETE ... LIMIT; select event_id then IN-delete.
    Open rows (closed_at IS NULL) are never selected.
    """
    rows = conn.execute(
        "SELECT event_id FROM connections "
        "WHERE last_seen_at < ? AND closed_at IS NOT NULL "
        "ORDER BY event_id LIMIT ?",
        (cutoff_iso, limit),
    ).fetchall()
    if not rows:
        return 0
    ids = [r[0] for r in rows]
    q = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM connections WHERE event_id IN ({q})", ids)
    return len(ids)


def _delete_expired_daily_usage_batch(
    conn: sqlite3.Connection,
    cutoff_date: str,
    limit: int = RETENTION_DELETE_BATCH,
) -> int:
    """Delete at most `limit` expired daily_usage rows by primary key."""
    rows = conn.execute(
        "SELECT date, user_id, destination_host FROM daily_usage "
        "WHERE date < ? "
        "ORDER BY date, user_id, destination_host LIMIT ?",
        (cutoff_date, limit),
    ).fetchall()
    if not rows:
        return 0
    keys = [(r[0], r[1], r[2]) for r in rows]
    conn.executemany(
        "DELETE FROM daily_usage WHERE date = ? AND user_id = ? AND destination_host = ?",
        keys,
    )
    return len(keys)


def apply_retention(
    conn: sqlite3.Connection,
    raw_days: int,
    daily_days: int,
) -> None:
    """Delete expired rows in bounded batches (one transaction per table).

    At most RETENTION_DELETE_BATCH rows per table per call. A leftover
    backlog drains on later maintenance cycles — this function does not
    loop until the over-window set is empty. Independent of any fleet
    cursor (none in 0.2.7).
    """
    now = datetime.now(timezone.utc)
    if raw_days > 0:
        cutoff = now.timestamp() - raw_days * 86400
        cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        _delete_expired_connections_batch(conn, cutoff_iso)
        conn.commit()
    if daily_days > 0:
        cutoff_date = datetime.fromtimestamp(
            now.timestamp() - daily_days * 86400, timezone.utc
        ).strftime("%Y-%m-%d")
        _delete_expired_daily_usage_batch(conn, cutoff_date)
        conn.commit()
    meta_set(conn, "last_retention_at", utc_now_iso())
    conn.commit()


def _parse_iso_utc(value: str) -> Optional[datetime]:
    ts = (value or "").strip()
    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _open_readonly_accounting_db(db_path: str) -> sqlite3.Connection:
    """Open accounting.db read-only. Does not migrate or write."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _plane_detail(text: str) -> str:
    return str(text).replace("\t", " ").replace("\n", " ").strip()


def accounting_plane_checks(
    db_path: str,
    *,
    service_active: bool,
    raw_days: int,
    daily_days: int,
) -> List[Tuple[str, bool, str]]:
    """D3 Accounting Plane checks. Pure function; no Clash API, no writes.

    Returns an ordered list of (name, ok, detail). Called by both
    `vcl verify` and `vcl accounting check`.
    """
    results: List[Tuple[str, bool, str]] = []
    results.append(
        (
            "accountd service",
            bool(service_active),
            "active" if service_active else "inactive",
        )
    )

    conn: Optional[sqlite3.Connection] = None
    skipped = "skipped: database unreadable"

    def fail_rest(reason: str) -> List[Tuple[str, bool, str]]:
        for name in (
            "schema expected",
            "heartbeat",
            "baseline sanity",
            "counter sanity",
            "retention state",
        ):
            results.append((name, False, _plane_detail(reason)))
        return results

    if not db_path or not os.path.isfile(db_path) or not os.access(db_path, os.R_OK):
        results.append(
            ("database readable", False, _plane_detail(f"unreadable: {db_path or '(none)'}"))
        )
        return fail_rest(skipped)

    try:
        conn = _open_readonly_accounting_db(db_path)
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            results.append(
                ("database readable", False, _plane_detail(f"integrity_check={check}"))
            )
            try:
                conn.close()
            except sqlite3.Error:
                pass
            return fail_rest(skipped)
        results.append(("database readable", True, "ok"))
    except sqlite3.Error as exc:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        results.append(("database readable", False, _plane_detail(str(exc))))
        return fail_rest(skipped)

    tables = _table_names(conn)

    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        schema = str(row[0]) if row and row[0] is not None else ""
    except sqlite3.Error as exc:
        schema = ""
        results.append(("schema expected", False, _plane_detail(f"unreadable: {exc}")))
    else:
        expected = str(SCHEMA_VERSION)
        results.append(
            (
                "schema expected",
                schema == expected,
                f"schema_version={schema or '(none)'} (expected {expected})",
            )
        )

    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='last_success_at'"
        ).fetchone()
        last_success = str(row[0]) if row and row[0] else ""
    except sqlite3.Error:
        last_success = ""
    if not last_success:
        results.append(("heartbeat", False, "last_success_at missing"))
    else:
        when = _parse_iso_utc(last_success)
        if when is None:
            results.append(
                ("heartbeat", False, _plane_detail(f"last_success_at unreadable: {last_success}"))
            )
        else:
            age = (datetime.now(timezone.utc) - when).total_seconds()
            if age > HEARTBEAT_MAX_AGE_SECONDS:
                results.append(
                    (
                        "heartbeat",
                        False,
                        f"last_success_at stale (age {int(age)}s > {HEARTBEAT_MAX_AGE_SECONDS}s)",
                    )
                )
            else:
                results.append(
                    ("heartbeat", True, f"last_success_at fresh (age {int(max(age, 0))}s)")
                )

    baseline_ok = True
    baseline_bits: List[str] = []
    if "connections" not in tables or "poll_baseline" not in tables:
        baseline_ok = False
        baseline_bits.append("connections or poll_baseline missing")
    else:
        try:
            missing_open = conn.execute(
                """
                SELECT COUNT(*) FROM connections c
                WHERE c.closed_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM poll_baseline b
                    WHERE b.connection_id = c.connection_id
                      AND b.generation = c.generation
                  )
                """
            ).fetchone()[0]
            stale_baseline = conn.execute(
                """
                SELECT COUNT(*) FROM poll_baseline b
                LEFT JOIN connections c
                  ON c.connection_id = b.connection_id
                 AND c.generation = b.generation
                WHERE c.event_id IS NULL OR c.closed_at IS NOT NULL
                """
            ).fetchone()[0]
            drifted = conn.execute(
                """
                SELECT COUNT(*) FROM connections c
                JOIN poll_baseline b
                  ON b.connection_id = c.connection_id
                 AND b.generation = c.generation
                WHERE c.closed_at IS NULL
                  AND (c.upload_bytes != b.accounted_upload
                       OR c.download_bytes != b.accounted_download)
                """
            ).fetchone()[0]
        except sqlite3.Error as exc:
            baseline_ok = False
            baseline_bits.append(f"query failed: {exc}")
        else:
            if missing_open:
                baseline_ok = False
                baseline_bits.append(f"{missing_open} open row(s) missing matching poll_baseline")
            if stale_baseline:
                baseline_ok = False
                baseline_bits.append(
                    f"{stale_baseline} poll_baseline row(s) point at missing or closed generation"
                )
            if drifted:
                baseline_ok = False
                baseline_bits.append(
                    f"{drifted} open row(s) drifted from poll_baseline accounted bytes"
                )
            if baseline_ok:
                baseline_bits.append("open generations match poll_baseline")
    results.append(
        (
            "baseline sanity",
            baseline_ok,
            _plane_detail("; ".join(baseline_bits) or "ok"),
        )
    )

    counter_ok = True
    counter_bits: List[str] = []
    if "connections" not in tables:
        counter_ok = False
        counter_bits.append("connections missing")
    else:
        try:
            neg_conn = conn.execute(
                """
                SELECT COUNT(*) FROM connections
                WHERE upload_bytes < 0 OR download_bytes < 0
                """
            ).fetchone()[0]
        except sqlite3.Error as exc:
            counter_ok = False
            counter_bits.append(f"connections query failed: {exc}")
            neg_conn = 0
        else:
            if neg_conn:
                counter_ok = False
                counter_bits.append(f"{neg_conn} connection row(s) with negative bytes")
    if "poll_baseline" in tables:
        try:
            neg_base = conn.execute(
                """
                SELECT COUNT(*) FROM poll_baseline
                WHERE last_upload_counter < 0 OR last_download_counter < 0
                   OR accounted_upload < 0 OR accounted_download < 0
                """
            ).fetchone()[0]
        except sqlite3.Error as exc:
            counter_ok = False
            counter_bits.append(f"poll_baseline query failed: {exc}")
        else:
            if neg_base:
                counter_ok = False
                counter_bits.append(f"{neg_base} poll_baseline row(s) with negative counters")
    if counter_ok:
        counter_bits.append("no negative counters")
    results.append(
        ("counter sanity", counter_ok, _plane_detail("; ".join(counter_bits)))
    )

    retention_ok = True
    retention_bits: List[str] = []
    last_retention = ""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='last_retention_at'"
        ).fetchone()
        last_retention = str(row[0]) if row and row[0] else ""
    except sqlite3.Error:
        last_retention = ""
    if last_retention:
        when_ret = _parse_iso_utc(last_retention)
        if when_ret is None:
            retention_bits.append(f"last_retention_at unreadable: {last_retention}")
        else:
            ret_age = int((datetime.now(timezone.utc) - when_ret).total_seconds())
            retention_bits.append(f"last_retention_at age {max(ret_age, 0)}s")
    else:
        retention_bits.append("last_retention_at missing")

    expired_conn = 0
    if "connections" in tables and raw_days > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - raw_days * 86400
        cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        try:
            expired_conn = conn.execute(
                """
                SELECT COUNT(*) FROM connections
                WHERE last_seen_at < ? AND closed_at IS NOT NULL
                """,
                (cutoff_iso,),
            ).fetchone()[0]
        except sqlite3.Error as exc:
            retention_ok = False
            retention_bits.append(f"connections query failed: {exc}")
        else:
            retention_bits.append(f"{expired_conn} expired closed connection(s)")
            if expired_conn > RETENTION_DELETE_BATCH:
                retention_ok = False
                retention_bits.append(
                    f"retention backlog exceeds batch {RETENTION_DELETE_BATCH}"
                )
    else:
        retention_bits.append("0 expired closed connection(s)")

    expired_daily = 0
    if "daily_usage" in tables and daily_days > 0:
        cutoff_date = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - daily_days * 86400,
            timezone.utc,
        ).strftime("%Y-%m-%d")
        try:
            expired_daily = conn.execute(
                "SELECT COUNT(*) FROM daily_usage WHERE date < ?",
                (cutoff_date,),
            ).fetchone()[0]
        except sqlite3.Error as exc:
            retention_ok = False
            retention_bits.append(f"daily_usage query failed: {exc}")
        else:
            if expired_daily > RETENTION_DELETE_BATCH:
                retention_ok = False
                retention_bits.append(
                    f"{expired_daily} expired daily_usage row(s) exceed batch {RETENTION_DELETE_BATCH}"
                )
    results.append(
        ("retention state", retention_ok, _plane_detail("; ".join(retention_bits)))
    )

    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
    return results


def format_accounting_plane_report(
    results: List[Tuple[str, bool, str]],
) -> Tuple[str, bool]:
    """Render tab-separated `OK|FAIL name detail` lines. Returns (text, all_ok)."""
    lines: List[str] = []
    all_ok = True
    for name, ok, detail in results:
        status = "OK" if ok else "FAIL"
        lines.append(f"{status}\t{name}\t{_plane_detail(detail)}")
        if not ok:
            all_ok = False
    return "\n".join(lines) + ("\n" if lines else ""), all_ok


class AccountDaemon:
    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        clash_url: str = DEFAULT_CLASH_URL,
        clash_secret: str = "",
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        raw_retention_days: int = DEFAULT_RAW_RETENTION_DAYS,
        daily_retention_days: int = DEFAULT_DAILY_RETENTION_DAYS,
        users_path: str = DEFAULT_USERS,
    ) -> None:
        self.db_path = db_path
        self.clash_url = clash_url
        self.clash_secret = clash_secret
        self.poll_interval = poll_interval
        self.raw_retention_days = raw_retention_days
        self.daily_retention_days = daily_retention_days
        self.users_path = users_path
        self._users_mtime: Optional[float] = None
        self._stop = False
        self._known_open: Dict[str, Dict[str, Any]] = {}
        self._last_live_ids: Optional[List[str]] = None
        self._cycles = 0

    def _set_known_open(self, known: Dict[str, Dict[str, Any]]) -> None:
        self._known_open = known

    def _reload_tag_map_if_changed(self) -> None:
        """Replace TAG_TO_USER_ID when users.json mtime changes.

        Full replacement keeps disabled users resolvable (Clash may still
        have residual connections). Bad JSON keeps the previous map.
        """
        global TAG_TO_USER_ID
        try:
            mtime = os.stat(self.users_path).st_mtime
        except OSError:
            return
        if self._users_mtime is not None and mtime == self._users_mtime:
            return
        try:
            new_map = load_tag_to_user_id(self.users_path)
        except SystemExit as exc:
            LOG.warning(
                "users.json changed but failed to reload; keeping previous tag map (%s)",
                exc,
            )
            self._users_mtime = mtime
            return
        TAG_TO_USER_ID = new_map
        self._users_mtime = mtime

    def request_stop(self, *_args: Any) -> None:
        self._stop = True

    def run(self) -> int:
        conn = open_db(self.db_path)
        self._known_open = reload_known_open_from_db(conn)
        LOG.info("polling Clash API at %s (approximate accounting)", self.clash_url)

        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)

        while not self._stop:
            try:
                self._tick(conn)
            except Exception:  # noqa: BLE001 — keep daemon alive for transient errors
                LOG.exception("accounting tick failed")
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            deadline = time.monotonic() + self.poll_interval
            while not self._stop and time.monotonic() < deadline:
                time.sleep(0.2)
        conn.close()
        return 0

    def _poll_clash(
        self, conn: sqlite3.Connection
    ) -> Tuple[bool, Optional[Dict[str, Dict[str, Any]]]]:
        try:
            live = fetch_clash_connections(self.clash_url, self.clash_secret)
            live_ids = [ev["connection_id"] for ev in live]
            self._last_live_ids = live_ids
            new_known = apply_poll_delta(conn, live, self._known_open)
            closed = close_stale_open_connections(conn, live_ids)
            prune_closed_poll_baselines(conn)
            if closed:
                LOG.info(
                    "marked %s stale open connection(s) closed (absent from Clash snapshot)",
                    closed,
                )
            return True, new_known
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            LOG.warning("Clash API poll failed: %s", exc)
            return False, None

    def _collect(
        self, conn: sqlite3.Connection
    ) -> Tuple[bool, Optional[Dict[str, Dict[str, Any]]]]:
        """Clash API poll is the only production collector."""
        return self._poll_clash(conn)

    def _tick(self, conn: sqlite3.Connection) -> None:
        self._cycles += 1
        self._reload_tag_map_if_changed()
        success, new_known = self._collect(conn)
        if success:
            meta_set(conn, "last_success_at", utc_now_iso())
            # COMMIT collect first, then refresh cache. Never assign cache before COMMIT.
            commit_accounting(conn, new_known or {}, self._set_known_open)

        if self._cycles == 1 or self._cycles % 720 == 0:
            rollup_daily_usage(conn)
            conn.commit()
            # Retention is its own transaction (and commits internally per
            # table). A long DELETE must not hold the ingest commit.
            apply_retention(conn, self.raw_retention_days, self.daily_retention_days)


def build_daemon_from_settings(settings_path: str = DEFAULT_SETTINGS) -> AccountDaemon:
    global NODE_ID, TAG_TO_USER_ID
    settings = parse_toml_simple(settings_path)
    NODE_ID = settings.get("node_id") or NODE_ID
    users_path = os.environ.get("VCL_USERS_FILE", DEFAULT_USERS)
    TAG_TO_USER_ID = load_tag_to_user_id(users_path)
    clash_url = clash_url_from_settings(settings)
    secret = (
        os.environ.get("VCL_CLASH_API_SECRET")
        or settings.get("clash_api_secret")
        or ""
    )
    return AccountDaemon(
        db_path=os.environ.get("VCL_ACCOUNTING_DB", DEFAULT_DB_PATH),
        clash_url=os.environ.get("VCL_CLASH_URL", clash_url),
        clash_secret=secret,
        poll_interval=float(os.environ.get("VCL_ACCOUNT_POLL", DEFAULT_POLL_INTERVAL)),
        raw_retention_days=settings_int(
            settings, "accounting_raw_retention_days", DEFAULT_RAW_RETENTION_DAYS
        ),
        daily_retention_days=settings_int(
            settings, "accounting_daily_retention_days", DEFAULT_DAILY_RETENTION_DAYS
        ),
        users_path=users_path,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Vincula local accounting daemon. "
            "Polling Clash API is approximate and is not exact billing."
        )
    )
    parser.add_argument(
        "--settings",
        default=DEFAULT_SETTINGS,
        help="path to config.toml",
    )
    parser.add_argument(
        "--users",
        default=DEFAULT_USERS,
        help="path to users.json (tag→user_id map)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run a single poll/rollup cycle and exit",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="override accounting SQLite path",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
    )
    parser.add_argument(
        "--check-accounting-plane",
        action="store_true",
        help="run D3 Accounting Plane checks and exit (no daemon)",
    )
    parser.add_argument(
        "--service-active",
        action="store_true",
        help="with --check-accounting-plane: treat accountd as active",
    )
    parser.add_argument(
        "--raw-days",
        type=int,
        default=DEFAULT_RAW_RETENTION_DAYS,
        help="with --check-accounting-plane: raw retention days for backlog cutoff",
    )
    parser.add_argument(
        "--daily-days",
        type=int,
        default=DEFAULT_DAILY_RETENTION_DAYS,
        help="with --check-accounting-plane: daily retention days for backlog cutoff",
    )
    args = parser.parse_args(argv)
    if args.check_accounting_plane:
        db_path = args.db or DEFAULT_DB_PATH
        report, all_ok = format_accounting_plane_report(
            accounting_plane_checks(
                db_path,
                service_active=args.service_active,
                raw_days=args.raw_days,
                daily_days=args.daily_days,
            )
        )
        sys.stdout.write(report)
        return 0 if all_ok else 1
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    os.environ.setdefault("VCL_USERS_FILE", args.users)
    daemon = build_daemon_from_settings(args.settings)
    if args.db:
        daemon.db_path = args.db
    if args.once:
        conn = open_db(daemon.db_path)
        daemon._known_open = reload_known_open_from_db(conn)
        daemon._tick(conn)
        if daemon._last_live_ids is not None:
            closed = close_stale_open_connections(conn, daemon._last_live_ids)
            if closed:
                LOG.info(
                    "marked %s stale open connection(s) closed (absent from Clash snapshot)",
                    closed,
                )
            prune_closed_poll_baselines(conn)
            conn.commit()
        conn.close()
        return 0
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
