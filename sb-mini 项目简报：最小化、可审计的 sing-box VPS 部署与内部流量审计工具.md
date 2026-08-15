# sb-mini 项目简报

**项目代号：** sb-mini  
**当前规划范围：** V0.1 → V0.2.x  
**核心定位：** 面向少量自有 VPS 和公司内部用户的最小化 sing-box 部署、用户管理与流量审计工具。  
**首要优先级：** 部署快捷 > 配置可靠 > 供应链可审计 > 运维简单 > 功能丰富。

---

# 1. 项目背景

当前常见的 sing-box “一键安装脚本”能够显著降低 VPS 部署门槛，但通常同时承担以下职责：

- 下载和更新 sing-box；
- 管理 systemd；
- 生成多种协议配置；
- 管理 Caddy、证书、DNS、BBR 等附属组件；
- 管理用户；
- 生成分享链接；
- 更新自身脚本；
- 兼容大量发行版和历史版本。

这种设计适合追求“一站式体验”的公共脚本，但同时扩大了 root 权限下的代码规模、外部依赖数量、更新路径和供应链信任面。

本项目的实际使用场景明显更窄：

1. 用户拥有数台 VPS；
2. VPS 主要用于公司不同部门或同事访问外部网络；
3. VPS 线路质量通常较好；
4. 默认协议可固定为 **VLESS + REALITY + Vision + TCP**；
5. 部署时最重要的体验是：
   - 新 VPS；
   - 执行一次脚本；
   - 自动完成安装；
   - 获得可直接导入客户端的链接；
6. 后续需要对内部用户进行审计，包括：
   - 谁在使用；
   - 使用了多少流量；
   - 哪一天使用；
   - 访问了哪些目标域名/IP；
   - 每个目标消耗了多少上下行流量；
   - 可按用户、部门、日期、VPS、域名等维度筛选和统计；
7. 暂不需要：
   - 公网 Web 面板；
   - 机场式订阅系统；
   - 流量计费；
   - HTTPS MITM；
   - 大规模用户管理；
   - 多租户控制面。

因此，本项目不应成为另一个“全功能 sing-box 管理脚本”，而应围绕上述实际工作流进行最小化设计。

---

# 2. 项目定位

项目定义：

> **sb-mini 是一个面向自有 VPS 的最小化、可审计 sing-box bootstrap 与内部流量观测工具。**

它不是：

- 机场面板；
- 通用 sing-box GUI；
- 多协议大全；
- 网络优化工具箱；
- Caddy/Nginx 管理器；
- VPS 初始化大全；
- 计费系统；
- DPI 或 HTTPS 解密设备。

项目应长期遵循四条原则：

### 2.1 一个功能只解决一个明确问题

如果某项功能不能直接服务于：

- VPS 部署；
- 用户凭据管理；
- sing-box 配置；
- 节点状态；
- 内部流量审计；

则默认不进入项目。

### 2.2 不重新实现 sing-box 已经提供的能力

例如：

- UUID / REALITY key 生成；
- 配置合法性检查；
- 配置格式验证；
- 协议运行时；

尽量调用 sing-box 本身完成。

### 2.3 默认路径必须无交互

最常见部署：

```bash
bash sb.sh
```

应直接完成：

```text
环境检查
→ 安装 sing-box
→ 生成 VLESS + REALITY + Vision
→ 生成默认用户
→ 校验配置
→ 启动服务
→ 健康检查
→ 输出链接
```

不要求用户回答十几个问题。

### 2.4 每增加一个依赖都必须有充分理由

特别避免重新引入：

- jq binary 下载；
- Caddy；
- Docker；
- Redis；
- PostgreSQL；
- Node.js；
- Web dashboard；
- 外部 Geo 数据库；
- 第三方 install script。

---

# 3. 核心使用场景

## 3.1 新 VPS 快速部署

用户购买新的 Debian/Ubuntu VPS 后执行：

```bash
curl -fsSL <release-url>/sb.sh | bash
```

或者更强调审计：

```bash
curl -fLO <release-url>/sb.sh
curl -fLO <release-url>/sb.sh.sha256
sha256sum -c sb.sh.sha256
sudo bash sb.sh
```

脚本完成：

