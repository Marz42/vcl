"""Pinned sing-box release asset naming (shared by provision preflight + vincula.sh).

Keep in sync with lib/sing-box-release.sh (tests assert parity).
"""
from __future__ import annotations

SING_BOX_VERSION = "1.13.18"
SING_BOX_RELEASE_BASE = (
    f"https://github.com/SagerNet/sing-box/releases/download/v{SING_BOX_VERSION}"
)


def release_asset_name(arch: str) -> str:
    return f"sing-box-{SING_BOX_VERSION}-linux-{arch}.tar.gz"


def release_asset_url(arch: str) -> str:
    return f"{SING_BOX_RELEASE_BASE}/{release_asset_name(arch)}"
