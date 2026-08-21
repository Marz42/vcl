# 0.4.2 Local Cache & Archive — DoD SUMMARY
**Stamp:** CTRL `0.4.2` / NODE `0.3.1` · **Gate:** offline `bash tests/test.sh` + `bash tests/test-fleet.sh`
| AC | Result | Evidence |
| --- | --- | --- |
| **4.1-01** | **PASS** | B4/B8 offline zero SSH |
| **4.1-03** | **PASS** offline / **SKIP LIVE** | B5 fake-ssh; LIVE optional |
| **4.1-04** | **PASS** | B5 PARTIAL exit 2 |
| **4.1-05** | **PASS** | B7 restore cursor unchanged |
| **4.1-06** | **PASS** offline half / **SKIP LIVE** | B7 Workspace+archive+fresh db |
| **4.2-C01** | **PASS** | B4 true mode=ro |
| **4.2-C02** | **PASS** | B3 fleet-cache/v4 |
| **4.2-C03** | **PASS** | B1/B3 local-state + MISMATCH |
| **4.2-C04** | **PASS** | B5 --full additive / sync legacy |
| D58 status/--live/probe | **PASS** | regression unchanged |
