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
    current = (current or "").strip()
    target = (target or "").strip()
    if current == target:
        return True  # already at target → SKIPPED path, not refuse
    return UPGRADE_ALLOWLIST.get(current) == target


def _ssh_json(
    node: dict[str, Any],
    remote_cmd: list[str],
    *,
    credential_class: Literal["observe", "admin"] = "observe",
    timeout: float = 20.0,
    require_exit_0: bool = False,
    unsupported_on_missing_command: bool = False,
    max_stdout_bytes: Optional[int] = None,
) -> tuple[str, Optional[dict[str, Any]], str]:
    host = _require_host()
    return host.observation_ssh_json(
        node,
        remote_cmd,
        credential_class=credential_class,
        timeout=timeout,
        require_exit_0=require_exit_0,
        unsupported_on_missing_command=unsupported_on_missing_command,
        max_stdout_bytes=max_stdout_bytes,
    )


def _fetch_identity(
    node: dict[str, Any],
    *,
    credential_class: Literal["observe", "admin"],
) -> tuple[str, Optional[dict[str, Any]], str]:
    return _ssh_json(
        node,
        ["vcl", "identity", "--json"],
        credential_class=credential_class,
    )


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


def run_upgrade_plan(
    node: dict[str, Any],
    *,
    credential_class: Literal["observe", "admin"] = "observe",
) -> dict[str, Any]:
    """Read-only upgrade plan (observe credential MAY be used; apply uses admin)."""
    target = upgrade_target_version()
    ssh_state, identity, detail = _fetch_identity(node, credential_class=credential_class)
    if ssh_state == "AUTH_FAILED":
        return {
            "ok": False,
            "state": "AUTH_FAILED",
            "target_version": target,
            "detail": detail,
            "credential_class": credential_class,
        }
    if ssh_state != "OK" or not isinstance(identity, dict):
        return {
            "ok": False,
            "state": "ERROR",
            "target_version": target,
            "detail": detail or "identity fetch failed",
            "credential_class": credential_class,
        }
    current = str(identity.get("vincula_version") or "").strip()
    checks = _plan_checks(node, identity, target)
    refused = any(c.get("status") == "fail" for c in checks)
    if current == target and not refused:
        return {
            "ok": True,
            "state": "SKIPPED",
            "node": node.get("name"),
            "node_id": node.get("node_id"),
            "instance_id": identity.get("instance_id"),
            "current_version": current,
            "target_version": target,
            "allowlist_ok": True,
            "checks": checks,
            "backup": "remote secretless vcl backup create",
            "rollback": "vincula.sh migrate EXIT trap + restore from backup",
            "outage_budget_seconds": OUTAGE_BUDGET_SECONDS,
            "credential_class": credential_class,
        }
    return {
        "ok": (not refused) and current != target,
        "state": "REFUSED" if refused else "PLANNED",
        "node": node.get("name"),
        "node_id": node.get("node_id"),
        "instance_id": identity.get("instance_id"),
        "current_version": current,
        "target_version": target,
        "allowlist_ok": is_upgrade_allowed(current, target),
        "checks": checks,
        "backup": "remote secretless vcl backup create + staged 0.5 helper upgrade checkpoint",
        "rollback": "vincula.sh migrate EXIT trap + vcl upgrade rollback <checkpoint>",
        "outage_budget_seconds": OUTAGE_BUDGET_SECONDS,
        "credential_class": credential_class,
        "identity": {
            "node_id": identity.get("node_id"),
            "instance_id": identity.get("instance_id"),
            "vincula_version": current,
        },
    }


