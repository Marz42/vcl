#!/usr/bin/env python3
"""Read-only telemetry/v1 snapshot for ``vcl telemetry snapshot --json``."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
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
        val = data.get(field)
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
        conn = sqlite3.connect(str(db_path))
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


def main(argv: list[str]) -> int:
    state_dir = Path(argv[1] if len(argv) > 1 else "/etc/vincula")
    accounting_db = Path(
        argv[2] if len(argv) > 2 else "/var/lib/vincula/accounting.db"
    )
    doc = build_snapshot(state_dir=state_dir, accounting_db=accounting_db)
    sys.stdout.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
