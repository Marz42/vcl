# VCL 0.5.x～0.7.x 实施与验收方案

> 编制日期：2026-09-26。状态：实施计划；不代表功能已经实现、现场已验收或版本已发布。
>
> 规划依据：[Master SPEC](../specs/VCL_0.5-0.7_Master_SPEC.md)；0.5.0 细则以 [V0.5.0 SPEC](../specs/V0.5.0_Spec.md) 为准。
>
> 人工验收：[大阶段人工验收清单与签署记录](VCL_0.5-0.7_Human_Acceptance.md)。**0.5.x、0.6.x、0.7.x 各自收尾必须人工验收；未通过不得宣布大阶段完成或进入下一大阶段的实现。**

## 1. 起点、范围与使用规则

### 1.1 本地起点

本方案编制时核对的本地分支为 `main`，HEAD 为 `d8734eb`（`Merge release/0.5.0 as development baseline`）；编制前工作区无未提交变更。Controller 与 Node 代码版本均为 `0.5.0`，最低兼容 Node 为 `0.3.1`。这只是本地开发基线，不据此推断远端发布、tag 或当前 CI 状态。

| 项目 | 已有事实及证据边界 | 本计划处理方式 |
| --- | --- | --- |
| 0.5.0 实现 | 已有 capability/telemetry、observe 路由、SSH 封装、单节点 typed upgrade | 复用现有实现，从基线核对开始，不重新开发一遍 |
| 自动化 | [TESTS](../evidence/0.5.0/TESTS.md) 记录代码提交 `98423ed` 的 1863 项通过及制品构建通过 | 历史结果只绑定原提交；后续候选必须产生自己的 G1/CI 证据 |
| 现场与 soak | [SUMMARY](../evidence/0.5.0/SUMMARY.md)、[LIVE](../evidence/0.5.0/LIVE.md)、[SOAK](../evidence/0.5.0/SOAK.md) 已记录 L1–L5 与 1000 次调用通过；包含历史现场结果和保存快照复核 | 保留原结果与原始失败记录；保存快照复核不描述为新一次 Live |
| 升级连续性 | L2 记录一秒轮询未观察到失败，同时明确“未精确测得断流时长” | 不改写历史 PASS；为 SPEC 的 **≤3 秒**要求补专门的新连接可用性测量 |
| 安全遗留 | [SECURITY](../evidence/0.5.0/SECURITY.md)：`SEC-050-01` accountd 仍为 root；`SEC-050-02` observer forced-command 延后 | accountd 降权纳入 0.5.1；observer 白名单纳入 0.5.1，最晚在 0.5.3 收口 |
| 文档状态差异 | README/索引/CHANGELOG 与最新 SUMMARY 对“开发分支、待合并、待 Live”的描述存在差异 | 基线核对时更新当前状态入口，并以补充记录解释差异；不覆盖历史测量结果 |

本次只编制方案与验收清单，不执行升级、现场故障注入、功能开发、提交、推送或发布。

### 1.2 规范与新增执行约定

- Master SPEC 的 MUST/MUST NOT 是不可降低的门槛；每个子版本都保留 G0～G5，不因大阶段人工验收而省略子版本门禁。
- 本文标为“执行默认”的数值、人工关卡和任务安排，是为落地补充的约定。SPEC 中的 SHOULD/MAY 仍保留原等级；偏离默认须在该版本 G0 记录理由、替代判据与风险。
- 新 schema/capability 名称、CLI 参数和模块名在子版本 G0 冻结。本文的拟新增路径是建议归属，不表示现有 API 已可调用。
- 技术选型必须按 0.6.2 Research Gate、0.7.1 Transport Decision Gate 的真实结果决定，不提前假定某个 backend/transport 可用。
- 版本独立交付；不预埋长期无法验证的半成品。0.8+ 的自动路由、无人值守 failover/修复、3-hop 生产路径、分布式权威均不在范围内。

## 2. 总体顺序与阶段依赖

```text
0.5.0 基线核对与补证
  → 0.5.1 Monitor / Health / hardening
  → 0.5.2 Finding / Audit / Timeline
  → 0.5.3 Inspect / Drift / Verify
  → H05：0.5.x 人工验收
  → 0.6.0 Desired / Reconcile / LKG
  → 0.6.1 Alert / Incident
  → 0.6.2 QoS / User Policy（先 Research Gate）
  → 0.6.3 Egress / Per-user Binding
  → 0.6.4 Controlled Maintenance
  → H06：0.6.x 人工验收
  → 0.7.0 Roles / Transit Identity / ACL
  → 0.7.1 Static 2-Hop（先 benchmark + transport ADR）
  → 0.7.2 Link / Path Observation
  → 0.7.3 Primary / Backup / Manual Failover
  → 0.7.4 Path Accounting / Capacity
  → H07：0.7.x 人工验收与总收口
```

| 大阶段 | 子版本 | 交付目标 | 进入条件 | 收尾关卡 |
| --- | --- | --- | --- | --- |
| A：Observation Plane | 0.5.0～0.5.3 | 事实可信、问题可解释、观察不改变数据面 | 核对当前 0.5.0 基线 | 全链路 soak + H05 |
| B：Declarative Controller | 0.6.0～0.6.4 | 声明、计划、人工批准、执行、验证、回滚可闭合 | H05 明确 PASS | 运维/QoS/Egress 综合回归 + H06 |
| C：Programmable Data Plane | 0.7.0～0.7.4 | 静态两跳、观测、人工切换、计量不双计 | H06 明确 PASS | 两跳全链路 soak + H07 |

时间安排以门禁和测试环境就绪为依据，不在尚未完成 QoS/transport 研究前承诺固定工期。各版本内部按“合同 → 服务与存储 → Node/CLI/UI 接入 → 自动化与安全 → Live/soak → 证据收口”推进。

## 3. 每个子版本统一执行流程

### 3.1 门禁与完成条件

