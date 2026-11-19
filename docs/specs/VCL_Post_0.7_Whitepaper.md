# Vincula Post-0.7.x 演进白皮书：从可编程数据平面走向意图流量工程与受护栏闭环自治

> **文档性质：** 长期架构白皮书（Forward-Looking Architecture Whitepaper）
> **适用范围：** VCL `0.8.x` → `0.9.x` → `1.0+`（以 `0.5.5`、`0.6.x`、`0.7.x` 收口为前提）
> **制定日期：** 2026-11-17
> **修订日期：** 2026-11-19
> **前置基线：** [0.5.x–0.7.x Master SPEC](VCL_0.5-0.7_Master_SPEC.md) · [0.6.x 开发规格与可行性研究](V0.6.x_SPEC.md) · [实施与验收方案](../plans/VCL_0.5-0.7_Implementation_Plan.md)

---

## 1. 文档定位与演进全景

经过 `0.4.x`～`0.7.x` 的建设，Vincula 将从单机脚本化节点管理工具逐步完成四次基础能力跃迁：

```text
0.4.x  Imperative Fleet Manager
       └─ 节点生命周期、用户下发、便携 Workspace、本地审计与只读 WebUI

0.5.x  Observable Appliance / Observation Plane  [当前收口：0.5.5]
       └─ 能力协商、受限 Observer、非 root accountd、Schema-5 独立日留存账本、
          健康状态机、真实 HTTPS 代理探针、14 类 Findings、Inspect/Drift、本地时间轴

0.6.x  Declarative Controller & Reliable Operations
       └─ SSH 三层闭环底座、Desired vs Observed Diff、PLAN_STALE 与 LKG 事务、
          R-03 受管重配置、Alerting 与 Finding 噪声治理、Traffic Policy v0.1、
          逐用户 Egress、归档/修剪与 Fleet Doctor；逐用户 QoS 取决于研究

0.7.x  Programmable Static Data Plane
       └─ Node Roles (entry/transit/egress)、Transit Principal & ACL、
          Transport ADR、静态 2-Hop Path Compiler、有界 Link/Path 测量、
          主备就绪度、人工批准切换、Entry 权威去重计量
```

`0.6.x` 先交付声明式变更、Traffic Policy v0.1 和逐用户出口。外部 SOCKS5 首版以 TCP/HTTPS、约定的 DNS 和出口隔离为必需能力，UDP/QUIC 逐项实测。若 QoS 研究无法证明用户隔离，可以明确延期。H06 前可在隔离环境做两跳选型与会话实验，H06 通过后正式集成。

`0.7.x` 的链路故障产生切换建议。操作者批准指定用户与目标路径后，可以立即执行，也可以限时等待该用户空闲后执行。等待期间若观测未知则继续等待，到期撤销。执行可中断目标用户的旧会话，逐用户操作应保持其他用户可用。路径选择与换回均由操作者批准。

本白皮书定义 `0.7.x` 验收（H07）通过之后的长期演进蓝图，将 Vincula 推向私有边缘网络控制平面的完整形态：

```text
0.8.x  Intent-Driven Traffic Engineering（意图驱动流量工程）
       └─ 声明北向路径意图 → 多维路径效用评分 → 抗震荡迟滞状态机 → 应用感知路由与受控 3-Hop

0.9.x  Guardrailed Closed-Loop Automation（受护栏约束的闭环自治）
       └─ 观察→Finding→策略→计划→六大硬护栏→分级 Staging→探针验证→自动提交或 LKG 秒级回退

1.0+   Zero-Touch Private Edge Appliance（零维护私有边缘网络家电）
       └─ 短期 SSH/Transit 证书、端到端签名客户端交付面、显式边缘加速服务、多年期自平衡存储
```

---

## 2. 核心架构哲学与不可逾越的边界

无论上层智能化和自动化演进到何种程度，Vincula 从 `0.5.0` 确立的核心架构铁律在 `0.8.x`～`1.0+` **继续保持永久不变**：

