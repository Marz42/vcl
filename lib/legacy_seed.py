#!/usr/bin/env python3
"""Legacy single-user seed helpers (VCL 0.4.5).

Stdlib only. Validates local secret files, VLESS Reality URI constraints,
and derives Reality public keys (X25519) for constant-time pbk checks.
Never logs URI, UUID, or private key material — errors cite path + type only.
"""
from __future__ import annotations

import base64
import hmac
import os
import re
import stat
from pathlib import Path
from typing import NamedTuple, Optional
from urllib.parse import parse_qs, unquote, urlparse

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
SHORT_ID_RE = re.compile(r"^[0-9a-f]{1,16}$", re.IGNORECASE)
# sing-box Reality keys: URL-safe base64 of 32 bytes (43–44 chars, optional =).
REALITY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{43,44}={0,2}$")
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

# VCL-compatible Reality fingerprints (normalize to chrome on install).
COMPAT_FP = frozenset({"", "chrome", "chrome_auto", "randomized"})

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


def validate_secret_file(path: Path, *, label: str) -> Path:
    """Fail-closed local secret file checks (V0.4.5 §3.3).

    Regular file, owned by current user, not group/world readable,
    no symlink (fail-close), not dir/FIFO/socket.
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
        if st.st_uid != os.getuid():
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


def _qs_one(qs: dict[str, list[str]], key: str) -> str:
    vals = qs.get(key) or []
    return vals[0] if vals else ""


def parse_legacy_vless_uri(uri: str) -> dict[str, str | int]:
    """Parse and validate a VCL-fixed VLESS+Reality URI. Raises LegacySeedError."""
    raw = uri.strip()
    if "\n" in raw or "\r" in raw:
        raise LegacySeedError("URI must be a single line")
    if not raw.lower().startswith("vless://"):
        raise LegacySeedError("scheme must be vless")
    # urlparse handles userinfo@host:port
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "vless":
        raise LegacySeedError("scheme must be vless")
    uuid = unquote(parsed.username or "")
    if not UUID_RE.match(uuid):
        raise LegacySeedError("invalid UUID")
    host = parsed.hostname or ""
    if not host:
        raise LegacySeedError("missing server host")
    if parsed.port is None:
        raise LegacySeedError("missing port")
    port = int(parsed.port)
    if not (1 <= port <= 65535):
        raise LegacySeedError("invalid port")
    qs = parse_qs(parsed.query, keep_blank_values=True)
    encryption = _qs_one(qs, "encryption").lower()
    flow = _qs_one(qs, "flow")
    security = _qs_one(qs, "security").lower()
    transport = _qs_one(qs, "type").lower() or "tcp"
    sni = _qs_one(qs, "sni")
    pbk = _qs_one(qs, "pbk")
    sid = _qs_one(qs, "sid")
    fp = _qs_one(qs, "fp").lower()

    if encryption and encryption != "none":
        raise LegacySeedError("encryption must be none")
    if flow != "xtls-rprx-vision":
        raise LegacySeedError("incompatible flow")
    if security != "reality":
        raise LegacySeedError("security must be reality")
    if transport != "tcp":
        raise LegacySeedError("transport must be tcp")
    if not sni:
        raise LegacySeedError("missing sni")
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
) -> LegacySeedInput:
    """Validate files + URI + key match. Safe for controller pre-upload checks."""
    tag = (user_tag or "").strip()
    if not TAG_RE.match(tag):
        raise LegacySeedError("invalid legacy user tag")
    if tag == "owner":
        raise LegacySeedError("legacy user tag must not be owner")

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

    adv = (advertised_server or "").strip()
    if not adv:
        raise LegacySeedError("advertised server required for legacy seed")
    # Compare authority host (case-insensitive for DNS names)
    uri_server = str(fields["server"])
    if uri_server.lower() != adv.lower() and uri_server != adv:
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


if __name__ == "__main__":
    # CLI for installer: derive-public <private-key-file>
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "derive-public":
        key = _read_single_key_line(Path(sys.argv[2]))
        sys.stdout.write(derive_reality_public_key(key) + "\n")
        raise SystemExit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "compare-pbk":
        key = _read_single_key_line(Path(sys.argv[2]))
        pbk = sys.argv[3].strip()
        derived = derive_reality_public_key(key)
        raise SystemExit(0 if constant_time_equal(derived, pbk) else 1)
    sys.stderr.write(
        "usage: legacy_seed.py derive-public KEYFILE | compare-pbk KEYFILE PBK\n"
    )
    raise SystemExit(2)
