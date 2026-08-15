#!/usr/bin/env python3
"""vincula-stats — single query/result model for Vincula accounting CLI.

Approximate accounting visibility (Clash polling). Not billing-grade.
UTC day windows only. Targets Python 3.10+. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ACCOUNTING_MODE = "approximate / Clash polling"
DEFAULT_LIMIT = 20
MAX_LIMIT = 1000


@dataclass
class Meta:
    accounting_mode: str
    collector_state: str
    last_success_at: str
    freshness: str
    hostname_coverage_pct: Optional[float]
    ip_only_coverage_pct: Optional[float]
    period_start: str
    period_end: str


@dataclass
class Result:
    meta: Meta
    mode: str
    columns: List[str]
    rows: List[Dict[str, Any]] = field(default_factory=list)
    warning: Optional[str] = None


def utc_today(day_offset: int = 0, now: Optional[date] = None) -> date:
    """UTC calendar date, optionally shifted by day_offset.

    Clock injection (tests): pass now=, or set VINCULA_STATS_NOW=YYYY-MM-DD.
    """
    if now is None:
        env = os.environ.get("VINCULA_STATS_NOW", "").strip()
        now = date.fromisoformat(env) if env else datetime.now(timezone.utc).date()
    elif isinstance(now, datetime):
        now = now.date()
    return now - timedelta(days=day_offset)


def period_for_days(days: int, day_offset: int) -> Tuple[str, str]:
    end = utc_today(day_offset)
    start = end - timedelta(days=max(days, 1) - 1)
    return start.isoformat(), end.isoformat()


def period_for_month(day_offset: int) -> Tuple[str, str]:
    """UTC calendar month containing (today - day_offset), from day 1 through that date."""
    end = utc_today(day_offset)
    start = end.replace(day=1)
    return start.isoformat(), end.isoformat()


def period_for_range(start: Any, end: Any) -> Tuple[str, str]:
    """Inclusive UTC day window [start, end] as YYYY-MM-DD strings."""
    start_d = start if isinstance(start, date) and not isinstance(start, datetime) else date.fromisoformat(str(start))
    end_d = end if isinstance(end, date) and not isinstance(end, datetime) else date.fromisoformat(str(end))
    if end_d < start_d:
        raise ValueError("period end is before start")
    return start_d.isoformat(), end_d.isoformat()


def normalize_host(host: Optional[str]) -> Optional[str]:
    if host is None:
        return None
    if not isinstance(host, str):
        return None
    value = host.strip().lower().rstrip(".")
    return value or None


def is_ip_literal(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def host_display(dest: Optional[str]) -> str:
    if not dest or dest == "(unknown)":
        return dest or "(unknown)"
    if is_ip_literal(dest):
        return f"[IP only] {dest}"
    return dest


def human_bytes(n: Any) -> str:
    try:
        value = float(int(n or 0))
    except (TypeError, ValueError):
        value = 0.0
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{int(value)} B"


def clamp_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, n))


def load_users(path: str) -> Dict[str, Dict[str, Any]]:
    """Index users by user_id and by tag for enrichment / current attribution."""
    by_id: Dict[str, Dict[str, Any]] = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return by_id
    for u in data.get("users", []) or []:
        if not isinstance(u, dict):
            continue
        uid = u.get("user_id") or ""
        tag = u.get("tag") or ""
        info = {
            "user_id": uid,
            "tag": tag,
            "display_name": u.get("display_name") or "",
            "department": u.get("department") or "",
        }
        if uid:
            by_id[uid] = info
        if tag and tag not in by_id:
            by_id[f"tag:{tag}"] = info
    return by_id


def resolve_user(by_id: Dict[str, Dict[str, Any]], user_id: str, user_tag: str) -> Dict[str, Any]:
    if user_id and user_id in by_id:
        return by_id[user_id]
    if user_tag:
        tagged = by_id.get(f"tag:{user_tag}")
        if tagged:
            return tagged
    return {
        "user_id": user_id or "",
        "tag": user_tag or "",
        "display_name": "",
        "department": "",
    }


def freshness_label(last_success_at: str) -> str:
    if not last_success_at:
        return "unknown"
    ts = last_success_at.strip()
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        when = datetime.fromisoformat(ts)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - when).total_seconds()
        if age < 0:
            age = 0
        if age < 60:
            return f"{int(age)} seconds ago"
        if age < 3600:
            return f"{int(age // 60)} minutes ago"
        if age < 86400:
            return f"{int(age // 3600)} hours ago"
        return f"{int(age // 86400)} days ago"
    except ValueError:
        return last_success_at


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def coverage_from_daily(
    conn: sqlite3.Connection, start: str, end: str
) -> Tuple[Optional[float], Optional[float]]:
    rows = conn.execute(
        """
        SELECT destination_host AS dest, SUM(connection_count) AS cnt
        FROM daily_usage
        WHERE date >= ? AND date <= ?
        GROUP BY 1
        """,
        (start, end),
    ).fetchall()
    host_n = 0
    ip_n = 0
    for r in rows:
        dest = r["dest"] or ""
        cnt = int(r["cnt"] or 0)
        if is_ip_literal(dest):
            ip_n += cnt
        elif dest and dest != "(unknown)":
            host_n += cnt
        # (unknown) excluded from both buckets
    total = host_n + ip_n
    if total <= 0:
        return None, None
    return round(100.0 * host_n / total, 1), round(100.0 * ip_n / total, 1)


def build_meta(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    collector_state: str,
    last_success_at: str,
) -> Meta:
    host_pct, ip_pct = coverage_from_daily(conn, start, end)
    return Meta(
        accounting_mode=ACCOUNTING_MODE,
        collector_state=collector_state or "unknown",
        last_success_at=last_success_at or "",
        freshness=freshness_label(last_success_at or ""),
        hostname_coverage_pct=host_pct,
        ip_only_coverage_pct=ip_pct,
        period_start=start,
        period_end=end,
    )


def fetch_daily_rows(
    conn: sqlite3.Connection, start: str, end: str
) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT date, user_id, user_tag, destination_host,
               upload_bytes, download_bytes, connection_count
        FROM daily_usage
        WHERE date >= ? AND date <= ?
        """,
        (start, end),
    ).fetchall()


