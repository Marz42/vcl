# 0.5.0 — SECURITY evidence

> G0 template. Complete at G3 Security Gate.

## Public listeners

| Check | Result | Notes |
| --- | --- | --- |
| No new VPS management port | **PENDING** | Compare pre/post 0.5.0 |
| Clash API loopback-only | **PENDING** | |
| UI loopback-only | **PENDING** | Unchanged from 0.4.x |

## Process identity

| Component | User | Result | Notes |
| --- | --- | --- | --- |
| sing-box | _TBD_ | **PENDING** | |
| vincula-accountd | root → _target_ | **PENDING** | de-root or documented blocker |
| observer SSH | _TBD_ | **PENDING** | forced-command deviation if any |

## Credential routing

| Rule | Result |
| --- | --- |
| observation uses observe ref when configured | **PENDING** |
| no silent admin fallback on observe auth fail | **PENDING** |
| mutation never uses observe identity | **PENDING** |
| logs record credential class only | **PENDING** |

## systemd hardening (accountd)

- `NoNewPrivileges` — **PENDING**
- `ProtectSystem=strict` — **PENDING**
- `ProtectHome=true` — **PENDING**
- `CapabilityBoundingSet=` — **PENDING**

## Secret redaction

| Surface | Result |
| --- | --- |
| telemetry JSON | **PENDING** |
| capabilities JSON | **PENDING** |
| operation journal | **PENDING** |
| fleet cache | **PENDING** |

## Unresolved deviations

| ID | Item | Disposition |
| --- | --- | --- |
| _TBD_ | accountd de-root | _complete or blocker_ |
| _TBD_ | observer forced-command | _complete or 0.5.x progressive_ |

## New attack surface

- `vcl capabilities --json` — read-only; SSH transport only
- `vcl telemetry snapshot --json` — read-only; bounded output

No new northbound HTTP API on Node.
