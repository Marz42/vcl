# VCL 0.5.x–0.7.x Master Development SPEC

> 状态：Draft / Planning Baseline  
> 适用范围：VCL 0.5.x、0.6.x、0.7.x  
> 前置基线：Controller 0.4.5；新 provision payload 为 Node 0.3.2；Controller 0.4.5 最低兼容 Node 0.3.1  
> 目标：从“VPS Fleet Manager”演进为“集中控制、可观测、可声明、可编程数据平面”的专用 SDN Controller

---

## 0. 规范约定

本文使用以下规范词：

- **MUST / 必须**：版本发布不可缺少的要求。
- **MUST NOT / 禁止**：不得违反的安全或架构约束。
- **SHOULD / 应当**：默认实现方向；如偏离必须在 SPEC / PR 中说明理由。
- **MAY / 可以**：非发布阻塞项。

每个子版本都必须经历：SPEC Gate → Offline Gate → Integration Gate → Live Gate → Release Gate。任何没有真实执行的 Live 项必须标记 `PENDING LIVE`，不得伪造 PASS。

---

# 1. 产品定位与演进目标

VCL 0.4.x 已完成节点安装、Adopt / Provision / Replace、用户管理、Workspace / Fleet cache、流量审计、备份恢复和本地 WebUI 等生产基础。

0.5.x–0.7.x 不再以“继续增加 CLI 功能”为主要目标，而是完成三个能力跃迁：

| 版本 | 定位 | 核心问题 |
|---|---|---|
| **0.5.x** | Observable Appliance / Observation Plane | 网络现在实际上怎么样？ |
| **0.6.x** | Declarative Controller / Reliable Operations | 网络应该是什么状态，如何安全达到该状态？ |
| **0.7.x** | Programmable Data Plane | 用户流量应该经过什么数据路径？ |

长期演进关系：

```text
0.4 Fleet Manager
        ↓
0.5 Observable Fleet
        ↓
0.6 Declarative Controller
        ↓
0.7 Programmable Network
        ↓
0.8 Traffic Engineering          [本文不实现]
        ↓
0.9 Closed-loop Automation       [本文不实现]
```

---

# 2. 总体架构

## 2.1 控制平面

VCL 保持单 Controller 对多 Node 的星型控制拓扑：

```text
                    Controller
                  /     |      \
                 /      |       \
             Node A   Node B   Node C
```

Node 之间：

- MUST NOT 交换 authoritative control state；
- MUST NOT 使用 gossip / distributed consensus；
- MUST NOT 接受其他 Node 的管理指令；
- MAY 在 Controller 调度下执行 bounded node-to-node measurement；
- 0.7.x 开始 MAY 形成 node-to-node **数据平面**连接。

核心原则：

> **Centralized control, programmable distributed data plane, controller-coordinated measurement, no distributed authority.**

## 2.2 Controller 逻辑分层

```text
CLI / WebUI
     │
     ▼
Application / Fleet Service
     │
     ├───────────────┐
     ▼               ▼
Observation       Control
Service           Service
     │               │
     └───────┬───────┘
             ▼
       SSH Transport
             │
             ▼
          VCL Node
```

SSH 是 transport，不是 VCL 的业务协议。机器可读能力必须通过版本化 JSON contract 暴露。

## 2.3 Node 设计目标

Node 必须逐步成为一个 **boring appliance**：

- 权限有限；
- 状态有限；
- 接口有限；
- 默认 fail-static；
- 行为可验证；
- Controller 离线不影响已有代理服务；
- observation / accounting 故障不影响 data plane；
- 除显式 mutation 外不自行改变 policy / desired state。

---

# 3. 跨版本架构不变量

以下约束从 0.5.0 起视为长期不变量。

| ID | 不变量 |
|---|---|
| INV-01 | Controller 是唯一 authoritative control plane。 |
| INV-02 | Node 之间不传播控制状态，不做 gossip / distributed authority。 |
| INV-03 | Controller 不可达时，现有 data plane MUST 继续按 Last Known Good 状态运行。 |
| INV-04 | telemetry / monitor / accounting / UI 故障 MUST NOT 停止 sing-box。 |
| INV-05 | 默认不新增公网管理 listener / HTTP API。 |
| INV-06 | `telemetry` / `health` / `verify` / `inspect` 必须严格 read-only。 |
| INV-07 | 所有 mutation 必须 typed、显式、可审计，不提供 generic remote exec。 |
| INV-08 | 所有配置 mutation 必须 stage → validate → activate → verify。 |
| INV-09 | Node 必须保留 Last Known Good，可在 activation 失败时恢复。 |
| INV-10 | URI、UUID、Reality private key、Clash secret、SSH private key、SOCKS password 等 secret 不得进入普通日志、telemetry、Fleet cache、operation journal。 |
| INV-11 | Node persistent state 必须 bounded：有 retention、size bound、cleanup policy 和 corruption behavior。 |
| INV-12 | read-only observation 发现故障时禁止隐式“顺便修复”。 |
| INV-13 | 外部 Egress / Path 失败默认 fail-closed；不得静默 direct fallback，除非策略显式允许。 |
| INV-14 | Node 可以恢复 transient runtime failure，但禁止自主改变 desired state / policy。 |
| INV-15 | 新功能必须通过 Application/Fleet Service 进入 CLI / UI，禁止继续无边界增长单体 CLI handler。 |

---

# 4. 兼容性与版本契约

## 4.1 基线

0.4.5 基线：

- Controller：0.4.5
- 新 provision payload：Node 0.3.2
- Controller 0.4.5 最低兼容 Node：0.3.1

## 4.2 兼容策略

### Controller 0.5.x

- MUST 继续识别并管理 Node 0.3.1 / 0.3.2 的已有 0.4 功能；
- Node 0.3.x 无 `telemetry/v1` 时显示 `UNSUPPORTED`，不得判为故障；
- 0.5 observation 完整能力要求 Node 0.5.x。

### Controller 0.6.x

- MAY 继续为旧 Node 提供 legacy management / upgrade path；
- Desired State / Reconciliation mutation 的完整支持要求 Node 0.6.x；
- Node 0.5.x 可作为 observation-only / limited-management Node；
- 禁止为了使用 Controller 0.6 而自动强制升级全部 Node。

### Controller 0.7.x

- 单节点管理能力继续按 capability negotiation 工作；
- Path / transit / node identity 能力要求参与节点均支持相应 0.7 capability；
- 不满足 capability 的节点不得被编译进 Path。

## 4.3 Node 升级不变量

任何 Node 原地升级 MUST 保留：

- node_id；
- instance_id；
- Reality keypair；
- 用户 UUID；
- user_id / credential_id；
- accounting history；
- 原有 URI 的连接语义；
- 当前有效 desired / runtime state（除非 SPEC 明确包含迁移）。

---

# 5. 共享核心数据模型

这些模型在不同版本分阶段落地，但名称和语义应从一开始保持一致。

## 5.1 Capability

```json
{
  "schema": "capabilities/v1",
  "node_version": "0.5.0",
  "capabilities": ["telemetry/v1", "health/v1", "inspect/v1"]
}
```

## 5.2 Observed State

