#!/usr/bin/env python3
"""vincula-accountd — local traffic accounting for Vincula.

Approximate accounting, not byte-perfect billing.
-------------------------------------------------
Polls the stock sing-box Clash API (/connections). Short-lived
connections may be missed between polls; close times and final byte
counts are inferred from the last observed snapshot. Treat results as
operational visibility, not metering for invoices.

Optional JSONL ingest at /var/lib/vincula/events.jsonl is preferred
when present; polling remains the fallback.

Daily rollups use the UTC calendar date of closed_at (or started_at if
still open during rebuild). Day boundaries are UTC.

Poll baseline: first sight of a connection stores Clash counters as
baseline with zero accounted delta. A counter decrease starts a new
generation (new baseline). Only positive deltas are accumulated.

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
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_DB_PATH = "/var/lib/vincula/accounting.db"
DEFAULT_EVENTS_PATH = "/var/lib/vincula/events.jsonl"
DEFAULT_CLASH_URL = "http://127.0.0.1:9090/connections"
DEFAULT_SETTINGS = "/etc/vincula/config.toml"
DEFAULT_USERS = "/etc/vincula/users.json"
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_RAW_RETENTION_DAYS = 90
DEFAULT_DAILY_RETENTION_DAYS = 90
SCHEMA_VERSION = 2

NODE_ID = "local"
TAG_TO_USER_ID: Dict[str, str] = {}

LOG = logging.getLogger("vincula-accountd")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
  connection_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  user_tag TEXT,
  destination_host TEXT,
  destination_ip TEXT,
  destination_port INTEGER,
  network TEXT,
  upload_bytes INTEGER NOT NULL DEFAULT 0,
  download_bytes INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  closed_at TEXT,
  last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_connections_user_seen
  ON connections(user_id, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_connections_open
  ON connections(closed_at);

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


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Migrate schema 0/1 → 2. Fail closed if user_tag cannot map to user_id."""
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "connections" not in tables and "daily_usage" not in tables:
        conn.executescript(SCHEMA_SQL)
        meta_set(conn, "schema_version", str(SCHEMA_VERSION))
        conn.commit()
        return

    if "meta" not in tables:
        conn.executescript(SCHEMA_SQL)

    raw = meta_get(conn, "schema_version", "")
    try:
        current = int(raw) if raw else 0
    except ValueError:
        current = 0

    if current >= SCHEMA_VERSION:
        # Ensure columns exist even if meta was set early.
        cols = _table_columns(conn, "connections") if "connections" in tables else []
        if cols and "user_id" in cols:
            return

    conn.executescript(SCHEMA_SQL)

    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn_cols = _table_columns(conn, "connections")
    if "user_id" not in conn_cols:
        # Legacy schema: user_tag NOT NULL, no user_id.
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
            "SELECT COUNT(*) FROM connections WHERE user_id IS NULL OR user_id = ''"
        ).fetchone()[0]
        if nulls:
            raise SystemExit("schema migrate fail-closed: unmapped connection rows remain")

    daily_cols = _table_columns(conn, "daily_usage") if "daily_usage" in tables else []
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
                        f"schema migrate fail-closed: {exc} (daily_usage rowid={rowid})"
                    ) from exc
                conn.execute(
                    "UPDATE daily_usage SET user_id = ? WHERE rowid = ?",
                    (uid, rowid),
                )
        nulls = conn.execute(
            "SELECT COUNT(*) FROM daily_usage WHERE user_id IS NULL OR user_id = ''"
        ).fetchone()[0]
        if nulls:
            raise SystemExit("schema migrate fail-closed: unmapped daily_usage rows remain")

    # Ensure user_tag column exists on daily_usage for display.
    daily_cols = _table_columns(conn, "daily_usage")
    if "user_tag" not in daily_cols:
        conn.execute("ALTER TABLE daily_usage ADD COLUMN user_tag TEXT")

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