```text
✓ Environment supported
✓ sing-box installed
✓ binary SHA-256 verified
✓ VLESS + REALITY + Vision configured
✓ config validated
✓ systemd active
✓ port listening

User: owner
Node:
vless://...
```

---

# 4. 支持平台

V0.1 明确限制支持范围：

| 项目 | 支持范围 |
|---|---|
| OS | Debian 12/13 |
| OS | Ubuntu 22.04/24.04/26.04 |
| Architecture | amd64 |
| Architecture | arm64 |
| Init | systemd |
| Privilege | root / sudo |
| Protocol | VLESS + REALITY + Vision |
| Transport | TCP |

明确不支持：

- CentOS；
- Rocky Linux；
- Alpine；
- OpenWrt；
- OpenRC；
- Docker-only deployment；
- 非 systemd Linux；
- Windows Server。

减少平台兼容范围是降低维护成本的重要手段。

---

# 5. 协议策略

## 5.1 V0.1 唯一默认协议

```text
VLESS
+
REALITY
+
xtls-rprx-vision
+
TCP
```

原因：

- 不依赖域名；
- 不依赖公开 TLS 证书；
- 非常适合新购 VPS；
- 默认配置变量较少；
- 高质量线路下性能和复杂度平衡较好；
- 能做到真正的零参数部署。

典型默认：

```text
Protocol: VLESS
Flow: xtls-rprx-vision
Security: REALITY
Transport: TCP
Listen: ::
Port: 443
UUID: random
Reality private/public key: generated
Short ID: random
```

---

# 6. 暂缓协议扩展

此前讨论的两个备选协议：

```text
Hysteria2
TUIC
```

仍然具有价值。

但为了防止 V0.2.x 同时承担：

```text
协议扩展
+
身份管理
+
流量采集
+
数据库
+
统计查询
```

导致范围膨胀，建议：

> **V0.2.x 不新增协议。**

Hysteria2/TUIC 推迟到 V0.3 或之后重新评估。

这样 V0.1—V0.2.x 可以只围绕一条经过充分测试的 Reality 数据路径开发。

---

# 7. 系统总体架构

到 V0.2.x 后，整体架构建议为：

```text
                   sb-mini
                      │
       ┌──────────────┴──────────────┐
       │                             │
   Control Plane                Accounting Plane
       │                             │
    sb / sb.sh                  sb-accountd
       │                             │
 ┌─────┼─────────┐          ┌────────┼─────────┐
 │     │         │          │        │         │
install users   config     Events   SQLite   Reports
       │                    │
       │                    │
       └────────┐    ┌──────┘
                ▼    ▼
                sing-box
                   │
        VLESS + REALITY + Vision
                   │
             authenticated user
                   │
                   ▼
             Internet traffic
```

系统由三个逻辑组件构成：

### A. `sb.sh`

Bootstrap installer。

负责：

- 环境检测；
- sing-box 下载；
- SHA-256 校验；
- systemd 安装；
- 初始配置；
- 默认用户；
- helper 安装。

### B. `sb`

管理 CLI。

负责：

- 用户；
- 配置；
- 链接；
- 服务状态；
- 日志；
- 审计查询；
- 统计查询。

### C. `sb-accountd`

V0.2.x 引入的本地 accounting daemon。

负责：

- 接收/采集连接元数据；
- 将运行时事件转换成统一 accounting event；
- 写 SQLite；
- 聚合统计；
- 数据保留和清理。

---

# 8. 目录规划

建议：

```text
/etc/sb-mini/
├── config.toml
├── state.json
├── users.json
└── VERSION

/etc/sing-box/
└── config.json

/usr/local/bin/
├── sing-box
└── sb

/usr/local/lib/sb-mini/
├── sb.sh
└── sb-accountd.py

/var/lib/sb-mini/
└── accounting.db

/var/log/
└── systemd journal

/etc/systemd/system/
├── sing-box.service
└── sb-accountd.service
```

基本原则：

```text
/etc
    配置和身份状态

/var/lib
    可变业务数据

/usr/local
    项目自身程序
```

---

# 9. 供应链模型

项目必须避免：

```text
脚本 A
→ 下载脚本 B
→ 下载脚本 C
→ 下载 binary D
→ 执行 latest
```

目标供应链应缩减为：

```text
sb-mini GitHub Release
        │
        └── sb.sh

SagerNet sing-box official release
        │
        └── pinned sing-box binary
```

