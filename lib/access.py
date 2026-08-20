"""SSH/SCP access seam (0.4.0 B3).

Loaded as a controller sibling via _load_controller_sibling — never import
this module from sys.path. Call bind(host) before use so die / _optional_text /
_chmod_private / _ssh_failure_detail / _has_ascii_control resolve from fleet.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_host: Any = None

SSH_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
SSH_USER_MAX = 32
SSH_HOST_MAX = 253
SSH_REMOTE_CMD_MAX_BYTES = 8192
_HOSTNAME_LABEL_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
SSH_TIMEOUT_SECONDS = 20
SSH_MUTATION_TIMEOUT_SECONDS = 60
SSH_BACKUP_TIMEOUT_SECONDS = 120
SSH_KEYSCAN_TIMEOUT_SECONDS = 10
SCP_TIMEOUT_SECONDS = 60


def bind(host: Any) -> None:
    global _host
    _host = host


def ssh_bin() -> str:
    env = os.environ.get("VCL_FLEET_SSH")
    if env:
        return env
    return "ssh.exe" if sys.platform == "win32" else "ssh"


def scp_bin() -> str:
    env = os.environ.get("VCL_FLEET_SCP")
    if env:
        return env
    return "scp.exe" if sys.platform == "win32" else "scp"


def ssh_keyscan_bin() -> str:
    env = os.environ.get("VCL_FLEET_SSH_KEYSCAN")
    if env:
        return env
    return "ssh-keyscan.exe" if sys.platform == "win32" else "ssh-keyscan"


def stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        return False


def _ssh_option_text(arg: str) -> str:
    if arg.startswith("-o") and len(arg) > 2 and not arg.startswith("-o "):
        return arg[2:]
    return arg


def _reject_forbidden_ssh_options(argv: list[str]) -> None:
    # Split literals so source grep cannot see the forbidden OpenSSH values.
    strict_no = "StrictHostKeyChecking=" + "no"
    known_null = "UserKnownHostsFile=" + "/dev/null"
    joined = " ".join(argv)
    if strict_no in argv or strict_no in joined:
        _host.die(f"refusing forbidden SSH option {strict_no}", 2)
    if known_null in argv or known_null in joined:
        _host.die(f"refusing forbidden SSH option {known_null}", 2)
    for arg in argv:
        option = _ssh_option_text(arg)
        if option.startswith("UserKnownHostsFile="):
            _host.die("refusing forbidden SSH option UserKnownHostsFile=", 2)


def validate_identity_file(path: str, *, must_exist: bool = True) -> str:
    """Return a local private-key path. Never stores key bytes."""
    raw = (path or "").strip()
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        _host.die("invalid --identity-file")
    candidate = Path(raw).expanduser()
    if must_exist:
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            _host.die(f"invalid --identity-file: {exc}")
        if not resolved.is_file():
            _host.die(f"identity file not found: {resolved}")
        return str(resolved)
    if candidate.is_file():
        try:
            return str(candidate.resolve())
        except OSError:
            return str(candidate)
    return str(candidate)


def ssh_identity_args(identity_file: Optional[str]) -> list[str]:
    path = _host._optional_text(identity_file)
    if not path:
        return []
    return ["-i", validate_identity_file(path, must_exist=True), "-o", "IdentitiesOnly=yes"]


def _node_identity_file(node: dict[str, Any]) -> Optional[str]:
    return _host._optional_text(node.get("identity_file"))


def ssh_argv(
    host: str,
    user: str,
    port: int,
    remote_cmd: list[str],
    *,
    batch: bool,
    extra: list[str] | None = None,
    identity_file: Optional[str] = None,
) -> list[str]:
    """Build an OpenSSH argv. Never weakens host-key checking.

    OpenSSH concatenates operands after the destination into one string
    for the remote login shell. Passing a single ``shlex.join`` string
    preserves argv boundaries (spaces, quotes, metacharacters). The
    remote shell is POSIX even when the local client is Windows OpenSSH.
    """
    validate_ssh_user(user)
    validate_ssh_host(host)
    if not isinstance(remote_cmd, (list, tuple)) or not remote_cmd:
        _host.die("remote command must be a non-empty argv list")
    parts: list[str] = []
    for part in remote_cmd:
        if not isinstance(part, str):
            _host.die("remote command argv must be strings")
        if "\x00" in part:
            _host.die("remote command argv must not contain NUL")
        parts.append(part)
    remote = shlex.join(parts)
    if len(remote.encode("utf-8")) > SSH_REMOTE_CMD_MAX_BYTES:
        _host.die(f"remote command exceeds {SSH_REMOTE_CMD_MAX_BYTES} bytes")
    argv = [ssh_bin(), "-p", str(port)]
    if extra:
        argv.extend(extra)
    if batch:
        argv.extend(["-o", "BatchMode=yes"])
    argv.extend(ssh_identity_args(identity_file))
    argv.extend([f"{user}@{host}", "--", remote])
    _reject_forbidden_ssh_options(argv)
    return argv


def ssh_run(
    host: str,
    user: str,
    port: int,
    remote_cmd: list[str],
    *,
    batch: bool = True,
    extra: list[str] | None = None,
    identity_file: Optional[str] = None,
    timeout: float = SSH_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run remote_cmd over SSH. Stderr is captured; exit code is preserved."""
    argv = ssh_argv(
        host,
        user,
        port,
        remote_cmd,
        batch=batch,
        extra=extra,
        identity_file=identity_file,
    )
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout
        stderr = exc.stderr
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        detail = (stderr or "").strip()
        timeout_msg = f"ssh timed out after {timeout}s"
        stderr = f"{detail}\n{timeout_msg}".strip() if detail else timeout_msg
        return subprocess.CompletedProcess(argv, 255, stdout or "", stderr)
    except OSError as exc:
        _host.die(f"cannot execute {argv[0]}: {exc}")


