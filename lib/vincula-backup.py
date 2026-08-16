#!/usr/bin/env python3
"""vincula-backup — backup format, secretless rendering, restore plan, SQLite snapshots.

Default backups are secretless identity/audit archives: they keep node_id,
instance_id, user_id, credential_id history, and accounting, and strip
node.reality_private_key, credentials[].uuid, and clash_api_secret.
They do not require age.

`--include-secrets` keeps those three files verbatim and requires whole-archive
age encryption (`age -e -R` recipient file). Secret-bearing archives are never
written as plaintext tar.

Restore is fresh-node only: a target with VERSION is refused. Safe mode mints a
new instance_id and rotates Reality/Clash/VLESS credentials; secrets mode
reuses those secrets but still mints a new instance_id.

Accounting snapshots use sqlite3.Connection.backup() so a live WAL writer
(accountd) is safe. Do not copy live database files.

Stdlib only. Targets Python 3.10+.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import re
import secrets as secrets_mod
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union
from urllib.parse import quote

BACKUP_SCHEMA_VERSION = 1
BACKUP_SCHEMA_VERSIONS_READ = (1,)
AGE_MISSING_MSG = "Secret-bearing backup requires age."
AGE_RECIPIENT_MSG = "Secret-bearing backup requires --age-recipient FILE."
AGE_IDENTITY_MSG = "Encrypted backup verify requires --age-identity FILE."
EXISTING_INSTALL_MSG = "Refusing to overwrite an existing Vincula install."
INCLUDE_SECRETS_MSG = "--include-secrets requires a secret-bearing backup."
SECRET_MODE_NO_CSV_MSG = "secret-mode restore reused credentials; no reissue CSV"
CSV_HEADER = ("user", "node", "old_credential_id", "new_credential_id", "vless_uri")
TOML_UNQUOTED_KEYS = {
    "port",
    "clash_api_port",
    "accounting_raw_retention_days",
    "accounting_daily_retention_days",
    "billing_cycle_start_day",
}
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
COMPONENT_NAMES = (
    "state.json",
    "users.json",
    "config.toml",
    "accounting.db",
    "VERSION",
)
REQUIRED_COMPONENTS = ("state.json", "users.json", "config.toml")
CLASH_SECRET_LINE = re.compile(r"^clash_api_secret\s*=", re.MULTILINE)
UUID_KEY = re.compile(r'"uuid"\s*:')

MemberSource = Union[Path, bytes]


def age_bin() -> str:
    """Return the age binary: $VCL_AGE_BIN if set, otherwise `age`."""
    override = os.environ.get("VCL_AGE_BIN", "").strip()
    return override or "age"


class AgeError(RuntimeError):
    """age subprocess failed."""


def age_available() -> bool:
    """True when the configured age binary exists and is executable."""
    return shutil.which(age_bin()) is not None


def _run_age(argv: Sequence[str], tmp_out: Path) -> None:
    proc = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not tmp_out.is_file():
        raise AgeError(f"age failed (exit {proc.returncode})")


def age_encrypt(src: Path, dst: Path, recipient_file: Path) -> None:
    """Encrypt src to dst via `age -e -R recipient -o dst src`."""
    src_path = Path(src)
    dst_path = Path(dst)
    recipient = Path(recipient_file)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst_path.with_name(f".{dst_path.name}.{os.getpid()}.age.tmp")
    try:
        _run_age(
            [age_bin(), "-e", "-R", str(recipient), "-o", str(tmp), str(src_path)],
            tmp,
        )
        os.chmod(tmp, 0o600)
        os.replace(tmp, dst_path)
        os.chmod(dst_path, 0o600)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def age_decrypt(src: Path, dst: Path, identity_file: Path) -> None:
    """Decrypt src to dst via `age -d -i identity -o dst src`."""
    src_path = Path(src)
    dst_path = Path(dst)
    identity = Path(identity_file)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst_path.with_name(f".{dst_path.name}.{os.getpid()}.tar.tmp")
    try:
        _run_age(
            [age_bin(), "-d", "-i", str(identity), "-o", str(tmp), str(src_path)],
            tmp,
        )
        os.chmod(tmp, 0o600)
        os.replace(tmp, dst_path)
        os.chmod(dst_path, 0o600)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def encrypt_age(tar_bytes: bytes, recipient_file: Path, dest: Path) -> None:
    """Encrypt tar bytes to dest using the configured age binary."""
    with tempfile.NamedTemporaryFile(
        prefix="vincula-age-pt-", suffix=".tar", delete=False
    ) as fh:
        fh.write(tar_bytes)
        src = Path(fh.name)
    try:
        age_encrypt(src, dest, recipient_file)
    finally:
        src.unlink(missing_ok=True)


def decrypt_age(src: Path, identity_file: Path, dest: Path) -> None:
    """Decrypt an age archive to dest using the configured age binary."""
    age_decrypt(src, dest, identity_file)


def resolve_backup_output(output: Path, include_secrets: bool) -> Path:
    """Force secret-bearing destinations to a `.tar.age` suffix."""
    path = Path(output)
    if not include_secrets:
        return path
    name = str(path)
    if name.endswith(".age"):
        return path
    if name.endswith(".tar"):
        return Path(name + ".age")
    return Path(name + ".tar.age")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _dumps(doc: Any) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _safe_member_name(name: str) -> str:
    if not name or name.startswith("/") or name.startswith("\\"):
        raise ValueError(f"refusing absolute tar member: {name}")
    if ".." in Path(name).parts:
        raise ValueError(f"refusing tar member with ..: {name}")
    return name


def copy_verbatim(obj: Any) -> Any:
    """Secrets-mode copy: bytes/str as-is, mappings via deepcopy."""
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj)
    if isinstance(obj, str):
        return obj
    return copy.deepcopy(obj)


def strip_state(doc: Mapping[str, Any]) -> Dict[str, Any]:
    """Deep-copy state.json and delete node.reality_private_key (key absent)."""
    out = copy.deepcopy(doc)
    node = out.get("node")
    if isinstance(node, dict):
        node.pop("reality_private_key", None)
    return out


def strip_users(doc: Mapping[str, Any]) -> Dict[str, Any]:
    """Deep-copy users.json and delete credentials[].uuid (including revoked)."""
    out = copy.deepcopy(doc)
    for user in out.get("users") or []:
        if not isinstance(user, dict):
            continue
        for cred in user.get("credentials") or []:
            if isinstance(cred, dict):
                cred.pop("uuid", None)
    return out


def strip_config_toml(text: str) -> str:
    """Drop lines matching ^clash_api_secret\\s*= ; keep remaining text/newlines."""
    kept = [line for line in text.splitlines(keepends=True) if not CLASH_SECRET_LINE.match(line)]
    return "".join(kept)


def strip_secretless(
    state: Mapping[str, Any],
    users: Mapping[str, Any],
    toml_text: str,
) -> tuple[Dict[str, Any], Dict[str, Any], str]:
    """Return stripped (state, users, toml) for the default backup."""
    return strip_state(state), strip_users(users), strip_config_toml(toml_text)


def assert_secretless(
    state: Mapping[str, Any],
    users: Mapping[str, Any],
    toml_text: str,
) -> None:
    """Raise ValueError if any of the three secret sites is still present."""
    node = state.get("node") if isinstance(state.get("node"), dict) else {}
    if "reality_private_key" in node:
        raise ValueError("secretless state still contains reality_private_key")
    for user in users.get("users") or []:
        if not isinstance(user, dict):
            continue
        for cred in user.get("credentials") or []:
            if isinstance(cred, dict) and "uuid" in cred:
                raise ValueError("secretless users still contain credentials[].uuid")
    if CLASH_SECRET_LINE.search(toml_text):
        raise ValueError("secretless config still contains clash_api_secret")


def snapshot_sqlite(src: Path, dest: Path) -> None:
    """Copy a consistent SQLite snapshot via Connection.backup().

    Opens the source read-only (URI) and copies pages to dest. Safe against a
    live WAL writer such as accountd. Do not copy live database files.
    """
    src_path = Path(src)
    dest_path = Path(dest)
    if not src_path.is_file():
        raise FileNotFoundError(str(src_path))
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        dest_path.unlink()
    abs_src = str(src_path.resolve())
    uri = "file:" + quote(abs_src, safe="/") + "?mode=ro"
    src_conn = sqlite3.connect(uri, uri=True)
    try:
        dest_conn = sqlite3.connect(str(dest_path))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def db_snapshot(src_db: Path, dst_path: Path) -> None:
    """Alias for snapshot_sqlite (Python sqlite3 Backup API)."""
    snapshot_sqlite(src_db, dst_path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mtime_from_iso(created_at: str) -> int:
    try:
        when = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return int(when.timestamp())


def build_manifest(
    *,
    vincula_version: str,
    created_at: str,
    source_node_id: str,
    source_instance_id: str,
    included_components: Sequence[str],
    secret_bearing: bool,
    encryption: str,
    hashes: Mapping[str, str],
) -> Dict[str, Any]:
    """Backup schema 1 manifest; field order matches plan §0.2.2."""
    files = [{"path": name, "sha256": hashes[name]} for name in included_components]
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "vincula_version": vincula_version,
        "created_at": created_at,
        "source_node_id": source_node_id,
        "source_instance_id": source_instance_id,
        "included_components": list(included_components),
        "secret_bearing": bool(secret_bearing),
        "encryption": encryption,
        "files": files,
    }


def _member_bytes(source: MemberSource) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    return Path(source).read_bytes()


def _add_bytes(tf: tarfile.TarFile, name: str, data: bytes, mtime: int) -> None:
    info = tarfile.TarInfo(name=_safe_member_name(name))
    info.size = len(data)
    info.mode = 0o600
    info.mtime = mtime
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    tf.addfile(info, io.BytesIO(data))


def atomic_replace(src: Path, dest: Path, mode: int = 0o600) -> None:
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_path.with_name(f".{dest_path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(Path(src).read_bytes())
        os.chmod(tmp, mode)
        os.replace(tmp, dest_path)
        os.chmod(dest_path, mode)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def write_tar(
    dest: Path,
    members: Mapping[str, MemberSource],
    manifest: Mapping[str, Any],
) -> None:
    """Write POSIX ustar: manifest.json first, then included_components order."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = str(manifest.get("created_at") or "")
    mtime = _mtime_from_iso(created_at)
    manifest_bytes = _dumps(manifest)
    included = list(manifest.get("included_components") or [])
    tmp = dest_path.with_name(f".{dest_path.name}.{os.getpid()}.tar.tmp")
    try:
        with tarfile.open(tmp, "w:", format=tarfile.USTAR_FORMAT) as tf:
            _add_bytes(tf, "manifest.json", manifest_bytes, mtime)
            for name in included:
                if name not in members:
                    raise KeyError(f"missing component for tar member {name}")
                _add_bytes(tf, name, _member_bytes(members[name]), mtime)
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest_path)
        os.chmod(dest_path, 0o600)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def build_backup(
    output: Path,
    components: Mapping[str, MemberSource],
    manifest: Mapping[str, Any],
) -> Path:
    """Assemble the archive (manifest.json first, deterministic member names)."""
    write_tar(output, components, manifest)
    return Path(output)


