# Vincula v0.3.1 → v0.5.x 开发规格（修订版 rev1）

Draft v1 修订 — 2026-08-20（rev1）
权威决策：`vcl-decisions-v0.4.md`（D45–D58 + 用户结构性修订）优先于 Draft v1；冲突处标注「【覆盖原 SPEC】」。

基线： `v0.3.1` stable（immutable）
范围： `v0.4.0–v0.4.5`、`v0.5.0–v0.5.3`
受众： Maintainer / Coding Agent
项目定位： CLI-first、低攻击面的 VPS 代理节点、Fleet、审计、可观测性与维护工具

代码版本事实（0.3.1 现状，供 0.4.0 解耦对照）：

- `lib/vincula-fleet.py`：`VCL_FLEET_VERSION = "0.3.1"`；`FLEET_SCHEMA_VERSION = 2`；`FLEET_DB_SCHEMA_VERSION = 3`
- `vincula.sh`：`VINCULA_VERSION="0.3.1"`
- `scripts/build-controller.sh`：当前从 `vincula.sh` → `VINCULA_VERSION` 取 controller 产物版本（0.4.0 起改为读 `VCL_FLEET_VERSION`）

---

## 0. 执行摘要

Vincula v0.3.1 已完成：

- 单节点安装 / 升级
- 多用户生命周期
- 近似流量审计
- Fleet Controller
- Fleet-global user_id
- Incremental Audit Sync
- Backup / Restore / Replace
- Local Audit UI
- Windows / Linux Controller Artifact
- Schema：`accounting-db/v4` / Export Protocol v2；controller `fleet-registry/v2`、`fleet-cache/v3`

v0.4.x 的任务不是继续扩展代理协议，而是把现有 Fleet Controller 从：

> 「绑定在一台管理员工作站上的 CLI」

演进为：

> 「可移动、可快速接管 VPS、以本地缓存和 Web UI 为主要观察入口的 Fleet Workspace」

**【覆盖原 SPEC】** 0.4.x 切分先建立 seam / 兼容基础，再迁移状态与功能，避免「大迁移 + 大 DB 改造 + SSH trust 改造」同时发生：

```
0.4.0 Compatibility Foundation
0.4.1 Portable Workspace
0.4.2 Local Cache & Archive
0.4.3 Adopt & Provision
0.4.4 Web UI v2
0.4.5 Integration & Hardening
```

v0.5.x 再在同一安全模型上增加：

- Observation Plane
- 30s 级遥测
- VPS inspection
- configuration drift
- tuning plan/apply
- maintenance plan/apply

整个演进必须保持最重要的安全边界：

- 不增加 VPS 公网管理 API
- 不增加 VPS 管理监听端口
- 不引入云端控制服务
- 不要求中心服务器
- 不把 Web UI 变成公网管理面

长期架构：

```
                    Administrator Machine
                           │
                 ┌─────────┴─────────┐
                 │                   │
            Local Web UI             CLI
                 │                   │
                 └─────────┬─────────┘
                           │
                    Fleet Controller
                           │
              ┌────────────┴────────────┐
              │                         │
       Observation Plane          Control Plane
        read-only / pull         explicit mutation
              │                         │
        Observe SSH                Admin SSH
              │                         │
              └──────────┬──────────────┘
                         │
                        VPS
```

---

## 1. 产品边界

### 1.1 Vincula 仍然不是中央控制平台

不得把 Vincula 演进成：

- 公网 Web Admin
- 公网 Management API
- SaaS Fleet Control Plane
- 机场式管理面板
- 通用 RMM
- 通用 SSH Remote Executor
- 计费系统

管理员工作站仍然是控制中心。

- 节点不主动连接 Controller。
- Controller 不要求固定公网地址。

---

## 2. 核心架构决策

以下决策视为 v0.4/v0.5 的基础约束。D45–D58 及用户结构性修订见文末《决策记录》；本节已并入其约束，冲突处以决策为准并标「【覆盖原 SPEC】」。

### D21 — Fleet 成为独立逻辑实体

引入：

```
fleet_id = UUID
```

Fleet 的身份独立于：

- 管理员机器
- WSL 实例
- Windows 用户
- workspace 路径
- fleet.db

`fleet_id` 创建后永久稳定。

**【覆盖原 SPEC 落位】** 真实引入与跨机验收在 **0.4.1**；0.4.0 仅建立 API/模块 seam，不改变磁盘布局行为。

### D22 — Workspace 是可移动的权威配置

Fleet Workspace 包含：

- Fleet identity
- Node registry
- SSH endpoint metadata
- Access references
- Host trust
- Instance history
- 少量 Fleet policy

Workspace：

- 可复制
- 可备份
- 可放入 Syncthing / OneDrive 等同步目录

但不得包含：

- SSH private key
- SSH password
- sudo password
- VLESS credential
- Reality private key
- Clash secret
- 机器专属绝对路径

### D23 — fleet.db 是 machine-local materialized cache

`fleet.db` 不再是 Fleet identity 的组成部分。

定义：

- Workspace = authoritative configuration
- fleet.db = machine-local observation cache

换管理员机器时：

```
Workspace
   ↓
vcl-fleet sync --full   # 【覆盖原 SPEC】0.4.x 默认 sync 仍为 legacy audit；全量观测刷新用 --full
   ↓
重新构建本机 fleet.db
```

默认不需要复制 `fleet.db`。

**【覆盖原 SPEC 落位】** cache 路径分离与强制 RO 在 **0.4.2**。

### D24 — fleet.db 的正常写入口只有 sync plane

从用户模型看：

- fleet.db = read-only analysis database

允许写入的内部路径仅限：

- sync（含 `sync --full`）
- reseed
- cache migration
- cache rebuild
- audit archive restore
- schema migration

以下路径必须以 SQLite read-only 模式打开：

- Web UI GET
- stats
- audit query
- cached status
- traffic analysis
- 普通 node/user 浏览

统一提供：

```
open_cache_readonly()
open_cache_for_sync()
```

Query path 使用：

```
SQLite URI mode=ro
```

**【覆盖原 SPEC / D47】**：

- **0.4.0**：建立 RO/RW API seam（边界存在，行为可仍走现有入口）。
- **0.4.2 起**：所有 query / UI GET 强制真正的 SQLite read-only connection。

### D25 — `sync` 成为类似 `apt update` 的核心动词

**【覆盖原 SPEC】** 心智模型仍为目标，但 **0.5 前不切换默认行为**：

```
vcl-fleet sync          # 0.4.x：legacy audit sync（保持 0.3.1）
vcl-fleet sync --full   # 新增：identity + health + users metadata + audit delta → local cache
```

`sync --full` 语义：

> «从 Workspace 中登记的节点依次拉取最新 observable state，并刷新本机 cache。」

典型模型：

```
Remote Fleet
    │
    │ explicit sync --full
    ▼
Local fleet.db
    │
    ├── Web UI
    ├── stats
    ├── audit
    ├── status（0.4.1+ cache-only）
    └── analysis
```

普通查看信息不隐式 SSH（见 D58）。UI Sync 按钮调用 `sync --full`。

0.5.x 可考虑切换默认；须在 0.4 release notes 写明 deprecation window。用户倾向：0.5 前不切默认。

### D26 — 不实现多 Controller 并发写（由 D52 精确化）

v0.4 支持：办公室 WSL、家中 WSL、笔记本管理同一个 Workspace。

**【覆盖原 SPEC】** 产品承诺必须写准确：

> **Multi-controller capable, Single-writer operational semantics.**

提供 **best-effort stale/divergence detection**，**不保证**通用文件同步工具下的 distributed mutual exclusion 或 zero lost updates。

不保证：

- 两个 Controller 同时修改同一个 Fleet
- 自动 merge
- distributed locking
- distributed transaction

若未来要 concurrent multi-controller，需要另一架构，不得偷偷塞进 Workspace revision。

Workspace manifest 与冲突三态见 **D52**（§3.1）。

### D27 — Fleet 使用自己的 SSH Trust Store

不再把 Fleet trust 绑定在某一台电脑的全局：

```
~/.ssh/known_hosts
```

改为：

```
workspace/trust/known_hosts
```

Controller SSH 必须继续：

```
StrictHostKeyChecking=yes
```

禁止：

```
StrictHostKeyChecking=no
UserKnownHostsFile=/dev/null
```

首次信任仍遵循：

- interactive TOFU

或自动化：

```
--host-key SHA256:...
```

`ssh-keyscan` 只能获取 candidate key，不构成信任。

**【覆盖原 SPEC 落位】** 真实 dedicated known_hosts 在 **0.4.1**；0.4.0 可抽 `trust.py` seam 但行为不变。

### D28 — SSH 凭据与 Workspace 分离

Workspace 只保存 credential reference。

例如：

```
admin_credential_ref = "admin-default"
observe_credential_ref = "observe-default"
```

实际机器路径存在 Machine Local Config：

办公室：

```
admin-default
→ /home/work/.ssh/vcl
```

家中：

```
admin-default
→ /home/home/.ssh/vcl
```

也允许：

```
admin-default
→ OpenSSH default / ssh-agent
```

不得把：

```
/home/user/.ssh/key
```

直接写入 portable Workspace。

### D29 — 提前区分 Admin 与 Observe Access（由 D57 精确化）

Workspace schema 从 v0.4 开始预留：

```
admin_credential_ref
observe_credential_ref
```

**【覆盖原 SPEC / D57】**：

- **0.4**：schema 预留；实际全部可用 admin（`observe = admin`，无额外配置成本）。
- **0.5**：Observation 强制 **observe routing**；Control 强制 **admin**。
- 显式配置 observe 后，**禁止静默 admin fallback**。

### D30 — UI 技术栈保持不变

v0.4 不引入：

- React
- Vue
- Node.js
- npm
- FastAPI
- Django
- 外部 CDN

继续使用：

- Python stdlib HTTP
- HTML
- CSS
- Vanilla JavaScript
- localhost

UI v2 的重点是：

- 信息架构
- 可读性
- 监控视图
- 过滤
- 快捷入口
- 降低 CLI 记忆成本

而不是前端框架升级。

**【覆盖原 SPEC 落位】** UI v2 在 **0.4.4**（原 0.4.3）。

### D31 — UI 默认只读取本地 Cache

页面加载不得：

- 隐式 SSH
- 隐式 Sync
- 隐式 Verify

UI 应明确显示：

- Last Sync
- Data Age
- Cache State

只有用户主动点击：

- Sync（→ `sync --full`）
- Verify
- Probe

