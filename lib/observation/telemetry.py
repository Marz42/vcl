"""Fetch and validate Node telemetry/v1 (0.5.0)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Callable, Optional

_sv_path = Path(__file__).resolve().parent / "schema_validate.py"
_sv_spec = importlib.util.spec_from_file_location("observation_schema_validate", _sv_path)
if _sv_spec is None or _sv_spec.loader is None:
    raise RuntimeError(f"cannot load {_sv_path}")
_sv = importlib.util.module_from_spec(_sv_spec)
_sv_spec.loader.exec_module(_sv)
validate_telemetry_v1 = _sv.validate_telemetry_v1

TELEMETRY_SCHEMA = "telemetry/v1"
TELEMETRY_CAPABILITY = "telemetry/v1"
TELEMETRY_MAX_BYTES = 65536
REMOTE_CMD = ["vcl", "telemetry", "snapshot", "--json"]


def fetch_telemetry(
    node: dict[str, Any],
    *,
    capabilities: dict[str, Any],
    ssh_json: Callable[..., tuple[str, Optional[dict[str, Any]], str]],
) -> dict[str, Any]:
    """Negotiate via capabilities, then fetch telemetry/v1."""
    cap_state = capabilities.get("state")
    if cap_state == "UNSUPPORTED":
        return {
            "state": "UNSUPPORTED",
            "schema": TELEMETRY_SCHEMA,
            "detail": capabilities.get("detail") or "capabilities not available",
            "credential_class": "observe",
        }
    if cap_state == "AUTH_FAILED":
        return {
            "state": "AUTH_FAILED",
            "schema": TELEMETRY_SCHEMA,
            "detail": capabilities.get("detail") or "observe auth failed",
            "credential_class": "observe",
        }
    if cap_state != "OK":
        return {
            "state": "ERROR",
            "schema": TELEMETRY_SCHEMA,
            "detail": capabilities.get("detail") or "capability negotiation failed",
            "credential_class": "observe",
        }
    caps = capabilities.get("capabilities")
    if not isinstance(caps, list) or TELEMETRY_CAPABILITY not in caps:
        return {
            "state": "UNSUPPORTED",
            "schema": TELEMETRY_SCHEMA,
            "detail": f"node does not declare {TELEMETRY_CAPABILITY}",
            "credential_class": "observe",
        }
    state, payload, detail = ssh_json(
        node=node,
        remote_cmd=REMOTE_CMD,
        unsupported_on_missing_command=True,
    )
    if state == "UNSUPPORTED":
        return {
            "state": "UNSUPPORTED",
            "schema": TELEMETRY_SCHEMA,
            "detail": detail or "telemetry not available on node",
            "credential_class": "observe",
        }
    if state == "AUTH_FAILED":
        return {
            "state": "AUTH_FAILED",
            "schema": TELEMETRY_SCHEMA,
            "detail": detail,
            "credential_class": "observe",
        }
    if state != "OK" or payload is None:
        return {
            "state": "ERROR",
            "schema": TELEMETRY_SCHEMA,
            "detail": detail or "telemetry fetch failed",
            "credential_class": "observe",
        }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(raw.encode("utf-8")) > TELEMETRY_MAX_BYTES:
        return {
            "state": "ERROR",
            "schema": TELEMETRY_SCHEMA,
            "detail": "telemetry response exceeds size limit",
            "credential_class": "observe",
        }
    errors = validate_telemetry_v1(payload)
    if errors:
        return {
            "state": "ERROR",
            "schema": TELEMETRY_SCHEMA,
            "detail": "; ".join(errors),
            "credential_class": "observe",
        }
    return {
        "state": "OK",
        "schema": TELEMETRY_SCHEMA,
        "credential_class": "observe",
        "snapshot": payload,
    }
