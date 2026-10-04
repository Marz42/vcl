"""Bounded read-only Node inspection. No raw config, argv or error text escapes."""
from __future__ import annotations

import hashlib
import errno
import ipaddress
import itertools
import json
import os
import re
import select
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STATES = ("OK", "PARTIAL", "UNKNOWN", "UNSUPPORTED", "UNREADABLE")
REASONS = ("NONE", "MISSING", "MISSING_TOOL", "PERMISSION", "INVALID", "LIMIT", "TIMEOUT", "COMMAND_FAILED", "SYMLINK", "UNSUPPORTED_OS")
MAX_BYTES, MAX_FILE, MAX_ITEMS = 65536, 1024 * 1024, 64
MAX_CONFIG = 4 * 1024 * 1024
UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
VERSION = r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?"
WORD = r"[A-Za-z0-9_.:+-]{1,96}"
INTERFACE = r"[A-Za-z0-9_.:-]{1,32}"
SERVICES = ("sing-box.service", "vincula-accountd.service")
SYSCTLS = {
    "net.ipv4.tcp_congestion_control": ("word", None),
    "net.core.default_qdisc": ("word", None),
    "net.ipv4.ip_forward": ("integer", 1),
    "net.ipv6.conf.all.forwarding": ("integer", 1),
    "net.ipv4.tcp_mtu_probing": ("integer", 2),
    "net.core.somaxconn": ("integer", 2**31 - 1),
}
ARTIFACTS = {"helper": "vincula", "common": "vincula-common.sh", "accountd": "vincula-accountd.py",
             "accountd_runtime": "accountd_runtime.py", "observer": "observer.py", "telemetry": "telemetry_snapshot.py",
             "inspect": "inspect_snapshot.py", "stats": "vincula-stats.py", "audit": "vincula-audit.py", "backup": "vincula-backup.py"}
UNITS = {"sing_box_unit": "sing-box.service", "accountd_unit": "vincula-accountd.service",
         "observer_socket": "vincula-observer.socket", "observer_unit": "vincula-observer@.service"}


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def text_schema(pattern, nullable=True):
    return {"type": ["string", "null"] if nullable else "string", "pattern": "^" + pattern + "$"}


def integer_schema(maximum=2**63 - 1, nullable=True, minimum=0):
    return {"type": ["integer", "null"] if nullable else "integer", "minimum": minimum, "maximum": maximum}


def section_schema(properties, array=False):
    return object_schema({"state": {"enum": list(STATES)}, "reason": {"enum": list(REASONS)},
                          **({"truncated": {"type": "boolean"}} if array else {}), **properties})


def array_schema(item):
    return {"type": "array", "items": item, "maxItems": MAX_ITEMS}


