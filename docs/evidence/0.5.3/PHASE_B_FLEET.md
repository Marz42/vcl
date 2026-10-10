# 阶段 B — 七台混合 Fleet 生产上下文复验（现场执行记录）

日期：2026-10-09 14:21 UTC 起，窗口 10h45m22s（2026-10-10 01:08 UTC 收尾）。分支 `codex/0.5.1`，冻结候选基线 `e024d12`（冻结提交 `a13d461`）。范围：[RC 0.5.3 验证方案](../../plans/RC_0.5.3_VERIFICATION_PLAN.md) 的**阶段 B**：用冻结候选在生产上下文里跑基线对照、能力/遥测矩阵与连续观测，并复核 Node 侧只读副作用。

**EXECUTED（生产上下文、隔离副本）/ PASS / 生产指纹两轮 4/4 一致 / PENDING C、D。** 候选身份见[冻结候选](CANDIDATE_FREEZE.md)（Node `8abe989c…`、Controller `65dbcc7b…`、`vcl-fleet 0.5.3`）。采集器：[tools/phase-b.sh](tools/README.md)。

## 1. 隔离与前置

| 项 | 值 |
| --- | --- |
| 生产工作区 / `fleet_id` | `/home/marz/vincula-fleet-live` / `1633b697-100f-44ba-bc67-acd28456d576` |
| 生产缓存 | `/home/marz/.local/state/vincula/1633b697…/fleet.db`，**2,101,264,384 B**（SQLite 在线备份一致复制） |
| 观测库 | 生产侧 `observation.db`/`findings.db`/`inspection.db` **不存在**（该 Controller 从未跑过 observe 监控） |
| 运行中的生产 Controller | **无**（准备时刻 `pgrep vcl-fleet` 为空）——本次观测不与生产进程并发 |
| 隔离根 | `/home/marz/vcl-phase-b-20261009T142138Z`（`ws/` 工作区副本、`state/` 四库副本、`config/` 绑定副本） |
| 候选校验 | `dist/vincula-controller-0.5.3.zip` sha256 == `65dbcc7b…`（每次运行前校验） |
| 观测参数 | `--interval 60 --inspect-interval 300`，`--concurrency 2`，`--timeout 60` |
| 窗口 | **38,722 s（10h45m22s）**，远超 2h 目标；`MONITOR_SECONDS=7200` 仅为下限约定 |

本轮所有写入（`last-status.json`、`observation.db`、`findings.db`、`inspection.db`）都落在副本里；生产工作区、缓存、绑定只被读取。

## 2. B1/B2：生产上下文对照

| 对照项 | 结果 |
| --- | --- |
| B1 与阶段 A 的逐节点差异（`ssh`/`reason`/版本/`proxy`/`accounting`） | **无差异**（`b1_diffs_vs_phase_a: []`） |
| B2 能力矩阵与阶段 A 的差异 | **无差异**（`b2_capability_diffs_vs_phase_a: []`） |
| `probe` / `verify` / `status` 退出码 | `1 / 1 / 0`（前两者非 0 来自两台 `AUTH_FAILED`，与阶段 A 一致；`status` 在阶段 A 因空缓存为 1，这里读的是副本里真实的生产缓存，故为 0） |

B1 缓存的 Node 状态（副本里的生产数据，`status --json`，全程无 SSH）：

| 节点 | ssh | proxy | accounting | cursor | 数据年龄 | 最后同步 |
| --- | --- | --- | --- | --- | --- | --- |
| 七台（eagleclaw、epicfury、fresh050、hot-beam-1、neptunespear、upperhand、urgentfury） | OK | OK | OK | ok | 162,967 s（≈45.3 h） | 2026-10-07T17:06:51Z |

即：生产缓存自 2026-10-07 恢复窗口后未再同步；本次验证**没有**更新生产游标。

## 3. B3：10h45m 连续观测

`health`/`findings`/`timeline` 三个 cache-only 视图的 `cache_state` 均为 **OK**；窗口内 **61** 条事件。

