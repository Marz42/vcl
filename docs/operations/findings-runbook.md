# Findings 与本地时间轴（0.5.2 开发候选）

适用当前 `codex/0.5.1` 分支的0.5.2候选，未发布。包含14类Node/User Finding与独立审计/用户采样；合同见 [SPEC](../specs/V0.5.2_Spec.md)，实际验证范围见 [M4](../evidence/0.5.2/M4.md)。Human Gate与实机保留PENDING，本轮跳过等待。

## 采集与读取

已有 Fleet registry 和 observe 身份时，按[monitoring runbook](monitoring-runbook.md)运行 monitor；它会在 telemetry 提交后更新本地 Findings。只读查看：

```bash
python3 bin/vcl-fleet findings --state ACTIVE --json
python3 bin/vcl-fleet findings myvps --json
python3 bin/vcl-fleet timeline myvps --limit 100 --json
```

有旧 observation 缓存、暂不启动 monitor 时，可显式重分析已有本地数据：

```bash
python3 bin/vcl-fleet findings --refresh --json
```

`--refresh` 不从节点获取新数据。无 observation/cursor 时检测为 UNKNOWN；默认 Findings/Timeline 查看与 UI 两页不创建或刷新缓存，不发起 SSH。EXPORT_GAP/SYNC_LAG 需要已有 `sync` / `sync --full` 的 export_seq cursor；没有 cursor 不表示审计正常。

## 阅读结果

- 查看 `evaluations` 的评估时间与每项结果；历史 NORMAL 不能代替当前实况。空缓存/空列表也不表示全部健康。
- ACTIVE 表示最近确定异常；缺测/SSH 失败后的 UNKNOWN 会保留 ACTIVE，直到确定恢复。RESOLVED 后再次异常复用稳定 id，Timeline 记录重开。
- 压力 ≥90% 触发，降到 <85% 恢复。使用率 85%～90% 时已有告警继续保留，避免反复开关。
- `truncated` 表示历史受容量限制；PARTIAL 表示坏行/不可完整读取；CACHE_CORRUPT 不自动重建整库。先保存损坏证据，再由管理员处理。
- Monitor 报 FINDINGS_WRITE_FAILED 时 telemetry 仍可能已写入；检查本地磁盘/权限/锁，解决后可 `findings --refresh`。输出只保留固定错误分类。

UI Findings 展示异常、解释、数值 evidence 和各项评估；Timeline 展示本地事件。ACK/SUPPRESS、通知、自动修复/策略变更均未实现。

## 审计可信度

支持 `audit-health/v1` 的 Node 在 monitor 的同一总 SSH deadline 内追加独立诊断；旧 Node 显示 UNSUPPORTED，继续原 telemetry 监控。无需重新安装 observer key，broker 白名单随 Node payload 更新；真实升级/权限行为仍需实机验收。

Findings 的 `evaluations[].audit` 和 UI Audit pipeline 表显示观测时间/新鲜度、DB 状态、heartbeat/poll/event 年龄、export progression、counter delta、retention watermark 和已有 sync cursor。查看已有数据不增加 SSH。STATIONARY 是合法结果：export_seq 只在连接关闭后增加；长连接或空闲不应报停滞。last event age 不代表 heartbeat。

SCHEMA_MISMATCH / ACCOUNTING_DB_CORRUPT 表示确定诊断；UNKNOWN/超时不表示损坏，也不关闭已有异常。EXPORT_SEQUENCE_REGRESSION 表示同安装 counter 回退，需管理员检查备份/恢复/数据库来源；诊断不会自动修改 DB。回放/回退使 Accounting UNKNOWN，并保留历史高水位。恢复须取得新且有序、DB OK 的真实诊断；新 instance 会重建推进 baseline。

本分支前台 `monitor --json` 汇总输出 schema=`monitor/v2`（含 finding_write_errors）；`health --json` 和 GET monitor 保持 monitor/v1。按 schema 字段选择消费者，不能按仍为 0.5.1 的开发 stamp 假定运行汇总形状。

## Human Gate / 实机

支持user-traffic/v1的Node随monitor增加固定用户采样。用户Finding展示node/tag；逻辑user hash保持稳定，tag改名不新建告警。Query time与成功poll sampled_at均可查，冻结poll/retention删除/counter回退/重装/缺用户为UNKNOWN；统计冷启动约需10分钟正常样本。用户流量floor1MiB/s、连接floor20，median/MAD阈值与85%恢复；持续异常需300s，缺测打断待触发窗口。该流量是retained连接窗口的近似差分，不是billing counter。

Node每次最多64用户，超过为PARTIAL；不能把未列用户视为正常。Controller最多4096用户baseline，满容量标user_coverage=CAPACITY/skip数量与truncated，保留当前用户去重。只读展示不迁移库；monitor/显式refresh将findings schema1事务迁移为2，旧schema1仍可只读。新库/用户私有baseline有界，不在公共monitor/v1回显。需要迁移回旧Controller时先保存本地cache，旧代码不能识别schema2；不自动破坏整库。

NETWORK_RATE_ANOMALY 需要至少20个前置正常样本和540s跨度；UI Detection baselines 显示 COLD/MISSING/STALE/RESET 等原因与 median/MAD/阈值。原始点不回显。统计使用 rx+tx bytes/s，前后计数/boot/instance 不可比较时不补零；采样缺口>90s重新建立基线。SERVICE_RESTART_LOOP 表示300s内≥3次确定自动重启；SERVICE_RESTART Timeline 展示差值，不将 counter reset 猜为重启。手动维护抑制/通知尚待0.6阶段，不自动修复。

G4 与 24h soak 为 **PENDING LIVE**，矩阵见 [LIVE](../evidence/0.5.2/LIVE.md)。0.5.1 原实机项仍为 PENDING LIVE。

**Human Gate H05：PENDING HUMAN**，只在 0.5.3 / 0.5.x RC 收尾人工验收；H06/H07 同为 PENDING HUMAN。本轮按[用户指令](../plans/MANUAL_VALIDATION_DEFERRED.md)跳过等待并继续本地开发，实机、soak 与签署仍待人工执行。