Controller 通过 telemetry / inspect / probe / audit 获取的事实，不是 desired state。

## 5.3 Finding

```json
{
  "finding_id": "...",
  "type": "AUDIT_STALLED",
  "category": "accounting",
  "subject": "node:lax-01",
  "severity": "warning",
  "state": "ACTIVE",
  "first_seen": "...",
  "last_seen": "...",
  "evidence": {},
  "explanation": "..."
}
```

## 5.4 Desired State

Workspace 中的 authoritative declaration。

## 5.5 Operation

```json
{
  "operation_id": "...",
  "type": "user_reconcile",
  "target": "user:alice@node:lax-01",
  "precondition": {},
  "proposed_changes": {},
  "risk": "low",
  "postcondition": {},
  "rollback": {}
}
```

## 5.6 Policy

用于 QoS、Egress 及未来 automation，不能直接等同于命令。

## 5.7 Egress

逻辑出口资源。0.6.3 首批支持 `direct`、`socks5`。

## 5.8 Path

0.7 引入的数据路径资源。0.7 初期仅允许静态 2-hop。

## 5.9 Link

Controller 维护的 Node A → Node B 逻辑测量关系，不是控制平面 peer relation。

---

# 6. 通用门禁体系

每个子版本必须满足以下通用门禁，并在对应 release evidence 中记录。

## G0 — SPEC Gate

编码前必须：

1. 更新目标版本 SPEC；
2. 更新 capability / schema contract；
3. 更新 compatibility matrix；
4. 定义 Acceptance Criteria；
5. 定义 Live Matrix；
6. 明确 Non-Goals；
7. 工作区干净，创建目标 release branch。

## G1 — Offline / Unit Gate

必须：

- 全量单元/集成测试通过；
- `git diff --check` 通过；
- JSON schema fixtures 正反例覆盖；
- secret redaction tests 通过；
- failure injection 覆盖目标 mutation / observation failure；
- 测试不得污染真实 HOME / Workspace / known_hosts；
- artifact digest / manifest 校验通过。

## G2 — Integration Gate

必须覆盖：

- CLI 与 WebUI 共享 service layer；
- mixed-version 行为；
- Controller crash / restart；
- Node-side daemon crash；
- corrupted cache / journal / DB row 的容错；
- concurrency / locking；
- idempotency（适用时）。

## G3 — Security Gate

必须检查：

- public listeners；
- process privileges；
- file owner/mode；
- systemd sandbox；
- secret scan；
- no silent privilege fallback；
- no silent direct fallback；
- management path 不新增未声明攻击面。

## G4 — Live Gate

必须在真实 VPS 上执行版本专属 Live Matrix。未执行项必须为 `PENDING LIVE`。

## G5 — Release / Soak Gate

发布前：

- required CI 全绿；
- Live Matrix 必须项目 PASS；
- release evidence 完整；
- 生产/类生产 soak 无 P0/P1；
- 没有 unexplained data corruption / secret exposure；
- 文档、CHANGELOG、manual、compatibility matrix 与实际一致。

---

# 7. VCL 0.5.x — Observation Plane

## 7.0 版本目标

0.5.x 负责建立可靠“事实层”，回答：

- Node 是否可达？
- sing-box 是否运行？
- 代理服务是否真的可用？
- accounting 是否可信？
- 资源是否异常？
- 配置是否漂移？
- 发生了什么变化？

0.5.x **不负责自动修复**。

## 7.0 Non-Goals

- 自动重启/修配置；
- 自动 QoS；
- 自动告警处置；
- Egress binding；
- 多跳；
- 动态路由；
- generic RMM；
- generic shell；
- billing-grade accounting；
- DPI / TLS MITM。

---

## 7.1 VCL 0.5.0 — Observation Foundation

### 7.1.1 Capability Discovery

新增：

```bash
vcl capabilities --json
```

要求：

- schema：`capabilities/v1`；
- 返回 Node version 和 capability list；
- future unknown capability MUST 被忽略但保留；
- malformed / oversize response MUST fail closed；
- Controller 禁止通过硬编码版本号推测 feature。

### 7.1.2 Telemetry v1

新增：

```bash
vcl telemetry snapshot --json
```

最小字段：

```text
node_id / instance_id
observed_at
uptime
load1/load5/load15
memory total/used
filesystem total/used
network rx/tx counters
sing-box active / connection_count / restart info
accountd active / last_poll_age / export_seq / last_event_age
```

约束：

- 默认不访问公网；
- 不执行 package update；
- 不扫描完整 journal；
- 不执行昂贵磁盘扫描；
- response SHOULD ≤ 64 KiB；
- 单次调用 SHOULD 在普通低配 VPS 上 p95 ≤ 2s；
- 无 secret。

### 7.1.3 Observation Credential Routing

Controller 支持：

```text
observe credential
admin credential
```

规则：

- 配置 observe credential 后，observation MUST 使用 observe route；
- observe auth failure 时禁止 silent admin fallback；
- mutation 不得使用 observe identity；
- 日志只记录 credential class，不记录 key material。

### 7.1.4 Restricted Observer Identity

Node SHOULD 支持独立 observer 用户：

- no sudo；
- no PTY；
- no agent forwarding；
- no port forwarding；
- no X11 forwarding；
- 仅可调用 approved read-only command。

若 0.5.0 不能完成 forced-command，可在 0.5.x 内渐进完成，但 observe/admin route 语义不得变化。

### 7.1.5 Node Observability Hardening

必须审查：

- `vincula-accountd` 是否可 de-root；
- 独立 `vincula-accountd` service user；
- accountd 只读取非 secret identity mapping；
- Clash API credential 以最小权限方式注入；
- systemd `NoNewPrivileges` / `ProtectSystem` / `ProtectHome` / capability bounding；
- accountd compromise 不应直接获得 Node root authority。

若 de-root 发现阻塞项，必须形成 documented blocker，不能静默保留 root 而声称完成 hardening。

### 7.1.6 Node In-Place Upgrade（Firmware）

0.5.0 引入 Controller 编排的单节点固件升级（详细见 [`V0.5.0_Spec.md`](V0.5.0_Spec.md) §三）：

```bash
vcl-fleet node upgrade plan NODE
vcl-fleet node upgrade apply NODE
```

要求：

- 支持 **0.3.1 / 0.3.2 → 0.5.0**（及同 minor patch）；保留 identity、URI、accounting；
- typed mutation + backup + migrate rollback；禁止 generic remote exec；
- data plane 断流预算 **≤3s**（Live 测量）；
- 升级后 Node 暴露 `capabilities/v1` / `telemetry/v1`。

0.6.4 在此基础上扩展 fleet 级 upgrade plan、maintenance window 与更完整 rollback 状态机。

### 7.1.7 Controller Service Boundary

新增 0.5 功能 MUST 通过可测试 service boundary。建议模块：

```text
fleet_service
ssh_transport
observation
telemetry
operations
```

禁止继续把完整业务逻辑堆入 `vincula-fleet.py` CLI handler。

### 7.1.8 0.5.0 门禁

**G0**
- `capabilities/v1`、`telemetry/v1` schema 冻结；
- legacy Node 行为定义完成；
- Node upgrade plan/apply 合同冻结。