> **Smart Controller, Boring Fail-Static Node, No Distributed Authority.**

### 2.1 三项永久架构支柱

1. **Controller 唯一权威（Single Authoritative Control Plane）：**
   所有的拓扑图计算、路径评分、切换决策、安全护栏判定和配置编译全部发生在 Controller；Node 永远不运行路由决策 Daemon，Node 之间不交换任何控制平面状态。
2. **Node 故障静态退化（Boring Fail-Static Appliance）：**
   当 Controller 离线、重启或网络分区时，Node 的数据平面必须无条件保持在当前已提交的 `current (LKG)` 配置上继续转发流量；Controller 失联绝不触发 Node 自主降级、自主改路或回退 `direct`。
3. **观测与数据面物理隔离（Observation/Data-Plane Isolation）：**
   `vincula-observer`、`vincula-accountd`、Link Probe 或 WebUI 的任意异常、满盘或超时，绝不允许中断 `sing-box` 既有转发，也不得通过观察通道执行任何写入。

### 2.2 长期 Anti-Goals（即使到 1.0+ 也不做的事）

除非另行立项重写产品定位，Vincula **永久拒绝** 引入以下机制：

| 拒绝项 | 架构原因 |
| --- | --- |
| 节点间 Gossip / 分布式共识（Raft / Etcd / BGP Mesh） | 私有小中规模节点集群不需要控制面一致性协议；多节点脑裂时的排障复杂度远超集中式 SSH/TLS 控制拓扑 |
| 节点间自动 Full-Mesh $N^2$ 探测风暴 | 探测开销随规模平方增长，易触发机房风控；只测量已声明路径与显式候选边 |
| 运行中 TCP/UDP 会话实时迁移（Live Flow Migration） | 新建连接使用新路径。已有连接按运行时能力继续或断开，变更计划记录其影响范围 |
| 通用远程 Shell / Web Terminal / 通用 RMM | 违背“受限 typed dispatcher”最小权限原则，将扩大管理平面被横向渗透的爆炸半径 |
| 透明 TLS MITM 缓存 / DPI 内容审查 | 破坏端到端加密信任与用户隐私底线，绝不伪造证书或窥探明文载荷 |
| 静默回退 `direct` 出口 | 策略或链路的显式意图必须 `fail-closed`；无法按声明路由时宁可拒绝连接并告警，也不偷偷暴露本地节点 IP |

---

## 3. VCL 0.8.x — Intent-Driven Traffic Engineering（意图驱动流量工程）

`0.8.x` 解决的核心问题是：**管理员不再需要为每个用户手工枚举“走哪条物理主备路径”，而是声明“流量想要什么属性”，由 Controller 基于 `0.7.2` 采集的真实链路遥测持续评估、防抖择优并安全重编译静态路径。**

### 3.1 北向意图模型（Northbound Route Intent）

在 `0.7.3` 的显式 `primary/backup` 基础上，Workspace Desired State 新增抽象层 `RouteIntent`：

```yaml
route_intents:
  tokyo-low-latency:
    objective: latency-first          # latency-first | throughput-first | availability-first | balanced
    entry_scope: [lax-01, sfo-01]
    egress_pool: [tyo-01, tyo-02, osa-01]
    constraints:
      max_hops: 2
      require_udp: true
      require_quic: true
      exclude_regions: [high-risk-transit]
      capacity_headroom_min: 0.25     # 节点预留至少 25% 带宽/连接余量
    fallback_policy: fail-closed      # 严禁默认 direct
```

- **确定性候选集生成：** Compiler 先按 `constraints`（角色、Capability、`require_udp`、ACL 就绪度、容量准入）过滤出合法候选路径集合 $\mathcal{P}_{\text{eligible}}$，若为空则立即标记 `UNSATISFIED` 并 `fail-closed`，绝不越界选择不满足约束的出口。

### 3.2 多维路径评分与效用函数（Multi-Dimensional Path Scoring）