def assemble_components(
    state_dir: Path,
    dest_dir: Path,
    *,
    accounting_db: Optional[Path] = None,
    include_secrets: bool = False,
) -> Dict[str, Path]:
    """Render archive members into dest_dir; return name → path.

    Member names are archive-root COMPONENT_NAMES (state.json, …), not a
    components/ prefix. Missing accounting.db / VERSION are omitted.
    """
    state_dir = Path(state_dir)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, Path] = {}

    state_path = state_dir / "state.json"
    users_path = state_dir / "users.json"
    config_path = state_dir / "config.toml"
    version_path = state_dir / "VERSION"
    for required, path in (
        ("state.json", state_path),
        ("users.json", users_path),
        ("config.toml", config_path),
    ):
        if not path.is_file():
            _die(f"{required} not found: {path}")

    state_bytes = state_path.read_bytes()
    users_bytes = users_path.read_bytes()
    config_bytes = config_path.read_bytes()
    if include_secrets:
        (dest_dir / "state.json").write_bytes(state_bytes)
        (dest_dir / "users.json").write_bytes(users_bytes)
        (dest_dir / "config.toml").write_bytes(config_bytes)
    else:
        try:
            state_doc = json.loads(state_bytes.decode("utf-8"))
            users_doc = json.loads(users_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _die(f"cannot parse state/users JSON: {exc}")
        toml_text = config_bytes.decode("utf-8")
        stripped_state, stripped_users, stripped_toml = strip_secretless(
            state_doc, users_doc, toml_text
        )
        assert_secretless(stripped_state, stripped_users, stripped_toml)
        (dest_dir / "state.json").write_bytes(_dumps(stripped_state))
        (dest_dir / "users.json").write_bytes(_dumps(stripped_users))
        (dest_dir / "config.toml").write_bytes(stripped_toml.encode("utf-8"))
    out["state.json"] = dest_dir / "state.json"
    out["users.json"] = dest_dir / "users.json"
    out["config.toml"] = dest_dir / "config.toml"

    if version_path.is_file():
        dest_ver = dest_dir / "VERSION"
        dest_ver.write_bytes(version_path.read_bytes())
        out["VERSION"] = dest_ver

    if accounting_db is not None:
        src_db = Path(accounting_db)
        if src_db.is_file():
            dest_db = dest_dir / "accounting.db"
            snapshot_sqlite(src_db, dest_db)
            out["accounting.db"] = dest_db

    return out


def _fail(code: str) -> Dict[str, Any]:
    return {"schema_version": 1, "ok": False, "error": code}


def _read_tar_members(path: Path) -> Dict[str, bytes]:
    members: Dict[str, bytes] = {}
    try:
        with tarfile.open(path, "r:") as tf:
            for info in tf.getmembers():
                name = info.name
                try:
                    _safe_member_name(name)
                except ValueError:
                    raise tarfile.TarError(f"unsafe member name {name!r}") from None
                if info.isdir():
                    continue
                if not info.isreg():
                    raise tarfile.TarError(f"unsupported member type {name!r}")
                extracted = tf.extractfile(info)
                if extracted is None:
                    raise tarfile.TarError(f"cannot read member {name!r}")
                members[name] = extracted.read()
    except tarfile.TarError as exc:
        raise tarfile.TarError(str(exc)) from exc
    return members


def _secret_bearing_consistent(
    secret_bearing: bool, encryption: str, path: Path
) -> bool:
    suffix_age = str(path).endswith(".age")
    if secret_bearing:
        return encryption == "age" and suffix_age
    return encryption == "none" and not suffix_age


def _load_members(
    archive: Path, age_identity: Optional[Path]
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, bytes]]]:
    """Decrypt `.age` if needed, then read tar members.

    Returns (fail_result, None) or (None, members). Outer path stays `archive`
    so secret-bearing / suffix checks use the ciphertext name.
    """
    if not archive.is_file():
        return _fail("invalid_archive"), None
    if str(archive).endswith(".age"):
        if age_identity is None or not Path(age_identity).is_file():
            return _fail("age_identity_required"), None
        if not age_available():
            return _fail("age_required"), None
        try:
            with tempfile.TemporaryDirectory(prefix="vincula-age-") as tmp:
                tar_path = Path(tmp) / "archive.tar"
                try:
                    age_decrypt(archive, tar_path, Path(age_identity))
                except AgeError:
                    return _fail("failed"), None
                try:
                    members = _read_tar_members(tar_path)
                except (tarfile.TarError, OSError, ValueError):
                    return _fail("invalid_archive"), None
        except OSError:
            return _fail("failed"), None
        return None, members
    try:
        members = _read_tar_members(archive)
    except (tarfile.TarError, OSError, ValueError):
        return _fail("invalid_archive"), None
    return None, members


