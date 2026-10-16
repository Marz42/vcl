"""Identity-bound inspect/v1 over the explicit observe transport."""
import importlib.util
import json
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location("vcl_inspect_contract", Path(__file__).resolve().parents[1] / "inspect_snapshot.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)
REMOTE_CMD = ["vcl", "inspect", "--json"]
IDENTITY_CMD = ["vcl", "identity", "--json"]
TRANSPORT_STATES = ("OK", "ERROR", "AUTH_FAILED", "UNSUPPORTED", "TIMEOUT")


def clean(value, node_id, instance_id):
    if not isinstance(value, dict) or value.get("state") not in TRANSPORT_STATES:
        return {"state": "ERROR"}
    if value["state"] != "OK":
        return {"state": value["state"]}
    snapshot = value.get("snapshot")
    if (contract.validate(snapshot) or snapshot["node_id"] != node_id or snapshot["instance_id"] != instance_id
            or node_id is None or instance_id is None):
        return {"state": "ERROR"}
    return {"state": "OK", "snapshot": json.loads(json.dumps(snapshot, allow_nan=False))}


def fetch(node, *, capabilities, ssh_json):
    """Caller owns one shared deadline for negotiation, snapshot and identity."""
    if capabilities.get("state") != "OK":
        state = capabilities.get("state")
        return {"state": state if state in TRANSPORT_STATES and state != "OK" else "ERROR"}
    if not isinstance(capabilities.get("capabilities"), list) or "inspect/v1" not in capabilities["capabilities"]:
        return {"state": "UNSUPPORTED"}
    try:
        state, snapshot, _ = ssh_json(node=node, remote_cmd=REMOTE_CMD, credential_class="observe",
            unsupported_on_missing_command=True, max_stdout_bytes=contract.MAX_BYTES)
        if state != "OK" or contract.validate(snapshot):
            return {"state": state if state in TRANSPORT_STATES and state != "OK" else "ERROR"}
        state, identity, _ = ssh_json(node=node, remote_cmd=IDENTITY_CMD, credential_class="observe", max_stdout_bytes=4096)
        if state != "OK":
            return {"state": state if state in TRANSPORT_STATES else "ERROR"}
        if not isinstance(identity, dict) or identity.get("node_id") != node.get("node_id"):
            return {"state": "ERROR"}
        return clean({"state": "OK", "snapshot": snapshot}, node.get("node_id"), identity.get("instance_id"))
    except subprocess.TimeoutExpired:
        return {"state": "TIMEOUT"}
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {"state": "ERROR"}
