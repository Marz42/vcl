# 0.4.3 Adopt & Provision — DoD SUMMARY
**Stamp:** CTRL `0.4.3` / NODE `0.3.1` · **Gate:** offline `bash tests/test.sh` + `bash tests/test-fleet.sh`

| AC | Result | Evidence |
| --- | --- | --- |
| **4.2-01** | **PASS LIVE** | fresh VPS+SSH key `node provision`（B4–B7；operator VPS 2026-08-24） |
| **4.2-02** | **PASS LIVE** | B2/B5 fingerprint；LIVE 交互确认 host-key |
| **4.2-03** | **PASS** | B5/B6 non-TTY 无 `--host-key` 拒 |
| **4.2-04** | **PASS** | B3/B6 digest mismatch 不跑 `vincula.sh` |
| **4.2-05** | **PASS LIVE** | verify+register+sync；VLESS 连通（URI/UUID 未入库） |
| **4.2-06** | **PASS LIVE** | 公网仅新增 TCP 443；Clash API 为本机回环 |
| **4.2-07** | **PASS** | B5/B6 help 无 password/sudo-password |
| **4.3-P01** | **PASS** | 单 tarball+manifest；zip `payload/` 三文件 |
| **4.3-P02** | **PASS** | 禁 air-gap 措辞；`VCL_SERVER` 跳过 ipify（B2/B8） |
| **4.3-P03** | **PASS** | `add`≡adopt；`add --offline`≡register（B5/B6） |

## Implementation notes

- **D34:** 禁 `StrictHostKeyChecking=no`；non-TTY 必 `--host-key`。
- **D35:** controller-carried digest-verified first-party payload，**非** air-gap；远端仍需 apt / HTTPS / sing-box release / 公网 IP / Reality。
- **P2 pipe drain:** provision installer SSH drains stdout/stderr on reader threads; saved output is a bounded redacted tail so large remote logs cannot deadlock as a 600s timeout.
- **D49:** `node add`≡`adopt`；`node add --offline --node-id`≡`register`；0.4.x 保留 alias、无 runtime warning。

## Test counts

Offline gate: **`bash tests/test.sh` 1736 PASS** (0 not ok; baseline ≥1652).

## LIVE gate (operator VPS)

| Field | Value |
| --- | --- |
| Date | 2026-08-24 |
| Code HEAD | `3429eb6` (`fix: drain provision installer pipes so large output cannot deadlock (0.4.3 LIVE)`) |
| VPS OS / arch | Debian 13 amd64 |
| Privilege | root path |
| Not recorded | IP, VLESS URI, UUID, Reality private key, Clash secret |

AC-4.2-01 / 02 / 05 / 06 **PASS LIVE**. Public listen is TCP 443 only; Clash API stays loopback. Interactive host-key confirmation (AC-4.2-02). verify + register + sync succeeded (AC-4.2-05).

## CLI reference

| Command | Role |
| --- | --- |
| `node adopt` | 已装节点：SSH `vcl identity --json` → register |
| `node provision` | fresh VPS：两阶段 preflight → SCP payload → install → verify → register → `sync --full` |
| `user link TAG --node NAME` | 单节点实时 SSH 取 VLESS URI（不缓存） |
| `node register` | registry-only（无 SSH）；`--node-id` + `--host` 必填 |
| `node add` | legacy alias ≡ `adopt` |
| `node add --offline --node-id` | legacy alias ≡ `register` |

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.4.3"`.
- Node: `VINCULA_VERSION="0.3.1"` unchanged (no allowlist / installer / node fixture bumps).
- D45 namespaces unchanged: accounting-db/v4 · fleet-registry/v2 · fleet-cache/v4 · workspace/v1 · audit-archive/v1.