**G1**
- schema 正反例；
- oversize / malformed / missing field；
- secret redaction；
- observer/admin route tests；
- telemetry 不执行 mutation 的回归测试；
- upgrade allowlist / rollback / inject fail。

**G2**
- Controller 0.5.0 + Node 0.3.1 / 0.3.2：显示 UNSUPPORTED 而非 ERROR；
- Controller 0.5.0 + Node 0.5.0：capability negotiation 正常；
- CLI/UI 通过 service layer 获取 observation；
- 0.3.x → 0.5.0 upgrade identity/URI preserved（fixture）。

**G3**
- observer 无 mutation 权限；
- no silent admin fallback；
- public listener 不增加；
- telemetry 输出无 secret。

**G4 Live**
1. Fresh Node 0.5.0 telemetry；
2. **`node upgrade apply`**：0.3.x → 0.5.0，identity/URI 不变，断流 ≤3s；
3. observer credential 正常读取；
4. observer credential 被破坏后 observation 明确 AUTH_FAILED；
5. Controller 不可达期间代理仍工作。

**G5**
- 至少 1 个真实节点连续调用 telemetry 1000 次无状态增长/崩溃；
- 无 P0/P1。

---

## 7.2 VCL 0.5.1 — Monitoring & Health

### 7.2.1 Fleet Monitor

新增：

```bash
vcl-fleet monitor
vcl-fleet monitor NODE
```

第一版为 foreground process，不要求 daemon。

默认：

- interval：30s；
- per-node timeout；
- concurrency cap；
- jitter；
- exponential backoff；
- 单节点失败不终止整个 monitor。

### 7.2.2 Telemetry Storage

Controller DB 新增：

```text
telemetry_samples
telemetry_rollup_5m
telemetry_rollup_hourly
```

推荐 retention：

- raw：24h；
- 5m：7d；
- hourly：90d。

必须 bounded，并对 crash/restart 安全。

### 7.2.3 Health State Machine

统一状态：

```text
HEALTHY
SUSPECT
DEGRADED
UNREACHABLE
RECOVERING
```

至少分别计算：

- Node Health；
- Observation Health；
- Proxy Service Health；
- Accounting Health。

Overall Health MUST 有解释依据，禁止黑盒单一 bool。

### 7.2.4 Synthetic Proxy Probe

必须区分：

```text
process alive ≠ service usable
```

Controller 使用专用测试身份完成真实代理 probe：

```text
Controller → VLESS/Reality → Node → known HTTPS endpoint
```

采集：

- success/failure；
- connect latency；
- HTTPS / TTFB；
- observed_at。

测试身份不得与普通用户 credential 混用。

### 7.2.5 Monitoring UI

增加：

- Fleet Health；
- Node health state；
- telemetry age；
- CPU/load、RAM、disk；
- connections；
- network rate；
- sing-box/accountd 状态；
- synthetic proxy probe。

UI 只读 Controller local cache；HTTP GET 禁止触发 SSH。

### 7.2.6 0.5.1 门禁

**G1**
- state machine transition unit tests；
- jitter/backoff/concurrency；
- retention/rollup；
- probe timeout / TLS failure / DNS failure fixtures。

**G2**
- 10+ simulated nodes；
- 单节点 timeout 不拖慢整轮；
- Controller crash/restart 后 monitor 可恢复；
- corrupt telemetry row 不导致 UI 崩溃。

**G3**
- probe credential 独立且无输出泄漏；
- UI GET 无 SSH；
- monitor 无 mutation。

**G4 Live**
- ≥10 Node（真实或受控混合矩阵）以 30s interval 运行 ≥2h；
- 停止 sing-box → Proxy Health 正确变 DEGRADED/UNREACHABLE；
- 停止 accountd → Accounting Health 变 DEGRADED，但 proxy 继续；
- 阻断 SSH → Node 状态按 SUSPECT→UNREACHABLE 迁移；
- 恢复后进入 RECOVERING→HEALTHY；
- kill Controller 不影响用户代理。

**G5**
- 推荐 24h 类生产 soak；
- 无 DB 无界增长、无 alert（本版本尚无通知）风暴、无 data-plane side effect。

---

## 7.3 VCL 0.5.2 — Findings & Audit Observability

### 7.3.1 Finding Model

新增统一 Finding store：

```text
finding_id
type
category
subject
severity
state
first_seen
last_seen
evidence
explanation
```

0.5.2 最低状态：

```text
ACTIVE
RESOLVED
```

为 0.6 预留 ACKNOWLEDGED / SUPPRESSED。

### 7.3.2 Audit Pipeline Health

必须监控：

- accountd heartbeat；
- last poll age；
- export_seq；
- export_seq progression；
- last event age；
- Controller received cursor；
- sync lag；
- DB schema；
- SQLite health；
- retention cursor/gap semantics。

Finding 至少：

```text
AUDIT_STALLED
EXPORT_GAP
SYNC_LAG
SCHEMA_MISMATCH
ACCOUNTING_DB_CORRUPT
```

目标：知道审计何时不可信，而不是把 approximate accounting 伪装成 billing-grade metering。

### 7.3.3 Basic Traffic Anomaly Detection

0.5.2 只检测，不 mutation。

第一版优先可解释统计方法：

- rolling median；
- MAD；
- EWMA；
- percentile；
- rate-of-change；
- consecutive duration threshold。

至少支持：

```text
USER_TRAFFIC_SPIKE
USER_CONNECTION_SPIKE
SUSTAINED_TRAFFIC_ANOMALY
DESTINATION_DIVERSITY_ANOMALY [可选，数据足够时]
```

### 7.3.4 Node Anomaly Detection

至少：

```text
DISK_PRESSURE
MEMORY_PRESSURE
SERVICE_RESTART_LOOP
TELEMETRY_STALE
NETWORK_RATE_ANOMALY
```

### 7.3.5 Incident Timeline Foundation

将以下事件映射到统一时间轴：

- telemetry state change；
- Finding open/resolve；
- operation journal；
- audit anomaly；
- service lifecycle；
- sync/probe/verify results。

Timeline MUST 只使用本地 Controller 数据，不为展示临时 SSH。

### 7.3.6 0.5.2 门禁

**G1**
- Finding dedupe/open/resolve；
- audit gap/stall fixtures；
- synthetic traffic spike；
- baseline statistical tests；
- zero mutation assertions。

**G2**
- accounting export gap 故障注入；
- monitor 与 finding pipeline 并发；
- timeline 顺序和 corrupt entry 容错。

**G3**
- evidence 不含 UUID/URI/secret；
- Finding explanation 不拼接敏感 argv；
- anomaly detector 无 mutation hook。

**G4 Live**
- 停止 accountd，成功产生 AUDIT_STALLED；
- 恢复后 Finding RESOLVED；
- 注入/制造用户流量尖峰，产生对应 Finding；
- 普通波动下不得产生明显持续误报；
- Timeline 能关联一次真实 service disruption。

**G5**
- production-like soak 中 Finding 数量 bounded；
- 无持续重复 Finding flood。

---

