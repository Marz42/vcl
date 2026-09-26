"""Bounded machine-local monitoring cache, independent of fleet-cache/v4."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sqlite3
from pathlib import Path


def sibling(name: str):
    spec = importlib.util.spec_from_file_location("vcl_monitor_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


health = sibling("health")
validator = sibling("schema_validate")
RAW_CAP = 100_000
ROLLUP_CAP = 200_000
TABLES = {"telemetry_samples": (86400, RAW_CAP), "telemetry_rollup_5m": (7 * 86400, ROLLUP_CAP),
          "telemetry_rollup_hourly": (90 * 86400, ROLLUP_CAP)}
DDL = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS health_latest (node_id TEXT PRIMARY KEY, at REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS telemetry_samples (id INTEGER PRIMARY KEY, node_id TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS samples_at ON telemetry_samples(at);
"""


def encode(value) -> str:
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def decode_record(payload: str) -> dict:
    if len(payload) > 16384:
        raise ValueError("oversize cache row")
    value = json.loads(payload)
    # Regenerate rather than echo unknown/cache-injected fields to a UI.
    if not isinstance(value, dict) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", value.get("name", "")):
        raise ValueError("invalid node name")
    if not validator.UUID_RE.fullmatch(value.get("node_id", "")):
        raise ValueError("invalid node id")
    for key in ("received_at", "sampled_at"):
        if value.get(key) is not None and health.number(value[key]) is None:
            raise ValueError("invalid timestamp")
    if value.get("received_at") is None or value.get("observation_state") not in health.OBSERVATION_STATES:
        raise ValueError("invalid observation")
    if value.get("observed_at") is not None and not validator._is_rfc3339(value["observed_at"]):
        raise ValueError("invalid observation timestamp")
    if value.get("instance_id") is not None and not validator.UUID_RE.fullmatch(value["instance_id"]):
        raise ValueError("invalid instance")
    allowed_metrics = {"uptime_seconds", "load1", "load5", "load15", "memory_total_bytes", "memory_used_bytes",
                       "disk_total_bytes", "disk_used_bytes", "rx_bytes", "tx_bytes", "connections", "restart_count",
                       "last_poll_age_seconds", "export_seq", "last_event_age_seconds", "rx_bytes_per_second", "tx_bytes_per_second"}
    numeric = value.get("metrics", {})
    if not isinstance(numeric, dict):
        raise ValueError("invalid metrics")
    services = value.get("services", {})
    if not isinstance(services, dict):
        services = {}
    dimensions = value["health"]
    clean_health = {}
    reasons = {"NO_OBSERVATION", "ERROR", "TIMEOUT", "SSH_RESPONDED", "AUTH_FAILED", "UNSUPPORTED", "FRESH",
               "TELEMETRY_STALE", "SERVICE_INACTIVE", "POLL_AGE_MISSING", "POLL_STALLED", "POLL_RECENT",
               "OK", "NOT_CONFIGURED", "TLS_FAILED", "DNS_FAILED", "CONNECT_FAILED", "HTTP_FAILED",
               "RUNTIME_UNAVAILABLE", "INVALID_CONFIG"}
    for key in health.DIMENSIONS:
        item = dimensions[key]
        if item["state"] not in health.STATES or item["reason"] not in reasons:
            raise ValueError("invalid health")
        if any(type(item[k]) is not int or not 0 <= item[k] <= 1001 for k in ("failures", "successes")):
            raise ValueError("invalid health counters")
        clean_health[key] = {"state": item["state"], "reason": item["reason"],
                             "failures": min(1001, int(item["failures"])), "successes": min(1001, int(item["successes"]))}
    return {**{key: value.get(key) for key in ("name", "node_id", "instance_id", "received_at", "sampled_at", "observed_at", "observation_state")},
            "health": clean_health, "overall": health.overall(clean_health),
            "metrics": {key: health.number(val) for key, val in numeric.items() if key in allowed_metrics},
            "services": {key: services.get(key) if type(services.get(key)) is bool else None
                         for key in ("sing_box_active", "accountd_active")},
            "probe": health.clean_probe(value.get("probe"))}


