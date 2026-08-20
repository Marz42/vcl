# AC-4.0-M05 — dual-controller portable workspace (LIVE)

**Status:** NOT RUN (requires two machines / dual WSL; gated by `VCL_LIVE_M05=1`).

Offline CI covers the structural half only (same `fleet_id`, independent `fleet.db`, bind on machine B). Full cross-machine migrate → sync → probe → copy → bind → sync → status → ui is LIVE.

| Artifact | Purpose |
| --- | --- |
| [`RUNBOOK.md`](RUNBOOK.md) | Operator steps (machine A → B) |
| [`SUMMARY.md`](SUMMARY.md) | Result record (fill after LIVE run) |

Do **not** commit private keys, VLESS URIs, or host credentials.