才允许访问远端。

### D32 — 高风险 Mutation 保持 CLI-first

v0.4 UI 不直接执行：

- user rotate
- node replace
- restore
- reseed
- retire
- credential reissue
- adopt / provision（见 D53 矩阵）

UI 可以生成：

- pre-filled command

并提供：

- Copy Command

低风险操作如 Sync/Verify/Probe 可以直接执行。操作矩阵见 D53。

### D33 — Adopt / Provision / Register 分离（由 D49 扩展）

**【覆盖原 SPEC】** 正式三类语义：

```
node adopt
    已安装 Vincula
    SSH verify
    register

node provision
    fresh VPS
    install
    verify
    register

node register
    registry-only
    no SSH
    advanced/recovery/testing
```

兼容层：

```
node add NAME ...
    ≡ node adopt NAME ...

node add NAME --offline --node-id UUID
    ≡ node register NAME --node-id UUID ...
```

时间窗口：

```
0.4.x   完整保留 node add；文档标记 legacy alias；不需要运行时 warning
0.5.x   可以 stderr 提示 deprecated
最早 0.6  再决定是否删除
```

**【覆盖原 SPEC 落位】** adopt/provision 在 **0.4.3**（原 0.4.2）。

### D34 — Provision 不降低 SSH 安全策略

Provision 必须继续验证 host key。

不得因为「一条命令安装」而使用：

```
StrictHostKeyChecking=no
```

Interactive 模式可以：

```
Host key:
SHA256:...
Trust? [y/N]
```

Non-interactive 必须要求：

```
--host-key SHA256:...
```

### D35 — Controller-carried, digest-verified first-party provisioning payload

**【覆盖原 SPEC】** 原「air-gap」表述作废。准确契约：

- Controller **不从互联网下载 Vincula 自身代码**。
- Controller **将固定版本的 Vincula node artifact SCP 到 VPS**。
- **两端校验 SHA256**。
- 远端**仍可能需要互联网**：安装 OS dependency、下载 pinned sing-box、检测公网地址并执行 REALITY self-test。

**不是 air-gapped provisioning。** 除非以后真正解决 OS dependency + binary + public-IP + self-test 全部问题，**不应使用「air-gap」一词**。

推荐 controller artifact 内包含（见 D51，单 tarball + manifest，非双 arch）：

```
payload/
├── vincula-node-<pinned-node-version>.tar.gz
├── vincula-node-<pinned-node-version>.tar.gz.sha256
└── payload-manifest.json
```

流程：

```
Controller artifact
     ↓
verify local digest
     ↓
SCP
     ↓
verify remote digest
     ↓
installer
```

因此 provisioning 不依赖远端下载 Vincula 自身；但不声称 air-gap。

未来真正离线能力（另做）：

```
offline provision bundle
├── Vincula node payload
├── sing-box amd64 tarball
└── sing-box arm64 tarball
```

配合 installer：`--sing-box-archive FILE`。即使如此，缺 OS package 仍可能需要 apt repo。

### D36 — 不保存 SSH / sudo 密码

支持：

- OpenSSH default
- ssh-agent
- identity file
- ~/.ssh/config

Provision 目标要求：

- root

或：

- passwordless sudo

不建设 Password Vault。

### D37 — Audit History 与 Workspace 分离

历史 Audit 很重要，但不要求多 Controller 自动同步。

定义：

```
Audit Archive
```

用于：

- export
- backup
- verify
- restore

Audit archive 不属于 Workspace。

**【覆盖原 SPEC 落位】** Audit Archive 在 **0.4.2**。

### D38 — Audit Archive 不携带 cursor

Archive 可以包含：

- audit_events
- node attribution
- user attribution
- instance attribution
- time range
- schema metadata（`audit-archive/v1`）

不得包含：

- sync_cursor
- last_export_seq
- last-status
- credential refs
- SSH state

因此恢复 Archive 不得改变下一次 sync 起点。

### D39 — Observation 与 Control 永久分离

Observation：

- read-only
- idempotent
- frequent
- cacheable
- low privilege capable

Control：

- explicit mutation
- rare
- high privilege
- auditable

不得构造：

```
heartbeat → pending commands
```

或：

```
node heartbeat → controller 返回指令
```

### D40 — v0.5 Telemetry 使用 SSH Pull

Telemetry 默认模型：

```
Controller
    │
    │ SSH
    ▼
vcl telemetry snapshot --json
```

不增加：

- Telemetry HTTP endpoint
- Prometheus public port
- WebSocket
- node push
- cloud relay

### D41 — 可选 Collector 也不得监听网络

如果未来采集成本过高，可以引入：

```
vincula-telemetryd
```

但只能：

```
local collect
→ local snapshot
```

例如写：

```
/run/vincula/telemetry.json
```

不得 `listen()`。

### D42 — Telemetry 不包含 Secret

禁止返回：

- Reality private key
- VLESS UUID
- Clash secret
- SSH material
- user credential
- URL/path/content

### D43 — v0.5 不做默认自动修复

Telemetry 可以触发：

- warning
- recommendation
- plan

但不得默认：

- 自动修改 sysctl
- 自动升级软件
- 自动 reboot
- 自动 rotate credential

Mutation 必须由管理员显式执行。

### D44 — UI 与 CLI 共用 Application Service

不得继续扩展：

```
UI → import arbitrary CLI internals
```

目标：

```
                    CLI
                     │
                     ▼
               Fleet Service
                     ▲
                     │
                    UI
```

不要求一次性重构整个 `vincula-fleet.py`。

采用渐进式抽取。

### D45 — Schema 版本命名必须带 namespace

**【新增 / 覆盖原 SPEC】** 从 0.4.0 最前面起强制：

| Namespace | 当前 / 目标版本 | 对象 |
| --- | --- | --- |
| `accounting-db/v4` | 4 | 节点 `accounting.db` |
| `fleet-registry/v2` | 2 | controller `fleet.json`（及未来 registry 文件） |
| `fleet-cache/v3` | 3（0.3.1 现状） | controller `fleet.db` |
| `fleet-cache/v4` | 4（**0.4.2** 升级目标） | controller `fleet.db`（RO/RW + archive 配套） |
| `workspace/v1` | 1 | `workspace.json` |
| `audit-archive/v1` | 1 | `.vclaudit` |
| `telemetry/v1` | 1 | telemetry JSON |

建议常量：

```python
ACCOUNTING_DB_SCHEMA_VERSION = 4
FLEET_REGISTRY_SCHEMA_VERSION = 2
FLEET_CACHE_SCHEMA_VERSION   = 3   # 0.4.2 升至 4
WORKSPACE_SCHEMA_VERSION     = 1
AUDIT_ARCHIVE_SCHEMA_VERSION = 1
TELEMETRY_SCHEMA_VERSION     = 1
```

0.4.0 **不修改磁盘格式**。可暂时保留兼容 alias：

```python
FLEET_SCHEMA_VERSION    = FLEET_REGISTRY_SCHEMA_VERSION
FLEET_DB_SCHEMA_VERSION = FLEET_CACHE_SCHEMA_VERSION
```

文档与 error message **立即禁止**裸名：

```
❌ unsupported schema 4
✅ unsupported accounting-db schema: 4
✅ unsupported fleet-cache schema: 3
✅ unsupported fleet-registry schema: 2
```

### Controller/Node 版本解耦

**【覆盖原 SPEC §54/§55】** 0.4.0 第一批修改解耦：

- `build-controller.sh` 从 **`VCL_FLEET_VERSION`** 读取 controller version。
- `build-release.sh` 继续从 **`VINCULA_VERSION`** 读取 node version。

允许：

```
Controller 0.4.0–0.4.5  +  Node ≥ 0.3.1
```

Provision 可 `Controller 0.4.5 → install pinned Node 0.3.2`（legacy seed 需要 0.3.2；已有 0.3.1 仍可管理）。

**Node 首次 capability/telemetry 升级：0.5.0**（`vcl telemetry snapshot --json`）。**0.3.2** 仅为 0.4.5 payload bump。

兼容矩阵见 §54。长期能力探测：

```json
capabilities:
  audit_export_v2
  backup_v1
  telemetry_v1
  inspect_v1
```

---

## 3. 状态模型

### 3.1 Portable Workspace

建议结构：

```
workspace/
├── workspace.json
├── fleet.json
├── trust/
│   └── known_hosts
└── history/
    └── instances.jsonl
```

**【覆盖原 SPEC / D52】** `workspace.json`（`workspace/v1`）至少：

```json
{
  "schema_version": 1,
  "fleet_id": "UUID",
  "name": "main",
  "revision": 18,
  "write_id": "UUID",
  "parent_revision": 17,
  "parent_write_id": "UUID",
  "state_digest": "sha256:...",
  "last_writer_controller_id": "UUID",
  "created_at": "RFC3339",
  "updated_at": "RFC3339"
}
```

每台 Controller machine-local 再保存：

```
last_seen_revision
last_seen_write_id
last_seen_state_digest
```

检测三态：

```
workspace revision < last_seen                     → WORKSPACE_ROLLBACK
workspace revision == last_seen
  but write_id != last_seen_write_id               → WORKSPACE_DIVERGED
state_digest 不匹配实际 portable files             → WORKSPACE_INCONSISTENT
```

每次 mutation：

```
read
→ validate digest
→ remember revision/write_id
→ perform operation
→ re-read before commit
→ CAS-like check
→ atomic commit
```

### 3.2 Fleet Registry（`fleet-registry/v2`）

**【覆盖原 SPEC】** 原「Schema 3」更正为与代码一致的 **`fleet-registry/v2`**。示意：

```json
{
  "schema_version": 2,
  "fleet_id": "UUID",
  "nodes": [
    {
      "node_id": "UUID",
      "name": "lax",
      "ssh_host": "203.0.113.10",
      "ssh_user": "root",
      "ssh_port": 22,

      "admin_credential_ref": "admin-default",
      "observe_credential_ref": "admin-default",

      "enabled": true,
      "status": "active"
    }
  ]
}
```

禁止出现：

- identity_file
- password
- private key
- VLESS UUID
- Reality secret

---

## 4. Machine Local State

### 4.1 Controller Identity

每台管理员机器生成：

```
controller_id = UUID
```

只属于本机。

### 4.2 Credential Bindings

示意：

```json
{
  "schema_version": 1,
  "bindings": {
    "admin-default": {
      "type": "identity_file",
      "path": "/home/user/.ssh/vcl"
    }
  }
}
```

或：

```json
{
  "type": "openssh-default"
}
```