## 9.1 固定版本

禁止：

```bash
VERSION=$(curl .../latest)
```

而采用：

```bash
SB_VERSION="x.y.z"
```

并在 release 时显式升级。

## 9.2 Hash pinning

针对：

```text
linux-amd64
linux-arm64
```

保存对应 SHA-256。

流程：

```text
download
   ↓
SHA-256
   ↓
compare
 ┌─┴─┐
FAIL PASS
 │    │
abort install
```

## 9.3 不关闭 TLS certificate verification

禁止：

```text
wget --no-check-certificate
curl -k
```

## 9.4 不自动更新

V0.1 和 V0.2.x 均不设计后台自动升级机制。

升级必须是显式行为。

---

# 10. 配置生成原则

配置采用固定模板，而不是通用 JSON builder。

生成流程：

```text
inputs
   ↓
fixed Reality template
   ↓
config.json.new
   ↓
sing-box check
   ↓
PASS?
 ┌─┴─┐
NO  YES
│    │
abort backup old config
         ↓
     atomic replace
         ↓
       restart
```

任何配置修改必须遵循事务式部署。

---

# 11. 身份模型

这是 V0.2.x 最重要的设计。

必须严格区分：

```text
Identity
≠
Credential
```

即：

```text
tag / user_id
≠
UUID
```

## 11.1 Stable identity

每名内部用户拥有长期稳定身份：

```text
user_id
tag
display_name
department
```

例如：

```text
tag: alice
display_name: Alice Zhang
department: Sales
```

`tag` 用于 sing-box 的认证用户名称，也用于操作和审计展示。

## 11.2 Credential

UUID 仅是认证 credential。

一个用户可以拥有：

```text
Alice
├── VPS-TYO → UUID-A
├── VPS-LAX → UUID-B
└── VPS-FRA → UUID-C
```

禁止为了方便而跨 VPS 共用 UUID。

优势：

- credential 泄露影响范围有限；
- 单节点可独立 revoke；
- UUID 可轮换；
- 历史统计连续；
- 用户身份不随 credential 更换而变化。

---

# 12. UUID 轮换

必须支持：

```bash
sb user rotate alice
```

语义：

```text
Alice
UUID-A
   ↓ revoke
UUID-B
   ↓ activate
```

数据库历史：

```text
Alice
├── UUID-A: 2026-01 → 2026-08
└── UUID-B: 2026-08 →
```

历史 accounting 仍然全部关联：

```text
user_id = Alice
```

而不是 UUID。

---

# 13. 用户管理 CLI

V0.2.0 规划：

```bash
sb user add alice
sb user remove alice
sb user rotate alice
sb user list
sb user show alice
sb user link alice
sb user disable alice
sb user enable alice
```

可以支持可选元数据：

```bash
sb user add alice \
  --department sales \
  --display-name "Alice Zhang"
```

默认首次安装：

```text
owner
```

作为初始用户。

---

# 14. Registry 是身份 Source of Truth

不能把：

```text
/etc/sing-box/config.json
```

当数据库使用。

应维护：

```text
sb-mini registry
        ↓
generate
        ↓
sing-box config
```

关系：

```text
Registry
│
├── user
├── department
├── credential
└── node
        │
        ▼
Config generator
        │
        ▼
sing-box config.json
```

增加：

```bash
sb verify
```

验证：

```text
registry tag/UUID
==
sing-box config tag/UUID
```

如果出现漂移：

```text
FAILED
alice:
registry UUID = A
config UUID   = B
```

不静默修复。

---

# 15. 审计目标

V0.2.x 的核心统计维度定义为：

```text
User
×
Node
×
Time
×
Destination
×
Traffic
```

其中最重要的可查询记录为：

```text
alice
2026-08-12
tyo-01
googlevideo.com
upload = 83 MB
download = 8.4 GB
```

---

# 16. 不进行 HTTPS MITM

系统明确不做：

- TLS certificate substitution；
- HTTPS 解密；
- HTTP body inspection；
- URL path 记录；
- Password/form 内容记录；
- Chat/message 内容记录。

收集对象限定为连接元数据：

```text
authenticated user
source IP
destination domain/IP
destination port
protocol
start time
end time
upload bytes
download bytes
```

