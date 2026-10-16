"""Bounded observe-only user samples and pure per-user anomaly assessment."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import re
from pathlib import Path


def sibling(name):
    spec = importlib.util.spec_from_file_location("vcl_user_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator, stats = sibling("schema_validate"), sibling("anomalies")
TYPES = ("USER_TRAFFIC_SPIKE", "USER_CONNECTION_SPIKE", "SUSTAINED_TRAFFIC_ANOMALY")
REASONS = stats.REASONS + ("DB_UNAVAILABLE", "UNSUPPORTED", "RETENTION_CHANGED", "COUNTER_RESET")
TRANSPORT_STATES = ("OK", "ERROR", "AUTH_FAILED", "UNSUPPORTED", "TIMEOUT")


def clean(result, node_id, instance_id):
    if not isinstance(result, dict) or result.get("state") not in TRANSPORT_STATES:
        return {"state": "ERROR"}
    if result["state"] != "OK":
        return {"state": result["state"]}
    snapshot = result.get("snapshot")
    if (validator.validate_user_traffic_v1(snapshot) or snapshot["node_id"] != node_id
            or snapshot["instance_id"] != instance_id):
        return {"state": "ERROR"}
    return {"state": "OK", "snapshot": {**snapshot, "users": [dict(row) for row in snapshot["users"]]}}


def fetch(node, *, capabilities, instance_id, ssh_json):
    if capabilities.get("state") != "OK" or "user-traffic/v1" not in (capabilities.get("capabilities") or []):
        return {"state": "UNSUPPORTED"}
    state, snapshot, _ = ssh_json(node=node, remote_cmd=["vcl", "telemetry", "users", "--json"],
                                 require_exit_0=True, max_stdout_bytes=32768)
    if state == "OK":
        try:
            if len(json.dumps(snapshot, allow_nan=False).encode()) > 32768:
                return {"state": "ERROR"}
        except (ValueError, TypeError, RecursionError):
            return {"state": "ERROR"}
    return clean({"state": state, "snapshot": snapshot}, node["node_id"], instance_id)


def clean_summary(value):
    value = value if isinstance(value, dict) else {}
    out = stats.clean_summary(value)
    if isinstance(value.get("reason"), str) and value["reason"] in REASONS:
        out["reason"] = value["reason"]
    return out


def clean_state(value):
    value = value if isinstance(value, dict) else {}
    key = value.get("instance_key")
    return {"instance_key": key if isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key) else None,
            **{key: stats.number(value.get(key)) for key in ("observed_at", "sampled_at")},
            **{key: value[key] if type(value.get(key)) is int and stats.number(value[key]) is not None else None for key in ("retained_bytes", "watermark")},
            "traffic": stats.clean_series(value.get("traffic")), "connections": stats.clean_series(value.get("connections"))}


def evaluate(snapshot, profile, previous, now, active=()):
    state = clean_state(previous)
    checks = {key: (None, {}) for key in TYPES}
    def unknown(reason, break_interval=True):
        # Every evidence gap breaks a pending sustained interval; ACTIVE still remains open.
        if break_interval:
            state["traffic"]["above_since"] = None
        return checks, state, {key: {"reason": reason} for key in TYPES}
    if not isinstance(snapshot, dict) or validator.validate_user_traffic_v1(snapshot):
        return unknown("UNSUPPORTED" if snapshot is None else "MISSING")
    observed, sampled = stats.timestamp(snapshot["observed_at"]), stats.timestamp(snapshot["sampled_at"])
    if snapshot["state"] not in ("OK", "PARTIAL"):
        return unknown("DB_UNAVAILABLE")
    if (observed is None or sampled is None or not -30 <= now - observed <= 90 or not -30 <= now - sampled <= 90
            or snapshot["heartbeat_age_seconds"] + max(0, now - observed) > 90):
        return unknown("STALE")
    instance = hashlib.sha256(snapshot["instance_id"].encode()).hexdigest()
    reset = instance != state["instance_key"]
    if reset:
        state = clean_state(None)
    elif state["observed_at"] is not None and observed <= state["observed_at"]:
        return unknown("NO_NEW_SAMPLE", observed < state["observed_at"])
    state.update(instance_key=instance, observed_at=observed)
    if not isinstance(profile, dict) or profile not in snapshot["users"]:
        return unknown("MISSING")
    if state["sampled_at"] is not None and sampled <= state["sampled_at"]:
        return unknown("NO_NEW_SAMPLE")
    before_at, before_bytes = state["sampled_at"], state["retained_bytes"]
    watermark = snapshot["pruned_max_export_seq"]
    reason = None
    if state["watermark"] is not None and state["watermark"] != watermark:
        reason = "RETENTION_CHANGED"
    elif before_bytes is not None and profile["retained_bytes"] < before_bytes:
        reason = "COUNTER_RESET"
    elif before_at is not None and sampled - before_at > stats.MAX_GAP:
        reason = "RESET"
    if reset or reason:
        state.update(traffic=stats.clean_series(None), connections=stats.clean_series(None))
    state.update(sampled_at=sampled, retained_bytes=profile["retained_bytes"], watermark=watermark)
    if reason:
        return unknown(reason)
    rate = (profile["retained_bytes"] - before_bytes) / (sampled - before_at) if before_at is not None and before_bytes is not None and not reset else None
    signal, state["traffic"], traffic = stats.series(rate, sampled, state["traffic"], floor=stats.NETWORK_FLOOR,
        active=any(key in active for key in ("USER_TRAFFIC_SPIKE", "SUSTAINED_TRAFFIC_ANOMALY")))
    signal_connections, state["connections"], connections = stats.series(profile["connections"], sampled,
        state["connections"], floor=20, active="USER_CONNECTION_SPIKE" in active)
    sustained = None if signal is None else signal and ("SUSTAINED_TRAFFIC_ANOMALY" in active or traffic["above_seconds"] >= 300)
    summaries = {"USER_TRAFFIC_SPIKE": clean_summary(traffic), "USER_CONNECTION_SPIKE": clean_summary(connections),
                 "SUSTAINED_TRAFFIC_ANOMALY": clean_summary(traffic)}
    for key, value in (("USER_TRAFFIC_SPIKE", signal), ("USER_CONNECTION_SPIKE", signal_connections),
                       ("SUSTAINED_TRAFFIC_ANOMALY", sustained)):
        checks[key] = (value, {key: val for key, val in summaries[key].items() if key != "reason"})
    return checks, state, summaries
