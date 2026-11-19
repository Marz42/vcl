"""Minimal accountd inputs; deliberately excludes proxy authentication credentials.

The privileged installer/mutation transaction produces this projection. The
unprivileged daemon consumes only this file and its accounting database.
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path

SCHEMA = "accountd-runtime/v1"
MAX_BYTES = 4 * 1024 * 1024
MAX_USERS = 10000
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
TAG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")


def validate(doc):
    if not isinstance(doc, dict) or set(doc) != {"schema", "node", "users", "clash_api_port", "clash_api_secret", "raw_retention_days", "daily_retention_days"}:
        raise ValueError("invalid accountd runtime fields")
    if doc["schema"] != SCHEMA:
        raise ValueError("unsupported accountd runtime schema")
    node = doc["node"]
    if not isinstance(node, dict) or set(node) != {"node_id", "instance_id"}:
        raise ValueError("invalid accountd node identity")
    if any(not isinstance(node[k], str) or not UUID.fullmatch(node[k]) for k in node) or node["node_id"] == node["instance_id"]:
        raise ValueError("invalid accountd identity values")
    if type(doc["clash_api_port"]) is not int or not 1 <= doc["clash_api_port"] <= 65535:
        raise ValueError("invalid accountd Clash port")
    secret = doc["clash_api_secret"]
    if not isinstance(secret, str) or not 1 <= len(secret) <= 512 or any(ord(c) < 32 for c in secret):
        raise ValueError("invalid accountd Clash credential")
    for key in ("raw_retention_days", "daily_retention_days"):
        if type(doc[key]) is not int or not 1 <= doc[key] <= 3650:
            raise ValueError("invalid accountd retention")
    if not isinstance(doc["users"], list) or not 1 <= len(doc["users"]) <= MAX_USERS:
        raise ValueError("invalid accountd mapping size")
    seen = set()
    for user in doc["users"]:
        if not isinstance(user, dict) or set(user) != {"tag", "user_id"}:
            raise ValueError("accountd mapping must contain only tag and logical user_id")
        if not isinstance(user["tag"], str) or not TAG.fullmatch(user["tag"]) or user["tag"] in seen:
            raise ValueError("invalid accountd mapping tag")
        if not isinstance(user["user_id"], str) or not UUID.fullmatch(user["user_id"]):
            raise ValueError("invalid accountd logical user identity")
        seen.add(user["tag"])
    return doc


def project(state: dict, users: dict, settings: dict) -> dict:
    """Copy only required scalars. Never copy state/settings/users wholesale."""
    node = state.get("node", {})
    try:
        doc = {"schema": SCHEMA,
               "node": {"node_id": node["node_id"], "instance_id": node["instance_id"]},
               "users": [{"tag": item["tag"], "user_id": item["user_id"]} for item in users["users"]],
               "clash_api_port": int(settings.get("clash_api_port", 9090)),
               "clash_api_secret": settings["clash_api_secret"],
               "raw_retention_days": int(settings.get("accounting_raw_retention_days", 90)),
               "daily_retention_days": int(settings.get("accounting_daily_retention_days", 90))}
        if settings.get("node_id") != node["node_id"]:
            raise ValueError
        return validate(doc)
    except (KeyError, TypeError, ValueError):
        raise ValueError("cannot project consistent accountd runtime inputs") from None


def read(path: Path, *, check_permissions=True) -> dict:
    # Refuse symlink substitution and overly permissive root-owned input files.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("invalid accountd runtime file")
        if check_permissions and os.name != "nt" and (info.st_uid != 0 or info.st_mode & 0o027):
            raise ValueError("accountd runtime must be root-owned and mode 0640 or stricter")
        raw = handle.read(MAX_BYTES + 1)
    try:
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise ValueError
        return validate(json.loads(raw))
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("invalid accountd runtime content") from None


def write(path: Path, doc: dict, *, uid=0, gid=0):
    """Atomic publication into a privileged, non-writable-by-daemon directory."""
    validate(doc)
    payload = json.dumps(doc, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("accountd runtime projection too large")
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or (os.name != "nt" and (info.st_uid != uid or info.st_mode & 0o022)):
        raise ValueError("accountd runtime directory must be privileged and not group/world writable")
    fd, staged = tempfile.mkstemp(prefix=".accountd-runtime-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            if os.name != "nt":
                os.fchown(handle.fileno(), uid, gid)
                os.fchmod(handle.fileno(), 0o640)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)


def canonical_text(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > MAX_BYTES:
            raise ValueError("unsafe canonical accountd input")
        raw = handle.read(MAX_BYTES + 1)
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("canonical accountd input too large")
    return raw


def prepare(state_dir: Path, data_dir: Path, target: Path):
    """Fixed privileged pre-start task, never callable through an observer route."""
    import pwd
    if os.geteuid() != 0:
        raise ValueError("accountd preparation requires root")
    account = pwd.getpwnam("vincula-accountd")
    if not 0 < account.pw_uid < 1000 or not account.pw_shell.endswith(("/nologin", "/false")):
        raise ValueError("unsafe accountd service account")
    if set(os.getgrouplist("vincula-accountd", account.pw_gid)) != {account.pw_gid}:
        raise ValueError("accountd must not have supplementary groups")
    state = json.loads(canonical_text(state_dir / "state.json"))
    users = json.loads(canonical_text(state_dir / "users.json"))
    settings = {}
    for line in canonical_text(state_dir / "config.toml").splitlines():
        key, sep, raw = line.partition("=")
        key = key.strip()
        if sep and key in {"node_id", "clash_api_port", "clash_api_secret", "accounting_raw_retention_days", "accounting_daily_retention_days"}:
            if key in settings:
                raise ValueError("duplicate accountd setting")
            settings[key] = json.loads(raw.strip())
    doc = project(state, users, settings)
    # State is not authoritative control state: only accounting DB/events live here.
    # Reject symlinks, non-regular files, and hard-link tricks before chown.
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory_fd = os.open(data_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(directory_fd).st_uid not in (0, account.pw_uid):
            raise ValueError("unexpected accounting directory owner")
        for name in ("accounting.db", "accounting.db-wal", "accounting.db-shm", "accounting.db-journal", "events.jsonl"):
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            except FileNotFoundError:
                continue
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError("unsafe accounting data file")
                os.fchown(fd, account.pw_uid, account.pw_gid)
                os.fchmod(fd, 0o600)
            finally:
                os.close(fd)
        os.fchown(directory_fd, account.pw_uid, account.pw_gid)
        os.fchmod(directory_fd, 0o700)
    finally:
        os.close(directory_fd)
    target.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    info = target.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError("unsafe accountd projection directory")
    os.chown(target.parent, 0, account.pw_gid)
    os.chmod(target.parent, 0o750)
    write(target, doc, uid=0, gid=account.pw_gid)


def main():
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Privileged minimal accountd projection preparation")
    parser.add_argument("--state-dir", type=Path, default=Path("/etc/vincula"))
    parser.add_argument("--data-dir", type=Path, default=Path("/var/lib/vincula"))
    parser.add_argument("--output", type=Path, default=Path("/etc/vincula-accountd/runtime.json"))
    args = parser.parse_args()
    try:
        prepare(args.state_dir, args.data_dir, args.output)
    except (OSError, ValueError, KeyError, TypeError):
        print("accountd preparation failed; canonical inputs/permissions must be repaired by an administrator", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