这是网络可观测性，而不是内容监控。

---

# 17. “网站统计”的准确语义

基础系统不使用：

```text
Website
```

作为数据主键。

而使用：

```text
destination_host
```

例如访问 YouTube 可能产生：

```text
youtube.com
googlevideo.com
ytimg.com
googleapis.com
gstatic.com
```

因此基础层只能准确声明：

```text
Alice → googlevideo.com → 8.4 GB
```

而不是直接：

```text
Alice → YouTube → 8.4 GB
```

以后可以增加：

```text
domain → service
```

归类层：

```text
youtube.com
googlevideo.com
ytimg.com
      ↓
YouTube
```

但这应属于独立 enrichment 模块，而非 accounting 基础模型。

---

# 18. Domain 获取

目标域名来源优先级：

```text
客户端直接提交 domain
        ↓
如果没有
        ↓
协议 sniff
        ↓
HTTP Host
TLS SNI
QUIC metadata
        ↓
仍没有
        ↓
IP only
```

必须允许：

```text
destination_host = NULL
```

不能为了生成漂亮报告而根据 reverse DNS 强行猜测真实网站。

统计报告应能够显示：

```text
Domain identified traffic
IP-only traffic
```

便于了解数据质量。

---

# 19. Accounting 数据模型

建议 SQLite 至少包含以下实体。

## users

```text
user_id
tag
display_name
department
created_at
disabled_at
```

## nodes

```text
node_id
hostname
region
created_at
```

## credentials

```text
credential_id
user_id
node_id
uuid
created_at
revoked_at
```

## connections

```text
connection_id
node_id
user_id
credential_id

started_at
closed_at

source_ip

destination_host
destination_ip
destination_port

network
protocol

upload_bytes
download_bytes
```

## daily_usage

```text
date
node_id
user_id
destination_host

upload_bytes
download_bytes
connection_count
```

必要索引：

```text
(date)
(user_id, date)
(destination_host, date)
(node_id, date)
(user_id, destination_host, date)
```

---

# 20. 为什么使用 SQLite

当前规模是：

```text
几台 VPS
+
几十以内内部用户
+
单机 collector
```

SQLite 足以承担。

优点：

- 无额外服务；
- Debian/Ubuntu 原生支持；
- 单文件；
- 易于备份；
- 易于导出；
- 支持复杂 GROUP BY；
- 易于后续聚合；
- 不开放网络端口；
- 运维成本接近零。

暂不引入：

```text
PostgreSQL
InfluxDB
Prometheus
ClickHouse
ElasticSearch
```

除非以后规模发生数量级变化。

---

# 21. Accounting Collector

从 V0.2.1 开始引入：

```text
sb-accountd
```

建议使用 Python 标准库实现。

依赖尽量限制在：

```text
sqlite3
json
urllib/http
datetime
socket
logging
```

避免：

```text
pip install
virtualenv
FastAPI
SQLAlchemy
requests
```

如果系统 Python 即可满足，就不增加独立 Python runtime。

---

# 22. Accounting Event Schema

数据库不应直接依赖某个 sing-box API。

首先定义自己的统一事件：

```json
{
  "event": "connection_closed",
  "connection_id": "...",
  "node_id": "tyo-01",
  "user": "alice",
  "destination_host": "googlevideo.com",
  "destination_ip": "203.0.113.10",
  "destination_port": 443,
  "network": "tcp",
  "upload_bytes": 102400,
  "download_bytes": 20841022,
  "started_at": "...",
  "closed_at": "..."
}
```

采集层只负责：

```text
sing-box runtime representation
        ↓
Accounting Event
```

后续数据库和报表完全使用自己的 schema。

这样可以更换 backend：

```text
Clash API
→ future sing-box API
→ telemetry patch
```

而不需要重写数据库。

---

# 23. V0.2.1 初始采集方案

第一阶段仍使用官方 sing-box binary。

利用：

```text
localhost Clash API
```

并且强制：

```text
127.0.0.1
```

监听。

禁止：

```text
0.0.0.0
```

VPS 防火墙不需要开放任何 management/accounting port。

---

# 24. auth_user 与 accounting outbound

为解决 stock Clash API 不直接暴露认证用户名的问题，可以利用 sing-box 的认证用户路由。

生成：