| Gate | 实施步骤 | 可判定的通过标准 | 证据 |
| --- | --- | --- | --- |
| G0 SPEC | 冻结子版本 SPEC、schema/capability、兼容矩阵、AC、Live Matrix、Non-Goals、数值阈值、回退方案；核对干净基线；创建版本分支，默认 `codex/0.x.y` | 每项 AC 有唯一编号、测试方法、期望值；研究前置项已完成；无会影响核心行为的未决合同 | 版本 SPEC、决策记录、基线 SHA |
| G1 Offline | 实现并跑全量回归、schema 正反例、失败注入、脱敏、制品检查 | 必需测试零失败；必需项不以 skip 代替；`git diff --check` 通过；真实 HOME/Workspace/known_hosts 不被污染；digest/manifest 通过 | `TESTS.md`、CI、构建摘要 |
| G2 Integration | 共用 service layer；混合版本；Controller/Node daemon crash；坏 cache/journal/DB row；并发/锁；幂等 | 失败被隔离、可恢复或明确 PARTIAL；不发生重复 mutation、静默提权或假成功；CLI/UI 对同一事实一致 | 集成与注入记录、兼容矩阵 |
| G3 Security | 核对 listener、进程身份、文件 owner/mode、systemd sandbox、secret 流向、管理路径 | 无未声明管理端口；observe 不能 mutation；不 silent admin/direct fallback；无 secret 落入日志/cache/journal/UI/evidence | `SECURITY.md` |
| G4 Live | 在真实 VPS 执行本版本所有必需 Live 项，保存脱敏前后状态和测量 | 每项具有实际结果且 PASS；未执行一律 `PENDING LIVE`；模拟、fixture 和人工报告明确标注来源 | `LIVE.md`、原始证据位置及摘要 digest |
| G5 Release/Soak | 候选制品固定，required CI 全绿，版本 soak，文档与兼容表收口 | 必需 G0～G4 全部通过；无 P0/P1、无未解释损坏/泄漏；证据绑定候选 SHA/digest；已记录限制 | `SUMMARY.md`、soak、发布检查记录 |
| H05/H06/H07 | 大阶段最后一个 RC 上执行人工验收与签署 | 指定人工验收人逐项检查并明确 PASS；签署绑定候选，不能由自动化代签 | [人工验收清单](VCL_0.5-0.7_Human_Acceptance.md)及实际 `HUMAN_ACCEPTANCE.md` |

大阶段最后一个子版本的 G5 先形成“技术门禁通过、待人工验收”的 RC；H 通过后才允许宣布大阶段完成。合并、tag、推送、对外发布另按实际授权执行，人工验收签署本身不等于这些动作已发生。

### 3.2 全程保持的不变量

| 约束 | 落实与重复验证位置 |
| --- | --- |
| Controller 唯一权威，Node 不传播控制状态；Controller 离线保留 LKG | 全版本；H05/H06/H07 均断开 Controller 检查真实用户连接 |
| observation/accounting/UI 故障不停止 sing-box；只读命令不修复 | 0.5.1～0.5.3、0.7.2；比较受管文件 hash/mtime、服务重启计数及真实代理结果，排除正常业务计数增长 |
| typed mutation；stage → validate → activate → verify；LKG 可恢复 | 沿用 0.5.0 upgrade 事务；0.6.0 建统一事务；后续所有 mutation 复用 |
| 无 generic exec；无隐式权限回退；默认无新增公网管理 listener | observe/operator/admin 分离；0.7 transit 只可新增明确声明并受 ACL 约束的数据面 listener |
| secret 不进入普通日志、telemetry、Workspace 明文、Fleet cache、journal、Finding、UI API、证据 | 每版 G1/G3；新 secret 类型必须加入反例 fixture 与扫描面 |
| 状态有界且损坏行为明确 | G0 列出 Node/Controller 每个 store 的 retention、size/row cap、清理所有权、满盘/坏行处理；G1/G2/G5 验证 |
| 能力协商决定可用功能；不强制全 Fleet 升级 | 0.5.x 对旧 Node 缺能力显示 UNSUPPORTED；0.6 旧 Node 不参与不支持的 reconcile mutation；0.7 Path 编译拒绝缺 capability 的节点 |
| Egress/Path 默认 fail-closed；不自动改变策略 | 0.6.3～0.7.4；故障时检查实际出口与新连接，不仅检查生成配置 |
| 业务通过 Application/Fleet Service 进入 CLI/UI | 新业务从入口拆出；UI GET 只读本地 cache，禁止为展示临时 SSH/probe |

### 3.3 默认测量口径

- **执行默认：** H05、H06、H07 各自要求固定 RC 连续 **24h** 综合 soak；0.5.1 采用 SPEC 推荐的 24h；0.6.1 和 0.7.1 的 24h 是 SPEC 门槛。相同候选且覆盖矩阵一致的 soak 可复用，须逐项映射。
- monitor 默认 **30s** interval；建议 timeout **5s**、最大并发 **8**、jitter **±10%**、指数退避上限 **300s**，后三类数值为执行默认，G0 冻结。10 个模拟节点含 1 个超时节点时，健康节点采样不能跨过下一次调度周期；不得因重试叠加形成无界队列。
- telemetry 保留 SPEC 的 **≤64 KiB** 和低配 VPS **p95 ≤2s**目标；分别记录 Node 命令耗时与端到端 SSH 耗时，不把 1000 次 soak 的总耗时除以次数当作 p95。执行默认至少 100 次有时间戳样本，超标解释计入 G0/发布偏差记录。
- retention 采用 SPEC 推荐的 raw **24h**、5m rollup **7d**、hourly **90d**；用推进时钟 fixture 验证长周期清理，再用 Live 检查增长趋势，不能声称 24h soak 已实测 90 天。
- 未给绝对预算的性能项采用同机器/拓扑/负载的 A/B 样本，记录基线、环境与干扰。QoS、SOCKS、transport 的具体判断见对应版本；选型前不得标 production-ready。
- 所有 Live 故障注入先固定测试目标、维护窗口、备份与恢复步骤；由执行者显式触发。代理成功以真实新连接/HTTPS/UDP 等任务结果判断，`systemctl active` 或配置文本不能替代数据面证据。

## 4. 阶段 A：0.5.x Observation Plane

### 4.1 0.5.0：复用 Observation Foundation，核对基线与补证

**依据：** Master §7.1；V0.5.0 SPEC 的 AC-5.0-01～14。**产出：**可继承的开发基线、遗留事项表、补充 Live 记录。

实施顺序：

1. 对齐本地 HEAD、代码版本、候选制品 source/epoch/digest、当前入口文档和既有 evidence；分别标记代码已合入、历史验收、未核对的远端状态。
2. 复核 capability/telemetry schema、unknown capability 保留、malformed/oversize fail-closed、identity 绑定和 observe/admin 路由；已有实现通过回归保留。
3. 沿用 `node upgrade plan/apply`，核对 0.3.1/0.3.2 升级 allowlist、identity/URI/accounting 不变量及失败回滚；不把 fleet upgrade 扩展提前放入本版本。
4. 补 ≤3 秒测量：对两个来源版本分别准备可恢复节点，在整个 upgrade 窗口连续建立真实代理新连接。执行默认采样间隔 ≤250ms，保存单调时间、成功/失败、timeout 和测量空窗；报告最坏不可用上界。无失败时报告“采样未观察到失败”和分辨率，不宣称零断流；有空窗或不能给出 ≤3 秒上界时保留 `PENDING LIVE`。
5. 保留 1000-call soak 与其原始失败/复核链；登记 `SEC-050-01/02` 的完成版本和验证办法；按改变的代码范围补测，不重写历史 PASS。

