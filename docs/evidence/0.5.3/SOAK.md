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
| 发现 | OPEN **0 → 6**：`SYNC_LAG`×3（neptunespear/fresh050/eagleclaw）+ `NETWORK_RATE_ANOMALY`×3（同三台）；窗口内 47 次 `FINDING_OPEN` / 47 次 `FINDING_RESOLVED`（见 §发现的判读） |
| 代理 | 七台 × 319 行全部 `UNKNOWN`（按执行人决定未配置探测，记录为**未覆盖**） |
| inspect/drift | `inspection.db` 窗口内 **0 事件、Δ0 字节** → 该维度**无数据**（新增待办：确认无 `probe-profiles` 时检查轮是否被整体跳过） |
| 生产未改动 | 工作区/四库/绑定指纹起止 **4/4 unchanged** |
| bundle | `…-phaseC.tgz` sha256 `3790a83125a29a76f8ba5cac52d39c5c466df6b1ee0b8e94b518f9441589338a` |
| CI | [REMOTE_CI_20261011_PHASE_C.json](REMOTE_CI_20261011_PHASE_C.json)：run `38119205923`（`41207dc`）七 job 全绿；`446ecf2` 因并发组被取消（非失败） |

**F-4 结论（阶段 B 的遗留问题）**：本窗口每台节点 `tail gap = 0.0 s`（收尾时停止 monitor 后立刻读取 health），且 26.5h 内 `inspection.db` 无任何事件 → 阶段 B 的"尾部 814 s + 全节点 UNKNOWN"确认为**采集器时序假象**（第一次 collect 停止 monitor 与其报告崩溃、第二次 collect 才成文，间隔 13 分钟；真实停止只差 34 s），不是候选缺陷。详见[阶段 B 记录的更正](PHASE_B_FLEET.md)。

#### 发现的判读（6 条 OPEN）

| 类型 | 数量与主体 | 判读 |
| --- | --- | --- |
| `SYNC_LAG`（WARNING） | neptunespear / fresh050 / eagleclaw 各 1 | **真阳性且符合预期**：判据是"仍有未接收的导出记录且最后成功同步超过 300 s"，而副本里生产缓存最后同步是 `2026-10-07T17:06:51Z`（本轮**刻意不做 sync**），生产 Controller 当时未运行。只在这三台出现，因为只有它们能观测到审计进度（`AUTH_FAILED` 两台无法评估、0.3.x 两台 `UNSUPPORTED`）。**不是候选缺陷** |
| `NETWORK_RATE_ANOMALY`（WARNING） | neptunespear / fresh050 / eagleclaw 各 1 | 判据基于本机滚动中位数/MAD（≥20 样本、跨度 ≥540 s）；这三台正是承载真实业务流量的节点（阶段 B 的 B4：neptunespear 10.5h +5.04 TB、eagleclaw +993 GB、fresh050 +201 GB），**由业务流量波动触发**，窗口内伴随无服务重启、无资源退化。**不是候选缺陷**；但 47/47 的 OPEN/RESOLVED 往返说明这两类警告在生产流量下会反复开合（见待办） |
| 未出现的类型 | `EXPORT_GAP`/`ACCOUNTING_DB_CORRUPT`/`SCHEMA_MISMATCH`/`TELEMETRY_STALE`/`DISK_PRESSURE`/`MEMORY_PRESSURE` 均未出现 | `EXPORT_GAP`（游标过期、远端保留窗口可能缺失）**缺席** → 本轮**没有**裁剪/保留窗口丢失的证据；`ACCOUNTING_DB_CORRUPT`/`SCHEMA_MISMATCH` 缺席 → 账本与 schema 健康 |

时间线（`timeline --limit 1000`，未截断，共 175 条）：窗口内 100 条（`FINDING_OPEN` 47、`FINDING_RESOLVED` 47、`HEALTH_CHANGE` 6），其余 75 条为窗口前的历史（含 2026-10-07 的 46 条 `OPERATION`、8 条 `SERVICE_CHANGE` 等）。即 **monitor → health → finding → timeline 四段链路在本窗口都有产出**；`inspect` 段无产出（见下）。

#### 收尾健康状态与故障/恢复

