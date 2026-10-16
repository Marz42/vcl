# 0.5.1 Soak — PENDING LIVE

本轮未执行≥10节点2h或24h真实/类生产soak，遵照用户“真实VPS验收先不做”的范围。

已有本地证据包括：12节点受控调度单测、clock推进的retention/rollup、错误/重启/并发/坏cache用例，以及原全量suite中的1000次fake telemetry回归。它们是offline/fixture证据，不能记录为PASS LIVE或24h soak。

后续需记录固定候选、真实/模拟节点数量、持续时间、采样成功/失败、超时/退避分布、DB大小/行数、RSS/FD、服务restart count、代理真实成功率及人工故障恢复。判定与恢复步骤见[SPEC](../../specs/V0.5.1_Spec.md)及[LIVE](LIVE.md)。