| 节点 | telemetry 能力 | 样本数 | 跨度 s | 最大间隔 s | 期望 | 覆盖率 |
| --- | --- | --- | --- | --- | --- | --- |
| fresh050 | OK | 599 | 37,870.6 | 69.7 | 631 | 0.949 |
| upperhand | UNSUPPORTED（0.3.1-rc2） | 612 | 37,904.1 | 71.5 | 631 | 0.970 |
| urgentfury | UNSUPPORTED（0.3.2） | 610 | 37,913.4 | 70.1 | 631 | 0.967 |
| neptunespear | OK | 576 | 37,893.0 | 71.7 | 631 | 0.913 |
| eagleclaw | OK | 574 | 37,899.8 | 72.3 | 631 | 0.910 |
| epicfury | **AUTH_FAILED** | 130 | 37,817.9 | 305.5 | 630 | **0.206** |
| hot-beam-1 | **AUTH_FAILED** | 130 | 37,850.6 | 303.7 | 630 | **0.206** |

读法：

- 五台可达节点的连续性满足判据（覆盖率 ≥0.9、最大间隔 ≤2.5×60 s）。**0.3.x 两台也产生了 610+ 样本**：`telemetry/v1` 不支持只影响遥测指标，健康/探针路径照样工作。
- 两台 `AUTH_FAILED` 节点只有 130 个样本、间隔约 300 s——这是监控对失败节点的**退避**（上界 300 s），不是断流；但它们在观测上实际处于**盲区**（见 F-2）。
- 窗口内事件分类：`FINDING_OPEN` 25、`FINDING_RESOLVED` 19、`HEALTH_CHANGE` 14、`SERVICE_CHANGE` 3（`neptunespear` 35、`eagleclaw` 9、`fresh050` 9，其余每台 2）。

### 停止时刻的 `UNKNOWN`（重要读法）

`B3-health.json` 里七台的 `health` 子状态都是 `UNKNOWN`、`overall=UNKNOWN`，并且时间线上在停止瞬间出现一批 `TELEMETRY_STALE` finding 与 `HEALTH_CHANGE→UNKNOWN`。原因是**新鲜度判定**：`lib/observation/health.py` 要求遥测年龄在 `-30..90 s` 才算 fresh，而停止时最后一次样本已约 814 s（13.5 min）之前——**这不是节点健康变化**：B4 显示服务 active、`restart_count` 0→0、`instance_id` 未变。

## 4. B4：Node 侧只读复核

| 节点 | instance 不变 | sing-box 重启 | sing-box active | accountd active | uptime 增(s) | tx 增量 | 连接数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| eagleclaw | 是 | 0 → 0 | True → True | True → True | +38,765 | +993 GB | – → 147 |
| fresh050 | 是 | 0 → 0 | True → True | True → True | +38,763 | +201 GB | 15 → 12 |
| neptunespear | 是 | 0 → 0 | True → True | True → True | +38,765 | **+5.04 TB** | 71 → 35 |
| epicfury / hot-beam-1 | 不可读（AUTH_FAILED） | – | – | – | – | – | – |
| upperhand / urgentfury | 不可读（遥测 UNSUPPORTED） | – | – | – | – | – | – |

结论：10h45m 的只读观测**没有**造成实例更替、服务重启或状态变化；`uptime` 增量与窗口一致；流量/连接为业务自然波动（`neptunespear` 约 5 TB、`eagleclaw` 约 993 GB、`fresh050` 约 201 GB），单独记录，不计入异常。

## 5. 生产未改动

两轮 collect 各做一次指纹（工作区文件与绑定的 sha256、四库 size/mtime、全量 size/mtime 列表）：**4/4 unchanged，两轮都一致**。回退边界：删除 `$B_ROOT` 即可，生产无需任何恢复动作。

## 6. 发现与待办