`0.7.3` 已预埋的只读稳定性评分在 `0.8.0` 升级为可审计、可复现的效用函数。对每条候选路径 $p = (e_{\text{entry}}, \ell, e_{\text{egress}})$，Controller 在每个评估周期（仅使用本地 `observation.db` 缓存，不阻塞采集）计算归一化代价函数 $C(p, t)$（分值越低越优）：

$$
C(p, t) = w_r \cdot \widehat{\text{RTT}}_{\text{ewma}}(p, t)
        + w_j \cdot \text{Jitter}_{p95}(p, t)
        + w_l \cdot \Phi_{\text{loss}}\!\left(\text{Loss}(p, t)\right)
        + w_t \cdot \widehat{\text{TTFB}}_{\text{https}}(p, t)
        + w_u \cdot \Psi_{\text{util}}(p, t)
        + w_s \cdot \text{InstabilityPenalty}(p, t)
$$

各分量设计与工程含义：

1. **时延与抖动项（$\widehat{\text{RTT}}_{\text{ewma}}$ / $\text{Jitter}_{p95}$）：** 采用指数加权移动平均消除单点尖峰毛刺，同时用 $p_{95}$ 抖动惩罚跨海高峰期排队缓冲膨胀（bufferbloat）。
2. **丢包非线性惩罚项 $\Phi_{\text{loss}}$：** 在 `0.7.1` Transport ADR 的 `0%/1%/3%` 基准数据上建模——当丢包率超过协议退化拐点（如 $> 1.5\%$ 对 TCP 吞吐产生非线性坍塌），惩罚权重呈超线性增长，避免“低延迟但高丢包”的幽灵链路胜出。
3. **端到端服务质量项（$\widehat{\text{TTFB}}_{\text{https}}$）：** 防止只测 ICMP/TCP 握手时延而忽略远端代理自身阻塞或 DNS 解析拖慢的“假通”现象。
4. **容量水位惩罚项 $\Psi_{\text{util}}$：** 结合节点当前连接数、网络速率与内存水位，当路径接近容量上限时平滑抬高代价，引导新会话分散到余量充足的同区域备路，避免羊群效应。
5. **近期不稳定惩罚（$\text{InstabilityPenalty}$）：** 若该路径在过去滑窗内刚发生过中断或切换，附加衰减惩罚，抑制“刚恢复立刻抢回”的乒乓效应。

### 3.3 抗震荡状态机（Anti-Flap & Hysteresis State Machine）

路由工程最大的风险不是“切换慢几秒”，而是**全局同步震荡（Route Flapping）**。`0.8.x` 采用非对称迟滞状态机：

```text
                  [硬故障 / 连续 M 次 probe 失败 / UNAVAILABLE]
               ┌────────────────────────────────────────────────┐
               ▼                                                │
       ┌──────────────┐   持续 W_down 窗口劣于候选且收益 >= Δmin  │
       │   ACTIVE     ├───────────────────────────────────────┐ │
       │  (Stickiness)│                                       ▼ ▼
       └──────▲───────┘                               ┌─────────────────┐
              │                                       │ SWITCH_PENDING  │
              │  冷却期 Cooldown 结束                   │ (Precheck+Plan) │
              │  & 恢复稳定窗 W_up 通过                 └────────┬────────┘
              │                                                │
       ┌──────┴───────┐        校验候选 Ready + 护栏通过          │
       │  COOLDOWN    │◄───────────────────────────────────────┘
       │ (禁止再次切回) │
       └──────────────┘
```

