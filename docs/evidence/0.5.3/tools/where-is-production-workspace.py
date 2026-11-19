#!/usr/bin/env python3
"""Read-only: show which workspace the Controller would use, and where its state lives.

Run this ON THE MACHINE AND AS THE USER that runs the Controller, with the same
environment (shell profile, service user, or explicit VCL_FLEET_* overrides).

  python3 tmp/where-is-production-workspace.py
  PROD_WS=... # -> copy the printed export lines into the phase A batch script

It only reads: environment variables, JSON files and directory listings. It never
opens the SQLite cache (so it never creates, migrates or locks it) and never
prints key material or key file contents.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "lib"))

try:  # product's own resolution rules; fail loudly rather than guess
    import legacy  # type: ignore
    import workspace as ws  # type: ignore

    legacy.apply_env_aliases()
except Exception as exc:  # pragma: no cover
    print(f"cannot load lib/workspace.py: {exc}", file=sys.stderr)
    raise SystemExit(2)


def env_rows() -> list[tuple[str, str, str]]:
    names = (
        "VCL_FLEET_WORKSPACE",
        "VCL_FLEET_HOME",
        "VCL_FLEET_LOCAL_STATE",
        "XDG_CONFIG_HOME",
        "XDG_STATE_HOME",
        "TMPDIR",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "HOME",
    )
    rows = []
    for n in names:
        v = os.environ.get(n)
        rows.append((n, v if v else "-", "set" if v else "unset"))
    return rows


def read_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"__error__": str(exc)}


def dbsize(path: Path) -> str:
    if not path.is_file():
        return "missing"
    st = path.stat()
    import datetime

    return f"{st.st_size} bytes, mtime {datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc).isoformat(timespec='seconds')}"


def main() -> int:
    home = ws.fleet_home()
    registry = ws.fleet_registry_path()
    manifest_path = ws.workspace_manifest_path()
    state_root = ws.fleet_local_state_root()
    config_root = ws.fleet_controller_config_root()

    print("== environment ==")
    for name, value, state in env_rows():
        print(f"  {name:<22} {state:<6} {value}")

    print("\n== resolved paths (product rules) ==")
    print(f"  workspace home   : {home}")
    print(f"  registry         : {registry}")
    print(f"  workspace.json   : {manifest_path}  ({'present' if manifest_path.is_file() else 'ABSENT -> legacy home mode'})")
    print(f"  state root       : {state_root}")
    print(f"  controller config: {config_root}")

    manifest = read_json(manifest_path)
    mode = "workspace" if isinstance(manifest, dict) and "__error__" not in manifest else "legacy"
    if isinstance(manifest, dict) and "__error__" in manifest:
        print(f"  WARNING: workspace.json unreadable: {manifest['__error__']}")
    print(f"\n== mode: {mode} ==")
    fleet_id = None
    if mode == "workspace":
        fleet_id = manifest.get("fleet_id")
        print(f"  fleet_id  : {fleet_id}")
        print(f"  name      : {manifest.get('name')}")
        print(f"  revision  : {manifest.get('revision')}   updated {manifest.get('updated_at')}")
    elif mode == "legacy" and manifest_path.is_file():
        print("  workspace.json exists but is not usable; treat this as a problem, not as legacy mode")

    reg = read_json(registry)
    nodes: list[dict] = []
    if isinstance(reg, dict) and "__error__" not in reg:
        nodes = reg.get("nodes") or []
        print(f"  registry nodes: {len(nodes)}")
        for n in nodes:
            print(
                "    - {name:<16} admin_ref={a}  observe_ref={o}".format(
                    name=n.get("name"), a=n.get("admin_credential_ref"), o=n.get("observe_credential_ref")
                )
            )
    elif reg is None:
        print("  registry nodes: registry file ABSENT -> `vcl-fleet init`/`workspace init` was never run here")
    else:
        print(f"  registry nodes: UNREADABLE ({reg.get('__error__')})")

    print("\n== cache / audit database ==")
    if fleet_id:
        db = state_root / fleet_id / "fleet.db"
        print(f"  expected   : {db}")
        print(f"  status     : {dbsize(db)}")
        view = state_root / fleet_id / "workspace-view.json"
        v = read_json(view)
        if isinstance(v, dict) and "__error__" not in v:
            print(f"  view       : fleet_id={v.get('fleet_id')} "
                  f"last_seen_revision={v.get('last_seen_revision')}")
            same_id = v.get("fleet_id") == fleet_id
            rev = v.get("last_seen_revision")
            if not same_id:
                print("  NOTE: the view belongs to another fleet_id (stale test data?)")
            elif rev is not None and manifest.get("revision") is not None and rev != manifest.get("revision"):
                print(f"  NOTE: view revision {rev} != workspace revision {manifest.get('revision')} "
                      "(imports/edits elsewhere)")
    else:
        db = home / "fleet.db"
        print(f"  expected   : {db}")
        print(f"  status     : {dbsize(db)}")
    print(f"  other dbs under state root: "
          f"{[str(p) for p in sorted(state_root.glob('*/fleet.db'))] if state_root.is_dir() else []}")

    print("\n== credential bindings (ref names only) ==")
    if config_root.is_dir():
        for d in sorted(config_root.iterdir()):
            f = d / "credential-bindings.json"
            doc = read_json(f)
            if isinstance(doc, dict) and "__error__" not in doc:
                refs = doc.get("bindings") if isinstance(doc.get("bindings"), dict) else doc
                mark = "  <- current fleet" if fleet_id == d.name else "  (other fleet_id: leftover test data?)"
                print(f"  {d.name}: refs={sorted(refs.keys())}{mark}")
            elif f.is_file():
                print(f"  {d.name}: UNREADABLE")
            else:
                print(f"  {d.name}: (no credential-bindings.json)")
    else:
        print(f"  {config_root} does not exist")

    print("\n== other state that matters ==")
    print(f"  trust/known_hosts: {ws.known_hosts_path()}  ({'present' if ws.known_hosts_path().is_file() else 'absent'})")
    print(f"  instance history : {ws.instances_history_path()}")

    print("\n== copy these into the phase A batch script ==")
    print(f"  export PROD_WS={home}")
    print(f"  export PROD_STATE={state_root}")
    print(f"  export PROD_CONFIG={Path(os.environ.get('XDG_CONFIG_HOME') or (Path.home() / '.config'))}")

    print("\n== reminders ==")
    print("  - workspace export/import does NOT carry credential bindings (machine-local by design);")
    print("    the isolated run needs its own `access bind` for every ref listed above.")
    print("  - if the Controller/monitor is running here, its cache keeps changing; leave HASH_PROD_DB=0.")
    print("  - run this on the machine that actually owns the fleet (the recovery record says the")
    print("    seven-node Controller ran on another computer).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