## 7.4 VCL 0.5.3 — Inspect & Drift

### 7.4.1 Inspect v1

新增：

```bash
vcl inspect --json
```

覆盖：

- OS/kernel；
- CPU/RAM/swap；
- disk/filesystem；
- clock/NTP；
- interfaces；
- TCP congestion control；
- qdisc；
- selected sysctl；
- file/socket limits；
- sing-box/accountd service state；
- VCL/sing-box version；
- firewall；
- public/loopback listeners；
- package update / reboot-required 的廉价状态（禁止 inspect 隐式执行完整升级）。

### 7.4.2 Desired Baseline / Drift

0.5.3 只比较，不 reconcile。

最少：

```text
MATCH
DRIFT
UNKNOWN
```

重点检查：

- expected public listeners；
- Clash API loopback-only；
- expected service enabled/active；
- expected version；
- runtime artifact / unit drift。

### 7.4.3 Non-secret Config Fingerprint

生成 canonical fingerprint：

- effective non-secret config hash；
- systemd unit hash；
- VCL runtime artifact hash；
- sing-box binary digest。

禁止把完整 secret config 拉回 Controller。

### 7.4.4 Strengthen `vcl verify`

统一输出：

```text
Identity       PASS/FAIL
Configuration  PASS/FAIL
Integrity      PASS/FAIL
Permissions    PASS/FAIL
Services       PASS/FAIL
Listeners      PASS/FAIL
Accounting     PASS/FAIL
Data Plane     PASS/FAIL
```

新增机器接口：

```bash
vcl verify --json
```

### 7.4.5 0.5.3 门禁

**G1**
- inspect schema；
- supported OS fixtures；
- unexpected listener / service / hash drift；
- verify JSON；
- read-only regression。

**G2**
- 在 inspect 前后比较关键文件 hash、service restart count、mtime，证明无 mutation；
- drift Finding 与 telemetry 不冲突。

**G3**
- inspect 输出不含 Reality private key、UUID、Clash secret；
- public listener inventory 准确；
- 权限异常可识别。

**G4 Live**
1. 手动新增非预期 public listener → 检出；
2. 修改受管 unit / non-secret config → 检出 drift；
3. 恢复后 MATCH；
4. `verify --json` 与人工检查一致；
5. inspect 全过程不重启服务。

**G5**
- 0.5.x 全链路：monitor → health → finding → inspect → timeline 稳定；
- 0.5.x Release Candidate 在当前生产节点上 soak，无 data-plane regression。

---

# 8. VCL 0.6.x — Declarative Controller & Reliable Operations

## 8.0 版本目标

0.6.x 建立：

```text
Desired State
      ↓
Observed State
      ↓
Diff
      ↓
Plan
      ↓
Apply
      ↓
Verify
      ↓
Rollback / Commit
```

这是 VCL 从 imperative Fleet Manager 转为 declarative Controller 的分水岭。

## 8.0 Non-Goals

- unattended closed-loop remediation；
- 自动动态路由；
- node-to-node transit；
- 3+ hop；
- generic arbitrary shell；
- 背景自动系统升级；
- 自动 fallback 到 direct；
- distributed controller。

---

## 8.1 VCL 0.6.0 — Desired State & Reconciliation

### 8.1.1 Desired State Model

Workspace 正式成为 authoritative desired state。

首批资源：

```text
Node
User
Deployment
Policy [可先定义 schema]
Egress [可先定义 schema]
```

示例：

```yaml
users:
  alice:
    enabled: true
    nodes:
      - lax-01
```

### 8.1.2 Desired vs Observed Diff

统一结果：

```text
MATCH
DRIFT
MISSING
EXTRA
DEGRADED
UNKNOWN
```

### 8.1.3 Reconciliation Engine

0.6.0 默认 `plan-only`：

```text
Desired → Observed → Diff → Plan
```

不得首次上线即 unattended apply。

### 8.1.4 Operation Model

所有 mutation 必须使用统一 Operation contract：

- operation_id；
- type；
- target；
- precondition；
- proposed changes；
- risk；
- postcondition；
- rollback；
- result。

### 8.1.5 PLAN_STALE

Apply 前必须重新检查 precondition。

状态变化时：

```text
PLAN_STALE
```

拒绝使用旧 plan 修改 Node。

### 8.1.6 Idempotency

若 desired 已满足：

```text
NOOP
```

禁止重复写 config / restart service。

### 8.1.7 Node Config Transaction & LKG

必须实现逻辑状态：

```text
staged
current
previous (LKG)
```

mutation：

```text
generate
→ validate schema
→ sing-box check
→ stage
→ atomic activate
→ health gate
→ commit
```

失败：

```text
restore LKG
→ restart/reload if required
→ verify previous state
```

### 8.1.8 0.6.0 门禁

**G1**
- desired schema migration；
- diff matrix；
- NOOP；
- PLAN_STALE；
- operation serialization；
- rollback state machine。

**G2**
- 连续 reconcile 产生 NOOP；
- plan 后人工改 Node → apply 返回 PLAN_STALE；
- activation 中途 kill process → 重启后状态可恢复；
- config write 原子性验证。

**G3**
- plan/journal 无 secret；
- read-only reconcile plan 不 mutation；
- LKG 权限正确。

**G4 Live**
1. User MISSING → plan → approve → apply → verify；
2. DRIFT → plan；
3. PLAN_STALE live；
4. 故意 staged invalid sing-box config → zero activation；
5. activation health fail → LKG rollback；
6. Controller loss 不改变当前状态。

**G5**
- 生产样本上至少完成一轮 desired migration + no-op reconcile；
- 无 identity/URI/accounting regression。

---

## 8.2 VCL 0.6.1 — Alerting & Incident Operations

### 8.2.1 Finding Lifecycle

扩展状态：

```text
ACTIVE
ACKNOWLEDGED
SUPPRESSED
RESOLVED
```

### 8.2.2 Alert Engine

实现：

- debounce；
- deduplication；
- grouping；
- cooldown；
- severity；
- recovery notification。

示例：

```text
1 failed probe → SUSPECT
3 consecutive failures / threshold duration → ALERT
2 successful probes → RESOLVED
```

### 8.2.3 Notification Adapter

至少一个生产可用 adapter；架构预留：

- Telegram；
- Email；
- Webhook。

Notification credential 必须 secret-ref 化。

### 8.2.4 Maintenance Window

支持：

- planned restart；
- planned reboot；
- planned upgrade；
- node / fleet scoped window。

窗口内相关 Finding 可被 SUPPRESSED，但原始 observation 仍记录。

### 8.2.5 Acknowledge / Silence

管理员可以：

- acknowledge finding；
- silence node；
- silence finding type；
- 设置有限时长。

所有操作进入 operation journal。

### 8.2.6 0.6.1 门禁

**G1**
- debounce/dedupe/group/cooldown；
- state lifecycle；
- notification adapter retry；
- secret redaction。

**G2**
- flap injection；
- 100 repeated same Finding 不产生 100 条独立通知；
- maintenance window suppression；
- Controller restart 后 alert state 可恢复。

**G3**
- notification token/password 不进入 journal；
- webhook 不允许注入任意本地 shell；
- acknowledge/silence 权限明确。

