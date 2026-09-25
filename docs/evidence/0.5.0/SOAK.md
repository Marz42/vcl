# 0.5.0 soak digest (redacted)

Operator-local raw evidence stays under `~/vcl-rc-evidence/0.5.0-soak/<NODE>/`.
This file is the **in-repo verifiable summary** (no IPs, URIs, UUIDs, or keys).

## Run — 2026-09-07 (`neptunespear`)

| Field | Value |
| --- | --- |
| Date (UTC day) | 2026-09-07 |
| Node label | `neptunespear` (upgraded 0.5.0 live candidate) |
| Script | `scripts/soak-0.5.0-telemetry.sh --live --iterations 1000` |
| Iterations | 1000 |
| Failures | 0 |
| Elapsed | 3881 s |
| state_dir_file_count | Δ0 |
| sing-box / accountd NRestarts | 0→0 |
| Services active | unchanged (reported active) |
| state/accounting bytes | Δ ≈344 KiB (live traffic; within 16 MiB slack) |

### Gate status vs current script

The 2026-09-07 run used an earlier gate that could **SKIP** missing metrics and accept `inactive→inactive`. Current script **fail-closes** missing metrics, requires **after=active**, and compares process **RSS/FD**.

| Gate item | 2026-09-07 evidence |
| --- | --- |
| 1000× telemetry OK | **PASS** |
| file count / NRestarts | **PASS** |
| require after=active | measured active (PASS under old compare) |
| RSS / FD before→after | **not measured** → soak gate **PENDING LIVE** re-run |
| In-repo DIGEST.json | produce on next run; copy `summary_sha256` here |

**Soak outcome for AC-5.0-10:** **PARTIAL** until a re-run with the tightened script emits `DIGEST.json` and `outcome=PASS LIVE`.

## Run — 2026-09-25 operator report (`eagleclaw`)

The current live run completed 1000/1000 telemetry calls with zero failures in 5643 s. State and accounting DB growth, service restart counts, active state, RSS, and file descriptors all passed. The script reported `FAIL LIVE` only because `/var/log/vincula` did not exist in either snapshot and its file count was recorded as null. Both snapshots also recorded null `log_dir_bytes`, which the collector emits only when the path is absent. The Node uses journald; `/var/log/vincula` is not created by the product.

| Field | Value |
| --- | --- |
| Original summary SHA-256 | `101968b85b10638d961a61be1bcab904eeaf1ffa43cf5e89dba3136e8671c48a` |
| Telemetry | 1000/1000 OK; 0 failures |
| Elapsed | 5643 s |
| State growth | +397528 bytes; accounting DB +360448 bytes; state file count 3→3 |
| Restarts | sing-box 0→0; accountd 0→0 |
| RSS | sing-box +5584 KiB; accountd +2136 KiB |
| FD | sing-box 18→22; accountd 7→7 |
| Original outcome | **FAIL LIVE** — optional log directory absent; recheck pending |

The revised script treats an absent optional log directory as zero files and provides `--recheck-evidence` to evaluate the saved snapshots without repeating the 1000 calls. It verifies the original summary/digest pair and writes separate `SUMMARY.recheck.txt` and `DIGEST.recheck.json`; the original failed evidence remains intact.

```bash
bash scripts/soak-0.5.0-telemetry.sh eagleclaw --recheck-evidence
```

### Operator copy checklist (next run)

```bash
VCL_SOAK_LIVE=1 VCL_FLEET_HOME=… \
  bash scripts/soak-0.5.0-telemetry.sh NODE --live --iterations 1000
# Then paste only: outcome, summary_sha256, metric status lines (no secrets).
```
