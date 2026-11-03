# 0.5.3 MPTCP 单元加固重建

日期：2026-11-02（Asia/Shanghai）。分支 `codex/0.5.1`，源码基线 `75071d8`（2026-10-16），加固提交 `5685983`（父提交 `5a4fd8c`）。版本仍为 **0.5.3**，最低兼容 Node **0.3.1**，sing-box **1.13.18**。

**RECONSTRUCTED LOCALLY / CI PASS (run 41455589528) / UNRELEASED / PENDING RE-FREEZE / PENDING LIVE / PENDING HUMAN。**本页只记录把现场已经验证的 MPTCP 加固纳入源码与安装包的过程，不授权 push/merge/tag/release，也不替代 H05。

## 变更

- Go 1.24+ 默认给 listener 启用 MPTCP（`multipathtcp=2`）；按 [Xray-core #7291](https://github.com/XTLS/Xray-core/pull/7291) 的讨论，这会扩大 CVE-2026-98432 的攻击面。
- `vincula.sh` 的 `render_systemd_unit` 在 `[Service]` 增加：

  ```ini
  # Go 1.24+ enables MPTCP by default for listeners; keep it off (CVE-2026-98432).
  Environment=GODEBUG=multipathtcp=0
  ```

- `tests/test.sh` 增加单元渲染断言，防止以后删除该行。
- 该函数被 `install_new_node`、`migrate_existing_install`、runtime-only 安装等路径复用；因此重装/升级会重新渲染 unit，补丁必须随安装包发布，不能只留在现场机器上。

## 现场落地（2026-11-01）

七台节点已手工落地并验证：`sing-box` unit 增加同一行、`daemon-reload`、restart，进程环境存在 `GODEBUG`，`ss -M -a` 不再出现 MPTCP listener，`vcl status`/`vcl verify` 通过；回滚点为各节点 `/root/sing-box.service.bak-mptcp-20261101`。完整记录见[2026-11-01 运维记录](../../operations/2026-11-01-sync-mptcp.md)。

## 测试与构建

- 单元渲染：`render_systemd_unit` 输出包含 `Environment=GODEBUG=multipathtcp=0`（新增断言，套件内 `ok … unit disables Go MPTCP listeners`）。
- 完整 Bash 套件：**1951/1951 PASS，exit 0**（`SQLITE_TMPDIR=<workspace>/tmp/sqlite-tmp bash tests/test.sh`；本机日志 `tmp/vcl-mptcp-20261102/bash.log`，未入库）。
- Python 套件：本变更不涉及 Python runtime；2026-11-02 复跑 **155 项：153 PASS / 8 skip / 2 个既有 root-only 用例 FAIL**（本机无 sudo；CI 的 ubuntu job 用 `sudo -n` 覆盖）。
- 构建：`scripts/build-release.sh` + `scripts/build-controller.sh`，`SOURCE_DATE_EPOCH=1793612077`（`5685983` 的提交时间）。Node tar 与 Controller embedded payload 均确认包含该行；sidecar、Node `release.lock`、Controller `controller.lock` 均校验通过。
- 独立制品检查：`scripts/check-controller-artifact.py` → `PASS OFFLINE`（schema 16、cache-only 入口 4、`node_cli=NOT RUN`，本机非 root；CI 用 sudo 覆盖）。
- 远端 required CI：[run 41455589528](https://github.com/Marz42/vcl/actions/runs/41455589528) 七个 job 全绿（Ubuntu、Debian 12/13、Windows、concurrency、failure-injection、artifact），`head_sha=56243b6`；脱敏快照见 [`REMOTE_CI_20261102_MPTCP.json`](REMOTE_CI_20261102_MPTCP.json)。

## 制品

**BUILT LOCALLY 2026-11-02 / UNRELEASED。**当前 `dist/`：

| 制品 | SHA256 |
| --- | --- |
| `dist/vincula-node-0.5.3.tar.gz` | `06e133fb9d67fc711aad6cab63e235e470c9c1a0e58da6765aa762f4b03837ec` |
| `dist/vincula-controller-0.5.3.zip` | `427fec191396adca39218bfd0e356ac66dc37820c3b5e833d3ad2831a8a6ac16` |
| `dist/vincula-controller-0.5.3/payload/payload-manifest.json` | `2c5f40f9d1db8df7f3aa8b45eb1b53c01654d7aca381cf730cdefcb41e7c946c` |

payload manifest 的 `node_payload_version=0.5.3`、`sha256=06e133fb…`，与 Node tar 一致。旧 [CANDIDATE_FREEZE](CANDIDATE_FREEZE.md) 的 `8abe989c…` / `65dbcc7b…` 只对应 2026-10-08 构建，不再对应当前 `dist/`。

## 限制与后续

1. **未升版本**：本轮按“把补丁进安装包”的最小范围处理，版本仍为 0.5.3；正式发布或 H05 前应决定是否升 0.5.4 并重新生成 `SOURCE_INPUTS`/冻结记录。同一版本对应不同 SHA 只应作为本地重建使用。
2. **只关 Go 侧**：`GODEBUG=multipathtcp=0` 关闭 Go 的 listener/dialer MPTCP；内核 `net.mptcp.enabled` 未改。若要主机级封堵，需另加 sysctl，并评估对其他程序的影响。
3. **未推送/未跑远端 CI**：本页的本地测试与构建完成后，仍需单独推送并跑 required CI，才能成为新候选。
4. **H05**：新制品需要重新冻结并重新绑定现场证据；旧阶段 A/B/C 证据仅对应旧制品。