```text
auth_user = alice
        ↓
outbound = acct/alice
```

例如：

```text
alice → acct/alice
bob   → acct/bob
```

这些 outbound 网络行为相同，tag 仅用于 accounting 标识。

于是 Clash connection metadata 中出现：

```text
acct/alice
```

即可映射回：

```text
user_id = alice
```

这允许 V0.2.x 在不修改官方 sing-box binary 的前提下实现：

```text
User × Destination × Bytes
```

---

# 25. Polling 模式的限制

通过轮询当前连接：

```text
T0:
connection A = 100 MB

T1:
connection A = 112 MB
```

可记录：

```text
delta = 12 MB
```

但如果：

```text
T0
无连接

T0+1
建立连接
下载 2 MB
关闭

T1
无连接
```

则该短连接可能完全没有被 collector 观察到。

因此必须明确：

> **V0.2.1 属于近似 accounting，而不是严格计费系统。**

不能宣称 byte-perfect。

---

# 26. V0.2.2 报表与聚合

V0.2.2 开始提供正式查询接口。

基础：

```bash
sb stats today
```

输出：

```text
User             Upload      Download      Total
alice             1.2 GB       18.4 GB     19.6 GB
bob             842 MB          7.3 GB      8.1 GB
```

单用户：

```bash
sb stats user alice --today
```

Top destination：

```bash
sb stats user alice --today --top 20
```

可能输出：

```text
Destination                    Download
googlevideo.com                  8.42 GB
youtube.com                      2.11 GB
github.com                       1.37 GB
githubusercontent.com          924.4 MB
```

---

# 27. 查询维度

目标支持：

```text
时间
├── today
├── yesterday
├── day
├── days N
├── week
└── month

主体
├── user
├── department
├── node
└── all

目标
├── domain
├── IP
└── destination port
```

示例：

```bash
sb stats department sales --days 30

sb stats node tyo-01 --month

sb stats user alice --days 7

sb stats domain github.com --days 30
```

---

# 28. Raw data 与聚合数据

建议使用两层：

```text
connections
        ↓
periodic rollup
        ↓
daily_usage
```

近期调查使用：

```text
connections
```

长期统计使用：

```text
daily_usage
```

例如：

```text
raw connection retention:
30–90 days

daily aggregate:
长期保留
```

具体周期做成配置。

---

# 29. V0.2.3 Reliable Accounting

V0.2.3 的主要目标不是增加 UI，而是：

> 解决短连接和连接结束事件丢失。

优先级：

### 方案 A

如果届时 sing-box stable API 能够可靠提供：

```text
connection opened
connection updated
connection closed
authenticated user
destination
bytes
```

直接切换正式 API。

### 方案 B

如果官方 API 仍不能满足需求，开发极小 telemetry patch。

patch 只负责在连接关闭时输出：

```text
user
destination
bytes
timestamps
```

而不修改：

- 协议行为；
- 路由逻辑；
- TLS；
- REALITY；
- VLESS；
- 网络栈。

目标是保持 fork delta 极小。

---

# 30. 多 VPS 架构

V0.2.x 仍然不设置公网控制面。

每台 VPS：

```text
VPS-TYO
├── sing-box
├── sb-accountd
└── accounting.db

VPS-LAX
├── sing-box
├── sb-accountd
└── accounting.db
```

所有 accounting API：

```text
localhost only
```

不开放：

```text
9090
8080
3000
```

到公网。

---

# 31. 后续 Fleet 聚合方向

管理机器主动通过 SSH pull：

```text
Admin PC
   │
   ├── SSH → VPS-TYO
   ├── SSH → VPS-LAX
   └── SSH → VPS-FRA
```

未来可以实现：

```bash
sb fleet sync
```

逻辑：

```text
remote accounting.db
        ↓
incremental export
        ↓
SSH
        ↓
local fleet.db
```

由管理 PC 统一查询：

```text
所有 VPS
×
所有用户
×
所有部门
```

VPS 仍然不需要暴露新的网络服务。

该功能建议不进入 V0.2.x 核心验收，可作为后续 V0.3+ 扩展。

---

# 32. CLI 总体规划

到 V0.2.x 时建议控制在以下范围。

## 节点

```bash
sb info
sb status
sb restart
sb logs
sb check
sb verify
```

## 链接

