"""Local observation findings: pure detectors, bounded store, cache-only surfaces.

Unknown evidence never resolves an active finding. No remote calls or mutation
callbacks belong in this module; only the machine-local findings cache is written.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("vcl_finding_anomalies", Path(__file__).with_name("anomalies.py"))
anomalies = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anomalies)
_spec = importlib.util.spec_from_file_location("vcl_finding_users", Path(__file__).with_name("user_traffic.py"))
user_traffic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(user_traffic)

TYPES = {
    "AUDIT_STALLED": ("audit", "WARNING", "Accountd is inactive or its successful poll is older than 90 seconds."),
    "EXPORT_GAP": ("audit", "ERROR", "The local sync cursor is expired; retained remote audit history may be missing."),
    "SYNC_LAG": ("audit", "WARNING", "Unreceived export records remain and the last successful sync is older than 300 seconds."),
    "DISK_PRESSURE": ("node", "WARNING", "Filesystem usage is at least 90%; recovery requires usage below 85%."),
    "MEMORY_PRESSURE": ("node", "WARNING", "Memory usage is at least 90%; recovery requires usage below 85%."),
    "TELEMETRY_STALE": ("observation", "WARNING", "Telemetry is older than 90 seconds, replayed, or its clock is more than 30 seconds ahead."),
    "SCHEMA_MISMATCH": ("audit", "ERROR", "The Node accounting database does not satisfy the required schema 4 contract."),
    "ACCOUNTING_DB_CORRUPT": ("audit", "ERROR", "SQLite reported accounting database corruption; audit data is not trustworthy."),
    "EXPORT_SEQUENCE_REGRESSION": ("audit", "ERROR", "The audit export counter decreased within the same Node installation."),
    "SERVICE_RESTART_LOOP": ("node", "WARNING", "At least three automatic sing-box restarts occurred within 300 seconds."),
    "NETWORK_RATE_ANOMALY": ("node", "WARNING", "Network rate exceeds the rolling median/MAD threshold after at least 20 baseline samples spanning 540 seconds."),
    "USER_TRAFFIC_SPIKE": ("user", "WARNING", "User traffic rate exceeds the rolling median/MAD threshold after at least 20 baseline samples spanning 540 seconds."),
    "USER_CONNECTION_SPIKE": ("user", "WARNING", "Open user connections exceed the rolling median/MAD threshold after at least 20 baseline samples spanning 540 seconds."),
    "SUSTAINED_TRAFFIC_ANOMALY": ("user", "WARNING", "User traffic stayed above the rolling median/MAD threshold for at least 300 continuous seconds."),
}
NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,31}")
ID_RE = re.compile(r"[0-9a-f]{64}")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
FINDING_CAP, EVENT_CAP, SUBJECT_CAP, USER_CAP = 32768, 10000, 1024, 4096
RETENTION = 90 * 86400
EVIDENCE_KEYS = {"poll_age_seconds", "accountd_active", "remote_export_seq", "received_cursor",
                 "sync_age_seconds", "usage_ratio", "telemetry_age_seconds"}
EVIDENCE_KEYS |= {"db_schema", "heartbeat_age_seconds", "pruned_max_export_seq", "export_seq_delta",
                  "last_event_age_seconds", "min_retained_export_seq", "diagnostic_age_seconds", "diagnostic_fresh"}
EVIDENCE_KEYS |= {"value", "baseline_median", "baseline_mad", "threshold", "sample_count",
                  "baseline_span_seconds", "above_seconds", "restart_delta", "window_seconds"}
DDL = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS findings(id TEXT PRIMARY KEY, at REAL NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS findings_at ON findings(at);
CREATE TABLE IF NOT EXISTS timeline(id TEXT PRIMARY KEY, at REAL NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS timeline_at ON timeline(at);
CREATE TABLE IF NOT EXISTS evaluations(subject TEXT PRIMARY KEY, at REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_evaluations(subject TEXT PRIMARY KEY, node_key TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS user_evaluations_node ON user_evaluations(node_key);
"""


def number(value):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and 0 <= value <= 2**63 - 1 else None
    except OverflowError:
        return None


