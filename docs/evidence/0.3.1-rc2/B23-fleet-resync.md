# B23 — Schema 4 Fleet reseed + incremental re-sync

**Result: PASS** (operator live run, 2026-08-20)

Covered on the live fleet after B21/B22 nodes:

- Protocol v2 / `export_seq` path exercised (legacy `CURSOR_PROTOCOL_MISMATCH` + `--reseed` where applicable, or already-migrated `cursor_kind=export_seq`)
- Incremental sync after new closed connections
- Second-round incremental import without duplicates / CURSOR_AHEAD
- Idle sync idempotent (`inserted=0`)
- Fleet `audit` / `stats` attribution OK

See operator session notes; tag artifacts remain `v0.3.1-rc2`.