def contract():
    boolean = {"type": ["boolean", "null"]}
    count = integer_schema()
    fingerprint = section_schema({"name": {"enum": ["config_nonsecret", "binary", *UNITS, *ARTIFACTS]},
        "sha256": text_schema(r"[0-9a-f]{64}"), "mode": integer_schema(4095), "uid": count, "gid": count})
    props = {
        "schema": {"const": "inspect/v1"}, "node_id": text_schema(UUID), "instance_id": text_schema(UUID),
        "observed_at": {"type": "string", "format": "date-time"}, "state": {"enum": ["OK", "PARTIAL", "UNKNOWN"]},
        "os": section_schema({"id": text_schema(r"[a-z0-9_-]{1,32}"), "version_id": text_schema(r"[0-9A-Za-z._-]{1,32}"),
            "kernel": text_schema(WORD), "supported": boolean}),
        "cpu": section_schema({"count": integer_schema(65536)}),
        "memory": section_schema({key: count for key in ("total_bytes", "available_bytes", "swap_total_bytes", "swap_free_bytes")}),
        "filesystems": section_schema({"items": array_schema(object_schema({"mount": {"enum": ["/", "/var", "/run", "/tmp"]},
            "total_bytes": count, "available_bytes": count, "filesystem": text_schema(r"[a-zA-Z0-9_.+-]{1,32}")}))}, True),
        "clock": section_schema({"synchronized": boolean, "ntp_active": boolean,
            "timezone": text_schema(r"[A-Za-z0-9_+-]{1,32}(?:/[A-Za-z0-9_+-]{1,32}){0,2}")}),
        "interfaces": section_schema({"items": array_schema(object_schema({"name": text_schema(INTERFACE, False),
            "mtu": integer_schema(2**31 - 1), "up": boolean, "loopback": {"type": "boolean"}}))}, True),
        "qdisc": section_schema({"items": array_schema(object_schema({"interface": text_schema(INTERFACE, False),
            "kind": text_schema(r"[a-zA-Z0-9_-]{1,32}", False), "root": {"type": "boolean"}}))}, True),
        "sysctl": section_schema({key: text_schema(WORD) if kind == "word" else integer_schema(maximum)
            for key, (kind, maximum) in SYSCTLS.items()}),
        "limits": section_schema({"system_file_max": count, "observer_nofile_soft": count, "observer_nofile_hard": count}),
        "services": section_schema({"items": array_schema(section_schema({"name": {"enum": list(SERVICES)},
            "active": boolean, "enabled": boolean, "restart_count": count,
            "user": text_schema(r"[a-zA-Z0-9_-]{1,32}"), "group": text_schema(r"[a-zA-Z0-9_-]{1,32}"),
            "limit_nofile_soft": count, "limit_nofile_hard": count}))}, True),
        "versions": section_schema({"vcl": text_schema(VERSION), "installed_vcl": text_schema(VERSION), "sing_box": text_schema(VERSION),
            "sing_box_source": {"enum": ["INSTALLED_MANIFEST", "UNKNOWN"]}}),
        "listeners": section_schema({"items": array_schema(object_schema({"protocol": {"enum": ["TCP", "UDP"]},
            "family": {"enum": ["IPV4", "IPV6", "ANY"]}, "scope": {"enum": ["LOOPBACK", "LINK_LOCAL", "NON_LOOPBACK"]},
            "address": text_schema(r"[0-9a-fA-F:.*]{1,45}", False), "interface": text_schema(INTERFACE),
            "port": integer_schema(65535, False, 1)}))}, True),
        "firewall": section_schema({"backend": {"enum": ["NFTABLES", "IPTABLES", None]}, "rule_count": count,
            "ipv4_available": boolean, "ipv6_available": boolean,
            "items": array_schema(object_schema({"chain_key": text_schema(r"[0-9a-f]{64}", False),
                "family": {"enum": ["ip", "ip6", "inet", "arp", "bridge", "netdev"]},
                "hook": {"enum": ["input", "output", "forward", "prerouting", "postrouting", "ingress", "egress"]},
                "policy": {"enum": ["ACCEPT", "DROP", None]}}))}, True),
        "updates": section_schema({"available_count": count, "security_count": count, "reboot_marker_present": boolean}),
        "fingerprints": section_schema({"projection": {"const": "managed-config/v1"}, "items": array_schema(fingerprint)}, True),
    }
    for rule in props.values():
        if rule.get("type") == "object" and "state" in rule["properties"]:
            rule["allOf"] = [{"if": {"properties": {"state": {"const": "OK"}}},
                              "then": {"properties": {"reason": {"const": "NONE"}}}}]
            if "truncated" in rule["properties"]:
                rule["allOf"].append({"if": {"properties": {"truncated": {"const": True}}},
                                     "then": {"properties": {"state": {"const": "PARTIAL"}}}})
    fingerprint["allOf"] = [{"if": {"properties": {"state": {"const": "OK"}}}, "then": {"properties": {
        "reason": {"const": "NONE"}, "sha256": {"type": "string"}, "mode": {"type": "integer"},
        "uid": {"type": "integer"}, "gid": {"type": "integer"}}}}]
    doc = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "inspect/v1 bounded read-only Node inventory", **object_schema(props)}
    healthy = {"node_id": {"type": "string"}, "instance_id": {"type": "string"}}
    healthy.update({key: {"properties": {"state": {"const": "OK"}}} for key, rule in props.items() if rule.get("type") == "object"})
    doc["allOf"] = [{"if": {"properties": {"state": {"const": "OK"}}}, "then": {"properties": healthy}}]
    return doc


def validate(doc):
    """Validate the entire fixed contract, not just selected identity fields."""
    def walk(value, rule, depth=0):
        if depth > 20:
            raise ValueError
        for child in rule.get("allOf", []):
            walk(value, child, depth + 1)
        if "if" in rule:
            try:
                walk(value, rule["if"], depth + 1)
            except ValueError:
                pass
            else:
                walk(value, rule.get("then", {}), depth + 1)
        if "const" in rule and value != rule["const"]:
            raise ValueError
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError
        if "type" in rule:
            kind = "null" if value is None else "boolean" if type(value) is bool else "integer" if type(value) is int else (
                "string" if isinstance(value, str) else "array" if isinstance(value, list) else "object" if isinstance(value, dict) else "invalid")
            allowed = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
            if kind not in allowed:
                raise ValueError
        if isinstance(value, dict):
            properties = rule.get("properties", {})
            if not set(rule.get("required", ())) <= set(value) or rule.get("additionalProperties") is False and set(value) - set(properties):
                raise ValueError
            for key, item in value.items():
                if key in properties:
                    walk(item, properties[key], depth + 1)
        elif isinstance(value, list):
            if len(value) > rule.get("maxItems", MAX_ITEMS):
                raise ValueError
            for item in value:
                walk(item, rule["items"], depth + 1)
        elif isinstance(value, str):
            if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
                raise ValueError
            if rule.get("format") == "date-time":
                if len(value) > 40 or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)", value):
                    raise ValueError
                if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
                    raise ValueError
        elif type(value) is int and not rule.get("minimum", 0) <= value <= rule.get("maximum", 2**63 - 1):
            raise ValueError
    try:
        walk(doc, contract())
        if doc["node_id"] is not None and doc["node_id"] == doc["instance_id"]:
            raise ValueError
        for row in doc["listeners"]["items"]:
            address = row["address"]
            ip = None if address == "*" else ipaddress.ip_address(address)
            family = "ANY" if ip is None else "IPV4" if ip.version == 4 else "IPV6"
            scope = "LOOPBACK" if ip and ip.is_loopback else "LINK_LOCAL" if ip and ip.is_link_local else "NON_LOOPBACK"
            if row["family"] != family or row["scope"] != scope:
                raise ValueError
        for section in ("interfaces", "qdisc", "listeners", "firewall", "filesystems", "services", "fingerprints"):
            value = doc[section]
            if value["truncated"] and value["state"] != "PARTIAL":
                raise ValueError
        sections = [value for value in doc.values() if isinstance(value, dict)]
        if any(value["state"] == "OK" and value["reason"] != "NONE" for value in sections):
            raise ValueError
        if doc["state"] == "OK" and (doc["node_id"] is None or doc["instance_id"] is None or any(value["state"] != "OK" for value in sections)):
            raise ValueError
        for row in doc["fingerprints"]["items"]:
            if row["state"] == "OK" and (row["reason"] != "NONE" or any(row[key] is None for key in ("sha256", "mode", "uid", "gid"))):
                raise ValueError
        for key in ("memory",):
            value = doc[key]
            for total, free in (("total_bytes", "available_bytes"), ("swap_total_bytes", "swap_free_bytes")):
                if value[total] is not None and value[free] is not None and value[free] > value[total]:
                    raise ValueError
        if len(json.dumps(doc, separators=(",", ":"), allow_nan=False).encode()) > MAX_BYTES:
            raise ValueError
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return ["invalid inspect/v1 snapshot"]
    return []