私钥文件本身永远不复制进 Vincula。

---

## 5. Local Cache

建议：

```
local-state/<fleet_id>/
├── fleet.db
├── archives/
└── ui-runtime/
```

Linux/WSL 推荐：

```
${XDG_STATE_HOME:-~/.local/state}/vincula/<fleet_id>/
```

Windows：

```
%LOCALAPPDATA%\vincula\<fleet_id>\
```

**【覆盖原 SPEC 落位】** 路径分离在 **0.4.2** 落地；0.4.0/0.4.1 可保留 legacy `$FLEET_HOME/fleet.db` 行为直至 cache 里程碑。

---

## 6. Fleet Cache Schema（`fleet-cache`）

0.3.1 现状：`fleet-cache/v3`。

**【覆盖原 SPEC】** 原「Fleet DB Schema 4」统一命名为 **`fleet-cache/v4`**，在 **0.4.2** 升级（非 0.4.0）。

至少包含：

- meta
- audit_events
- sync_cursor
- daily_usage
- node_snapshot
- user_snapshot
- sync_runs
- operations

`meta` 必须保存：

- fleet_id
- schema_version（消息中写 `fleet-cache` namespace）

打开 DB 时：

```
DB fleet_id != Workspace fleet_id
```

必须 fail closed：

```
CACHE_FLEET_MISMATCH
```

---

## 7. Instance History

当前 instance history 不应继续作为仅存在于本地 Fleet DB 的权威状态。

**【覆盖原 SPEC 落位】** v0.4.1 起：

```
workspace/history/instances.jsonl
```

成为 portable history。

记录：

- node_id
- instance_id
- started_at
- retired_at
- endpoint
- reason

不记录 secret。

`fleet.db` 可以有 instance history 的 materialized copy，用于 UI 查询，但不是 SoT。

---

## 8. v0.3.1 → Workspace Migration

**【覆盖原 SPEC】** 真实迁移在 **0.4.1**；**0.4.0** 仅提供 `migrate --dry-run`（及 seam），不写 Workspace、不改行为。

### 8.1 支持输入

正式支持：

- v0.3.1 stable controller state

兼容：

- 0.3.1-rc2 legacy layout

但若检测到 RC state，应警告：

```
LEGACY_PRERELEASE_CONTROLLER_STATE
```

Workspace migration 不自动升级远端节点。

### 8.2 Migration CLI

```
vcl-fleet workspace migrate --dry-run
```

必须：

- 不 SSH
- 不改远端
- 不删除任何文件
- 不写 Workspace
- 输出完整计划

**【覆盖原 SPEC / D48】** dry-run 必须报告：从未 sync 过的节点在迁移后 `instance_history` 可能为空的缺口（现状 `cmd_node_add` 不写 history，仅 sync 写入）。**migration 不得为补 history 而 SSH。**

执行（0.4.1）：

```
vcl-fleet workspace migrate
```

### 8.3 Migration Pipeline

1. lock legacy Fleet
2. validate fleet.json（`fleet-registry/v2`）
3. PRAGMA integrity_check fleet.db（`fleet-cache/v3`）
4. inventory legacy files
5. mint fleet_id
6. create temporary Workspace
7. migrate registry
8. migrate identity_file → credential refs
9. extract Fleet-only host trust
10. export instance_history
11. create machine-local credential bindings
12. migrate fleet.db → local state（完整 cache 路径分离可与 0.4.2 衔接）
13. migrate status/users cache as derived state
14. verify new Workspace
15. atomic commit
16. preserve old tree as legacy backup

### 8.4 Identity File Migration

对于每个不同 `identity_file`：

创建一个 machine-local credential ref。

例如：

```
/home/a/.ssh/key-a
→ migrated-key-1
```

Workspace：

```
admin_credential_ref = migrated-key-1
observe_credential_ref = migrated-key-1
```

Machine local：

```
migrated-key-1
→ /home/a/.ssh/key-a
```

第一版不强制自动 deduplicate credential refs。

### 8.5 Host Trust Migration

不得：

```
cp ~/.ssh/known_hosts workspace/trust/known_hosts
```

必须只提取 Fleet host。

优先使用 OpenSSH 工具匹配：

- host
- [host]:port
- hashed host entry

若无法确认已有 trust：

```
TRUST_MIGRATION_REQUIRED
```

不得自动以新的 `ssh-keyscan` 结果覆盖旧 trust。

### 8.6 Fleet DB Migration

旧：

```
$FLEET_HOME/fleet.db
```

新（0.4.2 完整形态）：

```
LOCAL_STATE/<fleet_id>/fleet.db
```

过程：

```
integrity check
→ copy
→ schema migrate（消息使用 fleet-cache namespace）
→ fleet_id stamp
→ integrity check
→ row/count/cursor verification
```

原 DB 不删除。

### 8.7 Retired Snapshot

Legacy：

```
retired/<name>/
```

中真正具有身份意义的数据迁入：

- registry
- instance history

cursor/status 等保持 legacy backup，不进入 Workspace。

### 8.8 Migration Acceptance Criteria（归属 **0.4.1**）

**AC-4.0-M01** — 迁移前后所有 `node_id` / `user_id` / node status / SSH endpoint 保持一致。

**AC-4.0-M02** — 迁移不修改任何远端 VPS。

**AC-4.0-M03** — 迁移失败不得破坏 legacy Fleet。

**AC-4.0-M04** — 迁移后的 Workspace 在原机器 `workspace verify` / `sync` / `status` / `audit` / `stats` / `ui` 全部正常。

**AC-4.0-M05** — 将 Workspace 复制至第二台 WSL：bind local credential → sync → status → ui，可以管理同一 Fleet。

**AC-4.0-M06**（【新增 / D48】）— `migrate --dry-run` 对从未 sync 的节点明确报告 instance history 缺口；实际 migrate 不 SSH 补 history。

---

## 9. Workspace CLI

**【覆盖原 SPEC】** 命令在 0.4.0 可出现为 no-op/seamed dry-run；完整语义按里程碑生效。

至少：

```
vcl-fleet workspace init          # 0.4.1
vcl-fleet workspace show
vcl-fleet workspace verify

vcl-fleet workspace migrate --dry-run   # 0.4.0 起
vcl-fleet workspace migrate             # 0.4.1

vcl-fleet workspace export FILE
vcl-fleet workspace import FILE

vcl-fleet access list
vcl-fleet access bind REF --identity-file PATH
vcl-fleet access bind REF --openssh-default
vcl-fleet access verify
```

支持：

```
--workspace PATH
```

以及：

```
VCL_FLEET_WORKSPACE
```

---

## 10. v0.4.0 — Compatibility Foundation

**【覆盖原 SPEC】** 原「Workspace Foundation / 大迁移」改为此节。

### 10.1 Scope

实现：

- schema namespace 强制（D45）；**不改磁盘格式**；兼容 alias
- Controller/Node 版本解耦：`build-controller.sh` → `VCL_FLEET_VERSION`；node 仍 `VINCULA_VERSION`
- 从 monolith 抽出 `workspace.py` / `access.py` / `trust.py` 等模块 seam，**保持原 CLI 行为完全不变**
- legacy adapter 边界
- `workspace migrate --dry-run`（不 SSH、不写 Workspace）
- RO/RW API seam：`open_cache_readonly()` / `open_cache_for_sync()` 边界（D47；尚未强制真正 mode=ro）
- observe/admin 字段在 schema/API 层预留（D57；运行仍 observe=admin）

不实现：

- 真实 Workspace 写入 / fleet_id 磁盘迁移
- dedicated known_hosts 切换
- cache 路径搬迁 / fleet-cache/v4
- provision / UI v2 / telemetry

### 10.2 Definition of Done

- 文档与错误信息无裸 schema 版本号
- controller zip 版本与 `VCL_FLEET_VERSION` 一致，可与 Node 0.3.1 并存
- 既有 0.3.1 CLI 行为回归：无行为变更
- `migrate --dry-run` 可输出计划（含 D48 history 缺口报告）且零副作用
- 模块 seam 存在，后续 0.4.1 可在其上实现真实迁移

### 10.3 Acceptance Criteria（【新增】无行为变更门禁）

- **AC-4.0-01** — 相对 0.3.1：默认 `status` / `sync` / `node add` / `ui` / audit / stats 行为与副作用不变（本里程碑内）。
- **AC-4.0-02** — `build-controller.sh` 产物版本取自 `VCL_FLEET_VERSION`，不再取自 `VINCULA_VERSION`。
- **AC-4.0-03** — 任何 schema 相关错误信息使用 namespaced 形式（`accounting-db` / `fleet-registry` / `fleet-cache`）。
- **AC-4.0-04** — `workspace migrate --dry-run`：不 SSH、不写 Workspace、不删文件；报告含 instance history 缺口说明。
- **AC-4.0-05** — RO/RW seam API 存在；query 路径可仍兼容旧入口，但新代码不得绕过 seam 扩散。

---

## 11. v0.4.1 — Portable Workspace

**【覆盖原 SPEC】** 原 §10 Workspace Foundation 的真实迁移与可移植性落于此；原 §11.4 status 语义按 D58 于此落地。

### 11.1 Scope

实现：

- 真实 `workspace migrate`
- fleet_id
- portable Workspace（`workspace/v1` + D52 manifest）
- machine-local credential binding
- Fleet trust store（dedicated known_hosts）
- instance history portability
- cross-machine acceptance（AC-4.0-M01..M05）
- status/probe/sync 副作用分离（D58）

### 11.2 status / probe / sync（D58）

**【覆盖原 SPEC】**：

```
vcl-fleet status          # 0.4.1 起：cache-only；documented breaking change（CHANGELOG）
vcl-fleet probe           # 新增：live SSH health
vcl-fleet status --live   # 0.4.x compatibility alias → probe 语义；deprecated
vcl-fleet sync            # 仍为 legacy audit（保持至 0.5 前）
vcl-fleet sync --full     # 可在本里程碑引入命令面，或与 0.4.2 一并完成实现；默认不切换
```

三者副作用严格区分：status 不 SSH；probe 可 SSH；sync / sync --full 语义见 D25/D58。

Cached status 显示：

```
LAST SYNC
DATA AGE
NODE STATUS
```

### 11.3 Definition of Done

```
0.3.1 Fleet
      ↓ migrate
Workspace
      ↓
Machine A sync / sync --full
      ↓
copy Workspace
      ↓
Machine B credential bind
      ↓
Machine B sync
```

并验证：

```
same fleet_id
same node_id
same logical users
same host trust
independent fleet.db（可仍在过渡路径）
```

