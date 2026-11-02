# 2026-11-01 运维记录：状态巡检 / 审计同步 / MPTCP 补丁

> 归档自 `tmp/ops-20261101-sync-mptcp.md`（2026-11-02）。本轮一次性的巡检/同步/rollout 脚本已清理；原始 `probe`/`sync` JSON 见 [2026-11-01-probe.json](2026-11-01-probe.json) 与 [2026-11-01-sync.json](2026-11-01-sync.json)。


## 1. 状态巡检（probe，08:10Z）

| 节点 | SSH | PROXY | ACCOUNTING | 备注 |
| --- | --- | --- | --- | --- |
| epicfury | OK | OK | OK | |
| upperhand | OK | OK | OK | |
| eagleclaw | OK | OK | OK | |
| neptunespear | OK | OK | OK | |
| hot-beam-1 | OK | OK | OK | |
| fresh050 | OK | OK | OK | |
| urgentfury | **FAIL** | UNKNOWN | UNKNOWN | `ssh_reason=TIMEOUT` |

**urgentfury 说明**：从国内到 `69.63.198.51` 的 22 与 443 **全部超时**；从 hot-beam-1（境外）测试 22/443 均 **OPEN**，主机在线。判定为针对该 IP 的 IP 级阻断（10-26 时仅 20687 被封，现已升级）。跳板 `ssh -J root@104.194.90.172` 可达，本次补丁即经跳板完成。

## 2. 审计日志同步（`sync --full` → 本地 fleet.db）

`VCL_FLEET_LOCAL_STATE=/home/marz/.local/state/vincula`，`--page-size 5000 --timeout 60`。

| 节点 | 起始游标 | 结束游标 | 新增事件 | 页数 |
| --- | ---: | ---: | ---: | ---: |
| epicfury | 890,858 | 981,369 | 90,511 | 19 |
| upperhand | 716,699 | 816,531 | 99,825 | 20 |
| eagleclaw | 1,223,092 | 1,477,582 | 254,482 | 51 |
| neptunespear | 1,760,887 | 2,024,531 | 263,599 | 53 |
| hot-beam-1 | 948,892 | 948,892 | 0 | 1 |
| fresh050 | 146,882 | 201,605 | 54,723 | 11 |
| urgentfury | 156,292 | 156,292 | 0（超时） | 0 |

合计新增 **763,140** 条；`fleet.db` 约 **3.3 GB**。urgentfury 因国内路径不可达未能同步，需在可路由的网络上补跑。

> 注：本轮最初误按“节点 journal 落盘”执行，已中止并清理临时目录；按你的口径改为审计数据 sync。

## 3. MPTCP 补丁

### 背景

- 参考 PR：XTLS/Xray-core #7291（comment 6540309985）——Go 1.24 起 **listener 默认启用 MPTCP**（`multipathtcp="2"`），作者主张默认关闭以减小 CVE-2026-98432 攻击面。
- Go 官方可切换值：`GODEBUG=multipathtcp=0`（dialer 与 listener 全关）。
- Vincula 的 sing-box 1.13.18 由 **Go 1.25.12** 构建，因此同样默认开启。

### 实测证据（补丁前）

hot-beam-1：
```
$ ss -M -a
LISTEN 0 4096 0.0.0.0:https      0.0.0.0:*
LISTEN 0 4096 127.0.0.1:9090     0.0.0.0:*
```
即 sing-box 的 443 与 Clash API 9090 都通过 MPTCP 监听。7 台节点 `net.mptcp.enabled` 均为 1，进程环境无 `GODEBUG`。

### 补丁

单元文件 `[Service]` 增加一行（源码模板同步修改）：

```ini
# Go 1.24+ enables MPTCP by default for listeners; keep it off (CVE-2026-98432).
Environment=GODEBUG=multipathtcp=0
```

代码改动：`vincula.sh:1409-1410`（unit 模板），`git diff` 为 1 文件 +2 行。`dist/vincula-node-0.5.3/` 是构建产物，未手工修改，需重新打包才能带上该行。

### 落地与验证（7 台全部完成）

每台执行：备份 unit → 写入 Environment → `daemon-reload` → `restart sing-box` → 校验；失败则自动回滚。

| 节点 | 单元 | 进程 env | `vcl status` | MPTCP 监听 | TCP 443 |
| --- | --- | --- | --- | --- | --- |
| hot-beam-1 | patched | ✓ | ✓ | 无 | ✓ |
| epicfury | patched | ✓ | ✓ | 无 | ✓ |
| upperhand | patched | ✓ | ✓ | 无 | ✓ |
| eagleclaw | patched | ✓ | ✓ | 无 | ✓ |
| neptunespear | patched | ✓ | ✓ | 无 | ✓ |
| fresh050 | patched | ✓ | ✓ | 无 | ✓ |
| urgentfury（经跳板） | patched | ✓ | ✓ | 无 | ✓（境外） |

- `vcl verify`（hot-beam-1）在改动后仍全绿，含 accounting 面与 Clash 鉴权。
- 回滚点：各节点 `/root/sing-box.service.bak-mptcp-20261101`。
- 国内到 6 台可达节点的 443 均 OPEN；urgentfury 仍受 IP 阻断影响。

### 仍需处理

1. **内核更新**：PR 作者同时建议更新内核；本次只关闭了 Go 侧 MPTCP 监听，未升级内核，也未设置 `net.mptcp.enabled=0`。若需要主机级封堵，可另加 sysctl。
2. **urgentfury 的国内可达性**：IP 级阻断不会因端口/MPTCP 改动而恢复，仍需换 IP 或前置中转。
3. **urgentfury 审计同步**：待其可达后补跑 `sync --full --node urgentfury`。
4. **构建产物**：`dist/` 未重建；发布前需用 `scripts/build-release.sh` 重新打包。

### 2026-11-02 补记：安装包已重建

- 上面第 4 项已完成：源码加入 `GODEBUG=multipathtcp=0` 与单元断言，`release.lock` 已更新，Node tar / Controller zip / embedded payload 均已重建并校验。
- 新制品：Node `06e133fb…`、Controller `427fec19…`、payload manifest `2c5f40f9…`；详见[MPTCP 单元加固记录](../evidence/0.5.3/MPTCP_UNIT_HARDENING.md)。
- 旧[冻结候选](../evidence/0.5.3/CANDIDATE_FREEZE.md)的 `8abe989c…` / `65dbcc7b…` 只对应旧构建，不再对应当前 `dist/`。
- 仍未 push、未跑远端 CI、未重新冻结；H05 仍 PENDING HUMAN。
