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

### Operator copy checklist (next run)

```bash
VCL_SOAK_LIVE=1 VCL_FLEET_HOME=… \
  bash scripts/soak-0.5.0-telemetry.sh NODE --live --iterations 1000
# Then paste only: outcome, summary_sha256, metric status lines (no secrets).
```
