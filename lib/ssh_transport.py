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


def _stdout_json(proc: subprocess.CompletedProcess[str]) -> Optional[Any]:
    text = (proc.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


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
) -> tuple[str, Optional[dict[str, Any]], str]:
    """SSH remote vcl --json with explicit credential class routing.

    Returns ``(state, payload, detail)`` where state is one of
    ``OK``, ``ERROR``, ``AUTH_FAILED``, ``UNSUPPORTED``.
    """
    proc = ssh_run(
        node["ssh_host"],
        node["ssh_user"],
        int(node.get("ssh_port") or 22),
        remote_cmd,
        batch=True,
        extra=extra,
        identity_file=identity_for_class(node, credential_class),
        timeout=timeout,
    )
    detail = failure_detail(proc)
    if proc.returncode == 255:
        if is_auth_failure(detail):
            return "AUTH_FAILED", None, detail
        return "ERROR", None, detail
    if unsupported_on_missing_command and proc.returncode != 0:
        if is_unsupported_remote(detail, returncode=proc.returncode):
            return "UNSUPPORTED", None, detail
    payload = _stdout_json(proc)
    if require_exit_0 and proc.returncode != 0:
        if unsupported_on_missing_command and is_unsupported_remote(
            detail, returncode=proc.returncode
        ):
            return "UNSUPPORTED", None, detail
        return "ERROR", payload if isinstance(payload, dict) else None, detail or (
            f"remote exit {proc.returncode}"
        )
    if not isinstance(payload, dict):
        if unsupported_on_missing_command and proc.returncode != 0:
            if is_unsupported_remote(detail, returncode=proc.returncode):
                return "UNSUPPORTED", None, detail
        return "ERROR", None, detail or "remote JSON missing or invalid"
    if proc.returncode != 0:
        return "ERROR", payload, detail or f"remote exit {proc.returncode}"
    return "OK", payload, detail
