# 阶段 A — Controller 隔离验证（现场执行记录）

日期：2026-10-09（Asia/Shanghai）。分支 `codex/0.5.1`，冻结候选基线 `e024d12`（冻结提交 `a13d461`，证据提交 `53c7618`）。范围：[RC 0.5.3 验证方案](../../plans/RC_0.5.3_VERIFICATION_PLAN.md) 的**阶段 A**：只验 Controller，**保留七台混合版本 Node 不动**，用隔离测试工作区跑基线、大积压、限一页续传、`sync --full` 与失败/恢复。

**EXECUTED（Controller 侧）/ PASS WITH FINDINGS / 生产指纹前后一致 / PENDING B、C、D。**本页文档提交 `0e93901` 的远端 CI（[run 37938802704](https://github.com/Marz42/vcl/actions/runs/37938802704)，脱敏快照 [REMOTE_CI_20261009_PHASE_A.json](REMOTE_CI_20261009_PHASE_A.json)）七个 job 全绿。 候选身份：Node `8abe989c…`、Controller `65dbcc7b…`（`vcl-fleet 0.5.3`）、payload `3389e3d6…`、固定输入 manifest `da84b695…`、`SOURCE_DATE_EPOCH=1791513039`，见[冻结候选](CANDIDATE_FREEZE.md)。以下结果全部来自真机现场（生产 Controller 主机、`marz` 用户、WSL），**未修改任何 Node、未改生产游标、未对生产缓存做故障注入**。

## 1. 环境与隔离

| 项 | 值 |
| --- | --- |
| 生产工作区 | `/home/marz/vincula-fleet-live`（workspace 模式） |
| 生产 `fleet_id` / revision | `1633b697-100f-44ba-bc67-acd28456d576` / 16 |
| 生产缓存 | `/home/marz/.local/state/vincula/1633b697…/fleet.db`，2,101,264,384 B |
| 生产绑定 | `/home/marz/.config/vincula/controllers/1633b697…/credential-bindings.json` |
| 隔离根 | `/home/marz/vcl-verify-20261009T052540Z`（`ws/`、`state/`、`config/`、`tmp/`） |
| 候选来源 | `dist/vincula-controller-0.5.3.zip`，sha256 = `65dbcc7b4ae19cfa480698ee2616ad67f43632460986ecae72ae89cfce0137a7`（每次运行前校验） |
| 磁盘 | 隔离根所在卷余量 943 G |

隔离守卫（脚本硬断言）：隔离 `VCL_FLEET_HOME`/`VCL_FLEET_LOCAL_STATE`/`XDG_CONFIG_HOME` 与生产路径不相等，否则 `exit 2`；Controller 一律从冻结 ZIP 解包运行。

## 2. A0–A4：候选校验、隔离导入、绑定、只读基线

| 步骤 | 结果 |
| --- | --- |
| A0 候选校验 | ZIP 摘要 == 冻结值；解包后 `vcl-fleet version` = `vcl-fleet 0.5.3` |
| A1 生产导出（只读）+ 隔离导入 | `workspace export` 成功；导入后 `fleet_id` 一致、revision 16 → 17 |
| A2 隔离绑定 | 6 个 ref 全部绑定成功（`admin-default`、`observe-default` + upperhand/urgentfury 各 admin/observe）；绑定只写隔离 `XDG_CONFIG_HOME` |
| A3 只读基线 | `probe`/`verify` exit 1（两台 AUTH_FAILED），`status` exit 1（`verify` 写入的 `last-status.json` 被 cache-only `status` 读到）；`A3-status.err` 为空 |
| A4 能力矩阵 | 逐节点 `capabilities --json` |

七台现场基线：

| 节点 | SSH | reason | 版本 | proxy | accounting | capabilities |
| --- | --- | --- | --- | --- | --- | --- |
| neptunespear | OK | – | 0.5.0 | OK | OK | OK |
| fresh050 | OK | – | 0.5.0 | OK | OK | OK |
| eagleclaw | OK | – | 0.5.0 | OK | OK | OK |
| epicfury | **AUTH_FAILED** | **AUTH_LIMIT** | – | UNKNOWN | UNKNOWN | AUTH_FAILED |
| hot-beam-1 | **AUTH_FAILED** | **AUTH_LIMIT** | – | UNKNOWN | UNKNOWN | AUTH_FAILED |
| upperhand | OK | – | **0.3.1-rc2** | OK | OK | UNSUPPORTED |
| urgentfury | OK | – | 0.3.2 | OK | OK | UNSUPPORTED |

凭据作用域（A2 生成时读出的生产注册表事实）：`neptunespear` 用 `admin-default`/`observe-default`；`fresh050` 只有 observe ref；`upperhand`/`urgentfury` 各有独立 recovery ref；**`epicfury`、`eagleclaw`、`hot-beam-1` 完全没有 ref**（回落到 OpenSSH 默认身份），其中两台因此达到认证上限。这是既有 FR-01/D28 缺口在现场的表现，见 §7 F-2。

## 3. FR-03 / FR-04 现场实证

两条 AUTH_FAILED 的 `ssh_detail` 与 `capabilities_detail`（原文）：

```
SSH authentication failed: the server exhausted its allowed authentication attempts
```

老 Node（0.3.1-rc2 / 0.3.2）的 `capabilities_detail`（原文）：

```
ERROR: Unknown command: capabilities. Run 'vcl help'.
```

对全部含远端文本的字段做了泄漏扫描（IPv4、`port N`、UUID、`Connection refused`、`permission denied|publickey|too many authentication`）：**全部 flags 为空**。即：

- AUTH_LIMIT 被分类为 `AUTH_FAILED` + `reason=AUTH_LIMIT`，摘要是固定模板，**未回落 admin**（同一次运行中其它节点的 admin ref 可用）；无端点、无逻辑身份、无远端 stderr 原文；
- 老 Node 的"未知命令"属**非 transport 的远端命令诊断**，按既定范围保留（不含端点/身份/密钥）；若要连这类文本也模板化，属新的候选改动。

## 4. A6/A7/A8：大积压、限一页续传、`sync --full`

参数：`--page-size 5000 --max-pages 300 --timeout 60 --stdout-cap 16777216 --budget 3600`。

| 观测 | 值 |
| --- | --- |
| 完整追平（一次连续运行） | **254 页 / 1,269,177 行 / 1091 s（≈18 分钟）**，`ok`，退出码 0 |
| 另一次完整追赶（`sync --full` 内） | **234 页 / 1,165,175 行 / 1081 s**，随后写快照 |
| 大积压节点保留窗口总量 | **1,280,175 行**（最终 rows == cursor；隔离缓存 674,844,672 B） |
| 默认 `--budget 3600` | 未成为限制（最大节点耗时 1091 s）；默认预算对当前最大节点足够 |
| 单页首批耗时 | 登录 + 建库 + 首页 ≈5 s；稳态 ≈4.3 s/页（5000 行/页） |
| 限一页 | `--max-pages 1` → `PARTIAL/more_pending/PAGE_CAP`，1 页 5000 行，游标 0→5000 |
| 续传链 | `0 → 5000 → 10000 → 15000 → 115000 → … → 1,280,175`（每一步都从上次提交游标继续） |
| `sync --full`（追平后） | `operation=sync_full`、`ok`、`node_ok=true`、`synced_at` ≥ 本次运行开始（fresh）、58 s；期间新增 1 行（节点是活的） |
| `sync --full`（未追平） | 先追赶 234 页再写快照，同样 `ok`、`synced_at` fresh |

注：`verify --json` 的顶层 `ok=false` 是**全 Fleet** 结果（含两台 AUTH_FAILED），与 neptunespear 无关；报告已分列 `node_ok` / `fleet_ok`。

## 5. A9：失败与恢复（真机，全部有确切文本）

| 场景 | 结果 | 游标 |
| --- | --- | --- |
| 页超时 `--timeout 1` | `error / TIMEOUT / audit_export`，0 页 | 5000 → 5000（守住） |
| 超量页 `--stdout-cap 1024` | `error / OUTPUT_LIMIT / audit_export`，0 页 | 5000 → 5000 |
| 页前预算 `--budget 2` | `more_pending / BUDGET_EXHAUSTED / audit_export`，0 页 | 5000 → 5000 |
| 导入期锁（持锁 > 剩余预算） | `more_pending / BUDGET_EXHAUSTED / audit_import`，0 页，**该页回滚** | 10000 → 10000（三次复现） |
| 连接期锁（先锁住缓存再启动） | **竞态**：竞争获胜时 `vcl-fleet: cannot initialize fleet.db: database is locked`，exit 1、无节点行；竞争失败时正常提交并继续 | 另见 F-1 |
| 运行中 SIGINT（8 s） | 子进程 `rc=-2`（被信号杀死），中断前已提交 1 页 | 10000 → 15000，`interrupt_effective=true` |
| 中断后续传（限 20 页） | `more_pending / PAGE_CAP / audit_export`，20 页 100,000 行 | 15000 → 115000（从被中断游标继续） |

失败模板原文（每步泄漏扫描均为空 flags）：

```
reached the per-node page cap (1 pages); audit data is still pending
SSH transport timed out
SSH response exceeded the configured size limit
reached the per-node run budget (2s); audit data is still pending
reached the per-node run budget during import; the page was rolled back
reached the per-node page cap (20 pages); audit data is still pending
```

**不变式（每一步）**：运行起点游标 == 上次提交游标；`max(export_seq) <= cursor`（不存在游标之后的半页）。五轮现场运行全部成立。

## 6. A10：生产未改动

每轮运行前后对生产做指纹：工作区文件与凭证绑定的 sha256、`fleet.db` 的 size+mtime（默认 `HASH_PROD_DB=0`，因为生产 Controller 在写，逐字节哈希会误报）、全量 size/mtime 列表。**五轮全部 4/4 一致**（ws / db / bindings / sizes+mtimes）。回退边界：删除隔离根即可，生产无需任何恢复动作。

## 7. 发现与待办

- **F-1（候选缺陷，低）连接期的锁不在预算内。** 缓存被独占锁住且连接竞争失败时，`sync` 在 `open_cache_for_sync` 阶段直接退出：`cannot initialize fleet.db: database is locked`，exit 1、**无机器可读节点行**；预算只覆盖导入与快照事务，初始 connect/schema init 走 SQLite 默认 `busy_timeout`。表现是**竞态**（同一命令多次运行结果不同），消息干净、无部分写入。已记入[可靠性待办](../../plans/Fleet_Recovery_Reliability_Backlog.md)。
- **F-2（既有 FR-01 缺口，中）生产仍有节点依赖默认身份。** `epicfury`、`eagleclaw`、`hot-beam-1` 无任何 ref，`fresh050` 只有 observe ref；两台因此 AUTH_LIMIT。修法是给每个节点显式 admin/observe ref（新候选范畴），已记入待办。
- **F-3（范围边界，记录）老 Node 的远端命令诊断保留原文。** `capabilities` 对 0.3.x 返回 `UNSUPPORTED` 且 `detail` 携带老 Node CLI 自身消息（无端点/身份/密钥）。当前按"非 transport 的远端诊断保留"处理；是否模板化留待后续候选决定。
- **A5 未做定向 `AUTH_DENIED`。** 现场以真实 `AUTH_LIMIT` 覆盖了 observe 认证失败分类与提示路径；"错误 observe 键 → AUTH_DENIED"的定向负例未单独执行，如需可在阶段 B 补。
- **未覆盖/限制**：中断仅真机执行一次（本地已另用假节点端到端验证 `rc=-2` + 续传）；连接期锁为竞态，仅一次复现 exit 1；A9d0 步骤本身不区分两种竞态结果，需按 `B3-steps.jsonl` 逐条判读。

## 8. 采集器与归档

现场采集器未入库（`scripts/` 属冻结输入集，提交会改变候选身份），只放在 `tmp/`：

| 脚本 | sha256 |
| --- | --- |
| `tmp/where-is-production-workspace.py` | `4179d6346ecc6ea5587b4c6cfe147f7bb4897617e4b058d4c66237e9d38b7147` |
| `tmp/phase-a-batch1.sh` | `20c58ffa83ad6a1c700da5019c95d228f860b9bf79aa661564514bb5949e2f5c` |
| `tmp/phase-a-batch3.sh` | `9aaabc24864257abc5651913e307ab968c5f2aea0dff5d597a9a6d7faf6141e7` |

现场原始证据不入库：`/home/marz/vcl-verify-20261009T052540Z/`（`evidence/A1-A4-summary.{md,json}`、`A1-nodes.txt`、`A2-refs.json`、`B3-summary.md`、`B3-steps.jsonl`、`B3-A6.json`、`batch.log`/`batch3.log`、`*-phaseA*.tgz` 及其 sha256）。本页只记录脱敏后的结论与确切错误模板文本。

**下一步**：阶段 B 需在生产工作区做只读对照（`probe`/`verify`）并轮换七台；`--max-pages`/`--page-size` 默认值已由本阶段实测覆盖最大节点。阶段 C（24h soak）与阶段 D（H05 人工签署）仍未开始。