def query(
    db_path: str,
    users_path: str,
    mode: str,
    days: int,
    day_offset: int,
    month: bool,
    user_tag: str,
    department: str,
    host: str,
    limit: int,
    collector_state: str,
    last_success_at: str,
    range_start: str = "",
    range_end: str = "",
) -> Result:
    if range_start:
        start, end = period_for_range(range_start, range_end or range_start)
    elif month:
        start, end = period_for_month(day_offset)
    else:
        start, end = period_for_days(days, day_offset)

    limit = clamp_limit(limit)
    users = load_users(users_path)

    try:
        conn = open_db(db_path)
    except sqlite3.Error as exc:
        raise SystemExit(f"ERROR: cannot open accounting DB: {exc}") from exc

    if not table_exists(conn, "daily_usage"):
        conn.close()
        print("(daily_usage missing — run vincula-accountd once)", file=sys.stderr)
        raise SystemExit(0)

    meta = build_meta(conn, start, end, collector_state, last_success_at)
    warning = None
    if collector_state != "active":
        warning = (
            "WARNING:\n"
            "Accounting collector is not healthy.\n"
            "Results may be stale.\n\n"
            f"Last successful sample:\n{last_success_at or '(none)'}"
        )

    raw = fetch_daily_rows(conn, start, end)
    conn.close()

    # Enrich + current department attribution
    enriched: List[Dict[str, Any]] = []
    for r in raw:
        info = resolve_user(users, r["user_id"] or "", r["user_tag"] or "")
        dest = r["destination_host"] or ""
        up = int(r["upload_bytes"] or 0)
        down = int(r["download_bytes"] or 0)
        enriched.append(
            {
                "user_id": info["user_id"] or (r["user_id"] or ""),
                "tag": info["tag"] or (r["user_tag"] or ""),
                "display_name": info["display_name"],
                "department": info["department"],
                "destination_host": dest,
                "upload_bytes": up,
                "download_bytes": down,
                "total_bytes": up + down,
                "connection_count": int(r["connection_count"] or 0),
            }
        )

    host_filter = normalize_host(host) if host else None

    def match_user(e: Dict[str, Any]) -> bool:
        return e["tag"] == user_tag or e["user_id"] == user_tag

    if mode == "user":
        if not user_tag:
            raise SystemExit("ERROR: --user TAG required for mode=user")
        enriched = [e for e in enriched if match_user(e)]
        return _aggregate_users(meta, enriched, mode, warning)

    if mode == "department":
        if not department:
            raise SystemExit("ERROR: --department NAME required for mode=department")
        enriched = [e for e in enriched if e["department"] == department]
        return _aggregate_users(meta, enriched, mode, warning)

    if mode == "host":
        if not host_filter:
            raise SystemExit("ERROR: --host HOST required for mode=host")
        matched = [
            e
            for e in enriched
            if normalize_host(e["destination_host"]) == host_filter
        ]
        return _aggregate_users(meta, matched, mode, warning)

    if mode == "top_users":
        return _top_users(meta, enriched, limit, warning)

    if mode == "top_departments":
        return _top_departments(meta, enriched, limit, warning)

    if mode == "top_hosts":
        # Optional --user filter (compat: vcl stats user TAG --top N)
        if user_tag:
            enriched = [e for e in enriched if match_user(e)]
        return _top_hosts(meta, enriched, limit, warning)

    # summary: all users
    return _aggregate_users(meta, enriched, "summary", warning)


