"""Credential-class aware SSH JSON transport for observation (0.5.0)."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable, Literal, Optional

CredentialClass = Literal["observe", "admin"]

AUTH_DENIED_MARKERS = (
    "permission denied",
    "authentication failed",
    "no mutual signature",
    "sign_and_send_pubkey",
)
# "publickey" is deliberately NOT a marker on its own: it also appears in
# ordinary diagnostics ("no matching publickey type", config dumps, protocol
# payloads) and would misclassify them as authentication failures. The real
# OpenSSH rejection text still matches through "permission denied".
AUTH_LIMIT_MARKERS = (
    "too many authentication failures",
)

# Local transport markers. lib/access.py emits these exact strings (through the
# shared helpers below) so nothing downstream has to re-derive them by string
# search on arbitrary remote output.
SSH_TIMEOUT_MARKER = "ssh timed out after"
SCP_TIMEOUT_MARKER = "scp timed out after"
STDOUT_LIMIT_MARKER = "stdout exceeds"
TIMEOUT_MARKERS = (SSH_TIMEOUT_MARKER, SCP_TIMEOUT_MARKER)

CODE_AUTH_LIMIT = "AUTH_LIMIT"
CODE_AUTH_DENIED = "AUTH_DENIED"
CODE_TIMEOUT = "TIMEOUT"
CODE_OUTPUT_LIMIT = "OUTPUT_LIMIT"
CODE_HOST_KEY = "HOST_KEY"
CODE_UNSUPPORTED = "UNSUPPORTED"
CODE_PROTOCOL_INVALID = "PROTOCOL_INVALID"
CODE_REMOTE_ERROR = "REMOTE_ERROR"
CODE_TRANSPORT = "TRANSPORT"
CODE_UNKNOWN = "UNKNOWN"

AUTH_CODES = (CODE_AUTH_LIMIT, CODE_AUTH_DENIED)
RETRYABLE_CODES = (CODE_TIMEOUT, CODE_TRANSPORT)

_HOST_KEY_MARKERS = (
    "host key verification failed",
    "remote host identification has changed",
    "host key mismatch",
)

# Fixed templates: never assembled from remote text, endpoints or identities.
FAILURE_SUMMARIES = {
    CODE_AUTH_LIMIT: (
        "SSH authentication failed: the server exhausted its allowed "
        "authentication attempts"
    ),
    CODE_AUTH_DENIED: (
        "SSH authentication failed: the server rejected the offered identity"
    ),
    CODE_TIMEOUT: "SSH transport timed out",
    CODE_OUTPUT_LIMIT: "SSH response exceeded the configured size limit",
    CODE_HOST_KEY: "SSH host key was not accepted",
    CODE_UNSUPPORTED: "the remote node does not support this command",
    CODE_PROTOCOL_INVALID: "the remote response did not match the expected protocol",
    CODE_REMOTE_ERROR: "the remote command failed",
    CODE_TRANSPORT: "SSH transport failed",
    CODE_UNKNOWN: "SSH failure",
}

# Minimal key-selection diagnosis (FR-03). Phrased as possible causes, never as
# an assertion about the operator's environment.
KEY_SELECTION_HINTS = {
    CODE_AUTH_LIMIT: (
        "select an explicit agent public key for this node and retry with "
        "IdentitiesOnly=yes; offering many agent keys can exhaust the "
        "server's authentication attempts"
    ),
    CODE_AUTH_DENIED: (
        "select the explicit agent public key authorized for this node and "
        "retry with IdentitiesOnly=yes"
    ),
}


def timeout_message(timeout: float) -> str:
    return f"{SSH_TIMEOUT_MARKER} {timeout}s"


def scp_timeout_message(timeout: float) -> str:
    return f"{SCP_TIMEOUT_MARKER} {timeout}s"


def output_limit_message(max_stdout_bytes: int) -> str:
    return f"{STDOUT_LIMIT_MARKER} {max_stdout_bytes} bytes"


def auth_failure_reason(detail: str) -> Optional[str]:
    """``AUTH_LIMIT`` / ``AUTH_DENIED`` / ``None`` for a transport detail."""
    lowered = (detail or "").lower()
    if any(marker in lowered for marker in AUTH_LIMIT_MARKERS):
        return CODE_AUTH_LIMIT
    if any(marker in lowered for marker in AUTH_DENIED_MARKERS):
        return CODE_AUTH_DENIED
    return None


def is_auth_failure(detail: str) -> bool:
    return auth_failure_reason(detail) is not None


def classify_failure(
    *,
    phase: str,
    detail: str,
    returncode: Optional[int],
    unsupported: bool = False,
    protocol_invalid: bool = False,
) -> dict[str, Any]:
    """Structured failure facts (FR-04): phase/code/state/retryable/summary.

    Local transport facts (timeout, output limit) are recognised first from the
    markers emitted by lib/access.py, then remote protocol/error text.
    """
    lowered = (detail or "").lower()
    code = CODE_UNKNOWN
    auth_reason = auth_failure_reason(detail)
    # Local transport facts first: a timeout that carried partial remote text
    # is still a timeout, not whatever the partial text happens to say.
    if any(marker in lowered for marker in TIMEOUT_MARKERS):
        code = CODE_TIMEOUT
    elif STDOUT_LIMIT_MARKER in lowered:
        code = CODE_OUTPUT_LIMIT
    elif auth_reason is not None:
        code = auth_reason
    elif any(marker in lowered for marker in _HOST_KEY_MARKERS):
        code = CODE_HOST_KEY
    elif unsupported:
        code = CODE_UNSUPPORTED
    elif protocol_invalid:
        code = CODE_PROTOCOL_INVALID
    elif returncode == 255:
        # OpenSSH's own failure exit: connect, host-key, DNS, pipe. It is a
        # transport failure, never a remote command error.
        code = CODE_TRANSPORT
    elif returncode not in (0, None):
        code = CODE_REMOTE_ERROR
    elif detail:
        code = CODE_TRANSPORT
    if code in AUTH_CODES:
        state = "AUTH_FAILED"
    elif code == CODE_TIMEOUT:
        state = "TIMEOUT"
    elif code == CODE_UNSUPPORTED:
        state = "UNSUPPORTED"
    else:
        state = "ERROR"
    facts: dict[str, Any] = {
        "phase": phase,
        "code": code,
        "state": state,
        "retryable": code in RETRYABLE_CODES,
        "summary": FAILURE_SUMMARIES[code],
    }
    hint = KEY_SELECTION_HINTS.get(code)
    if hint:
        facts["hint"] = hint
    return facts


def phase_for_command(remote_cmd: Optional[list[str]]) -> str:
    """Map a remote vcl argv to a stable phase name."""
    parts = [str(part) for part in (remote_cmd or []) if str(part) != "--json"]
    if len(parts) < 2:
        return "transport"
    verb = parts[1]
    if verb == "audit":
        return "audit_export" if "export" in parts else "audit"
    if verb in ("user", "users"):
        return "users"
    return {
        "identity": "identity",
        "status": "status",
        "capabilities": "capabilities",
        "verify": "verify",
        "inspect": "inspect",
        "telemetry": "telemetry",
    }.get(verb, "remote")


def machine_failure_facts(
    facts: dict[str, Any],
    *,
    node_id: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> dict[str, Any]:
    """Machine contract view: keeps logical identity next to the codes.

    The summary stays shareable (no endpoint, no logical identity); this view
    is not by itself a "shareable report".
    """
    doc: dict[str, Any] = {
        key: facts[key]
        for key in ("phase", "code", "state", "retryable", "summary")
        if key in facts
    }
    if node_id is not None:
        doc["node_id"] = node_id
    if instance_id is not None:
        doc["instance_id"] = instance_id
    return doc


def operator_failure_text(facts: dict[str, Any]) -> str:
    """Fixed-template operator text: summary plus the optional hint."""
    text = str(facts.get("summary") or FAILURE_SUMMARIES[CODE_UNKNOWN])
    hint = facts.get("hint")
    if hint:
        text = f"{text}\nnext: {hint}"
    return text


def is_unsupported_remote(detail: str, *, returncode: int) -> bool:
    if returncode == 127:
        return True
    lowered = (detail or "").lower()
    # Node 0.3.x: "Unknown command: capabilities. Run 'vcl help'."
    # fake-ssh / some paths: "unknown vcl command: …"
    return (
        "unknown vcl command" in lowered
        or "unknown command:" in lowered
        or "command not found" in lowered
    )


def raw_stdout_byte_len(stdout: Optional[str]) -> int:
    """UTF-8 byte length of raw SSH stdout (no strip — padding counts)."""
    return len((stdout or "").encode("utf-8"))


def parse_stdout_json(
    stdout: Optional[str],
    *,
    max_stdout_bytes: Optional[int] = None,
) -> tuple[str, Optional[Any], str]:
    """Parse JSON from SSH stdout with optional raw-size gate before loads.

    Returns ``(state, payload, detail)`` where state is ``OK`` or ``ERROR``.
    """
    raw = stdout or ""
    if max_stdout_bytes is not None:
        nbytes = len(raw.encode("utf-8"))
        if nbytes > max_stdout_bytes:
            return (
                "ERROR",
                None,
                f"response exceeds {max_stdout_bytes} bytes (raw {nbytes})",
            )
    text = raw.strip()
    if not text:
        return "ERROR", None, "remote JSON missing or invalid"

    def _reject_nonfinite(name: str) -> None:
        raise json.JSONDecodeError(f"non-finite JSON number: {name}", text, 0)

    try:
        payload = json.loads(text, parse_constant=_reject_nonfinite)
    except json.JSONDecodeError:
        return "ERROR", None, "remote JSON missing or invalid"
    if not isinstance(payload, dict):
        return "ERROR", None, "remote JSON missing or invalid"
    return "OK", payload, ""


def ssh_remote_json_for_class(
    *,
    node: dict[str, Any],
    remote_cmd: list[str],
    credential_class: CredentialClass,
    ssh_run: Callable[..., subprocess.CompletedProcess[str]],
    identity_for_class: Callable[[dict[str, Any], CredentialClass], Optional[str]],
    failure_detail: Callable[[subprocess.CompletedProcess[str]], str],
    timeout: float = 20.0,
    extra: Optional[list[str]] = None,
    require_exit_0: bool = False,
    unsupported_on_missing_command: bool = False,
    max_stdout_bytes: Optional[int] = None,
    facts: Optional[dict[str, Any]] = None,
) -> tuple[str, Optional[dict[str, Any]], str]:
    """SSH remote vcl --json with explicit credential class routing.

    Returns ``(state, payload, detail)`` where state is one of
    ``OK``, ``ERROR``, ``AUTH_FAILED``, ``UNSUPPORTED``.

    ``detail`` is the safe, fixed-template operator text for authentication
    failures; raw remote text is never echoed back as the user-facing detail.
    Pass ``facts`` to receive the structured classification (FR-04).

    When ``max_stdout_bytes`` is set, SSH capture is bounded and raw UTF-8
    length is checked before ``json.loads`` (whitespace padding cannot bypass).
    """
    run_kwargs: dict[str, Any] = {
        "batch": True,
        "extra": extra,
        "identity_file": identity_for_class(node, credential_class),
        "timeout": timeout,
    }
    if max_stdout_bytes is not None:
        run_kwargs["max_stdout_bytes"] = max_stdout_bytes
    proc = ssh_run(
        node["ssh_host"],
        node.get("observe_ssh_user", node["ssh_user"]) if credential_class == "observe" else node["ssh_user"],
        int(node.get("ssh_port") or 22),
        remote_cmd,
        **run_kwargs,
    )
    raw_detail = failure_detail(proc)
    classified = classify_failure(
        phase=phase_for_command(remote_cmd),
        detail=raw_detail,
        returncode=proc.returncode,
    )
    if facts is not None:
        facts.clear()
        facts.update(classified)
    if max_stdout_bytes is not None and STDOUT_LIMIT_MARKER in (raw_detail or "").lower():
        return (
            "ERROR",
            None,
            f"response exceeds {max_stdout_bytes} bytes",
        )
    if proc.returncode == 255:
        # Every ssh-level failure returns a fixed summary: the operator text
        # must never carry the endpoint, a logical identity or remote text.
        if is_auth_failure(raw_detail):
            return "AUTH_FAILED", None, classified["summary"]
        return "ERROR", None, classified["summary"]
    if unsupported_on_missing_command and proc.returncode != 0:
        if is_unsupported_remote(raw_detail, returncode=proc.returncode):
            return "UNSUPPORTED", None, raw_detail
    parse_state, payload, parse_detail = parse_stdout_json(
        proc.stdout, max_stdout_bytes=max_stdout_bytes
    )
    if parse_state != "OK":
        if unsupported_on_missing_command and proc.returncode != 0:
            if is_unsupported_remote(raw_detail, returncode=proc.returncode):
                return "UNSUPPORTED", None, raw_detail
        return (
            "ERROR",
            None,
            parse_detail or raw_detail or "remote JSON missing or invalid",
        )
    assert isinstance(payload, dict)
    if require_exit_0 and proc.returncode != 0:
        if unsupported_on_missing_command and is_unsupported_remote(
            raw_detail, returncode=proc.returncode
        ):
            return "UNSUPPORTED", None, raw_detail
        return "ERROR", payload, raw_detail or (f"remote exit {proc.returncode}")
    if proc.returncode != 0:
        return "ERROR", payload, raw_detail or f"remote exit {proc.returncode}"
    return "OK", payload, raw_detail
