# 0.5.2 M3 Node 检测与统计基础

日期：2026-10-04；分支 codex/0.5.1。状态：**M3 Node PASS OFFLINE；完整 M3 / 0.5.2 IN PROGRESS**。M2 冻结结果见 [CONTINUATION](CONTINUATION.md)，不能用于本页后续修改；本阶段由 [SOURCE_INPUTS_M3_NODE](SOURCE_INPUTS_M3_NODE.json) 的113个产品/测试/构建输入绑定。

新增纯函数 anomalies.py：rolling median/MAD、20 个先前正常样本且跨度 ≥540 秒、最多 60 样本/1h、缺测 >90s 重建基线；NETWORK_RATE_ANOMALY 阈值 max(1MiB/s, 4×median, median+6×MAD)，ACTIVE 恢复要求 <85% 阈值。spike 不训练自身；异常持续到基线过期为 UNKNOWN 并保留 ACTIVE，不把持续异常重新学成正常。摘要包含值、样本数/跨度、median/MAD、阈值、缺测/冷启动等固定原因；原始 baseline 只保存本地私有 evaluation，不输出 UI/CLI。

SERVICE_RESTART_LOOP 由相同 installation/boot 的连续 NRestarts 差值判断：300s 内 ≥3 次 automatic sing-box restart；计数下降、缺值、跨 boot/instance、采样间隔 >90s 为 UNKNOWN/RESET。正常窗口恢复闭合 Finding；确定 counter 增长增加 SERVICE_RESTART Timeline 事件，覆盖服务仍 active 的重启。新两个 detector 使用既有事务/稳定 id/UNKNOWN 不关闭生命周期，不触发 SSH 或 mutation。

初始 Windows Python 94 项出现一个新用例失败：用例在同一 evaluated_at 先写缺测再写恢复，按既有去重规则后者正确被忽略。已改为后续时间的恢复样本，保留业务时间单调规则；随后增补长期异常基线过期用例。Windows 完整 **95 项，89 PASS / 6 Linux 平台 skip，0 failure/error**。

tests/test_anomalies.py 九项覆盖正常波动、median/MAD evidence、hysteresis、持续300s、缺测/冷启动/样本跨度/回放、绝对 idle floor、恶意 baseline/非数值、异常基线过期、restart loop/恢复/reset、reboot/instance/stale/missing、跨进程持久化/未知/去重/恢复/私有状态、纯函数零 mutation（部分项在同一测试内）。打包成员与全量 Bash 入口已纳入新库/套件。

## 最终离线结果

| 检查 | 实际结果 / 证据边界 |
| --- | --- |
| WSL Ubuntu 24.04 root Python | **95/95 PASS，0 skip**，含Linux权限与socket测试 |
| WSL 全量 Bash/Fleet | **All 1869 tests passed**，新增统计子套件纳入；含1000次fake-SSH，不是VPS Live |
| Node/Controller 构建与 lock/digest | PASS；固定SOURCE_DATE_EPOCH=1790679997；Node stamp仍0.5.1 |
| 独立ZIP黑盒 | PASS；新 anomalies.py 明确成员检查、controller.lock逐项hash、包内 CLI init/findings/timeline，空缓存读取零DB写入 |
| JS / git diff / 文档本地链接 | PASS；node --check、git diff --check，35个新增文档目标存在 |

日志、exit_code=0的RESULTS及制品保存在本机 ignored `tmp/linux-validation-20261004-m3-node/`；未上传、未新跑远端CI。起点 fabe8f1f7cb5f39606b4fa8f76d7d9d40401b4ba；当前工作树未提交/推送/发布。SHA-256：

| 制品 | SHA-256 |
| --- | --- |
| vincula-node-0.5.1.tar.gz | 754a02015c90f664c180872e7d94bf73bacbd5a4c42170ddde284980df6d4edf |
| vincula-controller-0.5.1.zip | 124c716cd36fa9bfa8b15da2f7ede5618c2887aa47a2af738d0d34617d0ba426 |
| payload-manifest.json | e3c73b75a3d9fa385aa46e21ed38a02de362acf8634547ca2b5d878ce4b4c032 |

尚需完成：真正的用户级采样、USER_TRAFFIC_SPIKE / USER_CONNECTION_SPIKE / SUSTAINED_TRAFFIC_ANOMALY；其采样不能来自 Node 总量或将仅关闭连接的累计 export 当即时时序。[待实现采样设计](../../specs/V0.5.2_User_Sampling_Design.md)已核对底层数据语义，仍是设计而非实现。generic series 的持续时长支持目前只验证算法，不表示这些用户 detector 已交付。M4 正式 Findings/Timeline schema 与全量候选仍待实现。

**Human Gate H05/H06/H07：PENDING HUMAN；真实资源、网络/重启、用户负载、service disruption 与 soak：PENDING LIVE；本轮跳过并记录。**不把 fixture 对照替代 VPS 验收。
