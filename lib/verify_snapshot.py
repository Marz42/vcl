"""Read-only verify/v2. Explicit checks never infer data-plane success from listeners."""
from __future__ import annotations
import importlib.util
import ipaddress
import json
import re
import sqlite3
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("vcl_verify_inspect", Path(__file__).with_name("inspect_snapshot.py"))
inspect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect)
CHECKS = ("identity", "configuration", "integrity", "permissions", "services", "listeners", "accounting", "data_plane")
STATES = ("PASS", "FAIL", "UNKNOWN", "UNSUPPORTED")
REASONS = ("OK", "MISSING", "INVALID", "MISMATCH", "PERMISSION", "INACTIVE", "EXPOSED", "STALE", "TIMEOUT", "UNSUPPORTED", "NO_PROBE", "PROBE_FAILED")


def check(state="UNKNOWN", reason="MISSING", count=0):
    return {"state": state, "reason": reason, "checked_count": count}


def overall(checks):
    states = {v["state"] for v in checks.values()}
    return "FAIL" if "FAIL" in states else "UNKNOWN" if "UNKNOWN" in states or "UNSUPPORTED" in states else "PASS"


def contract():
    obj = inspect.object_schema
    item = obj({"state": {"enum": list(STATES)}, "reason": {"enum": list(REASONS)}, "checked_count": inspect.integer_schema(65536, False)})
    schema = obj({"schema": {"const": "verify/v2"}, "node_id": inspect.text_schema(inspect.UUID), "instance_id": inspect.text_schema(inspect.UUID),
        "observed_at": {"type": "string", "format": "date-time"}, "state": {"enum": list(STATES)},
        "checks": obj({k: item for k in CHECKS}), "data_plane_source": {"enum": ["NONE", "EXPLICIT_CONTROLLER_PROBE"]}})
    schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "verify/v2 explicit read-only checks"})
    scenarios = []
    for state, members in (("FAIL", ("FAIL",)), ("UNKNOWN", ("UNKNOWN", "UNSUPPORTED"))):
        scenarios.append({"properties": {"state": {"const": state}, "checks": {"anyOf": [
            {"properties": {k: {"properties": {"state": {"enum": list(members)}}}}} for k in CHECKS]}}})
    scenarios.append({"properties": {"state": {"const": "PASS"}, "checks": {"properties": {
        k: {"properties": {"state": {"const": "PASS"}}} for k in CHECKS}}}})
    schema["allOf"] = [{"anyOf": scenarios},
        {"if": {"properties": {"data_plane_source": {"const": "NONE"}}}, "then": {"properties": {
            "checks": {"properties": {"data_plane": {"properties": {"state": {"const": "UNKNOWN"}}}}}}}}]
    for k in CHECKS:
        schema["allOf"].append({"if": {"properties": {"checks": {"properties": {k: {"properties": {"state": {"const": "FAIL"}}}}}}},
                               "then": {"properties": {"state": {"const": "FAIL"}}}})
    for rule in schema["properties"]["checks"]["properties"].values():
        rule["allOf"] = [{"if": {"properties": {"state": {"const": "PASS"}}}, "then": {"properties": {"reason": {"const": "OK"}}},
                          "else": {"properties": {"reason": {"enum": [r for r in REASONS if r != "OK"]}}}}]
    return schema


