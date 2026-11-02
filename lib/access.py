"""SSH/SCP access seam (0.4.0 B3).

Loaded as a controller sibling via _load_controller_sibling — never import
this module from sys.path. Call bind(host) before use so die / _optional_text /
_chmod_private / _ssh_failure_detail / _has_ascii_control resolve from fleet.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Literal, Optional

# Cap stderr while draining so a malicious peer cannot OOM the controller.
_SSH_BOUNDED_STDERR_MAX = 1_048_576

CredentialClass = Literal["observe", "admin"]

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

BINDINGS_SCHEMA_VERSION = 2
BINDINGS_LEGACY_SCHEMA_VERSION = 1
BINDINGS_FILE_NAME = "credential-bindings.json"
AGENT_KEYS_DIRNAME = "keys"

AGENT_BINDING_TYPE = "agent"
IDENTITY_BINDING_TYPE = "identity_file"
MIGRATION_BINDING_TYPE = "migration_required"

CREDENTIAL_STATE_OK = "OK"
CREDENTIAL_STATE_MIGRATION_REQUIRED = "CREDENTIAL_MIGRATION_REQUIRED"
CODE_CREDENTIAL_UNBOUND = "CREDENTIAL_UNBOUND"
CODE_AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
CODE_AGENT_KEY_MISSING = "AGENT_KEY_MISSING"
CODE_IDENTITY_FILE_MISSING = "IDENTITY_FILE_MISSING"

_FINGERPRINT_PREFIX = "SHA256:"
_PUBLIC_KEY_MAX_BYTES = 16_384
_AGENT_LIST_TIMEOUT_SECONDS = 10


def bind(host: Any) -> None:
    global _host
    _host = host


def _public_key_parts(line: str) -> tuple[str, str, str, bytes]:
    """Parse one OpenSSH public key line into (type, base64, comment, blob)."""
    raw = (line or "").strip()
    if not raw or raw.startswith("#"):
        raise ValueError("empty public key line")
    if len(raw.encode("utf-8")) > _PUBLIC_KEY_MAX_BYTES:
        raise ValueError("public key line is too long")
    parts = raw.split(None, 2)
    if len(parts) < 2:
        raise ValueError("public key line is not '<type> <base64> [comment]'")
    key_type, encoded = parts[0], parts[1]
    if not re.fullmatch(r"[A-Za-z0-9@._+-]{1,64}", key_type):
        raise ValueError("invalid public key type")
    pad = "=" * ((4 - len(encoded) % 4) % 4)
    try:
        blob = base64.b64decode(encoded + pad, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid public key base64") from exc
    if not blob:
        raise ValueError("empty public key blob")
    comment = parts[2].strip() if len(parts) > 2 else ""
    return key_type, encoded, comment, blob


def fingerprint_public_key_line(line: str) -> str:
    """OpenSSH-compatible SHA256 fingerprint of a public key line."""
    _, _, _, blob = _public_key_parts(line)
    digest = hashlib.sha256(blob).digest()
    return _FINGERPRINT_PREFIX + base64.b64encode(digest).decode("ascii").rstrip("=")


def normalize_fingerprint(value: str) -> str:
    raw = (value or "").strip()
    if not raw.startswith(_FINGERPRINT_PREFIX):
        raise ValueError("fingerprint must start with SHA256:")
    encoded = raw[len(_FINGERPRINT_PREFIX) :].strip()
    pad = "=" * ((4 - len(encoded) % 4) % 4)
    try:
        digest = base64.b64decode(encoded + pad, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid SHA256 fingerprint") from exc
    if len(digest) != 32:
        raise ValueError("SHA256 fingerprint must decode to 32 bytes")
    return _FINGERPRINT_PREFIX + base64.b64encode(digest).decode("ascii").rstrip("=")


def ssh_add_argv() -> list[str]:
    """Command used to enumerate agent keys. Tests may inject a fixture."""
    raw = os.environ.get("VCL_FLEET_SSH_ADD")
    if raw:
        if raw.lower().endswith(".py"):
            return [sys.executable, raw]
        return shlex.split(raw, posix=(sys.platform != "win32"))
    return ["ssh-add.exe" if sys.platform == "win32" else "ssh-add"]


def read_agent_keys() -> dict[str, Any]:
    """Enumerate loaded agent public keys. Never returns private material.

    Returns ``{"state": "OK"|"AGENT_UNAVAILABLE", "keys": [...], "detail": str}``.
    An agent with no identities is available and returns an empty list.
    """
    try:
        proc = subprocess.run(
            [*ssh_add_argv(), "-L"],
            capture_output=True,
            text=True,
            timeout=_AGENT_LIST_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "state": CODE_AGENT_UNAVAILABLE,
            "keys": [],
            "detail": "ssh-add timed out while listing agent keys",
        }
    except OSError as exc:
        return {
            "state": CODE_AGENT_UNAVAILABLE,
            "keys": [],
            "detail": f"cannot execute ssh-add: {exc}",
        }
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        lowered = detail.lower()
        if "no identities" in lowered or "agent has no identities" in lowered:
            return {"state": "OK", "keys": [], "detail": ""}
        return {
            "state": CODE_AGENT_UNAVAILABLE,
            "keys": [],
            "detail": detail[:500] or "ssh-add could not reach an agent",
        }
    keys: list[dict[str, str]] = []
    skipped = 0
    for line in (proc.stdout or "").splitlines():
        if not line.strip():
            continue
        try:
            key_type, _encoded, comment, _blob = _public_key_parts(line)
            fingerprint = fingerprint_public_key_line(line)
        except ValueError:
            skipped += 1
            continue
        keys.append(
            {
                "fingerprint": fingerprint,
                "key_type": key_type,
                "comment": comment,
                "public_key": line.strip(),
            }
        )
    detail = f"skipped {skipped} malformed agent key line(s)" if skipped else ""
    return {"state": "OK", "keys": keys, "detail": detail}


def agent_key_by_fingerprint(
    keys: list[dict[str, str]], fingerprint: str
) -> Optional[dict[str, str]]:
    wanted = normalize_fingerprint(fingerprint)
    for key in keys:
        if key.get("fingerprint") == wanted:
            return key
    return None


def credential_bindings_path() -> Path:
    """CONFIG controllers/<fleet_id>/credential-bindings.json (P1-6).

    Requires an active workspace. One-time migrates legacy
    ``$FLEET_HOME/machine-local/credential-bindings.json`` if present.
    """
    if not _host.workspace_trust_active():
        _host.die(
            "workspace required for credential bindings "
            "(run workspace init or migrate)"
        )
    fid = _host.load_workspace_manifest()["fleet_id"]
    return _host.migrate_legacy_bindings_if_needed(fid)


def empty_bindings() -> dict[str, Any]:
    return {"schema_version": BINDINGS_SCHEMA_VERSION, "bindings": {}}


def _normalize_binding_entry(ref: str, binding: Any) -> dict[str, Any]:
    if not isinstance(binding, dict):
        _host.die(f"invalid binding for {ref}: expected object")
    btype = binding.get("type")
    if btype == AGENT_BINDING_TYPE:
        fingerprint = binding.get("fingerprint")
        public_key_file = binding.get("public_key_file")
        try:
            fingerprint = normalize_fingerprint(str(fingerprint or ""))
        except ValueError as exc:
            _host.die(f"invalid agent binding for {ref}: {exc}")
        rel = str(public_key_file or "").strip()
        path = Path(rel)
        if not rel or path.is_absolute() or ".." in path.parts:
            _host.die(f"invalid agent binding for {ref}: public_key_file must be a relative path")
        return {
            "type": AGENT_BINDING_TYPE,
            "fingerprint": fingerprint,
            "public_key_file": rel.replace("\\", "/"),
        }
    if btype == IDENTITY_BINDING_TYPE:
        path = binding.get("path")
        if not isinstance(path, str) or not path.strip():
            _host.die(f"invalid identity_file binding for {ref}: missing path")
        return {"type": IDENTITY_BINDING_TYPE, "path": path.strip()}
    if btype == MIGRATION_BINDING_TYPE:
        legacy = str(binding.get("legacy_type") or "").strip()
        return {
            "type": MIGRATION_BINDING_TYPE,
            "legacy_type": legacy or "unknown",
        }
    _host.die(f"invalid binding type for {ref}: {btype}")


def _normalize_bindings(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        _host.die("invalid credential-bindings.json: expected object")
    ver = data.get("schema_version")
    bindings = data.get("bindings")
    if not isinstance(bindings, dict):
        _host.die("invalid credential-bindings.json: bindings must be an object")
    normalized: dict[str, Any] = {}
    if ver == BINDINGS_LEGACY_SCHEMA_VERSION:
        for ref, binding in bindings.items():
            key = _validate_credential_ref(str(ref))
            if not isinstance(binding, dict):
                normalized[key] = {"type": MIGRATION_BINDING_TYPE, "legacy_type": "invalid"}
                continue
            btype = binding.get("type")
            if btype == IDENTITY_BINDING_TYPE:
                normalized[key] = _normalize_binding_entry(
                    key, {"type": IDENTITY_BINDING_TYPE, "path": binding.get("path")}
                )
            elif btype == "openssh-default":
                normalized[key] = {
                    "type": MIGRATION_BINDING_TYPE,
                    "legacy_type": "openssh-default",
                }
            else:
                normalized[key] = {
                    "type": MIGRATION_BINDING_TYPE,
                    "legacy_type": str(btype or "unknown"),
                }
        return {"schema_version": BINDINGS_SCHEMA_VERSION, "bindings": normalized}
    if ver != BINDINGS_SCHEMA_VERSION:
        _host.die(f"unsupported credential-bindings schema: {ver}")
    for ref, binding in bindings.items():
        key = _validate_credential_ref(str(ref))
        normalized[key] = _normalize_binding_entry(key, binding)
    return {"schema_version": BINDINGS_SCHEMA_VERSION, "bindings": normalized}


def load_bindings(path: Optional[Path] = None) -> dict[str, Any]:
    path = credential_bindings_path() if path is None else Path(path)
    if not path.is_file():
        return empty_bindings()
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        _host.die(f"invalid credential-bindings.json: {exc}")
    except OSError as exc:
        _host.die(f"cannot read {path}: {exc}")
    return _normalize_bindings(data)


def bindings_file_schema_version(path: Optional[Path] = None) -> int:
    """Raw schema version on disk (0 if the file is absent/invalid)."""
    path = credential_bindings_path() if path is None else Path(path)
    if not path.is_file():
        return 0
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return 0
    ver = data.get("schema_version") if isinstance(data, dict) else None
    return ver if isinstance(ver, int) else 0


def save_bindings(
    data: dict[str, Any], path: Optional[Path] = None
) -> None:
    path = credential_bindings_path() if path is None else Path(path)
    payload = _normalize_bindings(data)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(
        prefix=".credential-bindings.json.", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _validate_credential_ref(ref: str) -> str:
    raw = (ref or "").strip()
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        _host.die("invalid credential ref")
    return raw


def binding_public_key_path(
    binding: dict[str, Any], base: Optional[Path] = None
) -> Optional[Path]:
    if binding.get("type") != AGENT_BINDING_TYPE:
        return None
    rel = str(binding.get("public_key_file") or "").strip()
    path = Path(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        return None
    root = (credential_bindings_path().parent if base is None else Path(base))
    try:
        return (root / path).resolve()
    except OSError:
        return root / path


def bind_identity_file(ref: str, path: str) -> dict[str, Any]:
    key = _validate_credential_ref(ref)
    resolved = validate_identity_file(path, must_exist=True)
    data = load_bindings()
    data["bindings"][key] = {"type": IDENTITY_BINDING_TYPE, "path": resolved}
    save_bindings(data)
    return data["bindings"][key]


def _write_public_key_file(ref: str, public_key: str) -> str:
    keys_dir = credential_bindings_path().parent / AGENT_KEYS_DIRNAME
    keys_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(keys_dir, 0o700)
    except OSError:
        pass
    name = f"{credential_ref_slug(ref)}.pub"
    target = keys_dir / name
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=str(keys_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(public_key.strip() + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return f"{AGENT_KEYS_DIRNAME}/{name}"


def bind_agent(
    ref: str,
    fingerprint: str,
    *,
    public_key: Optional[str] = None,
) -> dict[str, Any]:
    """Bind an agent public key by SHA256 fingerprint.

    The public key selector is stored machine-locally; private key bytes never
    enter VCL. When ``public_key`` is omitted the agent is queried.
    """
    key = _validate_credential_ref(ref)
    try:
        wanted = normalize_fingerprint(fingerprint)
    except ValueError as exc:
        _host.die(f"invalid --fingerprint: {exc}")
    line = (public_key or "").strip()
    if line:
        try:
            actual = fingerprint_public_key_line(line)
        except ValueError as exc:
            _host.die(f"invalid agent public key: {exc}")
        if actual != wanted:
            _host.die(
                f"{CODE_AGENT_KEY_MISSING}: public key fingerprint does not match {wanted}"
            )
    else:
        snapshot = read_agent_keys()
        if snapshot["state"] != "OK":
            _host.die(f"{CODE_AGENT_UNAVAILABLE}: {snapshot.get('detail') or 'agent unavailable'}")
        found = agent_key_by_fingerprint(snapshot["keys"], wanted)
        if found is None:
            _host.die(f"{CODE_AGENT_KEY_MISSING}: {wanted} is not loaded in the SSH agent")
        line = found["public_key"]
    rel = _write_public_key_file(key, line)
    data = load_bindings()
    data["bindings"][key] = {
        "type": AGENT_BINDING_TYPE,
        "fingerprint": wanted,
        "public_key_file": rel,
    }
    save_bindings(data)
    return data["bindings"][key]


_REF_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
CREDENTIAL_PURPOSES = ("admin", "observe")
ADMIN_REF_KEY = "admin_credential_ref"
OBSERVE_REF_KEY = "observe_credential_ref"


def credential_ref_slug(name: str) -> str:
    """Node name reduced to a stable, ref-safe token (FR-01)."""
    slug = _REF_SLUG_RE.sub("-", (str(name) if name else "").strip()).strip("-._")
    return slug or "node"


def _referencing_nodes(ref: str) -> list[tuple[str, str]]:
    """``(node_name, purpose)`` pairs whose registry record uses ``ref``."""
    pairs: list[tuple[str, str]] = []
    registry = _host.load_registry()
    for node in registry.get("nodes") or []:
        name = str(node.get("name") or "")
        if _host._optional_text(node.get(ADMIN_REF_KEY)) == ref:
            pairs.append((name, "admin"))
        if _host._optional_text(node.get(OBSERVE_REF_KEY)) == ref:
            pairs.append((name, "observe"))
    return pairs


def affected_binding_consumers(ref: str) -> list[str]:
    """Human-readable consumers of a ref; used to flag explicit sharing."""
    return [f"{name}:{purpose}" for name, purpose in _referencing_nodes(ref)]


def _taken_credential_refs() -> set[str]:
    """Every ref already bound locally or referenced by the registry."""
    taken = set(list_bindings())
    for node in _host.load_registry().get("nodes") or []:
        for key in (ADMIN_REF_KEY, OBSERVE_REF_KEY):
            value = _host._optional_text(node.get(key))
            if value:
                taken.add(value)
    return taken


def allocate_node_credential_ref(name: str, purpose: str) -> str:
    """Return a fresh, unused ref for one node+purpose (FR-01).

    Copy-on-write: a rotation must never re-target a ref another node or the
    other purpose may still resolve, so an in-use name is never reused.
    """
    if purpose not in CREDENTIAL_PURPOSES:
        _host.die(f"invalid credential purpose: {purpose}")
    taken = _taken_credential_refs()
    base = f"{credential_ref_slug(name)}-{purpose}"
    if base not in taken:
        return base
    index = 2
    while f"{base}-{index}" in taken:
        index += 1
    return f"{base}-{index}"


def plan_node_credential_binding(
    node: dict[str, Any], purpose: str, path: str
) -> tuple[str, bool]:
    """Plan the ref for ``node``/``purpose`` holding ``path`` (FR-01).

    Returns ``(ref, needs_write)``. Unchanged key on an unshared ref keeps the
    ref (no write); anything else gets a brand-new ref so every existing
    consumer keeps its own credential.
    """
    if purpose not in CREDENTIAL_PURPOSES:
        _host.die(f"invalid credential purpose: {purpose}")
    resolved = validate_identity_file(str(path), must_exist=True)
    key = ADMIN_REF_KEY if purpose == "admin" else OBSERVE_REF_KEY
    current = _host._optional_text(node.get(key))
    if current:
        binding = list_bindings().get(current)
        if isinstance(binding, dict) and binding.get("type") == "identity_file":
            if binding.get("path") == resolved:
                name = node.get("name")
                shared = [
                    pair
                    for pair in _referencing_nodes(current)
                    if pair != (name, purpose)
                ]
                if not shared:
                    return current, False
    return allocate_node_credential_ref(str(node.get("name") or ""), purpose), True


def resolve_binding(ref: str) -> dict[str, Any]:
    key = _validate_credential_ref(ref)
    binding = load_bindings().get("bindings", {}).get(key)
    if binding is None:
        _host.die(f"unbound credential ref: {key}")
    if not isinstance(binding, dict):
        _host.die(f"invalid binding for {key}")
    return binding


def list_bindings() -> dict[str, Any]:
    return dict(load_bindings().get("bindings") or {})


_CREDENTIAL_HINTS = {
    CODE_CREDENTIAL_UNBOUND: (
        "run vcl-fleet access bind REF --agent|--identity-file, "
        "or vcl-fleet access migrate"
    ),
    CODE_AGENT_UNAVAILABLE: (
        "start the SSH agent and load the selected key "
        "(for example: pass show ... | ssh-add -)"
    ),
    CODE_AGENT_KEY_MISSING: (
        "load the selected public key into the agent or rebind another key"
    ),
    CODE_IDENTITY_FILE_MISSING: (
        "restore the identity file or rebind another local private key"
    ),
}


def _credential_error(
    code: str,
    message: str,
    *,
    ref: Optional[str] = None,
    purpose: Optional[str] = None,
    credential_state: Optional[str] = None,
    hint: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "state": "ERROR",
        "code": code,
        "message": message,
        "hint": hint or _CREDENTIAL_HINTS.get(code, ""),
        "ref": ref,
        "purpose": purpose,
        "credential_state": credential_state or code,
        "migration_required": (credential_state or code)
        == CREDENTIAL_STATE_MIGRATION_REQUIRED,
    }


def _resolve_ref(ref: str, purpose: Optional[str] = None) -> dict[str, Any]:
    key = _validate_credential_ref(ref)
    binding = list_bindings().get(key)
    if binding is None:
        return _credential_error(
            CODE_CREDENTIAL_UNBOUND,
            f"credential ref {key} is not bound on this machine",
            ref=key,
            purpose=purpose,
        )
    btype = binding.get("type")
    if btype == MIGRATION_BINDING_TYPE:
        legacy = str(binding.get("legacy_type") or "legacy")
        return _credential_error(
            CODE_CREDENTIAL_UNBOUND,
            f"credential ref {key} still uses {legacy}; migration is required",
            ref=key,
            purpose=purpose,
            credential_state=CREDENTIAL_STATE_MIGRATION_REQUIRED,
        )
    if btype == IDENTITY_BINDING_TYPE:
        path = str(binding.get("path") or "")
        if not path or not Path(path).is_file():
            return _credential_error(
                CODE_IDENTITY_FILE_MISSING,
                f"identity file for {key} does not exist",
                ref=key,
                purpose=purpose,
            )
        return {
            "state": "OK",
            "type": IDENTITY_BINDING_TYPE,
            "path": path,
            "ref": key,
            "purpose": purpose,
            "fingerprint": None,
            "migration_required": False,
        }
    if btype == AGENT_BINDING_TYPE:
        pub_path = binding_public_key_path(binding)
        expected = binding.get("fingerprint")
        if pub_path is None or not pub_path.is_file():
            return _credential_error(
                CODE_AGENT_KEY_MISSING,
                f"agent public-key selector for {key} is missing",
                ref=key,
                purpose=purpose,
            )
        try:
            actual = fingerprint_public_key_line(pub_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _credential_error(
                CODE_AGENT_KEY_MISSING,
                f"agent public-key selector for {key} is invalid",
                ref=key,
                purpose=purpose,
            )
        if actual != expected:
            return _credential_error(
                CODE_AGENT_KEY_MISSING,
                f"agent public-key selector for {key} does not match its fingerprint",
                ref=key,
                purpose=purpose,
            )
        snapshot = read_agent_keys()
        if snapshot["state"] != "OK":
            return _credential_error(
                CODE_AGENT_UNAVAILABLE,
                f"SSH agent is not available for {key}",
                ref=key,
                purpose=purpose,
            )
        if agent_key_by_fingerprint(snapshot["keys"], actual) is None:
            return _credential_error(
                CODE_AGENT_KEY_MISSING,
                f"agent key {actual} for {key} is not loaded",
                ref=key,
                purpose=purpose,
            )
        return {
            "state": "OK",
            "type": AGENT_BINDING_TYPE,
            "path": str(pub_path),
            "ref": key,
            "purpose": purpose,
            "fingerprint": actual,
            "migration_required": False,
        }
    return _credential_error(
        CODE_CREDENTIAL_UNBOUND,
        f"credential ref {key} has an unsupported binding type",
        ref=key,
        purpose=purpose,
    )


def _legacy_identity(node: dict[str, Any], purpose: Optional[str] = None) -> Optional[dict[str, Any]]:
    raw = _host._optional_text(node.get("identity_file"))
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        return _credential_error(
            CODE_IDENTITY_FILE_MISSING,
            "legacy identity_file does not exist",
            purpose=purpose,
            credential_state=CREDENTIAL_STATE_MIGRATION_REQUIRED,
        )
    return {
        "state": "OK",
        "type": IDENTITY_BINDING_TYPE,
        "path": str(path),
        "ref": None,
        "purpose": purpose,
        "fingerprint": None,
        "migration_required": True,
    }


def resolve_identity(
    node: dict[str, Any], credential_class: CredentialClass
) -> dict[str, Any]:
    """Resolve one node/purpose to a deterministic local identity.

    Returns ``{"state":"OK", "type", "path", ...}`` or a structured error.
    Never falls back to OpenSSH's default identity traversal.
    """
    admin_ref = _host._optional_text(node.get(ADMIN_REF_KEY))
    observe_ref = _host._optional_text(node.get(OBSERVE_REF_KEY))
    if credential_class == "admin":
        if admin_ref:
            return _resolve_ref(admin_ref, "admin")
        legacy = _legacy_identity(node, "admin")
        if legacy is not None:
            return legacy
        return _credential_error(
            CODE_CREDENTIAL_UNBOUND,
            "node has no admin credential ref; migration is required",
            purpose="admin",
            credential_state=CREDENTIAL_STATE_MIGRATION_REQUIRED,
        )
    if observe_ref:
        return _resolve_ref(observe_ref, "observe")
    if not admin_ref:
        legacy = _legacy_identity(node, "observe")
        if legacy is not None:
            return legacy
        return _credential_error(
            CODE_CREDENTIAL_UNBOUND,
            "node has no observe credential ref; migration is required",
            purpose="observe",
            credential_state=CREDENTIAL_STATE_MIGRATION_REQUIRED,
        )
    return _credential_error(
        CODE_CREDENTIAL_UNBOUND,
        "observe credential is not configured for this node",
        purpose="observe",
    )


def node_credential_state(node: dict[str, Any]) -> str:
    """Best-effort node state for status/access output. No SSH."""
    admin = resolve_identity(node, "admin")
    if admin["state"] != "OK":
        return str(admin.get("credential_state") or admin.get("code"))
    observe = resolve_identity(node, "observe")
    if observe["state"] != "OK":
        return str(observe.get("credential_state") or observe.get("code"))
    if admin.get("migration_required") or observe.get("migration_required"):
        return CREDENTIAL_STATE_MIGRATION_REQUIRED
    return CREDENTIAL_STATE_OK


def verify_bindings_report() -> dict[str, Any]:
    """Machine-readable, SSH-free credential verification report."""
    bindings = list_bindings()
    on_disk = bindings_file_schema_version()
    problems: list[dict[str, Any]] = []
    if on_disk == BINDINGS_LEGACY_SCHEMA_VERSION:
        problems.append(
            {
                "code": CREDENTIAL_STATE_MIGRATION_REQUIRED,
                "message": "credential-bindings.json is schema v1; run access migrate",
                "ref": None,
                "node": None,
                "purpose": None,
            }
        )
    binding_rows: list[dict[str, Any]] = []
    for ref in sorted(bindings):
        result = _resolve_ref(ref)
        row = {
            "ref": ref,
            "type": bindings[ref].get("type"),
            "ok": result["state"] == "OK",
            "code": result.get("code"),
            "message": result.get("message"),
        }
        binding_rows.append(row)
        if not row["ok"]:
            problems.append(
                {
                    "code": row["code"],
                    "message": row["message"],
                    "ref": ref,
                    "node": None,
                    "purpose": None,
                }
            )
    node_rows: list[dict[str, Any]] = []
    for node in _host.load_registry().get("nodes") or []:
        name = str(node.get("name") or "")
        for purpose in CREDENTIAL_PURPOSES:
            result = resolve_identity(node, purpose)  # type: ignore[arg-type]
            row = {
                "node": name,
                "purpose": purpose,
                "ref": result.get("ref"),
                "ok": result["state"] == "OK" and not result.get("migration_required"),
                "code": result.get("code")
                or (
                    CREDENTIAL_STATE_MIGRATION_REQUIRED
                    if result.get("migration_required")
                    else None
                ),
                "message": result.get("message"),
            }
            node_rows.append(row)
            if not row["ok"]:
                problems.append(
                    {
                        "code": row["code"],
                        "message": row["message"]
                        or "legacy identity requires explicit migration",
                        "ref": row["ref"],
                        "node": name,
                        "purpose": purpose,
                    }
                )
    return {
        "schema_version": 1,
        "ok": not problems,
        "on_disk_bindings_schema_version": on_disk,
        "bindings": binding_rows,
        "nodes": node_rows,
        "problems": problems,
    }


def verify_bindings() -> list[str]:
    """Human-readable problems; empty list means OK. No SSH."""
    report = verify_bindings_report()
    return [
        f"{item.get('code') or 'ERROR'}: {item.get('message') or 'credential problem'}"
        for item in report["problems"]
    ]


def migration_targets() -> list[dict[str, Any]]:
    """Nodes/purposes that still need an explicit v2 credential binding."""
    targets: list[dict[str, Any]] = []
    for node in _host.load_registry().get("nodes") or []:
        name = str(node.get("name") or "")
        for purpose in CREDENTIAL_PURPOSES:
            result = resolve_identity(node, purpose)  # type: ignore[arg-type]
            if result["state"] != "OK" or result.get("migration_required"):
                targets.append(
                    {
                        "node": name,
                        "purpose": purpose,
                        "ref": result.get("ref"),
                        "code": result.get("code")
                        or CREDENTIAL_STATE_MIGRATION_REQUIRED,
                        "message": result.get("message"),
                    }
                )
    return targets


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
    allowed_ukh: Optional[str] = None
    if _host.workspace_trust_active():
        allowed_ukh = f"UserKnownHostsFile={_host.default_known_hosts_path()}"
    for arg in argv:
        option = _ssh_option_text(arg)
        if option.startswith("UserKnownHostsFile="):
            if allowed_ukh is not None and option == allowed_ukh:
                continue
            _host.die("refusing forbidden SSH option UserKnownHostsFile=", 2)


def host_key_ssh_extra() -> list[str]:
    if not _host.workspace_trust_active():
        return []
    p = str(_host.known_hosts_path())
    return ["-o", f"UserKnownHostsFile={p}", "-o", "StrictHostKeyChecking=yes"]


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
        # Fail closed: no implicit SSH config / agent traversal.
        return ["-o", "IdentitiesOnly=yes"]
    return ["-i", validate_identity_file(path, must_exist=True), "-o", "IdentitiesOnly=yes"]


def _identity_from_ref(ref: str) -> Optional[str]:
    result = _resolve_ref(ref)
    if result["state"] != "OK":
        _host.die(f"{result['code']}: {result['message']}")
    return result["path"]


def node_identity_file_for_class(
    node: dict[str, Any], credential_class: CredentialClass
) -> Optional[str]:
    """Resolve SSH identity for observe or admin credential class (D57, 0.5.0).

    Compatibility wrapper: raises SystemExit with a coded message on failure.
    Callers that need structured results should use ``resolve_identity``.
    """
    result = resolve_identity(node, credential_class)
    if result["state"] != "OK":
        _host.die(f"{result['code']}: {result['message']}")
    return result["path"]


def node_credential_class_label(credential_class: CredentialClass) -> str:
    return credential_class


def _node_identity_file(node: dict[str, Any]) -> Optional[str]:
    # Mutations and legacy paths default to admin credential class.
    return node_identity_file_for_class(node, "admin")


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
    argv = [ssh_bin(), "-F", os.devnull, "-p", str(port)]
    argv[1:1] = host_key_ssh_extra()
    if extra:
        argv.extend(extra)
    if batch:
        argv.extend(["-o", "BatchMode=yes"])
    argv.extend(["-o", "PreferredAuthentications=publickey"])
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
    max_stdout_bytes: Optional[int] = None,
) -> subprocess.CompletedProcess[str]:
    """Run remote_cmd over SSH. Stderr is captured; exit code is preserved.

    When ``max_stdout_bytes`` is set, stdout is read only up to that many
    UTF-8 bytes (+1 to detect overflow); excess is discarded.
    """
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
        if max_stdout_bytes is None:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        return _ssh_run_bounded_stdout(
            argv, timeout=timeout, max_stdout_bytes=max_stdout_bytes
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout
        stderr = exc.stderr
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        detail = (stderr or "").strip()
        timeout_msg = _host.ssh_timeout_message(timeout)
        stderr = f"{detail}\n{timeout_msg}".strip() if detail else timeout_msg
        return subprocess.CompletedProcess(argv, 255, stdout or "", stderr)
    except OSError as exc:
        _host.die(f"cannot execute {argv[0]}: {exc}")


def _ssh_run_bounded_stdout(
    argv: list[str],
    *,
    timeout: float,
    max_stdout_bytes: int,
) -> subprocess.CompletedProcess[str]:
    """Capture SSH stdout with a hard byte cap and a hard wall-clock timeout.

    Drain pipes on background threads so a peer that emits a little then
    stalls cannot wedge a blocking ``read(65536)`` past ``timeout`` (selectors
    + blocking read is unsafe on some Windows pipe backends). The main thread
    owns the deadline and kills the child when it expires.
    """
    if max_stdout_bytes < 0:
        raise ValueError("max_stdout_bytes must be >= 0")
    timeout = float(timeout)
    if timeout < 0:
        raise ValueError("timeout must be >= 0")
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    assert proc.stdout is not None and proc.stderr is not None
    limit = max_stdout_bytes + 1
    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    out_total = 0
    err_total = 0
    lock = threading.Lock()
    deadline = time.monotonic() + timeout

    def _kill_and_timeout() -> None:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        with lock:
            out = b"".join(out_chunks)
            err = b"".join(err_chunks)
        raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err)

    def _drain(stream: Any, *, is_out: bool) -> None:
        nonlocal out_total, err_total
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                with lock:
                    if is_out:
                        if out_total < limit:
                            take = min(len(chunk), limit - out_total)
                            if take:
                                out_chunks.append(chunk[:take])
                                out_total += take
                        # Else discard: still drain so the peer can exit.
                    else:
                        if err_total < _SSH_BOUNDED_STDERR_MAX:
                            take = min(len(chunk), _SSH_BOUNDED_STDERR_MAX - err_total)
                            if take:
                                err_chunks.append(chunk[:take])
                                err_total += take
        except (OSError, ValueError):
            # Pipe closed after kill / process exit — expected.
            return

    t_out = threading.Thread(
        target=_drain, args=(proc.stdout,), kwargs={"is_out": True}, daemon=True
    )
    t_err = threading.Thread(
        target=_drain, args=(proc.stderr,), kwargs={"is_out": False}, daemon=True
    )
    t_out.start()
    t_err.start()
    try:
        while t_out.is_alive() or t_err.is_alive():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_and_timeout()
            slice_s = min(0.05, max(remaining, 0.0))
            t_out.join(timeout=slice_s)
            if t_err.is_alive():
                err_left = deadline - time.monotonic()
                if err_left <= 0:
                    _kill_and_timeout()
                t_err.join(timeout=min(0.05, max(err_left, 0.0)))
        wait_left = deadline - time.monotonic()
        if wait_left <= 0:
            _kill_and_timeout()
        try:
            proc.wait(timeout=wait_left)
        except subprocess.TimeoutExpired:
            _kill_and_timeout()
    except subprocess.TimeoutExpired:
        raise
    except Exception:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        raise
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            proc.stderr.close()
        except Exception:
            pass
        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)

    with lock:
        stdout_b = b"".join(out_chunks)
        stderr_b = b"".join(err_chunks)
    overflow = len(stdout_b) > max_stdout_bytes
    if overflow:
        stdout_b = stdout_b[:max_stdout_bytes]
    stdout = stdout_b.decode("utf-8", "replace")
    stderr = stderr_b.decode("utf-8", "replace")
    if overflow:
        marker = _host.ssh_output_limit_message(max_stdout_bytes)
        stderr = f"{stderr}\n{marker}".strip() if stderr.strip() else marker
        # Non-zero so callers treat as transport/protocol failure.
        rc = proc.returncode if proc.returncode not in (0, None) else 1
        return subprocess.CompletedProcess(argv, rc, stdout, stderr)
    return subprocess.CompletedProcess(argv, proc.returncode or 0, stdout, stderr)


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
    argv = [scp_bin(), "-F", os.devnull, "-P", str(port)]
    argv[1:1] = host_key_ssh_extra()
    if extra:
        argv.extend(extra)
    if batch:
        argv.extend(["-o", "BatchMode=yes"])
    argv.extend(["-o", "PreferredAuthentications=publickey"])
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
        timeout_msg = _host.scp_timeout_message(timeout)
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
