# 0.5.3 Observation RC soak

**2026-10-11 状态：突发腿（1000× telemetry + 节点状态增长）PASS LIVE；24h 连续观测腿完成，实测 95,597 s（26h33m）；代理与 inspect/drift 两个维度未覆盖；生产未改动 4/4。** 现场执行见下方[阶段 C（2026-10-10）](#阶段-c2026-10-10)；H05 仍未开始，本页不替代人工签署。

---

## 历史：准备记录（2026-10-05）

日期2026-10-05。**NOT RUN / PENDING LIVE / UNRELEASED**。本地0.5.3 RC见[RC](RC.md)，现场未启动；按 [用户延期指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)跳过24h人工现场等待，继续实现。1000次fake-SSH是离线回归，不是24h soak。

AC-5.3-05需固定Node/Controller版本、制品SHA、源码manifest、OS/架构、Node数量、实际proxy client路径、账户身份、monitor/probe/inspect间隔和UTC窗口。连续至少24h覆盖 monitor→health→finding→inspect→timeline；包含Drift/UNKNOWN/恢复和混合Node降级，并关联 [LIVE](LIVE.md) 的accountd/observer实际权限验证。

保留采样原始记录：真实代理成功/失败与断流窗口；sing-box/accountd/observer service active/restart/RSS/FD；telemetry/poll/heartbeat/inspect freshness与失败计数；数据库大小、retention/capacity/truncation与锁/写失败；Finding生命周期/Timeline与baseline来源。业务流量自然增长与只读副作用分开核对；缺关键指标不填PASS。

起止UTC、候选SHA、拓扑、测量、故障、恢复、最终service active、原始日志hash与结论全部 **PENDING**。soak失败或中断须保留失败记录，不能将离线时长或分段总时长换算为连续24h。

H05另见 [HUMAN_ACCEPTANCE](HUMAN_ACCEPTANCE.md)；本页不替代人工签署，也不授权发布。

---

## 阶段 C（2026-10-10）

分支 `codex/0.5.1`，冻结候选见[冻结候选](CANDIDATE_FREEZE.md)（Node `8abe989c…`、Controller `65dbcc7b…`、`vcl-fleet 0.5.3`），采集器 [tools/phase-c.sh](tools/README.md)。

### 固定输入

| 项 | 值 |
| --- | --- |
| 候选校验 | Controller ZIP sha256 == `65dbcc7b…`（准备段逐次校验） |
| 拓扑 | 生产工作区 `/home/marz/vincula-fleet-live`，`fleet_id 1633b697…`，七台混合版本 Node |
| 隔离 | 生产工作区/状态/绑定**取副本**（`fleet.db` 在线备份 2,101,264,384 B），生产根只读；准备时生产 Controller 进程为空 |
| 参数 | 突发 `SOAK_NODE=neptunespear --iterations 1000`；24h `monitor --interval 60 --inspect-interval 300 --concurrency 2 --timeout 60`；采样器 300 s |
| 代理探测 | **未启用**（执行人 2026-10-10 决定：不在生产 Node 新增 `vcl-probe-*` 测试用户）→ 代理维度未覆盖 |
| 隔离根 | `/home/marz/vcl-phase-c-20261010T023206Z` |
| 窗口起点 | `$C_ROOT/window.start`（突发结束后立即启动 monitor；突发自身耗时 5,666 s） |
| 准备段 | `PASS=8 FAIL=0` |

### 突发腿：1000× telemetry + 状态增长 — PASS LIVE

| 指标 | 观测 | 判据 | 结果 |
| --- | --- | --- | --- |
| 迭代 | ok=**1000**，fail_at=0，elapsed=**5,666 s** | 1000/1000 | PASS |
| `/var/lib/vincula` 字节 | 812,051,744 → 812,756,256（Δ +704,512） | ≤16 MiB | PASS |
| `accounting.db` 字节 | 795,242,496 → 795,947,008（Δ +704,512） | ≤16 MiB | PASS |
| 目录文件数 | 3 → 3（Δ 0） | ≤+8 | PASS |
| 日志目录文件数 | 0 → 0（Δ 0） | ≤+32 | PASS |
| sing-box `NRestarts` | **0 → 0** | 必须相等 | PASS |
| accountd `NRestarts` | **0 → 0** | 必须相等 | PASS |
| sing-box / accountd active | active / active | 必须 active | PASS |
| sing-box RSS | 262,668 → 262,020 KiB（Δ −648） | ≤+64 MiB | PASS |
| accountd RSS | 71,896 → 71,896 KiB（Δ 0） | ≤+64 MiB | PASS |
| sing-box FD | 98 → 108（Δ +10） | ≤+256 | PASS |
| accountd FD | 8 → 8（Δ 0） | ≤+256 | PASS |

`soak=PASS`、`state_growth=PASS`、**`outcome=PASS LIVE`**：1,000 次高频遥测读取未造成服务重启、文件/FD/RSS 退化或目录膨胀；唯一增长是 accounting 数据本身（约 0.7 MB），与业务写入一致。Digest `summary_sha256=31322260679765cc05959c2a88cf220c0e81ed6160a88f7ef848812a4d4ccfeb`。

### 24h 连续观测腿 — 完成（实测 95,597 s = 26h33m）

窗口：`2026-10-10T04:07:24Z`（`window.start`）→ `2026-10-11T06:40:41Z` 收尾，**实测 95,597 s ≥ 86,400 s**（超出部分同属连续窗口，未做折算）。采样器 319 行（04:07:24Z → 06:39:50Z），**三个 cache-only 视图（health/findings/timeline）非零退出 0 行**。

| 节点 | 样本数 | 跨度 s | 最大间隔 s | 覆盖率 | 尾部空档 s |
| --- | --- | --- | --- | --- | --- |
| upperhand（0.3.1-rc2） | 1393 | 86,332.5 | 71.6 | 0.969 | 0.0 |
| urgentfury（0.3.2） | 1382 | 86,362.8 | **259.7** | 0.960 | 0.0 |
| fresh050 | 1366 | 86,386.9 | 76.0 | 0.949 | 0.0 |
| neptunespear | 1316 | 86,399.5 | 80.5 | 0.915 | 0.0 |
| eagleclaw | 1308 | 86,385.4 | 74.0 | 0.909 | 0.0 |
| epicfury | 295 | 86,122.8 | 304.1 | 0.206 | 0.0 |
| hot-beam-1 | 294 | 86,116.2 | 304.0 | 0.205 | 0.0 |

| 维度 | 观测 |
| --- | --- |
| 遥测/健康连续性 | 五台可达节点覆盖率 0.909–0.969、最大间隔 ≤80.5 s（判据 2.5×60 s=150 s）✓；`urgentfury` 出现一次 **~259.7 s** 的瞬时间隔（≈连续两次失败退避），覆盖率仍 0.96，记为观察项 |
| AUTH_FAILED 两台 | 294/295 样本、覆盖率 ~0.206、间隔 ~304 s（退避上界）——FR-01 缺口下的监控盲区，与阶段 B 一致 |
| 缓存/DB 增长 | `fleet.db` **Δ0**；`observation.db` **+12,177,408 B（≈11.6 MiB / 26.5h）**；`findings.db` +98,304 B；`inspection.db` **Δ0** |
| 行增长 | `audit_events` Δ0、`daily_usage` Δ0（monitor 不做审计同步，故生产缓存内容未被改动） |
| 写失败/锁 | 收尾 `monitor --once`：`sampled_nodes=7`，`cache_write_errors=0`、`finding_write_errors=0`、`inspection_write_errors=0`；采样器 319 行全部退出 0 |
| 发现 | OPEN **0 → 6**（类型与生命周期待证据文件补录；类型决定能否覆盖 `SYNC_LAG`/`EXPORT_GAP`/`ACCOUNTING_DB_CORRUPT` 等判据） |
| 代理 | 七台 × 319 行全部 `UNKNOWN`（按执行人决定未配置探测，记录为**未覆盖**） |
| inspect/drift | `inspection.db` 窗口内 **0 事件、Δ0 字节** → 该维度**无数据**（新增待办：确认无 `probe-profiles` 时检查轮是否被整体跳过） |
| 生产未改动 | 工作区/四库/绑定指纹起止 **4/4 unchanged** |
| bundle | `…-phaseC.tgz` sha256 `3790a83125a29a76f8ba5cac52d39c5c466df6b1ee0b8e94b518f9441589338a` |

**F-4 结论（阶段 B 的遗留问题）**：本窗口每台节点 `tail gap = 0.0 s`（收尾时停止 monitor 后立刻读取 health），且 26.5h 内 `inspection.db` 无任何事件 → 阶段 B 的"尾部 814 s + 全节点 UNKNOWN"确认为**采集器时序假象**（第一次 collect 停止 monitor 与其报告崩溃、第二次 collect 才成文，间隔 13 分钟；真实停止只差 34 s），不是候选缺陷。详见[阶段 B 记录的更正](PHASE_B_FLEET.md)。

**待补（证据文件到位后填写）**：6 条 finding 的类型/生命周期与 `timeline` 事件统计、`C4-health.json` 的收尾新鲜度、`C-samples.jsonl` 中 `urgentfury` 瞬时间隔窗口的 `observation_state` 与 `restart_count` 序列、bundle/证据文件哈希。

### 限制

- 代理维度未覆盖：未配置 `probe-profiles/v1`，`proxy` 预期 `UNKNOWN`；真实业务流量只能由 telemetry 的 rx/tx、连接数与[阶段 B](PHASE_B_FLEET.md) 的 B4 数据侧面佐证。
- 突发只覆盖 `neptunespear` 一台；`epicfury`/`hot-beam-1`（`AUTH_FAILED`）与 0.3.x 两台无法作为突发目标。
- 连续 `monitor` 不打印 stdout（只有 `--once` 打印 `run` 计数），写失败计数只在收尾取样一次。