def validate(doc):
    try:
        if set(doc) != {"schema", "node_id", "instance_id", "observed_at", "state", "checks", "data_plane_source"} or doc["schema"] != "verify/v2":
            raise ValueError
        for k in ("node_id", "instance_id"):
            if doc[k] is not None and (not isinstance(doc[k], str) or not re.fullmatch(inspect.UUID, doc[k])):
                raise ValueError
        if not isinstance(doc["observed_at"], str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)", doc["observed_at"]) or datetime.fromisoformat(doc["observed_at"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
        if set(doc["checks"]) != set(CHECKS) or doc["state"] != overall(doc["checks"]):
            raise ValueError
        for row in doc["checks"].values():
            if set(row) != {"state", "reason", "checked_count"} or row["state"] not in STATES or row["reason"] not in REASONS or type(row["checked_count"]) is not int or not 0 <= row["checked_count"] <= 65536 or (row["state"] == "PASS") != (row["reason"] == "OK"):
                raise ValueError
        if doc["checks"]["identity"]["state"] == "PASS" and (doc["node_id"] is None or doc["instance_id"] is None or doc["node_id"] == doc["instance_id"]):
            raise ValueError
        if doc["data_plane_source"] not in ("NONE", "EXPLICIT_CONTROLLER_PROBE") or doc["data_plane_source"] == "NONE" and doc["checks"]["data_plane"]["state"] != "UNKNOWN":
            raise ValueError
        if len(json.dumps(doc, allow_nan=False).encode()) > 8192:
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        return ["invalid verify/v2"]
    return []


def read_json(reader, path, limit=inspect.MAX_CONFIG):
    state, reason, text = reader.read(path, limit, no_symlink=True)
    if text is None:
        return None
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError
            out[k] = v
        return out
    try:
        return json.loads(text, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, RecursionError):
        return None


def desired(settings, state, registry):
    # Mirrors the canonical accounting renderer, without writing or exposing credentials.
    node = state.get("node", state)
    users = []
    for u in registry["users"]:
        if u.get("enabled") is not True:
            continue
        creds = [c for c in u["credentials"] if c.get("status") == "active"]
        if len(creds) != 1 or not re.fullmatch(inspect.UUID, creds[0]["uuid"]) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", u["tag"]):
            raise ValueError
        users.append({"name": u["tag"], "uuid": creds[0]["uuid"], "flow": "xtls-rprx-vision"})
    if not users or len({u["name"] for u in users}) != len(users):
        raise ValueError
    port, clash_port = int(settings["port"]), int(settings["clash_api_port"])
    if not 1 <= port <= 65535 or not 1 <= clash_port <= 65535 or port != node["port"] or settings["reality_server_name"] != node["reality_server_name"]:
        raise ValueError
    host = settings["reality_server_name"]
    inbound = {"type": "vless", "tag": "vless-reality-in", "listen": settings["listen"], "listen_port": port, "users": users,
               "tls": {"enabled": True, "server_name": host, "reality": {"enabled": True, "handshake": {"server": host, "server_port": 443},
                    "private_key": node["reality_private_key"], "short_id": node["reality_short_id"]}}}
    sniff = settings.get("sniff", "true").lower() in ("1", "true", "yes", "on")
    rules = [{"inbound": ["vless-reality-in"], "action": "sniff"}] if sniff else []
    rules += [{"auth_user": [u["name"]], "action": "route", "outbound": "acct/" + u["name"]} for u in users]
    return {"log": {"level": "info", "timestamp": True}, "inbounds": [inbound],
            "outbounds": [{"type": "direct", "tag": "direct"}] + [{"type": "direct", "tag": "acct/" + u["name"]} for u in users],
            "route": {"rules": rules, "final": "direct"}, "experimental": {"clash_api": {"external_controller": "127.0.0.1:" + str(clash_port), "secret": settings["clash_api_secret"]}}}