def parse_jsonl_event(line: str) -> Optional[Dict[str, Any]]:
    """Parse one JSONL accounting event. Returns None if invalid/ignored."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    event = obj.get("event") or obj.get("type") or "connection_update"
    cid = obj.get("connection_id") or obj.get("id")
    user_tag = obj.get("user_tag") or obj.get("user")
    if not user_tag:
        user_tag = user_tag_from_outbound(obj.get("outbound"))
    if not cid or not user_tag:
        return None
    host = normalize_destination_host(obj.get("destination_host"))
    close_names = ("connection_close", "connection_closed", "close")
    user_id = obj.get("user_id")
    if not user_id:
        try:
            user_id = resolve_user_id(str(user_tag))
        except ValueError:
            LOG.warning("skip jsonl event %s: unknown user_tag %s", cid, user_tag)
            return None
    return {
        "event": "connection_close" if event in close_names else event,
        "connection_id": str(cid),
        "node_id": obj.get("node_id") or NODE_ID,
        "user_id": str(user_id),
        "user_tag": str(user_tag),
        "destination_host": host,
        "destination_ip": obj.get("destination_ip") or None,
        "destination_port": obj.get("destination_port"),
        "network": obj.get("network"),
        "upload_bytes": int(obj.get("upload_bytes") or 0),
        "download_bytes": int(obj.get("download_bytes") or 0),
        "started_at": obj.get("started_at") or obj.get("ts") or utc_now_iso(),
        "closed_at": obj.get("closed_at"),
        "ts": obj.get("ts") or utc_now_iso(),
        "absolute": True,
    }


def upsert_connection(
    conn: sqlite3.Connection,
    ev: Dict[str, Any],
    close: bool = False,
    *,
    accounted_upload: Optional[int] = None,
    accounted_download: Optional[int] = None,
) -> None:
    now = ev.get("ts") or utc_now_iso()
    closed_at = ev.get("closed_at") if close or ev.get("event") in (
        "connection_close",
        "connection_closed",
        "close",
    ) else None
    if close and not closed_at:
        closed_at = now

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

    conn.execute(
        """
        INSERT INTO connections(
          connection_id, node_id, user_id, user_tag, destination_host, destination_ip,
          destination_port, network, upload_bytes, download_bytes,
          started_at, closed_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(connection_id) DO UPDATE SET
          user_id = excluded.user_id,
          user_tag = excluded.user_tag,
          destination_host = COALESCE(excluded.destination_host, connections.destination_host),
          destination_ip = COALESCE(excluded.destination_ip, connections.destination_ip),
          destination_port = COALESCE(excluded.destination_port, connections.destination_port),
          network = COALESCE(excluded.network, connections.network),
          upload_bytes = excluded.upload_bytes,
          download_bytes = excluded.download_bytes,
          closed_at = CASE
            WHEN excluded.closed_at IS NOT NULL THEN excluded.closed_at
            ELSE connections.closed_at
          END,
          last_seen_at = excluded.last_seen_at
        """,
        (
            ev["connection_id"],
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


def close_stale_open_connections(conn: sqlite3.Connection, now: Optional[str] = None) -> int:
    """On startup: mark any open rows as closed with last known bytes."""
    now = now or utc_now_iso()
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
    """Track open connections with baseline/delta accounting; close vanished ids.

    known_open[cid] holds:
      ev            — last normalized event
      raw_up/raw_dn — last Clash counters (baseline for next delta)
      acc_up/acc_dn — accumulated positive deltas written to DB
    """
    live_map: Dict[str, Dict[str, Any]] = {ev["connection_id"]: ev for ev in live}
    for cid, ev in live_map.items():
        raw_up = int(ev.get("upload_bytes") or 0)
        raw_dn = int(ev.get("download_bytes") or 0)
        prev = known_open.get(cid)
        if prev is None:
            # First sight: baseline only, zero accounted delta.
            state = {
                "ev": ev,
                "raw_up": raw_up,
                "raw_dn": raw_dn,
                "acc_up": 0,
                "acc_dn": 0,
            }
            upsert_connection(
                conn, ev, close=False, accounted_upload=0, accounted_download=0
            )
            known_open[cid] = state
            continue

        prev_raw_up = int(prev["raw_up"])
        prev_raw_dn = int(prev["raw_dn"])
        acc_up = int(prev["acc_up"])
        acc_dn = int(prev["acc_dn"])

        if raw_up < prev_raw_up or raw_dn < prev_raw_dn:
            # Counter decrease = new generation; reset baseline, no delta.
            prev_raw_up = raw_up
            prev_raw_dn = raw_dn
            delta_up = 0
            delta_dn = 0
        else:
            delta_up = raw_up - prev_raw_up
            delta_dn = raw_dn - prev_raw_dn

        acc_up += max(0, delta_up)
        acc_dn += max(0, delta_dn)
        upsert_connection(
            conn, ev, close=False, accounted_upload=acc_up, accounted_download=acc_dn
        )
        known_open[cid] = {
            "ev": ev,
            "raw_up": raw_up,
            "raw_dn": raw_dn,
            "acc_up": acc_up,
            "acc_dn": acc_dn,
        }

    vanished = [cid for cid in list(known_open) if cid not in live_map]
    for cid in vanished:
        state = known_open.pop(cid)
        last = dict(state["ev"])
        last["event"] = "connection_close"
        last["ts"] = utc_now_iso()
        upsert_connection(
            conn,
            last,
            close=True,
            accounted_upload=int(state["acc_up"]),
            accounted_download=int(state["acc_dn"]),
        )
    return known_open


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


def apply_retention(
    conn: sqlite3.Connection,
    raw_days: int,
    daily_days: int,
) -> None:
    now = datetime.now(timezone.utc)
    if raw_days > 0:
        cutoff = now.timestamp() - raw_days * 86400
        cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        conn.execute(
            "DELETE FROM connections WHERE last_seen_at < ? AND closed_at IS NOT NULL",
            (cutoff_iso,),
        )
    if daily_days > 0:
        cutoff_date = datetime.fromtimestamp(
            now.timestamp() - daily_days * 86400, timezone.utc
        ).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM daily_usage WHERE date < ?", (cutoff_date,))


def read_new_jsonl(path: str, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    events: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.seek(offset)
            while True:
                line = f.readline()
                if not line:
                    break
                ev = parse_jsonl_event(line)
                if ev:
                    events.append(ev)
            offset = f.tell()
    except FileNotFoundError:
        return [], 0
    return events, offset


def apply_jsonl_events(conn: sqlite3.Connection, events: List[Dict[str, Any]]) -> None:
    for ev in events:
        close = ev.get("event") in (
            "connection_close",
            "connection_closed",
            "close",
        )
        # JSONL carries final absolute counters for the finished flow.
        upsert_connection(conn, ev, close=close)


class AccountDaemon:
    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        clash_url: str = DEFAULT_CLASH_URL,
        clash_secret: str = "",
        events_path: str = DEFAULT_EVENTS_PATH,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        raw_retention_days: int = DEFAULT_RAW_RETENTION_DAYS,
        daily_retention_days: int = DEFAULT_DAILY_RETENTION_DAYS,
        users_path: str = DEFAULT_USERS,
    ) -> None:
        self.db_path = db_path
        self.clash_url = clash_url
        self.clash_secret = clash_secret
        self.events_path = events_path
        self.poll_interval = poll_interval
        self.raw_retention_days = raw_retention_days
        self.daily_retention_days = daily_retention_days
        self.users_path = users_path
        self._users_mtime: Optional[float] = None
        self._stop = False
        self._known_open: Dict[str, Dict[str, Any]] = {}
        self._jsonl_offset = 0
        self._prefer_jsonl = False
        self._cycles = 0

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
        closed = close_stale_open_connections(conn)
        if closed:
            LOG.info("marked %s stale open connection(s) closed on startup", closed)
        conn.commit()

        if Path(self.events_path).is_file():
            self._prefer_jsonl = True
            self._jsonl_offset = 0
            LOG.info(
                "JSONL events present at %s; preferring file ingest for closed connections",
                self.events_path,
            )
        else:
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

    def _tick(self, conn: sqlite3.Connection) -> None:
        self._cycles += 1
        self._reload_tag_map_if_changed()
        success = False
        if Path(self.events_path).is_file():
            self._prefer_jsonl = True
            events, self._jsonl_offset = read_new_jsonl(
                self.events_path, self._jsonl_offset
            )
            if events:
                apply_jsonl_events(conn, events)
            success = True
        else:
            self._prefer_jsonl = False
            try:
                live = fetch_clash_connections(self.clash_url, self.clash_secret)
                self._known_open = apply_poll_delta(conn, live, self._known_open)
                success = True
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                LOG.warning("Clash API poll failed: %s", exc)

        if success:
            meta_set(conn, "last_success_at", utc_now_iso())

        if self._cycles == 1 or self._cycles % 720 == 0:
            rollup_daily_usage(conn)
            apply_retention(conn, self.raw_retention_days, self.daily_retention_days)
        conn.commit()


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
        events_path=os.environ.get("VCL_EVENTS_JSONL", DEFAULT_EVENTS_PATH),
        poll_interval=float(os.environ.get("VCL_ACCOUNT_POLL", DEFAULT_POLL_INTERVAL)),
        raw_retention_days=settings_int(
            settings, "accounting_raw_retention_days", DEFAULT_RAW_RETENTION_DAYS
        ),
        daily_retention_days=settings_int(
            settings, "accounting_daily_retention_days", DEFAULT_DAILY_RETENTION_DAYS
        ),
        users_path=users_path,
    )


def ingest_events_file(db_path: str, events_path: str, users_path: str = DEFAULT_USERS) -> int:
    """Ingest an entire events.jsonl into SQLite (test/helper entrypoint)."""
    global TAG_TO_USER_ID
    TAG_TO_USER_ID = load_tag_to_user_id(users_path)
    conn = open_db(db_path)
    events, _ = read_new_jsonl(events_path, 0)
    apply_jsonl_events(conn, events)
    rollup_daily_usage(conn)
    meta_set(conn, "last_success_at", utc_now_iso())
    conn.commit()
    conn.close()
    return len(events)


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
        "--ingest-file",
        default=None,
        metavar="PATH",
        help="ingest a sample events.jsonl into the DB and exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    os.environ.setdefault("VCL_USERS_FILE", args.users)
    if args.ingest_file:
        db_path = args.db or DEFAULT_DB_PATH
        n = ingest_events_file(db_path, args.ingest_file, args.users)
        print(f"ingested {n} event(s) into {db_path}")
        return 0
    daemon = build_daemon_from_settings(args.settings)
    if args.db:
        daemon.db_path = args.db
    if args.once:
        conn = open_db(daemon.db_path)
        close_stale_open_connections(conn)
        if Path(daemon.events_path).is_file():
            events, _ = read_new_jsonl(daemon.events_path, 0)
            apply_jsonl_events(conn, events)
            meta_set(conn, "last_success_at", utc_now_iso())
        else:
            try:
                live = fetch_clash_connections(daemon.clash_url, daemon.clash_secret)
                daemon._known_open = apply_poll_delta(conn, live, {})
                meta_set(conn, "last_success_at", utc_now_iso())
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Clash API poll failed: %s", exc)
        rollup_daily_usage(conn)
        apply_retention(conn, daemon.raw_retention_days, daemon.daily_retention_days)
        conn.commit()
        conn.close()
        return 0
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