| 验收项 | 通过标准 |
| --- | --- |
| 原合同 | AC-5.0-01～14 有对应证据；fixture/Offline/Live 不互相代替 |
| 升级连续性补证 | 0.3.1、0.3.2 → 0.5.0 实测可用性上界 ≤3s，身份、客户端 profile 和 accounting 连续；长连接允许重启断开但明确记录 |
| observer 边界 | 独立 observe 成功；撤销后 AUTH_FAILED，零 admin fallback；mutation 使用 admin |
| soak 与兼容 | 至少一真实 Node 1000 次 telemetry 无失败/泄漏，资源检查完整；旧 Node 缺能力为 UNSUPPORTED，旧管理能力可用 |
| 基线交接 | 版本/证据状态差异有解释；安全遗留纳入 0.5.1/0.5.3；不得把“documented blocker”改写成已降权 |

**推进规则：**已有合入的 0.5.0 可以作为 0.5.1 开发输入；补证与文档差异最晚在 H05 前闭合。此安排不豁免 ≤3 秒要求，也不撤销已保存的历史验收结论。

### 4.2 0.5.1：Monitoring & Health，完成基础 hardening

**依据：** Master §7.2、§12.1；`SEC-050-01/02`。**依赖：**0.5.0 已有 capability/telemetry/credential 路由。

实施顺序：

1. 冻结 Health 状态机、时间戳/缺测语义、probe 独立身份、监控调度预算、数据库迁移与 retention。
2. 实现前台 `monitor [NODE]` 调度：timeout、并发上限、jitter、退避、单节点隔离、退出/重启恢复。
3. 实现 samples、5m/hourly rollup、清理和坏行容错；分别计算 Node、Observation、Proxy、Accounting Health，并附可解释原因。
4. 实现专用身份的 VLESS/Reality → 已知 HTTPS 端点 probe；记录 success、connect latency、HTTPS/TTFB、observed_at。
5. 完成 accountd 独立 service user、非 secret identity mapping、最小权限 Clash credential 注入、目录权限迁移与 systemd sandbox；迁移失败安全回退。实现 observer no-sudo/no-PTY/no-forwarding 与只读命令白名单。
6. CLI/UI 接入共享服务和本地 cache，展示健康、年龄、负载、资源、连接、网络速率与服务/probe 状态；执行故障矩阵与 soak。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-5.1-01 | 10+ 模拟节点通过调度/退避/并发测试；单节点超时不阻塞健康节点；crash/restart 无重复失控任务 |
| AC-5.1-02 | HEALTHY/SUSPECT/DEGRADED/UNREACHABLE/RECOVERING 转移与 G0 阈值一致；进程存活但 HTTPS 失败不能显示 Proxy HEALTHY |
| AC-5.1-03 | raw/rollup retention、满盘/坏行/重启用例通过；无数据时显示未知/缺测，不能填造正常值；UI GET 零 SSH |
| AC-5.1-04 | accountd 以非 root 运行，所需读写正常且不能读取 Reality 私钥/用户 credential；observer 任意 shell、sudo、mutation、转发均被拒；破坏 observe 不回退 admin |
| AC-5.1-05 | ≥10 Node 的真实或受控混合矩阵以 30s interval 运行 ≥2h，明确真实/模拟数量；真实节点停止 sing-box/accountd、阻断 SSH、恢复、kill Controller 的结果符合 SPEC |
| AC-5.1-06 | 24h soak 无 P0/P1、无无界 DB/任务增长；accountd/Controller 故障期间已有代理服务持续可用；probe credential 不泄漏 |

**Live 最小矩阵：**正常监控；代理故障；仅 accounting 故障；SSH 故障与恢复；Controller 离线；受限 observer 拒绝越权；accountd 降权后 restart/upgrade。降权若仍受阻必须保留实际 BLOCKED，不能标 hardening 完成；本计划要求 H05 前关闭。observer 白名单也最晚于 H05 前关闭。

### 4.3 0.5.2：Findings、审计可信度与事件时间轴

**依据：** Master §7.3。**依赖：**monitor、分层 Health、bounded telemetry store。

实施顺序：

1. 定义 Finding contract/store：稳定去重键、ACTIVE/RESOLVED、first/last seen、证据/解释与 retention；预留 ACKNOWLEDGED/SUPPRESSED。
2. 接入 accountd heartbeat、poll/event age、export_seq 及推进、Controller cursor、sync lag、schema、SQLite、retention gap，生成审计可信度 Finding。
3. 实现可解释的 median/MAD/EWMA/percentile 等基础检测；冻结最小样本、冷启动、缺测、持续时长和阈值，数据不足显示 unknown。
4. 覆盖用户流量/连接尖峰、持续异常及磁盘/内存/重启循环/遥测陈旧/网络速率异常；destination diversity 仅数据足够时作为可选项。
5. 将 Finding、health、service lifecycle、operation journal、sync/probe/verify 串成本地 Timeline；实现排序、坏记录隔离和 CLI/UI 展示。
6. 跑并发、失败注入、误报对照与真实 accountd/用户负载场景，完成 release evidence。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-5.2-01 | 同一事件重复输入只更新同一 ACTIVE Finding；恢复转 RESOLVED；固定异常样本命中、正常对照样本不出现持续误报；无重复 flood |
| AC-5.2-02 | AUDIT_STALLED、EXPORT_GAP、SYNC_LAG、SCHEMA_MISMATCH、ACCOUNTING_DB_CORRUPT 均有正反例；审计不可用明确降级而非伪造零用量 |
| AC-5.2-03 | USER_TRAFFIC_SPIKE、USER_CONNECTION_SPIKE、SUSTAINED_TRAFFIC_ANOMALY 及五类 Node 异常可解释；阈值/基线/数据不足原因可查 |
| AC-5.2-04 | monitor 与 Finding 并发、Timeline 坏行/同时间戳排序可容错；展示零临时 SSH；所有 detector 零 mutation hook |
| AC-5.2-05 | Live 停 accountd 产生 AUDIT_STALLED，恢复 RESOLVED；制造流量尖峰产生 Finding；真实 service disruption 可在 Timeline 关联；普通波动无持续误报 |
| AC-5.2-06 | soak Finding/store 有界；evidence/explanation 不含 UUID/URI/敏感 argv；异常检测不改变配置、策略或服务状态 |

### 4.4 0.5.3：Inspect、Drift 与 Verify 收口

**依据：** Master §7.4、§16.1。**依赖：**分层 Health、Finding/Timeline。

实施顺序：