def accounting(reader, path, instance_id, node_id):
    conn = None
    try:
        if path.is_symlink() or not path.is_file():
            return check()
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=.1)
        conn.execute("PRAGMA query_only=ON")
        deadline = min(reader.deadline, time.monotonic() + .25)
        steps = [0]
        def bounded():
            steps[0] += 1
            return int(steps[0] > 2000 or time.monotonic() >= deadline)
        conn.set_progress_handler(bounded, 1000)
        conn.execute("BEGIN")
        meta = dict(conn.execute("SELECT key,value FROM meta WHERE key IN ('schema_version','heartbeat_at','last_success_at') LIMIT 3"))
        required = {"connections": {"event_id", "connection_id", "generation", "user_id", "node_id", "instance_id", "user_tag",
                    "started_at", "last_seen_at", "closed_at", "destination_host", "destination_ip", "destination_port", "network", "upload_bytes", "download_bytes", "export_seq"},
                    "poll_baseline": {"connection_id", "generation", "last_upload_counter", "last_download_counter", "accounted_upload", "accounted_download", "last_seen_at"},
                    "daily_usage": {"date", "user_id", "user_tag", "destination_host", "upload_bytes", "download_bytes", "connection_count"}}
        if meta.get("schema_version") != "4" or any(not columns <= {r[1] for r in conn.execute(f"PRAGMA table_info({table})")} for table, columns in required.items()):
            return check("FAIL", "INVALID", 1)
        if conn.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
            return check("FAIL", "INVALID", 1)
        for key in ("heartbeat_at", "last_success_at"):
            try:
                value = meta.get(key)
                if not isinstance(value, str):
                    raise ValueError
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if not dt.tzinfo:
                    raise ValueError
                age = time.time() - dt.timestamp()
            except (OSError, ValueError, TypeError, OverflowError):
                return check("UNKNOWN", "INVALID", 1)
            if age < -30:
                return check("UNKNOWN", "INVALID", 1)
            if age > 90:
                return check("FAIL", "STALE", 1)
        return check("PASS", "OK", 4)
    except sqlite3.Error as exc:
        code = getattr(exc, "sqlite_errorcode", 0) & 0xff
        return check("FAIL", "INVALID", 1) if code in (1, 11, 26) else check("UNKNOWN", "TIMEOUT")
    except (OSError, ValueError, TypeError, KeyError):
        return check("UNKNOWN", "INVALID")
    finally:
        if conn:
            conn.close()