### 11.4 Acceptance Criteria

保留并归属本里程碑：

- **AC-4.0-M01** … **AC-4.0-M05**（见 §8.8）
- **AC-4.0-M06**（D48 dry-run history 缺口）
- **AC-4.1-02** — `status`（裸）不产生 SSH。

以及：

- **AC-4.1-S01**（【新增 / D58】）— CHANGELOG 明确记录裸 `status` cache-only breaking change；`probe` 与 `status --live` 可用。
- **AC-4.1-S02**（【新增 / D52】）— Workspace mutation 使用 CAS-like revision/write_id 检查；可检测 WORKSPACE_ROLLBACK / DIVERGED / INCONSISTENT。

---

## 12. Audit Archive

**【覆盖原 SPEC 落位】** 整章能力归属 **0.4.2**（原夹在 0.4.1）。

### 12.1 目的

解决：

> «某一台管理员机器保存了长期 Audit，换机器时不希望丢掉历史。»

但不要求：

> 办公室和家中 audit 自动实时同步

### 12.2 Archive Format

建议：

```
*.vclaudit
```

本质为版本化 SQLite 数据库，schema namespace：`audit-archive/v1`。

包含：

- archive schema
- fleet_id
- created_at
- time range
- audit_events
- node attribution snapshot
- user attribution snapshot
- instance attribution

不得包含：

- sync_cursor
- SSH path
- credential refs
- private secrets

### 12.3 Commands

```
vcl-fleet audit archive create \
  --from RFC3339 \
  --to RFC3339 \
  --output FILE.vclaudit

vcl-fleet audit archive verify FILE.vclaudit
vcl-fleet audit archive inspect FILE.vclaudit
vcl-fleet audit archive restore FILE.vclaudit
```

Restore：

- 只导入历史 event
- 不得修改 cursor

### 12.4 Conflict Policy

唯一键：

```
(node_id, event_id)
```

相同 key + 相同 payload：deduplicate

相同 key + 不同 payload：`ARCHIVE_CONFLICT`，整个 restore transaction rollback。

### 12.5 Encryption

Audit archive 属于敏感行为数据。

支持：

```
--age-recipient FILE
```

输出：

```
FILE.vclaudit.age
```

继续复用系统 `age`。

不建设新的密码学实现。

---

## 13. v0.4.2 — Local Cache & Archive

**【覆盖原 SPEC】** 原 §11 Sync v2 + Cache + 原 Audit Archive；含强制 RO 与 `fleet-cache/v4`。

### 13.1 Scope

- cache path separation（local-state / fleet_id）
- `open_cache_readonly()` / `open_cache_for_sync()`：**真正** SQLite `mode=ro` 用于 query / UI GET（D47）
- `fleet-cache/v4` 升级
- audit archive create/verify/inspect/restore
- additive APIs：`sync --full`（若 0.4.1 未完成实现则此处完成）、cached query 面
- per-node sync transaction / PARTIAL 模型

不实现：adopt/provision、UI v2 大改、telemetry。

### 13.2 Sync v2（`sync --full`）

对每个 active node：

1. identity
2. version
3. health
4. users metadata
5. audit delta
6. instance observation

默认：sequential。

未来可以增加：`--jobs N`，但不是 0.4.2 gate。

默认 `sync`（无 `--full`）在 0.4.x **仍为 legacy audit**。

### 13.3 Per-node Transaction

每个节点独立：

```
pull
→ validate
→ DB transaction
→ cursor commit
```

Node A 成功、Node B 不可达时：

```
A = committed
B = error
overall = PARTIAL
exit = 2
```

不得为了整个 Fleet atomicity 回滚 A。

### 13.4 Sync Failure Rules

以下必须 fail closed：

- node_id mismatch
- instance identity impossible transition
- protocol mismatch
- invalid JSON/schema（namespaced errors）
- audit cursor ahead
- export sequence invalid

失败节点不得前移 audit cursor。

### 13.5 Definition of Done

- UI / stats / audit / cached status 全部可从本地 cache 服务
- query 路径强制 RO connection
- archive round-trip 不碰 cursor
- 新机器：Workspace + Audit Archive + fresh fleet.db 可恢复历史查询

### 13.6 Acceptance Criteria

保留并归属本里程碑：

- **AC-4.1-01** — 无 `sync` / `sync --full` 时打开 UI 不产生 SSH。
- **AC-4.1-03** — 一次 `sync --full` 后 Nodes/Users/Audit/Stats 全部能从本地 DB 查询。
- **AC-4.1-04** — 单节点离线只产生 PARTIAL，不影响其它节点 cache。
- **AC-4.1-05** — Audit archive restore 不改变任何 sync cursor。
- **AC-4.1-06** — 新机器可：Workspace + Audit Archive + fresh fleet.db 恢复历史查询能力。

【新增】cache/archive：

- **AC-4.2-C01** — query / UI GET 使用真正的 SQLite read-only connection（非仅约定）。
- **AC-4.2-C02** — `fleet-cache` schema 升级到 v4；错误信息使用 `fleet-cache` namespace。
- **AC-4.2-C03** — cache 位于 machine-local state 路径，按 `fleet_id` 隔离；`CACHE_FLEET_MISMATCH` fail closed。
- **AC-4.2-C04** — `sync --full` 可用且不改变无参 `sync` 的 legacy audit 默认语义。

---

## 14. v0.4.3 — Adopt & Provision

**【覆盖原 SPEC】** 原 §14/§15（原版本号 0.4.2）归位至此。

### 14.1 Adopt

```
vcl-fleet node adopt NAME --host HOST
```

目标：

```
已有 Vincula 节点
→ identity verify
→ host trust
→ registry
→ initial sync（legacy sync 与/或 sync --full，按实现选择并文档化）
```

### 14.2 Provision

```
vcl-fleet node provision NAME \
  --host HOST
```

目标：

```
fresh VPS
→ usable Vincula node（pinned Node 版本，可为 0.3.1）
→ registered Fleet node
```

管理员应只需要提供：

- SSH reachable host
- SSH credential
- 必要时 host-key confirmation

### 14.3 Provision Preflight

**【覆盖原 SPEC / D35 修订】** 必须检查：

- SSH connectivity
- host key
- OS / OS version / architecture
- root / sudo -n
- disk space
- existing Vincula
- existing conflicting services/files
- TCP port availability
- required commands
- apt availability
- outbound HTTPS
- sing-box release reachability
- public server address availability
- Reality target reachability

若用户提供：

```
VCL_SERVER=...
```

则可**跳过 ipify dependency**。

### 14.4 Existing Vincula

如果目标已有 Vincula：

```
node provision
```

必须拒绝并提示：

```
use node adopt
```

不得隐式升级已有节点。

### 14.5 Artifact Flow（D51）

**【覆盖原 SPEC】** 单 architecture-neutral node tarball + manifest；**不**要求双 arch payload：

```
payload/
├── vincula-node-0.3.1.tar.gz
├── vincula-node-0.3.1.tar.gz.sha256
└── payload-manifest.json
```

`payload-manifest.json` 示例：

```json
{
  "controller_version": "0.4.3",
  "node_payload_version": "0.3.1",
  "sha256": "...",
  "supported_os": ["debian12", "debian13", "..."],
  "supported_arch": ["amd64", "arm64"]
}
```

架构选择在远端 `uname` → 下载对应 pinned sing-box（安装器已有双 SHA256）。

流程：

```
controller payload
     ↓
local sha256
     ↓
SCP temp path
     ↓
remote sha256
     ↓
unpack
     ↓
installer
```

任何 digest mismatch：fail closed。

### 14.6 Provision Commit Boundary

Workspace 注册节点必须发生在：

```
remote install
+ vcl verify
+ vcl identity
```

全部成功之后。

若远端已经安装成功但本地 Workspace commit 失败：

```
REMOTE_READY_LOCAL_UNCOMMITTED
```

并建议：

```
vcl-fleet node adopt NAME --host HOST
```

不得重复安装。

### 14.7 Initial Sync

Provision 成功后自动进行最终 observation（`sync` 与/或 `sync --full`，文档固定一种，优先与 cache 模型一致）。

### 14.8 Register + `node add` 兼容（D49）

见 §2 D33。0.4.x 完整保留 `node add` 为 legacy alias，文档标记，无强制 runtime warning。

### 14.9 Acceptance Criteria

保留并归属本里程碑（原 AC-4.2-*）：

- **AC-4.2-01** — Fresh Debian/Ubuntu VPS 仅凭有效 SSH key 可完成 provisioning。
- **AC-4.2-02** — 无 host trust 时 interactive 模式明确展示 fingerprint。
- **AC-4.2-03** — Non-interactive 无 `--host-key` 时拒绝。
- **AC-4.2-04** — Artifact digest mismatch 时 remote installer 不运行。
- **AC-4.2-05** — Provision 后 `vcl verify` PASS、node registered、sync PASS、real VLESS handshake PASS。
- **AC-4.2-06** — Provision 不增加 VPS 公网监听端口。
- **AC-4.2-07** — Controller 不存 SSH/sudo password。

【新增】：

- **AC-4.3-P01** — Controller payload 为单 tarball + manifest；无双 arch node tarball 要求。
- **AC-4.3-P02** — 文档与输出不使用「air-gap」描述 provision；`VCL_SERVER` 可跳过 ipify。
- **AC-4.3-P03** — `node add` ≡ adopt；`node add --offline --node-id` ≡ register。

---

## 15. （保留编号）节点命令一览（0.4.3+）

见 D33/D49；本节无额外规范。

---

## 16. v0.4.4 — Web UI v2

**【覆盖原 SPEC】** 原 §16–§25（原版本号 0.4.3）归位至此。

### 16.1 一级导航

固定为：

```
Overview
Nodes
Users
Traffic
Audit
Operations
```

### 16.2 Overview

第一屏回答：Fleet 是否正常？哪里有问题？数据多久没同步？今天用了多少？哪些用户/节点最活跃？

至少显示：

- Fleet Health
- Node Count
- Healthy / Offline
- User Count
- Active/Recent Connections
- Traffic Today
- Last Sync
- Cache Age
- Warnings

以及：

- Traffic Trend
- Node Health
- Top Users
- Top Destinations
- Recent Problems

### 16.3 Nodes

列表：

```
NODE  HEALTH  VERSION  LAST SYNC  USERS  TRAFFIC TODAY  ENDPOINT
```

Node Detail：

- Identity
- Health
- Traffic
- Users
- Audit
- Instance History
- Last Operations

