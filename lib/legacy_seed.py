#!/usr/bin/env python3
"""Legacy single-user seed helpers (VCL 0.4.5).

Stdlib only. Validates local secret files, VLESS Reality URI constraints,
and derives Reality public keys (X25519) for constant-time pbk checks.
Never logs URI, UUID, or private key material — errors cite path + type only.

Installer entry: ``validate-seed URI_FILE KEY_FILE TAG`` (path-only argv).
"""
from __future__ import annotations

import argparse
import base64
import hmac
import ipaddress
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import NamedTuple, Optional
from urllib.parse import parse_qsl, unquote, urlparse

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
SHORT_ID_RE = re.compile(r"^[0-9a-f]{1,16}$", re.IGNORECASE)
# sing-box Reality keys: URL-safe base64 of 32 bytes (43–44 chars, optional =).
REALITY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{43,44}={0,2}$")
# Same contract as is_valid_user_tag / vincula-common.sh.
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
# DNS label rules aligned with vincula.sh is_dns_name (requires a dot / multi-label).
DNS_NAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
    r"(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)

# VCL-compatible Reality fingerprints (normalize to chrome on install).
COMPAT_FP = frozenset({"", "chrome", "chrome_auto", "randomized"})
# Reject duplicate values for these query keys.
CRITICAL_QS_KEYS = frozenset(
    {"encryption", "flow", "security", "type", "sni", "fp", "pbk", "sid"}
)

P = 2**255 - 19
A24 = 121665


class LegacySeedError(ValueError):
    """Fail-closed validation error (safe message; no secret content)."""


class LegacySeedInput(NamedTuple):
    uri_path: Path
    private_key_path: Path
    user_tag: str
    uuid: str
    server: str
    port: int
    sni: str
    public_key: str
    short_id: str
    private_key: str
    fingerprint: str


def _b64url_decode_32(raw: str) -> bytes:
    s = raw.strip()
    pad = "=" * ((4 - len(s) % 4) % 4)
    try:
        data = base64.urlsafe_b64decode(s + pad)
    except Exception as exc:  # noqa: BLE001
        raise LegacySeedError("invalid Reality key encoding") from exc
    if len(data) != 32:
        raise LegacySeedError("invalid Reality key length")
    return data


def _b64url_encode_32(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _x25519_scalarmult_base(private: bytes) -> bytes:
    """Pure-Python X25519 public key from 32-byte private key (RFC 7748)."""
    if len(private) != 32:
        raise LegacySeedError("invalid Reality private key length")
    k = bytearray(private)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    n = int.from_bytes(k, "little")

    x1 = 9
    x2, z2 = 1, 0
    x3, z3 = x1, 1
    swap = 0
    for t in range(254, -1, -1):
        kt = (n >> t) & 1
        swap ^= kt
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = kt
        a = (x2 + z2) % P
        aa = (a * a) % P
        b = (x2 - z2) % P
        bb = (b * b) % P
        e = (aa - bb) % P
        c = (x3 + z3) % P
        d = (x3 - z3) % P
        da = (d * a) % P
        cb = (c * b) % P
        x3 = ((da + cb) % P) ** 2 % P
        z3 = (x1 * (((da - cb) % P) ** 2 % P)) % P
        x2 = (aa * bb) % P
        z2 = (e * ((aa + (A24 * e) % P) % P)) % P
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    inv_z = pow(z2, P - 2, P)
    return ((x2 * inv_z) % P).to_bytes(32, "little")


def derive_reality_public_key(private_key: str) -> str:
    """Derive Reality public key (URL-safe base64) from private key string."""
    priv = _b64url_decode_32(private_key)
    pub = _x25519_scalarmult_base(priv)
    return _b64url_encode_32(pub)


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def validate_user_tag(tag: str) -> str:
    """Return normalized tag or raise LegacySeedError."""
    t = (tag or "").strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in t):
        raise LegacySeedError("invalid legacy user tag")
    if not TAG_RE.match(t):
        raise LegacySeedError("invalid legacy user tag")
    if t == "owner":
        raise LegacySeedError("legacy user tag must not be owner")
    return t