def _aggregate_users(
    meta: Meta, rows: Sequence[Dict[str, Any]], mode: str, warning: Optional[str]
) -> Result:
    buckets: Dict[str, Dict[str, Any]] = {}
    for e in rows:
        key = e["user_id"] or e["tag"] or "(unknown)"
        b = buckets.get(key)
        if b is None:
            b = {
                "user_id": e["user_id"],
                "tag": e["tag"],
                "display_name": e["display_name"],
                "department": e["department"],
                "upload_bytes": 0,
                "download_bytes": 0,
                "total_bytes": 0,
                "connection_count": 0,
            }
            buckets[key] = b
        b["upload_bytes"] += e["upload_bytes"]
        b["download_bytes"] += e["download_bytes"]
        b["total_bytes"] += e["total_bytes"]
        b["connection_count"] += e["connection_count"]
    out = sorted(buckets.values(), key=lambda x: x["total_bytes"], reverse=True)
    columns = [
        "user_id",
        "tag",
        "display_name",
        "department",
        "upload_bytes",
        "download_bytes",
        "total_bytes",
        "connection_count",
    ]
    return Result(meta=meta, mode=mode, columns=columns, rows=out, warning=warning)


def _top_users(
    meta: Meta, rows: Sequence[Dict[str, Any]], limit: int, warning: Optional[str]
) -> Result:
    result = _aggregate_users(meta, rows, "top_users", warning)
    result.rows = result.rows[:limit]
    return result


def _top_departments(
    meta: Meta, rows: Sequence[Dict[str, Any]], limit: int, warning: Optional[str]
) -> Result:
    buckets: Dict[str, Dict[str, Any]] = {}
    for e in rows:
        dept = e["department"] or "(none)"
        b = buckets.get(dept)
        if b is None:
            b = {
                "department": dept,
                "upload_bytes": 0,
                "download_bytes": 0,
                "total_bytes": 0,
                "connection_count": 0,
            }
            buckets[dept] = b
        b["upload_bytes"] += e["upload_bytes"]
        b["download_bytes"] += e["download_bytes"]
        b["total_bytes"] += e["total_bytes"]
        b["connection_count"] += e["connection_count"]
    out = sorted(buckets.values(), key=lambda x: x["total_bytes"], reverse=True)[:limit]
    columns = [
        "department",
        "upload_bytes",
        "download_bytes",
        "total_bytes",
        "connection_count",
    ]
    return Result(meta=meta, mode="top_departments", columns=columns, rows=out, warning=warning)


