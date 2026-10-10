"""Explicit, dedicated VLESS/Reality synthetic probe. Never falls back to direct."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path


def read_profiles(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise ValueError("invalid probe profile file")
        if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("probe profiles require current-user ownership and mode 0600")
        raw = handle.read(65537)
    if len(raw.encode("utf-8")) > 65536:
        raise ValueError("probe profile file too large")
    try:
        doc = json.loads(raw)
        if set(doc) != {"schema", "nodes"} or doc["schema"] != "probe-profiles/v1" or not isinstance(doc["nodes"], dict):
            raise ValueError
        if len(doc["nodes"]) > 1024:
            raise ValueError
        for name, entry in doc["nodes"].items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", name):
                raise ValueError
            validate_profile(entry)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("invalid dedicated probe profiles") from None
    return doc["nodes"]


def validate_profile(entry: dict):
    fields = {"node_id", "purpose", "user_tag", "server", "server_port", "uuid", "server_name", "public_key", "short_id", "url"}
    if not isinstance(entry, dict) or set(entry) != fields or entry["purpose"] != "synthetic-probe":
        raise ValueError("invalid dedicated probe profile")
    if not re.fullmatch(r"vcl-probe-[a-z0-9-]{1,20}", entry["user_tag"]):
        raise ValueError("dedicated probe user required")
    uuid.UUID(entry["uuid"])
    uuid.UUID(entry["node_id"])
    ipaddress.ip_address(entry["server"])
    if type(entry["server_port"]) is not int or not 1 <= entry["server_port"] <= 65535:
        raise ValueError("invalid port")
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", entry["server_name"]):
        raise ValueError("invalid server name")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,44}", entry["public_key"]):
        raise ValueError("invalid public key")
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}){0,8}", entry["short_id"]):
        raise ValueError("invalid short id")
    target = urllib.parse.urlsplit(entry["url"])
    if target.scheme != "https" or not target.hostname or target.username or target.password or target.query or target.fragment:
        raise ValueError("probe URL must be plain HTTPS without credentials or query")
    if len(entry["url"]) > 2048 or any(ord(c) < 33 for c in entry["url"]):
        raise ValueError("invalid probe URL")


def client_config(profile: dict, port: int) -> dict:
    validate_profile(profile)
    return {"log": {"disabled": True},
            "inbounds": [{"type": "socks", "listen": "127.0.0.1", "listen_port": port}],
            "outbounds": [{"type": "vless", "tag": "probe", "server": profile["server"],
                           "server_port": profile["server_port"], "uuid": profile["uuid"],
                           "flow": "xtls-rprx-vision", "tls": {"enabled": True,
                           "server_name": profile["server_name"], "utls": {"enabled": True, "fingerprint": "chrome"},
                           "reality": {"enabled": True, "public_key": profile["public_key"], "short_id": profile["short_id"]}}}],
            "route": {"final": "probe"}}


class ProxyProbe:
    def __init__(self, profiles: dict, *, sing_box="sing-box", curl="curl", temp_root=None):
        self.profiles = profiles
        self.sing_box = shutil.which(sing_box)
        self.curl = shutil.which(curl)
        self.temp_root = temp_root

    def __call__(self, node, *, timeout):
        profile = self.profiles.get(node["name"])
        if profile is None:
            return {"success": None, "reason": "NOT_CONFIGURED"}
        if profile["node_id"] != node["node_id"]:
            return {"success": None, "reason": "INVALID_CONFIG"}
        if not self.sing_box or not self.curl:
            return {"success": None, "reason": "RUNTIME_UNAVAILABLE"}
        deadline, process = time.monotonic() + timeout, None
        try:
            with tempfile.TemporaryDirectory(prefix="vcl-probe-", dir=self.temp_root) as root:
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    port = listener.getsockname()[1]
                path = Path(root) / "client.json"
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(client_config(profile, port), handle)
                kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                # No shell; only a private config path appears in argv, never credential material.
                process = subprocess.Popen([self.sing_box, "run", "-c", str(path)], **kwargs)
                try:
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            return {"success": None, "reason": "INVALID_CONFIG"}
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=.1):
                                break
                        except OSError:
                            time.sleep(.025)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return {"success": False, "reason": "TIMEOUT"}
                    # -q ignores user curlrc; explicit proxy + empty no-proxy override env bypass.
                    args = [self.curl, "-q", "--silent", "--output", os.devnull,
                            "--write-out", "%{http_code} %{time_appconnect} %{time_starttransfer} %{time_total}",
                            "--proxy", f"socks5h://127.0.0.1:{port}", "--noproxy", "",
                            "--proto", "=https", "--tlsv1.2", "--max-time", str(remaining),
                            "--connect-timeout", str(remaining), "--head", "--url", profile["url"]]
                    env = {key: val for key, val in os.environ.items() if key.lower() not in
                           {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "curl_home"}}
                    run_kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL,
                                  "timeout": remaining, "env": env, "text": True}
                    if os.name == "nt":
                        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                    result = subprocess.run(args, **run_kwargs)
                    if result.returncode:
                        reason = {28: "TIMEOUT", 6: "DNS_FAILED", 35: "TLS_FAILED", 60: "TLS_FAILED"}.get(result.returncode, "CONNECT_FAILED")
                        return {"success": False, "reason": reason}
                    values = result.stdout.strip().split()
                    if len(values) != 4 or len(result.stdout) > 256:
                        return {"success": False, "reason": "HTTP_FAILED"}
                    code = int(values[0])
                    success = 200 <= code < 400
                    return {"success": success, "reason": "OK" if success else "HTTP_FAILED",
                            "connect_ms": float(values[1]) * 1000, "ttfb_ms": float(values[2]) * 1000,
                            "total_ms": float(values[3]) * 1000}
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            return {"success": False, "reason": "TIMEOUT"}
        except (OSError, ValueError, TypeError):
            return {"success": None, "reason": "INVALID_CONFIG"}
