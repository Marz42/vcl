# Operations runbooks

高风险、需要独立检查表的操作。日常流程见 [`../user-guide.md`](../user-guide.md)。

| Runbook | 说明 |
| --- | --- |
| [`node-replace-runbook.md`](node-replace-runbook.md) | B14 live replace 检查表（历史 PASS 2026-08-18；步骤正文不改写） |
| [`monitoring-runbook.md`](monitoring-runbook.md) | 0.5.1 候选监控、专用代理probe、accountd权限与observer接入；Live待执行 |
| [`findings-runbook.md`](findings-runbook.md) | 0.5.2 本地 Findings / Timeline / Audit；stamp 0.5.2；实机 PENDING LIVE、H05 PENDING HUMAN |
| [`inspect-runbook.md`](inspect-runbook.md) | 0.5.3 M1 Node只读Inspect合同/预算/未知语义；Controller缓存/Drift待开发，Human Gate / 实机PENDING |
| [`fleet-recovery-status.md`](fleet-recovery-status.md) | 2026-10-08七台混合版本Fleet恢复回传、缓存与版本来源；正式缺陷修复见[待办](../plans/Fleet_Recovery_Reliability_Backlog.md) |
| [`fleet-recovery-20261008.json`](fleet-recovery-20261008.json) | 本次恢复的脱敏结构化汇总；来源为用户另一台电脑的回传，不替代0.5.3 Live/H05 |