**G4 Live**
1. 真实 Node outage → 单一聚合告警；
2. 恢复 → RESOLVED；
3. maintenance window 中 planned reboot 不产生事故告警；
4. 非 planned outage 仍能告警；
5. 通知渠道失败不会影响 monitor/data plane。

**G5**
- 24h soak 无 alert storm；
- Notification adapter 故障不造成队列无界增长。

---

## 8.3 VCL 0.6.2 — QoS & User Policy

### 8.3.1 Policy Resource

示例：

```yaml
policies:
  standard:
    bandwidth: 20mbps
    max_connections: 300
```

Policy 是 desired state，不是临时 shell command。

### 8.3.2 Enforcement Backend Research Gate

在冻结实现前必须完成短期 spike：

- sing-box 原生能力；
- tc / nftables 等 Linux enforcement；
- per-user identity 如何映射到 enforcement；
- TCP/UDP 行为；
- rollback；
- CPU/内存开销；
- 与 accountd/route 的耦合。

没有可证明的 per-user isolation，不得宣布 QoS production-ready。

### 8.3.3 User → Policy Binding

```yaml
users:
  alice:
    policy: standard
```

### 8.3.4 Per-user Rate Limit

第一版只要求稳定、可验证的 per-user rate limit。

不做复杂 HTB hierarchy / global scheduler，除非 enforcement backend 必须。

### 8.3.5 Connection Guard

至少支持语义：

- soft warning threshold；
- hard guard（backend 可行时）。

目标是防止单用户 FD / connection exhaustion 拖死整个 Node。

### 8.3.6 Finding → Recommendation

0.5 的 anomaly Finding 可生成：

```text
Recommended Action:
limit user alice to 20Mbps for 30m
```

0.6.2 允许：

```text
mode = recommend
mode = approve
```

禁止默认 `automatic`。

### 8.3.7 0.6.2 门禁

**Research Gate**
- enforcement backend benchmark / security review 完成；
- rollback 机制明确。

**G1**
- policy schema；
- user binding；
- idempotent apply；
- rate accounting tests。

**G2**
- Alice limit 不影响 Bob；
- policy remove 后恢复 baseline；
- service restart 后 policy 状态符合 desired；
- no-op reconcile 不重复重建规则。

**G3**
- 不需要新增公网端口；
- rule ownership 明确，只删除 VCL-owned rules；
- Node 重启后 fail-static 行为定义清楚。

**G4 Live**
1. 单用户限速实测；
2. 第二用户吞吐不受明显影响；
3. UDP 行为验证；
4. policy apply/rollback；
5. 异常流量 Finding → recommendation → 人工 approve → apply。

**G5**
- 持续限速 soak 无资源泄漏；
- 不出现全节点误限速。

---

## 8.4 VCL 0.6.3 — Egress Resource & Per-user Egress Binding

### 8.4.1 Egress Resource

禁止将 SOCKS 直接硬编码为 `user.socks_url`。

新增：

```text
Egress
```

首批类型：

```text
direct
socks5
```

### 8.4.2 SOCKS5 Egress

示例：

```yaml
egresses:
  west-socks:
    type: socks5
    server: socks.example:1080
    credential_ref: secret:egress/west-socks
```

支持：

- no-auth；
- username/password（如当前实际场景需要）。

Secret 不得存入普通 Workspace 明文。

### 8.4.3 User → Egress Binding

```yaml
users:
  alice:
    egress: west-socks
  bob:
    egress: direct
```

Node 编译为：

```text
auth_user alice → socks outbound
auth_user bob   → direct
```

### 8.4.4 Egress Health Probe

至少检测：

- TCP reachability；
- SOCKS auth；
- CONNECT success；
- effective egress IP；
- latency / TTFB（bounded）。

### 8.4.5 Failure Semantics

默认：

```text
configured egress failed → user request fails
```

MUST NOT：

```text
SOCKS failed → silently direct
```

未来 fallback 必须成为显式 Policy。

### 8.4.6 DNS Semantics

必须定义并验证：

- local resolve vs remote resolve；
- SOCKS5 / SOCKS5h 等价语义；
- domain route matching；
- DNS leak；
- CDN locality。

### 8.4.7 UDP / QUIC Semantics

必须明确：

- SOCKS UDP 是否支持；
- 不支持时如何报错；
- QUIC/HTTP3 是否工作；
- 禁止静默协议降级导致不可解释行为。

### 8.4.8 Performance Validation

使用固定 A/B/C 测试：

```text
A Client → LAX VLESS → direct
B Client local dialer-proxy → LAX VLESS → SOCKS5
C Client → LAX VLESS → VPS-side SOCKS5 → target
```

记录：

- Clash/Mihomo latency：10 次 min/median/max；
- HTTPS cold TTFB：10 次 median；
- total request time；
- throughput：3 次；
- Client→LAX RTT；
- LAX→SOCKS RTT。

不设 topology-independent 的硬性性能提升比例，但 C 不得出现无法解释的额外巨大 overhead。

### 8.4.9 0.6.3 门禁

**G1**
- Egress schema；
- direct/socks compile；
- auth_user binding；
- secret ref；
- invalid credential / timeout / DNS / UDP fixtures。

**G2**
- Alice SOCKS、Bob direct；
- egress add/remove/update idempotent；
- config rollback；
- UI/CLI effective egress 一致。

**G3**
- SOCKS password 不进 argv/log/journal；
- fail-closed；
- no public management listener；
- no silent direct fallback。

**G4 Live**
1. LAX VPS + US-West SOCKS A/B/C benchmark；
2. Alice effective egress IP = SOCKS IP；
3. Bob effective egress IP = VPS IP；
4. SOCKS credential 错误 → Alice fail closed、Bob 不受影响；
5. SOCKS server down → Finding/health 可见；
6. DNS leak test；
7. UDP/QUIC 行为有明确结果。

**G5**
- 真实用户测试中无 cross-user routing；
- SOCKS failure 不影响 direct 用户；
- 性能结果进入 evidence。

---

## 8.5 VCL 0.6.4 — Controlled Maintenance

> **注：** 单节点 typed upgrade（plan/apply、0.3.1+ → 当前 Node 固件、断流 ≤3s）已在 **0.5.0** 交付（Master §7.1.6）。本节扩展 fleet 级编排、maintenance window 与更完整 rollback。

### 8.5.1 Upgrade Plan

新增 typed workflow：

```bash
vcl-fleet upgrade plan NODE
```

输出：

- current/target version；
- compatibility；
- preconditions；
- backup requirement；
- expected downtime；
- rollback plan。

### 8.5.2 Upgrade Apply

流程：

```text
preflight
→ backup
→ stage
→ apply
→ service health gate
→ proxy probe
→ commit
```

### 8.5.3 Upgrade Rollback

失败必须：

- 恢复 previous runtime/config；
- 恢复 service state；
- verify；
- 记录 PARTIAL / ROLLED_BACK；
- 不宣称跨节点 distributed rollback。

### 8.5.4 Typed Maintenance Operations

首批只允许：

```text
restart sing-box
restart accountd
reboot node
cleanup VCL-owned data
```

