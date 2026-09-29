# 0.5.1 Live Matrix — PENDING LIVE

用户于2026-09-27明确要求本轮暂不执行真实VPS验收。以下均为待执行步骤，实际结果为空，不能由本地单测或旧0.5.0 evidence代填。

执行前需固定候选source/digest、备份/回退、测试节点/专用身份和维护窗口。不要将URI/UUID/私钥/Clash secret/probe profile写入evidence。

| ID | 前置与操作 | 期望 | 实际结果 / 状态 |
| --- | --- | --- | --- |
| L1 | ≥10真实/受控混合节点，30s interval ≥2h，逐项记录真实/模拟数量 | 无单节点拖垮整轮、无probe storm，retention/资源增长可解释 | 未执行；PENDING LIVE |
| L2 | 专用probe正常后停止sing-box；另测进程active但HTTPS不可用；恢复 | Proxy正确降级/恢复，不把进程active当可用 | 未执行；PENDING LIVE |
| L3 | 持续真实用户代理时停止accountd，再恢复 | Accounting降级，proxy继续，恢复后数据可信状态正确 | 未执行；PENDING LIVE |
| L4 | 阻断SSH，撤销observe key，再恢复 | SUSPECT→UNREACHABLE或AUTH_FAILED；无admin fallback；恢复RECOVERING→HEALTHY | 未执行；PENDING LIVE |
| L5 | kill/restart Controller，保持用户流量 | 代理继续，monitor/cache状态可恢复 | 未执行；PENDING LIVE |
| L6 | fresh 0.5.1及0.3.x/0.5.0升级；检查accountd身份、secret权限、restore/rollback；配置observer并尝试PTY/forward/sudo/shell/mutation | 真实权限隔离、identity/URI/accounting保留、无新公网管理listener；升级可用性≤3s有时间序列 | 未执行；PENDING LIVE |
| L7 | 固定RC 24h类生产soak，含实际probe与恢复场景 | 无P0/P1、无界DB/FD/RSS增长或数据面副作用 | 未执行；PENDING LIVE |

每项完成后追加：时间（含时区）、执行人、候选SHA/digest、匿名拓扑、实际步骤、测量值、恢复结果、脱敏证据路径/digest。原始失败记录与复验分别保存。
