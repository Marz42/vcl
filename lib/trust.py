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
import tempfile
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
    # Legacy seam name kept for tests; workspace trust when manifest present.
    if _host.workspace_trust_active():
        return _host.known_hosts_path()
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


TRUST_MIGRATION_REQUIRED = "TRUST_MIGRATION_REQUIRED"


def _ssh_keygen_find_host(marker: str, src: Path) -> list[str]:
    """Return non-comment known_hosts lines for marker via ssh-keygen -F."""
    if not src.is_file():
        return []
    argv = ["ssh-keygen", "-F", marker, "-f", str(src)]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10,
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


def extract_fleet_host_trust(
    nodes: list[dict], src: Path, dest: Path
) -> dict[str, Any]:
    """Extract Fleet-only host entries from an existing known_hosts.

    Uses ssh-keygen -F for host / [host]:port (incl. hashed). Never keyscan.
    If any node yields zero lines, warnings include TRUST_MIGRATION_REQUIRED.
    """
    matched: list[str] = []
    missing_hosts: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    src_path = Path(src)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        host = _host._optional_text(node.get("ssh_host"))
        if not host:
            continue
        port_raw = node.get("ssh_port", 22)
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            port = 22
        found: list[str] = []
        for marker in (host, f"[{host}]:{port}"):
            for line in _ssh_keygen_find_host(marker, src_path):
                if line not in seen:
                    seen.add(line)
                    found.append(line)
                    matched.append(line)
        if not found:
            missing_hosts.append(host)
    if missing_hosts:
        warnings.append(TRUST_MIGRATION_REQUIRED)
    dest_path = Path(dest)
    parent = dest_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    payload = ""
    if matched:
        payload = "\n".join(matched) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix=".known_hosts.", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest_path)
        os.chmod(dest_path, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {
        "matched": matched,
        "missing_hosts": missing_hosts,
        "warnings": warnings,
    }
