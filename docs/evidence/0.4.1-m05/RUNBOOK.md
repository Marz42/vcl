# AC-4.0-M05 LIVE runbook — dual WSL / dual controller

Prerequisite: two controller homes (machine **A** and machine **B**), shared SSH reachability to the same fleet node(s), and a portable identity file available on both (or rebound on B).

Gate: set `VCL_LIVE_M05=1` only on an operator machine. CI must never set this variable.

## Machine A

1. `vcl-fleet init` (or use an existing legacy fleet home).
2. Ensure at least one active node is registered (live add or offline + reachable).
3. `vcl-fleet workspace migrate` — creates `workspace.json`, credential refs, `trust/`, `history/`, `machine-local/` bindings.
4. `vcl-fleet sync --node <name>` — refresh machine-local cache (`fleet.db`).
5. `vcl-fleet probe` — live SSH health; writes `last-status.json`.
6. Record `fleet_id` from `vcl-fleet workspace show`.

## Copy portable workspace A → B

Copy the portable tree to B’s `$VCL_FLEET_HOME` (or `--workspace` root). **Exclude:**

- `machine-local/` (bindings + workspace-view are machine-local)
- `fleet.db` (+ `-wal`/`-shm` if present)
- `last-status.json` (derived cache)

Include at least: `workspace.json`, `fleet.json`, `trust/`, `history/`, and any non-secret portable assets. Do not pack private keys into the archive if they live outside the tree; bind them on B instead.

## Machine B

1. Point `VCL_FLEET_HOME` (or `vcl-fleet --workspace`) at the copied root.
2. `vcl-fleet access bind <admin_credential_ref> --identity-file <path-on-B>`  
   (ref name from A’s migrated registry, e.g. `migrated-key-1`).
3. `vcl-fleet access verify`
4. `vcl-fleet sync --node <name>` — creates an **independent** `fleet.db` on B.
5. `vcl-fleet status` — cache-only (no SSH); confirm nodes/`fleet_id` identity.
6. `vcl-fleet ui --help` (optional: brief loopback UI smoke).
7. Confirm: same `fleet_id` as A; `fleet.db` on A and B are distinct files (not the same inode/path).

## Evidence

Update [`SUMMARY.md`](SUMMARY.md) with date, hosts, commit SHA, and PASS/FAIL per step. Redact secrets.
