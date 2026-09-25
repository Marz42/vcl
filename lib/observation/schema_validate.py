"""Lightweight schema checks for observation contracts (stdlib only)."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$")
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_-]*/v[0-9]+$")
# JSON Schema format:date-time (RFC 3339 subset used by Node/Controller).
RFC3339_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


def _is_int_nonneg(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_number_nonneg(value: Any) -> bool:
    """Finite non-negative JSON number (rejects NaN / ±Infinity)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return value >= 0


def _is_rfc3339(value: Any) -> bool:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        return False
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def _reject_extra(obj: dict[str, Any], allowed: set[str], prefix: str, errors: list[str]) -> None:
    extra = set(obj.keys()) - allowed
    if extra:
        errors.append(f"unexpected fields in {prefix}: {sorted(extra)}")


def _opt_int_nonneg(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    if not _is_int_nonneg(value):
        errors.append(f"invalid {path}")


def _opt_rfc3339(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    if not _is_rfc3339(value):
        errors.append(f"invalid {path}")


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
    """Fail-closed validation matching schemas/telemetry/v1.schema.json."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["expected object"]
    if doc.get("schema") != "telemetry/v1":
        errors.append("schema must be telemetry/v1")
    for key in ("node_id", "instance_id"):
        val = doc.get(key)
        if not isinstance(val, str) or not UUID_RE.fullmatch(val):
            errors.append(f"invalid {key}")
    if not _is_rfc3339(doc.get("observed_at")):
        errors.append("invalid observed_at")
    if not _is_int_nonneg(doc.get("uptime_seconds")):
        errors.append("invalid uptime_seconds")

    load = doc.get("load")
    if not isinstance(load, dict):
        errors.append("invalid load")
    else:
        _reject_extra(load, {"load1", "load5", "load15"}, "load", errors)
        for key in ("load1", "load5", "load15"):
            if not _is_number_nonneg(load.get(key)):
                errors.append(f"invalid load.{key}")

    memory = doc.get("memory")
    if not isinstance(memory, dict):
        errors.append("invalid memory")
    else:
        _reject_extra(memory, {"total_bytes", "used_bytes"}, "memory", errors)
        for key in ("total_bytes", "used_bytes"):
            if not _is_int_nonneg(memory.get(key)):
                errors.append(f"invalid memory.{key}")

    fs = doc.get("filesystem")
    if not isinstance(fs, dict):
        errors.append("invalid filesystem")
    else:
        _reject_extra(fs, {"mount", "total_bytes", "used_bytes"}, "filesystem", errors)
        mount = fs.get("mount")
        if not isinstance(mount, str) or not (1 <= len(mount) <= 256):
            errors.append("invalid filesystem.mount")
        for key in ("total_bytes", "used_bytes"):
            if not _is_int_nonneg(fs.get(key)):
                errors.append(f"invalid filesystem.{key}")

    net = doc.get("network")
    if not isinstance(net, dict):
        errors.append("invalid network")
    else:
        _reject_extra(net, {"rx_bytes", "tx_bytes"}, "network", errors)
        for key in ("rx_bytes", "tx_bytes"):
            if not _is_int_nonneg(net.get(key)):
                errors.append(f"invalid network.{key}")

    sing = doc.get("sing_box")
    if not isinstance(sing, dict):
        errors.append("invalid sing_box")
    else:
        _reject_extra(
            sing,
            {"active", "connection_count", "restart_count", "last_restart_at"},
            "sing_box",
            errors,
        )
        if not isinstance(sing.get("active"), bool):
            errors.append("invalid sing_box.active")
        _opt_int_nonneg(sing.get("connection_count"), "sing_box.connection_count", errors)
        _opt_int_nonneg(sing.get("restart_count"), "sing_box.restart_count", errors)
        _opt_rfc3339(sing.get("last_restart_at"), "sing_box.last_restart_at", errors)

    acct = doc.get("accountd")
    if not isinstance(acct, dict):
        errors.append("invalid accountd")
    else:
        _reject_extra(
            acct,
            {
                "active",
                "last_poll_age_seconds",
                "export_seq",
                "last_event_age_seconds",
            },
            "accountd",
            errors,
        )
        if not isinstance(acct.get("active"), bool):
            errors.append("invalid accountd.active")
        _opt_int_nonneg(
            acct.get("last_poll_age_seconds"), "accountd.last_poll_age_seconds", errors
        )
        _opt_int_nonneg(acct.get("export_seq"), "accountd.export_seq", errors)
        _opt_int_nonneg(
            acct.get("last_event_age_seconds"),
            "accountd.last_event_age_seconds",
            errors,
        )

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
