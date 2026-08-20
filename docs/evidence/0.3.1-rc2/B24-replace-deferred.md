# B24 — Replace regression smoke (deferred)

**Status: DEFERRED — Known Issue** (operator choice, 2026-08-20)

## Intent

Re-smoke secretless `vcl-fleet node replace` on the **rc2** tree after Schema 4 /
Fleet Protocol v2, without re-running the full B14 matrix (Win11 + real `age`
already PASS in [`../0.3.1-live/`](../0.3.1-live/)).

## Why deferred

Operator paused before NEW runtime-only VPS + replace cut-over. Tracked as a
**documented limitation / deferred ops item**, **not** a P0/P1 product defect:

- Replace contract (B10 argv + B14 live) already closed on the living tree.
- No known Schema 4 change alters restore argv / `node_id` keep / reissue CSV.
- Residual risk is “rc2 packaging + Protocol v2 cursor kept across replace”
  un-smoked on a second fresh host this round.

## Resume checklist

See readiness B24 section / operator steps previously issued (runtime-only NEW,
`--host-key`, `node replace`, AC-3.0-11, normal sync without auto-reseed).

When completed: move this file’s Result to PASS and close the Known Issue row.