```bash
sb link
sb qr
```

## 用户

```bash
sb user add
sb user remove
sb user disable
sb user enable
sb user rotate
sb user list
sb user show
sb user link
```

## Audit / Stats

```bash
sb connections
sb audit
sb stats
```

## 生命周期

```bash
sb uninstall
```

暂不提供复杂菜单式 UI。

---

# 33. 安全边界

## 管理接口

全部：

```text
127.0.0.1
```

除 Reality 服务端口外，不产生新的公网监听。

## 文件权限

至少：

```text
/etc/sb-mini/
root:root

credentials/config
0600 或 0640

accounting.db
0600/0640
```

## UUID

使用高质量随机生成。

## Reality private key

只允许 root/sing-box service account 读取。

## 临时文件

使用：

```bash
mktemp -d
```

而不是：

```bash
mktemp -u
```

并通过 trap 自动清理。

---

# 34. 隐私与内部治理

由于本项目用于公司内部用户，虽然不进行 MITM，仍然会记录：

```text
用户名
时间
来源 IP
目标域名/IP
流量
```

这些数据本质上属于网络活动日志。

因此部署前应明确：

- 公司内部授权；
- 员工知情；
- 数据用途；
- 数据访问权限；
- retention period；
- 是否允许导出；
- 谁能够查询具体个人记录。

技术设计默认：

> 收集满足运维与安全审计所需的最少元数据，不主动扩大到内容级监控。

---

# 35. V0.1 里程碑

目标：

> 将新 VPS 变成可靠 Reality 节点。

范围：

```text
Debian/Ubuntu
amd64/arm64
official pinned sing-box
SHA-256 verification
VLESS + Reality + Vision
systemd
owner user
config transaction
link output
basic sb helper
```

验收：

```text
bash sb.sh
```

在干净 VPS 上能够：

1. 自动识别环境；
2. 下载固定版本；
3. 校验 SHA-256；
4. 生成合法配置；
5. `sing-box check` PASS；
6. systemd 启动成功；
7. 监听预期端口；
8. 输出可用 VLESS URI；
9. 客户端成功连接；
10. 重新执行不会破坏已有安装。

---

# 36. V0.2.0 — Identity

主题：

> 从“一个节点链接”升级到“有身份的用户系统”。

实现：

```text
stable user ID
tag
department
per-node UUID
credential rotation
registry
config generation
sb verify
```

验收：

```text
Alice
Bob
Charlie
```

能够拥有独立 UUID，且：

```text
tag ↔ user_id ↔ credential
```

关系稳定。

---

# 37. V0.2.1 — Local Accounting

主题：

> 开始采集 User × Destination × Traffic。

实现：

```text
local Clash API
acct/<user> routing
sb-accountd
SQLite
connection ingestion
basic traffic delta
```

验收至少能够查询：

```text
当前连接
用户
destination
upload/download
```

并能够保存到重启后的 SQLite。

同时文档必须明确：

```text
polling accounting ≠ exact billing
```

---

# 38. V0.2.2 — Analytics

主题：

> 从原始连接数据变成可使用的管理信息。

实现：

```text
daily rollup
date filters
user filters
department filters
node filters
domain filters
Top N
CSV/JSON export（可选）
retention
```

核心问题必须能够直接回答：

```text
某个人今天用了多少？
某部门一个月用了多少？
哪个域名占据最多流量？
Alice 今天访问了哪些域名？
某台 VPS 今天承载多少？
```

---

# 39. V0.2.3 — Reliable Accounting

主题：

> 提升 accounting 完整性。

任务：

1. 重新评估届时稳定版 sing-box API；
2. 优先使用正式 lifecycle event；
3. 如果不足，则开发最小 telemetry patch；
4. 获取完整 closed connection counter；
5. 减少短连接漏记；
6. 建立 crash/restart consistency tests。

该阶段仍然不以：

```text
billing-grade
```

作为目标。

---

# 40. V0.2.x 明确不做

为控制 scope：

```text
❌ 公网 Web Dashboard
❌ 用户自行登录
❌ 机场订阅
❌ 月度流量套餐
❌ 自动限速
❌ 欠费停机
❌ HTTPS MITM
❌ 内容审查
❌ DPI
❌ PostgreSQL
❌ Prometheus/Grafana
❌ Docker control plane
❌ 多协议同时监听
❌ 自动追 latest
```

