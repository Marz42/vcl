# 0.5.0 LIVE handbook — Observation Foundation

Operator checklist for **AC-5.0-10** and Live Matrix **L1–L5**.

Record outcomes in [`SUMMARY.md`](SUMMARY.md). **Never** paste IPs, VLESS URIs, UUIDs, Reality private keys, or Clash secrets.

## Preconditions

- Controller tree / zip stamp **0.5.0** with Node payload **0.5.0**.
- At least one **fresh** VPS and one **upgrade** candidate (existing 0.3.1 or 0.3.2).
- Workspace with separate **observe** and **admin** credential bindings (or documented deviation).
- System OpenSSH on workstation; key-based access.

---

## L1 — Fresh Node 0.5.0 telemetry

1. Provision fresh Node 0.5.0 (`vcl-fleet node provision …`).
2. Run on node: `vcl capabilities --json` — expect `telemetry/v1` in list.
3. Run: `vcl telemetry snapshot --json` — schema valid; required fields present.
4. From Controller: `vcl-fleet capabilities NODE --json` / `vcl-fleet telemetry NODE --json` — same fields, no secrets.
5. Optional: loop 10× and note p95 latency ≤2s subjective / log timestamps.

| Field | Value |
| --- | --- |
| Date | _operator TBD_ |
| Outcome | **PENDING LIVE** |
| Offline equiv | **PASS** — fake-ssh `obsnode` alias + obs050 block |

---

## L2 — Upgrade 0.3.x → 0.5.0 (`node upgrade apply`)

1. Record pre-upgrade: client connects without URI change (yes/no only in notes).
2. Start continuous lightweight probe (e.g. `vcl-fleet probe NODE` every 1s in a loop) in a second terminal; record timestamps.
3. Run:

   ```bash
   vcl-fleet node upgrade plan NODE
   vcl-fleet node upgrade apply NODE --yes
   ```

4. Measure probe failure window; target **≤3s** until proxy OK again.
5. Verify `node_id`, `instance_id`, user count, accounting cursor continuity.
6. Re-run client test **without** URI/profile change.
7. Confirm `vcl capabilities --json` and `vcl telemetry snapshot --json` on upgraded node.

| Field | Value |
| --- | --- |
| Date | 2026-08-31 |
| Source version | 0.3.1 |
| Measured outage (s) | ~0 (no consecutive non-OK probe) |
| Outcome | **PASS LIVE** |
| Notes | identity preserved; capabilities/telemetry OK after hotfixes (installer telemetry helper + nested instance_id); client URI unchanged |
| Offline equiv | **PASS** — obs050 upgrade apply + migrate fail fixtures |

---

## L3 — Observer credential

1. Configure `observe_credential_ref` distinct from admin (workspace binding).
2. Controller observation (`capabilities` / `telemetry`) succeeds.
3. Confirm mutation (e.g. `user list` live path) still uses admin.

| Field | Value |
| --- | --- |
| Date | 2026-08-31 |
| Outcome | **PASS LIVE** |
| Notes | observe-default ≠ admin-default; capabilities/telemetry OK via observe; probe/user via admin |

---

## L4 — Broken observer → AUTH_FAILED

1. Revoke or corrupt observe key / binding.
2. Retry observation — expect **AUTH_FAILED**, not silent admin success.
3. Restore observe key; observation recovers.

| Field | Value |
| --- | --- |
| Date | 2026-08-31 |
| Outcome | **PASS LIVE** |
| Notes | revoke observe pubkey → AUTH_FAILED; restore → OK; no silent admin fallback |

---

## L5 — Controller offline; data plane continues

1. Establish working client session through node.
2. Stop Controller or block SSH from Controller only (not node public proxy).
3. Confirm existing proxy sessions / new client connects still work for ≥5 minutes.
4. Confirm node did not autonomously change sing-box config.

| Field | Value |
| --- | --- |
| Date | 2026-09-01 |
| Outcome | **PASS LIVE** |
| Notes | Controller SSH blocked ≥5min; proxy continuous; config/state/users sha unchanged; probe recovered |

---

## Soak — 1000× telemetry (G5)

On one production-like node:

```bash
VCL_SOAK_LIVE=1 VCL_FLEET_HOME=… \
  bash scripts/soak-0.5.0-telemetry.sh NODE --live --iterations 1000
```

Operator evidence (local, not committed): `~/vcl-rc-evidence/0.5.0-soak/<NODE>/SUMMARY.txt`.

| Field | Value |
| --- | --- |
| Date | 2026-09-07 |
| Node | `neptunespear` (upgraded 0.5.0 live candidate) |
| Iterations | 1000 |
| Failures | 0 |
| Elapsed | 3881 s |
| Node state growth | **PASS** — state file count Δ0; sing-box/accountd NRestarts 0→0; active unchanged; state/accounting bytes Δ ≈344 KiB (live traffic; within 16 MiB slack) |
| Outcome | **PASS LIVE** |
| Offline equiv | **PASS** — `soak050` block in test-fleet |

---

## Fail-close spot checks (optional)

- Invalid JSON from mocked response → Controller fail closed. **PASS (offline)**
- Oversize payload → rejected. **PASS (offline)**
- `telemetry` before/after: no unexpected service restarts. **PASS (offline)** — telemetry audit block

Evidence notes: **path + error type only**; no secret content.