四道防抖硬约束：
1. **双门槛收益判定（Minimum Improvement）：** 候选路径 $p_{\text{new}}$ 必须同时满足相对改善 $\frac{C(p_{\text{cur}}) - C(p_{\text{new}})}{C(p_{\text{cur}})} \ge \Delta_{\text{rel}}$（如 $\ge 20\%$）**且**绝对改善 $\ge \Delta_{\text{abs}}$（如 RTT 差值 $\ge 15\,\text{ms}$），防止两条同样优质的线路因 $2\,\text{ms}$ 波动互切。
2. **非对称确认窗（Asymmetric Dwell Time）：**
   - **逃逸快（Fast Escape）：** 当路径状态转为 `UNAVAILABLE` 或连续硬探针超时，经短确认窗（如 3 个采样周期）即可生成切换计划；
   - **回切慢（Slow Recovery）：** 当原主路从故障恢复为 `HEALTHY` 后，必须经过较长稳定期 $W_{\text{up}}$（如 10～15 分钟持续零丢包）且仍通过 `Cooldown`（如 $\ge 30$ 分钟），才允许评估切回。
3. **局部随机抖动退避（Desynchronization Jitter）：** 不同用户组/Intent 绑定独立的微秒级评估偏移，防止所有用户在同一秒集中迁移至同一条备用链路引发二次过载。
4. **连接影响与执行时机：** 新连接使用已选路径。计划记录目标用户已有会话的中断风险和执行方式。故障恢复可在审批后立即执行，计划内改路可选有截止时间的空闲等待。等待依据新鲜会话观测和执行前复核，到期撤销。逐用户切换验证无关用户可用。无人值守执行须满足 0.9 的授权模式与六项护栏。

### 3.4 应用/目标域感知路由与受控 3-Hop 实验

1. **融合 `0.6.2` Policy Engine（Application-Aware TE）：**
   在 `0.6.2` 只做“域名允许/拒绝”的基础上，`0.8.x` 将 `RuleGroup` 升级为路径选择器输入：
   - 例如：同一用户的 `realtime-gaming` / `ssh-interactive` 规则组绑定 `latency-first` Intent；`bulk-download` / `cdn-media` 规则组绑定 `throughput-first` Intent；敏感域名组绑定 `region-pinned + strict-isolation` Intent。
   - **编译规则铁律：** 显式 `reject` 规则（Traffic Policy）优先级永远高于任何 Intent 选路规则；若特定 Intent 的合格路径为空，该流量的匹配动作必须为 `reject (fail-closed)`，绝不落入默认直连。
2. **受控 3-Hop 实验能力（Bounded 3-Hop Experiment）：**
   在 `0.7.x` 静态 2-Hop 经过长期真实 soak 与对账验证后，`0.8.x` 开放受 `experimental_3hop: true` 显式开关保护的 3-Hop（`Entry → Relay → Egress`），用于应对跨大洲单段不可直达或中转清洗场景：
   - 硬限制 `max_hops <= 3`，Compiler 严格校验无环与角色序列（`entry -> transit -> egress`）；
   - 强制计算累计 PMTU/MSS 扣除与链路端到端 RTT 上限，超预算拒绝编译；
   - 沿用 `0.7.4` 近似计量。用户总量以 `Entry` 的 `user_ingress` 为权威，按会话实际路径归属，无法拆分到 Path 的中转流量按 Link 展示。

---

## 4. VCL 0.9.x — Guardrailed Closed-Loop Automation（受护栏约束的闭环自治）

从 `0.5` 到 `0.8`，Controller 的决策链始终在“安全但需要人点批准”或“仅做路由选择”的区间运行。`0.9.x` 的目标是引入**有严格护栏、有限权限、完全可审计的无人值守闭环自愈（Closed-Loop Remediation）**——解决值守运维中最消耗人力的 80% 重复性局部异常，同时确保自动化系统本身**永远不会成为放大故障的灾难源**。

### 4.1 闭环控制流水线

```text
Observation (0.5/0.7)
    │  telemetry / proxy probe / link probe / audit health
    ▼
Finding & Correlation (0.5.2 / 0.6.1)
    │  hysteresis 过滤瞬间抖动，排除 maintenance window
    ▼
Automation Policy Match (0.9)
    │  检查当前资源是否授权 autonomy_mode = bounded-auto
    ▼
Automated Operation Plan (0.6.0)
    │  生成确定性 Operation（含 precondition / rollback / TTL）
    ▼
╔══════════════════════════════════════════════════╗
║         Six Hard Guardrails Gate (0.9)           ║
║  爆炸半径 │ 令牌桶 │ 容量准入 │ 新鲜度 │ 自锁检查 ║
╚═══════════════════════╤══════════════════════════╝
                        │ PASS（否则降级为人工待批）
                        ▼
         Staged Apply → Health & Probe Verify
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
   Verify PASS                  Verify FAIL / Worse
   Commit & TTL 计时            Instant LKG Rollback + Circuit Break
```