这些功能只有在出现明确实际需求时才重新评估。

---

# 41. 测试策略

整个项目应尽量采用自动化测试，而不是依赖“我在某台 VPS 上试过”。

## Generator tests

给定：

```text
tag
UUID
Reality keys
port
SNI
```

输出必须稳定。

## sing-box integration

CI 对所有模板运行：

```bash
sing-box check
```

## Identity tests

测试：

```text
add
remove
rotate
disable
enable
```

后 registry/config 一致。

## Migration tests

测试：

```text
old registry
→ new version
```

不会造成 UUID/user association 丢失。

## Accounting tests

构造事件：

```text
Alice → github.com → 100 MB
Bob → github.com → 20 MB
Alice → youtube.com → 1 GB
```

验证：

```text
user
domain
date
department
```

聚合结果正确。

---

# 42. CI / Release

建议 release pipeline：

```text
commit
   ↓
ShellCheck
   ↓
unit tests
   ↓
generate configs
   ↓
sing-box check
   ↓
integration test
   ↓
package sb.sh
   ↓
SHA-256
   ↓
GitHub Release
```

sing-box version bump 必须通过独立 PR。

例如：

```text
Update sing-box
1.13.x → 1.13.y
```

必须重新执行全部 config integration tests。

---

# 43. 风险清单

## R1：sing-box 配置 schema 演进

缓解：

```text
version pin
integration test
explicit upgrade
```

## R2：UUID 与用户身份漂移

缓解：

```text
registry source of truth
sb verify
no manual production config
```

## R3：短连接漏记

缓解：

```text
V0.2.1 明示限制
V0.2.3 lifecycle events
```

## R4：domain 无法识别

缓解：

```text
allow IP-only
record data quality
never guess
```

## R5：数据库无限增长

缓解：

```text
retention
daily rollup
raw data pruning
```

## R6：管理接口误暴露

缓解：

```text
localhost-only hard default
startup verification
```

## R7：项目逐渐膨胀成机场面板

缓解：

任何新增功能必须回答：

> 它是否直接服务于内部 VPS 部署、身份管理或流量审计？

如果不能，默认拒绝进入核心。

---

# 44. 最终版本路线

```text
V0.1
│
│  Deploy
│  VLESS + REALITY + Vision
│  pinned binary
│  SHA256
│  transactional config
│
▼
V0.2.0
│
│  Identity
│  tag / user_id
│  per-node UUID
│  rotate
│  registry
│
▼
V0.2.1
│
│  Local Accounting
│  sb-accountd
│  SQLite
│  User × Destination × Bytes
│
▼
V0.2.2
│
│  Analytics
│  daily aggregation
│  filters
│  Top N
│  reports
│
▼
V0.2.3
   Reliable Accounting
   connection lifecycle
   short-connection coverage
   stable API / minimal telemetry patch
```

协议扩展：

```text
Hysteria2
TUIC
```

不进入 V0.2.x 主线，待 accounting 主路径稳定后再重新规划。

---

# 45. 项目成功标准

如果 V0.2.x 完成，项目应达到以下体验。

管理员购买一台新 VPS：

```bash
bash sb.sh
```

得到：

```text
VLESS + REALITY + Vision
```

然后：

```bash
sb user add alice --department sales
```

得到 Alice 的独立链接。

再：

```bash
sb user add bob --department engineering
```

得到 Bob 的独立链接。

一段时间后：

```bash
sb stats today
```

看到：

```text
Alice       19.6 GB
Bob          8.1 GB
Owner       12.4 GB
```

进一步：

```bash
sb stats user alice --today --top 20
```

看到：

```text
googlevideo.com       8.42 GB
youtube.com           2.11 GB
github.com             1.37 GB
...
```

同时管理员能够确认：

```text
Alice
→ stable identity
→ 当前 VPS credential
→ UUID
→ historical traffic
```

关系始终一致。

整个系统只需要：

```text
sing-box
sb
sb-accountd
SQLite
systemd
```

除代理端口本身以外，没有新的公网服务。

这就是 sb-mini 在 V0.2.x 阶段应达到的目标：**仍然保持“一键部署”的轻量体验，同时具备足够可靠的用户身份、连接审计和内部流量统计能力。**