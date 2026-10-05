# 0.5.3 Observation RC soak — PENDING LIVE

日期2026-10-05。**NOT RUN / PENDING LIVE / UNRELEASED**。本地0.5.3 RC见[RC](RC.md)，现场未启动；按 [用户延期指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)跳过24h人工现场等待，继续实现。1000次fake-SSH是离线回归，不是24h soak。

AC-5.3-05需固定Node/Controller版本、制品SHA、源码manifest、OS/架构、Node数量、实际proxy client路径、账户身份、monitor/probe/inspect间隔和UTC窗口。连续至少24h覆盖 monitor→health→finding→inspect→timeline；包含Drift/UNKNOWN/恢复和混合Node降级，并关联 [LIVE](LIVE.md) 的accountd/observer实际权限验证。

保留采样原始记录：真实代理成功/失败与断流窗口；sing-box/accountd/observer service active/restart/RSS/FD；telemetry/poll/heartbeat/inspect freshness与失败计数；数据库大小、retention/capacity/truncation与锁/写失败；Finding生命周期/Timeline与baseline来源。业务流量自然增长与只读副作用分开核对；缺关键指标不填PASS。

起止UTC、候选SHA、拓扑、测量、故障、恢复、最终service active、原始日志hash与结论全部 **PENDING**。soak失败或中断须保留失败记录，不能将离线时长或分段总时长换算为连续24h。

H05另见 [HUMAN_ACCEPTANCE](HUMAN_ACCEPTANCE.md)；本页不替代人工签署，也不授权发布。