不得显示：

- Reality private key
- Clash secret
- VLESS UUID

### 16.4 Users

列表：

```
USER  DEPARTMENT  NODES  ENABLED STATE  TODAY  30D
```

User Detail：

- logical user_id
- per-node deployment
- enabled/disabled
- traffic
- destinations
- audit

必须体现：

```
one logical user
→ multiple nodes
→ per-node credential state
```

### 16.5 Traffic

Traffic 是聚合分析页面，不与 Audit 混合。

过滤：

- time
- node
- user
- department
- destination

至少提供：

- traffic trend
- top users
- top nodes
- top hosts
- connection count
- upload/download

始终标注：

```
Approximate accounting
```

### 16.6 Audit

连接级分析。

过滤：

- time range
- user
- node
- destination host
- destination IP
- port
- network

必须：SQL filter before LIMIT。

分页不得先 LIMIT 再过滤。

### 16.7 Operations

**【覆盖原 SPEC / D53】** Operations 页展示本机 Controller 的**操作历史**，不是「UI 能执行这些操作」。

```
TIME  OPERATION  TARGET  STATE  RESULT
```

例如历史类别：sync、node.provision、node.adopt、node.replace、user.add、user.rotate、backup、restore。

不得记录 secret argv（credential URI 必须 redact）。

### 16.8 UI 操作矩阵（D53）

| Operation | UI direct execute | Command Builder | Operations history |
| --- | --- | --- | --- |
| Sync | Yes（调用 `sync --full`） | — | Yes |
| Probe | Yes | — | Yes |
| Verify | Yes | — | Yes |
| Adopt | No | Yes | Yes |
| Provision | No | Yes | Yes |
| User Add | No | Yes | Yes |
| Rotate | No | Yes | Yes |
| Replace | No | Yes | Yes |
| Restore | No | Yes | Yes |
| Reseed | No | Yes | Yes |

可直接执行时必须提示：

```
This action contacts remote nodes over SSH.
```

Command Builder 示例：

```
Node: lax
Host: 1.2.3.4

Generated command:

vcl-fleet node provision lax --host 1.2.3.4

[COPY]
```

### 16.9 UI Security

继续保持：

- loopback only
- Host validation
- per-process token
- Origin validation
- JSON POST
- worker cap
- request timeout

拒绝：

- 0.0.0.0
- LAN address
- public address

任何新增 UI endpoint 必须先分类为：

```
CACHE READ
OBSERVATION
MUTATION
```

v0.4 UI 不增加高风险 MUTATION endpoint。

### 16.10 Acceptance Criteria

保留并归属本里程碑（原 AC-4.3-*）：

- **AC-4.3-01** — Overview 在一次 sync（`--full`）后完全离线可用。
- **AC-4.3-02** — 页面浏览没有 SSH side effect。
- **AC-4.3-03** — 所有远端操作均由显式用户动作触发。
- **AC-4.3-04** — UI 无 secret exposure。
- **AC-4.3-05** — Nodes / Users / Traffic / Audit 信息能够覆盖日常管理员主要查看需求。
- **AC-4.3-06** — 常见 CLI mutation 能从 UI 在 2–3 次点击内生成完整命令。

【新增】：

- **AC-4.4-U01** — Sync Fleet / Sync Node 按钮调用 `vcl-fleet sync --full`，不调用无参 legacy `sync` 冒充全量刷新。
- **AC-4.4-U02** — D53 矩阵中 No 的操作不可经 UI 直接执行，仅 Command Builder。

---

## 17–25. （原 UI 分节编号）

内容已并入 §16；保留交叉引用：原 Overview=§17 … UI Security=§24、原 AC=§25 → 现 §16.2–§16.10。

---

## 26. v0.4.5 — Integration & Hardening

**【覆盖原 SPEC】** 原 0.4.4；新增里程碑编号 0.4.5。

0.4.5 不新增大功能。

用于：

- migration hardening
- cross-machine validation
- provision live validation
- UI polish
- docs
- artifact
- security review
- **0.4 Replace Live Gate**（D56）

### 26.1 Required Live Matrix

至少：

- A. 0.3.1 legacy → Workspace migration
- B. Office WSL → sync / sync --full → UI
- C. Workspace copy → Home WSL → local credential bind → sync → UI
- D. Audit archive export → second machine restore → historical query
- E. Fresh VPS provision
- F. Existing 0.3.1 node adopt
- G. **Replace Live Gate**（物理实例替换端到端；B24 补跑**不是** blocker，本 Gate 才是）

### 26.2 Dependabot（D55）

CI 依赖升级顺序：

```
PR #2 (checkout v7)           → recreate/rebase → full CI → merge
PR #1 (upload-artifact v7)    → recreate/rebase again → full CI → merge
```

（先 checkout 后 upload-artifact，按 CI 执行顺序。）

### 26.3 Acceptance Criteria（【新增】）

- **AC-4.5-01** — §26.1 Live Matrix A–G 全部 PASS，证据可追溯。
- **AC-4.5-02** — Replace Live Gate PASS；明确 B24 历史补跑非发布 blocker。
- **AC-4.5-03** — 无新增 VPS 公网 management listener。

---

## 27. v0.4 Final Definition of Done

必须同时成立：

- Fleet 可以脱离单一管理员机器
- fleet.db 不再是 portable SoT
- Workspace 不含 secret / machine paths
- Host trust 可随 Workspace 移动
- 新机器能重新构建 cache（`sync --full`）
- 历史 Audit 可以 export/restore
- fresh VPS 可由 Fleet provision（非 air-gap 表述）
- 现有 VPS 可 adopt
- UI v2 覆盖主要 observation workflow
- 无新增远端 management port
- Controller 0.4.x 可管理 Node 0.3.1
- 裸 `status` cache-only + `probe` live 已 documented

---

## 28. v0.5.x 总目标

v0.5 将 Fleet Controller 从：

> Fleet configuration + audit manager

扩展为：

> Fleet operations + observability controller

但不改变基本网络安全模型。

Node **首次 capability/telemetry 升级**版本： **0.5.0**（**0.3.2** 仅为 0.4.5 payload/legacy-seed 制品 bump）。

---

## 29. Observation Plane

定义 `Observation Plane` 必须具备：

- read-only
- versioned
- bounded
- no secrets
- no arbitrary command
- no mutation

---

## 30. v0.5.0 — Observation Protocol

新增节点命令：

```
vcl telemetry snapshot --json
```

返回 cheap heartbeat。Schema namespace：`telemetry/v1`。

### 30.1 Telemetry Schema v1

示意：

```json
{
  "schema_version": 1,
  "node_id": "UUID",
  "instance_id": "UUID",
  "observed_at": "RFC3339",

  "system": {
    "uptime_seconds": 123456,
    "load_1": 0.10,
    "load_5": 0.08,
    "load_15": 0.04,
    "memory_used_bytes": 123,
    "memory_total_bytes": 456,
    "disk_used_bytes": 123,
    "disk_total_bytes": 456
  },

  "network": {
    "rx_bytes": 123,
    "tx_bytes": 456
  },

  "sing_box": {
    "active": true,
    "connections": 12
  },

  "accountd": {
    "active": true,
    "last_poll_age_seconds": 3
  }
}
```

### 30.2 Heartbeat 必须 Cheap

30 秒级 Heartbeat 不采：

- apt update
- 完整 package list
- SMART long test
- 大目录扫描
- 完整 journal
- 全量 audit
- 复杂 network probe

这些归入 `Inspection Plane`，按需执行。

### 30.3 Observe 路由强制（D57）

Observation 强制 observe credential routing；Control 强制 admin。显式配置 observe 后禁止静默 admin fallback。

### 30.4 sync 默认切换窗口（可选）

若切换：

```
0.5.x 可考虑：
  sync              = full
  sync --audit-only = legacy
```

须先有 0.4 release notes deprecation window；用户倾向仍是先看真实使用体验再决定。

---

## 31. Observation Credential

v0.5 支持：

```
observe_credential_ref != admin_credential_ref
```

默认仍可相同。

未来可配置 `vcl-observer` 低权限账户。

### 31.1 Optional Restricted Observer

可选安全增强：

- no sudo
- no PTY
- no port forwarding
- no agent forwarding
- no arbitrary shell

可进一步使用 OpenSSH forced-command：

```
仅允许：vcl telemetry *   vcl observe *
```

不得作为 v0.5 基础运行要求。

---

## 32. v0.5.0 Acceptance Criteria

- **AC-5.0-01** — Telemetry snapshot 无写操作。
- **AC-5.0-02** — Telemetry response 不包含 secret。
- **AC-5.0-03** — 错误 `node_id` / `instance_id` 必须被 Controller 拒绝。
- **AC-5.0-04** — Telemetry JSON 必须有 size limit 和 schema validation（`telemetry/v1`）。
- **AC-5.0-05** — Telemetry 不需要新网络监听器。
- **AC-5.0-06**（【新增 / D57】）— 显式 observe 凭据配置后，Observation 路径禁止静默 fallback 到 admin。

---

## 33. v0.5.1 — Monitoring

新增：

```
vcl-fleet monitor --interval 30
vcl-fleet monitor --node lax --interval 30
```

第一版为 foreground process，不要求 system daemon。

---

## 34. Monitoring Transport

基线：

```
every interval
→ SSH（observe routing）
→ telemetry snapshot
```

优化可包括 OpenSSH connection reuse、long-lived SSH read stream，但不得改变协议语义。

---

## 35. Telemetry Storage

Fleet DB 新增：

- telemetry_samples
- telemetry_rollup_5m
- telemetry_rollup_hourly

推荐默认 retention：

```
raw 30s samples     24h
5-minute rollup      7d
hourly rollup       90d
```

允许配置。

---

## 36. Monitoring Failure

单节点失败不得终止整个 Monitor。

记录：

- reachable
- error
- last_success
- failure_count

不得自动：

- restart VPS
- restart sing-box
- change config

---

## 37. UI Monitoring

UI 新增：

- Current Health
- CPU/load
- memory
- disk
- connections
- network rate
- service status
- telemetry age

仍然只读取本地 cache。

UI 页面加载不得启动 Monitor。

如未来提供 `Start Monitoring` 必须是显式动作。

---

## 38. v0.5.1 Acceptance Criteria

- **AC-5.1-01** — 10+ 节点 30 秒 heartbeat 可稳定运行。
- **AC-5.1-02** — 关闭 Monitor 不影响 VPS。
- **AC-5.1-03** — Controller crash 不影响 VPS 服务。
- **AC-5.1-04** — Telemetry database retention 有界。
- **AC-5.1-05** — VPS 防火墙监听端口与启用 Monitor 前相同。