### 4.2 三级自治模式（Autonomy Modes）

| 模式 | 允许动作 | 适用场景 | 触发方式 |
| --- | --- | --- | --- |
| `recommend-only` | 只产出 Operation Plan 与 Recommendation | 默认模式、高风险区域、生产核心变更前观察 | 全自动评估，零远端变更 |
| `bounded-auto` | 仅限白名单、可自动逆转或局部隔离的动作 | 经过验证的自动主备切换、单用户租约限速、受管服务无响应恢复 | 必须全部通过六大护栏 |
| `human-approval-required` | 所有结构性/拓扑性/安全边界类变更 | 节点升级、Egress 增删、端口/SNI 修改、Transit ACL 调整、清理操作 | 强制等待人工显式确认 |

### 4.3 六大硬性安全护栏（Six Hard Guardrails）

任何 `bounded-auto` 动作在执行前，必须由 Controller 内核的独立 Guardrail Evaluator 逐一校验通过；任一项不满足即**阻断自动执行**并退化为人工待批建议：

1. **护栏 1 — 爆炸半径上限（Blast-Radius Ceiling）：**
   在任意滑动时间窗（如 15 分钟）内，自动操作最多允许同时影响 **1 个节点** 或 **$\le 25\%$ 的活跃节点/用户**（取更严格者）。若多个节点同时触发告警（暗示可能是上游机房/国际出口大面积震荡或 Controller 本身网络故障），**全局自动变更立即冻结**，防止误判引发全网同时重启或切流雪崩。
2. **护栏 2 — 变更令牌桶与熔断（Mutation Token Bucket & Circuit Breaker）：**
   每个 Node、每个 Path、每个 User 维护独立的自动化操作预算（例如：单节点每小时最多 2 次自动重启或切流）。令牌耗尽后该实体自动进入 `CIRCUIT_OPEN (Manual-Only)` 状态，必须人工介入复核后方可复位。
3. **护栏 3 — 容量准入防雪崩（Capacity-Aware Admission）：**
   在自动将流量从故障路径 A 迁往备路径 B 前，必须校验备路径 B 加上迁移估算负载后的 CPU、连接数和带宽余量仍处于安全阈值内。若全部备路均接近饱和，宁可保持受损路径或显式限流，**严禁把雪崩传染给健康节点**。
4. **护栏 4 — 失明即冻结（Dead-Man's Switch / Fail-Static on Stale Observation）：**
   如果 Controller 自身本地时间跳变、刚从长时间离线恢复（遥测处于冷启动期）、或目标状态为 `UNKNOWN` / 观测数据超过新鲜度窗口（`telemetry_age` 超限），**禁止基于过时或缺失的事实做任何自动变更**。
5. **护栏 5 — 闭环实证与瞬时 LKG 回退（Closed-Loop Verify & Instant Revert）：**
   所有自动配置下发后，必须在限定窗口内通过真实的代理/链路探针（而非仅仅 `systemctl is-active`）验证故障确实缓解且未引入关联劣化。一旦验证失败或指标恶化，**自动执行 LKG 回滚并拉响高级别人工告警**。
6. **护栏 6 — 全因果链审计账本（Causal Provenance Ledger）：**
   每一笔自动触发的 Operation 必须在 `operation_journal` 与 `Timeline` 中写入不可篡改的因果链：`trigger_finding_id` → `raw_metric_snapshot` → `scoring_diff` → `guardrail_eval_report` → `plan_id` → `verify_result`。

### 4.4 首批 `bounded-auto` 受控场景示例

