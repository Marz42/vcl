#!/usr/bin/env python3
"""Read-only telemetry/v1 snapshot for ``vcl telemetry snapshot --json``."""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA = "telemetry/v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_uptime_seconds() -> int:
    try:
        with open("/proc/uptime", encoding="ascii") as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError, IndexError):
        return 0


def _read_load() -> dict[str, float]:
    try:
        parts = Path("/proc/loadavg").read_text(encoding="ascii").split()
        return {
            "load1": float(parts[0]),
            "load5": float(parts[1]),
            "load15": float(parts[2]),
        }
    except (OSError, ValueError, IndexError):
        return {"load1": 0.0, "load5": 0.0, "load15": 0.0}


def _read_memory() -> dict[str, int]:
    total = 0
    used = 0
    try:
        info: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, _, val = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                info[key] = int(val.strip().split()[0]) * 1024
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", 0)
        used = max(total - avail, 0) if total else 0
    except (OSError, ValueError):
        pass
    return {"total_bytes": total, "used_bytes": used}


def _read_filesystem(mount: str = "/") -> dict[str, Any]:
    try:
        out = subprocess.run(
            ["df", "-B1", "--output=target,size,used", mount],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        lines = [ln for ln in out.stdout.strip().splitlines() if ln.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 3:
                return {
                    "mount": mount,
                    "total_bytes": int(parts[1]),
                    "used_bytes": int(parts[2]),
                }
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return {"mount": mount, "total_bytes": 0, "used_bytes": 0}


def _read_network_totals() -> dict[str, int]:
    """Sum rx/tx bytes across non-loopback interfaces (/proc/net/dev)."""
    rx = 0
    tx = 0
    try:
        lines = Path("/proc/net/dev").read_text(encoding="ascii").splitlines()[2:]
        for line in lines:
            if ":" not in line:
                continue
            iface, rest = line.split(":", 1)
            iface = iface.strip()
            if not iface or iface == "lo":
                continue
            cols = rest.split()
            if len(cols) >= 9:
                rx += int(cols[0])
                tx += int(cols[8])
    except (OSError, ValueError, IndexError):
        pass
    return {"rx_bytes": rx, "tx_bytes": tx}


def _systemd_active(unit: str) -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            timeout=5,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _systemd_restart_info(unit: str) -> tuple[Optional[int], Optional[str]]:
    try:
        proc = subprocess.run(
            [
                "systemctl",
                "show",
                unit,
                "-p",
                "NRestarts",
                "-p",
                "ActiveEnterTimestamp",
                "--value",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        restarts: Optional[int] = int(lines[0]) if lines else None
        ts: Optional[str] = None
        if len(lines) >= 2 and lines[1] not in ("", "n/a"):
            try:
                when = datetime.strptime(lines[1], "%a %Y-%m-%d %H:%M:%S %Z")
                when = when.replace(tzinfo=timezone.utc)
                ts = when.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                ts = None
        return restarts, ts
    except (subprocess.SubprocessError, OSError, ValueError):
        return None, None


def _clash_connection_count(port: int, secret: str) -> Optional[int]:
    url = f"http://127.0.0.1:{port}/connections"
    req = urllib.request.Request(url)
    if secret:
        req.add_header("Authorization", f"Bearer {secret}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read(65536)
        data = json.loads(body)
        if isinstance(data, dict) and isinstance(data.get("connections"), list):
            return len(data["connections"])
    except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError):
        pass
    return None


def _read_toml(path: Path, key: str) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key} = "):
                val = line.split("=", 1)[1].strip()
                if val.startswith('"') and val.endswith('"'):
                    return val[1:-1]
                return val
    except OSError:
        pass
    return ""


def _json_field(path: Path, field: str) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ""
        val = data.get(field)
        if val is None and isinstance(data.get("node"), dict):
            val = data["node"].get(field)
        return str(val) if val is not None else ""
    except (OSError, json.JSONDecodeError, TypeError):
        return ""


def _parse_iso_age_seconds(raw: str, now: datetime) -> Optional[int]:
    ts = raw.strip()
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
    return int((now - when).total_seconds())


def _accounting_metrics(db_path: Path) -> dict[str, Any]:
    active = _systemd_active("vincula-accountd.service")
    last_poll_age: Optional[int] = None
    export_seq: Optional[int] = None
    last_event_age: Optional[int] = None
    if not db_path.is_file():
        return {
            "active": active,
            "last_poll_age_seconds": None,
            "export_seq": None,
            "last_event_age_seconds": None,
        }
    try:
        # Read-only: URI mode=ro + query_only (AC / Spec soak safety).
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.execute("PRAGMA query_only=ON")
        except sqlite3.Error:
            pass
        now = datetime.now(timezone.utc)
        row = conn.execute(
            "SELECT value FROM meta WHERE key='last_success_at'"
        ).fetchone()
        if row and row[0]:
            last_poll_age = _parse_iso_age_seconds(str(row[0]), now)
        row = conn.execute(
            "SELECT value FROM meta WHERE key='audit_export_seq'"
        ).fetchone()
        if row and row[0] is not None and str(row[0]).strip() != "":
            export_seq = int(row[0])
        row = conn.execute(
            "SELECT MAX(last_seen_at) FROM connections WHERE last_seen_at IS NOT NULL"
        ).fetchone()
        if row and row[0]:
            last_event_age = _parse_iso_age_seconds(str(row[0]), now)
        conn.close()
    except (sqlite3.Error, ValueError, OSError):
        pass
    return {
        "active": active,
        "last_poll_age_seconds": last_poll_age,
        "export_seq": export_seq,
        "last_event_age_seconds": last_event_age,
    }


def build_snapshot(
    *,
    state_dir: Path,
    accounting_db: Path,
) -> dict[str, Any]:
    settings = state_dir / "config.toml"
    state_file = state_dir / "state.json"
    node_id = _read_toml(settings, "node_id")
    instance_id = _json_field(state_file, "instance_id")
    clash_port = int(_read_toml(settings, "clash_api_port") or "9090")
    clash_secret = _read_toml(settings, "clash_api_secret")
    sing_active = _systemd_active("sing-box.service")
    restarts, last_restart = _systemd_restart_info("sing-box.service")
    conn_count = (
        _clash_connection_count(clash_port, clash_secret) if sing_active else None
    )
    return {
        "schema": SCHEMA,
        "node_id": node_id,
        "instance_id": instance_id,
        "observed_at": _utc_now(),
        "uptime_seconds": _read_uptime_seconds(),
        "load": _read_load(),
        "memory": _read_memory(),
        "filesystem": _read_filesystem("/"),
        "network": _read_network_totals(),
        "sing_box": {
            "active": sing_active,
            "connection_count": conn_count,
            "restart_count": restarts,
            "last_restart_at": last_restart,
        },
        "accountd": _accounting_metrics(accounting_db),
    }


def build_audit_snapshot(*, state_dir: Path, accounting_db: Path, budget_seconds: float = .25) -> dict[str, Any]:
    """Bounded, read-only audit diagnostics. SQLite errors never become free text."""
    now = datetime.now(timezone.utc)
    out = {"schema": "audit-health/v1", "node_id": _read_toml(state_dir / "config.toml", "node_id"),
           "instance_id": _json_field(state_dir / "state.json", "instance_id"), "observed_at": _utc_now(),
           "accountd_active": _systemd_active("vincula-accountd.service"), "db_state": "UNKNOWN",
           "db_schema": None, "heartbeat_age_seconds": None, "last_poll_age_seconds": None,
           "last_event_age_seconds": None, "export_seq": None, "min_retained_export_seq": None,
           "pruned_max_export_seq": None}
    conn = None
    deadline = time.monotonic() + max(.001, min(1, budget_seconds))
    try:
        accounting_db.stat()
        conn = sqlite3.connect(accounting_db.resolve().as_uri() + "?mode=ro", uri=True, timeout=.1)
        conn.execute("PRAGMA query_only=ON")
        steps = 0
        def bounded():
            nonlocal steps
            steps += 1
            return steps > 2000 or time.monotonic() >= deadline
        conn.set_progress_handler(bounded, 1000)
        meta = dict(conn.execute("SELECT key,value FROM meta WHERE key IN "
            "('schema_version','heartbeat_at','last_success_at','audit_export_seq','audit_pruned_max_export_seq') LIMIT 5"))
        def integer(value):
            if not isinstance(value, str) or len(value) > 19 or not value.isascii() or not value.isdigit():
                return None
            value = int(value)
            return value if 0 <= value <= 2**63 - 1 else None
        out["db_schema"] = integer(meta.get("schema_version"))
        if out["db_schema"] != 4:
            out["db_state"] = "SCHEMA_MISMATCH"
            return out
        required = {
            "connections": {"event_id", "connection_id", "generation", "user_id", "node_id", "instance_id", "user_tag",
                            "started_at", "last_seen_at", "closed_at", "destination_host", "destination_ip", "destination_port",
                            "network", "upload_bytes", "download_bytes", "export_seq"},
            "poll_baseline": {"connection_id", "generation", "last_upload_counter", "last_download_counter",
                              "accounted_upload", "accounted_download", "last_seen_at"},
            "daily_usage": {"date", "user_id", "user_tag", "destination_host", "upload_bytes", "download_bytes", "connection_count"},
        }
        for table, columns in required.items():
            found = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not columns <= found:
                out["db_state"] = "SCHEMA_MISMATCH"
                return out
        checked = conn.execute("PRAGMA quick_check(1)").fetchone()
        if checked is None or checked[0] != "ok":
            out["db_state"] = "CORRUPT"
            return out
        for field, key in (("heartbeat_age_seconds", "heartbeat_at"), ("last_poll_age_seconds", "last_success_at")):
            raw = meta.get(key)
            if isinstance(raw, str) and len(raw) <= 40:
                age = _parse_iso_age_seconds(raw, now)
                out[field] = age if age is not None and age >= 0 else None
        out["export_seq"] = integer(meta.get("audit_export_seq"))
        out["pruned_max_export_seq"] = integer(meta.get("audit_pruned_max_export_seq"))
        minimum, last_event = conn.execute("SELECT MIN(export_seq),MAX(last_seen_at) FROM connections").fetchone()
        out["min_retained_export_seq"] = minimum if type(minimum) is int and 0 <= minimum <= 2**63 - 1 else None
        if isinstance(last_event, str) and len(last_event) <= 40:
            age = _parse_iso_age_seconds(last_event, now)
            out["last_event_age_seconds"] = age if age is not None and age >= 0 else None
        out["db_state"] = "OK"
    except FileNotFoundError:
        out["db_state"] = "MISSING"
    except (PermissionError, OSError):
        out["db_state"] = "UNREADABLE"
    except sqlite3.Error as exc:
        code = getattr(exc, "sqlite_errorcode", 0) & 0xff
        out["db_state"] = ("CORRUPT" if code in (getattr(sqlite3, "SQLITE_CORRUPT", 11), getattr(sqlite3, "SQLITE_NOTADB", 26)) else
                           "SCHEMA_MISMATCH" if code == getattr(sqlite3, "SQLITE_ERROR", 1) else "UNKNOWN")
    except (ValueError, TypeError, OverflowError):
        out["db_state"] = "UNKNOWN"
    finally:
        if conn is not None:
            conn.close()
    return out


def build_user_snapshot(*, state_dir: Path, accounting_db: Path, budget_seconds: float = .25) -> dict[str, Any]:
    """A transactionally consistent retained-byte sample, including open connections."""
    now = datetime.now(timezone.utc)
    out = {"schema": "user-traffic/v1", "node_id": _read_toml(state_dir / "config.toml", "node_id"),
           "instance_id": _json_field(state_dir / "state.json", "instance_id"), "observed_at": _utc_now(),
           "sampled_at": None, "heartbeat_age_seconds": None, "pruned_max_export_seq": None,
           "state": "UNKNOWN", "truncated": False, "users": []}
    conn = None
    deadline = time.monotonic() + max(.001, min(1, budget_seconds))
    try:
        accounting_db.stat()
        conn = sqlite3.connect(accounting_db.resolve().as_uri() + "?mode=ro", uri=True, timeout=.1)
        conn.execute("PRAGMA query_only=ON")
        steps = 0
        def bounded():
            nonlocal steps
            steps += 1
            return steps > 2000 or time.monotonic() >= deadline
        conn.set_progress_handler(bounded, 1000)
        conn.execute("BEGIN")
        if not {"key", "value"} <= {row[1] for row in conn.execute("PRAGMA table_info(meta)")}:
            out["state"] = "SCHEMA_MISMATCH"
            return out
        meta = dict(conn.execute("SELECT key,value FROM meta WHERE key IN "
            "('schema_version','heartbeat_at','last_success_at','audit_pruned_max_export_seq') LIMIT 4"))
        required = {"user_id", "user_tag", "upload_bytes", "download_bytes", "closed_at"}
        if meta.get("schema_version") != "4" or not required <= {row[1] for row in conn.execute("PRAGMA table_info(connections)")}:
            out["state"] = "SCHEMA_MISMATCH"
            return out
        polled, heartbeat, watermark = meta.get("last_success_at"), meta.get("heartbeat_at"), meta.get("audit_pruned_max_export_seq")
        poll_age = _parse_iso_age_seconds(polled, now) if isinstance(polled, str) and len(polled) <= 40 else None
        heartbeat_age = _parse_iso_age_seconds(heartbeat, now) if isinstance(heartbeat, str) and len(heartbeat) <= 40 else None
        if (poll_age is None or poll_age < 0 or heartbeat_age is None or heartbeat_age < 0
                or not isinstance(watermark, str) or not watermark.isascii() or not watermark.isdigit()
                or len(watermark) > 19 or int(watermark) > 2**63 - 1):
            return out
        out.update(sampled_at=polled, heartbeat_age_seconds=heartbeat_age, pruned_max_export_seq=int(watermark))
        rows = conn.execute("SELECT user_id,MAX(user_tag),SUM(upload_bytes),SUM(download_bytes),"
            "SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END),MIN(upload_bytes),MIN(download_bytes),"
            "MIN(typeof(upload_bytes)='integer' AND typeof(download_bytes)='integer') "
            "FROM connections GROUP BY user_id ORDER BY user_id LIMIT 65").fetchall()
        out["truncated"] = len(rows) > 64
        seen = set()
        for uid, tag, up, down, count, min_up, min_down, integers in rows[:64]:
            if (not isinstance(uid, str) or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", uid)
                    or tag is not None and (not isinstance(tag, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", tag))
                    or integers != 1 or any(type(val) is not int or not 0 <= val <= 2**63 - 1 for val in (up, down, count, min_up, min_down))
                    or up + down > 2**63 - 1):
                out["truncated"] = True
                continue
            key = hashlib.sha256(uid.lower().encode()).hexdigest()
            if key in seen:
                out.update(state="UNKNOWN", users=[], truncated=True)
                return out
            seen.add(key)
            out["users"].append({"user_key": key, "tag": tag, "retained_bytes": up + down, "connections": count})
        out["state"] = "PARTIAL" if out["truncated"] else "OK"
    except FileNotFoundError:
        out["state"] = "MISSING"
    except (PermissionError, OSError):
        out["state"] = "UNREADABLE"
    except sqlite3.Error as exc:
        code = getattr(exc, "sqlite_errorcode", 0) & 0xff
        out["state"] = "CORRUPT" if code in (getattr(sqlite3, "SQLITE_CORRUPT", 11), getattr(sqlite3, "SQLITE_NOTADB", 26)) else "UNKNOWN"
        out["users"] = []
    except (ValueError, TypeError, OverflowError):
        out.update(state="UNKNOWN", users=[])
    finally:
        if conn is not None:
            conn.close()
    return out


def main(argv: list[str]) -> int:
    state_dir = Path(argv[1] if len(argv) > 1 else "/etc/vincula")
    accounting_db = Path(
        argv[2] if len(argv) > 2 else "/var/lib/vincula/accounting.db"
    )
    builder = {"--audit": build_audit_snapshot, "--users": build_user_snapshot}.get(argv[3] if len(argv) > 3 else "", build_snapshot)
    doc = builder(state_dir=state_dir, accounting_db=accounting_db)
    sys.stdout.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
