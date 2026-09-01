"""Credential-class aware SSH JSON transport for observation (0.5.0)."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable, Literal, Optional

CredentialClass = Literal["observe", "admin"]

AUTH_MARKERS = (
    "permission denied",
    "authentication failed",
    "publickey",
    "no mutual signature",
    "sign_and_send_pubkey",
)


def is_auth_failure(detail: str) -> bool:
    lowered = (detail or "").lower()
    return any(marker in lowered for marker in AUTH_MARKERS)


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
    try:
        payload = json.loads(text)
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
) -> tuple[str, Optional[dict[str, Any]], str]:
    """SSH remote vcl --json with explicit credential class routing.

    Returns ``(state, payload, detail)`` where state is one of
    ``OK``, ``ERROR``, ``AUTH_FAILED``, ``UNSUPPORTED``.

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
        node["ssh_user"],
        int(node.get("ssh_port") or 22),
        remote_cmd,
        **run_kwargs,
    )
    detail = failure_detail(proc)
    if max_stdout_bytes is not None and "stdout exceeds" in (detail or "").lower():
        return (
            "ERROR",
            None,
            f"response exceeds {max_stdout_bytes} bytes",
        )
    if proc.returncode == 255:
        if is_auth_failure(detail):
            return "AUTH_FAILED", None, detail
        return "ERROR", None, detail
    if unsupported_on_missing_command and proc.returncode != 0:
        if is_unsupported_remote(detail, returncode=proc.returncode):
            return "UNSUPPORTED", None, detail
    parse_state, payload, parse_detail = parse_stdout_json(
        proc.stdout, max_stdout_bytes=max_stdout_bytes
    )
    if parse_state != "OK":
        if unsupported_on_missing_command and proc.returncode != 0:
            if is_unsupported_remote(detail, returncode=proc.returncode):
                return "UNSUPPORTED", None, detail
        return "ERROR", None, parse_detail or detail or "remote JSON missing or invalid"
    assert isinstance(payload, dict)
    if require_exit_0 and proc.returncode != 0:
        if unsupported_on_missing_command and is_unsupported_remote(
            detail, returncode=proc.returncode
        ):
            return "UNSUPPORTED", None, detail
        return "ERROR", payload, detail or (f"remote exit {proc.returncode}")
    if proc.returncode != 0:
        return "ERROR", payload, detail or f"remote exit {proc.returncode}"
    return "OK", payload, detail