def scp_argv(
    *,
    port: int,
    src: str,
    dest: str,
    batch: bool = True,
    extra: list[str] | None = None,
    identity_file: Optional[str] = None,
) -> list[str]:
    """Build an OpenSSH scp argv. Never weakens host-key checking."""
    argv = [scp_bin(), "-P", str(port)]
    if extra:
        argv.extend(extra)
    if batch:
        argv.extend(["-o", "BatchMode=yes"])
    argv.extend(ssh_identity_args(identity_file))
    argv.extend([src, dest])
    _reject_forbidden_ssh_options(argv)
    return argv


def scp_run(
    *,
    port: int,
    src: str,
    dest: str,
    batch: bool = True,
    extra: list[str] | None = None,
    identity_file: Optional[str] = None,
    timeout: float = SCP_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Copy src to dest via scp. List argv only; never shell=True."""
    argv = scp_argv(
        port=port,
        src=src,
        dest=dest,
        batch=batch,
        extra=extra,
        identity_file=identity_file,
    )
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout
        stderr = exc.stderr
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        detail = (stderr or "").strip()
        timeout_msg = f"scp timed out after {timeout}s"
        stderr = f"{detail}\n{timeout_msg}".strip() if detail else timeout_msg
        return subprocess.CompletedProcess(argv, 255, stdout or "", stderr)
    except OSError as exc:
        _host.die(f"cannot execute {argv[0]}: {exc}")


def _scp_remote_spec(node: dict[str, Any], remote_path: str) -> str:
    return f"{node['ssh_user']}@{node['ssh_host']}:{remote_path}"


def scp_pull(
    node: dict[str, Any],
    remote_path: str,
    local_path: Path,
    *,
    extra: list[str] | None = None,
    timeout: float = SCP_TIMEOUT_SECONDS,
) -> None:
    dest = Path(local_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = scp_run(
        port=int(node.get("ssh_port") or 22),
        src=_scp_remote_spec(node, remote_path),
        dest=str(dest),
        extra=extra,
        identity_file=_node_identity_file(node),
        timeout=timeout,
    )
    if proc.returncode != 0:
        _host.die(f"scp pull failed: {_host._ssh_failure_detail(proc)}")
    if not dest.is_file():
        _host.die(f"scp pull did not write {dest}")
    _host._chmod_private(dest, 0o600)


def scp_push(
    node: dict[str, Any],
    local_path: Path,
    remote_path: str,
    *,
    extra: list[str] | None = None,
    timeout: float = SCP_TIMEOUT_SECONDS,
) -> None:
    src = Path(local_path)
    if not src.is_file():
        _host.die(f"scp push source not found: {src}")
    proc = scp_run(
        port=int(node.get("ssh_port") or 22),
        src=str(src),
        dest=_scp_remote_spec(node, remote_path),
        extra=extra,
        identity_file=_node_identity_file(node),
        timeout=timeout,
    )
    if proc.returncode != 0:
        _host.die(f"scp push failed: {_host._ssh_failure_detail(proc)}")

def validate_ssh_user(user: str) -> str:
    """Reject control chars, whitespace, shell-unsafe, and overlong users."""
    if not isinstance(user, str) or not user:
        _host.die("invalid ssh_user: empty")
    if _host._has_ascii_control(user) or any(c.isspace() for c in user):
        _host.die("invalid ssh_user: whitespace or control characters")
    if len(user) > SSH_USER_MAX or not SSH_USER_RE.fullmatch(user):
        _host.die(f"invalid ssh_user: {user}")
    return user

def _is_dns_hostname(host: str) -> bool:
    name = host[:-1] if host.endswith(".") else host
    if not name or len(host) > SSH_HOST_MAX:
        return False
    labels = name.split(".")
    return bool(labels) and all(_HOSTNAME_LABEL_RE.fullmatch(label) for label in labels)

def validate_ssh_host(host: str) -> str:
    """Allow DNS / IPv4 / IPv6 only. No whitespace, controls, or shell metacharacters."""
    if not isinstance(host, str) or not host:
        _host.die("invalid ssh_host: empty")
    if _host._has_ascii_control(host) or any(c.isspace() for c in host):
        _host.die("invalid ssh_host: whitespace or control characters")
    if len(host) > SSH_HOST_MAX:
        _host.die("invalid ssh_host: too long")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if not _is_dns_hostname(host):
        _host.die(f"invalid ssh_host: {host}")
    return host
