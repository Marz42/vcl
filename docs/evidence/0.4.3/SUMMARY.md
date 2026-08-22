# 0.4.3 Adopt & Provision — DoD SUMMARY
**Stamp:** CTRL `0.4.3` / NODE `0.3.1` · **Gate:** offline `bash tests/test.sh` + `bash tests/test-fleet.sh`

| AC | Result | Evidence |
| --- | --- | --- |
| **4.2-01** | **SKIP LIVE** | fresh VPS+SSH key provision（B4–B7；operator LIVE） |
| **4.2-02** | **PASS** offline / **SKIP LIVE** | B2/B5 fingerprint；LIVE 交互确认 |
| **4.2-03** | **PASS** | B5/B6 non-TTY 无 `--host-key` 拒 |
| **4.2-04** | **PASS** | B3/B6 digest mismatch 不跑 `vincula.sh` |
| **4.2-05** | **SKIP LIVE** | verify+register+sync+VLESS（B4/B7） |
| **4.2-06** | **SKIP LIVE** | 不增公网监听端口（ss/sshd+443 only） |
| **4.2-07** | **PASS** | B5/B6 help 无 password/sudo-password |
| **4.3-P01** | **PASS** | 单 tarball+manifest；zip `payload/` 三文件 |
| **4.3-P02** | **PASS** | 禁 air-gap 措辞；`VCL_SERVER` 跳过 ipify（B2/B8） |
| **4.3-P03** | **PASS** | `add`≡adopt；`add --offline`≡register（B5/B6） |

## Implementation notes

- **D34:** 禁 `StrictHostKeyChecking=no`；non-TTY 必 `--host-key`。
- **D35:** controller-carried digest-verified first-party payload，**非** air-gap；远端仍需 apt / HTTPS / sing-box release / 公网 IP / Reality。
- **D49:** `node add`≡`adopt`；`node add --offline --node-id`≡`register`；0.4.x 保留 alias、无 runtime warning。

## Test counts

Offline gate after B1–B7 stamp: **`bash tests/test.sh` 1693 PASS** · **`bash tests/test-fleet.sh` 925 PASS** (0 not ok; baselines ≥1652 / ≥884).

## CLI reference

| Command | Role |
| --- | --- |
| `node adopt` | 已装节点：SSH `vcl identity --json` → register |
| `node provision` | fresh VPS：preflight → SCP payload → install → verify → register → `sync --full` |
| `node register` | registry-only（无 SSH）；`--node-id` + `--host` 必填 |
| `node add` | legacy alias ≡ `adopt` |
| `node add --offline --node-id` | legacy alias ≡ `register` |

## Stamp

- Controller: `VCL_FLEET_VERSION = "0.4.3"`.
- Node: `VINCULA_VERSION="0.3.1"` unchanged (no allowlist / installer / node fixture bumps).
- D45 namespaces unchanged: accounting-db/v4 · fleet-registry/v2 · fleet-cache/v4 · workspace/v1 · audit-archive/v1.
