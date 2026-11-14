"""Extended Verify via observe only; explicit Controller probe is separate evidence."""
import importlib.util
import json
import subprocess
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location("vcl_verify_contract", Path(__file__).resolve().parents[1] / "verify_snapshot.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)
spec = importlib.util.spec_from_file_location("vcl_verify_monitor", Path(__file__).with_name("monitor.py"))
monitor_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor_module)
REMOTE_CMD = ["vcl", "verify", "--extended", "--json"]


def fetch(node, *, capabilities, ssh_json):
    if capabilities.get("state") != "OK":
        return {"state": capabilities.get("state") if capabilities.get("state") in ("AUTH_FAILED", "TIMEOUT", "UNSUPPORTED") else "ERROR", "snapshot": None}
    if "verify/v2" not in (capabilities.get("capabilities") or []):
        return {"state": "UNSUPPORTED", "snapshot": None}
    try:
        state, doc, _ = ssh_json(node=node, remote_cmd=REMOTE_CMD, credential_class="observe", max_stdout_bytes=8192, unsupported_on_missing_command=True)
        if state != "OK":
            return {"state": state if state in ("AUTH_FAILED", "TIMEOUT", "UNSUPPORTED") else "ERROR", "snapshot": None}
        if contract.validate(doc) or doc["node_id"] != node["node_id"] or doc["data_plane_source"] != "NONE":
            raise ValueError
        state, identity, _ = ssh_json(node=node, remote_cmd=["vcl", "identity", "--json"], credential_class="observe", max_stdout_bytes=4096, require_exit_0=True)
        if state != "OK":
            return {"state": state if state in ("AUTH_FAILED", "TIMEOUT") else "ERROR", "snapshot": None}
        if not isinstance(identity, dict) or any(identity.get(k) != doc[k] or doc[k] is None for k in ("node_id", "instance_id")):
            raise ValueError
        when = contract.datetime.fromisoformat(doc["observed_at"].replace("Z", "+00:00")).timestamp()
        if not -30 <= time.time() - when <= 90:
            raise ValueError
        return {"state": "OK", "snapshot": json.loads(json.dumps(doc, allow_nan=False))}
    except subprocess.TimeoutExpired:
        return {"state": "TIMEOUT", "snapshot": None}
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return {"state": "ERROR", "snapshot": None}


def run_cli(host, args):
    import sys
    module = monitor_module
    nodes = module.active_nodes(host, args.name)
    if not 1 <= len(nodes) <= 1024:
        raise ValueError("extended verify requires 1..1024 enabled nodes")
    probe = None
    if args.probe_profiles:
        probe_mod = module.store_module.sibling("probe")
        profiles_path = Path(args.probe_profiles).resolve()
        if host.workspace_manifest_path().is_file() and profiles_path.is_relative_to(host.fleet_home().resolve()):
            raise ValueError("probe profiles must be outside the portable Workspace")
        probe = probe_mod.ProxyProbe(probe_mod.read_profiles(profiles_path), sing_box=args.probe_sing_box)
    rows = []
    for node in nodes:
        deadline = time.monotonic() + args.timeout
        def ssh_json(**kw):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired("verify", args.timeout)
            return host.observation_ssh_json(node, kw["remote_cmd"], credential_class="observe", timeout=remaining,
                        max_stdout_bytes=kw.get("max_stdout_bytes"), require_exit_0=kw.get("require_exit_0", False),
                        unsupported_on_missing_command=kw.get("unsupported_on_missing_command", False))
        try:
            caps = host.fetch_node_capabilities(node, credential_class="observe", timeout=args.timeout)
            result = fetch(node, capabilities=caps, ssh_json=ssh_json)
            if result["state"] == "OK" and probe:
                outcome = None
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired("verify", args.timeout)
                    outcome = probe(node, timeout=remaining)
                except (Exception, SystemExit):
                    pass
                # Every attempted probe can span a replacement or revocation,
                # including an invalid outcome or a probe exception. Do not
                # publish the pre-probe checks without a current identity.
                doc = result["snapshot"]
                state, identity, _ = ssh_json(remote_cmd=["vcl", "identity", "--json"], require_exit_0=True)
                if state != "OK":
                    result = {"state": state if state in ("AUTH_FAILED", "TIMEOUT") else "ERROR", "snapshot": None}
                elif not isinstance(identity, dict) or any(identity.get(k) != doc[k] for k in ("node_id", "instance_id")):
                    result = {"state": "ERROR", "snapshot": None}
                else:
                    success = module.store_module.health.clean_probe(outcome)["success"]
                    if type(success) is bool:
                        doc["checks"]["data_plane"] = contract.check("PASS" if success else "FAIL", "OK" if success else "PROBE_FAILED", 1)
                        doc["data_plane_source"] = "EXPLICIT_CONTROLLER_PROBE"
                        doc["state"] = contract.overall(doc["checks"])
        except subprocess.TimeoutExpired:
            result = {"state": "TIMEOUT", "snapshot": None}
        except (Exception, SystemExit):
            result = {"state": "ERROR", "snapshot": None}
        rows.append({"name": node["name"], **result})
    doc = {"schema": "fleet-verify/v2", "nodes": rows}
    if args.as_json:
        print(json.dumps(doc, allow_nan=False))
    else:
        for row in rows:
            print(f"{row['name']}: {row['state']} {row['snapshot']['state'] if row['snapshot'] else ''}")
            if row["snapshot"]:
                for k, v in row["snapshot"]["checks"].items():
                    print(f"  {k}: {v['state']} {v['reason']}")
    return 2 if any(r["state"] != "OK" or r["snapshot"]["state"] != "PASS" for r in rows) else 0
