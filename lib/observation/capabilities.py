"""Fetch and validate Node capabilities/v1 (0.5.0)."""

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
validate_capabilities_v1 = _sv.validate_capabilities_v1

CAPABILITIES_SCHEMA = "capabilities/v1"
CAPABILITIES_MAX_BYTES = 4096
REMOTE_CMD = ["vcl", "capabilities", "--json"]


def fetch_capabilities(
    node: dict[str, Any],
    *,
    ssh_json: Callable[..., tuple[str, Optional[dict[str, Any]], str]],
) -> dict[str, Any]:
    """Return a structured observation result for capabilities/v1."""
    state, payload, detail = ssh_json(
        node=node,
        remote_cmd=REMOTE_CMD,
        unsupported_on_missing_command=True,
        max_stdout_bytes=CAPABILITIES_MAX_BYTES,
    )
    if state == "UNSUPPORTED":
        return {
            "state": "UNSUPPORTED",
            "schema": CAPABILITIES_SCHEMA,
            "detail": detail or "capabilities not available on node",
            "credential_class": "observe",
        }
    if state == "AUTH_FAILED":
        return {
            "state": "AUTH_FAILED",
            "schema": CAPABILITIES_SCHEMA,
            "detail": detail,
            "credential_class": "observe",
        }
    if state != "OK" or payload is None:
        return {
            "state": "ERROR",
            "schema": CAPABILITIES_SCHEMA,
            "detail": detail or "capabilities fetch failed",
            "credential_class": "observe",
        }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(raw.encode("utf-8")) > CAPABILITIES_MAX_BYTES:
        return {
            "state": "ERROR",
            "schema": CAPABILITIES_SCHEMA,
            "detail": "capabilities response exceeds size limit",
            "credential_class": "observe",
        }
    # Transport already enforced raw UTF-8 size; keep canonical re-check.
    errors = validate_capabilities_v1(payload)
    if errors:
        return {
            "state": "ERROR",
            "schema": CAPABILITIES_SCHEMA,
            "detail": "; ".join(errors),
            "credential_class": "observe",
        }
    return {
        "state": "OK",
        "schema": CAPABILITIES_SCHEMA,
        "credential_class": "observe",
        "node_version": payload.get("node_version"),
        "capabilities": list(payload.get("capabilities") or []),
        "raw": payload,
    }


def node_declares_capability(result: dict[str, Any], capability: str) -> bool:
    if result.get("state") != "OK":
        return False
    caps = result.get("capabilities")
    if not isinstance(caps, list):
        return False
    return capability in caps
