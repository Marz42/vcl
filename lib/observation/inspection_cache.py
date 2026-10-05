"""Workstation-local inspection and explicit baselines. Reading never creates files."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("vcl_cache_inspection", Path(__file__).with_name("inspection.py"))
inspection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspection)
contract = inspection.contract
CAP, EVENT_CAP, TTL, FRESH = 1024, 10000, 7 * 86400, 600
COMPONENTS = ("listeners", "services", "versions", "config", "units", "runtime", "binary")
REASONS = ("NONE", "EMPTY", "ERROR", "AUTH_FAILED", "UNSUPPORTED", "TIMEOUT", "STALE", "CLOCK_SKEW",
           "REPLAYED", "IDENTITY", "ENDPOINT", "COVERAGE", "NO_BASELINE", "CACHE_CORRUPT", "CAPACITY")
DDL = """
CREATE TABLE latest(node TEXT PRIMARY KEY, at REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE baselines(node TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE events(id TEXT PRIMARY KEY, at REAL NOT NULL, node TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX events_at ON events(at);
"""


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def subject_key(node_id):
    # Same stable subject encoding as findings.digest(node_id).
    return hashlib.sha256(json.dumps((node_id,), separators=(",", ":")).encode()).hexdigest()


def stamp(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp() if dt.tzinfo else None
    except (ValueError, TypeError, AttributeError, OSError, OverflowError):
        return None


def valid_now(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 253402300799


def endpoint(node):
    # Includes observe reference identity, never its contents or private key path.
    return sha({k: node.get(k) for k in ("node_id", "ssh_host", "ssh_port", "ssh_user", "observe_ssh_user", "observe_credential_ref")})


def projection(snapshot):
    """Independent coverage; partial observation cannot prove equality."""
    out = dict.fromkeys(COMPONENTS)
    for name in ("listeners", "services", "versions"):
        section = snapshot[name]
        if section["state"] != "OK" or section.get("truncated"):
            continue
        if name == "versions":
            if all(section[k] is not None for k in ("vcl", "installed_vcl", "sing_box")) and section["sing_box_source"] == "INSTALLED_MANIFEST":
                out[name] = {k: section[k] for k in ("vcl", "installed_vcl", "sing_box")}
        elif name == "services":
            rows = section["items"]
            if len(rows) == 2 and {r["name"] for r in rows} == set(contract.SERVICES) and all(
                    r["state"] == "OK" and all(r[k] is not None for k in ("active", "enabled", "user", "group", "limit_nofile_soft", "limit_nofile_hard")) for r in rows):
                out[name] = sorted(({k: r[k] for k in ("name", "active", "enabled", "user", "group", "limit_nofile_soft", "limit_nofile_hard")} for r in rows), key=lambda r: r["name"])
        else:
            out[name] = sorted(section["items"], key=encoded)
    section = snapshot["fingerprints"]
    rows = section["items"]
    names = [r["name"] for r in rows]
    if section.get("truncated") or len(names) != len(set(names)):
        return out
    by_name = {r["name"]: r for r in rows}
    for component, wanted in (("config", ("config_nonsecret",)), ("units", tuple(contract.UNITS)),
                               ("runtime", tuple(contract.ARTIFACTS)), ("binary", ("binary",))):
        if all(n in by_name and by_name[n]["state"] == "OK" for n in wanted):
            out[component] = [{k: by_name[n][k] for k in ("name", "sha256", "mode", "uid", "gid")} for n in sorted(wanted)]
    return out


def decode(raw, kind, node_id):
    if not isinstance(raw, str) or len(raw.encode()) > contract.MAX_BYTES + 2048:
        raise ValueError("invalid inspection cache")
    row = json.loads(raw)
    fields = {"endpoint", "snapshot", "snapshot_sha256"} | ({"at", "reason"} if kind == "latest" else {"schema", "source", "accepted_at", "baseline_sha256"})
    if not isinstance(row, dict) or set(row) != fields or not re.fullmatch(r"[0-9a-f]{64}", row["endpoint"]):
        raise ValueError("invalid inspection cache")
    snapshot = row["snapshot"]
    if snapshot is not None and (contract.validate(snapshot) or snapshot["node_id"] != node_id or snapshot["instance_id"] is None or sha(snapshot) != row["snapshot_sha256"]):
        raise ValueError("invalid inspection snapshot")
    if snapshot is None and row["snapshot_sha256"] is not None:
        raise ValueError("invalid inspection hash")
    if kind == "latest":
        if not valid_now(row["at"]) or row["reason"] not in REASONS or row["reason"] == "NONE" and snapshot is None:
            raise ValueError("invalid inspection attempt")
    elif (row["schema"] != "baseline/v1" or row["source"] != "LOCAL_ACCEPTED" or not valid_now(row["accepted_at"])
          or snapshot is None or any(v is None for v in projection(snapshot).values())
          or row["baseline_sha256"] != sha({k: v for k, v in row.items() if k != "baseline_sha256"})):
        raise ValueError("invalid baseline")
    return row


def empty(node, reason="EMPTY"):
    return {"name": node["name"], "node_id": node["node_id"], "instance_id": None, "state": "UNKNOWN", "reason": reason,
            "observed_at": None, "snapshot_sha256": None, "baseline": None, "snapshot": None,
            "drift": {"state": "UNKNOWN", "checks": {k: {"state": "UNKNOWN", "changed_count": 0} for k in COMPONENTS}}}


def view(node, latest, baseline, now, identity, detail=False):
    out = empty(node)
    reason = latest["reason"] if latest else "EMPTY"
    snapshot = latest["snapshot"] if latest else None
    if baseline:
        out["baseline"] = {k: baseline[k] for k in ("source", "accepted_at", "baseline_sha256", "snapshot_sha256")}
        out["baseline"].update(instance_id=baseline["snapshot"]["instance_id"], observed_at=baseline["snapshot"]["observed_at"])
    if snapshot:
        out.update(instance_id=snapshot["instance_id"], observed_at=snapshot["observed_at"], snapshot_sha256=latest["snapshot_sha256"])
        if detail:
            out["snapshot"] = snapshot
        observed = stamp(snapshot["observed_at"])
        if latest["endpoint"] != endpoint(node):
            reason = "ENDPOINT"
        elif identity != snapshot["instance_id"]:
            reason = "IDENTITY"
        elif now - observed < -30 or latest["at"] > now + 30:
            reason = "CLOCK_SKEW"
        elif now - observed > FRESH or now - latest["at"] > FRESH:
            reason = "STALE"
    if reason == "NONE":
        out["state"] = "OK" if snapshot["state"] == "OK" else "PARTIAL"
        if not baseline:
            reason = "NO_BASELINE"
        elif baseline["endpoint"] != latest["endpoint"] or baseline["snapshot"]["instance_id"] != identity:
            reason = "IDENTITY"
        else:
            desired, actual = projection(baseline["snapshot"]), projection(snapshot)
            checks = {}
            for key in COMPONENTS:
                a, b = desired[key], actual[key]
                state = "UNKNOWN" if b is None else "MATCH" if a == b else "DRIFT"
                count = 0 if state != "DRIFT" else len(set(map(encoded, a)) ^ set(map(encoded, b))) if isinstance(a, list) else sum(a[k] != b[k] for k in a)
                checks[key] = {"state": state, "changed_count": count}
            states = {c["state"] for c in checks.values()}
            out["drift"] = {"state": "DRIFT" if "DRIFT" in states else "UNKNOWN" if "UNKNOWN" in states else "MATCH", "checks": checks}
            if "UNKNOWN" in states:
                reason = "COVERAGE"
    out["reason"] = reason
    return out


class Store:
    def __init__(self, path):
        self.path = Path(path)

    def connect(self, write=False):
        if not write and not self.path.is_file():
            return None
        if self.path.is_symlink() or self.path.exists() and self.path.stat().st_size > 128 * 1024 * 1024:
            raise ValueError("invalid inspection database")
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        conn = sqlite3.connect(self.path if write else self.path.resolve().as_uri() + "?mode=ro", uri=not write, timeout=.1)
        try:
            conn.execute("PRAGMA trusted_schema=OFF")
            if write:
                conn.execute("PRAGMA journal_mode=DELETE")
                conn.execute(f"PRAGMA max_page_count={128 * 1024 * 1024 // conn.execute('PRAGMA page_size').fetchone()[0]}")
            else:
                conn.execute("PRAGMA query_only=ON")
            deadline, steps = time.monotonic() + 1, [0]
            def budget():
                steps[0] += 1
                return int(steps[0] > 2000 or time.monotonic() > deadline)
            conn.set_progress_handler(budget, 1000)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if write and version == 0:
                conn.executescript("BEGIN IMMEDIATE;" + DDL + "PRAGMA user_version=1;COMMIT;")
            elif version != 1:
                raise ValueError("unsupported inspection database")
            return conn
        except BaseException:
            conn.close()
            raise

    @staticmethod
    def row(conn, table, node):
        row = conn.execute(f"SELECT CASE WHEN length(CAST(payload AS BLOB)) <= ? THEN payload ELSE '' END FROM {table} WHERE node=?",
                           (contract.MAX_BYTES + 2048, node["node_id"])).fetchone()
        return decode(row[0], "latest" if table == "latest" else "baseline", node["node_id"]) if row else None

    def record(self, node, result, now, instance_id):
        if not valid_now(now):
            raise ValueError("invalid inspection time")
        value = inspection.clean(result, node["node_id"], instance_id)
        snapshot = value.get("snapshot")
        reason = "NONE" if snapshot else value["state"]
        if snapshot:
            age = now - stamp(snapshot["observed_at"])
            reason = "CLOCK_SKEW" if age < -30 else "STALE" if age > FRESH else "NONE"
        conn = self.connect(True)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM latest WHERE at < ?", (now - TTL,))
            try:
                old = self.row(conn, "latest", node)
            except (ValueError, TypeError, KeyError, RecursionError):
                old = None
            if old and now < old["at"]:
                raise ValueError("REPLAYED")
            if not old and conn.execute("SELECT count(*) FROM latest").fetchone()[0] >= CAP:
                raise ValueError("CAPACITY")
            if snapshot and reason == "NONE" and old and old["snapshot"] and old["endpoint"] == endpoint(node) and old["snapshot"]["instance_id"] == instance_id and stamp(snapshot["observed_at"]) <= stamp(old["snapshot"]["observed_at"]):
                reason = "REPLAYED"
            if reason != "NONE":
                snapshot = old["snapshot"] if old and old["endpoint"] == endpoint(node) else None
            row = {"endpoint": endpoint(node), "snapshot": snapshot, "snapshot_sha256": sha(snapshot) if snapshot else None, "at": now, "reason": reason}
            conn.execute("INSERT OR REPLACE INTO latest VALUES(?,?,?)", (node["node_id"], now, encoded(row)))
            conn.commit()
        finally:
            conn.close()

    def read(self, nodes, now, identities=None, detail=False):
        if len(nodes) > CAP or not valid_now(now):
            raise ValueError("invalid inspection view")
        out = {"schema": "inspect-cache/v1", "cache_state": "EMPTY", "nodes": [], "truncated": False}
        conn = None
        try:
            conn = self.connect()
            if conn:
                conn.execute("BEGIN")
                out["cache_state"] = "OK"
            for node in nodes:
                try:
                    latest = self.row(conn, "latest", node) if conn else None
                    baseline = self.row(conn, "baselines", node) if conn else None
                    out["nodes"].append(view(node, latest, baseline, now, (identities or {}).get(node["node_id"]), detail))
                except (ValueError, TypeError, KeyError, RecursionError):
                    out["cache_state"] = "PARTIAL"
                    out["nodes"].append(empty(node, "CACHE_CORRUPT"))
        except (sqlite3.Error, OSError, ValueError):
            out.update(cache_state="CACHE_CORRUPT", nodes=[empty(n, "CACHE_CORRUPT") for n in nodes])
        finally:
            if conn:
                conn.close()
        return out

    def accept(self, node, expected_sha, now, instance_id, clear=False):
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha or "") or not valid_now(now):
            raise ValueError("baseline requires a valid expected SHA and time")
        # No creation on a failed acceptance.
        if not self.path.is_file():
            raise ValueError("EMPTY")
        conn = self.connect(True)
        try:
            conn.execute("BEGIN IMMEDIATE")
            latest, old = self.row(conn, "latest", node), self.row(conn, "baselines", node)
            if clear:
                if not old or old["baseline_sha256"] != expected_sha:
                    raise ValueError("BASELINE_CHANGED")
                baseline = old
                conn.execute("DELETE FROM baselines WHERE node=?", (node["node_id"],))
            else:
                current = view(node, latest, None, now, instance_id)
                if current["reason"] != "NO_BASELINE" or current["snapshot_sha256"] != expected_sha:
                    raise ValueError("SNAPSHOT_CHANGED_OR_UNAVAILABLE")
                if any(v is None for v in projection(latest["snapshot"]).values()):
                    raise ValueError("COVERAGE")
                if not old and conn.execute("SELECT count(*) FROM baselines").fetchone()[0] >= CAP:
                    raise ValueError("CAPACITY")
                baseline = {"schema": "baseline/v1", "source": "LOCAL_ACCEPTED", "endpoint": latest["endpoint"],
                            "snapshot": latest["snapshot"], "snapshot_sha256": expected_sha, "accepted_at": now}
                baseline["baseline_sha256"] = sha(baseline)
                conn.execute("INSERT OR REPLACE INTO baselines VALUES(?,?)", (node["node_id"], encoded(baseline)))
            kind = "BASELINE_CLEARED" if clear else "BASELINE_ACCEPTED"
            event = {"id": sha([node["node_id"], kind, now, baseline["baseline_sha256"]]), "at": now, "kind": kind,
                     "subject": {"kind": "node", "name": node["name"], "key": subject_key(node["node_id"])},
                     "detail": {"source": "LOCAL_ACCEPTED", "snapshot_sha256": baseline["snapshot_sha256"], "baseline_sha256": baseline["baseline_sha256"]}}
            conn.execute("INSERT INTO events VALUES(?,?,?,?)", (event["id"], now, node["node_id"], encoded(event)))
            conn.execute("DELETE FROM events WHERE at < ?", (now - 90 * 86400,))
            conn.execute("DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY at DESC,id LIMIT -1 OFFSET ?)", (EVENT_CAP,))
            conn.commit()
            return event
        finally:
            conn.close()

    def events(self, nodes, limit):
        conn, rows, state = None, [], "EMPTY"
        try:
            conn = self.connect()
            if conn:
                state = "OK"
                allowed = {subject_key(n["node_id"]): n for n in nodes}
                for raw, in conn.execute("SELECT CASE WHEN length(payload)<2048 THEN payload ELSE '' END FROM events ORDER BY at DESC,id LIMIT ?", (EVENT_CAP,)):
                    try:
                        row = json.loads(raw)
                        if set(row) != {"id", "at", "kind", "subject", "detail"} or row["kind"] not in ("BASELINE_ACCEPTED", "BASELINE_CLEARED") or not valid_now(row["at"]):
                            raise ValueError
                        s, d = row["subject"], row["detail"]
                        if set(s) != {"kind", "name", "key"} or s["kind"] != "node" or set(d) != {"source", "snapshot_sha256", "baseline_sha256"} or d["source"] != "LOCAL_ACCEPTED" or any(not re.fullmatch(r"[0-9a-f]{64}", v) for v in (row["id"], s["key"], d["snapshot_sha256"], d["baseline_sha256"])):
                            raise ValueError
                        if s["key"] in allowed:
                            row["subject"]["name"] = allowed[s["key"]]["name"]
                            rows.append(row)
                    except (ValueError, TypeError, KeyError, RecursionError):
                        state = "PARTIAL"
        except (sqlite3.Error, OSError, ValueError):
            state = "CACHE_CORRUPT"
        finally:
            if conn:
                conn.close()
        return rows[:limit], state


def path(host):
    return host.fleet_db_path().with_name("inspection.db")


def identities(host, nodes, now):
    spec = importlib.util.spec_from_file_location("vcl_inspection_health", Path(__file__).with_name("store.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    doc = module.Store(host.fleet_db_path().with_name("observation.db")).read(nodes, now)
    return {r["node_id"]: r["instance_id"] for r in doc["nodes"] if r["observation_state"] == "OK" and r["sampled_at"] is not None and -30 <= now - stamp(r["sampled_at"]) <= 90 and r["observed_at"] is not None and -30 <= now - stamp(r["observed_at"]) <= 90}


def cached(host, nodes, detail=False, now=None):
    now = time.time() if now is None else now
    return Store(path(host)).read(nodes, now, identities(host, nodes, now), detail)


def baseline(host, node, expected_sha, clear=False):
    now = time.time()
    if clear:
        return Store(path(host)).accept(node, expected_sha, now, None, True)
    # Hold the current telemetry identity read transaction through the inspection
    # CAS commit. A concurrent replacement cannot commit a new identity midway.
    health_path = host.fleet_db_path().with_name("observation.db")
    if not health_path.is_file():
        raise ValueError("IDENTITY")
    conn = sqlite3.connect(health_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=.1)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        conn.execute("SELECT node_id FROM health_latest WHERE node_id=?", (node["node_id"],)).fetchone()
        return Store(path(host)).accept(node, expected_sha, now, identities(host, [node], now).get(node["node_id"]))
    finally:
        conn.close()
