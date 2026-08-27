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
4. From Controller: fetch telemetry via planned CLI/service — same fields, no secrets.
5. Optional: loop 10× and note p95 latency ≤2s subjective / log timestamps.

| Field | Value |
| --- | --- |
| Date | _TBD_ |
| Outcome | **PENDING LIVE** |
| Notes | _no secrets_ |

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
| Date | _TBD_ |
| Source version | _0.3.1 or 0.3.2_ |
| Measured outage (s) | _TBD_ |
| Outcome | **PENDING LIVE** |

---

## L3 — Observer credential

1. Configure `observe_credential_ref` distinct from admin (or approved deviation).
2. Controller observation (`capabilities` / `telemetry`) succeeds.
3. Confirm mutation (e.g. `user list` live path) still uses admin.

| Field | Value |
| --- | --- |
| Date | _TBD_ |
| Outcome | **PENDING LIVE** |

---

## L4 — Broken observer → AUTH_FAILED

1. Revoke or corrupt observe key / binding.
2. Retry observation — expect **AUTH_FAILED**, not silent admin success.
3. Restore observe key; observation recovers.

| Field | Value |
| --- | --- |
| Date | _TBD_ |
| Outcome | **PENDING LIVE** |

---

## L5 — Controller offline; data plane continues

1. Establish working client session through node.
2. Stop Controller or block SSH from Controller only (not node public proxy).
3. Confirm existing proxy sessions / new client connects still work for ≥5 minutes.
4. Confirm node did not autonomously change sing-box config.

| Field | Value |
| --- | --- |
| Date | _TBD_ |
| Outcome | **PENDING LIVE** |

---

## Soak — 1000× telemetry (G5)

On one production-like node:

```bash
# Example; exact Controller CLI TBD at implementation
for i in $(seq 1 1000); do vcl telemetry snapshot --json >/dev/null || break; done
```

| Field | Value |
| --- | --- |
| Iterations | _TBD / 1000_ |
| Failures | _TBD_ |
| Node state growth | _TBD_ |
| Outcome | **PENDING LIVE** |

---

## Fail-close spot checks (optional)

- Invalid JSON from mocked response → Controller fail closed.
- Oversize payload → rejected.
- `telemetry` before/after: no unexpected service restarts.

Evidence notes: **path + error type only**; no secret content.