1. 冻结 `inspect`、强化 `verify --json` 合同及 OS 支持矩阵；定义无权限/缺工具/未知结果，禁止把未知标 PASS。
2. 实现有界只读 inventory：OS/kernel、CPU/RAM/swap、文件系统、clock/NTP、接口、拥塞控制/qdisc、选定 sysctl、limits、服务/版本、防火墙/listener、廉价 update/reboot-required 状态。
3. 生成脱敏 canonical config、unit、runtime artifact、sing-box binary 指纹；仅比较 baseline，输出 MATCH/DRIFT/UNKNOWN，不 reconcile。
4. 强化 verify 的 Identity/Configuration/Integrity/Permissions/Services/Listeners/Accounting/Data Plane 分项，接入 Finding 与 Timeline。
5. 完成 0.5.x 安全遗留、混合版本与完整 Observation 链回归，生成 RC、24h 综合 soak 和 H05 验收包。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-5.3-01 | 支持 OS fixture、inspect/verify schema 正反例齐全；不存在 secret 全配置回传；public/loopback listener 列表与现场核对一致 |
| AC-5.3-02 | 非预期 listener、受管 unit/config/version/artifact drift 可检测；恢复后 MATCH；信息不足为 UNKNOWN |
| AC-5.3-03 | inspect/verify 前后受管文件 hash/mtime、服务 restart count 不变；无 package update、无隐式修复/重启 |
| AC-5.3-04 | Live 人工新增 listener、修改受管非 secret config/unit 可检出；恢复可闭合 Finding；verify 分项与人工检查一致 |
| AC-5.3-05 | 0.5.x 全链路 24h RC soak 无数据面回归；accountd de-root、observer 白名单已实际验证；H05 所需证据齐全 |