def validate_server_host(value: str) -> bool:
    """IPv4, unbracketed IPv6, or DNS name (matches vincula.sh validate_server)."""
    v = (value or "").strip()
    if not v or any(ord(ch) < 32 for ch in v):
        return False
    if ":" in v:
        try:
            ipaddress.IPv6Address(v)
            return True
        except ValueError:
            return False
    if re.match(r"^[0-9.]+$", v):
        try:
            ipaddress.IPv4Address(v)
            return True
        except ValueError:
            return False
    # Multi-label DNS (same as is_dns_name: requires a dot).
    if "." not in v or ".." in v:
        return False
    return bool(DNS_NAME_RE.match(v))


def validate_sni_host(value: str) -> bool:
    """Reality SNI must be a multi-label DNS name (matches is_dns_name)."""
    v = (value or "").strip()
    if not v or any(ord(ch) < 32 for ch in v):
        return False
    if "." not in v or ".." in v:
        return False
    return bool(DNS_NAME_RE.match(v))


def allowed_secret_owners() -> set[int]:
    """UIDs allowed to own secret files.

    When running as root under sudo, accept the invoking user's SUDO_UID
    (and root) so ``sudo bash vincula.sh --legacy-*-file …`` works on 0600
    caller-owned files. Non-root ignores forged SUDO_UID.
    """
    if not hasattr(os, "geteuid"):
        return set()
    euid = os.geteuid()
    allowed = {euid}
    if euid == 0:
        raw = (os.environ.get("SUDO_UID") or "").strip()
        if raw.isdigit():
            allowed.add(int(raw))
    return allowed


def validate_secret_file(path: Path, *, label: str) -> Path:
    """Fail-closed local secret file checks (V0.4.5 §3.3).

    Regular file, owned by current user (or verified SUDO_UID when root),
    not group/world readable, no symlink (fail-close), not dir/FIFO/socket.
    """
    raw = Path(path)
    try:
        # lstat: do not follow symlinks
        st = raw.lstat()
    except OSError as exc:
        raise LegacySeedError(f"{label}: cannot stat ({exc.errno})") from exc
    if stat.S_ISLNK(st.st_mode):
        raise LegacySeedError(f"{label}: symlink refused")
    if not stat.S_ISREG(st.st_mode):
        raise LegacySeedError(f"{label}: not a regular file")
    if hasattr(os, "getuid"):
        if st.st_uid not in allowed_secret_owners():
            raise LegacySeedError(f"{label}: not owned by current user")
        # Unix permission bits are meaningful on POSIX only (Windows chmod is ACL-mapped).
        mode = stat.S_IMODE(st.st_mode)
        if mode & 0o077:
            raise LegacySeedError(f"{label}: group/world readable refused")
    return raw.resolve(strict=True)


