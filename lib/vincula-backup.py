#!/usr/bin/env python3
"""vincula-backup — backup format, secretless rendering, and SQLite snapshots.

Default backups are secretless identity/audit archives: they keep node_id,
instance_id, user_id, credential_id history, and accounting, and strip
node.reality_private_key, credentials[].uuid, and clash_api_secret.
They do not require age.

`--include-secrets` keeps those three files verbatim and requires whole-archive
age encryption (`age -e -R` recipient file). Secret-bearing archives are never
written as plaintext tar.

Accounting snapshots use sqlite3.Connection.backup() so a live WAL writer
(accountd) is safe. Do not copy live database files.

Stdlib only. Targets Python 3.10+.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Union
from urllib.parse import quote

BACKUP_SCHEMA_VERSION = 1
BACKUP_SCHEMA_VERSIONS_READ = (1,)
AGE_MISSING_MSG = "Secret-bearing backup requires age."
AGE_RECIPIENT_MSG = "Secret-bearing backup requires --age-recipient FILE."
AGE_IDENTITY_MSG = "Encrypted backup verify requires --age-identity FILE."
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

    sub.add_parser("restore-plan", help="placeholder; restore lands in a later batch")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "restore-plan":
        print("ERROR: restore-plan is not implemented in this build.", file=sys.stderr)
        return 2
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
        return 0
    if args.command == "verify":
        identity = Path(args.age_identity) if args.age_identity else None
        result = verify_archive(args.file, age_identity=identity)
        if args.json_flag:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result.get("ok"):
            print(f"Backup OK: {args.file}")
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
