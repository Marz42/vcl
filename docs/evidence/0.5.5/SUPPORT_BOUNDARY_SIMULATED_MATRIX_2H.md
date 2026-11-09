# Support-boundary synthetic 2h matrix — 2026-11-09

**PASS OFFLINE / two_hour_matrix=true.**

| Field | Value |
| --- | --- |
| Source commit | `465106440688ab73823cbe4871139c834488d4ae` |
| Start (UTC / CST) | 2026-11-08T23:28:44Z / 2026-11-09 07:28:44 |
| End (UTC / CST) | 2026-11-09T01:28:44Z / 2026-11-09 09:28:44 |
| Elapsed | 7,200.0056 s |
| Exit code | 0 |
| Nodes | 10 |
| Samples | 2,401 (238–241 per node) |
| Observation errors | 0 |
| Maximum concurrency | 8 |
| State | PASS OFFLINE |

## Original files and SHA256

| Original file | SHA256 | Archived copy |
| --- | --- | --- |
| `SUMMARY.json` | `309a4dfb8ee8ebbf4f70e495d8650eea8845fefa57e9b660ceaf8919030d5363` | `SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.json` |
| `runner.log` | `65d0a0388d08b5ccf5062be6ff54850ee0681911c5af6d948c2b7b37094ad43b` | `SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.runner.log.txt` |
| `START.json` | `5c777f934ddd436302940270a7b0245846224f3a4afa02e07244053cc770bc4b` | `SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.start.json` |
| `PROGRESS.json` | `9a495d3168e935c31446d82b9bb47e3315b10b27d1c0d92698ca272f6c4d7795` | `SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H.progress.json` |
| `observation.db` | `dab500145799527857cd8ba79f78336432d8614dd4020ee1139a3b6ad9b43f8e` | not committed (binary; SHA recorded) |

The first four archived copies are byte-identical to the originals. The machine-readable
manifest is [SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H_MANIFEST.json](SUPPORT_BOUNDARY_SIMULATED_MATRIX_2H_MANIFEST.json).

## Log summary

```json
{"state": "PASS OFFLINE", "elapsed_seconds": 7200.005599575998, "two_hour_matrix": true, "maximum_concurrency": 8}
```

Final progress reached 2,391 samples at 7,170.2 s; the completed report records 2,401 samples.
No sleep, pause or interruption was observed: wall-clock duration was exactly two hours,
the observed maximum per-node sampling gap was 33.0–33.6 s, and `observation_errors=0`.

## Input verification

- 17 report inputs match source commit `4651064` (17/17, 0 mismatches).
- 202 source inputs in `SUPPORT_BOUNDARY_SOURCE_INPUTS.json` match the same commit (202/202, 0 mismatches).

This is an offline, synthetic result. Real proxy, Inspect/Drift, Live/H05 and the new
continuous 24h soak remain pending.
