# 0.5.2 实机验收 — PENDING LIVE

本轮未连接 VPS；当前0.5.2候选见 [M4](M4.md)。以下为必需待执行矩阵，fixture、WSL 和 UI 接口测试不能替代实机结果。

| Case | 实机操作与判据 | 状态 |
| --- | --- | --- |
| L1 | 真实代理持续流量时停止 accountd；出现 AUDIT_STALLED；恢复后 RESOLVED；数据面持续可用 | PENDING LIVE |
| L2 | 真实 export retention/cursor gap 与 sync lag；schema/corruption/loop heartbeat、静止/回退/新 instance 判据；不伪造零用量，恢复/补齐后解释正确 | PENDING LIVE；M2 已实现自动化候选，待实机 |
| L3 | 受控用户流量/连接尖峰和持续异常；正常对照无明显持续误报；证据可解释 | PENDING LIVE；M3 User已PASS OFFLINE，实机本轮跳过 |
| L4 | 真实 service disruption 的 health/service/finding/probe/sync/verify 时间轴可关联；Controller 读取零临时 SSH | PENDING LIVE |
| L5 | 真实节点资源压力、重启循环、网络异常/复位；恢复正确、无 mutation | PENDING LIVE；Node detector 已 PASS OFFLINE，实机本轮跳过 |
| L6 | 完整 RC soak：Finding/store 有界，无 credential UUID/URI/argv 泄漏，无自动配置/服务变更 | PENDING LIVE |

执行前固定候选 SHA、Node/Controller digest、拓扑、测量窗口与可恢复操作步骤。记录真实结果与原始失败；不要补写“推定通过”。

按[最新用户指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)，本轮跳过以上手工执行及等待，状态保留 PENDING LIVE。

**Human Gate H05：PENDING HUMAN**。0.5.x 全部必需项完成后按[人工清单](../../plans/VCL_0.5-0.7_Human_Acceptance.md)验收，工具/CI/实施代理不代签。