---

## 39. v0.5.2 — VPS Inspect & Drift

Telemetry 负责：continuous cheap metrics。

Inspect 负责：slow / detailed / on-demand observation。

新增：

```
vcl-fleet inspect NODE
```

能力探测优先于单纯 `version >= 0.5`（见 §54）。

---

## 40. Inspect Domains

至少可逐步覆盖：

- OS / kernel
- CPU
- RAM / swap
- disk
- filesystem
- clock / NTP
- network interfaces
- TCP congestion control
- qdisc
- selected sysctl
- socket/file limits
- sing-box version
- sing-box service
- accountd service
- firewall summary
- package update status
- reboot-required status

不得读取用户内容。

---

## 41. Drift

Workspace 可逐步引入 `desired policy`：

- 例如 required Vincula version、required service state、preferred TCP congestion algorithm、disk warning threshold、clock skew threshold

输出：

```
CURRENT  EXPECTED  STATE
```

例如：

```
BBR
current: cubic
desired: bbr
state: DRIFT
```

---

## 42. Inspect 不做 Mutation

```
vcl-fleet inspect
```

必须永远 read-only。

---

## 43. v0.5.2 Acceptance Criteria

- **AC-5.2-01** — Inspect 可在不修改 VPS 的情况下生成完整 system snapshot。
- **AC-5.2-02** — 所有建议均能追溯到 observed value / rule / recommendation。
- **AC-5.2-03** — Inspect 不允许 arbitrary shell 插件。

---

## 44. v0.5.3 — Tuning & Maintenance

从 `Observe` 扩展至：

```
Plan
→ Explicit Apply
→ Verify
→ Rollback if possible
```

---

## 45. Tuning Workflow

```
vcl-fleet tune plan NODE
```

输出：

```
CURRENT  DESIRED  CHANGE  RISK  ROLLBACK
```

不修改远端。

真正修改：

```
vcl-fleet tune apply NODE
```

必须显式确认。

---

## 46. 第一批 Tuning Domain

优先考虑：

- TCP congestion control
- qdisc
- selected safe sysctl
- file descriptor limits
- service limits
- Vincula/sing-box recommended settings

不把 `arbitrary sysctl editor` 作为产品能力。

所有 tunable 必须有：

```
allowlist  validator  current reader  apply implementation  post-check  rollback implementation
```

---

## 47. Maintenance Workflow

读：`vcl-fleet maintenance check NODE`

规划：`vcl-fleet maintenance plan NODE`

执行：`vcl-fleet maintenance apply NODE`

逐步支持：

- package updates
- Vincula upgrade
- service restart
- reboot-required handling
- disk cleanup of Vincula-owned data

---

## 48. 禁止 Generic Remote Exec

不得新增：

```
vcl-fleet exec NODE "arbitrary shell"
```

也不得通过 Web UI 包装任意 root shell。

所有 Control Plane 功能必须是：

- typed operation
- validated arguments
- known behavior
- known rollback semantics

---

## 49. Plan / Apply Contract

Plan 必须产生：

- operation_id
- target node
- precondition
- proposed changes
- risk
- expected postcondition
- rollback plan

Apply 前必须重新验证 precondition。

如果当前状态已经变化：`PLAN_STALE`，拒绝执行。

---

## 50. Multi-node Mutation

继续使用现有 PARTIAL 模型：SUCCESS / PARTIAL。

不声称存在 distributed rollback。

例如 10 nodes、8 success、2 failed → PARTIAL，每个节点提供 remediation。

---

## 51. Health Gate

任何 tuning / maintenance mutation 后：

- service state
- Vincula verify
- network/proxy health

必须通过。

否则：attempt rollback；若 rollback 无法完整恢复：`ROLLBACK_PARTIAL`。

---

## 52. v0.5.3 Acceptance Criteria

- **AC-5.3-01** — `tune plan` 无远端 mutation。
- **AC-5.3-02** — `apply` 必须显式确认。
- **AC-5.3-03** — Plan stale 时禁止 apply。
- **AC-5.3-04** — 任何 tune item 都必须有 rollback strategy 或明确标记 `NON_ROLLBACKABLE`。
- **AC-5.3-05** — 不存在 arbitrary remote shell interface。
- **AC-5.3-06** — Heartbeat/Monitor 永远不能触发 Control Plane operation。

---

## 53. Application Architecture

由于当前 Controller 已较大，v0.4 开始进行渐进式模块化。

目标不是一次大重构。

**【覆盖原 SPEC】** 0.4.0 **先**抽出 seam 并保持行为不变：

```
lib/vincula-fleet/
├── workspace.py
├── access.py
├── trust.py
├── cache.py
├── transport.py
├── sync.py
├── query.py
├── nodes.py
├── users.py
├── audit_archive.py
├── provision.py
├── operations.py
└── service.py
```

UI：

```
HTTP
  ↓
service/query API
```

CLI：

```
argparse
  ↓
service API
```

禁止新增 UI 对随机 private function 的依赖。

---

## 54. Compatibility Matrix

**【覆盖原 SPEC】** 使用用户新表：

| Controller | Minimum Node | 新 Node 功能要求 |
| --- | --- | --- |
| 0.4.0 | 0.3.1 | 无 |
| 0.4.1 | 0.3.1 | 无 |
| 0.4.2 | 0.3.1 | 无 |
| 0.4.3 | 0.3.1 | 无 |
| 0.4.4 | 0.3.1 | 无 |
| 0.4.5 | 0.3.1 | 新 provision 钉 Node **0.3.2**（legacy seed）；已有 0.3.1 不强制升级 |
| 0.5.0 | 0.3.1 basic / 0.5.0 telemetry | Telemetry |
| 0.5.x | capability-based | Inspect/Tuning 按能力判断 |

基础 Fleet 能力不得因为 Telemetry 引入而强制所有节点同时升级到 0.5。

长期：

```json
capabilities:
  audit_export_v2
  backup_v1
  telemetry_v1
  inspect_v1
```

优先于单纯 `version >= 0.5` 判断。

---

## 55. Node Upgrade Contract

**【覆盖原 SPEC】** Controller 与 Node 版本解耦后：

- `0.4.0–0.4.5` Controller **Minimum Node = 0.3.1**（已有节点不强制升级）。
- **0.4.5** 新 provision payload 钉 **Node 0.3.2**（legacy seed / installer）；这是首个 **payload** bump，不是 capability 升级。
- 首个 **capability/telemetry** Node 升级仍为：`0.5.0`（Telemetry）。

所有 `0.3.1 → 0.3.2` / `0.3.1 → 0.5.x`（以及未来同主线升级）：

默认必须保持：

- node_id
- instance_id
- Reality keys
- credential UUID
- user_id
- existing URI
- accounting history

除非管理员显式执行 rotate / replace / secretless restore。

---

## 56. Security Invariants

以下条件适用于整个 0.4/0.5：

- **S1** No public Vincula management port.
- **S2** No node → controller unsolicited connection.
- **S3** No cloud relay requirement.
- **S4** Strict SSH host-key checking.
- **S5** No SSH private key in Workspace.
- **S6** No password storage.
- **S7** UI loopback only.
- **S8** UI page load has no remote side effects.
- **S9** Observation cannot mutate.
- **S10** Telemetry contains no secrets.
- **S11** Telemetry cannot carry commands.
- **S12** No arbitrary remote exec.
- **S13** Provision artifact is digest verified.
- **S14** Control Plane uses explicit operation.
- **S15** PARTIAL is reported honestly.
- **S16** Controller compromise does not create a new VPS network listener.
- **S17** Stopping Controller does not affect proxy availability.

---

## 57. Testing Strategy

测试从现有大 Bash harness 逐步分层。

保持：installer / shell transaction tests。

逐步增加：

- Python unit tests
- contract tests
- workspace migration fixtures
- cache tests
- SSH fake integration
- artifact black-box
- live VPS acceptance

建议层级：

```
L1 Unit
L2 Contract
L3 Integration
L4 Artifact
L5 Live
```

---

## 58. v0.4 Live Gates

发布 v0.4 stable 前至少：

- 0.3.1 → Workspace migration
- Workspace cross-machine handoff
- fresh local cache rebuild
- audit archive export/restore
- existing node adopt
- fresh VPS provision
- UI v2 browser test
- Windows/WSL controller test
- no-new-listener security check
- **Replace Live Gate**（0.4.5；B24 非 blocker）

---

## 59. v0.5 Live Gates

至少：

- 30s monitor multi-hour run
- SSH reconnect test
- controller crash/restart
- node reboot/reconnect
- telemetry retention
- observer credential test（含禁止静默 admin fallback）
- inspect read-only verification
- tuning plan/apply/rollback
- maintenance failure injection
- no-new-port verification

---

## 60. 版本路线图

**【覆盖原 SPEC】**：

```
v0.3.1  Stable / immutable baseline
        │
        ▼
v0.4.0  Compatibility Foundation
        schema namespace · version decouple · Workspace/Access/Trust seam ·
        legacy adapter · migrate --dry-run · RO/RW seam
        │
        ▼
v0.4.1  Portable Workspace
        actual migration · fleet_id · credential refs · known_hosts ·
        instance history · cross-machine · status cache-only (breaking) · probe
        │
        ▼
v0.4.2  Local Cache & Archive
        cache path · true mode=ro · fleet-cache/v4 · audit archive · sync --full
        │
        ▼
v0.4.3  Adopt & Provision
        node adopt / provision / register · preflight · digest-verified payload
        │
        ▼
v0.4.4  Web UI v2
        Overview / Nodes / Users / Traffic / Audit / Operations · D53 matrix
        │
        ▼
v0.4.5  Integration & Hardening
        live matrix · Replace Live Gate · legacy single-user seed ·
        Node 0.3.2 payload pin · UI PARTIAL close · operation journal
        │
        ▼
v0.5.0  Observation Protocol / Telemetry Snapshot / Observe Credential routing
        （首个 **capability/telemetry** Node 升级；0.3.2 仅为 payload bump）
        │
        ▼
v0.5.1  Monitoring
        │
        ▼
v0.5.2  Inspect & Drift
        │
        ▼
v0.5.3  Tuning & Maintenance
```

---

## 61. v0.4 的最终用户体验

第一次新建 Fleet：

```
vcl-fleet workspace init
vcl-fleet node provision lax --host 1.2.3.4
vcl-fleet node provision sjc --host 5.6.7.8
vcl-fleet sync --full
vcl-fleet ui
```

