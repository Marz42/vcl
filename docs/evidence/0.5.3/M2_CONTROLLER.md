# 0.5.3 M2 — Controller Inspect / Baseline / Drift

日期2026-10-05；IMPLEMENTED。完整测试、固定输入与制品以[RC](RC.md)为准。M1历史输入独立保留，不覆盖当前源码。

已接入前台monitor：inspect默认300秒，telemetry默认30秒，每Node共享15秒capability/telemetry/audit/users/inspect/identity deadline。独立inspection.db与写失败计数，Inspect失败保留有效telemetry；不将64KiB snapshot复制到raw/rollup。缓存CLI/API/UI均不SSH，默认Fleet摘要、指定Node提供脱敏snapshot。

显式基线接受需snapshot SHA；事务重查endpoint/current instance/freshness/coverage/CAS，当前telemetry身份read transaction保持至CAS提交。基线与BASELINE_ACCEPTED/BASELINE_CLEARED事件同事务；只表示LOCAL_ACCEPTED。首次采集不接受，UI无接受动作。baseline clear需baseline SHA。容量不驱逐已接受baseline。

七分项比较产生七类DRIFT_*，复用稳定Finding生命周期；UNKNOWN保留ACTIVE，MATCH才恢复。缺基线/失测/陈旧/未来偏差/重放/换instance/endpoint变化均不假MATCH；已知Drift优先于其他分项未知。重接受基线记录独立事件，不能称作文件修复。

测试覆盖真实受管文件的非secret变化/恢复与secret rotation；SHA预览后样本变化、缺项/重复项、instance/endpoint、更换凭据reference、锁/容量/坏行/secret注入、baseline事件失败的同事务回滚、cache-only CLI及真实HTTP GET；监控低频/共享deadline/写失败隔离；Drift ACTIVE→UNKNOWN→RESOLVED稳定id。Findings新增Node/总Finding容量拒绝，保留已有ACTIVE，物理schema2兼容。

公开合同inspect-cache/v1、baseline/v1、findings/v2、timeline/v2、monitor/v3，固定正反fixtures；v1未改写。SQLite latest/baseline各1024，DB128MiB，.1秒锁等待，1秒/200万VM步；latest7天、baseline显式保留，events1万/90天。接受必需两service、三version与16唯一完整fingerprint和未截断listeners。

真实OS/observer权限、人工listener/config/unit drift恢复及24h soak PENDING LIVE；H05/H06/H07 PENDING HUMAN。本页不填生产PASS，不授权apply/发布。