def _read_first_nonempty_line(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except OSError as exc:
        raise LegacySeedError(f"cannot read file ({exc.errno})") from exc
    except UnicodeError as exc:
        raise LegacySeedError("file is not valid UTF-8") from exc
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    raise LegacySeedError("file is empty")


def _read_single_key_line(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except OSError as exc:
        raise LegacySeedError(f"cannot read file ({exc.errno})") from exc
    except UnicodeError as exc:
        raise LegacySeedError("file is not valid UTF-8") from exc
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise LegacySeedError("private key file is empty")
    if len(lines) != 1:
        raise LegacySeedError("private key file must contain exactly one key")
    key = lines[0]
    if not REALITY_KEY_RE.match(key):
        raise LegacySeedError("invalid Reality private key format")
    return key


def _parse_query_no_dup(query: str) -> dict[str, str]:
    """Parse query string; refuse duplicate critical keys."""
    seen: dict[str, str] = {}
    counts: dict[str, int] = {}
    for key, value in parse_qsl(query, keep_blank_values=True):
        k = key.lower()
        counts[k] = counts.get(k, 0) + 1
        if k in CRITICAL_QS_KEYS and counts[k] > 1:
            raise LegacySeedError(f"duplicate query parameter: {k}")
        if k not in seen:
            seen[k] = value
    return seen


def parse_legacy_vless_uri(uri: str) -> dict[str, str | int]:
    """Parse and validate a VCL-fixed VLESS+Reality URI. Raises LegacySeedError."""
    raw = uri.strip()
    if "\n" in raw or "\r" in raw:
        raise LegacySeedError("URI must be a single line")
    if not raw.lower().startswith("vless://"):
        raise LegacySeedError("scheme must be vless")
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise LegacySeedError("invalid URI") from exc
    if parsed.scheme.lower() != "vless":
        raise LegacySeedError("scheme must be vless")
    if parsed.password is not None:
        raise LegacySeedError("URI userinfo must not include a password")
    path = parsed.path or ""
    if path not in ("", "/"):
        raise LegacySeedError("URI must not include a path")
    uuid = unquote(parsed.username or "")
    if not UUID_RE.match(uuid):
        raise LegacySeedError("invalid UUID")
    try:
        host = parsed.hostname or ""
    except ValueError as exc:
        raise LegacySeedError("invalid server host") from exc
    if not host:
        raise LegacySeedError("missing server host")
    if not validate_server_host(host):
        raise LegacySeedError("invalid server host")
    try:
        port_val = parsed.port
    except ValueError as exc:
        raise LegacySeedError("invalid port") from exc
    if port_val is None:
        raise LegacySeedError("missing port")
    try:
        port = int(port_val)
    except ValueError as exc:
        raise LegacySeedError("invalid port") from exc
    if not (1 <= port <= 65535):
        raise LegacySeedError("invalid port")
    qs = _parse_query_no_dup(parsed.query)
    encryption = (qs.get("encryption") or "none").lower()
    flow = qs.get("flow") or ""
    security = (qs.get("security") or "").lower()
    transport = (qs.get("type") or "tcp").lower()
    sni = qs.get("sni") or ""
    pbk = qs.get("pbk") or ""
    sid = qs.get("sid") or ""
    fp = (qs.get("fp") or "").lower()

    if encryption != "none":
        raise LegacySeedError("encryption must be none")
    if flow != "xtls-rprx-vision":
        raise LegacySeedError("incompatible flow")
    if security != "reality":
        raise LegacySeedError("security must be reality")
    if transport != "tcp":
        raise LegacySeedError("transport must be tcp")
    if not sni:
        raise LegacySeedError("missing sni")
    if not validate_sni_host(sni):
        raise LegacySeedError("invalid sni")
    if not pbk:
        raise LegacySeedError("missing pbk")
    if not sid:
        raise LegacySeedError("missing sid")
    if not REALITY_KEY_RE.match(pbk):
        raise LegacySeedError("invalid pbk")
    if not SHORT_ID_RE.match(sid):
        raise LegacySeedError("invalid short ID")
    if fp not in COMPAT_FP:
        raise LegacySeedError("incompatible Reality fingerprint")

    return {
        "uuid": uuid.lower(),
        "server": host,
        "port": port,
        "sni": sni,
        "public_key": pbk,
        "short_id": sid.lower(),
        "fingerprint": fp or "chrome",
    }


def load_legacy_seed(
    *,
    uri_file: Path,
    private_key_file: Path,
    user_tag: str,
    advertised_server: Optional[str],
    install_port: int = 443,
    require_advertised_server: bool = True,
) -> LegacySeedInput:
    """Validate files + URI + key match. Safe for controller / installer checks."""
    tag = validate_user_tag(user_tag)

    uri_path = validate_secret_file(Path(uri_file), label="legacy URI file")
    key_path = validate_secret_file(
        Path(private_key_file), label="legacy Reality private key file"
    )
    uri_line = _read_first_nonempty_line(uri_path)
    private_key = _read_single_key_line(key_path)
    fields = parse_legacy_vless_uri(uri_line)

    derived = derive_reality_public_key(private_key)
    if not constant_time_equal(derived, str(fields["public_key"])):
        raise LegacySeedError("Reality private key does not match URI pbk")

    uri_server = str(fields["server"])
    adv = (advertised_server or "").strip()
    if require_advertised_server and not adv:
        raise LegacySeedError("advertised server required for legacy seed")
    if adv and uri_server.lower() != adv.lower() and uri_server != adv:
        raise LegacySeedError("URI authority must match --server")
    if int(fields["port"]) != int(install_port):
        raise LegacySeedError("URI port must match install port")

    return LegacySeedInput(
        uri_path=uri_path,
        private_key_path=key_path,
        user_tag=tag,
        uuid=str(fields["uuid"]),
        server=uri_server,
        port=int(fields["port"]),
        sni=str(fields["sni"]),
        public_key=str(fields["public_key"]),
        short_id=str(fields["short_id"]),
        private_key=private_key,
        fingerprint=str(fields["fingerprint"]),
    )


def redact_seed_text(text: str) -> str:
    """Redact URI / UUID / Reality keys from operator text (journal/logs)."""
    if not text:
        return ""
    out = re.sub(r"vless://\S+", "vless://<redacted>", text, flags=re.I)
    out = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "<uuid>",
        out,
        flags=re.I,
    )
    out = re.sub(r"[A-Za-z0-9_-]{43,44}={0,2}", "<key>", out)
    return out


def _cli_validate_uri(uri: str) -> None:
    fields = parse_legacy_vless_uri(uri)
    # Machine-readable one-liner (test/debug only; installer must use validate-seed).
    sys.stdout.write(
        json.dumps(
            {
                "uuid": fields["uuid"],
                "server": fields["server"],
                "port": fields["port"],
                "sni": fields["sni"],
                "pbk": fields["public_key"],
                "sid": fields["short_id"],
                "fp": fields["fingerprint"],
            },
            separators=(",", ":"),
        )
        + "\n"
    )


def _cli_validate_tag(tag: str) -> None:
    validate_user_tag(tag)
    sys.stdout.write("ok\n")


def _cli_validate_seed(argv: list[str]) -> int:
    """Path-only installer entry. Stdout: KEY=value lines (no JSON blob)."""
    parser = argparse.ArgumentParser(prog="legacy_seed.py validate-seed", add_help=False)
    parser.add_argument("uri_file")
    parser.add_argument("key_file")
    parser.add_argument("tag")
    parser.add_argument("--server", default="")
    parser.add_argument("--port", type=int, default=443)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    try:
        seed = load_legacy_seed(
            uri_file=Path(args.uri_file),
            private_key_file=Path(args.key_file),
            user_tag=args.tag,
            advertised_server=(args.server or "").strip() or None,
            install_port=int(args.port),
            require_advertised_server=False,
        )
    except LegacySeedError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
    # KEY=value for bash while-read; values may contain secrets — pipe only, never argv.
    lines = [
        f"UUID={seed.uuid}",
        f"SERVER={seed.server}",
        f"PORT={seed.port}",
        f"SNI={seed.sni}",
        f"PBK={seed.public_key}",
        f"SID={seed.short_id}",
        f"FP={seed.fingerprint}",
        f"PRIVATE_KEY={seed.private_key}",
        f"PUBLIC_KEY={seed.public_key}",
        f"TAG={seed.user_tag}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    # CLI: validate-seed (installer) | derive-public | compare-pbk | validate-uri | validate-tag
    if len(sys.argv) >= 2 and sys.argv[1] == "validate-seed":
        raise SystemExit(_cli_validate_seed(sys.argv[2:]))
    if len(sys.argv) == 3 and sys.argv[1] == "derive-public":
        try:
            key = _read_single_key_line(Path(sys.argv[2]))
            sys.stdout.write(derive_reality_public_key(key) + "\n")
        except LegacySeedError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            raise SystemExit(1) from exc
        raise SystemExit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "compare-pbk":
        try:
            key = _read_single_key_line(Path(sys.argv[2]))
            pbk = sys.argv[3].strip()
            derived = derive_reality_public_key(key)
            raise SystemExit(0 if constant_time_equal(derived, pbk) else 1)
        except LegacySeedError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            raise SystemExit(1) from exc
    if len(sys.argv) == 3 and sys.argv[1] == "validate-uri":
        try:
            _cli_validate_uri(sys.argv[2])
        except LegacySeedError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            raise SystemExit(1) from exc
        raise SystemExit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "validate-tag":
        try:
            _cli_validate_tag(sys.argv[2])
        except LegacySeedError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            raise SystemExit(1) from exc
        raise SystemExit(0)
    sys.stderr.write(
        "usage: legacy_seed.py validate-seed URI_FILE KEY_FILE TAG "
        "[--server HOST] [--port N]\n"
        "       legacy_seed.py derive-public KEYFILE | compare-pbk KEYFILE PBK | "
        "validate-uri URI | validate-tag TAG\n"
    )
    raise SystemExit(2)