已有 0.3.1：

```
vcl-fleet workspace migrate --dry-run
vcl-fleet workspace migrate
vcl-fleet sync --full
vcl-fleet ui
```

换到另一台电脑：

```
vcl-fleet workspace open /path/to/shared-workspace
vcl-fleet access bind admin-default \
  --identity-file ~/.ssh/vcl
vcl-fleet sync --full
vcl-fleet ui
```

历史 Audit：

```
vcl-fleet audit archive create \
  --from 2026-01-01T00:00:00Z \
  --to 2026-06-30T23:59:59Z \
  --output 2026-H1.vclaudit
```

日常：

```
vcl-fleet status          # cache-only（0.4.1+）
vcl-fleet probe           # live
vcl-fleet sync            # legacy audit（0.4.x 默认）
vcl-fleet sync --full     # 刷新本地 observation cache
```

---

## 62. v0.5 的最终用户体验

持续监控：

```
vcl-fleet monitor --interval 30
```

查看 VPS：

```
vcl-fleet inspect lax
```

发现：

```
TCP congestion: cubic
Recommended: bbr

Disk usage: 82%
Updates: 17
Reboot required: yes
Clock skew: 1.3s
```

生成计划：

```
vcl-fleet tune plan lax
```

管理员确认后：

```
vcl-fleet tune apply lax
```

维护：

```
vcl-fleet maintenance check lax
vcl-fleet maintenance plan lax
vcl-fleet maintenance apply lax
```

Web UI 主要承担：看 / 找问题 / 比较 / 过滤 / 生成操作入口

CLI 主要承担：高权限 mutation / 明确 apply / 恢复 / 替换 / 调优 / 维护

---

## 63. 最终产品方向

Vincula v0.5 应形成如下形态：

```
            Local Fleet Workstation
                  │
        ┌─────────┼─────────┐
        │         │         │
      Web UI     CLI     Local DB
        │         │         │
        └─────────┼─────────┘
                  │
          Fleet Controller
                  │
          System OpenSSH
          /             \
   Observation        Control
      Pull              Apply
       │                  │
   ┌───┼────┐         ┌───┼────┐
   │   │    │         │   │    │
 VPS VPS  VPS        VPS VPS  VPS
```

它可以拥有越来越强的 VPS 管理、监控、调优和维护能力，但仍然坚持：

> «Controller 主动连接 VPS，而不是 VPS 暴露一个新的管理控制面。»

这应当成为 Vincula 0.4–0.5 乃至后续版本最核心的架构原则。

---

## 64. 决策记录（D45–D58 + 用户修订）

> 本章为用户拍板意见的**忠实转录**（源自 `vcl-decisions-v0.4.md`），权威优先级高于 Draft v1 原文。不摘要、不发挥。

### D45 — Schema 版本命名（用户修订，2026-08-20）

从 0.4 SPEC 开始规定：**schema version 永远必须带 namespace**。

统一术语：

| Namespace | 当前版本 | 对象 |
| --- | --- | --- |
| `accounting-db/v4` | 4 | 节点 `accounting.db` |
| `fleet-registry/v2` | 2 | controller `fleet.json` |
| `fleet-cache/v3` | 3 | controller `fleet.db` |
| `workspace/v1` | 1 | 未来 `workspace.json` |
| `audit-archive/v1` | 1 | 未来 `.vclaudit` |
| `telemetry/v1` | 1 | 未来 telemetry JSON |

代码也建议逐步改名（常量）：

```python
ACCOUNTING_DB_SCHEMA_VERSION = 4
FLEET_REGISTRY_SCHEMA_VERSION = 2
FLEET_CACHE_SCHEMA_VERSION   = 3
WORKSPACE_SCHEMA_VERSION     = 1
AUDIT_ARCHIVE_SCHEMA_VERSION = 1
TELEMETRY_SCHEMA_VERSION     = 1
```

0.4.0 **不需要**为此修改磁盘格式。可暂时保留内部兼容 alias，逐步消除旧名字：

```python
FLEET_SCHEMA_VERSION    = FLEET_REGISTRY_SCHEMA_VERSION
FLEET_DB_SCHEMA_VERSION = FLEET_CACHE_SCHEMA_VERSION
```

文档和 error message **立即禁止**裸名写法。例：

```
❌ unsupported schema 4
✅ unsupported accounting-db schema: 4
✅ unsupported fleet-cache schema: 3
✅ unsupported fleet-registry schema: 2
```

【新增】此修正应放到 **0.4.0 最前面**。

### 0.4.x 版本切分（用户修订，2026-08-20）【覆盖原 SPEC §60 路线图 / §10–§27】

用户建议把 0.4.x 重新切成：

```
0.4.0  Compatibility Foundation
       schema namespace
       controller/node version decouple
       Workspace module/API seam
       legacy adapter
       migrate --dry-run

0.4.1  Portable Workspace
       actual migration
       fleet_id
       credential refs
       dedicated known_hosts
       instance history portability
       cross-machine acceptance

0.4.2  Local Cache & Archive
       cache path separation
       open_cache_readonly()
       open_cache_for_sync()
       fleet-cache/v4
       audit archive/export
       additive cached/full-sync APIs

0.4.3  Adopt & Provision
       node adopt
       node provision
       preflight
       artifact transfer

0.4.4  Web UI v2
       Overview
       Nodes
       Users
       Traffic
       Audit
       Operations

0.4.5  Integration / Hardening
```

理由（用户原话要点）：
- 这样 **0.4.0 就没有「大迁移 + 大 DB 改造 + SSH trust 改造」同时发生**。
- 特别建议 0.4.0 **先从 monolith 抽出 `workspace.py` `access.py` `trust.py`，但保持原 CLI 行为完全不变**。
- 这相当于**先建立 seam，再添加功能**，而不是一边迁移状态一边拆 6000 行 controller（`vincula-fleet.py` ~6220 行）。

注意点（本决策隐含的映射变化，供修订 spec 落位）：
- `fleet-cache/v4`（D24 只读 cache / `open_cache_readonly()` / `open_cache_for_sync()`）→ **0.4.2**（审查原建议 0.4.0 拆 API、0.4.1 强制 ro）
- UI v2 → **0.4.4**（原 spec 0.4.3）
- adopt/provision → **0.4.3**（原 spec 0.4.2）
- migrate（真实迁移）→ **0.4.1**（原 spec 0.4.0）
- hardening → **0.4.5**（新增里程碑，原 spec 0.4.4）

### Controller/Node 版本解耦（用户修订，2026-08-20）【覆盖原 SPEC §54 兼容矩阵 / §55 Node Upgrade Contract / 审查 D46】

#### 现状问题（用户指出，Hermes 已核实属实）

当前版本机制把两者错误耦合：

- `VCL_FLEET_VERSION = "0.3.1"`（`lib/vincula-fleet.py:43`）——controller 本身有版本。
- 但 `scripts/build-controller.sh:12` **不从它取** Controller 版本，而是从 `vincula.sh` → `VINCULA_VERSION` 读取命名 `vincula-controller-${VERSION}.zip`。
- node artifact 同样从 `vincula.sh` 的 `VINCULA_VERSION` 构建 `vincula-node-${VERSION}`（`scripts/rc-build-artifacts.sh:63`）。

事实上现在是：

```
Repo Version
     ├── Node Version
     └── Controller Version
```

强制绑在一起。

#### 用户建议：0.4.0 第一批修改就解耦

分离 **Node Runtime Version** 与 **Controller Version**：

- `build-controller.sh` 从 **`VCL_FLEET_VERSION`** 读取 controller version。
- `build-release.sh` 继续从 **`VINCULA_VERSION`** 读取 node version。

于是形成合理状态：

```
Controller 0.4.0  +  Node 0.3.1
Controller 0.4.1  +  Node 0.3.1
Controller 0.4.2  +  Node 0.3.1
```

甚至 node provision 也完全可以 `Controller 0.4.3 → install pinned Node 0.3.1`——因为 provisioning 是 Controller feature，**不要求 Node 有新 API**。

真正第一次需要 **capability/telemetry** Node 升级，等 **0.5.0**（`vcl telemetry snapshot --json`）出现之后。
（**0.4.5** 已引入 Node **0.3.2** payload pin / legacy seed；Minimum Node 仍为 0.3.1。）

#### 兼容矩阵改法（替代原 §54 表）

| Controller | Minimum Node | 新 Node 功能要求 |
| --- | --- | --- |
| 0.4.0 | 0.3.1 | 无 |
| 0.4.1 | 0.3.1 | 无 |
| 0.4.2 | 0.3.1 | 无 |
| 0.4.3 | 0.3.1 | 无 |
| 0.4.4 | 0.3.1 | 无 |
| 0.4.5 | 0.3.1 | 新 provision 钉 Node **0.3.2**（legacy seed） |
| 0.5.0 | 0.3.1 basic / 0.5.0 telemetry | Telemetry |
| 0.5.x | capability-based | Inspect/Tuning 按能力判断 |

#### 能力探测（长期方向）

建议未来**不要只检查 `version >= 0.5`**，而逐渐转向 capability 判断：

```json
capabilities:
  audit_export_v2
  backup_v1
  telemetry_v1
  inspect_v1
```

这样长期兼容性会比依赖版本号好很多。

### D35 修订 — Air Gap 断言（用户修订，2026-08-20）【覆盖原 SPEC D35 / 审查 D50】

#### 改名

D35 应改名为：

> **Controller-carried, digest-verified first-party provisioning payload**

#### 准确契约（不是 air-gapped provisioning）

- Controller **不从互联网下载 Vincula 自身代码**。
- Controller **将固定版本的 Vincula node artifact SCP 到 VPS**。
- **两端校验 SHA256**。
- 远端**仍可能需要互联网**：安装 OS dependency、下载 pinned sing-box、检测公网地址并执行 REALITY self-test。

也就是说：**不是 air-gapped provisioning**。

#### 0.4.3 preflight 明确检查

- required commands
- apt availability
- outbound HTTPS
- sing-box release reachability
- public server address availability
- Reality target reachability

如果用户提供：

```
VCL_SERVER=...
```

则可以**跳过 ipify dependency**。

#### 未来真正的离线能力（以后另做）

```
offline provision bundle
├── Vincula node payload
├── sing-box amd64 tarball
└── sing-box arm64 tarball
```

配合 installer 新参数：

```
--sing-box-archive FILE
```

