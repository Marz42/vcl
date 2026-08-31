#!/usr/bin/env python3
"""Controller-orchestrated Node firmware upgrade (0.5.0)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

_host: Any = None

UPGRADE_ALLOWLIST: dict[str, str] = {
    "0.3.1": "0.5.0",
    "0.3.2": "0.5.0",
}
OUTAGE_BUDGET_SECONDS = 3


def bind(host: Any) -> None:
    global _host
    _host = host


def _require_host() -> Any:
    if _host is None:
        raise RuntimeError("node_upgrade.bind(host) required before use")
    return _host


def upgrade_target_version() -> str:
    prov = _require_host().load_provision_module()
    return prov.NODE_PAYLOAD_VERSION


def is_upgrade_allowed(current: str, target: Optional[str] = None) -> bool:
    target = target or upgrade_target_version()
    return UPGRADE_ALLOWLIST.get((current or "").strip()) == target


def _ssh_json(
    node: dict[str, Any],
    remote_cmd: list[str],
    *,
    credential_class: Literal["observe", "admin"] = "observe",
    timeout: float = 20.0,
    require_exit_0: bool = False,
) -> tuple[str, Optional[dict[str, Any]], str]:
    host = _require_host()
    return host.observation_ssh_json(
        node,
        remote_cmd,
        credential_class=credential_class,
        timeout=timeout,
        require_exit_0=require_exit_0,
    )


def _fetch_identity(node: dict[str, Any]) -> tuple[str, Optional[dict[str, Any]], str]:
    return _ssh_json(node, ["vcl", "identity", "--json"], credential_class="observe")


def _plan_checks(
    node: dict[str, Any],
    identity: dict[str, Any],
    target: str,
) -> list[dict[str, Any]]:
    current = str(identity.get("vincula_version") or "").strip()
    checks: list[dict[str, Any]] = []
    if current == target:
        checks.append(
            {
                "id": "version",
                "status": "skip",
                "detail": f"already at {target}",
            }
        )
    elif is_upgrade_allowed(current, target):
        checks.append(
            {
                "id": "allowlist",
                "status": "pass",
                "detail": f"{current} → {target}",
            }
        )
    else:
        checks.append(
            {
                "id": "allowlist",
                "status": "fail",
                "detail": f"unsupported upgrade path {current!r} → {target!r}",
            }
        )
    remote_id = identity.get("node_id")
    if remote_id != node.get("node_id"):
        checks.append(
            {
                "id": "node_id",
                "status": "fail",
                "detail": "remote node_id does not match registry",
            }
        )
    else:
        checks.append({"id": "node_id", "status": "pass", "detail": "match"})
    checks.append(
        {
            "id": "backup",
            "status": "pass",
            "detail": "remote vcl backup create (secretless default)",
        }
    )
    checks.append(
        {
            "id": "outage_budget",
            "status": "pass",
            "detail": f"target ≤{OUTAGE_BUDGET_SECONDS}s (Live L2)",
        }
    )
    return checks


def run_upgrade_plan(node: dict[str, Any]) -> dict[str, Any]:
    """Read-only upgrade plan (observe credential MAY be used)."""
    target = upgrade_target_version()
    ssh_state, identity, detail = _fetch_identity(node)
    if ssh_state == "AUTH_FAILED":
        return {
            "ok": False,
            "state": "AUTH_FAILED",
            "target_version": target,
            "detail": detail,
            "credential_class": "observe",
        }
    if ssh_state != "OK" or not isinstance(identity, dict):
        return {
            "ok": False,
            "state": "ERROR",
            "target_version": target,
            "detail": detail or "identity fetch failed",
            "credential_class": "observe",
        }
    current = str(identity.get("vincula_version") or "").strip()
    checks = _plan_checks(node, identity, target)
    allowed = all(c.get("status") != "fail" for c in checks)
    return {
        "ok": allowed and current != target,
        "state": "PLANNED" if allowed else "REFUSED",
        "node": node.get("name"),
        "node_id": node.get("node_id"),
        "current_version": current,
        "target_version": target,
        "allowlist_ok": is_upgrade_allowed(current, target),
        "checks": checks,
        "backup": "remote secretless vcl backup create",
        "rollback": "vincula.sh migrate EXIT trap + restore from backup",
        "outage_budget_seconds": OUTAGE_BUDGET_SECONDS,
        "credential_class": "observe",
    }


def run_upgrade_apply(
    node: dict[str, Any],
    *,
    confirmed: bool,
    skip_backup: bool = False,
) -> dict[str, Any]:
    """Typed Node firmware upgrade (admin credential only)."""
    host = _require_host()
    prov = host.load_provision_module()
    if not confirmed:
        host.die("node upgrade apply requires --yes")

    plan = run_upgrade_plan(node)
    if plan.get("state") == "AUTH_FAILED":
        host.die(f"upgrade plan failed: {plan.get('detail') or 'AUTH_FAILED'}")
    if not plan.get("allowlist_ok"):
        host.die(
            f"unsupported upgrade: {plan.get('current_version')} → "
            f"{plan.get('target_version')}"
        )
    if str(plan.get("current_version") or "") == plan.get("target_version"):
        return {
            "ok": True,
            "state": "SKIPPED",
            "detail": "already at target version",
            "credential_class": "admin",
        }

    identity_file = host.node_identity_file_for_class(node, "admin")
    extra: list[str] = []
    privilege_mode = prov._resolve_privilege_mode(
        ssh_host=node["ssh_host"],
        ssh_user=node["ssh_user"],
        ssh_port=int(node.get("ssh_port") or 22),
        identity_file=identity_file,
        extra=extra,
    )

    if not skip_backup:
        ssh_state, backup_doc, backup_detail = _ssh_json(
            node,
            ["vcl", "backup", "create", "--json"],
            credential_class="admin",
            timeout=host.SSH_BACKUP_TIMEOUT_SECONDS,
            require_exit_0=True,
        )
        if (
            ssh_state != "OK"
            or not isinstance(backup_doc, dict)
            or backup_doc.get("ok") is not True
        ):
            host.die(
                f"upgrade backup failed: {backup_detail or 'remote backup failed'}"
            )

    resolved = prov.resolve_node_payload()
    prov.verify_local_payload(resolved)
    remote_stage = prov._create_remote_stage(
        ssh_host=node["ssh_host"],
        ssh_user=node["ssh_user"],
        ssh_port=int(node.get("ssh_port") or 22),
        identity_file=identity_file,
        extra=extra,
    )
    try:
        prov.upload_and_verify_remote_payload(
            resolved,
            ssh_host=node["ssh_host"],
            ssh_user=node["ssh_user"],
            ssh_port=int(node.get("ssh_port") or 22),
            identity_file=identity_file,
            extra=extra,
            remote_stage=remote_stage,
        )
        paths = prov._remote_stage_paths(remote_stage)
        tar_proc = host.ssh_run(
            node["ssh_host"],
            node["ssh_user"],
            int(node.get("ssh_port") or 22),
            ["tar", "-xzf", paths["tar"], "-C", remote_stage],
            batch=True,
            extra=extra,
            identity_file=identity_file,
        )
        if tar_proc.returncode != 0:
            host.die(f"remote tar unpack failed: {host._ssh_failure_detail(tar_proc)}")
        install_argv = prov.installer_remote_argv(
            f"{paths['unpack']}/vincula.sh",
            privilege_mode=privilege_mode,
            vcl_server=None,
        )
        install_proc = host.ssh_run(
            node["ssh_host"],
            node["ssh_user"],
            int(node.get("ssh_port") or 22),
            install_argv,
            batch=True,
            extra=extra,
            identity_file=identity_file,
            timeout=host.SSH_MUTATION_TIMEOUT_SECONDS,
        )
        if install_proc.returncode != 0:
            host.die(f"remote migrate failed: {host._ssh_failure_detail(install_proc)}")
    finally:
        prov._cleanup_remote_stage(
            remote_stage,
            ssh_host=node["ssh_host"],
            ssh_user=node["ssh_user"],
            ssh_port=int(node.get("ssh_port") or 22),
            identity_file=identity_file,
            extra=extra,
        )

    ssh_state, verify_doc, verify_detail = _ssh_json(
        node,
        ["vcl", "verify", "--json"],
        credential_class="admin",
        require_exit_0=False,
    )
    if ssh_state != "OK" or not isinstance(verify_doc, dict) or not verify_doc.get("ok"):
        host.die(f"post-upgrade verify failed: {verify_detail or 'verify failed'}")

    caps = host.fetch_node_capabilities(node)
    if caps.get("state") != "OK":
        host.die(
            f"post-upgrade capabilities failed: {caps.get('detail') or caps.get('state')}"
        )

    ssh_state, ident, _ = _ssh_json(
        node,
        ["vcl", "identity", "--json"],
        credential_class="admin",
    )
    current = str((ident or {}).get("vincula_version") or "")
    target = upgrade_target_version()
    if current != target:
        host.die(f"post-upgrade version mismatch: expected {target}, got {current}")

    return {
        "ok": True,
        "state": "SUCCESS",
        "node": node.get("name"),
        "node_id": node.get("node_id"),
        "from_version": plan.get("current_version"),
        "to_version": target,
        "credential_class": "admin",
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
