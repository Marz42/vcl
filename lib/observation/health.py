"""Pure, explainable observation health. No I/O and no mutation callbacks."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

STATES = {"HEALTHY", "SUSPECT", "DEGRADED", "UNREACHABLE", "RECOVERING", "UNKNOWN"}
DIMENSIONS = ("node", "observation", "proxy", "accounting")
OBSERVATION_STATES = {"OK", "ERROR", "AUTH_FAILED", "UNSUPPORTED", "TIMEOUT"}


def timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def utc(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def transition(previous: dict, signal: str, reason: str) -> dict:
    """Transport failures debounce; positive service failures are immediate."""
    failures = min(1000, int(previous.get("failures", 0)))
    successes = min(1000, int(previous.get("successes", 0)))
    old = previous.get("state", "UNKNOWN")
    if signal == "UNKNOWN":
        state, failures, successes = "UNKNOWN", 0, 0
    elif signal in ("FAILED", "DEGRADED"):
        failures, successes = failures + 1, 0
        state = "DEGRADED" if signal == "DEGRADED" else (
            "UNREACHABLE" if failures >= 3 else "SUSPECT"
        )
    else:
        successes, failures = successes + 1, 0
        state = "RECOVERING" if old in (
            "SUSPECT", "DEGRADED", "UNREACHABLE", "RECOVERING"
        ) and successes < 2 else "HEALTHY"
    return {"state": state, "reason": reason, "failures": failures, "successes": successes}


def number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and 0 <= value <= 2**63 - 1 else None
    except OverflowError:
        return None


def metrics(snapshot: dict, previous: dict, now: float) -> dict:
    """Allowlist numerical values; never persist free-form remote strings."""
    fields = {
        "uptime_seconds": snapshot.get("uptime_seconds"),
        "load1": snapshot["load"].get("load1"),
        "load5": snapshot["load"].get("load5"),
        "load15": snapshot["load"].get("load15"),
        "memory_total_bytes": snapshot["memory"].get("total_bytes"),
        "memory_used_bytes": snapshot["memory"].get("used_bytes"),
        "disk_total_bytes": snapshot["filesystem"].get("total_bytes"),
        "disk_used_bytes": snapshot["filesystem"].get("used_bytes"),
        "rx_bytes": snapshot["network"].get("rx_bytes"),
        "tx_bytes": snapshot["network"].get("tx_bytes"),
        "connections": snapshot["sing_box"].get("connection_count"),
        "restart_count": snapshot["sing_box"].get("restart_count"),
        "last_poll_age_seconds": snapshot["accountd"].get("last_poll_age_seconds"),
        "export_seq": snapshot["accountd"].get("export_seq"),
        "last_event_age_seconds": snapshot["accountd"].get("last_event_age_seconds"),
    }
    out = {key: number(value) for key, value in fields.items()}
    sampled_at = previous.get("sampled_at")
    elapsed = now - sampled_at if sampled_at is not None else 0
    old = previous.get("metrics", {})
    same_instance = previous.get("instance_id") == snapshot["instance_id"]
    same_boot = out["uptime_seconds"] is not None and old.get("uptime_seconds") is not None and (
        out["uptime_seconds"] >= old["uptime_seconds"]
    )
    for key in ("rx_bytes", "tx_bytes"):
        value, before = out[key], old.get(key)
        out[key + "_per_second"] = (
            (value - before) / elapsed if same_instance and same_boot and elapsed > 0
            and value is not None and before is not None and value >= before else None
        )
    return out


def clean_probe(probe: Any) -> dict:
    reasons = {"OK", "NOT_CONFIGURED", "TIMEOUT", "TLS_FAILED", "DNS_FAILED",
               "CONNECT_FAILED", "HTTP_FAILED", "RUNTIME_UNAVAILABLE", "INVALID_CONFIG"}
    if not isinstance(probe, dict):
        probe = {}
    reason = probe.get("reason")
    if reason not in reasons:
        reason = "NOT_CONFIGURED"
    success = probe.get("success")
    if type(success) is not bool or (success and reason != "OK"):
        success = None
    return {"success": success, "reason": reason,
            **{key: number(probe.get(key)) for key in ("connect_ms", "ttfb_ms", "total_ms")}}


def build(node: dict, result: dict, previous: dict, now: float, probe: dict | None = None) -> dict:
    state = result.get("state", "ERROR")
    if state not in OBSERVATION_STATES:
        state = "ERROR"
    snapshot = result.get("snapshot") if state == "OK" else None
    signals = {key: ("UNKNOWN", "NO_OBSERVATION") for key in DIMENSIONS}
    if state in ("ERROR", "TIMEOUT"):
        signals["node"] = ("FAILED", state)
        signals["observation"] = ("FAILED", state)
    elif state == "AUTH_FAILED":
        # Authentication rejection proves an SSH endpoint answered, not proxy health.
        signals["node"] = ("HEALTHY", "SSH_RESPONDED")
        signals["observation"] = ("DEGRADED", "AUTH_FAILED")
    elif state == "UNSUPPORTED":
        signals["node"] = ("HEALTHY", "SSH_RESPONDED")
        signals["observation"] = ("UNKNOWN", "UNSUPPORTED")
    current_probe = clean_probe(probe)
    out = {"name": node["name"], "node_id": node["node_id"], "received_at": now,
           "observation_state": state, "sampled_at": previous.get("sampled_at"),
           "observed_at": previous.get("observed_at"),
           "instance_id": previous.get("instance_id"), "metrics": previous.get("metrics", {}),
           "services": previous.get("services", {"sing_box_active": None, "accountd_active": None}),
           "probe": current_probe}
    if snapshot:
        age = now - timestamp(snapshot["observed_at"])
        fresh = -30 <= age <= 90
        signals["node"] = ("HEALTHY", "SSH_RESPONDED")
        signals["observation"] = ("HEALTHY", "FRESH") if fresh else ("DEGRADED", "TELEMETRY_STALE")
        if fresh:
            out.update(instance_id=snapshot["instance_id"], sampled_at=now,
                       observed_at=snapshot["observed_at"], metrics=metrics(snapshot, previous, now))
            out["services"] = {"sing_box_active": snapshot["sing_box"]["active"], "accountd_active": snapshot["accountd"]["active"]}
            if not snapshot["sing_box"]["active"]:
                signals["proxy"] = ("DEGRADED", "SERVICE_INACTIVE")
            elif current_probe["success"] is not None:
                signals["proxy"] = ("HEALTHY" if current_probe["success"] else "DEGRADED", current_probe["reason"])
            else:
                signals["proxy"] = ("UNKNOWN", current_probe["reason"])
            accountd = snapshot["accountd"]
            poll_age = accountd.get("last_poll_age_seconds")
            if not accountd["active"]:
                signals["accounting"] = ("DEGRADED", "SERVICE_INACTIVE")
            elif poll_age is None:
                signals["accounting"] = ("UNKNOWN", "POLL_AGE_MISSING")
            else:
                signals["accounting"] = ("DEGRADED", "POLL_STALLED") if poll_age > 90 else ("HEALTHY", "POLL_RECENT")
    old_health = previous.get("health", {})
    if snapshot and previous.get("instance_id") is not None and previous["instance_id"] != snapshot["instance_id"]:
        old_health = {}
    out["health"] = {key: transition(old_health.get(key, {}), *signals[key]) for key in DIMENSIONS}
    out["overall"] = overall(out["health"])
    return out


def overall(health: dict) -> str:
    states = {value["state"] for value in health.values()}
    return next((state for state in ("UNREACHABLE", "DEGRADED", "SUSPECT", "RECOVERING", "UNKNOWN")
                 if state in states), "HEALTHY")


def present(record: dict, now: float) -> dict:
    out = dict(record)
    age = now - record["received_at"]
    out["telemetry_age_seconds"] = max(0, now - timestamp(record["observed_at"])) if record.get("observed_at") else None
    out["received_at"] = utc(record["received_at"])
    out["sampled_at"] = utc(record["sampled_at"]) if record.get("sampled_at") is not None else None
    if age > 90 or age < -30:
        out["last_health"] = record["health"]
        out["health"] = {key: transition({}, "UNKNOWN", "CACHE_STALE") for key in DIMENSIONS}
        out["overall"] = "UNKNOWN"
    return out