class Store:
    def __init__(self, path: Path):
        self.path = path

    def writer(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass  # Another writer initialized the file; SQLite serializes the transaction.
        conn = sqlite3.connect(self.path, timeout=2)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
            conn.execute(f"PRAGMA max_page_count={256 * 1024 * 1024 // page_size}")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported observation cache schema")
            if version == 1:
                return conn
            conn.executescript(DDL)
            for table in ("telemetry_rollup_5m", "telemetry_rollup_hourly"):
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (node_id TEXT NOT NULL, at REAL NOT NULL, samples INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(node_id, at))")
                conn.execute(f"CREATE INDEX IF NOT EXISTS {table}_at ON {table}(at)")
            conn.execute("PRAGMA user_version=1")
            conn.commit()
            return conn
        except BaseException:
            conn.close()
            raise

    def record(self, node: dict, result: dict, now: float, probe=None) -> dict:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", node["name"]) or not validator.UUID_RE.fullmatch(node["node_id"]):
            raise ValueError("invalid monitoring target")
        if result.get("state") == "OK":
            snapshot = result.get("snapshot")
            if validator.validate_telemetry_v1(snapshot) or snapshot["node_id"] != node["node_id"]:
                result = {"state": "ERROR"}
        conn = self.writer()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM health_latest WHERE node_id=?", (node["node_id"],)).fetchone()
            previous = {}
            if row:
                try:
                    previous = decode_record(row[0])
                    if previous["node_id"] != node["node_id"]:
                        previous = {}
                except (ValueError, TypeError, KeyError):
                    pass
            if previous and now <= previous["received_at"]:
                conn.rollback()
                return previous
            if not row and conn.execute("SELECT count(*) FROM health_latest").fetchone()[0] >= 1024:
                raise ValueError("monitor node capacity reached")
            # Reclaim expired rows before inserting, including after a previous SQLITE_FULL.
            self.prune(conn, now)
            record = health.build(node, result, previous, now, probe)
            payload = encode(record)
            conn.execute("INSERT OR REPLACE INTO health_latest VALUES(?,?,?)", (node["node_id"], now, payload))
            conn.execute("INSERT INTO telemetry_samples(node_id,at,payload) VALUES(?,?,?)", (node["node_id"], now, payload))
            for table, width in (("telemetry_rollup_5m", 300), ("telemetry_rollup_hourly", 3600)):
                bucket = int(now // width) * width
                row = conn.execute(f"SELECT samples,payload FROM {table} WHERE node_id=? AND at=?", (node["node_id"], bucket)).fetchone()
                count, aggregate = 0, {}
                if row:
                    try:
                        count, aggregate = int(row[0]), json.loads(row[1])
                        if not isinstance(aggregate, dict):
                            aggregate = {}
                    except (ValueError, TypeError):
                        count, aggregate = 0, {}
                values = record["metrics"] if record["sampled_at"] == now else {}
                # Each metric has its own sample count: failed/missing polls are not zeroes.
                clean = {}
                for key, val in values.items():
                    if val is not None:
                        old = aggregate.get(key, {})
                        if not isinstance(old, dict) or health.number(old.get("sum")) is None or type(old.get("count")) is not int or not 0 <= old["count"] <= 1_000_000:
                            old = {}
                        clean[key] = {"sum": old.get("sum", 0) + val, "count": old.get("count", 0) + 1}
                for key in record["metrics"]:
                    if key not in clean and isinstance(aggregate.get(key), dict):
                        old = aggregate[key]
                        if health.number(old.get("sum")) is not None and type(old.get("count")) is int and 0 <= old["count"] <= 1_000_000:
                            clean[key] = {"sum": old["sum"], "count": old["count"]}
                conn.execute(f"INSERT OR REPLACE INTO {table} VALUES(?,?,?,?)", (node["node_id"], bucket, count + 1, encode(clean)))
            self.prune(conn, now)
            conn.commit()
            return record
        finally:
            conn.close()

    @staticmethod
    def prune(conn, now):
        for table, (retention, cap) in TABLES.items():
            conn.execute(f"DELETE FROM {table} WHERE at < ?", (now - retention,))
            excess = max(0, conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] - cap)
            if excess:
                conn.execute(f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} ORDER BY at,rowid LIMIT ?)", (excess,))
                conn.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", ("truncated_" + table, str(now)))

    def read(self, nodes: list[dict], now: float) -> dict:
        records, cache_state = {}, "EMPTY"
        conn = None
        try:
            if self.path.is_file():
                conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
                conn.execute("PRAGMA query_only=ON")
                if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("unsupported schema")
                cache_state = "OK"
                for node_id, payload in conn.execute("SELECT node_id,payload FROM health_latest LIMIT 1024"):
                    try:
                        record = decode_record(payload)
                        if record["node_id"] != node_id:
                            raise ValueError("identity mismatch")
                        records[node_id] = health.present(record, now)
                    except (ValueError, TypeError, KeyError, OverflowError):
                        cache_state = "PARTIAL"
        except (sqlite3.Error, OSError, ValueError):
            cache_state = "CACHE_CORRUPT"
        finally:
            if conn is not None:
                conn.close()
        out = []
        for node in nodes:
            item = records.get(node["node_id"])
            if item is None:
                item = health.present(health.build(node, {"state": "UNSUPPORTED"}, {}, now), now)
                item["health"] = {key: health.transition({}, "UNKNOWN", "NO_OBSERVATION") for key in health.DIMENSIONS}
                item["observation_state"] = "UNKNOWN"
                item["received_at"] = None
            item["name"] = node["name"]
            out.append(item)
        return {"schema": "monitor/v1", "generated_at": health.utc(now), "cache_state": cache_state, "nodes": out}
