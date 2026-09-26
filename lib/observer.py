"""Restricted observer SSH client and local, sandboxed read-only broker.

Only exact protocol commands cross the Unix socket. No shell evaluation,
caller-controlled executable, environment, file path or mutation is supported.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import select
import shlex
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

SOCKET = "/run/vincula-observer.sock"
USER = "vincula-observer"
ALLOWED = frozenset({("identity", "--json"), ("capabilities", "--json"),
                     ("telemetry", "snapshot", "--json"), ("status", "--json"), ("verify", "--json")})
MAX_RESPONSE = 65536


def parse_command(command: str) -> list[str]:
    if not command or len(command.encode("utf-8")) > 1024 or any(ord(c) < 32 for c in command):
        raise ValueError("observer command denied")
    try:
        args = shlex.split(command)
    except ValueError:
        raise ValueError("observer command denied") from None
    if not args or args[0] not in ("vcl", "/usr/local/bin/vcl") or tuple(args[1:]) not in ALLOWED:
        raise ValueError("observer command denied")
    return args[1:]


def read_frame(channel, maximum):
    data = bytearray()
    deadline = time.monotonic() + 12
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("observer frame timed out")
        channel.settimeout(remaining)
        chunk = channel.recv(min(4096, maximum + 1 - len(data)))
        if not chunk:
            raise ValueError("incomplete observer frame")
        data.extend(chunk)
        if len(data) > maximum:
            raise ValueError("oversize observer frame")
        if b"\n" in data:
            line, rest = bytes(data).split(b"\n", 1)
            if rest.strip():
                raise ValueError("multiple observer requests denied")
            return json.loads(line)


def run_readonly(args):
    if tuple(args) not in ALLOWED:
        raise ValueError("observer command denied")
    process = subprocess.Popen(["/usr/local/bin/vcl", *args], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env={"PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8"})
    raw, deadline = bytearray(), time.monotonic() + 10
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("observer command timed out")
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            if not ready:
                raise ValueError("observer command timed out")
            chunk = os.read(process.stdout.fileno(), min(4096, MAX_RESPONSE + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > MAX_RESPONSE:
                raise ValueError("observer response too large")
        code = process.wait(timeout=max(.001, deadline - time.monotonic()))
        payload = json.loads(raw)
        if not isinstance(payload, dict) or code not in (0, 1):
            raise ValueError("observer command failed")
        return {"exit_code": code, "payload": payload}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=1)
        process.stdout.close()


def broker(channel, *, execute=run_readonly, expected_uid=None):
    if expected_uid is None:
        import pwd
        expected_uid = pwd.getpwnam(USER).pw_uid
    _, uid, _ = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid not in (0, expected_uid):
        raise ValueError("observer peer denied")
    request = read_frame(channel, 1024)
    if not isinstance(request, dict) or set(request) != {"args"} or not isinstance(request["args"], list):
        raise ValueError("invalid observer request")
    if any(not isinstance(arg, str) for arg in request["args"]) or tuple(request["args"]) not in ALLOWED:
        raise ValueError("observer command denied")
    response = execute(request["args"])
    encoded = json.dumps(response, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(encoded) > MAX_RESPONSE + 1024:
        raise ValueError("observer response too large")
    channel.sendall(encoded)


def client(command):
    args = parse_command(command)
    with socket.socket(socket.AF_UNIX) as channel:
        channel.settimeout(12)
        channel.connect(SOCKET)
        channel.sendall(json.dumps({"args": args}).encode() + b"\n")
        doc = read_frame(channel, MAX_RESPONSE + 1024)
    if not isinstance(doc, dict) or set(doc) != {"exit_code", "payload"} or type(doc["exit_code"]) is not int or doc["exit_code"] not in (0, 1) or not isinstance(doc["payload"], dict):
        raise ValueError("invalid observer response")
    sys.stdout.write(json.dumps(doc["payload"], allow_nan=False) + "\n")
    return doc["exit_code"]


def public_key(raw):
    pieces = raw.strip().split()
    if len(raw) > 16384 or len(pieces) < 2 or pieces[0] != "ssh-ed25519" or "\n" in raw.strip() or "\r" in raw.strip():
        raise ValueError("expected one plain Ed25519 public key")
    try:
        blob = base64.b64decode(pieces[1], validate=True)
    except ValueError:
        raise ValueError("invalid observer public key") from None
    if len(blob) != 51 or blob[:19] != b"\0\0\0\x0bssh-ed25519\0\0\0\x20":
        raise ValueError("invalid observer public key")
    return "ssh-ed25519 " + pieces[1]


def install_key(path):
    import grp
    import pwd
    import stat
    import tempfile
    if os.geteuid() != 0:
        raise ValueError("observer setup requires admin/root")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("invalid observer public key file")
        key = public_key(handle.read(16385))
    home = Path("/var/lib/vincula-observer")
    try:
        account = pwd.getpwnam(USER)
    except KeyError:
        if home.exists():
            raise ValueError("observer home already exists without managed account")
        subprocess.run(["/usr/sbin/useradd", "--system", "--user-group", "--home-dir", str(home),
                        "--no-create-home", "--shell", "/bin/sh", USER], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        account = pwd.getpwnam(USER)
    group = grp.getgrnam(USER)
    if not 0 < account.pw_uid < 1000 or account.pw_gid != group.gr_gid or account.pw_dir != str(home) or account.pw_shell != "/bin/sh":
        raise ValueError("unsafe existing observer account")
    if set(os.getgrouplist(USER, account.pw_gid)) != {account.pw_gid}:
        raise ValueError("observer must not have supplementary groups")
    status = subprocess.run(["/usr/bin/passwd", "-S", USER], capture_output=True, text=True, timeout=5, check=True)
    if len(status.stdout.split()) < 2 or status.stdout.split()[1] != "L":
        raise ValueError("observer password authentication must be locked")
    for directory in (home, home / ".ssh"):
        directory.mkdir(mode=0o750, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("observer SSH files must be controlled by root")
        os.chown(directory, 0, group.gr_gid)
        os.chmod(directory, 0o750)
    target = home / ".ssh" / "authorized_keys"
    if any(path.name != "authorized_keys" for path in target.parent.iterdir()):
        raise ValueError("unexpected observer SSH files")
    options = 'restrict,command="/usr/bin/python3 -I /usr/local/lib/vincula/observer.py client" '
    if target.exists() and not target.read_text().startswith(options):
        raise ValueError("refusing to overwrite unmanaged observer authorized_keys")
    # Check service readiness before replacing a working key.
    subprocess.run(["/usr/bin/systemctl", "daemon-reload"], check=True)
    subprocess.run(["/usr/bin/systemctl", "enable", "--now", "vincula-observer.socket"], check=True)
    fd, staged = tempfile.mkstemp(prefix=".observer-", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            os.fchown(handle.fileno(), 0, group.gr_gid)
            os.fchmod(handle.fileno(), 0o640)
            handle.write(options + key + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, target)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)


def main():
    parser = argparse.ArgumentParser(description="Typed, read-only observer transport")
    parser.add_argument("mode", choices=("client", "broker", "install-key"))
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "client":
            return client(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
        if args.mode == "broker":
            with socket.socket(fileno=os.dup(0)) as channel:
                broker(channel)
            return 0
        if args.file is None:
            raise ValueError("observer public key file required")
        install_key(args.file)
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print("observer request/setup refused; check command, credential and local service readiness", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
