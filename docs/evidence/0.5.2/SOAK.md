# 0.5.2 Soak — PENDING LIVE

本轮未执行 production-like soak；当前0.5.2候选与离线范围见 [M4](M4.md)。执行前需固定 SHA/digest，至少 24h 检查 Finding 数量、重复事件、DB/FD/RSS 增长、并发读取、故障恢复、普通波动误报与数据面副作用；本轮按用户指令跳过等待。

行数/DB 上限及截断标记的单元测试不代表 24h soak 已通过。结果、原始证据位置和摘要未齐全前，G5 保持 **PENDING LIVE / UNRELEASED**；Human Gate H05 仍为 **PENDING HUMAN**。