def build_snapshot(*, state_dir=Path("/etc/vincula"), config_path=Path("/etc/sing-box/config.json"), binary_path=Path("/usr/local/bin/sing-box"),
                   lib_dir=Path("/usr/local/lib/vincula"), accounting_db=Path("/var/lib/vincula/accounting.db"), root=Path("/"), version="0.5.3", runner=None):
    reader = inspect.Reader(8, runner)
    snapshot = inspect.build_snapshot(state_dir=state_dir, config_path=config_path, binary_path=binary_path, lib_dir=lib_dir, root=root, version=version, reader=reader)
    checks = {k: check() for k in CHECKS}
    node_id, instance_id = snapshot["node_id"], snapshot["instance_id"]
    state = read_json(reader, state_dir / "state.json")
    _, _, text = reader.read(state_dir / "config.toml", no_symlink=True)
    settings = inspect.pairs(text or "")
    settings = {k.strip(): v.strip().strip('"') for k, v in settings.items()}
    actual, users = read_json(reader, config_path), read_json(reader, state_dir / "users.json")
    if state is not None and text is not None:
        node = state.get("node", state) if isinstance(state, dict) else {}
        identity_ok = node_id is not None and instance_id is not None and node_id != instance_id and node.get("node_id") == node_id and node.get("instance_id") == instance_id
        checks["identity"] = check("PASS" if identity_ok else "FAIL", "OK" if identity_ok else "MISMATCH", 2)
    if actual is not None and state is not None and users is not None and text is not None:
        try:
            expected = desired(settings, state, users)
            if inspect.config_hash(json.dumps(actual)) is None:
                raise ValueError
            matched = actual == expected
            checks["configuration"] = check("PASS" if matched else "FAIL", "OK" if matched else "MISMATCH", 1)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            checks["configuration"] = check("FAIL", "INVALID", 1)
    binary = next((r for r in snapshot["fingerprints"]["items"] if r["name"] == "binary"), {})
    _, _, lock = reader.read(lib_dir / "sing-box.lock", no_symlink=True)
    expected_sha = inspect.pairs(lock or "").get("binary_sha256")
    if binary.get("state") == "OK" and isinstance(expected_sha, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        matched = binary["sha256"] == expected_sha
        checks["integrity"] = check("PASS" if matched else "FAIL", "OK" if matched else "MISMATCH", 1)
    if sys.platform == "linux":
        try:
            paths = (state_dir / "config.toml", state_dir / "state.json", state_dir / "users.json", config_path)
            safe, complete = True, True
            for path in paths:
                try:
                    info = path.lstat()
                    safe &= stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o027
                    if info.st_mode & 0o040:
                        import grp
                        expected_group = "sing-box" if path == config_path else "root"
                        try:
                            safe &= info.st_gid == grp.getgrnam(expected_group).gr_gid
                        except KeyError:
                            complete = False
                except OSError:
                    complete = False
            for row in snapshot["fingerprints"]["items"]:
                if row["state"] != "OK":
                    complete = False
                    continue
                safe &= row["uid"] == 0 and not row["mode"] & 0o022
            checks["permissions"] = check("FAIL", "PERMISSION", 20) if not safe else check("PASS", "OK", 20) if complete else check()
        except (OSError, ValueError):
            pass
    else:
        checks["permissions"] = check("UNSUPPORTED", "UNSUPPORTED")
    services = snapshot["services"]
    if services["state"] == "OK" and len(services["items"]) == 2:
        safe = all(r["active"] is True and r["enabled"] is True and r["user"] == ("sing-box" if r["name"] == "sing-box.service" else "vincula-accountd") and r["group"] == r["user"] for r in services["items"])
        checks["services"] = check("PASS" if safe else "FAIL", "OK" if safe else "INACTIVE", 2)
    listeners = snapshot["listeners"]
    if actual is not None and listeners["state"] == "OK" and not listeners["truncated"]:
        try:
            bind = actual["experimental"]["clash_api"]["external_controller"]
            address, port = bind.rsplit(":", 1)
            api_address = ipaddress.ip_address(address.strip("[]"))
            loopback = api_address.is_loopback
            api_port = int(port)
            exposed = not loopback or any(r["protocol"] == "TCP" and r["port"] == api_port and r["scope"] != "LOOPBACK" for r in listeners["items"])
            wanted = actual["inbounds"][0]
            wanted_address = ipaddress.ip_address(wanted["listen"])
            listening = any(r["protocol"] == "TCP" and r["port"] == wanted["listen_port"] and r["address"] is not None and ipaddress.ip_address(r["address"]) == wanted_address for r in listeners["items"])
            api_listening = any(r["protocol"] == "TCP" and r["port"] == api_port and r["address"] is not None and ipaddress.ip_address(r["address"]) == api_address for r in listeners["items"])
            passed = not exposed and listening and api_listening
            checks["listeners"] = check("PASS" if passed else "FAIL", "OK" if passed else "EXPOSED" if exposed else "MISSING", 2)
        except (ValueError, KeyError, TypeError, IndexError):
            checks["listeners"] = check("UNKNOWN", "INVALID")
    checks["accounting"] = accounting(reader, accounting_db, instance_id, node_id)
    if checks["services"]["state"] == "FAIL" and snapshot["services"]["state"] == "OK" and any(r["name"] == "vincula-accountd.service" and r["active"] is False for r in snapshot["services"]["items"]):
        checks["accounting"] = check("FAIL", "INACTIVE", 1)
    checks["data_plane"] = check("UNKNOWN", "NO_PROBE")
    return {"schema": "verify/v2", "node_id": node_id, "instance_id": instance_id, "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "state": overall(checks), "checks": checks, "data_plane_source": "NONE"}


def main(argv):
    if len(argv) != 7:
        return 2
    doc = build_snapshot(state_dir=Path(argv[1]), config_path=Path(argv[2]), binary_path=Path(argv[3]), lib_dir=Path(argv[4]), version=argv[5], accounting_db=Path(argv[6]))
    if validate(doc):
        return 2
    print(json.dumps(doc, separators=(",", ":"), allow_nan=False))
    return 1 if doc["state"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
