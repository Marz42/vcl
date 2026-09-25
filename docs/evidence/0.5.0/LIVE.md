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
5. Compare `node_id` in the registry, live `vcl identity --json`, and Controller telemetry; compare `instance_id` in live identity and telemetry. Do this locally and record only match/mismatch, never the UUID values.
6. With the distinct observe binding, run `vcl-fleet probe --json` and `vcl-fleet verify --json`; both must succeed.
7. Optional: loop 10× and note p95 latency ≤2s subjective / log timestamps.

| Field | Value |
| --- | --- |
| Date | 2026-09-25 |
| Outcome | **PASS LIVE** — fresh provision, direct and Controller capabilities/telemetry, probe and verify all OK with a separate observe credential |
| Clock note | VPS reported `NTP=yes`, `NTPSynchronized=yes`. The prior ~57s full-Fleet clock WARN cleared on `8762362`; follow-up skew was ~6.9s and clock=OK. |
| Offline equiv | **PASS** — fake-ssh `obsnode` alias + obs050 block |

---

## L2 — Upgrade 0.3.x → 0.5.0 (`node upgrade apply`)

1. Record pre-upgrade: client connects without URI change (yes/no only in notes).
2. Start a one-second watcher in a second terminal that uses the node's admin SSH binding to run remote `vcl status --json`. Record proxy OK/FAIL transitions and timestamps. The Fleet `probe` command has no per-node argument.
3. Run:

   ```bash
   vcl-fleet node upgrade plan NODE
   vcl-fleet node upgrade apply NODE --yes
   ```

4. If a poll fails, measure the interval from the last OK poll to the first recovered OK poll; target **≤3s**. If no poll fails, record "none observed" rather than claiming zero outage.
5. Verify `node_id`, `instance_id`, user count, accounting cursor continuity.
6. Re-run client test **without** URI/profile change.
7. Confirm `vcl capabilities --json` and `vcl telemetry snapshot --json` on upgraded node. From Controller, confirm telemetry identity matches the current Node identity and `probe` / `verify` work via the observe binding.

| Field | Value |
| --- | --- |
| Date | 2026-09-25 re-check |
| Source version | 0.3.1 |
| Measured outage (s) | No failed one-second proxy-status polls observed; exact outage duration was not measured. |
| Outcome | **PARTIAL LIVE** — current `node upgrade apply` returned SUCCESS and subsequent sync succeeded; client-profile and post-upgrade observation confirmations pending |
| Notes | Current apply's post-check verifies version, node_id and instance_id. Operator reported only initial watcher OK, upgrade success and normal sync. Prior 2026-08-31 full L2 run passed; do not use that run to claim current client continuity. |
| Offline equiv | **PASS** — obs050 upgrade apply + migrate fail fixtures |

---

## L3 — Observer credential

1. Configure `observe_credential_ref` distinct from admin (workspace binding).
2. Controller observation (`capabilities` / `telemetry`) succeeds.
3. Confirm mutation (e.g. `user list` live path) still uses admin.

| Field | Value |
| --- | --- |
| Date | 2026-09-25 re-check |
| Outcome | **PASS LIVE** — capabilities, telemetry, probe and verify all OK via observe |
| Notes | Operator confirmed admin-default and observe-default contain different keys on an existing 0.5.0 node. Fresh node also passed verify after the observe public key was authorized. |

---

## L4 — Broken observer → AUTH_FAILED

1. Revoke or corrupt observe key / binding.
2. Retry `capabilities`, `telemetry`, `probe`, and `verify` — expect **AUTH_FAILED**, not silent admin success. A locally bound, unauthorized test key may be used instead of revoking the remote key; restore the original observe ref afterward.
3. Restore observe key; observation recovers.

| Field | Value |
| --- | --- |
| Date | 2026-09-25 re-check |
| Outcome | **PASS LIVE** — capabilities, telemetry, probe and verify rejected unauthorized observe access; recovered after authorization/binding restore |
| Notes | On an existing node, a temporarily unauthorized local observe key yielded AUTH_FAILED for capabilities, telemetry and probe; restoring the binding recovered capabilities. On the fresh node, verify yielded AUTH_FAILED before its observe public key was authorized and OK afterward. |

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

Operator evidence (local): `~/vcl-rc-evidence/0.5.0-soak/<NODE>/{SUMMARY.txt,DIGEST.json}`.
In-repo redacted digest: [`SOAK.md`](SOAK.md).

Gate (current script): missing metrics → **FAIL**; services must end **active**; RSS/FD growth bounded; no SKIP→PASS LIVE.

| Field | Value |
| --- | --- |
| Date | 2026-09-07 |
| Node | `neptunespear` (upgraded 0.5.0 live candidate) |
| Iterations | 1000 |
| Failures | 0 |
| Elapsed | 3881 s |
| Node state growth | **PASS** (file count Δ0; NRestarts 0→0; bytes Δ≈344 KiB) under prior gate |
| RSS / FD | **PENDING LIVE** (not in 2026-09-07 snapshot; re-run required) |
| Outcome | **PARTIAL** (telemetry soak OK; tightened resource gate pending) |
| Offline equiv | **PASS** — `soak050` block in test-fleet |

---

## Fail-close spot checks (optional)

- Invalid JSON from mocked response → Controller fail closed. **PASS (offline)**
- Oversize payload → rejected. **PASS (offline)**
- `telemetry` before/after: no unexpected service restarts. **PASS (offline)** — telemetry audit block

Evidence notes: **path + error type only**; no secret content.