def _top_hosts(
    meta: Meta, rows: Sequence[Dict[str, Any]], limit: int, warning: Optional[str]
) -> Result:
    buckets: Dict[str, Dict[str, Any]] = {}
    for e in rows:
        dest = e["destination_host"] or "(unknown)"
        key = normalize_host(dest) or dest
        b = buckets.get(key)
        if b is None:
            b = {
                "destination_host": dest,
                "host_label": host_display(dest),
                "upload_bytes": 0,
                "download_bytes": 0,
                "total_bytes": 0,
                "connection_count": 0,
                "ip_only": is_ip_literal(dest),
            }
            buckets[key] = b
        b["upload_bytes"] += e["upload_bytes"]
        b["download_bytes"] += e["download_bytes"]
        b["total_bytes"] += e["total_bytes"]
        b["connection_count"] += e["connection_count"]
    out = sorted(buckets.values(), key=lambda x: x["total_bytes"], reverse=True)[:limit]
    columns = [
        "destination_host",
        "host_label",
        "upload_bytes",
        "download_bytes",
        "total_bytes",
        "connection_count",
        "ip_only",
    ]
    return Result(meta=meta, mode="top_hosts", columns=columns, rows=out, warning=warning)


def result_to_dict(result: Result) -> Dict[str, Any]:
    return {
        "meta": asdict(result.meta),
        "mode": result.mode,
        "columns": list(result.columns),
        "rows": result.rows,
        "warning": result.warning,
    }


def render_table(result: Result) -> None:
    m = result.meta
    if result.warning:
        print(result.warning)
        print()
    print("Vincula Usage Report")
    print()
    print("Period:")
    print(f"{m.period_start} → {m.period_end} UTC")
    print()
    print("Accounting mode:")
    print(m.accounting_mode)
    print()
    print("Accounting health")
    print()
    print(f"Mode: {m.accounting_mode}")
    coll = m.collector_state
    if coll != "active":
        print(f"Collector: STALE ({coll})")
    else:
        print(f"Collector: {coll}")
    print(f"Last successful sample: {m.freshness}")
    if m.last_success_at:
        print(f"  ({m.last_success_at})")
    print()
    print("Destination attribution:")
    if m.hostname_coverage_pct is None and m.ip_only_coverage_pct is None:
        print("  Hostname: n/a")
        print("  IP only:  n/a")
    else:
        hp = m.hostname_coverage_pct if m.hostname_coverage_pct is not None else 0.0
        ip = m.ip_only_coverage_pct if m.ip_only_coverage_pct is not None else 0.0
        print(f"  Hostname: {hp}%")
        print(f"  IP only:  {ip}%")
    print()

    if result.mode in ("summary", "user", "department", "host", "top_users"):
        print(
            f"{'USER':<16} {'DEPT':<14} {'DOWNLOAD':>12} {'UPLOAD':>12} {'TOTAL':>12}"
        )
        for r in result.rows:
            tag = (r.get("tag") or r.get("user_id") or "?")[:16]
            dept = (r.get("department") or "")[:14]
            print(
                f"{tag:<16} {dept:<14} "
                f"{human_bytes(r['download_bytes']):>12} "
                f"{human_bytes(r['upload_bytes']):>12} "
                f"{human_bytes(r['total_bytes']):>12}"
            )
    elif result.mode == "top_departments":
        print(f"{'DEPARTMENT':<24} {'DOWNLOAD':>12} {'UPLOAD':>12} {'TOTAL':>12}")
        for r in result.rows:
            name = (r.get("department") or "")[:24]
            print(
                f"{name:<24} "
                f"{human_bytes(r['download_bytes']):>12} "
                f"{human_bytes(r['upload_bytes']):>12} "
                f"{human_bytes(r['total_bytes']):>12}"
            )
    elif result.mode == "top_hosts":
        print(f"{'HOST':<40} {'DOWNLOAD':>12} {'UPLOAD':>12} {'TOTAL':>12}")
        for r in result.rows:
            label = (r.get("host_label") or r.get("destination_host") or "")[:40]
            print(
                f"{label:<40} "
                f"{human_bytes(r['download_bytes']):>12} "
                f"{human_bytes(r['upload_bytes']):>12} "
                f"{human_bytes(r['total_bytes']):>12}"
            )
    if not result.rows:
        print("(no daily_usage rows in period)")


