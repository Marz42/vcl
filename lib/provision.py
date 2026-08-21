#!/usr/bin/env python3
"""vincula provision — Adopt/Provision controller logic (D33/D35/D49/D51).

Controller-carried, digest-verified first-party payload (D35/D51): single
architecture-neutral vincula-node-<ver>.tar.gz + .sha256 + payload-manifest.json.
Not air-gapped: remote may still need apt, HTTPS, sing-box release, public IP,
and Reality. Host-key policy unchanged (D34). Stdlib only. Python 3.10+.
"""
from __future__ import annotations

from typing import Any, Optional


def run_provision_preflight(*_a: Any, **_k: Any) -> dict[str, Any]:
    raise NotImplementedError("B2")