- **F-4（候选观测层，待定因）停止前尾部 814 s 无样本，且停止后立刻读 health 得到全节点 `UNKNOWN`。** 窗口内最大间隔只有 ~72 s，说明采样一直正常；只有**尾部**在停止瞬间前约 13.5 min 没有新样本（很可能是 `inspect_interval=300` 的检查轮正在进行，检查轮不写遥测样本），随后 `health --json` 按 90 s 新鲜度判定为 `UNKNOWN`，`findings --refresh` 因此在停止瞬间写入一批 `TELEMETRY_STALE`/`HEALTH_CHANGE` 事件。**影响**：操作者停掉 monitor 后立刻看健康面板会看到"全部未知"，时间线被这批陈旧判定污染。**未能定因**：这次 monitor 日志是块缓冲的，`SIGTERM` 时缓冲区丢失（`kept: 0 log lines`）——采集器已改为 `python3 -u`，阶段 C 会用无缓冲日志复测，届时可判定是"检查轮阻塞"还是"停止路径"。
- **F-5（数据缺口，低）**`eagleclaw` 的 B2 遥测快照缺 `connection_count`（B4 有 147），同机 `instance_id`/`restart_count` 正常。仅记录，不影响判定。
- **F-2 强化（既有 FR-01 缺口）**：两台无显式 ref 的节点在观测里只有失败样本（覆盖率 0.206、约 5 分钟一次退避），即**只要仍依赖 OpenSSH 默认身份，它们同时也是监控盲区**。已并入[可靠性待办](../../plans/Fleet_Recovery_Reliability_Backlog.md)的对应条目。

## 7. 证据与哈希

现场证据（不进仓库）：`/home/marz/vcl-phase-b-20261009T142138Z/`。

| 文件 | sha256 |
| --- | --- |
| `evidence/B-summary.md` | `c05f2215db7258f1aaf4a1d764d1497dc53454329ec3a346cc56f97ae7b96bec` |
| `evidence/B-report.json` | `6541cc23c338d0f72cca45a7bf7410afce716f31f13b56a6fdb2fdf3ba4ad217` |
| `evidence/B1-verify.json` | `e77763de3afc01c5387ce8e91c52f7e7f79f40dcc9c578285a3c71286af0b90e` |
| `evidence/B3-health.json` | `28deca36b6fe860d917f217f8c135c644b51833cbddaa97bfef9de288ec81e67` |
| `evidence/B3-timeline.json` | `be1942c0985d49c908075b1b9fda9cbfdcdf18dd51af3aaaee009763d120c1dc` |
| `batch-b.log`（在 `$B_ROOT/` 根，不在 `evidence/`） | `c68e94c832069bf4e29d6c646969afabf5f64b58e914744df987d589ce7f382f` |
| `…-phaseB.tgz`（首次 collect，报告崩溃轮，保留） | `f9d161dc8a7ddcd241afeadc95f369a73448cc001deaa0b27655a0e76fe2bb28` |
| `…-phaseB.tgz`（第二次 collect，报告成功轮） | `694920fb38c76944c0a729bbd9e14743d563360828acde590457e6b7732b1788` |

采集器版本：准备段与第一次 collect 用的是 `b5515c37bfd0aa6cec37088e8fbba16069b6cab043efea683e6bf7513bb15b64`（`a2305dd`），第二次 collect 用的是 `bd45a40945b69fc1d383be96b38581cbfa61ce0e2e7271ccd51a896654e3eb14`（`79ab23e`）。首次 collect 的报告崩溃源于采集器把循环变量命名为 `now`、覆盖了时间戳变量（`str - float`），已修并本地回归；同一次提交把 monitor 改为 `python3 -u` 以保住日志（本次 prep 启动的 monitor 是旧版，缓冲区随 `SIGTERM` 丢失）。

**限制**：本次是"冻结候选 + 生产工作区/绑定副本 + 真实七台 Node"，不是"生产 Controller 进程在跑"的场景；生产 Controller 当时未运行，也没有被替换。阶段 C（24h soak）才覆盖长时间运行的 Controller 进程本身，且仍需无缓冲日志复核 F-4。
