# Vincula 文档导航

主线 `main`：**Controller/Node 0.5.0**；当前开发分支 `codex/0.5.1`：**Controller/Node 0.5.3 候选**；最低兼容 Node **0.3.1**。0.5.x 的本地收口、当前修复与远端 CI 适用范围见[阶段记录](evidence/0.5.3/PHASE_05_CLOSEOUT.md)。实机 / soak / H05 仍待验收；按 2026-10-07 用户指令停在 0.6.x 之前。旧分支见[清理记录](plans/BRANCH_CLEANUP_2026-09-28.md)。

2026-10-08：现场混合版本Fleet已恢复七台管理面与审计观测，见[恢复记录](operations/fleet-recovery-status.md)和[脱敏汇总](operations/fleet-recovery-20261008.json)。恢复暴露的凭据引用P1（FR-01）已在本地修复并回归，见[FR-01记录](evidence/0.5.3/FR01_CREDENTIAL_ISOLATION.md)；认证分类与错误摘要P2（FR-03/04）也已在本地修复并回归，见[FR-03/04记录](evidence/0.5.3/FR03_FR04_ERROR_MODEL.md)；无界同步P1仍待修复，统一跟踪于[0.5.x可靠性待办](plans/Fleet_Recovery_Reliability_Backlog.md)。临时工具恢复成功不关闭产品缺陷；FR-01 的远端 required CI 已在 `7836b14` 全绿（[#88](https://github.com/Marz42/vcl/actions/runs/37731099502)），但现场混合 Fleet 复验、soak 与 H05 仍 PENDING。

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
| 使用 Inspect、显式基线、Drift 与增强 Verify | [`operations/inspect-runbook.md`](operations/inspect-runbook.md) |
| 核对七台Fleet恢复及下一批0.5.x补修 | [`恢复记录`](operations/fleet-recovery-status.md) · [`可靠性待办`](plans/Fleet_Recovery_Reliability_Backlog.md) |
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
