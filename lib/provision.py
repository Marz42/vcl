#!/usr/bin/env python3
"""vincula provision — Adopt/Provision controller logic (D33/D35/D49/D51).

Controller-carried, digest-verified first-party payload (D35/D51): single
architecture-neutral vincula-node-<ver>.tar.gz + .sha256 + payload-manifest.json.
Not air-gapped: remote may still need apt, HTTPS, sing-box release, public IP,
and Reality. Host-key policy unchanged (D34). Stdlib only. Python 3.10+.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
from pathlib import Path
from typing import Any, Optional

_host: Any = None

# D51: single arch-neutral node payload pinned for 0.4.x provision.
NODE_PAYLOAD_VERSION = "0.3.1"
NODE_TARBALL_NAME = f"vincula-node-{NODE_PAYLOAD_VERSION}.tar.gz"
NODE_SHA256_NAME = NODE_TARBALL_NAME + ".sha256"
MANIFEST_NAME = "payload-manifest.json"
IO_CHUNK = 1024 * 1024
# Remote staging dir used by verify_remote_payload_digest (B4 uploads here).
REMOTE_STAGE = "/tmp/vincula-provision"

DEFAULT_SUPPORTED_OS = (
    "debian12",
    "debian13",
    "ubuntu22.04",
    "ubuntu24.04",
    "ubuntu26.04",
)

REQUIRED_CMDS = (
    "uname",
    "id",
    "groups",
    "sudo",
    "curl",
    "tar",
    "sha256sum",
    "python3",
    "apt-get",
    "systemctl",
    "ss",
    "df",
)

DEFAULT_SUPPORTED_ARCH = ("amd64", "arm64")
DISK_MIN_AVAIL_KB = 512000
SING_BOX_VERSION = "1.13.18"
SINGBOX_RELEASE_PROBE = (
    f"https://github.com/SagerNet/sing-box/releases/download/v{SING_BOX_VERSION}/"
)

ARCH_MAP = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

REMOTE_CHECK_IDS = (
    "ssh_connect",
    *(f"cmd_{b}" for b in REQUIRED_CMDS),
    "os",
    "arch",
    "root_or_sudo",
    "disk",
    "already_vincula",
    "port_443",
    "sing_box_unit",
    "https_out",
    "singbox_release",
    "public_ip",
    "reality",
)


def bind(host: Any) -> None:
    """Bind fleet host for ssh_run / prepare_ssh_host_key / die."""
    global _host
    _host = host


def sha256_file(path: Path) -> str:
    """Streaming SHA-256 hex digest (stdlib only; not backup module)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(IO_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_host() -> Any:
    if _host is None:
        raise RuntimeError("provision.bind(host) required")
    return _host


def _payload_paths(root: Path) -> dict[str, Path]:
    return {
        "tarball": root / NODE_TARBALL_NAME,
        "sha256_sidecar": root / NODE_SHA256_NAME,
        "manifest_path": root / MANIFEST_NAME,
        "root": root,
    }


def _die_missing_payload(paths: dict[str, Path]) -> None:
    missing = [
        str(paths[k])
        for k in ("tarball", "sha256_sidecar", "manifest_path")
        if not paths[k].is_file()
    ]
    host = _require_host()
    host.die("node payload not found: " + ", ".join(missing))


def resolve_node_payload() -> dict[str, Path]:
    """Locate node tarball + sidecar + manifest (D51).

    Order: ``VCL_NODE_ARCHIVE`` → shipped ``payload/`` beside controller root →
    repo ``dist/``. Dies if any of the three files is missing.
    """
    host = _require_host()
    archive_env = os.environ.get("VCL_NODE_ARCHIVE", "").strip()
    if archive_env:
        tarball = Path(archive_env).expanduser().resolve()
        sidecar = Path(str(tarball) + ".sha256")
        man_env = os.environ.get("VCL_PAYLOAD_MANIFEST", "").strip()
        if man_env:
            manifest_path = Path(man_env).expanduser().resolve()
        else:
            manifest_path = tarball.parent / MANIFEST_NAME
        paths = {
            "tarball": tarball,
            "sha256_sidecar": sidecar,
            "manifest_path": manifest_path,
            "root": tarball.parent,
        }
        if not all(
            paths[k].is_file()
            for k in ("tarball", "sha256_sidecar", "manifest_path")
        ):
            _die_missing_payload(paths)
        return paths

    controller_root = Path(__file__).resolve().parent.parent
    shipped = controller_root / "payload" / NODE_TARBALL_NAME
    if shipped.is_file():
        paths = _payload_paths(controller_root / "payload")
        if not all(
            paths[k].is_file()
            for k in ("tarball", "sha256_sidecar", "manifest_path")
        ):
            _die_missing_payload(paths)
        return paths

    for parent in Path(__file__).resolve().parents:
        dist_tar = parent / "dist" / NODE_TARBALL_NAME
        if dist_tar.is_file():
            paths = _payload_paths(parent / "dist")
            # Manifest is not produced by build-release.sh; require it or die.
            if not all(
                paths[k].is_file()
                for k in ("tarball", "sha256_sidecar", "manifest_path")
            ):
                _die_missing_payload(paths)
            return paths

    host.die(f"node payload not found: {NODE_TARBALL_NAME}")


def load_payload_manifest(path: Path) -> dict[str, Any]:
    """Load and return payload-manifest.json (D51 fields)."""
    host = _require_host()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        host.die(f"invalid payload manifest {path}: {exc}")
    if not isinstance(data, dict):
        host.die(f"invalid payload manifest {path}: not an object")
    return data


def _read_sidecar_hex(sidecar: Path) -> str:
    text = Path(sidecar).read_text(encoding="utf-8").strip()
    if not text:
        return ""
    return text.split()[0].strip().lower()


def verify_local_payload(resolved: dict[str, Path]) -> dict[str, Any]:
    """Fail-closed local digest + pinned version check (AC-4.2-04 / AC-4.3-P01).

    Requires file digest, sidecar hex, and ``manifest.sha256`` to match.
    Returns the loaded manifest on success.
    """
    host = _require_host()
    tarball = Path(resolved["tarball"])
    sidecar = Path(resolved["sha256_sidecar"])
    manifest_path = Path(resolved["manifest_path"])

    actual = sha256_file(tarball).lower()
    sidecar_hex = _read_sidecar_hex(sidecar)
    manifest = load_payload_manifest(manifest_path)
    man_hex = str(manifest.get("sha256") or "").strip().lower()

    if not actual or actual != sidecar_hex or actual != man_hex:
        host.die("payload digest mismatch (local); refusing install")

    npv = str(manifest.get("node_payload_version") or "")
    if npv != NODE_PAYLOAD_VERSION:
        host.die(
            f"node_payload_version {npv!r} != pinned {NODE_PAYLOAD_VERSION!r}; "
            "refusing install"
        )
    return manifest


def normalize_os_id(os_id: str) -> str:
    """Map ``debian:12`` / ``ubuntu:24.04`` / ``debian12`` → manifest form."""
    s = (os_id or "").strip().lower()
    if ":" in s:
        distro, ver = s.split(":", 1)
        return f"{distro}{ver}"
    return s


def validate_manifest_for_target(
    manifest: dict[str, Any],
    *,
    os_id: str,
    arch: str,
) -> None:
    """Fail-closed OS/arch gate against D51 manifest lists."""
    host = _require_host()
    raw_os = manifest.get("supported_os")
    raw_arch = manifest.get("supported_arch")
    supported_os = [str(x) for x in raw_os] if isinstance(raw_os, (list, tuple)) else []
    supported_arch = (
        [str(x) for x in raw_arch] if isinstance(raw_arch, (list, tuple)) else []
    )
    norm_os = normalize_os_id(os_id)
    if arch not in supported_arch:
        host.die(
            f"arch {arch!r} not in supported_arch={supported_arch}; refusing install"
        )
    if norm_os not in supported_os:
        host.die(
            f"os {norm_os!r} not in supported_os={supported_os}; refusing install"
        )


def verify_remote_payload_digest(
    *,
    ssh_host: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    identity_file: Optional[str] = None,
    extra: Optional[list[str]] = None,
    remote_stage: str = REMOTE_STAGE,
) -> None:
    """Fail-closed remote sha256sum -c before unpack (AC-4.2-04).

    Assumes tarball + ``.sha256`` already staged under ``remote_stage``.
    Does not SCP, unpack, or run the installer — B4 calls this after upload.
    """
    host = _require_host()
    stage = shlex.quote(remote_stage)
    sum_name = shlex.quote(NODE_SHA256_NAME)
    proc = host.ssh_run(
        ssh_host,
        ssh_user,
        ssh_port,
        ["sh", "-c", f"cd {stage} && sha256sum -c {sum_name}"],
        batch=True,
        extra=extra,
        identity_file=identity_file,
    )
    if proc.returncode != 0:
        host.die("payload digest mismatch (remote); refusing install")


def _check(
    check_id: str,
    status: str,
    detail: str,
    *,
    remedy: Optional[str] = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": check_id, "status": status, "detail": detail}
    if remedy is not None:
        row["remedy"] = remedy
    return row


def _skipped(check_id: str, detail: str = "skipped") -> dict[str, Any]:
    return _check(check_id, "skip", detail)


def _ssh(
    ssh_host: str,
    ssh_user: str,
    ssh_port: int,
    remote_cmd: list[str],
    *,
    identity_file: Optional[str],
    extra: Optional[list[str]],
) -> Any:
    return _host.ssh_run(
        ssh_host,
        ssh_user,
        ssh_port,
        remote_cmd,
        batch=True,
        extra=extra,
        identity_file=identity_file,
    )


def _normalize_arch(uname_m: str) -> Optional[str]:
    return ARCH_MAP.get(uname_m.strip())


def _parse_df_avail_kb(stdout: str) -> Optional[int]:
    lines = [ln for ln in (stdout or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    parts = lines[1].split()
    if len(parts) < 4:
        return None
    try:
        return int(parts[3])
    except ValueError:
        return None


def run_provision_preflight(
    *,
    ssh_host: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    identity_file: Optional[str] = None,
    host_key: Optional[str] = None,
    manifest: Optional[dict[str, Any]] = None,
    reality_host: Optional[str] = None,
    vcl_server: Optional[str] = None,
    skip: Optional[set[str]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run D35 provision preflight over the existing SSH/trust layer (D34).

    Returns ``{"ok": bool, "checks": [{"id","status","detail","remedy"?}, ...]}``.
    Does not install payload (B3+) or write registry. Non-interactive without
    ``host_key`` dies via trust.NONINTERACTIVE_HOST_KEY_MSG.
    """
    if _host is None:
        raise RuntimeError("provision.bind(host) required before run_provision_preflight")

    skip_set = set(skip or ())
    if vcl_server is None:
        vcl_server = os.environ.get("VCL_SERVER")
    vcl_server_set = bool((vcl_server or "").strip())

    supported_arch: list[str] = list(DEFAULT_SUPPORTED_ARCH)
    if manifest is not None:
        raw = manifest.get("supported_arch")
        if isinstance(raw, (list, tuple)) and raw:
            supported_arch = [str(x) for x in raw]

    extra, _batch = _host.prepare_ssh_host_key(ssh_host, ssh_port, host_key)

    checks: list[dict[str, Any]] = []

    def add(row: dict[str, Any]) -> None:
        checks.append(row)

    def want(check_id: str) -> bool:
        return check_id not in skip_set

    if dry_run:
        for cid in REMOTE_CHECK_IDS:
            if cid in skip_set:
                add(_skipped(cid))
            else:
                add(_skipped(cid, "dry_run"))
        return {"ok": True, "checks": checks}

    # --- B2-T1: SSH connect ---
    if want("ssh_connect"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["true"],
            identity_file=identity_file,
            extra=extra,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            add(_check("ssh_connect", "fail", detail))
            return {"ok": False, "checks": checks}
        add(_check("ssh_connect", "pass", "ok"))
    else:
        add(_skipped("ssh_connect"))

    # --- B2-T2: required commands ---
    for bin_name in REQUIRED_CMDS:
        cid = f"cmd_{bin_name}"
        if not want(cid):
            add(_skipped(cid))
            continue
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["command", "-v", bin_name],
            identity_file=identity_file,
            extra=extra,
        )
        if proc.returncode != 0:
            add(_check(cid, "fail", f"{bin_name} not found"))
        else:
            path = (proc.stdout or "").strip() or bin_name
            add(_check(cid, "pass", path))

    # --- B2-T3: OS / arch / sudo / disk ---
    if want("os"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["uname", "-s"],
            identity_file=identity_file,
            extra=extra,
        )
        os_name = (proc.stdout or "").strip()
        if proc.returncode != 0 or os_name != "Linux":
            add(_check("os", "fail", os_name or f"exit {proc.returncode}"))
        else:
            add(_check("os", "pass", os_name))
    else:
        add(_skipped("os"))

    if want("arch"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["uname", "-m"],
            identity_file=identity_file,
            extra=extra,
        )
        uname_m = (proc.stdout or "").strip()
        mapped = _normalize_arch(uname_m) if proc.returncode == 0 else None
        if mapped is None or mapped not in supported_arch:
            add(
                _check(
                    "arch",
                    "fail",
                    f"{uname_m or 'unknown'} (supported: {','.join(supported_arch)})",
                )
            )
        else:
            add(_check("arch", "pass", mapped))
    else:
        add(_skipped("arch"))

    if want("root_or_sudo"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["id", "-u"],
            identity_file=identity_file,
            extra=extra,
        )
        uid = (proc.stdout or "").strip()
        if proc.returncode == 0 and uid == "0":
            add(_check("root_or_sudo", "pass", "uid=0"))
        else:
            sudo_proc = _ssh(
                ssh_host,
                ssh_user,
                ssh_port,
                ["sudo", "-n", "true"],
                identity_file=identity_file,
                extra=extra,
            )
            if sudo_proc.returncode == 0:
                add(_check("root_or_sudo", "pass", f"uid={uid or '?'} sudo -n ok"))
            else:
                add(
                    _check(
                        "root_or_sudo",
                        "fail",
                        f"uid={uid or '?'} and sudo -n failed",
                    )
                )
    else:
        add(_skipped("root_or_sudo"))

    if want("disk"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["df", "-Pk", "/"],
            identity_file=identity_file,
            extra=extra,
        )
        avail = _parse_df_avail_kb(proc.stdout or "") if proc.returncode == 0 else None
        if avail is None:
            add(_check("disk", "fail", "could not parse df -Pk /"))
        elif avail < DISK_MIN_AVAIL_KB:
            add(_check("disk", "fail", f"avail_kb={avail} < {DISK_MIN_AVAIL_KB}"))
        else:
            add(_check("disk", "pass", f"avail_kb={avail}"))
    else:
        add(_skipped("disk"))

    # --- B2-T4: conflicts ---
    if want("already_vincula"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["test", "-f", "/etc/vincula/VERSION"],
            identity_file=identity_file,
            extra=extra,
        )
        if proc.returncode == 0:
            add(
                _check(
                    "already_vincula",
                    "fail",
                    "/etc/vincula/VERSION present",
                    remedy="use node adopt",
                )
            )
        else:
            add(_check("already_vincula", "pass", "no VERSION"))
    else:
        add(_skipped("already_vincula"))

    if want("port_443"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["ss", "-lntH", "sport = :443"],
            identity_file=identity_file,
            extra=extra,
        )
        out = (proc.stdout or "").strip()
        if out:
            add(_check("port_443", "fail", "port 443 in use"))
        else:
            add(_check("port_443", "pass", "port 443 free"))
    else:
        add(_skipped("port_443"))

    if want("sing_box_unit"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            ["systemctl", "cat", "sing-box.service"],
            identity_file=identity_file,
            extra=extra,
        )
        if proc.returncode == 0:
            add(_check("sing_box_unit", "fail", "sing-box.service present"))
        else:
            add(_check("sing_box_unit", "pass", "no sing-box.service"))
    else:
        add(_skipped("sing_box_unit"))

    # --- B2-T5: outbound / public IP / Reality ---
    if want("https_out"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            [
                "curl",
                "-fsS",
                "--max-time",
                "10",
                "-o",
                "/dev/null",
                "https://github.com/",
            ],
            identity_file=identity_file,
            extra=extra,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip() or f"exit {proc.returncode}"
            add(_check("https_out", "fail", detail))
        else:
            add(_check("https_out", "pass", "https://github.com/ ok"))
    else:
        add(_skipped("https_out"))

    if want("singbox_release"):
        proc = _ssh(
            ssh_host,
            ssh_user,
            ssh_port,
            [
                "curl",
                "-fsS",
                "--max-time",
                "15",
                "-o",
                "/dev/null",
                "-I",
                SINGBOX_RELEASE_PROBE,
            ],
            identity_file=identity_file,
            extra=extra,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip() or f"exit {proc.returncode}"
            add(_check("singbox_release", "fail", detail))
        else:
            add(_check("singbox_release", "pass", f"v{SING_BOX_VERSION} reachable"))
    else:
        add(_skipped("singbox_release"))

    if want("public_ip"):
        if vcl_server_set:
            add(_skipped("public_ip", "VCL_SERVER set"))
        else:
            proc = _ssh(
                ssh_host,
                ssh_user,
                ssh_port,
                ["curl", "-fsS", "--max-time", "10", "https://api.ipify.org"],
                identity_file=identity_file,
                extra=extra,
            )
            ip_text = (proc.stdout or "").strip()
            if proc.returncode != 0 or not ip_text:
                detail = (proc.stderr or "").strip() or f"exit {proc.returncode}"
                add(_check("public_ip", "fail", detail))
            else:
                add(_check("public_ip", "pass", ip_text))
    else:
        add(_skipped("public_ip"))

    if want("reality"):
        rh = (reality_host or "").strip()
        if not rh:
            add(_skipped("reality", "reality_host not configured"))
        else:
            proc = _ssh(
                ssh_host,
                ssh_user,
                ssh_port,
                [
                    "curl",
                    "-fsS",
                    "--max-time",
                    "10",
                    "-o",
                    "/dev/null",
                    f"https://{rh}/",
                ],
                identity_file=identity_file,
                extra=extra,
            )
            if proc.returncode != 0:
                detail = (proc.stderr or "").strip() or f"exit {proc.returncode}"
                add(_check("reality", "fail", detail))
            else:
                add(_check("reality", "pass", f"https://{rh}/ ok"))
    else:
        add(_skipped("reality"))

    ok = not any(c.get("status") == "fail" for c in checks)
    return {"ok": ok, "checks": checks}
