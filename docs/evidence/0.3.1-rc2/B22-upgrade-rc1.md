# B22 — Live upgrade surrogate: 0.3.1-rc1 → 0.3.1-rc2

**Result: PASS** (operator live run, 2026-08-20)

| Item | Notes |
| --- | --- |
| From → To | `0.3.1-rc1` → `0.3.1-rc2` (allowlisted; **surrogate** for planned `0.3.0 → rc2`) |
| Artifact | `vincula-node-0.3.1-rc2.tar.gz` / SHA256 `ce806450…c93d92` |
| Identity | `node_id` / `instance_id` unchanged |
| Credentials / Reality | unchanged; old URI still worked |
| Accounting | schema already **4** on rc1; remained **4**; history continuous |
| Services | both enabled+active after migrate; no rollback |

**Honesty:** This closes the **rc1→rc2** live upgrade path. True live **`0.3.0 → 0.3.1-rc2`** (schema 3→4 on open) remains an evidence gap unless waived or run later.