**人工关卡 H05：**按[专用清单](VCL_0.5-0.7_Human_Acceptance.md#h05-05x-observation-plane)演示“节点是否存活、代理是否真可用、审计是否可信、是否漂移、变化何时发生”。人工签署前，状态为 `PENDING HUMAN`，不得启动 0.6.x 实现。

## 5. 阶段 B：0.6.x Declarative Controller

### 5.1 0.6.0：Desired State、Reconciliation 与 LKG

**依据：** Master §8.1。**进入条件：**H05 PASS；已有 workspace/capability/inspect/finding/journal 可复用。

实施顺序：

1. 冻结 authoritative desired schema（Node/User/Deployment，Policy/Egress 可先定义结构）、旧 Workspace 迁移、Observed 新鲜度和兼容矩阵；旧 Node 不强制升级。
2. 提取共享 Operation/Journal 服务；定义 operation_id/type/target/precondition/changes/risk/postcondition/rollback/result，明确每节点锁、幂等键、失败状态与恢复入口。
3. 实现 Desired/Observed Diff：MATCH/DRIFT/MISSING/EXTRA/DEGRADED/UNKNOWN；默认只生成 deterministic plan，敏感数据仅以引用表达。
4. 实现显式 approve/apply；执行前重查 Workspace revision、Node/instance、capability、有效配置指纹等前置条件，不一致返回 PLAN_STALE 且零 mutation。
5. 建立 staged/current/previous(LKG) 事务：generate → schema/sing-box check → stage → atomic activate → health gate → commit；失败恢复 LKG 并 verify。
6. 实现 crash 恢复、rollback 失败后的 PARTIAL/恢复指引；接入 CLI/UI 共享 plan 结果，跑迁移、并发和 Live 矩阵。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-6.0-01 | 旧 Workspace 迁移可验证/回退；六类 Diff 均有 fixture；缺测不推断需删除/修改；默认 reconcile 只生成 plan |
| AC-6.0-02 | desired 已满足时连续 reconcile 为 NOOP，config hash/mtime/restart count 不变；相同输入产生相同 plan 内容 |
| AC-6.0-03 | plan 后修改 Node 或 Workspace → PLAN_STALE，零远端 mutation；并发 apply 受锁/precondition 约束，不发生双写 |
| AC-6.0-04 | invalid config 零 activation；写入/激活中途 kill 后 current 是完整旧/新版本之一；health fail 恢复可验证 LKG；rollback 失败明确 PARTIAL |
| AC-6.0-05 | Live 完成 MISSING 用户的 plan→人工 approve→apply→verify、DRIFT、PLAN_STALE、invalid stage、health-fail rollback、Controller loss 全矩阵 |
| AC-6.0-06 | 至少一个生产样本完成 desired migration + NOOP；identity/URI/accounting 无回归；plan/journal 无 secret，LKG owner/mode 合规；Node 0.5.x 不接受不支持的 0.6 mutation |

### 5.2 0.6.1：Alerting 与 Incident Operations

**依据：** Master §8.2。**依赖：**Finding、Operation、持久化状态与可靠观测。

实施顺序：

1. 扩展 ACTIVE/ACKNOWLEDGED/SUPPRESSED/RESOLVED，定义去抖、聚合键、cooldown、恢复通知与时间窗口。
2. 建 alert engine 和 bounded queue，持久化重试/去重状态，使 Controller restart 后不重发整批旧告警。
3. 实现至少一个生产可用通知 adapter；执行默认先做 Webhook，Telegram/Email 作为后续可替换 adapter。token/password 使用 secret-ref，payload 不执行本地 shell。
4. 实现 node/fleet maintenance window、acknowledge、按 node/type silence 和过期恢复，全部写 operation journal；只抑制相关通知，不丢原始 observation。
5. 接入 CLI/UI 告警状态/事件记录，验证 flapping、渠道故障、Controller restart 与 24h soak。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-6.1-01 | 状态转换、debounce/group/cooldown/retry 正反例通过；100 次同一 Finding 更新只形成一个告警事件，重试不形成 100 个独立通知 |
| AC-6.1-02 | Live outage 形成单一聚合告警，恢复产生 recovery；flapping 在阈值内不形成风暴；重启后告警状态可恢复 |
| AC-6.1-03 | planned reboot 在维护窗口中不产生事故通知；同窗口内无关故障仍告警；窗口/silence 到期自动恢复通知，原始观测可查 |
| AC-6.1-04 | 通知渠道失败只影响投递状态，队列/重试次数有上限，不影响 monitor/data plane；ack/silence 有权限检查和 journal |
| AC-6.1-05 | 真实测试接收端收发通过且无 credential 泄漏；24h soak 无 alert storm/无界队列；执行 Live 发消息前明确目标接收端与发送授权 |

### 5.3 0.6.2：QoS 与 User Policy

**依据：** Master §8.3。**依赖：**Desired/Operation/LKG；先完成 Research Gate。

实施顺序：

1. 做有限范围 spike：比较 sing-box 原生、tc/nftables 等 backend，证明如何将已认证用户映射到 enforcement；测 TCP/UDP、规则恢复、CPU/RAM、accountd/路由耦合。
2. 形成 QoS 决策记录：backend、支持/不支持项、VCL-owned rule 标记、权限、重启语义、回滚、性能与隔离结果；无法证明 per-user isolation 则停止 production 实现收口。
3. 冻结 Policy/User binding schema、带宽单位、方向、burst、soft connection warning、可行时的 hard guard，以及有限时策略到期行为。
4. 通过统一 plan/apply/verify/rollback 编译和应用规则；只操作 VCL-owned rules；NOOP 不重建规则，service/node restart 后有效策略符合声明。
5. 将 Finding 转为 Recommendation/Operation Plan，支持 recommend/approve；无默认 automatic 执行入口。
6. 执行 Alice/Bob 隔离、TCP/UDP、规则移除/重启/回滚、持续限速 soak 和人工 approve 链路。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-6.2-01 | Research Gate 有实测报告和安全/回滚结论；用户身份到规则映射可证明；仅有全节点限速不能视为 per-user QoS |
| AC-6.2-02 | Policy apply 幂等；删除后恢复 baseline；NOOP 不重建规则；重启符合 desired；非 VCL-owned 规则保持不变 |
| AC-6.2-03 | 执行默认：在带宽余量充足、无竞争瓶颈的双用户测试中，Alice 设 20Mbps，预热后 3×60s 的吞吐均值在目标 ±15% 内；Bob 吞吐相对独立对照下降 ≤10%。环境不满足则重建测试条件，不直接归 PASS |
| AC-6.2-04 | TCP/UDP 分别实测；soft threshold 命中能告警，hard guard 若不可行明确 unsupported、不得宣称已支持；异常用户不能耗尽整个 Node 的连接资源 |
| AC-6.2-05 | Finding→recommendation→人工 approve→apply 生效；拒绝/未批准时零 mutation；策略 rollback 恢复，持续限速无资源泄漏/全节点误限速 |
| AC-6.2-06 | 无新增公网管理端口，规则权限和所有权可审计；有限时策略的到期恢复作为已批准操作的一部分验证，不成为无人值守策略决策 |

带宽/隔离数值为本方案执行默认。Research Gate 如证明需不同容差，必须在编码前修改 G0 判据并解释测量误差，不能看到失败结果后临时放宽。

### 5.4 0.6.3：Egress 资源与逐用户出口绑定

**依据：** Master §8.4。**依赖：**Desired/User binding、事务/回滚、独立 secret-ref 与 Health。

实施顺序：

1. 定义独立 Egress 资源（direct/socks5）及 credential_ref；User 引用 Egress，禁止把 SOCKS URL 硬编码进 user 字段。
2. 编译 auth_user→outbound，分别支持 direct、SOCKS no-auth，以及实际认证场景需要的 username/password；secret 通过受限文件/通道注入，不进 argv/log。
3. 冻结 DNS 本地/远端解析、域名匹配、SOCKS5h 等价语义、CDN locality、UDP/QUIC/HTTP3 支持和不支持时的显式失败方式。
4. 实现 bounded Egress probe：TCP、auth、CONNECT、有效出口 IP、latency/TTFB；失败进入 Finding/Health；默认 fail-closed。
5. 经共享服务完成 add/update/remove/bind 的 plan/apply/verify/rollback，CLI/UI 展示相同 effective egress；direct 用户保持隔离。
6. 按固定 A/B/C 真实拓扑执行 benchmark 与故障矩阵，将数据和解释写入 evidence。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-6.3-01 | Egress/secret-ref schema 正反例通过；增删改幂等、回滚可恢复；Alice/Bob binding 不串线，CLI/UI effective egress 一致 |
| AC-6.3-02 | Live Alice 出口 IP 为 SOCKS，Bob 为 VPS；错误密码、SOCKS 停机、超时均使 Alice 显式失败且 Bob 正常；出口观测证明零 silent direct fallback |
| AC-6.3-03 | DNS leak/domain/CDN 行为符合冻结语义；UDP、QUIC/HTTP3 有逐项实测结果，不支持时明确失败，不静默降级/绕过出口 |
| AC-6.3-04 | A=Client→LAX VLESS→direct；B=Client local dialer-proxy→LAX VLESS→SOCKS5；C=Client→LAX VLESS→VPS-side SOCKS5→target；固定目标/负载，保存每组 latency 10 次 min/median/max、cold TTFB 10 次 median、总请求时间、吞吐 3 次及两段 RTT |
| AC-6.3-05 | C 无无法解释的巨大 overhead；不要求与拓扑无关的固定提升比例。异常开销须复测定位并关闭原因后收口，不能只填“能访问” |
| AC-6.3-06 | 错误/泄漏/故障注入及真实用户回归通过；密码不进 Workspace 明文、argv、log、journal；SOCKS 故障不影响 direct 用户 |

**环境前置：**需 LAX VPS、US-West SOCKS 与可控客户端/目标；准备 no-auth/auth 和 UDP 支持矩阵。无法取得指定环境时标 `PENDING LIVE`，其他地区替代须先更新 G0 的拓扑与偏差说明。

### 5.5 0.6.4：受控维护与 Fleet 升级编排

**依据：** Master §8.5、§16.2。**依赖：**0.5.0 单节点 upgrade、0.6.0 事务、0.6.1 maintenance window。

实施顺序：

1. 统一单节点与 fleet upgrade plan 的模型，输出 current/target、compatibility、precondition、备份、预计停机、rollback；明确旧 CLI 的兼容入口。
2. 编排 preflight→backup→stage→apply→service health→proxy probe→commit；执行默认先 canary、再逐节点滚动，失败停止扩散。
3. 实现中断恢复、previous runtime/config/service 恢复、verify 以及 ROLLED_BACK/PARTIAL；不宣称跨节点原子提交或分布式回滚。
4. 加入 typed maintenance allowlist：restart sing-box、restart accountd、reboot、cleanup VCL-owned data；cleanup 有 ownership/边界检查。
5. 完成 restricted management SSH：no-PTY/no-forwarding、forced-command/typed dispatcher、observer/operator/admin 分权与 capability；任意 shell 被拒。
6. 在维护窗口做真实 minor upgrade、health-fail rollback、planned reboot，完成 0.6.x 综合 RC/soak 并提交 H06。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-6.4-01 | 损坏/digest 不符/不兼容 artifact 零 apply；backup 不满足时拒绝；manifest/digest 必须校验，签名能力按 G0 声明，不虚称已签名 |
| AC-6.4-02 | health gate 失败恢复旧 runtime/config/service 并 verify；Controller 中途退出后能恢复或明确 PARTIAL；journal 足够定位每节点已完成步骤 |
| AC-6.4-03 | canary 失败不继续扩散；无 distributed rollback 假承诺；所有 maintenance 仅在 allowlist 内，cleanup 不触及非 VCL-owned 数据 |
| AC-6.4-04 | restricted operator 无法执行任意 shell/越权操作/转发；observer 不能 mutation；备份和凭据的 owner/mode/脱敏检查通过 |
| AC-6.4-05 | Live 0.6.x minor upgrade、主动 health fail→rollback、maintenance reboot 全部通过；URI、identity、accounting 保留；真实 proxy 恢复与预期一致 |
| AC-6.4-06 | 0.6.x 固定 RC 24h 综合 soak 覆盖 reconcile、alert、QoS、Egress、维护与恢复，无不可恢复损坏/P0/P1；H06 证据齐全 |

**人工关卡 H06：**验收人确认“要改什么、plan 是否仍有效、执行是否生效、失败能否回滚、用户策略/出口是否隔离”。按[专用清单](VCL_0.5-0.7_Human_Acceptance.md#h06-06x-declarative-controller)签署后才进入 0.7.x 实现。

## 6. 阶段 C：0.7.x Programmable Data Plane

### 6.1 0.7.0：Node Roles、Transit Identity 与 ACL

**依据：** Master §9.1。**进入条件：**H06 PASS；可靠 plan/apply/verify、secret-ref、restricted management 已成立。

实施顺序：

1. 冻结 entry/transit/egress role、能力要求及默认 transit disabled；角色来自 desired state，不通过开放端口猜测。
2. 实现独立 Node principal 和 credential issue/rotate/revoke/audit，secret 不入 Workspace 明文；普通用户 UUID 不能当 transit credential。
3. 实现目标端显式 source principal ACL，未授权默认拒绝；声明必要数据面 listener、源限制与最小暴露范围。
4. 定义用户身份在 Entry 终止，Egress 仅识别上游 Node principal；先建立 transit 分类与路径关联，为 0.7.4 去重计量预留来源。
5. 将角色/ACL/credential 生命周期纳入 typed plan/apply/verify/rollback，执行未授权、授权、轮换、撤销和 legacy single-hop 回归。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-7.0-01 | 默认 transit 关闭；角色/capability 不满足则拒绝变更；声明之外无可用 open transit |
| AC-7.0-02 | Live 未授权 A→B 必须拒绝，授权后成功，revoke 后新连接立即失败；rotate 后新凭据正常、旧凭据按冻结的撤销语义失效 |
| AC-7.0-03 | 普通用户 credential 不能认证为 Node；撤销 Node credential 不影响普通用户连接；legacy single-hop 回归通过 |
| AC-7.0-04 | Node secret 不进入 Workspace/journal/cache/evidence；Egress 无原始用户 credential；ACL 与 compromise 影响范围有安全审阅记录 |
| AC-7.0-05 | role/ACL 变更经过 plan/apply/verify，失败可恢复；transit accounting 识别 `node:<name>`，不混作普通用户身份 |

### 6.2 0.7.1：Static 2-Hop Path

**依据：** Master §9.2。**依赖：**0.7.0；production baseline 冻结前必须完成 Transport Decision Gate。

实施顺序：

1. 在可重复真实网络测试中比较 VLESS/WireGuard，必要时增加 Hysteria2/TUIC；覆盖 connect setup、HTTPS TTFB、TCP 吞吐、UDP/QUIC、0%/1%/3% loss、CPU/RAM、运维、rotation、rollback。
2. 形成 transport ADR 并冻结安全、端口/ACL、维护、MTU/DNS/UDP 能力与回退模型；SOCKS5 继续作为外部 Egress adapter，不默认选作内部长期 transport。
3. 定义 Path/User binding schema，生产 `max_hops=2`；compiler 检查 role、capability、credential readiness、loop、重复节点/hop 上限，生成 deterministic Entry/Egress plan。
4. 建跨节点有序 apply：先验证 Egress 就绪再激活 Entry 引用，定义移除顺序、单侧失败补偿和 PARTIAL 恢复；不把部分成功显示全成功。
5. 冻结 Entry/Egress DNS resolve、domain routing、CDN/DNS leak、remote resolver failure、UDP/QUIC/HTTP3、MTU/MSS/PMTU 与 session 语义。
6. 实现静态两跳、显式移除到 direct/指定出口、NOOP、失败隔离；执行全部 Live 协议/故障矩阵与 ≥24h soak。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-7.1-01 | benchmark+ADR 完成，保留每个 loss/协议场景数据与选型理由；核心 DNS/UDP/QUIC/MTU 要求未满足不得冻结 production baseline |
| AC-7.1-02 | 非法 role/capability/credential/loop/>2-hop 在 schema/compiler 阶段被拒；相同输入 plan 一致；不支持的 Node 不进入 Path |
| AC-7.1-03 | Live 单用户 A→B 两跳生效，direct 用户仍单跳；remove 恢复显式声明出口；重复 reconcile 为 NOOP；单侧失败明确 PARTIAL 并恢复可验证旧态，禁止留下继续承载流量的未知半配置 |
| AC-7.1-04 | TCP 网站、DNS UDP、generic UDP、QUIC/HTTP3、DNS leak/CDN、fragmentation/PMTU/large TLS/QUIC packet size/TCP MSS 均有实际结果；不支持显式失败，不静默绕行 |
| AC-7.1-05 | Path 变更仅对新连接生效；健康旧会话不主动迁移/终止；Entry/Egress 重启的真实影响单独记录；故障不 silent direct fallback |
| AC-7.1-06 | Controller 离线已有静态 Path 继续转发；独立 Node credential/ACL/listener 安全检查通过；两跳 ≥24h soak 无未知断流、资源泄漏或错误 fallback |

选型完成前允许研究原型，不对外宣称完整 Path 能力已交付。某协议若需排除，必须先明确修订 SPEC 范围，不能用 `UNSUPPORTED` 自动冲抵原有发布要求。

### 6.3 0.7.2：Link / Path Observation 与拓扑

**依据：** Master §9.3。**依赖：**已验证的静态 Path、bounded observation、Health/Finding。

实施顺序：

1. 定义 Link（source/target/measured_at/RTT/loss/connect latency/availability，可选吞吐）及 freshness/unknown 语义。
2. 实现 Controller→A 发起、A→B 有界测量、A→Controller 返回的 probe；只允许已声明 Path 和 configured backup candidate links。
3. 冻结每任务 timeout/payload/rate/concurrency/总预算；measurement 使用受限非 admin/root 身份，禁止持续 peer gossip 或默认 N² 探测。
4. 组合 Entry+Link+Egress 为 HEALTHY/DEGRADED/UNAVAILABLE/UNKNOWN；采集 Path connect/TTFB/failure rate，可选低频吞吐。
5. WebUI 从本地 cache 展示 Entry/Egress/Link/Path、health、RTT/loss、绑定用户、流量；缺测清晰可见；执行 loss/failure/恢复与开销对照。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-7.2-01 | Link schema、loss/timeout、health 聚合、过期 UNKNOWN fixture 通过；100 节点只调度 declared/candidate links，任务数按声明边数增长而非默认 9900 条有向边 |
| AC-7.2-02 | probe 数量/超时/payload/并发不超过 G0 上限；worker crash/timeout 不形成重试风暴；非受限目标和任意探测 payload 被拒 |
| AC-7.2-03 | Live A→B RTT/loss 实测；注入 loss→DEGRADED，Egress 停止→UNAVAILABLE，恢复→HEALTHY；measurement 停止→UNKNOWN/陈旧标记，静态转发继续 |
| AC-7.2-04 | 拓扑 UI GET 零 SSH/node-to-node probe；probe failure 不改 data plane；不引入 peer control channel；无 admin/root credential |
| AC-7.2-05 | 同负载 A/B 对照记录 CPU/网络开销。执行默认：持续 30 分钟测量额外 CPU 平均 ≤单核 5%，低频吞吐样本单独核算；超预算调低频率并复测，无 probe storm |

### 6.4 0.7.3：Primary / Backup 与人工切换

**依据：** Master §9.4。**依赖：**两个已编译静态 Path、Path Health、Operation precondition。

实施顺序：

1. 定义 primary/backup route policy 与 readiness：capability、credential、config compilable、path health、egress reachable。
2. 实现 switch plan→approve→apply→verify，保存 source/target/revision/precondition；backup 不 ready 或 plan stale 直接拒绝。
3. primary DEGRADED/UNAVAILABLE 且 backup HEALTHY 时生成 Recommendation/Plan，不自动 apply。
4. 只读计算 minimum improvement/duration、cooldown、stickiness 与 score explanation，为 0.8 预留；无无人值守 switch hook。
5. 验证新旧 session 边界、重复切换 NOOP、故障建议、手动切换、主路恢复不自动回切和人工 switch-back。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-7.3-01 | readiness 每个缺失条件均拒绝 switch；unavailable/untrusted path 不可选择；plan 失效返回 PLAN_STALE；重复目标切换 NOOP |
| AC-7.3-02 | Live primary 故障只生成 recommendation，未 approve 时不变更；approve 后新连接走 backup，出口与 path 标识可证明 |
| AC-7.3-03 | 在两条 Path 都健康的受控切换中，既有 TCP 会话继续原路直至自然结束，新连接使用新路；主路真实故障导致的旧会话断开单独记录，不宣称故障连接一定存活 |
| AC-7.3-04 | primary 恢复后不自动切回；人工 switch-back 正常；score/cooldown 仅用于解释/建议，不触发自动路由 |
| AC-7.3-05 | 执行默认至少 3 轮切换/切回，无配置漂移、credential 泄漏、silent direct fallback 或无人值守 flapping |

### 6.5 0.7.4：Path-aware Accounting 与容量可见性

**依据：** Master §9.5、§16.3。**依赖：**Path 身份关系、transit 分类、可恢复 accounting、manual switch。

实施顺序：

1. 冻结 accounting invariant：user_ingress 以 Entry 为权威，transit 单列且不进入 user fleet-total，egress 用于 network/path capacity；明确时间窗/重试/缺测/切换归属。
2. 实现事件来源标记、去重聚合、schema 迁移、rollup/retention/gap 语义，保持 approximate accounting 定位。
3. 提供 per-path bytes/connections/active users/failure count；建立 Node/Path connections、network rate、CPU/RAM/path traffic 压力 Finding。
4. 验证切换前后按事件所属 path/time 归属，不将已结束 Path 历史流量归入新路径；不要求 Egress 得到原始用户 credential。
5. 用可控 1GB 数据集和真实大文件两跳核对 Entry/Egress/transit/Fleet；完成 capacity Finding、全链路 RC soak、H07 验收与文档收口。

| AC | 通过标准与测试方法 |
| --- | --- |
| AC-7.4-01 | fixture 精确证明 Entry 1GB + transit/egress 各自统计不会变成 user fleet-total 2GB/3GB；重放/重试不重复入账；rollup/retention/gap 正反例通过 |
| AC-7.4-02 | Live 单用户两跳大文件：Fleet user-total 等于同窗口 Entry user usage 聚合（允许已声明的展示舍入），不再叠加 transit/egress；原始文件大小与近似计量差异单独解释 |
| AC-7.4-03 | transit 可单独查询；path bytes/connections/active users/failures 可查；切换前后 usage 归属正确，旧路径历史不丢失/不改写 |
| AC-7.4-04 | Path usage 与接口流量量级可解释，协议封装/背景流量/采样间隔有记录；capacity pressure 可产生 Finding/Recommendation，零自动迁移 |
| AC-7.4-05 | export/cache/UI/evidence 无 transit secret，Egress 不掌握用户原始 credential；accounting 故障不停止转发 |
| AC-7.4-06 | 固定 RC ≥24h 完成静态两跳+Link/Path observation+人工 failover+accounting 综合 soak；无 P0/P1、双计、静默回退、未知断流；H07 材料完整 |

**人工关卡 H07：**按[专用清单](VCL_0.5-0.7_Human_Acceptance.md#h07-07x-programmable-data-plane)演示 User→Entry→Egress→Internet，并复核 ACL、真实协议流量、Controller 离线、人工切换和计量归属。签署后才可声明 0.5～0.7 总体实施完成；自动路由仍未在本范围实现。

## 7. 实施归属、证据与交接

### 7.1 代码与文档归属

| 现有落点 | 后续实施归属 |
| --- | --- |
| `lib/observation/`、`lib/telemetry_snapshot.py` | capability/telemetry 复用；新增 monitor/health/finding/inspect/link observation 的独立服务模块 |
| `lib/access.py`、`lib/ssh_transport.py`、`lib/trust.py` | typed transport、credential class、受限 observation/operator；不扩展 generic remote exec |
| `lib/workspace.py`、`lib/vincula-fleet.py` 内现有 journal/cache | 将 desired/reconcile/operations/policy/egress/path 服务逐步提取到独立模块，CLI 保持薄入口 |
| `lib/node_upgrade.py`、`vincula.sh`、`bin/` | 复用单节点 upgrade；事务/LKG、typed maintenance、Node capability/dispatcher 逐步扩展 |
| `lib/vincula-accountd.py`、`lib/vincula-accountd.service` | de-root、最小 mapping/credential、accounting health 与 traffic class；迁移保留历史 |
| `lib/vincula-ui/server.py`、`lib/vincula-ui/static/` | 读本地 cache 的健康、Finding、plan、拓扑与 capacity 展示；不在 GET 中发起 SSH |
| `schemas/`、`tests/fixtures/`、`tests/test.sh`、`tests/test-fleet.sh` | 每版 contract、反例、失败注入、并发/兼容回归；按功能拆小模块测试，保留全量入口 |
| `scripts/`、`.github/workflows/ci.yml` | 有界 Live driver/soak/benchmark、打包/digest 与 required CI；不得伪造 Live job 通过 |
| `docs/specs/`、`docs/evidence/<version>/`、手册/CHANGELOG | 子版本冻结规格、逐项证据、实际兼容矩阵、操作说明与版本状态 |

### 7.2 研究和合同决策的最晚时点

| 决策 | 最晚完成 | 必须交付的可审查结果 |
| --- | --- | --- |
| accountd 数据访问/Clash credential、observer 白名单 | 0.5.1 G0，遗留最晚 H05 关闭 | 权限矩阵、迁移/回退、无法读取 secret/无法越权的验证方案 |
| Health/Finding 阈值、冷启动、缺测与资源 cap | 各自 0.5.1/0.5.2 G0 | 状态转移表、固定正反例、store 的 retention/size/corruption 规则 |
| Desired migration、事务恢复、plan precondition | 0.6.0 G0 | schema 迁移样本、crash 状态表、恢复命令和 PLAN_STALE 判据 |
| 通知渠道及测试接收端 | 0.6.1 G0 / Live 前 | 至少一个 adapter 合同、secret-ref、队列限制与实际发送授权 |
| QoS backend 与用户隔离 | 0.6.2 Research Gate，生产实现冻结前 | benchmark/安全/回滚报告；失败即 BLOCKED，不顺延为“已支持” |
| SOCKS DNS/UDP 与 benchmark 拓扑 | 0.6.3 G0 | 支持矩阵、fail-closed 判据、A/B/C runbook |
| 内部 transport 与 DNS/UDP/MTU/session 语义 | 0.7.1 Transport Decision Gate | VLESS/WireGuard 对照数据及 ADR；未完成不得冻结 production baseline |
| 双计防止与切换时计量归属 | 0.7.4 G0 | user/transit/egress invariant、1GB fixture、Live 对账表 |

新增决策记录归档到 `docs/specs/decisions/`，需要时创建；本方案不预造选型结论。

### 7.3 每个子版本交付包

```text
docs/specs/V0.x.y_Spec.md              # G0 时建立；0.5.0 已存在
docs/evidence/0.x.y/
  SUMMARY.md                         # 版本、SHA、制品 digest、G0～G5、AC、限制
  TESTS.md                           # 命令/环境/pass/fail/skip/失败注入/并发
  SECURITY.md                        # listener/权限/sandbox/secret/攻击面/偏差
  COMPATIBILITY.md                    # Controller × Node × capability，含方法
  LIVE.md                            # 前置/步骤/期望/实际/状态/证据
  SOAK.md                            # 候选、时长、负载、资源前后值、缺测、结论
  HUMAN_ACCEPTANCE.md                 # 仅大阶段收尾版本必须：0.5.3/0.6.4/0.7.4
```

每个 AC 必须映射到测试名称或 Live case ID，并注明适用 SHA/digest。SUMMARY 状态采用 `PLANNED`、`IN PROGRESS`、`PASS OFFLINE`、`PENDING LIVE`、`PASS LIVE`、`PENDING HUMAN`、`ACCEPTED`、`FAIL`、`BLOCKED`；`ACCEPTED` 仅可在所需人工关卡通过后使用。这些是计划/证据状态，不改变产品内 Operation/Health 枚举。

Live 每行必须含：目标匿名标识、Controller/Node 版本、capabilities、OS/arch、拓扑、候选 SHA/digest、前置条件、步骤、期望、实际、测量窗口、执行人、恢复结果和脱敏证据位置。不得写完整 URI、UUID、私钥、Clash secret、SOCKS password 或可直接登录凭证。secret 的前后比对在受限环境完成，文档只保存一致/不一致结论及非敏感证据引用。

### 7.4 验证命令与运行环境

沿用仓库现有全量入口，在隔离的 Linux/WSL 测试副本执行：

```bash
bash tests/test.sh
bash scripts/build-release.sh
bash scripts/build-controller.sh
git diff --check
```

`tests/test.sh` 已 source Fleet suite，不重复要求再独立全跑 `tests/test-fleet.sh`。制品按现有 CI 校验 sidecar、release.lock/controller.lock、payload manifest 与离开源码目录的 black-box Controller 包；保留 source commit 与 `SOURCE_DATE_EPOCH`，避免将不同构建输入的 digest 混比。

现有 required CI 包括 Ubuntu、Debian 12/13、concurrency、failure-injection、artifact；新增功能补入对应门禁。声明支持的其他 OS/arch 与 Windows Controller 通过兼容矩阵另外记录实际验证方式；不可从 Linux fixture 推断这些目标已 Live PASS。

自动测试运行在隔离 HOME/Workspace/known_hosts 下，禁止触及真实 credential/UI runtime。Live driver 只针对已明确选择的验收节点与测试身份；最终证据写入新记录，不为“统一状态”批量改写旧 evidence。

### 7.5 人工验收失败与候选变更

1. 实施者先完成代码、G0～G5、手册、回退步骤与脱敏证据包，再提交人工验收；不以“请确认是否继续”替代具体可验收成果。
2. 人工验收人执行或见证操作并逐项记录实际结果。自动化可以准备/采集证据，不能替人工填写签署结论。
3. 必需项 FAIL/PENDING LIVE/PENDING HUMAN、P0/P1、未解释的数据损坏/secret 泄漏均阻止通过；MUST 不得以风险接受豁免。
4. 失败项形成缺陷编号、修复范围和复验清单。修复后重跑直接影响项及共同不变量；变更影响全链路时重跑综合 soak，不无条件重复无关测试。
5. 签署绑定 RC commit/artifact digest；验收后有代码或打包内容变更则重新判断影响并取得补充签署。纯证据文档变更保留原 source/digest 的可追溯关系。
6. H05/H06 未通过时只允许本阶段修复与下一阶段只读设计，不进入下一大阶段实现；H07 未通过不宣布总体完成。非阻塞 SHOULD 偏差如需保留，必须明示原因、期限和人工确认。

### 7.6 执行起始清单

- [ ] 核对 0.5.0 本地基线、当前文档状态和历史 evidence 的适用范围，建立 ≤3 秒升级补证任务。
- [ ] 建立 0.5.1 版本 SPEC，冻结 Health、monitor/store/probe 与 accountd/observer hardening 方案。
- [ ] 为 0.5.1 建立 AC→测试→Live 映射、隔离测试环境和 ≥10 节点受控混合矩阵。
- [ ] G0 通过后进入 0.5.1 实现；按本文推进至 0.5.3，再提交 H05 的具体 RC 与证据。

本清单初始均未勾选，表示后续执行任务；本方案的创建不构成这些任务已经执行。