def stamp(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return number(when.timestamp()) if when.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def valid_time(value):
    return number(value) is not None and value <= 253402300799


def encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def digest(*parts):
    return hashlib.sha256(encode(parts).encode()).hexdigest()


def target(node):
    if not isinstance(node, dict) or not isinstance(node.get("name"), str) or not NAME_RE.fullmatch(node["name"]):
        raise ValueError("invalid finding target")
    if not isinstance(node.get("node_id"), str) or not UUID_RE.fullmatch(node["node_id"]):
        raise ValueError("invalid finding identity")
    # Opaque stable subject: logical IDs, SSH endpoints and credentials are not copied.
    return {"kind": "node", "name": node["name"], "key": digest(node["node_id"])}


def clean_subject(value):
    if not isinstance(value, dict) or value.get("kind") not in ("node", "user"):
        raise ValueError("invalid subject")
    name, key = value.get("name"), value.get("key")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or not isinstance(key, str) or not ID_RE.fullmatch(key):
        raise ValueError("invalid subject")
    if value["kind"] == "node":
        return {"kind": "node", "name": name, "key": key}
    node_key, user_key, tag = value.get("node_key"), value.get("user_key"), value.get("user_tag")
    if (any(not isinstance(item, str) or not ID_RE.fullmatch(item) for item in (node_key, user_key))
            or not isinstance(tag, str) or not NAME_RE.fullmatch(tag) or key != digest(node_key, "user", user_key)):
        raise ValueError("invalid user subject")
    return {"kind": "user", "name": name, "key": key, "node_key": node_key, "user_key": user_key, "user_tag": tag}


def user_target(node, profile):
    parent = target(node)
    key = profile["user_key"]
    return clean_subject({"kind": "user", "name": parent["name"], "key": digest(parent["key"], "user", key),
                          "node_key": parent["key"], "user_key": key, "user_tag": profile.get("tag") or "user-" + key[:12]})


def clean_evidence(value):
    if not isinstance(value, dict):
        raise ValueError("invalid evidence")
    return {key: val for key, val in value.items() if key in EVIDENCE_KEYS
            and (type(val) is bool or number(val) is not None)}


def decode(payload, kind):
    if not isinstance(payload, str) or len(payload) > 8192:
        raise ValueError("oversize finding cache row")
    try:
        value = json.loads(payload)
    except (ValueError, RecursionError):
        raise ValueError("invalid finding cache row") from None
    if not isinstance(value, dict):
        raise ValueError("invalid finding cache row")
    subject = clean_subject(value.get("subject"))
    if kind in ("evaluation", "user_evaluation"):
        if subject["kind"] != ("user" if kind == "user_evaluation" else "node"):
            raise ValueError("invalid evaluation subject kind")
        checks = value.get("checks")
        baselines = value.get("baselines", {})
        if not isinstance(checks, dict) or not isinstance(baselines, dict) or not valid_time(value.get("evaluated_at")):
            raise ValueError("invalid evaluation")
        return {"subject": subject, "evaluated_at": value["evaluated_at"],
                "checks": {key: checks[key] for key in TYPES if (key in user_traffic.TYPES) == (kind == "user_evaluation")
                           and checks.get(key) in ("ANOMALOUS", "NORMAL", "UNKNOWN")},
                "context": clean_context(value.get("context")), "audit": clean_audit(value.get("audit")),
                "user_coverage": clean_user_coverage(value.get("user_coverage")),
                "detector_state": user_traffic.clean_state(value.get("detector_state")) if kind == "user_evaluation" else anomalies.clean_state(value.get("detector_state")),
                "baselines": {key: (user_traffic.clean_summary(item) if kind == "user_evaluation" else anomalies.clean_summary(item))
                              for key, item in baselines.items()
                              if key in (user_traffic.TYPES if kind == "user_evaluation" else ("SERVICE_RESTART_LOOP", "NETWORK_RATE_ANOMALY"))}}
    id_field = "finding_id" if kind == "finding" else "id"
    if not isinstance(value.get(id_field), str) or not ID_RE.fullmatch(value[id_field]):
        raise ValueError("invalid row id")
    if kind == "finding":
        typ = value.get("type")
        if not isinstance(typ, str) or typ not in TYPES or value.get("state") not in ("ACTIVE", "RESOLVED"):
            raise ValueError("invalid finding")
        if (typ in user_traffic.TYPES) != (subject["kind"] == "user"):
            raise ValueError("invalid finding subject kind")
        for key in ("first_seen", "last_seen"):
            if not valid_time(value.get(key)):
                raise ValueError("invalid finding time")
        if value["last_seen"] < value["first_seen"] or value["finding_id"] != digest(subject["key"], typ):
            raise ValueError("invalid finding identity or chronology")
        category, severity, explanation = TYPES[typ]
        return {"finding_id": value["finding_id"], "type": typ, "category": category, "severity": severity,
                "subject": subject, "state": value["state"], "first_seen": value["first_seen"],
                "last_seen": value["last_seen"], "evidence": clean_evidence(value.get("evidence")),
                "explanation": explanation}
    if not valid_time(value.get("at")) or value.get("kind") not in ("FINDING_OPEN", "FINDING_RESOLVED", "HEALTH_CHANGE", "SERVICE_CHANGE", "SERVICE_RESTART", "PROBE_RESULT"):
        raise ValueError("invalid timeline event")
    detail = value.get("detail")
    if not isinstance(detail, dict):
        raise ValueError("invalid timeline detail")
    if value["kind"].startswith("FINDING_"):
        if not isinstance(detail.get("type"), str) or detail["type"] not in TYPES:
            raise ValueError("invalid timeline finding")
        if (detail["type"] in user_traffic.TYPES) != (subject["kind"] == "user"):
            raise ValueError("invalid timeline subject kind")
        detail = {"type": detail["type"]}
    elif value["kind"] == "SERVICE_RESTART":
        if subject["kind"] != "node":
            raise ValueError("invalid service event subject")
        delta = detail.get("restart_delta")
        if type(delta) is not int or number(delta) is None or delta == 0:
            raise ValueError("invalid restart event")
        detail = {"restart_delta": delta}
    else:
        if subject["kind"] != "node":
            raise ValueError("invalid node event subject")
        detail = clean_context(detail)
    return {"id": value["id"], "at": value["at"], "kind": value["kind"], "subject": subject, "detail": detail}


def clean_context(value):
    value = value if isinstance(value, dict) else {}
    out = {}
    states = {"HEALTHY", "SUSPECT", "DEGRADED", "UNREACHABLE", "RECOVERING", "UNKNOWN"}
    for key in ("node", "observation", "proxy", "accounting"):
        if isinstance(value.get(key), str) and value[key] in states:
            out[key] = value[key]
    for key in ("sing_box_active", "accountd_active"):
        if type(value.get(key)) is bool:
            out[key] = value[key]
    if type(value.get("probe_success")) is bool:
        out["probe_success"] = value["probe_success"]
    return out


def clean_audit(value):
    value = value if isinstance(value, dict) else {}
    out = clean_evidence(value)
    for key, states in (("transport", ("OK", "ERROR", "AUTH_FAILED", "UNSUPPORTED", "TIMEOUT")),
                        ("db_state", ("OK", "MISSING", "CORRUPT", "UNREADABLE", "SCHEMA_MISMATCH", "UNKNOWN")),
                        ("progression", ("UNKNOWN", "COLD", "ADVANCING", "STATIONARY", "REGRESSED", "REPLAYED"))):
        if isinstance(value.get(key), str) and value[key] in states:
            out[key] = value[key]
    if valid_time(value.get("observed_at")):
        out["observed_at"] = value["observed_at"]
    return out


def clean_user_coverage(value):
    value = value if isinstance(value, dict) else {}
    out = {key: value[key] for key in ("observed_users", "stored_users", "capacity_skipped")
           if number(value.get(key)) is not None}
    out.update({key: value[key] for key in ("observed_at", "sampled_at") if valid_time(value.get(key))})
    if type(value.get("fresh")) is bool:
        out["fresh"] = value["fresh"]
    if isinstance(value.get("state"), str) and value["state"] in (
            "OK", "PARTIAL", "UNKNOWN", "MISSING", "CORRUPT", "UNREADABLE", "SCHEMA_MISMATCH",
            "ERROR", "AUTH_FAILED", "UNSUPPORTED", "TIMEOUT", "CAPACITY"):
        out["state"] = value["state"]
    return out


def audit_summary(record, cursor, now):
    diagnostic = record.get("audit_health") or {}
    snapshot = diagnostic.get("snapshot") or {}
    progress = record.get("audit_progress") or {}
    out = {"transport": diagnostic.get("state", "UNSUPPORTED"), "db_state": snapshot.get("db_state"),
           "progression": progress.get("state", "UNKNOWN"), "observed_at": stamp(snapshot.get("observed_at")),
           "export_seq_delta": progress.get("export_seq_delta"), "remote_export_seq": snapshot.get("export_seq"),
           "db_schema": snapshot.get("db_schema"), "heartbeat_age_seconds": snapshot.get("heartbeat_age_seconds"),
           "poll_age_seconds": snapshot.get("last_poll_age_seconds"), "accountd_active": snapshot.get("accountd_active"),
           "pruned_max_export_seq": snapshot.get("pruned_max_export_seq"),
           "min_retained_export_seq": snapshot.get("min_retained_export_seq"),
           "last_event_age_seconds": snapshot.get("last_event_age_seconds")}
    if out["observed_at"] is not None:
        age = now - out["observed_at"]
        out["diagnostic_age_seconds"] = max(0, age)
        out["diagnostic_fresh"] = -30 <= age <= 90 and progress.get("state") not in ("REPLAYED", "REGRESSED")
    if cursor.get("instance_id") == record.get("instance_id") and cursor.get("cursor_kind") == "export_seq":
        out["received_cursor"] = cursor.get("last_export_seq")
        synced = stamp(cursor.get("last_sync_at"))
        if synced is not None and synced <= now:
            out["sync_age_seconds"] = now - synced
    return clean_audit(out)


def detect(record, cursor, now, active=()):
    """Tri-state signals: True anomaly, False recovery, None insufficient evidence.

    Export sequence jumps are legal; only the durable expired cursor proves a gap.
    A last-event age or stationary export counter alone never proves an audit stall.
    """
    checks = {key: (None, {}) for key in TYPES if key not in user_traffic.TYPES}
    record = record if isinstance(record, dict) else {}
    cursor = cursor if isinstance(cursor, dict) else {}
    observed = stamp(record.get("observed_at"))
    age = now - observed if observed is not None else None
    observation = (record.get("health") or {}).get("observation", {})
    stale = age is not None and (age > 90 or age < -30)
    replayed = observation.get("reason") == "TELEMETRY_STALE"
    if age is not None:
        checks["TELEMETRY_STALE"] = (stale or replayed, {"telemetry_age_seconds": max(0, age)})
    fresh = (not stale and not replayed and age is not None and record.get("observation_state") == "OK")
    if fresh:
        metrics = record.get("metrics") or {}
        services = record.get("services") or {}
        poll = number(metrics.get("last_poll_age_seconds"))
        if poll is not None:
            poll += max(0, age)  # Snapshot ages continue to age during local refresh.
        running = services.get("accountd_active")
        if type(running) is bool and (running is False or poll is not None):
            checks["AUDIT_STALLED"] = (not running or poll > 90,
                                      {"accountd_active": running, **({"poll_age_seconds": poll} if poll is not None else {})})
        for typ, prefix in (("DISK_PRESSURE", "disk"), ("MEMORY_PRESSURE", "memory")):
            total, used = number(metrics.get(prefix + "_total_bytes")), number(metrics.get(prefix + "_used_bytes"))
            if total is not None and used is not None and total > 0 and used <= total:
                ratio = used / total
                checks[typ] = (ratio >= (.85 if typ in active else .9), {"usage_ratio": ratio})
        # An instance reset cannot be compared against the preceding installation's cursor.
        same_instance = (cursor.get("instance_id") == record.get("instance_id") and record.get("instance_id") is not None
                         and cursor.get("cursor_kind") == "export_seq")
        if same_instance:
            if cursor.get("status") in ("expired", "ok"):
                checks["EXPORT_GAP"] = (cursor["status"] == "expired", {})
            seq, received = number(metrics.get("export_seq")), number(cursor.get("last_export_seq"))
            synced = stamp(cursor.get("last_sync_at"))
            if cursor.get("status") == "ok" and seq is not None and received is not None and received <= seq and synced is not None and synced <= now + 30:
                lag_age = max(0, now - synced)
                checks["SYNC_LAG"] = (seq > received and lag_age > 300,
                                      {"remote_export_seq": seq, "received_cursor": received, "sync_age_seconds": lag_age})
    diagnostic = record.get("audit_health")
    if isinstance(diagnostic, dict) and diagnostic.get("state") in ("ERROR", "AUTH_FAILED", "TIMEOUT"):
        checks["AUDIT_STALLED"] = (None, {})
        checks["SYNC_LAG"] = (None, {})
        if checks["EXPORT_GAP"][0] is not True:
            checks["EXPORT_GAP"] = (None, {})
    if isinstance(diagnostic, dict) and diagnostic.get("state") == "OK":
        snapshot = diagnostic.get("snapshot") or {}
        audit_at = stamp(snapshot.get("observed_at"))
        audit_age = now - audit_at if audit_at is not None else None
        # Only an independently fresh, identity-bound diagnostic proves DB/pipeline state.
        progress = (record.get("audit_progress") or {}).get("state")
        ordered = progress not in ("REPLAYED", "REGRESSED")
        trusted = (audit_age is not None and -30 <= audit_age <= 90 and snapshot.get("instance_id") == record.get("instance_id"))
        if trusted and progress in ("COLD", "ADVANCING", "STATIONARY", "REGRESSED"):
            checks["EXPORT_SEQUENCE_REGRESSION"] = (progress == "REGRESSED", {})
        if trusted and ordered:
            db = snapshot.get("db_state")
            schema = number(snapshot.get("db_schema"))
            checks["SCHEMA_MISMATCH"] = (True if db == "SCHEMA_MISMATCH" else False if db == "OK" else None,
                                         {"db_schema": schema} if schema is not None else {})
            checks["ACCOUNTING_DB_CORRUPT"] = (True if db == "CORRUPT" else False if db == "OK" else None, {})
            if db == "OK":
                heartbeat, poll = number(snapshot.get("heartbeat_age_seconds")), number(snapshot.get("last_poll_age_seconds"))
                running = snapshot.get("accountd_active")
                signal = (True if running is False else (max(heartbeat, poll) + max(0, audit_age) > 90)
                          if running is True and heartbeat is not None and poll is not None else None)
                checks["AUDIT_STALLED"] = (signal, clean_evidence({"heartbeat_age_seconds": heartbeat,
                                          "poll_age_seconds": poll, "accountd_active": running}))
                watermark, received = number(snapshot.get("pruned_max_export_seq")), number(cursor.get("last_export_seq"))
                seq = number(snapshot.get("export_seq"))
                same_instance = cursor.get("instance_id") == snapshot.get("instance_id") and cursor.get("cursor_kind") == "export_seq"
                if same_instance and watermark is not None and received is not None and seq is not None and received <= seq:
                    checks["EXPORT_GAP"] = (watermark > received or cursor.get("status") == "expired",
                                            {"pruned_max_export_seq": watermark, "received_cursor": received})
                elif checks["EXPORT_GAP"][0] is not True:
                    checks["EXPORT_GAP"] = (None, {})
                synced = stamp(cursor.get("last_sync_at"))
                if (same_instance and cursor.get("status") == "ok" and seq is not None and received is not None
                        and received <= seq and synced is not None and synced <= now + 30):
                    lag_age = max(0, now - synced)
                    checks["SYNC_LAG"] = (seq > received and lag_age > 300,
                                          {"remote_export_seq": seq, "received_cursor": received, "sync_age_seconds": lag_age})
                else:
                    checks["SYNC_LAG"] = (None, {})
            else:
                checks["AUDIT_STALLED"] = (None, {})
                checks["SYNC_LAG"] = (None, {})
                if checks["EXPORT_GAP"][0] is not True:
                    checks["EXPORT_GAP"] = (None, {})
        else:
            for typ in ("AUDIT_STALLED", "SYNC_LAG"):
                checks[typ] = (None, {})
            if checks["EXPORT_GAP"][0] is not True:
                checks["EXPORT_GAP"] = (None, {})
    return checks


class Store:
    def __init__(self, path):
        self.path = Path(path)

    def writer(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        conn = sqlite3.connect(self.path, timeout=2)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            size = conn.execute("PRAGMA page_size").fetchone()[0]
            conn.execute(f"PRAGMA max_page_count={128 * 1024 * 1024 // size}")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("unsupported findings cache schema")
            if version < 2:
                if version == 1 and not {"metadata", "findings", "timeline", "evaluations"} <= {
                        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                    raise ValueError("invalid findings cache structure")
                conn.executescript("BEGIN IMMEDIATE;\n" + DDL + "\nPRAGMA user_version=2;\nCOMMIT;")
            return conn
        except BaseException:
            conn.close()
            raise

    @staticmethod
    def prune(conn, now):
        conn.execute("DELETE FROM timeline WHERE at < ?", (now - RETENTION,))
        conn.execute("DELETE FROM user_evaluations WHERE at < ?", (now - RETENTION,))
        for fid, payload in conn.execute("SELECT id,payload FROM findings WHERE at < ? LIMIT ?", (now - RETENTION, FINDING_CAP)):
            try:
                if decode(payload, "finding")["state"] == "RESOLVED":
                    conn.execute("DELETE FROM findings WHERE id=?", (fid,))
            except (ValueError, TypeError, KeyError):
                conn.execute("DELETE FROM findings WHERE id=?", (fid,))
        for table, cap in (("findings", FINDING_CAP), ("timeline", EVENT_CAP), ("evaluations", SUBJECT_CAP), ("user_evaluations", USER_CAP)):
            # Finding payloads may be externally corrupted; never use JSON functions for cap pruning.
            excess = max(0, conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] - cap)
            if excess:
                conn.execute(f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} ORDER BY at,rowid LIMIT ?)", (excess,))
                conn.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", ("truncated_" + table, str(now)))

    def evaluate(self, node, record, cursor, now):
        subject = target(node)
        record = record if isinstance(record, dict) else {}
        if not valid_time(now):
            raise ValueError("invalid evaluation time")
        conn = self.writer()
        try:
            conn.execute("BEGIN IMMEDIATE")
            previous = {}
            row = conn.execute("SELECT payload FROM evaluations WHERE subject=?", (subject["key"],)).fetchone()
            if row:
                try:
                    previous = decode(row[0], "evaluation")
                    if previous["subject"]["key"] != subject["key"]:
                        previous = {}
                except (ValueError, TypeError):
                    pass
            if previous and now <= previous["evaluated_at"]:
                conn.rollback()
                return
            existing = {}
            for typ in TYPES:
                fid = digest(subject["key"], typ)
                row = conn.execute("SELECT payload FROM findings WHERE id=?", (fid,)).fetchone()
                if row:
                    try:
                        item = decode(row[0], "finding")
                        if item["finding_id"] == fid and item["type"] == typ and item["subject"]["key"] == subject["key"]:
                            existing[typ] = item
                    except (ValueError, TypeError):
                        pass
            checks = detect(record, cursor, now, [typ for typ, item in existing.items() if item["state"] == "ACTIVE"])
            node_checks, detector_state, baselines, lifecycle = anomalies.evaluate(
                record, previous.get("detector_state"), now, [typ for typ, item in existing.items() if item["state"] == "ACTIVE"])
            checks.update(node_checks)
            for typ, (signal, evidence) in checks.items():
                old = existing.get(typ)
                if signal is None or (signal is False and (not old or old["state"] == "RESOLVED")):
                    continue
                state = "ACTIVE" if signal else "RESOLVED"
                fid = digest(subject["key"], typ)
                category, severity, explanation = TYPES[typ]
                first = old["first_seen"] if old else now
                item = {"finding_id": fid, "type": typ, "category": category, "subject": subject,
                        "severity": severity, "state": state, "first_seen": first, "last_seen": now,
                        "evidence": clean_evidence(evidence), "explanation": explanation}
                conn.execute("INSERT OR REPLACE INTO findings VALUES(?,?,?)", (fid, now, encode(item)))
                if not old or old["state"] != state:
                    self.event(conn, subject, now, "FINDING_OPEN" if signal else "FINDING_RESOLVED", {"type": typ})
            context = clean_context({**{key: item.get("state") for key, item in (record.get("health") or {}).items() if isinstance(item, dict)},
                                     **(record.get("services") or {}), "probe_success": (record.get("probe") or {}).get("success")})
            old_context = previous.get("context", {})
            if lifecycle:
                self.event(conn, subject, now, "SERVICE_RESTART", lifecycle)
            for kind, keys in (("HEALTH_CHANGE", ("node", "observation", "proxy", "accounting")),
                               ("SERVICE_CHANGE", ("sing_box_active", "accountd_active")), ("PROBE_RESULT", ("probe_success",))):
                detail = {key: context[key] for key in keys if key in context}
                before = {key: old_context[key] for key in keys if key in old_context}
                if detail and detail != before:
                    self.event(conn, subject, now, kind, detail)
            evaluation = {"subject": subject, "evaluated_at": now, "context": context,
                          "checks": {key: "UNKNOWN" if val[0] is None else "ANOMALOUS" if val[0] else "NORMAL" for key, val in checks.items()},
                          "audit": audit_summary(record, cursor, now), "detector_state": detector_state, "baselines": baselines}
            evaluation["user_coverage"] = self.evaluate_users(conn, node, record, now)
            conn.execute("INSERT OR REPLACE INTO evaluations VALUES(?,?,?)", (subject["key"], now, encode(evaluation)))
            self.prune(conn, now)
            conn.commit()
        finally:
            conn.close()

    def evaluate_users(self, conn, node, record, now):
        parent = target(node)
        diagnostic = user_traffic.clean(record.get("user_traffic", {"state": "UNSUPPORTED"}), node["node_id"], record.get("instance_id"))
        snapshot = diagnostic.get("snapshot")
        profiles = {row["user_key"]: row for row in snapshot["users"]} if snapshot else {}
        skipped = 0
        conn.execute("DELETE FROM user_evaluations WHERE at < ?", (now - RETENTION,))
        previous = {}
        for key, at, payload in conn.execute("SELECT subject,at,payload FROM user_evaluations WHERE node_key=? LIMIT ?", (parent["key"], USER_CAP)):
            try:
                item = decode(payload, "user_evaluation")
                if item["subject"]["key"] == key and item["subject"].get("node_key") == parent["key"]:
                    previous[item["subject"]["user_key"]] = (item, at)
            except (ValueError, TypeError, KeyError):
                pass
        for user_key in sorted(set(previous) | set(profiles)):
            profile = profiles.get(user_key)
            old, old_at = previous.get(user_key, ({}, now))
            if old and now <= old["evaluated_at"]:
                continue
            subject = user_target(node, profile) if profile else {**old["subject"], "name": parent["name"]}
            if not old and conn.execute("SELECT count(*) FROM user_evaluations").fetchone()[0] >= USER_CAP:
                # Refuse new baseline admission rather than evicting current users every poll.
                conn.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", ("truncated_user_evaluations", str(now)))
                skipped += 1
                continue
            existing = {}
            for typ in user_traffic.TYPES:
                fid = digest(subject["key"], typ)
                row = conn.execute("SELECT payload FROM findings WHERE id=?", (fid,)).fetchone()
                if row:
                    try:
                        item = decode(row[0], "finding")
                        if item["finding_id"] == fid and item["subject"]["key"] == subject["key"] and item["type"] == typ:
                            existing[typ] = item
                    except (ValueError, TypeError, KeyError):
                        pass
            checks, detector_state, baselines = user_traffic.evaluate(snapshot, profile, old.get("detector_state"), now,
                [key for key, item in existing.items() if item["state"] == "ACTIVE"])
            for typ, (signal, evidence) in checks.items():
                previous_finding = existing.get(typ)
                if signal is None or (not signal and (not previous_finding or previous_finding["state"] == "RESOLVED")):
                    continue
                state = "ACTIVE" if signal else "RESOLVED"
                fid = digest(subject["key"], typ)
                category, severity, explanation = TYPES[typ]
                item = {"finding_id": fid, "type": typ, "category": category, "severity": severity, "subject": subject,
                        "state": state, "first_seen": previous_finding["first_seen"] if previous_finding else now,
                        "last_seen": now, "evidence": clean_evidence(evidence), "explanation": explanation}
                conn.execute("INSERT OR REPLACE INTO findings VALUES(?,?,?)", (fid, now, encode(item)))
                if not previous_finding or previous_finding["state"] != state:
                    self.event(conn, subject, now, "FINDING_OPEN" if signal else "FINDING_RESOLVED", {"type": typ})
            evaluation = {"subject": subject, "evaluated_at": now, "context": {}, "audit": {},
                          "checks": {key: "UNKNOWN" if value[0] is None else "ANOMALOUS" if value[0] else "NORMAL" for key, value in checks.items()},
                          "detector_state": detector_state, "baselines": baselines}
            valid_at = now if detector_state["sampled_at"] is not None and detector_state["sampled_at"] != old.get("detector_state", {}).get("sampled_at") else old_at
            conn.execute("INSERT OR REPLACE INTO user_evaluations VALUES(?,?,?,?)", (subject["key"], parent["key"], valid_at, encode(evaluation)))
        observed = stamp(snapshot.get("observed_at")) if snapshot else None
        sampled = stamp(snapshot.get("sampled_at")) if snapshot else None
        coverage = {"state": "CAPACITY" if skipped else snapshot["state"] if snapshot else diagnostic["state"],
                    "observed_users": len(profiles), "capacity_skipped": skipped,
                    "stored_users": conn.execute("SELECT count(*) FROM user_evaluations WHERE node_key=?", (parent["key"],)).fetchone()[0],
                    "observed_at": observed, "sampled_at": sampled,
                    "fresh": bool(snapshot and snapshot["state"] in ("OK", "PARTIAL") and observed is not None and sampled is not None
                                  and -30 <= now - observed <= 90 and -30 <= now - sampled <= 90
                                  and snapshot["heartbeat_age_seconds"] + max(0, now - observed) <= 90)}
        return clean_user_coverage(coverage)

    @staticmethod
    def event(conn, subject, now, kind, detail):
        eid = digest(subject["key"], now, kind, detail)
        conn.execute("INSERT OR IGNORE INTO timeline VALUES(?,?,?)", (eid, now, encode(
            {"id": eid, "at": now, "kind": kind, "subject": subject, "detail": detail})))

    def read(self, *, nodes=None, state=None, limit=100):
        limit = max(1, min(int(limit), 1000))
        if state not in (None, "ACTIVE", "RESOLVED"):
            raise ValueError("state must be ACTIVE or RESOLVED")
        subjects = {target(node)["key"]: target(node) for node in nodes} if nodes is not None else None
        out = {"schema": "findings/v1", "cache_state": "EMPTY", "findings": [], "evaluations": [], "events": [], "truncated": []}
        if not self.path.is_file():
            return out
        conn = None
        try:
            conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
            conn.execute("PRAGMA query_only=ON")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (1, 2):
                raise ValueError("unsupported findings cache schema")
            out["cache_state"] = "OK"
            tables = [("findings", "finding", "findings", FINDING_CAP),
                                           ("evaluations", "evaluation", "evaluations", SUBJECT_CAP),
                                           ("timeline", "event", "events", EVENT_CAP)]
            if version == 2:
                tables.append(("user_evaluations", "user_evaluation", "evaluations", USER_CAP))
            users_presented = 0
            for table, kind, dest, cap in tables:
                is_evaluation = kind in ("evaluation", "user_evaluation")
                column = "subject" if is_evaluation else "id"
                parent_column = "node_key" if kind == "user_evaluation" else "NULL"
                for key, payload, stored_parent in conn.execute(f"SELECT {column},payload,{parent_column} FROM {table} ORDER BY at DESC,{column} LIMIT ?", (cap,)):
                    try:
                        item = decode(payload, kind)
                        expected = item["subject"]["key"] if is_evaluation else item["finding_id"] if kind == "finding" else item["id"]
                        if key != expected:
                            raise ValueError("cache identity mismatch")
                        if kind == "user_evaluation" and stored_parent != item["subject"]["node_key"]:
                            raise ValueError("cache parent identity mismatch")
                        parent_key = item["subject"].get("node_key", item["subject"]["key"])
                        if subjects is not None and parent_key not in subjects:
                            continue
                        if subjects is not None:
                            item["subject"] = {**item["subject"], "name": subjects[parent_key]["name"]}
                        if kind == "finding" and state and item["state"] != state:
                            continue
                        if kind == "evaluation" or (users_presented < limit if kind == "user_evaluation" else len(out[dest]) < limit):
                            if is_evaluation:
                                item.pop("detector_state", None)
                            out[dest].append(item)
                            if kind == "user_evaluation":
                                users_presented += 1
                    except (ValueError, TypeError, KeyError, OverflowError):
                        out["cache_state"] = "PARTIAL"
            out["truncated"] = [key.removeprefix("truncated_") for key, in conn.execute(
                "SELECT key FROM metadata WHERE key IN ('truncated_findings','truncated_timeline','truncated_evaluations','truncated_user_evaluations') ORDER BY key")]
        except (sqlite3.Error, OSError, ValueError):
            out["cache_state"] = "CACHE_CORRUPT"
        finally:
            if conn is not None:
                conn.close()
        return out


def cursor_snapshot(path, node):
    """Only existing fleet-cache/v4 is read; never migrate/create a Fleet DB."""
    path = Path(path)
    if not path.is_file():
        return {}
    conn = None
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT instance_id,last_export_seq,cursor_kind,last_sync_at,status FROM sync_cursor WHERE node_id=?", (node["node_id"],)).fetchone()
        return dict(row) if row else {}
    except (sqlite3.Error, OSError):
        return {}
    finally:
        if conn is not None:
            conn.close()


def paths(host):
    db = host.fleet_db_path()
    return db.with_name("findings.db"), db.with_name("observation.db")


def record_observation(host, node, record, now):
    store, _ = paths(host)
    Store(store).evaluate(node, record, cursor_snapshot(host.fleet_db_path(), node), now)


def refresh(host, nodes, now=None):
    """Explicit local analysis; the UI/CLI display path never calls this writer."""
    now = time.time() if now is None else now
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("vcl_findings_observation_store", Path(__file__).with_name("store.py"))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    _, cache = paths(host)
    doc = module.Store(cache).read(nodes, now, include_audit=True)
    for node, record in zip(nodes, doc["nodes"]):
        record_observation(host, node, record, now)
    return doc["cache_state"]


def cached(host, nodes, *, state=None, limit=100):
    return Store(paths(host)[0]).read(nodes=nodes, state=state, limit=limit)


def timeline(host, nodes, *, limit=100, include_fleet=True):
    """Merge bounded local journal data without invoking its lock-file writer."""
    doc = cached(host, nodes, limit=limit)
    rows = list(doc["events"])
    path = host.operation_journal_path(create=False)
    names = {node["name"] for node in nodes}
    try:
        if path.is_file():
            with path.open(encoding="utf-8") as stream:
                raw = stream.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                doc["cache_state"] = "PARTIAL"
                lines = []
            else:
                lines = raw.splitlines()[-5000:]
            for line in lines:
                try:
                    if len(line) > 8192:
                        raise ValueError("oversize operation")
                    item = json.loads(line)
                    at = stamp(item.get("time") or item.get("finished_at") or item.get("started_at"))
                    operation = item.get("operation")
                    # Known journal verbs only; injected argv/text is never echoed.
                    if at is None or operation not in ("sync", "sync_full", "reseed", "probe", "verify", "node_upgrade", "provision", "provision_legacy_seed", "adopt", "replace", "retire", "backup", "restore", "user_add", "user_import", "user_rotate", "user_disable", "refresh_users", "audit_archive_restore"):
                        continue
                    name = item.get("target")
                    if name and name not in names and not (include_fleet and operation.startswith("user_")):
                        continue
                    if not name and not include_fleet:
                        continue
                    state = item.get("state")
                    if state not in ("SUCCESS", "PARTIAL", "FAILED", "ERROR", "OK", "UNSUPPORTED", "AUTH_FAILED", "TIMEOUT"):
                        continue
                    detail = {"operation": operation, "state": state}
                    if type(item.get("exit_code")) is int and -255 <= item["exit_code"] <= 255:
                        detail["exit_code"] = item["exit_code"]
                    subject = next((target(node) for node in nodes if node["name"] == name), None)
                    rows.append({"id": digest(item.get("operation_id") if isinstance(item.get("operation_id"), str) else line),
                                 "at": at, "kind": "OPERATION", "subject": subject, "detail": detail})
                except (ValueError, TypeError, AttributeError, RecursionError):
                    doc["cache_state"] = "PARTIAL"
    except (OSError, UnicodeError):
        doc["cache_state"] = "PARTIAL"
    # Stable ordering even when observations/journal entries share the same timestamp.
    rows.sort(key=lambda item: (-item["at"], item["id"]))
    return {"schema": "timeline/v1", "cache_state": doc["cache_state"],
            "events": rows[:max(1, min(int(limit), 1000))], "truncated": doc["truncated"]}