def csv_fieldnames(result: Result) -> List[str]:
    base = ["period_start", "period_end"]
    if result.mode in ("summary", "user", "department", "host", "top_users"):
        return base + [
            "user_id",
            "tag",
            "display_name",
            "department",
            "upload_bytes",
            "download_bytes",
            "total_bytes",
        ]
    if result.mode == "top_departments":
        return base + [
            "department",
            "upload_bytes",
            "download_bytes",
            "total_bytes",
        ]
    if result.mode == "top_hosts":
        return base + [
            "destination_host",
            "host_label",
            "upload_bytes",
            "download_bytes",
            "total_bytes",
            "ip_only",
        ]
    return base + list(result.columns)


def render_csv(result: Result, csv_file: Optional[str]) -> None:
    fields = csv_fieldnames(result)
    rows_out: List[Dict[str, Any]] = []
    for r in result.rows:
        row = {"period_start": result.meta.period_start, "period_end": result.meta.period_end}
        for k in fields:
            if k in ("period_start", "period_end"):
                continue
            val = r.get(k, "")
            if isinstance(val, bool):
                val = "1" if val else "0"
            row[k] = val
        rows_out.append(row)

    if csv_file:
        path = Path(csv_file)
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows_out)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_out)


def render_json(result: Result) -> None:
    print(json.dumps(result_to_dict(result), indent=2, sort_keys=False))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Vincula accounting stats (UTC)")
    p.add_argument("--db", required=True)
    p.add_argument("--users", required=True)
    p.add_argument(
        "--mode",
        required=True,
        choices=(
            "summary",
            "user",
            "department",
            "host",
            "top_users",
            "top_departments",
            "top_hosts",
        ),
    )
    window = p.add_mutually_exclusive_group()
    window.add_argument("--days", type=int)
    window.add_argument("--date", metavar="YYYY-MM-DD")
    window.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", metavar="YYYY-MM-DD")
    p.add_argument("--day-offset", type=int, default=0)
    p.add_argument("--month", type=int, choices=(0, 1), default=0)
    p.add_argument("--user", default="")
    p.add_argument("--department", default="")
    p.add_argument("--host", default="")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--format", choices=("table", "json", "csv"), default="table")
    p.add_argument("--csv-file", default="")
    p.add_argument(
        "--collector-state",
        choices=("active", "inactive", "unknown"),
        default="unknown",
    )
    p.add_argument("--last-success-at", default="")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.days is not None and args.days < 1:
        print("ERROR: --days must be >= 1", file=sys.stderr)
        return 1
    if (args.from_date is None) != (args.to_date is None):
        print("ERROR: --from and --to must both be given", file=sys.stderr)
        return 1
    if (args.date or args.from_date) and args.month:
        print("ERROR: --date/--from/--to cannot be combined with --month", file=sys.stderr)
        return 1

    range_start = ""
    range_end = ""
    try:
        if args.date:
            range_start, range_end = period_for_range(args.date, args.date)
        elif args.from_date:
            range_start, range_end = period_for_range(args.from_date, args.to_date)
    except ValueError as exc:
        print(f"ERROR: invalid date window: {exc}", file=sys.stderr)
        return 1

    result = query(
        db_path=args.db,
        users_path=args.users,
        mode=args.mode,
        days=args.days if args.days is not None else 1,
        day_offset=args.day_offset,
        month=bool(args.month),
        user_tag=args.user,
        department=args.department,
        host=args.host,
        limit=args.limit,
        collector_state=args.collector_state,
        last_success_at=args.last_success_at or "",
        range_start=range_start,
        range_end=range_end,
    )
    if args.format == "json":
        render_json(result)
    elif args.format == "csv":
        render_csv(result, args.csv_file or None)
    else:
        render_table(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
