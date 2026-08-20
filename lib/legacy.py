"""Legacy compatibility facade (0.4.0 B4).

Canonical env remains VCL_FLEET_HOME (fleet_home). Optional alias:
if VCL_FLEET_WORKSPACE is set and VCL_FLEET_HOME is unset, treat the workspace
path as VCL_FLEET_HOME (read-only env alias; no new disk layout).
CLI ``--workspace PATH`` (0.4.1) sets VCL_FLEET_HOME and prefers over this alias.

Loaded as a controller sibling via _load_controller_sibling — never import
this module from sys.path.

UI-required fleet surface (LEGACY_FLEET_ATTRS): VCL_FLEET_VERSION, fleet_home,
fleet_registry_path, load_registry, save_registry, open_fleet_db, validate_name,
find_by_name, load_audit_module, ssh_run, prepare_ssh_host_key.
"""

from __future__ import annotations

import os
from typing import Any

LEGACY_FLEET_ATTRS = (
    "VCL_FLEET_VERSION",
    "fleet_home",
    "fleet_registry_path",
    "load_registry",
    "save_registry",
    "open_fleet_db",
    "validate_name",
    "find_by_name",
    "load_audit_module",
    "ssh_run",
    "prepare_ssh_host_key",
)


def apply_env_aliases() -> None:
    """Map VCL_FLEET_WORKSPACE → VCL_FLEET_HOME when HOME is unset (read-only)."""
    ws = os.environ.get("VCL_FLEET_WORKSPACE")
    home = os.environ.get("VCL_FLEET_HOME")
    if ws and not home:
        os.environ["VCL_FLEET_HOME"] = ws


def attach(fleet_mod: Any) -> dict[str, Any]:
    """Apply env aliases and return the UI-facing fleet attribute map."""
    apply_env_aliases()
    return {n: getattr(fleet_mod, n) for n in LEGACY_FLEET_ATTRS}