def run_upgrade_apply(
    node: dict[str, Any],
    *,
    confirmed: bool,
    skip_backup: bool = False,
) -> dict[str, Any]:
    """Typed Node firmware upgrade (admin credential only for all steps)."""
    host = _require_host()
    prov = host.load_provision_module()
    if not confirmed:
        host.die("node upgrade apply requires --yes")

    # Spec §3.3 / §3.6: apply MUST use admin for plan/preflight/post-check.
    plan = run_upgrade_plan(node, credential_class="admin")
    if plan.get("state") == "AUTH_FAILED":
        host.die(f"upgrade plan failed: {plan.get('detail') or 'AUTH_FAILED'}")
    if plan.get("state") == "ERROR":
        host.die(f"upgrade plan failed: {plan.get('detail') or 'ERROR'}")
    if plan.get("state") == "SKIPPED":
        return {
            "ok": True,
            "state": "SKIPPED",
            "detail": "already at target version",
            "node": node.get("name"),
            "node_id": node.get("node_id"),
            "from_version": plan.get("current_version"),
            "to_version": plan.get("target_version"),
            "credential_class": "admin",
        }
    if plan.get("state") == "REFUSED" or not plan.get("allowlist_ok"):
        host.die(
            f"unsupported upgrade: {plan.get('current_version')} → "
            f"{plan.get('target_version')}"
        )

    pre = plan.get("identity") or {}
    pre_node_id = pre.get("node_id") or node.get("node_id")
    pre_instance_id = pre.get("instance_id")
    pre_version = plan.get("current_version")
    target = upgrade_target_version()

    identity_file = host.node_identity_file_for_class(node, "admin")
    extra: list[str] = []
    privilege_mode = prov._resolve_privilege_mode(
        ssh_host=node["ssh_host"],
        ssh_user=node["ssh_user"],
        ssh_port=int(node.get("ssh_port") or 22),
        identity_file=identity_file,
        extra=extra,
    )

    # Secretless archive on the *installed* helper (0.3.1+ has ``vcl backup``).
    # Do NOT call ``vcl upgrade checkpoint`` on the installed helper: 0.3.1/0.3.2
    # helpers have no ``upgrade`` subcommand, so apply would die before staging.
    backup_path: Optional[str] = None
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
        backup_path = _optional_backup_path(backup_doc)

    resolved = prov.resolve_node_payload()
    prov.verify_local_payload(resolved)
    remote_stage = prov._create_remote_stage(
        ssh_host=node["ssh_host"],
        ssh_user=node["ssh_user"],
        ssh_port=int(node.get("ssh_port") or 22),
        identity_file=identity_file,
        extra=extra,
    )
    checkpoint_path: Optional[str] = None
    migrate_committed = False
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

        # In-place checkpoint via the *staged* 0.5 helper (not the installed 0.3.x
        # vcl). Fresh-node restore is unused: it refuses VERSION and rotates URI.
        staged_helper = f"{paths['unpack']}/bin/vincula"
        ssh_state, ck_doc, ck_detail = _ssh_json(
            node,
            ["bash", staged_helper, "upgrade", "checkpoint", "--json"],
            credential_class="admin",
            timeout=host.SSH_BACKUP_TIMEOUT_SECONDS,
            require_exit_0=True,
        )
        if (
            ssh_state != "OK"
            or not isinstance(ck_doc, dict)
            or ck_doc.get("ok") is not True
        ):
            host.die(
                f"upgrade checkpoint failed: {ck_detail or 'remote checkpoint failed'}"
            )
        checkpoint_path = _optional_backup_path(ck_doc)
        if not checkpoint_path:
            host.die("upgrade checkpoint failed: missing path in JSON response")

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
            # migrate EXIT trap should have rolled back on node.
            host.die(f"remote migrate failed: {host._ssh_failure_detail(install_proc)}")
        migrate_committed = True
    finally:
        prov._cleanup_remote_stage(
            remote_stage,
            ssh_host=node["ssh_host"],
            ssh_user=node["ssh_user"],
            ssh_port=int(node.get("ssh_port") or 22),
            identity_file=identity_file,
            extra=extra,
        )

    if not checkpoint_path:
        host.die("upgrade checkpoint path missing after staging")

    def _finished_base() -> dict[str, Any]:
        return {
            "node": node.get("name"),
            "node_id": node.get("node_id"),
            "from_version": pre_version,
            "to_version": target,
            "credential_class": "admin",
            "migrate_committed": True,
            "checkpoint_path": checkpoint_path,
            "backup_path": backup_path,
            "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def _partial(detail: str, *, restore_detail: Optional[str] = None) -> dict[str, Any]:
        out = _finished_base()
        out.update(
            {
                "ok": False,
                "state": "PARTIAL",
                "detail": detail,
            }
        )
        if restore_detail:
            out["restore_detail"] = restore_detail
        out["recovery"] = (
            f"post-check failed after migrate; in-place upgrade rollback from "
            f"{checkpoint_path} did not succeed"
            + (f" ({restore_detail})" if restore_detail else "")
            + f"; operator: run `vcl upgrade rollback {checkpoint_path}` on the node"
            + (
                f" (secretless archive still at {backup_path})"
                if backup_path
                else ""
            )
        )
        return out

    def _rollback_or_partial(detail: str) -> dict[str, Any]:
        rolled = _attempt_post_upgrade_rollback(
            node,
            checkpoint_path=checkpoint_path,
            backup_path=backup_path,
            post_check_detail=detail,
            pre_version=pre_version,
            target=target,
        )
        if rolled is not None:
            return rolled
        return _partial(
            detail,
            restore_detail="upgrade rollback failed or refused (see node stderr)",
        )

    ssh_state, verify_doc, verify_detail = _ssh_json(
        node,
        ["vcl", "verify", "--json"],
        credential_class="admin",
        require_exit_0=False,
    )
    if ssh_state != "OK" or not isinstance(verify_doc, dict) or not verify_doc.get("ok"):
        fail_detail = f"post-upgrade verify failed: {verify_detail or 'verify failed'}"
        if migrate_committed:
            return _rollback_or_partial(fail_detail)
        host.die(fail_detail)

    # Post capabilities via admin (not observe) — Spec §3.3.
    caps_mod = host.load_observation_capabilities_module()
    max_cap = getattr(caps_mod, "CAPABILITIES_MAX_BYTES", 4096)

    ssh_state, cap_payload, cap_detail = _ssh_json(
        node,
        ["vcl", "capabilities", "--json"],
        credential_class="admin",
        unsupported_on_missing_command=True,
        max_stdout_bytes=max_cap,
    )
    if ssh_state != "OK" or not isinstance(cap_payload, dict):
        return _rollback_or_partial(
            f"post-upgrade capabilities failed: {cap_detail or ssh_state}"
        )
    cap_errors = caps_mod.validate_capabilities_v1(cap_payload)
    if cap_errors:
        return _rollback_or_partial(
            f"post-upgrade capabilities invalid: {'; '.join(cap_errors)}"
        )

    ssh_state, ident, ident_detail = _ssh_json(
        node,
        ["vcl", "identity", "--json"],
        credential_class="admin",
    )
    if ssh_state != "OK" or not isinstance(ident, dict):
        return _rollback_or_partial(
            f"post-upgrade identity failed: {ident_detail or ssh_state}"
        )
    current = str(ident.get("vincula_version") or "").strip()
    if current != target:
        return _rollback_or_partial(
            f"post-upgrade version mismatch: expected {target}, got {current}"
        )
    if ident.get("node_id") != pre_node_id:
        return _rollback_or_partial(
            "post-upgrade node_id changed (identity not preserved)"
        )
    if pre_instance_id and ident.get("instance_id") != pre_instance_id:
        return _rollback_or_partial(
            "post-upgrade instance_id changed (identity not preserved)"
        )

    out = _finished_base()
    out.update(
        {
            "ok": True,
            "state": "SUCCESS",
        }
    )
    return out


def _optional_backup_path(backup_doc: dict[str, Any]) -> Optional[str]:
    path = backup_doc.get("path")
    if isinstance(path, str) and path.strip():
        return path.strip()
    return None


def _attempt_post_upgrade_rollback(
    node: dict[str, Any],
    *,
    checkpoint_path: str,
    backup_path: Optional[str],
    post_check_detail: str,
    pre_version: Optional[str],
    target: str,
) -> Optional[dict[str, Any]]:
    """Try in-place ``vcl upgrade rollback`` after post-check failure (Spec §3.3).

    Unlike fresh-node ``vcl restore``, this preserves VERSION, instance_id, and
    URI credentials. Returns ROLLED_BACK on success, or None → PARTIAL.
    """
    host = _require_host()
    rollback_argv = [
        "vcl",
        "upgrade",
        "rollback",
        checkpoint_path,
        "--json",
    ]
    timeout = getattr(host, "SSH_MUTATION_TIMEOUT_SECONDS", 60)
    ssh_state, doc, restore_detail = _ssh_json(
        node,
        rollback_argv,
        credential_class="admin",
        timeout=timeout,
        require_exit_0=False,
    )
    if ssh_state != "OK" or not isinstance(doc, dict) or doc.get("ok") is not True:
        return None
    return {
        "ok": False,
        "state": "ROLLED_BACK",
        "detail": f"post-check failed; rolled back checkpoint: {post_check_detail}",
        "post_check_detail": post_check_detail,
        "checkpoint_path": checkpoint_path,
        "backup_path": backup_path,
        "rollback": doc,
        "node": node.get("name"),
        "node_id": node.get("node_id"),
        "from_version": pre_version,
        "to_version": target,
        "credential_class": "admin",
        "migrate_committed": True,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
