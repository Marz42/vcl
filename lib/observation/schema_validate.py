"""Lightweight schema checks for observation contracts (stdlib only)."""

from __future__ import annotations

import re
from typing import Any

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$")
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_-]*/v[0-9]+$")


def _is_int_nonneg(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_number_nonneg(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def validate_capabilities_v1(doc: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["expected object"]
    if doc.get("schema") != "capabilities/v1":
        errors.append("schema must be capabilities/v1")
    ver = doc.get("node_version")
    if not isinstance(ver, str) or not VERSION_RE.fullmatch(ver):
        errors.append("invalid node_version")
    caps = doc.get("capabilities")
    if not isinstance(caps, list):
        errors.append("capabilities must be an array")
    elif len(caps) > 64:
        errors.append("capabilities exceeds max items")
    else:
        seen: set[str] = set()
        for item in caps:
            if not isinstance(item, str) or not CAPABILITY_RE.fullmatch(item):
                errors.append(f"invalid capability: {item!r}")
            elif item in seen:
                errors.append(f"duplicate capability: {item!r}")
            else:
                seen.add(item)
    extra = set(doc.keys()) - {"schema", "node_version", "capabilities"}
    if extra:
        errors.append(f"unexpected fields: {sorted(extra)}")
    return errors


def validate_telemetry_v1(doc: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["expected object"]
    if doc.get("schema") != "telemetry/v1":
        errors.append("schema must be telemetry/v1")
    for key in ("node_id", "instance_id"):
        val = doc.get(key)
        if not isinstance(val, str) or not UUID_RE.fullmatch(val):
            errors.append(f"invalid {key}")
    observed = doc.get("observed_at")
    if not isinstance(observed, str) or not observed:
        errors.append("invalid observed_at")
    if not _is_int_nonneg(doc.get("uptime_seconds")):
        errors.append("invalid uptime_seconds")
    load = doc.get("load")
    if not isinstance(load, dict):
        errors.append("invalid load")
    else:
        for key in ("load1", "load5", "load15"):
            if not _is_number_nonneg(load.get(key)):
                errors.append(f"invalid load.{key}")
    memory = doc.get("memory")
    if not isinstance(memory, dict):
        errors.append("invalid memory")
    else:
        for key in ("total_bytes", "used_bytes"):
            if not _is_int_nonneg(memory.get(key)):
                errors.append(f"invalid memory.{key}")
    fs = doc.get("filesystem")
    if not isinstance(fs, dict):
        errors.append("invalid filesystem")
    else:
        mount = fs.get("mount")
        if not isinstance(mount, str) or not mount:
            errors.append("invalid filesystem.mount")
        for key in ("total_bytes", "used_bytes"):
            if not _is_int_nonneg(fs.get(key)):
                errors.append(f"invalid filesystem.{key}")
    net = doc.get("network")
    if not isinstance(net, dict):
        errors.append("invalid network")
    else:
        for key in ("rx_bytes", "tx_bytes"):
            if not _is_int_nonneg(net.get(key)):
                errors.append(f"invalid network.{key}")
    sing = doc.get("sing_box")
    if not isinstance(sing, dict) or not isinstance(sing.get("active"), bool):
        errors.append("invalid sing_box")
    acct = doc.get("accountd")
    if not isinstance(acct, dict) or not isinstance(acct.get("active"), bool):
        errors.append("invalid accountd")
    allowed = {
        "schema",
        "node_id",
        "instance_id",
        "observed_at",
        "uptime_seconds",
        "load",
        "memory",
        "filesystem",
        "network",
        "sing_box",
        "accountd",
    }
    extra = set(doc.keys()) - allowed
    if extra:
        errors.append(f"unexpected fields: {sorted(extra)}")
    return errors