禁止 generic `exec NODE shell`。

### 8.5.5 Restricted Management SSH

逐步支持：

- no-pty；
- no-agent-forwarding；
- no-port-forwarding；
- forced-command / typed dispatcher；
- observer/operator/admin capability separation。

目标：

```text
SSH = authenticated transport
VCL protocol = management API
```

而不是开放通用远程 shell 给 Controller 日常使用。

### 8.5.6 0.6.4 门禁

**G1**
- upgrade plan/apply/rollback state machine；
- interrupted upgrade；
- typed operation allowlist；
- cleanup ownership tests。

**G2**
- broken target artifact → zero apply；
- post-upgrade health fail → rollback；
- Controller crash mid-upgrade → 可恢复/明确 PARTIAL；
- no arbitrary command path。

**G3**
- management SSH restrictions；
- artifact signature/digest；
- backup secret handling；
- cleanup 不删除非 VCL-owned data。

**G4 Live**
1. Node 0.6.x minor upgrade；
2. 故意 health-gate fail → rollback；
3. planned reboot + maintenance window；
4. restricted operator credential 不能执行任意 shell；
5. proxy URI/identity/accounting 保持。

**G5**
- 0.6.x RC 完成真实维护操作；
- 无不可恢复配置损坏。

---

# 9. VCL 0.7.x — Programmable Data Plane

## 9.0 版本目标

0.7.x 开始让 Controller 定义：

```text
User Intent
    ↓
Route / Path Policy
    ↓
Path
    ↓
Entry → Egress
    ↓
Internet
```

原则：

> **Static first. Observable first. No automatic routing yet.**

## 9.0 Non-Goals

- 自动路径评分并切换；
- unattended failover；
- >2-hop production path；
- node gossip；
- live TCP migration；
- arbitrary overlay mesh；
- transparent HTTPS cache；
- traffic engineering closed loop。

---

## 9.1 VCL 0.7.0 — Node Roles & Transit Identity

### 9.1.1 Node Roles

新增：

```text
entry
transit
egress
```

默认：

```text
transit = disabled
```

角色是 desired state，不能通过端口是否开放“猜”。

### 9.1.2 Node Credential

Node-to-node 使用独立 principal：

```text
node:lax-01
```

MUST NOT 复用普通用户 UUID。

### 9.1.3 Transit ACL

Egress/Transit Node 必须显式允许哪些 Node principal 接入。

未授权 Node MUST 被拒绝。

### 9.1.4 Transit Credential Lifecycle

至少支持：

- issue；
- rotate；
- revoke；
- audit；
- secret handling。

Credential compromise 可只 revoke 对应 Node，不影响普通用户。

### 9.1.5 Transit Accounting

Egress 侧识别：

```text
principal = node:lax-01
```

而不是将 Alice 的 user credential 继续传播到 Egress。

### 9.1.6 User Identity Boundary

第一版明确：

> 用户身份在 Entry 终止；Egress 只识别上游 Node principal；Controller 通过 Path 关系理解用户路径。

### 9.1.7 0.7.0 门禁

**G1**
- role schema；
- node credential lifecycle；
- ACL allow/deny；
- revoke/rotate；
- secret scan。

**G2**
- unauthorized Node rejected；
- revoked Node credential immediate fail for new sessions；
- user credential 不可作为 transit credential；
- legacy single-hop 不受影响。

**G3**
- transit 默认关闭；
- Node credential 不进入 Workspace plaintext/journal；
- attack blast radius review。

**G4 Live**
1. Node A 获得 entry；Node B 获得 egress；
2. 未授权 A→B 被拒；
3. 授权后成功；
4. revoke 后新连接失败；
5. 普通用户连接继续正常。

**G5**
- 无 accidental open transit；
- role changes 通过 plan/apply/verify。

---

## 9.2 VCL 0.7.1 — Static 2-Hop Path

### 9.2.1 Path Resource

新增：

```yaml
paths:
  jp-primary:
    hops:
      - lax-01
      - tokyo-01
```

### 9.2.2 Max Hop Guard

0.7.x production baseline：

```text
max_hops = 2
```

超过 2 hop 必须被 schema/compiler 拒绝。

### 9.2.3 Path Compiler

Controller 根据：

```text
User → Path → Node capabilities → Node-specific config
```

分别生成 Entry / Egress 所需配置。

Compiler 必须：

- 检查 role；
- 检查 capability；
- 检查 credential readiness；
- 检查 loop；
- 检查 max hops；
- 输出 deterministic plan。

### 9.2.4 Node-to-node Transport Decision Gate

在实现 freeze 前完成真实 benchmark：

首选比较：

```text
VLESS
WireGuard
```

必要时扩展：

```text
Hysteria2 / TUIC
```

测试：

- connect setup；
- HTTPS TTFB；
- TCP throughput；
- UDP/QUIC；
- 0%、1%、3% packet loss；
- CPU/RAM；
- operational complexity；
- credential rotation；
- rollback。

必须形成 transport ADR（Architecture Decision Record）后才能冻结 0.7.1 production baseline。

SOCKS5 保持 `external Egress adapter`，不默认作为 VCL 内部 node-to-node 长期 transport。

### 9.2.5 DNS Path Semantics

必须定义：

- Entry resolve vs Egress resolve；
- domain routing；
- CDN locality；
- DNS leak；
- remote resolver failure semantics。

### 9.2.6 UDP / QUIC

必须验证：

- DNS UDP；
- generic UDP；
- QUIC；
- HTTP/3；
- 不支持时显式失败。

### 9.2.7 MTU / MSS / PMTU

必须进行：

- fragmentation test；
- PMTU test；
- large TLS transfer；
- QUIC packet size；
- TCP MSS behavior。

### 9.2.8 Session Semantics

Path mutation：

```text
existing sessions → 不主动迁移
new sessions      → 使用新 path
```

禁止尝试 live TCP migration。

### 9.2.9 0.7.1 门禁

**Transport Decision Gate**
- benchmark + ADR 完成；
- baseline transport 有明确安全和维护模型。

**G1**
- path schema；
- compiler deterministic；
- role/capability/loop/max-hop validation；
- DNS/UDP/MTU fixtures。

**G2**
- static A→B path；
- path remove 恢复 direct/specified egress；
- repeated reconcile NOOP；
- Entry/Egress 单侧失败产生明确 PARTIAL，不制造半配置。

**G3**
- Node credentials 独立；
- transit listener/ACL 最小暴露；
- no user credential propagation；
- no silent direct fallback。

**G4 Live**
1. 单用户 static 2-hop；
2. direct 用户保持单跳；
3. TCP 网站访问；
4. UDP；
5. QUIC/HTTP3；
6. DNS leak；
7. large transfer/MTU；
8. Entry restart；
9. Egress restart；
10. Controller offline 时已有静态 path 继续工作。

**G5**
- 静态 2-hop ≥24h soak；
- 无未知断流、资源泄漏或错误 fallback。

---

## 9.3 VCL 0.7.2 — Link & Path Observation

### 9.3.1 Link Resource

Controller 建立：

```text
Node A → Node B
```

字段至少：

