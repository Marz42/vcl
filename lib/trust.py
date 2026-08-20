"""Host-key trust seam (0.4.0 B3).

Loaded as a controller sibling via _load_controller_sibling — never import
this module from sys.path. Call bind(host) before use so die / ssh_keyscan_bin /
SSH_KEYSCAN_TIMEOUT_SECONDS / stdin_is_tty resolve from the fleet host module.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

_host: Any = None

HOST_KEY_TYPES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "ssh-dss",
)
HOST_KEY_FP_BODY_RE = re.compile(r"^[A-Za-z0-9+/]+$")
NONINTERACTIVE_HOST_KEY_MSG = "non-interactive add requires --host-key SHA256:..."


def bind(host: Any) -> None:
    global _host
    _host = host


def default_known_hosts_path() -> Path:
    return Path.home() / ".ssh" / "known_hosts"


def normalize_fingerprint(value: str) -> str:
    raw = (value or "").strip()
    if not raw.startswith("SHA256:"):
        _host.die("invalid --host-key: expected SHA256:<base64>")
    body = raw[len("SHA256:") :].replace("=", "")
    if not body or not HOST_KEY_FP_BODY_RE.fullmatch(body):
        _host.die("invalid --host-key: expected SHA256:<base64>")
    return "SHA256:" + body


def _key_blob_from_line(raw_key_line: str) -> bytes:
    parts = raw_key_line.split()
    blob_b64 = None
    for i, part in enumerate(parts):
        if part in HOST_KEY_TYPES and i + 1 < len(parts):
            blob_b64 = parts[i + 1]
            break
    if not blob_b64:
        raise ValueError(f"cannot parse host key line: {raw_key_line}")
    pad = "=" * ((4 - len(blob_b64) % 4) % 4)
    return base64.b64decode(blob_b64 + pad)


def fingerprint_sha256(raw_key_line: str) -> str:
    """OpenSSH SHA256 fingerprint of a known_hosts / keyscan line.

    Hashlib of the key blob is the CI-stable implementation. Matches
    `ssh-keygen -l` display form SHA256:... (unpadded standard base64).
    """
    blob = _key_blob_from_line(raw_key_line)
    digest = hashlib.sha256(blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def candidate_host_keys(host: str, port: int) -> list[str]:
    """ssh-keyscan candidates only. Empty on failure; never means verified."""
    argv = [_host.ssh_keyscan_bin(), "-p", str(port), "-T", "5", host]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_host.SSH_KEYSCAN_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    lines: list[str] = []
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def append_known_hosts(line: str) -> None:
    path = default_known_hosts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    existing = ""
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        present = {row.strip() for row in existing.splitlines() if row.strip()}
        if line.strip() in present:
            return
    with path.open("a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write(line.rstrip("\n") + "\n")
    os.chmod(path, 0o600)


def pin_host_key(host: str, port: int, host_key: str) -> None:
    expected = normalize_fingerprint(host_key)
    matched = None
    for line in candidate_host_keys(host, port):
        try:
            fp = fingerprint_sha256(line)
        except (ValueError, OSError):
            continue
        if fp == expected:
            matched = line
            break
    if matched is None:
        _host.die("host key mismatch")
    append_known_hosts(matched)


def prepare_ssh_host_key(
    host: str,
    port: int,
    host_key: Optional[str],
) -> tuple[Optional[list[str]], bool]:
    """Return (extra ssh -o args, batch). Never weakens host-key checking.

    --host-key: keyscan is candidate acquisition only; fingerprint match
    writes the user default known_hosts, then StrictHostKeyChecking=yes.
    No --host-key on a TTY: no BatchMode, OpenSSH prompts. Non-TTY without
    --host-key is refused; keyscan alone never makes add succeed.
    """
    if host_key:
        pin_host_key(host, port, host_key)
        return ["-o", "StrictHostKeyChecking=yes"], True
    if not _host.stdin_is_tty():
        _host.die(NONINTERACTIVE_HOST_KEY_MSG)
    return None, False
