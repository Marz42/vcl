"""Capability-negotiated, observe-only audit diagnostics, independent of telemetry/v1."""
from __future__ import annotations
import importlib.util
import json
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("vcl_audit_schema", Path(__file__).with_name("schema_validate.py"))
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
STATES = ("OK", "ERROR", "AUTH_FAILED", "UNSUPPORTED", "TIMEOUT")
PROGRESS_STATES = ("UNKNOWN", "COLD", "ADVANCING", "STATIONARY", "REGRESSED", "REPLAYED")


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def clean_progress(value):
    value = value if isinstance(value, dict) else {}
    state = value.get("state")
    delta = value.get("export_seq_delta")
    return {"state": state if state in PROGRESS_STATES else "UNKNOWN",
            "export_seq_delta": delta if type(delta) is int and 0 <= delta <= 2**63 - 1 else None}


def clean_baseline(value, node_id=None, instance_id=None):
    if not isinstance(value, dict):
        return None
    if (not isinstance(value.get("node_id"), str) or not validator.UUID_RE.fullmatch(value["node_id"])
            or not isinstance(value.get("instance_id"), str) or not validator.UUID_RE.fullmatch(value["instance_id"])
            or not validator._is_rfc3339(value.get("observed_at"))
            or (node_id is not None and value["node_id"] != node_id)
            or (instance_id is not None and value["instance_id"] != instance_id)):
        return None
    seq = value.get("export_seq")
    if seq is not None and (type(seq) is not int or not 0 <= seq <= 2**63 - 1):
        return None
    return {key: value.get(key) for key in ("node_id", "instance_id", "observed_at", "export_seq")}


def progression(result, baseline, now):
    """Compare only fresh, ordered snapshots from the same installation.

    Export sequences count closed connections: stationary is valid even while
    last-event time advances. Failed/missing snapshots retain the last baseline.
    """
    baseline = clean_baseline(baseline)
    out = clean_progress(None)
    if result.get("state") != "OK":
        return out, baseline
    snapshot = result["snapshot"]
    if baseline and (baseline["instance_id"] != snapshot["instance_id"] or baseline["node_id"] != snapshot["node_id"]):
        baseline = None
    age = now - timestamp(snapshot["observed_at"])
    if not -30 <= age <= 90:
        return out, baseline
    if baseline and timestamp(snapshot["observed_at"]) <= timestamp(baseline["observed_at"]):
        out["state"] = "REPLAYED"
        return out, baseline
    updated = {key: snapshot[key] for key in ("node_id", "instance_id", "observed_at")}
    updated["export_seq"] = baseline["export_seq"] if baseline else None
    if snapshot["db_state"] != "OK" or snapshot["export_seq"] is None:
        # Even a known corrupt/unknown database advances the replay watermark.
        return out, updated
    if baseline is None or baseline["export_seq"] is None:
        out["state"] = "COLD"
        updated["export_seq"] = snapshot["export_seq"]
        return out, updated
    delta = snapshot["export_seq"] - baseline["export_seq"]
    if delta < 0:
        out["state"] = "REGRESSED"
        # Keep the high-water baseline until a known instance change or recovery.
        return out, updated
    out.update(state="ADVANCING" if delta else "STATIONARY", export_seq_delta=delta)
    updated["export_seq"] = snapshot["export_seq"]
    return out, updated


def clean(result, node_id, instance_id):
    if not isinstance(result, dict) or result.get("state") not in STATES:
        return {"state": "ERROR"}
    if result["state"] != "OK":
        return {"state": result["state"]}
    snapshot = result.get("snapshot")
    if validator.validate_audit_health_v1(snapshot) or snapshot["node_id"] != node_id or snapshot["instance_id"] != instance_id:
        return {"state": "ERROR"}
    return {"state": "OK", "snapshot": dict(snapshot)}


def fetch(node, *, capabilities, instance_id, ssh_json):
    if capabilities.get("state") != "OK":
        return {"state": "AUTH_FAILED" if capabilities.get("state") == "AUTH_FAILED" else "UNSUPPORTED"}
    if "audit-health/v1" not in (capabilities.get("capabilities") or []):
        return {"state": "UNSUPPORTED"}
    state, snapshot, _ = ssh_json(node=node, remote_cmd=["vcl", "telemetry", "audit", "--json"],
                                  require_exit_0=True, max_stdout_bytes=8192)
    if state == "OK":
        try:
            if len(json.dumps(snapshot, allow_nan=False).encode()) > 8192:
                return {"state": "ERROR"}
        except (ValueError, TypeError, RecursionError):
            return {"state": "ERROR"}
    return clean({"state": state, "snapshot": snapshot}, node["node_id"], instance_id)