- source_node；
- target_node；
- measured_at；
- RTT；
- loss；
- connect latency；
- availability；
- optional throughput sample。

### 9.3.2 Controller-coordinated Probe

模式：

```text
Controller → A: probe B
A → B: bounded measurement
A → Controller: result
```

禁止 Node 之间持续 gossip。

### 9.3.3 Bounded Probing

默认只探测：

- declared paths；
- configured candidate backup links。

禁止默认 full-mesh N² 高频测量。

### 9.3.4 Path Health

Path health 由：

```text
Entry Health
+ Link Health
+ Egress Health
```

组合。

至少状态：

```text
HEALTHY
DEGRADED
UNAVAILABLE
UNKNOWN
```

### 9.3.5 Path Performance

采集：

- path connect latency；
- synthetic HTTPS TTFB；
- failure rate；
- throughput sample（低频/可选）。

### 9.3.6 Topology UI

WebUI 增加逻辑 data-plane topology：

- Entry；
- Egress；
- Link；
- Path；
- health；
- RTT/loss；
- bound users；
- traffic。

UI 仍读 Controller cache，不直接 node-to-node probe。

### 9.3.7 0.7.2 门禁

**G1**
- Link schema；
- path health aggregation；
- probe timeout/loss；
- bounded scheduler。

**G2**
- declared links only；
- 100 nodes 时不会意外生成 full mesh；
- probe failure 不影响 data plane；
- topology UI cache-only。

**G3**
- probe 不使用 admin/root credential；
- probe payload bounded；
- 不引入 peer control channel。

**G4 Live**
1. A→B RTT/loss 实测；
2. 注入 link packet loss → Path DEGRADED；
3. Egress stop → Path UNAVAILABLE；
4. 恢复后 Path HEALTHY；
5. Controller 停止 measurement → path 静态转发继续。

**G5**
- measurement 对 Node CPU/网络开销可接受；
- 无 probe storm。

---

## 9.4 VCL 0.7.3 — Primary / Backup Path

### 9.4.1 Primary / Backup Declaration

```yaml
route_policies:
  jp:
    primary: jp-primary
    backup: jp-backup
```

### 9.4.2 Backup Readiness

持续检查：

- capability ready；
- credential ready；
- config compilable；
- path health；
- egress reachable。

### 9.4.3 Manual Failover

支持：

```text
plan switch
→ approve
→ apply
→ verify
```

只影响新连接；现有 TCP 不迁移。

### 9.4.4 Recommended Failover

当：

```text
primary = DEGRADED/UNAVAILABLE
backup = HEALTHY
```

产生 Recommendation / Operation Plan，但不自动 apply。

### 9.4.5 Route Stability Model

为 0.8 预埋只读计算：

- minimum improvement；
- minimum duration；
- cooldown；
- stickiness；
- candidate score explanation。

0.7.3 禁止根据这些分数 unattended switch。

### 9.4.6 0.7.3 门禁

**G1**
- primary/backup schema；
- readiness；
- manual switch plan；
- existing-session semantics。

**G2**
- primary down / backup healthy；
- backup not ready 时拒绝 switch；
- plan stale；
- repeated switch no-op。

**G3**
- failover 不 silent direct；
- 不允许 unavailable/untrusted path 被选；
- route recommendation 无 auto hook。

**G4 Live**
1. primary 正常；
2. primary 故障 → recommendation；
3. 人工 approve → 新连接走 backup；
4. 旧连接自然结束；
5. primary 恢复不自动切回；
6. manual switch-back 正常。

**G5**
- 多次人工 failover 无配置漂移/credential 泄漏；
- 无 route flapping（本版本无自动切换）。

---

## 9.5 VCL 0.7.4 — Path-aware Accounting & Capacity

### 9.5.1 Traffic Class

审计至少区分：

```text
user_ingress
transit
egress
```

### 9.5.2 Double-count Prevention

必须避免：

```text
Entry alice 1GB + Egress node:lax 1GB = Fleet 2GB
```

Fleet 逻辑 usage 必须有明确 accounting invariant。

建议：

- user usage 以 Entry 为 authoritative；
- transit usage 单独统计，不加入 user fleet-total；
- Egress 使用量作为 network/path capacity 视图。

### 9.5.3 Per-path Usage

可查询：

```text
path bytes
connections
active users
failure count
```

### 9.5.4 Capacity Signals

Node / Path 暴露：

- connections；
- network rate；
- CPU；
- memory；
- path traffic；
- saturation / pressure Finding。

0.7.4 只提供 capacity visibility / recommendation，不自动迁移用户。

### 9.5.5 0.7.4 门禁

**G1**
- accounting classification；
- aggregation invariant；
- rollup；
- retention。

**G2**
- 1GB test flow 在 fleet user usage 中只计一次；
- transit statistics 可单独看到；
- path switch 前后 usage 归属正确。

**G3**
- Egress 不需要知道原始 user credential；
- accounting export 不泄漏 node transit secret。

**G4 Live**
1. 单用户 2-hop 大文件；
2. Entry/Egress/transit 数据核对；
3. Fleet total 不双计；
4. path usage 与接口流量量级合理；
5. capacity pressure 可产生 Finding。

**G5**
- 0.7.x RC 完成 static path + observation + manual failover + accounting 全链路 soak。

---

# 10. 0.5.x–0.7.x Release Evidence 规范

每个 release 建议：

```text
docs/evidence/<version>/
├── SUMMARY.md
├── TESTS.md
├── SECURITY.md
├── COMPATIBILITY.md
└── LIVE.md
```

## 10.1 SUMMARY.md

必须列出：

- Controller version；
- Node payload version；
- minimum compatible Node；
- commit SHA；
- artifact digest；
- automated test count；
- Offline/Integration/Live gate 状态；
- known limitations。

## 10.2 TESTS.md

- test commands；
- test environment；
- total pass/fail/skip；
- failure injection；
- concurrency；
- schema tests；
- secret scan。

## 10.3 SECURITY.md

记录：

- listeners；
- process users/capabilities；
- file permission audit；
- systemd hardening；
- credential path；
- secret redaction；
- new attack surface；
- unresolved security deviations。

## 10.4 COMPATIBILITY.md

实际验证矩阵：

```text
Controller version × Node version × Capability
```

禁止仅依据代码推测标 PASS。

## 10.5 LIVE.md

每项必须包含：

- 前置条件；
- 操作步骤；
- 期望结果；
- 实际结果；
- PASS / FAIL / PENDING LIVE；
- 非敏感 evidence。

不得保存：

- 完整 URI；
- UUID；
- Reality private key；
- Clash secret；
- SSH private key；
- SOCKS password；
- 可直接登录的完整凭证。

---

# 11. CI / 测试体系增强

0.5.x–0.7.x 应逐步增加以下 CI 类别：

## 11.1 Schema Contract Tests

所有 machine-readable interface 都必须有：

- valid fixture；
- missing required field；
- unknown field；
- future version；
- malformed JSON；
- oversize；
- secret-like content rejection（适用时）。

## 11.2 Failure Injection

重点：

- SSH timeout；
- service crash；
- Controller crash；
- disk full / DB corrupt；
- config activation fail；
- rollback fail；
- egress down；
- transit down；
- partial path mutation。