def _verify_members(members: Dict[str, bytes], outer_path: Path) -> Dict[str, Any]:
    """Steps 2–6: manifest, schema, flag/suffix consistency, sha256, members."""
    if "manifest.json" not in members:
        return _fail("missing_manifest")
    try:
        manifest = json.loads(members["manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _fail("invalid_archive")
    if not isinstance(manifest, dict):
        return _fail("invalid_archive")

    schema = manifest.get("schema_version")
    if schema not in BACKUP_SCHEMA_VERSIONS_READ:
        return _fail("unsupported_schema")

    secret_bearing = bool(manifest.get("secret_bearing"))
    encryption = manifest.get("encryption")
    if encryption not in ("none", "age"):
        return _fail("invalid_archive")
    if secret_bearing and encryption != "age":
        return _fail("secret_bearing_unencrypted")
    if not _secret_bearing_consistent(secret_bearing, encryption, outer_path):
        if secret_bearing:
            return _fail("secret_bearing_unencrypted")
        return _fail("invalid_archive")

    included = manifest.get("included_components")
    files = manifest.get("files")
    if not isinstance(included, list) or not isinstance(files, list):
        return _fail("invalid_archive")
    included_names = [str(n) for n in included]
    hash_by_path = {}
    for entry in files:
        if not isinstance(entry, dict) or "path" not in entry or "sha256" not in entry:
            return _fail("invalid_archive")
        hash_by_path[str(entry["path"])] = str(entry["sha256"]).lower()
    if set(included_names) != set(hash_by_path):
        return _fail("invalid_archive")

    actual = {name for name in members if name != "manifest.json"}
    if set(included_names) != actual:
        return _fail("invalid_archive")

    for name in included_names:
        digest = sha256_bytes(members[name])
        expected = hash_by_path[name]
        if digest != expected:
            return _fail("checksum_mismatch")

    out = dict(manifest)
    out["ok"] = True
    return out


def verify_manifest(
    path: Union[str, Path], age_identity: Optional[Path] = None
) -> Dict[str, Any]:
    """Parse a backup tar (decrypt `.age` first), validate schema 1 and flags."""
    archive = Path(path)
    err, members = _load_members(archive, age_identity)
    if err is not None:
        return err
    assert members is not None
    return _verify_members(members, archive)


def _assert_secret_bearing_members(members: Mapping[str, bytes]) -> Optional[str]:
    """Secrets archives must still contain the three secret sites."""
    if "state.json" in members:
        try:
            state = json.loads(members["state.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "invalid_archive"
        node = state.get("node") if isinstance(state, dict) else None
        if not isinstance(node, dict) or not node.get("reality_private_key"):
            return "invalid_archive"
    if "users.json" in members:
        try:
            users = json.loads(members["users.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "invalid_archive"
        user_list = users.get("users") if isinstance(users, dict) else None
        if isinstance(user_list, list) and user_list:
            has_active_uuid = False
            for user in user_list:
                if not isinstance(user, dict):
                    continue
                for cred in user.get("credentials") or []:
                    if (
                        isinstance(cred, dict)
                        and cred.get("status") == "active"
                        and cred.get("uuid")
                    ):
                        has_active_uuid = True
            if not has_active_uuid:
                return "invalid_archive"
    if "config.toml" in members:
        text = members["config.toml"].decode("utf-8", errors="replace")
        if not CLASH_SECRET_LINE.search(text):
            return "invalid_archive"
    return None


def _assert_secretless_members(members: Mapping[str, bytes]) -> Optional[str]:
    if "state.json" in members:
        try:
            state = json.loads(members["state.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "invalid_archive"
        node = state.get("node") if isinstance(state, dict) else None
        if isinstance(node, dict) and "reality_private_key" in node:
            return "invalid_archive"
    if "users.json" in members:
        try:
            users = json.loads(members["users.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "invalid_archive"
        if UUID_KEY.search(members["users.json"].decode("utf-8", errors="replace")):
            return "invalid_archive"
        if isinstance(users, dict):
            try:
                assert_secretless({"node": {}}, users, "")
            except ValueError:
                return "invalid_archive"
    if "config.toml" in members:
        text = members["config.toml"].decode("utf-8", errors="replace")
        if CLASH_SECRET_LINE.search(text):
            return "invalid_archive"
    return None


def verify_archive(
    path: Union[str, Path], age_identity: Optional[Path] = None
) -> Dict[str, Any]:
    """Verify a backup archive (plan §0.4.2 eight steps)."""
    archive = Path(path)
    err, members = _load_members(archive, age_identity)
    if err is not None:
        return err
    assert members is not None
    result = _verify_members(members, archive)
    if not result.get("ok"):
        return result
    if result.get("secret_bearing"):
        bad = _assert_secret_bearing_members(members)
    else:
        bad = _assert_secretless_members(members)
    if bad:
        return _fail(bad)
    return result


def create_backup(
    state_dir: Path,
    accounting_db: Optional[Path],
    include_secrets: bool,
    output: Path,
    age_recipient: Optional[Path] = None,
    *,
    created_at: Optional[str] = None,
    vincula_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble, self-verify, atomically write a 0600 archive.

    include_secrets requires age wrapping and never writes a plaintext
    secret-bearing tar. Missing age dies with AGE_MISSING_MSG (D17).
    """
    if include_secrets:
        if not age_recipient:
            _die(AGE_RECIPIENT_MSG)
        if not age_available():
            _die(AGE_MISSING_MSG)

    state_dir = Path(state_dir)
    output = resolve_backup_output(Path(output), include_secrets)
    when = created_at or utc_now_iso()
    with tempfile.TemporaryDirectory(prefix="vincula-backup-") as tmp:
        tmp_path = Path(tmp)
        parts = tmp_path / "parts"
        components = assemble_components(
            state_dir,
            parts,
            accounting_db=accounting_db,
            include_secrets=include_secrets,
        )
        included = [name for name in COMPONENT_NAMES if name in components]
        hashes = {name: sha256_file(components[name]) for name in included}
        state_doc = json.loads(components["state.json"].read_text(encoding="utf-8"))
        node = state_doc.get("node") if isinstance(state_doc.get("node"), dict) else {}
        source_node_id = str(node.get("node_id") or "")
        source_instance_id = str(node.get("instance_id") or "")
        if not source_node_id or not source_instance_id:
            _die("state.json missing node.node_id or node.instance_id")
        version = vincula_version
        if not version:
            if "VERSION" in components:
                version = components["VERSION"].read_text(encoding="utf-8").strip()
            else:
                version = str(state_doc.get("project_version") or "")
        if not version:
            _die("cannot determine vincula_version for manifest")
        secret_bearing = bool(include_secrets)
        encryption = "age" if include_secrets else "none"
        manifest = build_manifest(
            vincula_version=version,
            created_at=when,
            source_node_id=source_node_id,
            source_instance_id=source_instance_id,
            included_components=included,
            secret_bearing=secret_bearing,
            encryption=encryption,
            hashes=hashes,
        )
        staged = tmp_path / "archive.tar"
        write_tar(staged, components, manifest)
        inner = _read_tar_members(staged)
        checked = _verify_members(inner, output)
        if not checked.get("ok"):
            _die(str(checked.get("error") or "failed"))
        if secret_bearing:
            bad = _assert_secret_bearing_members(inner)
        else:
            bad = _assert_secretless_members(inner)
        if bad:
            _die(bad)
        if include_secrets:
            encrypted = tmp_path / "archive.tar.age"
            assert age_recipient is not None
            try:
                age_encrypt(staged, encrypted, Path(age_recipient))
            except AgeError:
                _die("age encryption failed")
            atomic_replace(encrypted, output, 0o600)
        else:
            atomic_replace(staged, output, 0o600)

    archive_hash = sha256_file(output)
    return {
        "schema_version": 1,
        "ok": True,
        "path": str(output),
        "secret_bearing": secret_bearing,
        "encryption": encryption,
        "backup_schema_version": BACKUP_SCHEMA_VERSION,
        "source_node_id": source_node_id,
        "source_instance_id": source_instance_id,
        "sha256": archive_hash,
    }


class RestoreError(Exception):
    """Restore preflight or transaction failed."""

    def __init__(self, message: str, code: str = "failed") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def mint_instance_id(node_id: str, existing: str = "") -> str:
    """Return a UUID that is never equal to node_id (INV-02)."""
    if UUID_RE.fullmatch(existing) and existing != node_id:
        return existing
    for _ in range(8):
        minted = str(uuid.uuid4())
        if minted != node_id:
            return minted
    raise RestoreError("Refusing to copy node_id into instance_id.")


def mint_uuid(forbid: Optional[str] = None) -> str:
    for _ in range(8):
        minted = str(uuid.uuid4())
        if minted != forbid:
            return minted
    raise RestoreError("failed to mint UUID")


def _uri_authority_host(server: str) -> str:
    if ":" in server and not server.startswith("["):
        return f"[{server}]"
    return server


def render_vless_uri(
    vless_uuid: str,
    server: str,
    port: Union[int, str],
    server_name: str,
    public_key: str,
    short_id: str,
    tag: str = "owner",
) -> str:
    authority = _uri_authority_host(server)
    return (
        f"vless://{vless_uuid}@{authority}:{port}"
        f"?encryption=none&flow=xtls-rprx-vision&security=reality"
        f"&sni={server_name}&fp=chrome&pbk={public_key}&sid={short_id}"
        f"&type=tcp#vincula-{tag}"
    )


def toml_get(text: str, key: str) -> Optional[str]:
    pattern = re.compile(rf"^{re.escape(key)}\s*=\s*(.*)$")
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        raw = match.group(1).strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            return raw[1:-1]
        return raw
    return None


def toml_set(text: str, key: str, value: Any) -> str:
    """Replace or append a TOML assignment, preserving other lines."""
    if key in TOML_UNQUOTED_KEYS or isinstance(value, int):
        rendered = f"{key} = {value}"
    else:
        rendered = f'{key} = "{value}"'
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    lines = text.splitlines(keepends=True)
    found = False
    out: List[str] = []
    for line in lines:
        if pattern.match(line):
            nl = "\n" if line.endswith("\n") else ""
            out.append(rendered + nl)
            found = True
        else:
            out.append(line)
    if not found:
        body = "".join(out)
        if body and not body.endswith("\n"):
            body += "\n"
        body += rendered + "\n"
        return body
    return "".join(out)


def write_restore_marker(dir_path: Path, marker_type: str, status: str = "") -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    version = os.environ.get("VCL_RESTORE_VERSION") or os.environ.get(
        "VINCULA_VERSION", "0.3.0-dev"
    )
    payload = (
        "project=vincula\n"
        f"type={marker_type}\n"
        f"version={version}\n"
    )
    if status:
        payload += f"status={status}\n"
    marker = dir_path / ".vincula-backup"
    marker.write_text(payload, encoding="utf-8")
    os.chmod(marker, 0o600)


def preflight_restore(
    manifest: Mapping[str, Any],
    *,
    installed: bool,
    include_secrets: bool,
) -> None:
    """Refuse existing installs and --include-secrets on secretless archives."""
    if installed:
        raise RestoreError(EXISTING_INSTALL_MSG, "existing_install")
    secret_bearing = bool(manifest.get("secret_bearing"))
    if include_secrets and not secret_bearing:
        raise RestoreError(INCLUDE_SECRETS_MSG, "invalid_archive")


def _validate_plan_identity(state: Mapping[str, Any], source_node_id: str, new_iid: str) -> None:
    node = state.get("node") if isinstance(state.get("node"), dict) else {}
    node_id = str(node.get("node_id") or "")
    instance_id = str(node.get("instance_id") or "")
    if node_id != source_node_id:
        raise RestoreError("staged node_id does not match backup source_node_id")
    if instance_id != new_iid:
        raise RestoreError("staged instance_id is not the planned new instance_id")
    if instance_id == node_id:
        raise RestoreError("staged instance_id must not equal node_id")


def build_restore_plan(
    *,
    state: Mapping[str, Any],
    users: Mapping[str, Any],
    config_toml: str,
    accounting: Optional[bytes],
    manifest: Mapping[str, Any],
    include_secrets: bool,
    new_instance_id: str,
    new_reality_private: str,
    new_reality_public: str,
    new_reality_short_id: str,
    new_clash_secret: str,
    target_server: Optional[str] = None,
    target_listen: Optional[str] = None,
    target_port: Optional[Union[int, str]] = None,
    target_service_account: Optional[Mapping[str, Any]] = None,
    reissue_ids: Optional[Mapping[str, Mapping[str, str]]] = None,
    project_version: Optional[str] = None,
    now: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble staged canonical files and reissue CSV rows.

    Safe mode (default, or secretless archive): rotate Reality, Clash, and
    every previously-active credential (new credential_id + uuid). Secrets
    mode (`include_secrets` and a secret-bearing archive): reuse those
    secrets byte-for-byte, still minting a new instance_id.
    """
    when = now or utc_now_iso()
    source_node_id = str(manifest.get("source_node_id") or "")
    source_instance_id = str(manifest.get("source_instance_id") or "")
    secret_bearing = bool(manifest.get("secret_bearing"))
    secrets_mode = bool(include_secrets) and secret_bearing
    mode = "secrets" if secrets_mode else "safe"

    staged_state = copy.deepcopy(state) if secrets_mode else strip_state(state)
    node = staged_state.setdefault("node", {})
    if not isinstance(node, dict):
        raise RestoreError("state.json node is not an object", "invalid_archive")
    node_id = str(node.get("node_id") or source_node_id)
    if not node_id:
        raise RestoreError("backup state missing node_id", "invalid_archive")
    new_iid = mint_instance_id(node_id, new_instance_id)
    node["node_id"] = node_id
    node["instance_id"] = new_iid
    if target_server:
        node["server"] = target_server
    if target_listen:
        node["listen"] = target_listen
    if target_port is not None and str(target_port) != "":
        try:
            node["port"] = int(target_port)
        except (TypeError, ValueError):
            node["port"] = target_port
    if target_service_account is not None:
        staged_state["service_account"] = copy.deepcopy(dict(target_service_account))
    running_version = project_version or str(staged_state.get("project_version") or "")
    if running_version:
        staged_state["project_version"] = running_version

    if secrets_mode:
        if not node.get("reality_private_key"):
            raise RestoreError("secrets restore missing reality_private_key", "invalid_archive")
        reality_private = str(node.get("reality_private_key") or "")
        reality_public = str(node.get("reality_public_key") or "")
        reality_short_id = str(node.get("reality_short_id") or "")
        clash_secret = toml_get(config_toml, "clash_api_secret") or new_clash_secret
        staged_users = copy.deepcopy(users)
    else:
        if not new_reality_private or not new_reality_public or not new_reality_short_id:
            raise RestoreError("safe restore requires a new Reality keypair")
        if not new_clash_secret:
            raise RestoreError("safe restore requires a new Clash secret")
        node["reality_private_key"] = new_reality_private
        node["reality_public_key"] = new_reality_public
        node["reality_short_id"] = new_reality_short_id
        reality_private = new_reality_private
        reality_public = new_reality_public
        reality_short_id = new_reality_short_id
        clash_secret = new_clash_secret
        staged_users = strip_users(users)

    server = str(node.get("server") or "")
    port = node.get("port") if node.get("port") is not None else 443
    sni = str(node.get("reality_server_name") or "")
    node_name = str(node.get("node_name") or "node")

    reissue_rows: List[Dict[str, str]] = []
    assigned = dict(reissue_ids or {})
    if not secrets_mode:
        for user in staged_users.get("users") or []:
            if not isinstance(user, dict):
                continue
            creds = list(user.get("credentials") or [])
            new_creds: List[Dict[str, Any]] = []
            to_append: List[Dict[str, Any]] = []
            tag = str(user.get("tag") or "")
            for cred in creds:
                if not isinstance(cred, dict):
                    continue
                cred = copy.deepcopy(cred)
                cred.pop("uuid", None)
                if cred.get("status") == "active":
                    old_cid = str(cred.get("credential_id") or "")
                    mapping = assigned.get(old_cid) or {}
                    new_cid = str(mapping.get("credential_id") or mint_uuid(node_id))
                    new_uuid = str(mapping.get("uuid") or mint_uuid(node_id))
                    cred["status"] = "revoked"
                    cred["revoked_at"] = when
                    new_creds.append(cred)
                    to_append.append(
                        {
                            "credential_id": new_cid,
                            "node_id": node_id,
                            "uuid": new_uuid,
                            "status": "active",
                            "created_at": when,
                            "revoked_at": None,
                        }
                    )
                    uri = render_vless_uri(
                        new_uuid, server, port, sni, reality_public, reality_short_id, tag
                    )
                    reissue_rows.append(
                        {
                            "user": tag,
                            "node": node_name,
                            "old_credential_id": old_cid,
                            "new_credential_id": new_cid,
                            "vless_uri": uri,
                        }
                    )
                else:
                    new_creds.append(cred)
            new_creds.extend(to_append)
            user["credentials"] = new_creds
        for user in staged_users.get("users") or []:
            if not isinstance(user, dict):
                continue
            for cred in user.get("credentials") or []:
                if (
                    isinstance(cred, dict)
                    and cred.get("status") != "active"
                    and "uuid" in cred
                ):
                    raise RestoreError("safe restore left a uuid on a historical credential")
        old_uuids = []
        for user in users.get("users") or []:
            if not isinstance(user, dict):
                continue
            for cred in user.get("credentials") or []:
                if isinstance(cred, dict) and cred.get("uuid"):
                    old_uuids.append(str(cred["uuid"]))
        staged_uuid_set = {
            str(c.get("uuid"))
            for u in staged_users.get("users") or []
            if isinstance(u, dict)
            for c in u.get("credentials") or []
            if isinstance(c, dict) and c.get("uuid")
        }
        if staged_uuid_set.intersection(old_uuids):
            raise RestoreError("safe restore reused a backup VLESS uuid")
    else:
        backup_uuid_map = {}
        for user in users.get("users") or []:
            if not isinstance(user, dict):
                continue
            for cred in user.get("credentials") or []:
                if isinstance(cred, dict) and cred.get("credential_id") is not None:
                    backup_uuid_map[str(cred["credential_id"])] = cred.get("uuid")
        for user in staged_users.get("users") or []:
            if not isinstance(user, dict):
                continue
            for cred in user.get("credentials") or []:
                if not isinstance(cred, dict):
                    continue
                cid = str(cred.get("credential_id") or "")
                if backup_uuid_map.get(cid) != cred.get("uuid"):
                    raise RestoreError("secrets restore changed a credential uuid")

    staged_toml = config_toml if secrets_mode else strip_config_toml(config_toml)
    staged_toml = toml_set(staged_toml, "node_id", node_id)
    if running_version:
        staged_toml = toml_set(staged_toml, "project_version", running_version)
    if target_server:
        staged_toml = toml_set(staged_toml, "server", target_server)
    if target_listen:
        staged_toml = toml_set(staged_toml, "listen", target_listen)
    if target_port is not None and str(target_port) != "":
        staged_toml = toml_set(staged_toml, "port", int(target_port) if str(target_port).isdigit() else target_port)
    if not secrets_mode:
        staged_toml = toml_set(staged_toml, "clash_api_secret", clash_secret)
    elif not toml_get(staged_toml, "clash_api_secret"):
        raise RestoreError("secrets restore missing clash_api_secret", "invalid_archive")

    if not secrets_mode:
        if "reality_private_key" not in node or not node.get("reality_private_key"):
            raise RestoreError("safe restore staged empty Reality private key")
        if not toml_get(staged_toml, "clash_api_secret"):
            raise RestoreError("safe restore staged empty Clash secret")

    _validate_plan_identity(staged_state, source_node_id or node_id, new_iid)

    owner_uri = ""
    for user in staged_users.get("users") or []:
        if not isinstance(user, dict):
            continue
        tag = str(user.get("tag") or "")
        for cred in user.get("credentials") or []:
            if isinstance(cred, dict) and cred.get("status") == "active" and cred.get("uuid"):
                owner_uri = render_vless_uri(
                    str(cred["uuid"]),
                    str(node.get("server") or server),
                    node.get("port") if node.get("port") is not None else port,
                    str(node.get("reality_server_name") or sni),
                    str(node.get("reality_public_key") or reality_public),
                    str(node.get("reality_short_id") or reality_short_id),
                    tag,
                )
                if tag == "owner":
                    break
        if tag == "owner" and owner_uri:
            break

    return {
        "mode": mode,
        "node_id": node_id,
        "source_instance_id": source_instance_id,
        "new_instance_id": new_iid,
        "state": staged_state,
        "users": staged_users,
        "config_toml": staged_toml,
        "accounting": accounting,
        "reissue_rows": reissue_rows,
        "owner_uri": owner_uri,
        "reality_private_key": str(node.get("reality_private_key") or reality_private),
        "reality_public_key": str(node.get("reality_public_key") or reality_public),
        "reality_short_id": str(node.get("reality_short_id") or reality_short_id),
        "clash_secret": toml_get(staged_toml, "clash_api_secret") or clash_secret,
        "secret_bearing": secret_bearing,
    }


def write_reissue_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.csv.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(CSV_HEADER), lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in CSV_HEADER})
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
        os.chmod(dest, 0o600)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _write_private(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        os.chmod(path, mode)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _safety_copy_existing(
    dest_state_dir: Path,
    dest_accounting_db: Optional[Path],
    safety_dir: Path,
) -> List[str]:
    copied: List[str] = []
    safety_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(safety_dir, 0o700)
    for name in ("state.json", "users.json", "config.toml", "VERSION", "owner.uri"):
        src = dest_state_dir / name
        if src.is_file():
            shutil.copy2(src, safety_dir / name)
            copied.append(name)
    if dest_accounting_db is not None and Path(dest_accounting_db).is_file():
        snapshot_sqlite(Path(dest_accounting_db), safety_dir / "accounting.db")
        copied.append("accounting.db")
    write_restore_marker(safety_dir, "restore-safety")
    return copied


def rollback_restore(
    safety_dir: Path,
    dest_state_dir: Path,
    dest_accounting_db: Optional[Path] = None,
    written: Optional[Sequence[str]] = None,
) -> None:
    """Copy the safety tree back; remove dest files that were not in the backup."""
    safety = Path(safety_dir)
    dest_state_dir = Path(dest_state_dir)
    present = {p.name for p in safety.iterdir() if p.is_file()} if safety.is_dir() else set()
    for name in ("state.json", "users.json", "config.toml", "VERSION", "owner.uri"):
        src = safety / name
        dest = dest_state_dir / name
        if src.is_file():
            _write_private(dest, src.read_bytes(), 0o600)
        elif name in (written or []) and dest.exists():
            dest.unlink()
    if dest_accounting_db is not None:
        db_dest = Path(dest_accounting_db)
        db_src = safety / "accounting.db"
        if db_src.is_file():
            snapshot_sqlite(db_src, db_dest)
            os.chmod(db_dest, 0o600)
        elif "accounting.db" in (written or []) and db_dest.exists():
            db_dest.unlink()
    _ = present
    if safety.is_dir():
        write_restore_marker(safety, "restore-rollback", status="rolled-back")


def _load_verified_members(
    archive: Path, age_identity: Optional[Path]
) -> tuple[Dict[str, Any], Dict[str, bytes]]:
    verified = verify_archive(archive, age_identity)
    if not verified.get("ok"):
        code = str(verified.get("error") or "failed")
        if code == "age_identity_required":
            raise RestoreError(AGE_IDENTITY_MSG, code)
        if code == "age_required":
            raise RestoreError(AGE_MISSING_MSG, code)
        raise RestoreError(code, code)
    err, members = _load_members(archive, age_identity)
    if err is not None or members is None:
        code = str((err or {}).get("error") or "failed")
        raise RestoreError(code, code)
    return verified, members


def apply_restore(
    archive: Path,
    dest_state_dir: Path,
    *,
    dest_accounting_db: Optional[Path] = None,
    age_identity: Optional[Path] = None,
    include_secrets: bool = False,
    reissue_output: Optional[Path] = None,
    safety_dir: Optional[Path] = None,
    server: Optional[str] = None,
    listen: Optional[str] = None,
    port: Optional[Union[int, str]] = None,
    service_account: Optional[Mapping[str, Any]] = None,
    new_instance_id: Optional[str] = None,
    new_reality_private: Optional[str] = None,
    new_reality_public: Optional[str] = None,
    new_reality_short_id: Optional[str] = None,
    new_clash_secret: Optional[str] = None,
    reissue_ids: Optional[Mapping[str, Mapping[str, str]]] = None,
    project_version: Optional[str] = None,
    now: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify, preflight, safety-backup, stage, and commit dest files.

    The first mutation of dest happens after verify_archive and preflight.
    Failure restores the safety tree and never edits the source archive.
    """
    archive = Path(archive)
    dest_state_dir = Path(dest_state_dir)
    verified, members = _load_verified_members(archive, age_identity)
    installed = (dest_state_dir / "VERSION").is_file()
    preflight_restore(
        verified, installed=installed, include_secrets=include_secrets
    )

    try:
        state = json.loads(members["state.json"].decode("utf-8"))
        users = json.loads(members["users.json"].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RestoreError(f"invalid_archive: {exc}", "invalid_archive") from exc
    config_toml = members.get("config.toml", b"").decode("utf-8")
    accounting = members.get("accounting.db")

    env_iid = new_instance_id or os.environ.get("VCL_RESTORE_INSTANCE_ID") or ""
    env_priv = new_reality_private or os.environ.get("VCL_RESTORE_REALITY_PRIVATE") or ""
    env_pub = new_reality_public or os.environ.get("VCL_RESTORE_REALITY_PUBLIC") or ""
    env_sid = new_reality_short_id or os.environ.get("VCL_RESTORE_REALITY_SHORT_ID") or ""
    env_clash = new_clash_secret or os.environ.get("VCL_RESTORE_CLASH_SECRET") or ""
    if not env_iid:
        node = state.get("node") if isinstance(state.get("node"), dict) else {}
        env_iid = mint_instance_id(str(node.get("node_id") or verified.get("source_node_id") or ""))
    secrets_mode = include_secrets and bool(verified.get("secret_bearing"))
    if not secrets_mode:
        if not env_priv or not env_pub or not env_sid:
            raise RestoreError(
                "safe restore requires Reality keys "
                "(pass --new-reality-* or set VCL_RESTORE_REALITY_*)."
            )
        if not env_clash:
            env_clash = secrets_mod.token_urlsafe(32)

    plan = build_restore_plan(
        state=state,
        users=users,
        config_toml=config_toml,
        accounting=accounting,
        manifest=verified,
        include_secrets=include_secrets,
        new_instance_id=env_iid,
        new_reality_private=env_priv,
        new_reality_public=env_pub,
        new_reality_short_id=env_sid,
        new_clash_secret=env_clash,
        target_server=server,
        target_listen=listen,
        target_port=port,
        target_service_account=service_account,
        reissue_ids=reissue_ids,
        project_version=project_version,
        now=now,
    )

    if safety_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safety_path = dest_state_dir.parent / f"pre-restore-{stamp}"
    else:
        safety_path = Path(safety_dir)
    copied = _safety_copy_existing(dest_state_dir, dest_accounting_db, safety_path)

    fail_after = os.environ.get("VCL_RESTORE_FAIL_AFTER", "").strip()
    if fail_after == "stage":
        write_restore_marker(safety_path, "restore-rollback", status="rolled-back")
        raise RestoreError("restore failure injected after stage", "injected_failure")

    written: List[str] = []
    try:
        dest_state_dir.mkdir(parents=True, exist_ok=True)
        _write_private(dest_state_dir / "state.json", _dumps(plan["state"]))
        written.append("state.json")
        _write_private(dest_state_dir / "users.json", _dumps(plan["users"]))
        written.append("users.json")
        _write_private(
            dest_state_dir / "config.toml",
            str(plan["config_toml"]).encode("utf-8"),
        )
        written.append("config.toml")
        version = (
            project_version
            or str(plan["state"].get("project_version") or "")
            or "0.3.0-dev"
        )
        _write_private(dest_state_dir / "VERSION", (version + "\n").encode("utf-8"))
        written.append("VERSION")
        if plan.get("owner_uri"):
            _write_private(
                dest_state_dir / "owner.uri",
                (str(plan["owner_uri"]) + "\n").encode("utf-8"),
            )
            written.append("owner.uri")
        if plan.get("accounting") is not None and dest_accounting_db is not None:
            db_dest = Path(dest_accounting_db)
            db_dest.parent.mkdir(parents=True, exist_ok=True)
            _write_private(db_dest, bytes(plan["accounting"]))
            written.append("accounting.db")
        if fail_after == "install":
            raise RestoreError(
                "restore failure injected after install", "injected_failure"
            )
    except Exception:
        rollback_restore(safety_path, dest_state_dir, dest_accounting_db, written)
        raise

    csv_path = None
    if plan["mode"] == "safe" and plan["reissue_rows"]:
        if reissue_output is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            csv_path = dest_state_dir.parent / f"reissue-{plan['node_id']}-{stamp}.csv"
        else:
            csv_path = Path(reissue_output)
        write_reissue_csv(csv_path, plan["reissue_rows"])
        print(
            f"WARNING: {csv_path} contains authentication credentials.\n"
            "Store and distribute it securely.",
            file=sys.stderr,
        )

    write_restore_marker(safety_path, "restore-safety", status="committed")
    _ = copied
    return {
        "schema_version": 1,
        "ok": True,
        "mode": plan["mode"],
        "node_id": plan["node_id"],
        "source_instance_id": plan["source_instance_id"],
        "instance_id": plan["new_instance_id"],
        "secret_bearing": bool(verified.get("secret_bearing")),
        "reissue_csv": str(csv_path) if csv_path else None,
        "users_reissued": len(plan["reissue_rows"]),
        "safety_backup": str(safety_path),
        "reissue_rows": plan["reissue_rows"],
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vincula backup format (secretless default; age optional)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a node backup archive")
    create.add_argument("--state-dir", required=True)
    create.add_argument("--accounting-db", default="")
    create.add_argument("--output", required=True)
    create.add_argument("--include-secrets", action="store_true")
    create.add_argument("--age-recipient", default="")
    create.add_argument("--json", dest="json_flag", action="store_true")

    verify = sub.add_parser("verify", help="verify a backup archive")
    verify.add_argument("file")
    verify.add_argument("--age-identity", default="")
    verify.add_argument("--json", dest="json_flag", action="store_true")

    restore_plan = sub.add_parser(
        "restore-plan", help="build a restore plan from a backup archive"
    )
    restore_plan.add_argument("file")
    restore_plan.add_argument("--age-identity", default="")
    restore_plan.add_argument("--include-secrets", action="store_true")
    restore_plan.add_argument("--server", default="")
    restore_plan.add_argument("--listen", default="")
    restore_plan.add_argument("--port", default="")
    restore_plan.add_argument("--new-instance-id", default="")
    restore_plan.add_argument("--new-reality-private", default="")
    restore_plan.add_argument("--new-reality-public", default="")
    restore_plan.add_argument("--new-reality-short-id", default="")
    restore_plan.add_argument("--new-clash-secret", default="")
    restore_plan.add_argument("--project-version", default="")
    restore_plan.add_argument("--json", dest="json_flag", action="store_true")
    restore = sub.add_parser("restore", help="restore a backup onto a fresh node")
    restore.add_argument("file")
    restore.add_argument("--age-identity", default="")
    restore.add_argument("--include-secrets", action="store_true")
    restore.add_argument("--reissue-output", default="")
    restore.add_argument("--server", default="")
    restore.add_argument("--listen", default="")
    restore.add_argument("--port", default="")
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--target-state-dir", default="")
    restore.add_argument("--target-accounting-db", default="")
    restore.add_argument("--safety-dir", default="")
    restore.add_argument("--new-instance-id", default="")
    restore.add_argument("--new-reality-private", default="")
    restore.add_argument("--new-reality-public", default="")
    restore.add_argument("--new-reality-short-id", default="")
    restore.add_argument("--new-clash-secret", default="")
    restore.add_argument("--project-version", default="")
    restore.add_argument("--json", dest="json_flag", action="store_true")
    return parser.parse_args(argv)


def _print_restore_failure(exc: RestoreError, json_flag: bool) -> int:
    payload = {"schema_version": 1, "ok": False, "error": exc.code}
    if json_flag:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"ERROR: {exc.message}", file=sys.stderr)
    return 1


def _plan_from_archive(args: argparse.Namespace) -> Dict[str, Any]:
    identity = Path(args.age_identity) if args.age_identity else None
    verified, members = _load_verified_members(Path(args.file), identity)
    preflight_restore(
        verified, installed=False, include_secrets=bool(args.include_secrets)
    )
    state = json.loads(members["state.json"].decode("utf-8"))
    users = json.loads(members["users.json"].decode("utf-8"))
    config_toml = members.get("config.toml", b"").decode("utf-8")
    node = state.get("node") if isinstance(state.get("node"), dict) else {}
    iid = args.new_instance_id or os.environ.get("VCL_RESTORE_INSTANCE_ID") or ""
    if not iid:
        iid = mint_instance_id(str(node.get("node_id") or verified.get("source_node_id") or ""))
    priv = args.new_reality_private or os.environ.get("VCL_RESTORE_REALITY_PRIVATE") or ""
    pub = args.new_reality_public or os.environ.get("VCL_RESTORE_REALITY_PUBLIC") or ""
    sid = args.new_reality_short_id or os.environ.get("VCL_RESTORE_REALITY_SHORT_ID") or ""
    clash = args.new_clash_secret or os.environ.get("VCL_RESTORE_CLASH_SECRET") or ""
    secrets_mode = bool(args.include_secrets) and bool(verified.get("secret_bearing"))
    if not secrets_mode:
        if not priv or not pub or not sid:
            raise RestoreError(
                "safe restore requires Reality keys "
                "(pass --new-reality-* or set VCL_RESTORE_REALITY_*)."
            )
        if not clash:
            clash = secrets_mod.token_urlsafe(32)
    port = args.port or None
    return build_restore_plan(
        state=state,
        users=users,
        config_toml=config_toml,
        accounting=members.get("accounting.db"),
        manifest=verified,
        include_secrets=bool(args.include_secrets),
        new_instance_id=iid,
        new_reality_private=priv,
        new_reality_public=pub,
        new_reality_short_id=sid,
        new_clash_secret=clash,
        target_server=args.server or None,
        target_listen=args.listen or None,
        target_port=port,
        project_version=args.project_version or None,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "restore-plan":
        try:
            plan = _plan_from_archive(args)
        except RestoreError as exc:
            return _print_restore_failure(exc, bool(getattr(args, "json_flag", False)))
        summary = {
            "schema_version": 1,
            "ok": True,
            "mode": plan["mode"],
            "node_id": plan["node_id"],
            "source_instance_id": plan["source_instance_id"],
            "instance_id": plan["new_instance_id"],
            "users_reissued": len(plan["reissue_rows"]),
            "reissue_rows": plan["reissue_rows"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.command == "restore":
        if not args.target_state_dir:
            print("ERROR: restore requires --target-state-dir DIR.", file=sys.stderr)
            return 2
        identity = Path(args.age_identity) if args.age_identity else None
        db = Path(args.target_accounting_db) if args.target_accounting_db else None
        csv_out = Path(args.reissue_output) if args.reissue_output else None
        safety = Path(args.safety_dir) if args.safety_dir else None
        try:
            result = apply_restore(
                Path(args.file),
                Path(args.target_state_dir),
                dest_accounting_db=db,
                age_identity=identity,
                include_secrets=bool(args.include_secrets),
                reissue_output=csv_out,
                safety_dir=safety,
                server=args.server or None,
                listen=args.listen or None,
                port=args.port or None,
                new_instance_id=args.new_instance_id or None,
                new_reality_private=args.new_reality_private or None,
                new_reality_public=args.new_reality_public or None,
                new_reality_short_id=args.new_reality_short_id or None,
                new_clash_secret=args.new_clash_secret or None,
                project_version=args.project_version or None,
            )
        except RestoreError as exc:
            return _print_restore_failure(exc, bool(args.json_flag))
        public = {k: v for k, v in result.items() if k != "reissue_rows"}
        if args.json_flag:
            print(json.dumps(public, ensure_ascii=False, indent=2))
        else:
            print(f"Restore {result['mode']} node_id={result['node_id']}")
            print(f"instance_id: {result['instance_id']}")
            print(f"source_instance_id: {result['source_instance_id']}")
            if result.get("reissue_csv"):
                print(f"reissue_csv: {result['reissue_csv']}")
            else:
                if result.get("mode") == "secrets":
                    print(SECRET_MODE_NO_CSV_MSG)
            print(f"safety_backup: {result['safety_backup']}")
        return 0
    if args.command == "create":
        db = Path(args.accounting_db) if args.accounting_db else None
        recipient = Path(args.age_recipient) if args.age_recipient else None
        result = create_backup(
            Path(args.state_dir),
            db,
            include_secrets=bool(args.include_secrets),
            output=Path(args.output),
            age_recipient=recipient,
        )
        if args.json_flag:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Backup written to {result['path']}")
            print(f"backup_schema_version: {result['backup_schema_version']}")
            print(f"source_node_id: {result['source_node_id']}")
            print(f"source_instance_id: {result['source_instance_id']}")
            print(f"secret_bearing: {str(result['secret_bearing']).lower()}")
            print(f"encryption: {result['encryption']}")
            print(f"sha256: {result['sha256']}")
        if result.get("secret_bearing"):
            print(
                f"WARNING: {result['path']} contains authentication credentials.\n"
                "Store and distribute it securely.",
                file=sys.stderr,
            )
        return 0
    if args.command == "verify":
        identity = Path(args.age_identity) if args.age_identity else None
        result = verify_archive(args.file, age_identity=identity)
        if args.json_flag:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result.get("ok"):
            included = result.get("included_components") or []
            print(f"Backup OK: {args.file}")
            print(f"schema_version: {result.get('schema_version')}")
            print(f"vincula_version: {result.get('vincula_version')}")
            print(f"created_at: {result.get('created_at')}")
            print(f"source_node_id: {result.get('source_node_id')}")
            print(f"source_instance_id: {result.get('source_instance_id')}")
            print(f"secret_bearing: {str(result.get('secret_bearing')).lower()}")
            print(f"encryption: {result.get('encryption')}")
            print(f"included_components: {', '.join(str(x) for x in included)}")
        else:
            err = str(result.get("error") or "failed")
            if err == "age_identity_required":
                msg = AGE_IDENTITY_MSG
            elif err == "age_required":
                msg = AGE_MISSING_MSG
            else:
                msg = err
            print(f"ERROR: {msg}", file=sys.stderr)
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