- **有租约的异常用户自愈限速（Lease-Bound Auto-Throttle）：**
  逐用户 QoS capability 通过隔离、重启和回滚验证后，持续异常且同节点负载上升可触发有租约的限速计划。租约到期恢复基线，仍有异常时转交人工评估。
- **受管进程死锁的有界恢复：**
  当真实代理探针连续失败而主机 SSH 存活、且 `NRestarts` 在冷却窗内未超限，允许自动执行一次受管 `restart sing-box` 或 `restart vincula-accountd` 并复核探针恢复；若重启一次仍无效，立刻停止自动重启并升级告警（绝不陷入无限重启循环）。
- **基于 0.8 Intent 的受限自动主备切换：**
  使用 `0.8` 抗震荡状态机生成的计划，按 `0.9` 的六项护栏核对切换授权、容量、观测与中断预算，经 LKG 事务激活后用真实路径探针验证并记录结果。

---

## 5. VCL 1.0+ — Zero-Touch Private Edge Appliance（零维护私有边缘网络家电）

到了 `1.0+`，Vincula 在控制平面、数据平面与自动化上已然成熟，最后一块拼图是**消除长期运行中的日常运维手工摩擦（Toil）**，让整套系统真正实现“部署后可连续平稳运行数年”。

### 5.1 零接触控制通道与短期凭证轮换（Zero-Touch Trust & Ephemeral Credentials）

回顾 `0.5.4`/`0.5.5` 现场踩坑：静态 SSH 公钥分发、手工管理 `known_hosts`、以及长期有效的节点密钥始终是规模扩大后的运维负担。`1.0+` 引入可离线运行的本机微证书颁发机构（Controller-Local Ephemeral CA）：

- **SSH 短期证书体系（Short-Lived SSH Certificates）：**
  - **Host CA：** Node 在 `provision` 或首次接入时由本地私钥生成 CSR 并由 Controller CA 签发主机证书，彻底消除跨电脑迁移 Workspace 后 `known_hosts` 失同步或首次连接手工核对指纹的痛点。
  - **User / Role CA：** Controller 为 `admin` / `operator` / `observer` 动态签发数分钟至数小时有效的 SSH 证书，并在证书 `principals` 与 `extensions` 中硬编码受限命令角色。即使某个工作站临时凭据泄露，也在极短 TTL 后自动失效。
- **数据面双活无缝轮换（Grace-Period Overlap Rotation）：**
  对 `0.7.0` 的 Node Transit 密钥以及用户级/REALITY 参数支持 **“生成新凭据 → 双活期广播（新旧同时有效） → 客户端/Entry 切换 → 宽限期满撤销旧凭据”** 的零断流轮换流水线。

### 5.2 南向客户端订阅交付面（Client Profile Delivery Plane）

在 `0.6.0` 实现 R-03（改端口/SNI）与 `0.7.x` 实现多跳后，最大的最后一公里问题在于：**服务端改完了，客户端配置文件怎么安全更新？**

在严守 **INV-05（Node 默认不新增公网管理端口）** 的前提下，`1.0+` 由 Controller 承担南向配置编译器角色：

- **端到端加密签名 Profile Bundle：**
  Controller 从 Workspace 与节点权威状态直接编译生成标准化的客户端配置包（如 Sing-box client config、Mihomo/Clash profile），并使用每个用户独立的公钥/预共享密钥加密与签名。
- **只读静态分发与零信任拉取：**
  客户端订阅源可导出至任意受控的只读静态分发位置（如本地离线导出、内网受限静态服务或用户自带加密存储），Node 本身不承载任何订阅 HTTP Server 或凭据聚合库，保持 Node 端零新增公网攻击面。

### 5.3 显式应用感知边缘服务（Explicit Application-Aware Edge Services）

严格遵守 `Master SPEC §14` 的红线：**永不做透明 TLS 拦截或隐式代理缓存**。在此前提下，`1.0+` 可在 Node 上提供按 Desired Policy 显式启用的边缘增值组件：