def numeric(value, maximum=2**63 - 1):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,19}", value):
        value = int(value)
    return value if type(value) is int and 0 <= value <= maximum else None


def safe_text(value, pattern=WORD):
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def result(state="OK", reason="NONE", **fields):
    return {"state": state, "reason": reason, **fields}


class Reader:
    def __init__(self, seconds=6, runner=None):
        self.deadline = time.monotonic() + max(.01, min(8, seconds))
        self.runner = runner

    @staticmethod
    def open_file(path, no_symlink=False):
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        if no_symlink:
            flags |= getattr(os, "O_NOFOLLOW", 0)
        return os.fdopen(os.open(path, flags), "rb")

    def read(self, path, limit=MAX_FILE, no_symlink=False):
        if time.monotonic() >= self.deadline:
            return "UNKNOWN", "TIMEOUT", None
        try:
            if no_symlink and path.is_symlink():
                return "UNKNOWN", "SYMLINK", None
            # proc/sys regular files report size 0; always bound actual bytes.
            with self.open_file(path, no_symlink) as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    return "UNKNOWN", "INVALID", None
                data = stream.read(limit + 1)
                after = os.fstat(stream.fileno())
                if no_symlink and (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns):
                    return "UNKNOWN", "INVALID", None
                if no_symlink:
                    current = path.lstat()
                    # Windows fstat/path stat expose different ctime semantics.
                    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                            current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
                        return "UNKNOWN", "INVALID", None
            if len(data) > limit:
                return "UNKNOWN", "LIMIT", None
            if time.monotonic() >= self.deadline:
                return "UNKNOWN", "TIMEOUT", None
            return "OK", "NONE", data.decode("utf-8").replace("\r\n", "\n")
        except FileNotFoundError:
            return "UNKNOWN", "MISSING", None
        except PermissionError:
            return "UNREADABLE", "PERMISSION", None
        except OSError as error:
            return "UNKNOWN", "SYMLINK" if error.errno == errno.ELOOP else "INVALID", None
        except UnicodeError:
            return "UNKNOWN", "INVALID", None

    def command(self, argv, limit=MAX_BYTES):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return "UNKNOWN", "TIMEOUT", None
        if self.runner is not None:
            return self.runner(argv, timeout=min(1, remaining), limit=limit)
        if os.name != "posix":
            return "UNSUPPORTED", "MISSING_TOOL", None
        process = None
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, start_new_session=True)
            deadline, data = time.monotonic() + min(1, remaining), bytearray()
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    return "UNKNOWN", "TIMEOUT", None
                ready, _, _ = select.select([process.stdout], [], [], min(.05, left))
                if not ready:
                    continue
                chunk = os.read(process.stdout.fileno(), min(4096, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > limit:
                    return "UNKNOWN", "LIMIT", None
            process.wait(timeout=max(.001, deadline - time.monotonic()))
            if process.returncode:
                return "UNKNOWN", "COMMAND_FAILED", None
            return "OK", "NONE", data.decode("utf-8")
        except FileNotFoundError:
            return "UNSUPPORTED", "MISSING_TOOL", None
        except PermissionError:
            return "UNREADABLE", "PERMISSION", None
        except subprocess.TimeoutExpired:
            return "UNKNOWN", "TIMEOUT", None
        except (OSError, UnicodeError, ValueError):
            return "UNKNOWN", "INVALID", None
        finally:
            if process is not None:
                # The parent can exit while a descendant keeps the pipe open.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                process.stdout.close()

    def hash_file(self, path, limit=MAX_FILE):
        out = result("UNKNOWN", "MISSING", sha256=None, mode=None, uid=None, gid=None)
        try:
            if path.is_symlink():
                return {**out, "reason": "SYMLINK"}
            with self.open_file(path, True) as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    return {**out, "reason": "INVALID"}
                out.update(mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
                if info.st_size > limit:
                    return {**out, "reason": "LIMIT"}
                digest, size = hashlib.sha256(), 0
                while True:
                    if time.monotonic() >= self.deadline:
                        return {**out, "reason": "TIMEOUT"}
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        return {**out, "reason": "LIMIT"}
                    digest.update(chunk)
                after = os.fstat(stream.fileno())
                current = path.lstat()
                if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or (
                        info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                    return {**out, "reason": "INVALID"}
                return {**out, "state": "OK", "reason": "NONE", "sha256": digest.hexdigest()}
        except FileNotFoundError:
            return out
        except PermissionError:
            return {**out, "state": "UNREADABLE", "reason": "PERMISSION"}
        except OSError:
            return {**out, "reason": "INVALID"}


def pairs(text):
    return {key: value for line in text.splitlines() if "=" in line for key, value in [line.split("=", 1)]}


def combine(items, truncated=False):
    bad = next((item for item in items if item["state"] != "OK"), None)
    return result("PARTIAL" if bad or truncated else "OK", "LIMIT" if truncated else bad["reason"] if bad else "NONE",
                  truncated=truncated, items=items[:MAX_ITEMS])


def parse_listeners(text):
    rows, invalid = [], False
    for line in text.splitlines():
        try:
            columns = line.split()
            if len(columns) != 6 or columns[0] not in ("tcp", "udp"):
                raise ValueError
            address, port = columns[4].rsplit(":", 1)
            address = address.removeprefix("[").removesuffix("]")
            address, _, interface = address.partition("%")
            if interface and safe_text(interface, INTERFACE) is None:
                raise ValueError
            ip = None if address == "*" else ipaddress.ip_address(address)
            port = numeric(port, 65535)
            if port is None or port == 0:
                raise ValueError
            row = {"protocol": columns[0].upper(), "family": "ANY" if ip is None else "IPV4" if ip.version == 4 else "IPV6",
                   "scope": "LOOPBACK" if ip and ip.is_loopback else "LINK_LOCAL" if ip and ip.is_link_local else "NON_LOOPBACK",
                   "address": "*" if ip is None else str(ip), "interface": interface or None, "port": port}
            if row not in rows:
                rows.append(row)
        except (ValueError, IndexError):
            invalid = True
    rows.sort(key=lambda row: (row["protocol"], row["family"], row["address"], row["port"], row["interface"] or ""))
    truncated = len(rows) > MAX_ITEMS
    return result("PARTIAL" if invalid or truncated else "OK", "LIMIT" if truncated else "INVALID" if invalid else "NONE",
                  truncated=truncated, items=rows[:MAX_ITEMS])


def config_projection(doc):
    """Recognize managed config shapes; unknown fields never silently disappear.

    Secret values are checked for shape but replaced before hashing, including
    credential UUID, Reality private/short keys and Clash API authentication.
    """
    def object_fields(value, required, optional=()):
        if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
            raise ValueError
    def string(value):
        if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
            raise ValueError
        return value
    def boolean(value):
        if type(value) is not bool:
            raise ValueError
        return value
    def port(value):
        if numeric(value, 65535) is None or type(value) is not int or value == 0:
            raise ValueError
        return value
    def strings(value):
        if not isinstance(value, list) or len(value) > 10000:
            raise ValueError
        return [string(item) for item in value]
    object_fields(doc, ("log", "inbounds", "outbounds", "route", "experimental"))
    log = doc["log"]
    object_fields(log, ("level", "timestamp"))
    cleaned = {"log": {"level": string(log["level"]), "timestamp": boolean(log["timestamp"])} , "inbounds": [], "outbounds": []}
    if not isinstance(doc["inbounds"], list) or len(doc["inbounds"]) != 1:
        raise ValueError
    for inbound in doc["inbounds"]:
        object_fields(inbound, ("type", "tag", "listen", "listen_port", "users", "tls"))
        if inbound["type"] != "vless" or not isinstance(inbound["users"], list) or not 1 <= len(inbound["users"]) <= 10000:
            raise ValueError
        users = []
        for user in inbound["users"]:
            object_fields(user, ("name", "uuid", "flow"))
            if safe_text(user["uuid"], UUID) is None:
                raise ValueError
            users.append({"name": string(user["name"]), "flow": string(user["flow"])})
        tls = inbound["tls"]
        object_fields(tls, ("enabled", "server_name", "reality"))
        reality = tls["reality"]
        object_fields(reality, ("enabled", "handshake", "private_key", "short_id"))
        string(reality["private_key"])
        short_ids = strings(reality["short_id"]) if isinstance(reality["short_id"], list) else [string(reality["short_id"])]
        if len(short_ids) > 16:
            raise ValueError
        handshake = reality["handshake"]
        object_fields(handshake, ("server", "server_port"))
        cleaned["inbounds"].append({"type": inbound["type"], "tag": string(inbound["tag"]), "listen": string(inbound["listen"]),
            "listen_port": port(inbound["listen_port"]), "users": sorted(users, key=lambda item: item["name"]),
            "tls": {"enabled": boolean(tls["enabled"]), "server_name": string(tls["server_name"]), "reality": {
                "enabled": boolean(reality["enabled"]), "handshake": {"server": string(handshake["server"]), "server_port": port(handshake["server_port"])}}}})
    if not isinstance(doc["outbounds"], list) or len(doc["outbounds"]) > 10001:
        raise ValueError
    for outbound in doc["outbounds"]:
        object_fields(outbound, ("type", "tag"))
        if outbound["type"] != "direct":
            raise ValueError
        cleaned["outbounds"].append({"type": "direct", "tag": string(outbound["tag"])})
    route = doc["route"]
    object_fields(route, ("rules", "final"))
    rules = []
    if not isinstance(route["rules"], list) or len(route["rules"]) > 10001:
        raise ValueError
    for rule in route["rules"]:
        if rule.get("action") == "sniff":
            object_fields(rule, ("action", "inbound"))
            rules.append({"action": "sniff", "inbound": strings(rule["inbound"])})
        else:
            object_fields(rule, ("auth_user", "action", "outbound"))
            if rule["action"] != "route":
                raise ValueError
            rules.append({"auth_user": strings(rule["auth_user"]), "action": "route", "outbound": string(rule["outbound"])})
    cleaned["route"] = {"rules": rules, "final": string(route["final"])}
    object_fields(doc["experimental"], ("clash_api",))
    clash = doc["experimental"]["clash_api"]
    object_fields(clash, ("external_controller", "secret"))
    string(clash["secret"])
    cleaned["experimental"] = {"clash_api": {"external_controller": string(clash["external_controller"])}}
    return cleaned


def config_hash(text):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value
    try:
        doc = json.loads(text, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        projected = config_projection(doc)
        return hashlib.sha256(json.dumps(projected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        return None


def firewall(reader):
    base = dict(backend=None, rule_count=None, ipv4_available=None, ipv6_available=None, truncated=False, items=[])
    state, reason, text = reader.command(["nft", "-j", "list", "ruleset"])
    if state == "OK":
        try:
            records = json.loads(text)["nftables"]
            if not isinstance(records, list):
                raise ValueError
            rows, count = [], 0
            for entry in records:
                if "rule" in entry:
                    count += 1
                chain = entry.get("chain", {})
                if "hook" not in chain:
                    continue
                family, hook, policy = chain.get("family"), chain["hook"], chain.get("policy")
                if family not in ("ip", "ip6", "inet", "arp", "bridge", "netdev") or hook not in (
                        "input", "output", "forward", "prerouting", "postrouting", "ingress", "egress") or policy not in (None, "accept", "drop"):
                    raise ValueError
                identity = [family, str(chain.get("table")), str(chain.get("name"))]
                rows.append({"chain_key": hashlib.sha256(json.dumps(identity).encode()).hexdigest(), "family": family,
                             "hook": hook, "policy": policy.upper() if policy else None})
            return result("PARTIAL" if len(rows) > MAX_ITEMS else "OK", "LIMIT" if len(rows) > MAX_ITEMS else "NONE",
                **{**base, "backend": "NFTABLES", "rule_count": count, "ipv4_available": True, "ipv6_available": True,
                   "truncated": len(rows) > MAX_ITEMS, "items": rows[:MAX_ITEMS]})
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            return result("UNKNOWN", "INVALID", **base)
    if state != "UNSUPPORTED":
        return result(state, reason, **base)
    rows, available, count, failures = [], [], 0, []
    for command, family in (("iptables-save", "ip"), ("ip6tables-save", "ip6")):
        state, reason, text = reader.command([command])
        available.append(True if state == "OK" else None)
        if state != "OK":
            failures.append((state, reason))
            continue
        if not re.search(r"^\*(filter|nat|mangle|raw|security)$", text, re.M) or not re.search(r"^COMMIT$", text, re.M):
            available[-1] = None
            failures.append(("UNKNOWN", "INVALID"))
            continue
        for line in text.splitlines():
            if line.startswith("-A "):
                count += 1
            match = re.fullmatch(r":(INPUT|OUTPUT|FORWARD|PREROUTING|POSTROUTING) (ACCEPT|DROP) \[[0-9]+:[0-9]+\]", line)
            if match:
                rows.append({"chain_key": hashlib.sha256((family + line.split()[0]).encode()).hexdigest(), "family": family,
                             "hook": match[1].lower(), "policy": match[2]})
    if not any(available):
        return result(failures[0][0], failures[0][1], **base)
    return result("PARTIAL" if failures else "OK", failures[0][1] if failures else "NONE", **{**base, "backend": "IPTABLES",
        "rule_count": count, "ipv4_available": available[0], "ipv6_available": available[1], "items": rows[:MAX_ITEMS], "truncated": len(rows) > MAX_ITEMS})


def build_snapshot(*, state_dir=Path("/etc/vincula"), config_path=Path("/etc/sing-box/config.json"),
                   binary_path=Path("/usr/local/bin/sing-box"), lib_dir=Path("/usr/local/lib/vincula"),
                   root=Path("/"), version="0.5.2", seconds=6, runner=None):
    reader = Reader(seconds, runner)
    schema = contract()
    def empty(rule):
        if rule.get("type") == "array":
            return []
        if "const" in rule:
            return rule["const"]
        return None
    doc = {"schema": "inspect/v1", "node_id": None, "instance_id": None,
           "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "state": "UNKNOWN"}
    for key, rule in schema["properties"].items():
        if key in doc:
            continue
        doc[key] = {field: empty(child) for field, child in rule["properties"].items()}
        doc[key].update(state="UNKNOWN", reason="MISSING")
        if "truncated" in doc[key]:
            doc[key]["truncated"] = False
    doc["versions"]["sing_box_source"] = "UNKNOWN"
    state, reason, settings = reader.read(state_dir / "config.toml")
    if settings:
        match = re.search(r'^node_id\s*=\s*"(' + UUID + r')"\s*$', settings, re.M)
        doc["node_id"] = match[1] if match else None
    state, reason, text = reader.read(state_dir / "state.json")
    try:
        doc["instance_id"] = safe_text(json.loads(text)["instance_id"], UUID) if text else None
    except (ValueError, TypeError, KeyError, RecursionError):
        pass
    def read_field(path, pattern=None, maximum=2**63 - 1):
        state, reason, value = reader.read(path, 65536)
        value = value.strip() if value is not None else None
        parsed = safe_text(value, pattern) if pattern else numeric(value, maximum)
        return state if parsed is not None else "UNKNOWN" if state == "OK" else state, reason if state != "OK" or parsed is not None else "INVALID", parsed
    state, reason, text = reader.read(root / "etc/os-release", 65536)
    if text:
        fields = pairs(text)
        os_id = safe_text(fields.get("ID", "").strip('"'), r"[a-z0-9_-]{1,32}")
        os_version = safe_text(fields.get("VERSION_ID", "").strip('"'), r"[0-9A-Za-z._-]{1,32}")
        _, _, kernel = read_field(root / "proc/sys/kernel/osrelease", WORD)
        supported = (os_id == "debian" and os_version in ("12", "13")) or (os_id == "ubuntu" and os_version in ("22.04", "24.04", "26.04"))
        doc["os"] = result("OK" if os_id and os_version and kernel else "PARTIAL", "NONE" if os_id and os_version and kernel else "INVALID",
            id=os_id, version_id=os_version, kernel=kernel, supported=supported if os_id and os_version else None)
        if os_id and os_version and not supported:
            doc["os"].update(state="UNSUPPORTED", reason="UNSUPPORTED_OS")
    else:
        doc["os"].update(state=state, reason=reason)
    state, reason, text = reader.read(root / "proc/stat")
    if text:
        count = len(re.findall(r"^cpu[0-9]+\s", text, re.M))
        doc["cpu"] = result("OK" if 0 < count <= 65536 else "UNKNOWN", "NONE" if 0 < count <= 65536 else "INVALID", count=count if 0 < count <= 65536 else None)
    else:
        doc["cpu"].update(state=state, reason=reason)
    state, reason, text = reader.read(root / "proc/meminfo", 65536)
    if text:
        fields = {name: numeric(value) for name, value in re.findall(r"^(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+([0-9]+) kB$", text, re.M)}
        memory = {key: fields.get(source) * 1024 if fields.get(source) is not None and fields[source] <= (2**63 - 1) // 1024 else None for key, source in (
            ("total_bytes", "MemTotal"), ("available_bytes", "MemAvailable"), ("swap_total_bytes", "SwapTotal"), ("swap_free_bytes", "SwapFree"))}
        if memory["total_bytes"] is not None and memory["available_bytes"] is not None and memory["available_bytes"] > memory["total_bytes"]:
            memory["available_bytes"] = None
        if memory["swap_total_bytes"] is not None and memory["swap_free_bytes"] is not None and memory["swap_free_bytes"] > memory["swap_total_bytes"]:
            memory["swap_free_bytes"] = None
        doc["memory"] = result("OK" if all(value is not None for value in memory.values()) else "PARTIAL", "NONE" if all(value is not None for value in memory.values()) else "INVALID", **memory)
    else:
        doc["memory"].update(state=state, reason=reason)
    state, reason, mounts = reader.read(root / "proc/self/mountinfo")
    filesystem_types = {}
    for line in (mounts or "").splitlines():
        before, sep, after = line.partition(" - ")
        if sep and len(before.split()) >= 5 and after.split():
            filesystem_types[before.split()[4]] = safe_text(after.split()[0], r"[a-zA-Z0-9_.+-]{1,32}")
    rows, failed = [], False
    for mount in ("/", "/var", "/run", "/tmp"):
        if time.monotonic() >= reader.deadline:
            failed = True
            break
        try:
            space = os.statvfs(root / mount.lstrip("/"))
            parents = [name for name in filesystem_types if mount == name or name == "/" or mount.startswith(name.rstrip("/") + "/")]
            kind = filesystem_types[max(parents, key=len)] if parents else None
            rows.append({"mount": mount, "total_bytes": numeric(space.f_blocks * space.f_frsize),
                         "available_bytes": numeric(space.f_bavail * space.f_frsize), "filesystem": kind})
            failed |= kind is None or rows[-1]["total_bytes"] is None or rows[-1]["available_bytes"] is None
        except (OSError, AttributeError):
            failed = True
    doc["filesystems"] = result("PARTIAL" if failed else "OK", "INVALID" if failed else "NONE", truncated=False, items=rows)
    state, reason, text = reader.command(["timedatectl", "show", "--property=NTPSynchronized", "--property=NTP", "--property=Timezone"])
    if text is not None:
        fields = pairs(text)
        clock = {"synchronized": {"yes": True, "no": False}.get(fields.get("NTPSynchronized")),
                 "ntp_active": {"yes": True, "no": False}.get(fields.get("NTP")),
                 "timezone": safe_text(fields.get("Timezone"), r"[A-Za-z0-9_+-]{1,32}(?:/[A-Za-z0-9_+-]{1,32}){0,2}")}
        doc["clock"] = result("OK" if all(value is not None for value in clock.values()) else "PARTIAL", "NONE" if all(value is not None for value in clock.values()) else "INVALID", **clock)
    else:
        doc["clock"].update(state=state, reason=reason)
    rows, invalid = [], False
    try:
        names = sorted(path.name for path in itertools.islice((root / "sys/class/net").iterdir(), MAX_ITEMS + 1))
        for name in names[:MAX_ITEMS]:
            if not safe_text(name, INTERFACE):
                invalid = True
                continue
            path = root / "sys/class/net" / name
            _, _, mtu = read_field(path / "mtu", maximum=2**31 - 1)
            state, reason, flags_text = reader.read(path / "flags", 64)
            flags = int(flags_text.strip(), 16) if flags_text and re.fullmatch(r"0x[0-9a-fA-F]{1,8}\s*", flags_text) else None
            up = bool(flags & 1) if flags is not None else None
            rows.append({"name": name, "mtu": mtu, "up": up, "loopback": name == "lo"})
            invalid |= mtu is None or up is None
        doc["interfaces"] = result("PARTIAL" if invalid or len(names) > MAX_ITEMS else "OK", "LIMIT" if len(names) > MAX_ITEMS else "INVALID" if invalid else "NONE", truncated=len(names) > MAX_ITEMS, items=rows)
    except PermissionError:
        doc["interfaces"].update(state="UNREADABLE", reason="PERMISSION")
    except OSError:
        pass
    state, reason, text = reader.command(["tc", "-j", "qdisc", "show"])
    if text is not None:
        try:
            source = json.loads(text)
            if not isinstance(source, list):
                raise ValueError
            rows = []
            for row in source[:MAX_ITEMS]:
                if (not safe_text(row.get("dev"), INTERFACE) or not safe_text(row.get("kind"), r"[a-zA-Z0-9_-]{1,32}")
                        or "root" in row and type(row["root"]) is not bool):
                    raise ValueError
                rows.append({"interface": row["dev"], "kind": row["kind"], "root": row.get("root") is True})
            doc["qdisc"] = result("PARTIAL" if len(source) > MAX_ITEMS else "OK", "LIMIT" if len(source) > MAX_ITEMS else "NONE", truncated=len(source) > MAX_ITEMS, items=rows)
        except (ValueError, AttributeError, TypeError, RecursionError):
            doc["qdisc"].update(reason="INVALID")
    else:
        doc["qdisc"].update(state=state, reason=reason)
    unknown = False
    for key, (kind, maximum) in SYSCTLS.items():
        state, reason, value = read_field(root / "proc/sys" / key.replace(".", "/"), WORD if kind == "word" else None, maximum or 2**63 - 1)
        doc["sysctl"][key] = value
        if state != "OK":
            unknown = True
            doc["sysctl"].update(reason=reason)
    doc["sysctl"].update(state="PARTIAL" if unknown else "OK", reason=doc["sysctl"]["reason"] if unknown else "NONE")
    state, reason, file_max = read_field(root / "proc/sys/fs/file-max")
    doc["limits"].update(state=state, reason=reason, system_file_max=file_max)
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        doc["limits"].update(observer_nofile_soft=numeric(soft), observer_nofile_hard=numeric(hard))
        if numeric(soft) is None or numeric(hard) is None:
            doc["limits"].update(state="PARTIAL", reason="INVALID")
    except (ImportError, OSError, ValueError):
        doc["limits"].update(state="PARTIAL", reason="INVALID")
    services = []
    for name in SERVICES:
        state, reason, text = reader.command(["systemctl", "show", name, "--property=LoadState", "--property=ActiveState", "--property=UnitFileState",
            "--property=NRestarts", "--property=User", "--property=Group", "--property=LimitNOFILESoft", "--property=LimitNOFILE"])
        fields = pairs(text) if text is not None else {}
        loaded = fields.get("LoadState") == "loaded"
        active = {"active": True, "inactive": False, "failed": False}.get(fields.get("ActiveState")) if loaded else None
        enabled = {"enabled": True, "enabled-runtime": True, "disabled": False, "masked": False, "masked-runtime": False}.get(fields.get("UnitFileState")) if loaded else None
        values = {"active": active, "enabled": enabled, "restart_count": numeric(fields.get("NRestarts")),
                  "user": safe_text(fields.get("User") or "root", r"[a-zA-Z0-9_-]{1,32}") if loaded else None,
                  "group": safe_text(fields.get("Group"), r"[a-zA-Z0-9_-]{1,32}"),
                  "limit_nofile_soft": numeric(fields.get("LimitNOFILESoft")), "limit_nofile_hard": numeric(fields.get("LimitNOFILE"))}
        if state == "OK" and (not loaded or any(values[key] is None for key in ("active", "enabled", "restart_count", "limit_nofile_soft", "limit_nofile_hard"))):
            state, reason = "PARTIAL", "INVALID"
        services.append(result(state, reason, name=name, **values))
    doc["services"] = combine(services)
    state, reason, installed = read_field(state_dir / "VERSION", VERSION)
    doc["versions"].update(state=state, reason=reason, vcl=safe_text(version, VERSION), installed_vcl=installed)
    state, reason, text = reader.command(["ss", "-H", "-lntu"])
    doc["listeners"] = parse_listeners(text) if text is not None else result(state, reason, truncated=False, items=[])
    doc["firewall"] = firewall(reader)
    state, reason, text = reader.read(root / "var/lib/update-notifier/updates-available", 65536)
    count = re.search(r"^([0-9]+) (?:packages? can be updated|updates? can be applied)", text or "", re.M)
    security = re.search(r"^([0-9]+) of these updates (?:are|is) (?:a )?security", text or "", re.M)
    doc["updates"].update(state=state if text is None else "PARTIAL", reason=reason if text is None else "INVALID",
        available_count=numeric(count[1]) if count else None, security_count=numeric(security[1]) if security else None)
    try:
        (root / "run/reboot-required").stat()
        doc["updates"]["reboot_marker_present"] = True
    except FileNotFoundError:
        doc["updates"]["reboot_marker_present"] = False
    except PermissionError:
        doc["updates"].update(state="UNREADABLE", reason="PERMISSION")
    except OSError:
        pass
    if count and security and doc["updates"]["reboot_marker_present"] is not None:
        doc["updates"].update(state="OK", reason="NONE")
    fingerprint_rows = []
    for name, path in {**{key: root / "etc/systemd/system" / filename for key, filename in UNITS.items()},
                       **{key: root / "usr/local/bin/vincula" if key == "helper" else lib_dir / filename for key, filename in ARTIFACTS.items()}}.items():
        fingerprint_rows.append({"name": name, **reader.hash_file(path)})
    state, reason, text = reader.read(config_path, MAX_CONFIG, no_symlink=True)
    config = result(state, reason, name="config_nonsecret", sha256=None, mode=None, uid=None, gid=None)
    if text is not None:
        config["sha256"] = config_hash(text)
        if config["sha256"] is None:
            config.update(state="UNKNOWN", reason="INVALID")
        try:
            info = config_path.stat()
            config.update(mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
        except OSError:
            config.update(state="UNKNOWN", reason="INVALID", sha256=None)
    fingerprint_rows.append(config)
    binary = {"name": "binary", **reader.hash_file(binary_path, 256 * 1024 * 1024)}
    fingerprint_rows.append(binary)
    # Match the installed version record to bytes without executing the binary.
    # An unexpected binary may itself be the drift under investigation.
    _, _, manifest = reader.read(lib_dir / "sing-box.lock", 65536, no_symlink=True)
    fields = pairs(manifest) if manifest else {}
    expected = safe_text(fields.get("binary_sha256"), r"[0-9a-f]{64}")
    recorded_version = safe_text(fields.get("sing_box_version"), VERSION)
    if binary["state"] == "OK" and expected and binary["sha256"] == expected and recorded_version:
        doc["versions"].update(sing_box=recorded_version, sing_box_source="INSTALLED_MANIFEST")
    if doc["versions"]["sing_box"] is None:
        doc["versions"].update(state="PARTIAL", reason="INVALID")
    doc["fingerprints"] = {**combine(fingerprint_rows), "projection": "managed-config/v1"}
    identity_ok = doc["node_id"] is not None and doc["instance_id"] is not None and doc["node_id"] != doc["instance_id"]
    doc["state"] = ("OK" if all(value["state"] == "OK" for value in doc.values() if isinstance(value, dict)) else "PARTIAL") if identity_ok else "UNKNOWN"
    return doc


def main(argv):
    if len(argv) != 6:
        return 2
    doc = build_snapshot(state_dir=Path(argv[1]), config_path=Path(argv[2]), binary_path=Path(argv[3]), lib_dir=Path(argv[4]), version=argv[5])
    if validate(doc):
        return 1
    sys.stdout.write(json.dumps(doc, separators=(",", ":"), allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