**但即使如此**，如果系统缺 Python/curl/tar 等 package，仍需要 apt repo。

**结论（用户原话）**：除非以后真的解决 OS dependency + binary + public-IP + self-test 全部问题，**不应该使用「air-gap」这个词**。

### status/sync 默认语义保持 0.3.1（用户修订，2026-08-20）【覆盖原 SPEC §11.4 Cached Status / 审查 D58】

**0.4 不直接改变默认语义。** 最稳的兼容方案：

#### 保持 0.3.1 行为（默认不变）

```
vcl-fleet status     # live SSH probe
vcl-fleet sync       # audit sync
```

#### 新增

```
vcl-fleet status --cached
```

表示：只读本地最后一次 observation snapshot，**绝不 SSH**。

```
vcl-fleet sync --full
```

表示：identity + health + users metadata + audit delta → local cache。

#### 结果

想要的 apt-update 心智模型仍可实现：

```
vcl-fleet sync --full
        ↓
local cache
        ↓
UI / audit / stats / cached status
```

UI v2 的 Sync Fleet 按钮**直接调用 `vcl-fleet sync --full`**，不会破坏旧脚本。

#### status 长期保持 live（用户明确倾向）

用户甚至建议 **status 长期保持 live 语义，没有必要非改成 cached**——两个概念都很合理：

```
status            现在服务器到底怎么样？
status --cached   上次同步时服务器怎么样？
```

语义非常清楚。

#### sync 未来默认切换的过渡窗口

如果未来真的希望 `vcl-fleet sync` 默认等价 `--full`，至少应经过：

```
0.4.x
  sync          = legacy audit
  sync --full   = new behavior

0.5.x
  可考虑：
  sync          = full
  sync --audit-only = legacy
```

并在 **0.4 release notes 中明确 deprecation window**。

**用户倾向（原话）**：0.5 之前都不要切默认行为，先看看真实使用体验。

> ⚠️【覆盖说明】上节「status 长期保持 live」的倾向性表述与下方 **D58 正式拍板**不一致。以 D58 为准：0.4.1 起裸 `status` = cache-only（breaking）；`sync` 默认仍按本节（0.5 前不切换，`sync --full` 新增）。

### D47 — `mode=ro` 只读 force 时机（用户拍板，2026-08-20）

- **0.4.0**：建立 **RO/RW API seam**（`open_cache_readonly()` / `open_cache_for_sync()` 边界）。
- **0.4.2 起**：所有 query / UI GET 强制使用**真正的 SQLite read-only connection**。

（现状：唯一入口 `open_fleet_db()` 是 RW + WAL + 读时可能 migrate，audit/stats/UI GET 全走它，对 D24 是潜伏并发问题。）

### D48 — migrate 是否 SSH 补 history（用户拍板，2026-08-20）

**否**（符合 §8.2 不隐式 SSH）。

- 现状：`cmd_node_add` 不写 `instance_history`，只有 sync 时写 → 从未 sync 的节点迁移后 history 为空。
- 缺口**进 dry-run 报告** + AC 写明。
- **migration 不应该为了补这个洞而 SSH。**

### D49 — `node add` / `--offline` 去留（用户拍板，2026-08-20）

#### 正式新命令（三类语义分离）

```
node adopt
    已安装 Vincula
    SSH verify
    register

node provision
    fresh VPS
    install
    verify
    register

node register
    registry-only
    no SSH
    advanced/recovery/testing
```

#### 兼容层

```
node add NAME ...
    ≡ node adopt NAME ...

node add NAME --offline --node-id UUID
    ≡ node register NAME --node-id UUID ...
```

#### 时间窗口

```
0.4.x   完整保留 node add；文档标记 legacy alias；不需要运行时 warning
0.5.x   可以 stderr 提示 deprecated
最早 0.6  再决定是否删除
```

### D51 — Controller payload 多架构（用户拍板，2026-08-20，修正问题定义）

**现状**：`vincula-node-0.3.1.tar.gz` 本身是 **architecture-neutral** 的——里面主要是 Shell/Python/systemd 文件，**没有 amd64/arm64 sing-box binary**。

**真正的架构选择发生在远端**：

```
uname arch
→ amd64 / arm64
→ download corresponding pinned sing-box
```

安装器内部已经分别保存两个 SHA256。

**所以 0.4.3 Controller 不需要**：

```
payload/node-amd64.tar.gz
payload/node-arm64.tar.gz
```

**只需要**：

```
payload/
├── vincula-node-0.3.1.tar.gz
├── vincula-node-0.3.1.tar.gz.sha256
└── payload-manifest.json
```

`payload-manifest.json`：

```json
{
  "controller_version": "0.4.3",
  "node_payload_version": "0.3.1",
  "sha256": "...",
  "supported_os": ["debian12", "debian13", "..."],
  "supported_arch": ["amd64", "arm64"]
}
```

### D52 — Workspace 冲突模型（用户拍板，2026-08-20）

#### Workspace manifest（至少此结构，含 write log 语义）

```json
{
  "revision": 18,
  "write_id": "UUID",
  "parent_revision": 17,
  "parent_write_id": "UUID",
  "state_digest": "sha256:...",
  "last_writer_controller_id": "UUID",
  "updated_at": "..."
}
```

#### 每台 Controller machine-local 再保存

```
last_seen_revision
last_seen_write_id
last_seen_state_digest
```

#### 检测

```
workspace revision < last_seen                     → WORKSPACE_ROLLBACK
workspace revision == last_seen
  but write_id != last_seen_write_id               → WORKSPACE_DIVERGED
state_digest 不匹配实际 portable files             → WORKSPACE_INCONSISTENT
```

#### 每次 mutation 流程

```
read
→ validate digest
→ remember revision/write_id
→ perform operation
→ re-read before commit
→ CAS-like check
→ atomic commit
```

#### 产品承诺必须写准确（用户原话要点）

VCL 提供 **best-effort stale/divergence detection**，**不保证**通用文件同步工具下的 distributed mutual exclusion 或 zero lost updates。

真正的支持模型仍然是：

> **Multi-controller capable, Single-writer operational semantics。**

这是关键。如果未来真的要 concurrent multi-controller，**需要另一个架构**，不应该偷偷把它塞进 Workspace revision。

### D53 — UI 高危操作（用户拍板，2026-08-20）

§22「Operations: sync / node.provision / node.adopt / node.replace ...」应解释成：

> **显示操作历史**。不是「UI 能执行这些操作」。

SPEC 直接加矩阵：

| Operation | UI direct execute | Command Builder | Operations history |
| --- | --- | --- | --- |
| Sync | Yes | — | Yes |
| Probe | Yes | — | Yes |
| Verify | Yes | — | Yes |
| Adopt | No | Yes | Yes |
| Provision | No | Yes | Yes |
| User Add | No | Yes | Yes |
| Rotate | No | Yes | Yes |
| Replace | No | Yes | Yes |
| Restore | No | Yes | Yes |
| Reseed | No | Yes | Yes |

### D55 — Dependabot PR #1/#2（用户拍板，2026-08-20）

```
PR #2 (checkout v7)           → recreate/rebase → full CI → merge
PR #1 (upload-artifact v7)    → recreate/rebase again → full CI → merge
```

（先 checkout 后 upload-artifact，按 CI 执行顺序。）

### D56 — B24 补跑时机（用户拍板，2026-08-20）

**不是 blocker。**

真正必须做的是一个新的 **0.4 Replace Live Gate**，放在：

```
0.4.5 Integration / Hardening
```

### D57 — observe/admin 凭据路由（用户拍板，2026-08-20）

**ACCEPT。**

- **0.4**：schema 预留 admin/observe。
- **0.4 实际**：全部可用 admin（observe=admin，无额外配置成本）。
- **0.5**：Observation 强制 **observe routing**；Control 强制 **admin**。
- 显式配置 observe 后，**禁止静默 admin fallback**。

### D58 — status/probe/sync 副作用分离（用户拍板，2026-08-20）

**ACCEPT WITH CONTRACT。**

- **0.4.1**：将**裸 `status` 改为 cache-only**——这是**明确的 documented breaking change**。
- 新增 **`probe`** 作为 live SSH health operation。
- **`status --live`** 作为 0.4.x compatibility alias。
- **status / probe / sync 三者副作用严格区分**。

> ⚠️【覆盖说明】本条与「status/sync 默认语义保持 0.3.1」一节（用户第 5 条）中「status 长期保持 live 语义」的**倾向性表述不一致**。D58 为正式拍板，以**本条为准**：0.4.1 起裸 `status` = cache-only（breaking），live 语义迁移到 `probe`，`status --live` 仅作 0.4.x 兼容 alias；`sync` 默认语义则仍按第 5 条（0.5 前不切换，`sync --full` 新增）。

---

## 附录 A — AC 归属速查

| AC ID | 归属里程碑 |
| --- | --- |
| AC-4.0-01..05 | 0.4.0 Compatibility Foundation（无行为变更门禁） |
| AC-4.0-M01..M06 | 0.4.1 Portable Workspace（迁移） |
| AC-4.1-02, AC-4.1-S01..S02 | 0.4.1（status/probe/D52） |
| AC-4.1-01, 03..06；AC-4.2-C01..C04 | 0.4.2 Local Cache & Archive |
| AC-4.2-01..07；AC-4.3-P01..P03 | 0.4.3 Adopt & Provision |
| AC-4.3-01..06；AC-4.4-U01..U02 | 0.4.4 Web UI v2 |
| AC-4.5-01..03 | 0.4.5 Integration & Hardening（含 Replace Live Gate） |
| AC-5.0-01..06 | 0.5.0 |
| AC-5.1-01..05 | 0.5.1 |
| AC-5.2-01..03 | 0.5.2 |
| AC-5.3-01..06 | 0.5.3 |

## 附录 B — 版本号归位自检（相对 Draft v1）

| Draft v1 | rev1 |
| --- | --- |
| 0.4.0 大迁移 / Workspace Foundation | → 0.4.1；0.4.0 改为 Compatibility Foundation |
| 0.4.1 Sync/Cache/Archive | → 0.4.2（status breaking 例外：0.4.1） |
| 0.4.2 Adopt/Provision | → 0.4.3 |
| 0.4.3 Web UI v2 | → 0.4.4 |
| 0.4.4 Integration | → 0.4.5 |
| Fleet Registry「Schema 3」 | → `fleet-registry/v2` |
| Fleet DB「Schema 4」 | → `fleet-cache/v4` @ 0.4.2 |
| D35 air-gap | → Controller-carried digest-verified payload（非 air-gap） |