- **策略驱动的边缘 DNS（Policy-Aware DoH/DoT Resolver）：**
  与 `0.6.2` 规则组和 `0.8` 应用路由联动，在 Entry/Egress 按预设策略选择分流解析与防污染缓存，将 CDN 地域就近性（CDN Locality）与 DNS 零泄漏统一纳入可验证的 `vcl verify` 指标。
- **声明式分流与边缘代理辅助：**
  对明确声明的包管理镜像、软件分发源等场景，通过显式策略路由至指定低成本/高带宽 Egress（如结合 `0.6.2` 规则组放行或定向限速），无需对加密流量做任何拆包篡改。

### 5.4 多年期存储自平衡与联邦多工作区（Long-Horizon Maintainability）

基于 `0.5.5` 奠定的 `1.4 GB / 3.8 GB` 大库安全底座及 `0.6.4` 的验证归档机制，`1.0+` 将实现长期无人值守存储运维：

- **多年期自平衡存储流水线（Self-Maintaining Storage）：**
  后台定期自动执行：`增量差异归档导出 (.vclaudit.age)` → `独立沙盒校验与抽样恢复验证` → `写入 history_coverage 覆盖边界` → `按 retention 有界修剪原始连接` → `空闲窗口低负载增量 VACUUM/整理`。全程遵循“未验证不删除”原则，即便运行 5 年以上，`accounting.db` 与 `fleet.db` 体积仍保持在预设上限内稳态运转。
- **受控多工作区联邦视图（Read-Only Multi-Workspace Federation）：**
  对于需要按业务线或地域拆分多个独立 Controller Workspace 的场景，支持在不合并管理私钥与 `admin` 控制权的前提下，提供只读聚合观察面与跨 Fleet 容量汇总，兼顾规模扩展与故障域绝对隔离。

---

## 6. 各大阶段边界与前置门禁总览

| 阶段 | 核心定位 | 强制前置门禁 | 标志性突破 |
| --- | --- | --- | --- |
| **0.5.x** | Observable Appliance | [H05 已签署](../evidence/0.5.5/HUMAN_ACCEPTANCE.md)，24h 连续窗口含 6/7 实机，另有 10 模拟节点 / 2h | 可信观测事实、Schema-5 账本、独立 Observer、大库兼容 |
| **0.6.x** | Declarative Controller | **H06** 含 SSH、Policy/Egress、维护和 24h soak。QoS 实测通过或记录延期 | Desired/Diff/LKG 事务、R-03、Traffic Policy v0.1、Egress 隔离 |
| **0.7.x** | Programmable Data Plane | **H07** 含 Transport ADR、静态两跳、切换影响和去重对账 | Transit ACL、2-Hop 编译、Link Probe、人工批准切换、Entry 权威计量 |
| **0.8.x** | Intent Traffic Engineering | H07 PASS + TE 仿真/抗震荡基准矩阵 | 北向路由意图、多维效用评分、非对称抗震荡切换、应用感知 TE |
| **0.9.x** | Guardrailed Automation | 0.8.x 评分稳定性验证 + 六大护栏故障注入矩阵 | 分级自治模式、爆炸半径/令牌桶熔断、因果审计账本、自愈闭环 |
| **1.0+** | Zero-Touch Edge Appliance | 0.9.x 长期无 P0/P1 闭环运行记录 + 安全审计 | 短期 SSH/Transit CA、端到端加密客户端交付、多年期存储自平衡 |

> **结语：** Vincula 的演进路径并非堆砌复杂分布式系统，而是持续在 **“Controller 集中化智能”** 与 **“Node 极简确定性静态退化”** 之间保持工程张力。`0.5.5` 为这套体系打下了可信观测与大容量存储的地基；`0.6.x` 与 `0.7.x` 将完成声明式运维与可编程数据平面；而在 `0.8.x`～`1.0+` 中，所有意图计算与闭环自治都将建立在可验证、可回退、有硬性护栏的坚实底座之上。
