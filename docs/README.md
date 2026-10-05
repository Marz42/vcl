# Vincula 文档导航

主线 `main`：**Controller/Node 0.5.0**；当前开发分支 `codex/0.5.1`：**Controller/Node 0.5.2 候选**；最低兼容 Node **0.3.1**。真实 VPS / soak / 发布门禁尚未完成，见 [`0.5.2 evidence`](evidence/0.5.2/SUMMARY.md)。旧分支已按[分支清理记录](plans/BRANCH_CLEANUP_2026-09-28.md)处理。

2026-10-04 实现 **0.5.2 Findings / Audit / Anomalies**，M1～M3离线验证通过，M4正式合同/版本/打包收口见[当前记录](evidence/0.5.2/M4.md)。**Human Gate H05/H06/H07 = PENDING HUMAN；实机与 soak = PENDING LIVE。**按[最新用户指令](plans/MANUAL_VALIDATION_DEFERRED.md)跳过等待并记录，正式验收状态保留。

0.5.3本地功能已完成：Node Inspect、Controller缓存/显式baseline/Drift与增强Verify；Node/Controller stamp0.5.3。完整离线验证见[RC记录](evidence/0.5.3/RC.md)，Human Gate/实机与24h soak仍PENDING。

## 按受众阅读

| 你是… | 先读 |
| --- | --- |
| 新用户 / 想 10 分钟了解项目 | 根目录 [`README.md`](../README.md) |
| 日常用终端管 VPS 的管理员 | [`user-guide.md`](user-guide.md) |
| 维护者 / 要对齐实现与合同 | [`technical-guide.md`](technical-guide.md) |
| 做换机等高风险操作 | [`operations/node-replace-runbook.md`](operations/node-replace-runbook.md) |
| 使用 0.5.1 监控、专用 probe 与 observer | [`operations/monitoring-runbook.md`](operations/monitoring-runbook.md) |
| 使用首批 Findings 与本地时间轴 | [`operations/findings-runbook.md`](operations/findings-runbook.md) |
| 核对规格或验收 | [`specs/`](specs/README.md) · [`evidence/`](evidence/README.md) |
| 推进 0.5.x～0.7.x 开发与阶段验收 | [`实施方案`](plans/VCL_0.5-0.7_Implementation_Plan.md) · [`人工验收清单`](plans/VCL_0.5-0.7_Human_Acceptance.md) |
| 查历史冻结 / 旧 known-issues | [`legacy/`](legacy/README.md)（只读，非当前操作依据） |

## 目录结构

```text
docs/
  README.md                 # 本页
  user-guide.md             # 用户手册（操作权威）
  technical-guide.md        # 技术手册（架构与合同权威）
  operations/               # 高风险独立 runbook
  release-readiness-0.3.1.md
  known-issues-0.3.1.md
  specs/                    # 设计规格
  plans/                    # 实施步骤、阶段验收与人工关卡
  evidence/                 # 验收证据（勿改写失真）
  legacy/                   # 历史材料
```

## 单一权威原则

| 主题 | 权威文档 |
| --- | --- |
| 安装与日常工作流 | `user-guide.md` |
| 版本兼容、身份、backup、accounting、UI 边界 | `technical-guide.md` |
| replace 逐步检查表 | `operations/node-replace-runbook.md` |
| CLI 全参数 | 各命令 `--help` |
| 产品版本戳 | 代码中的 `VCL_FLEET_VERSION` / `VINCULA_VERSION` |

同一事实不要在多份「当前手册」里各维护一份；用链接引用权威章节。

## Gate 与限制（Node 线）

- [`release-readiness-0.3.1.md`](release-readiness-0.3.1.md)
- [`known-issues-0.3.1.md`](known-issues-0.3.1.md)
- Controller 0.4.5：[`evidence/0.4.5/SUMMARY.md`](evidence/0.4.5/SUMMARY.md)
