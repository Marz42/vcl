# 0.5.0 — SECURITY evidence

## Public listeners

| Check | Result | Notes |
| --- | --- | --- |
| No new VPS management port | **PASS (offline)** | 0.5.0 adds SSH-only `capabilities`/`telemetry`; no new unit listening on public interfaces |
| Clash API loopback-only | **PASS (offline)** | `test.sh`: clash_api binds `127.0.0.1:9090` in generated config |
| UI loopback-only | **PASS (offline)** | `test-fleet.sh` B15: `assert_loopback_host` in `lib/vincula-ui/server.py` |

0.5.0 observation commands use existing SSH transport; Node does not expose northbound HTTP for telemetry.

## Process identity

| Component | User | Result | Notes |
| --- | --- | --- | --- |
| sing-box | dedicated (installer) | **PASS (offline)** | unchanged from 0.3.x |
| vincula-accountd | root | **BLOCKER (documented)** | de-root deferred to 0.5.1+; see deviations |
| observer SSH | admin/observe keys | **DEVIATION (documented)** | forced-command whitelist deferred; route semantics enforced |

## Credential routing

| Rule | Result |
| --- | --- |
| observation uses observe ref when configured | **PASS (offline)** — obs-auth + obs050 blocks |
| no silent admin fallback on observe auth fail | **PASS (offline)** — AUTH_FAILED fixture |
| mutation never uses observe identity | **PASS (offline)** — upgrade apply argv log uses admin `-i` |
| logs record credential class only | **PASS (offline)** — journal redaction + secret scan |

## systemd hardening (accountd)

Current unit (`lib/vincula-accountd.service`):

- `NoNewPrivileges=true` — **PASS**
- `ProtectSystem=strict` — **PASS**
- `ProtectHome=true` — **PASS**
- `CapabilityBoundingSet=` (empty) — **PASS**
- `User=root` — **BLOCKER** (see below)

Hardening flags are in place; dedicated non-root user is the remaining gap.

## Secret redaction

| Surface | Result |
| --- | --- |
| telemetry JSON | **PASS (offline)** |
| capabilities JSON | **PASS (offline)** |
| operation journal | **PASS (offline)** |
| fleet cache | **PASS (offline)** — unchanged 0.4.x redaction |

## Unresolved deviations

| ID | Item | Disposition | Target |
| --- | --- | --- | --- |
| **SEC-050-01** | accountd runs as root | **BLOCKER documented** | 0.5.1 patch: dedicated `vincula-accountd` user + chown state dirs |
| **SEC-050-02** | observer forced-command SSH whitelist | **DEVIATION documented** | 0.5.x patch: `vincula-observer` user + authorized_keys forced-command |

Threat model (accountd): process can read `/var/lib/vincula` including accounting DB; cannot read Reality private key path when permissions are correct, but root privilege remains broader than target. Accept for 0.5.0 with explicit CHANGELOG note.

L4 equivalent (offline): wrong observe key → AUTH_FAILED, not silent admin success (`obs-auth` test-fleet block).

## New attack surface

- `vcl capabilities --json` — read-only; SSH transport only
- `vcl telemetry snapshot --json` — read-only; bounded output (64KiB cap)
- Controller `vcl-fleet capabilities|telemetry NODE` — same transport; oversize/malformed fail-closed

No new northbound HTTP API on Node.