## 11.3 Concurrency

- monitor polling；
- operation journal；
- config mutation lock；
- simultaneous CLI/UI read；
- simultaneous plan/apply conflict。

## 11.4 Secret Regression Tests

扫描：

- stdout/stderr；
- JSON；
- progress；
- operation journal；
- telemetry DB；
- Finding evidence；
- UI API payload；
- release evidence。

## 11.5 Real HOME Isolation

全量测试持续证明不读写真实：

- `~/.ssh/known_hosts`；
- Workspace；
- Fleet Home；
- credential files；
- UI runtime。

---

# 12. Node Appliance Hardening Roadmap

这些工作跨 0.5–0.7 持续进行。

## 12.1 0.5 — Observable Appliance

- accountd de-root；
- observer identity；
- stronger `verify`；
- service/resource health；
- bounded telemetry；
- systemd sandbox review。

## 12.2 0.6 — Maintainable Appliance

- LKG config；
- atomic activation；
- upgrade preflight/rollback；
- restricted management SSH；
- QoS/resource guards；
- signed/digested release manifest 可逐步增强。

## 12.3 0.7 — Programmable Appliance

- node role；
- transit identity；
- ACL；
- static path；
- link probe；
- path telemetry。

长期 Node 原则：

```text
Controller: intelligent / complex
Node:       boring / predictable / minimal / fail-static
```

---

# 13. 明确推迟到 0.8+ 的能力

## 13.1 0.8.x — Traffic Engineering

候选：

- automatic primary/backup failover；
- path scoring；
- hysteresis；
- cooldown；
- capacity-aware path selection；
- health-aware routing；
- policy-based routing by destination / region；
- limited 3-hop experiments（只有 2-hop 已充分验证后）。

## 13.2 0.9.x — Closed-loop Automation

候选：

```text
Observation
   ↓
Finding
   ↓
Policy
   ↓
Automatic Plan
   ↓
Guardrails
   ↓
Apply
   ↓
Verify
   ↓
Rollback
```

包括：

- limited auto-throttle；
- safe service remediation；
- bounded automatic failover；
- approval modes；
- automated rollback。

---

# 14. 长期 Non-Goals / 产品边界

除非未来另立项目或重大 SPEC，不将 VCL 演化成：

- generic RMM；
- generic SSH executor；
- Web shell / file manager；
- transparent HTTPS MITM cache；
- packet-content surveillance；
- billing platform；
- DPI 内容审计平台；
- public cloud control API；
- 默认 node-to-node control mesh；
- 分布式共识控制器。

缓存若未来引入，应为显式 application-aware service（DNS cache / package cache / registry cache 等），而非透明 TLS interception。

---

# 15. 推荐开发顺序

严格按依赖推进：

```text
0.5.0  Observation Foundation
  ↓
0.5.1  Monitoring & Health
  ↓
0.5.2  Findings & Audit Observability
  ↓
0.5.3  Inspect & Drift
  ↓
0.6.0  Desired State & Reconciliation
  ↓
0.6.1  Alerting & Incident Operations
  ↓
0.6.2  QoS & User Policy
  ↓
0.6.3  Egress Resource & Per-user Egress Binding
  ↓
0.6.4  Controlled Maintenance
  ↓
0.7.0  Node Roles & Transit Identity
  ↓
0.7.1  Static 2-Hop Path
  ↓
0.7.2  Link & Path Observation
  ↓
0.7.3  Primary / Backup Path
  ↓
0.7.4  Path-aware Accounting & Capacity
```

原则：每个子版本必须能够独立收口和发布；不得为了未来功能留下长期不可用的 half-state。

---

# 16. 总体完成定义（Definition of Done）

## 16.1 0.5.x 完成时

VCL 必须能够可靠回答：

```text
Is the node alive?
Is the proxy actually usable?
Is accounting trustworthy?
Is the node drifting?
What changed and when?
```

且 observation 不改变网络状态。

## 16.2 0.6.x 完成时

VCL 必须能够可靠回答并执行：

```text
What should the fleet look like?
How does observed state differ?
What exact change is proposed?
Is the plan still valid?
Can it be applied safely?
Did it work?
Can it roll back?
Which user policy / egress should apply?
```

并具备稳定 alerting、QoS policy、per-user Egress 和 typed maintenance。

## 16.3 0.7.x 完成时

VCL 必须能够表达并运行：

```text
User → Entry → Egress → Internet
```

并且具备：

- Node role / identity / ACL；
- static 2-hop Path；
- link/path telemetry；
- primary/backup readiness；
- manual failover；
- path-aware accounting；
- capacity visibility；
- Controller 离线时静态 data plane 继续工作。

此时 VCL 应正式具备“集中式专用 SDN Controller”的基础形态，但仍不进行 unattended dynamic routing。

---

# 17. 最终架构目标（0.7.x 收口状态）

```text
                       Northbound
                 CLI / WebUI / Policy
                         │
                         ▼
                  Desired State
                         │
                  Reconciliation
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       Observation Plane       Control Plane
             │                       │
             └───────────┬───────────┘
                         │
               Typed VCL Protocol
                  over SSH transport
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
          Entry Node  ─────────→  Egress Node
              │        Data Path      │
              │                       │
            User                   Internet
```

控制平面仍保持星型：

```text
Controller → Nodes
```

数据平面开始可编程：

```text
User → Entry → Egress
```

权威状态始终只存在于 Controller / Workspace：

```text
No distributed authority.
```

---

# 18. 版本验收总表

| 版本 | 核心 Release Gate |
|---|---|
| 0.5.0 | capability/telemetry 稳定；observe route 无 privilege fallback；legacy Node 正确降级；**0.3.x→0.5.0 upgrade 断流 ≤3s** |
| 0.5.1 | 30s monitoring 稳定；health state 正确；Controller/accountd 故障不影响 data plane |
| 0.5.2 | audit stall/gap 可见；Finding 可解释；异常检测不产生 mutation |
| 0.5.3 | inspect/verify read-only；listener/config/integrity drift 可识别 |
| 0.6.0 | Desired/Observed/Reconcile；NOOP；PLAN_STALE；LKG rollback |
| 0.6.1 | alert lifecycle；无 alert storm；maintenance window 正确 |
| 0.6.2 | per-user QoS isolation；Finding→recommendation；无误伤其他用户 |
| 0.6.3 | per-user Egress；SOCKS fail-closed；DNS/UDP 明确；VPS-side SOCKS Live benchmark |
| 0.6.4 | typed maintenance；upgrade health gate；rollback；restricted management path |
| 0.7.0 | Node roles/credential/ACL；unauthorized transit 必须拒绝 |
| 0.7.1 | static 2-hop；transport ADR；TCP/UDP/QUIC/MTU/DNS 通过；Controller offline 继续运行 |
| 0.7.2 | Link/Path health；bounded probes；无 gossip/full-mesh storm |
| 0.7.3 | primary/backup readiness；manual failover；existing session 语义正确 |
| 0.7.4 | user/transit accounting 不双计；path usage/capacity 可观测 |

---

**End of SPEC**