| 节点 | `observation_state` | `overall` | observation | accounting | 遥测年龄 s |
| --- | --- | --- | --- | --- | --- |
| eagleclaw / neptunespear / fresh050 | OK | UNKNOWN（proxy 未配置） | **HEALTHY** | HEALTHY | 0.03 / 0.03 / 1.03 |
| epicfury / hot-beam-1 | AUTH_FAILED | DEGRADED | DEGRADED | UNKNOWN | – |
| upperhand / urgentfury | UNSUPPORTED | UNKNOWN | UNKNOWN | UNKNOWN | – |

- 三台可达节点在收尾（停止 monitor 后立刻读取）时**遥测年龄 0.03–1.03 s、observation=HEALTHY** —— 这正是 F-4"陈旧判定假象"结论的直接反证：只要读取时机紧跟样本，状态就是 HEALTHY。
- `overall=UNKNOWN` 仅因 `proxy` 未配置（`overall` 需要四个子状态全健康），与 decide 的"代理维度未覆盖"一致。
- **故障与恢复（真实发生一次）**：`urgentfury`（0.3.2）在窗口内出现一次瞬时故障窗口——采样器 319 行里有 1 行 `observation_state=ERROR`、`overall=SUSPECT`，随后 1 行 `RECOVERING`，其余 317 行 `UNSUPPORTED`/`UNKNOWN`；对应遥测序列上 ~259.7 s 的间隔（≈连续两次失败退避）。**无人工干预即自行恢复**，判定为探针/SSH 瞬时失败，不是候选缺陷；这也是本窗口"故障探测 → 分类 → 恢复"路径的现场证据。
- **服务重启**：三台可读 `restart_count` 的节点全程 `{0}`（首行 `None` 为首轮采样前的空值）；0.3.x 与 `AUTH_FAILED` 节点无遥测指标。结合突发腿 `systemctl NRestarts 0→0`（neptunespear）→ 全程无服务重启。
- 采样器自身从未停顿（相邻行间隔 >400 s 的次数为 0）。

#### 保留/裁剪与锁写判据

- `EXPORT_GAP` 缺席 + `fleet.db` Δ0 + 生产指纹 4/4 一致 → 本轮**没有**远端保留窗口丢失/本地游标过期的证据（判据覆盖），同时证明验证过程没有改动生产审计缓存。
- 锁/写失败：采样器 319 行三个视图全部退出 0；收尾 `monitor --once` 三项写错误计数全 0；无 `ACCOUNTING_DB_CORRUPT`。
- 容量：`observation.db` 26.5h 增长 ≈11.6 MiB（7 台、interval 60、含 rollup），`findings.db` +96 KiB，未见裁剪事件；无上限/裁剪阈值可判读 → 记录为**增长曲线**而非 PASS/FAIL。

### 限制

- 代理维度未覆盖：未配置 `probe-profiles/v1`，`proxy` 预期 `UNKNOWN`；真实业务流量只能由 telemetry 的 rx/tx、连接数与[阶段 B](PHASE_B_FLEET.md) 的 B4 数据侧面佐证。
- 突发只覆盖 `neptunespear` 一台；`epicfury`/`hot-beam-1`（`AUTH_FAILED`）与 0.3.x 两台无法作为突发目标。
- 连续 `monitor` 不打印 stdout（只有 `--once` 打印 `run` 计数），写失败计数只在收尾取样一次。
- **发现抖动（观察项）**：26.5h 内 `FINDING_OPEN` 47 次 / `FINDING_RESOLVED` 47 次，主体是 `SYNC_LAG` 与 `NETWORK_RATE_ANOMALY`。前者在"生产 Controller 未运行、缓存按预期陈旧"时会持续存在，后者随真实业务流量开合；对运维而言是噪声，阈值/静默与聚合方式待定（见[可靠性待办](../../plans/Fleet_Recovery_Reliability_Backlog.md)）。
- `inspect`/drift 维度未覆盖：无 `probe-profiles` 时 `inspection.db` 全程无事件、无增长，`monitor → health → finding → timeline` 四段有产出而 `inspect` 段没有；本轮不把该维度记成 PASS。
