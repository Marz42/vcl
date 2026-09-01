# Vincula 用户手册（Controller 0.5.0 · Node 0.5.0）

面向能使用终端、但不需要阅读源码的 VPS 管理者。
架构与合同细节见 [`technical-guide.md`](technical-guide.md)。完整参数以 CLI `--help` 为准。

**记账始终是 approximate（Clash 轮询），不能当发票。**

---

## 1. 安装 Controller

工作站产物：`vincula-controller-<version>.zip`（无 installer、无节点 `release.lock`）。

依赖：**Python 3.10+**、**系统 OpenSSH**（Windows：可选功能「OpenSSH 客户端」）。

1. 校验 sidecar：`sha256sum -c vincula-controller-<ver>.zip.sha256`
2. 解压；再 `sha256sum -c controller.lock`（在解压目录内）
3. 验证：

**Windows 11**

```bat
py -3 bin\vcl-fleet.cmd version
bin\vcl-fleet.cmd help
```

**Linux / macOS**

```bash
python3 bin/vcl-fleet version
python3 bin/vcl-fleet help
```

zip 内摘要见仓库根目录 [`README-controller.md`](../README-controller.md)。

从源码构建发布包仅供维护者：`bash scripts/build-controller.sh`（见技术手册）。

---

## 2. 初始化 Fleet 目录

| 环境变量 / 参数 | 作用 |
| --- | --- |
| `VCL_FLEET_HOME` 或 `--workspace PATH` | 可移植 workspace 根 |
| 缺省（Windows） | `%APPDATA%\vincula\` |
| 缺省（Unix） | `${XDG_CONFIG_HOME:-~/.config}/vincula/` |

```bash
# Linux 示例
export VCL_FLEET_HOME="$HOME/.config/vincula"
python3 bin/vcl-fleet init
# 或（0.4.1+ workspace）
python3 bin/vcl-fleet workspace init
python3 bin/vcl-fleet access bind admin --identity-file ~/.ssh/id_ed25519
```

```bat
REM Windows
bin\vcl-fleet.cmd init
bin\vcl-fleet.cmd workspace init
bin\vcl-fleet.cmd access bind admin --identity-file %USERPROFILE%\.ssh\id_ed25519
```

Workspace 根只放可拷贝的 `workspace.json` / `fleet.json` / `trust/` / `history/`。
私钥绑定在机器本地 CONFIG，不要把私钥拷进可移动的 workspace。

---

## 3. SSH 密钥与 host-key 指纹

1. 工作站对 VPS 使用 **密钥登录**（通常 `root`），先确认 `ssh user@host` 可用。
2. 首次 `adopt` / `provision` / `replace` **必须**提供 `--host-key SHA256:…`。
3. 获取指纹（在工作站）：

```bash
ssh-keyscan -t ed25519,rsa HOST 2>/dev/null | ssh-keygen -lf -
```

输出形如 `SHA256:…` 的一行用于 `--host-key`。

**高风险提示：** 错误的 host-key 会导致信任错误主机。核对来自控制台/云厂商的指纹。

---

## 4. Fresh VPS：`node provision`

在**空** VPS 上安装 Node 0.3.2、校验并写入 registry。

| 项 | 说明 |
| --- | --- |
| 前置 | Controller 已 init；SSH 与 host-key；VPS 为受支持 Debian/Ubuntu |
| 是否改远端 | **是**（安装 sing-box、写入 `/etc/vincula`、启服务） |
| 成功 | 节点出现在 `node list`；可 `probe` / `status` |
| 敏感输出 | 普通成功不含 URI；legacy 模式见 §14 |
| 验证 | `vcl-fleet node list` · `vcl-fleet probe` · `vcl-fleet sync --full` |

```bash
python3 bin/vcl-fleet node provision NAME \
  --host HOST \
  --host-key 'SHA256:…' \
  --server ADVERTISED_HOST
```

`--server` 为客户端看到的地址（域名或公网 IP）。更多旗标：`vcl-fleet node provision -h`。

---

## 5. 已装节点：`node adopt`

远端已有 Vincula，只需登记到 Fleet。

| 项 | 说明 |
| --- | --- |
| 前置 | 远端 `vcl identity --json` 可用 |
| 是否改远端 | **否**（只读 identity，写本地 registry） |
| 成功 | registry 有该节点 |
| 验证 | `vcl-fleet node show NAME` · `vcl-fleet probe` |

```bash
python3 bin/vcl-fleet node adopt NAME --host HOST --host-key 'SHA256:…'
```

`node add NAME --host …` 是 **adopt 的别名**。

---

## 6. 离线注册：`register` / `add --offline`

| 项 | 说明 |
| --- | --- |
| 用途 | 无 SSH 时先写入 `node_id` + host |
| 限制 | **不**验证远端；之后仍须 adopt / set / probe |
| 是否改远端 | **否** |

```bash
python3 bin/vcl-fleet node register NAME --node-id UUID --host HOST
# 或
python3 bin/vcl-fleet node add NAME --host HOST --offline --node-id UUID
```

---

## 7. Node、instance、user、credential（用户层）

| 概念 | 一句话 |
| --- | --- |
| **Node（`node_id`）** | 逻辑节点；换机后仍是「同一个」节点 |
| **Instance（`instance_id`）** | 某次物理安装；replace 会产生新 instance |
| **User（`user_id`）** | Fleet 里同一个人；多节点共用同一 `user_id` |
| **Credential** | 某节点上的一条 VLESS 凭据；rotate 只换该节点 |

改 IP 但机器未换：用 `node set`（rebind）。机器报废换新：用 `node replace`（见 §13）。

---

## 8. 用户：添加、查看、轮换、停用

命名：tag / 节点短名 `^[a-z0-9][a-z0-9._-]{0,31}$`（最长 32）。

### 添加

```bash
python3 bin/vcl-fleet user add alice --nodes lax,tokyo --display-name Alice
```

| 项 | 说明 |
| --- | --- |
| 是否改远端 | **是**（各节点 `vcl user add`） |
| 成功 | 全部节点 SUCCESS → exit 0 |
| 常见失败 | **PARTIAL exit 2**（部分节点失败）；无自动回滚 |
| 敏感 | 成功路径可能涉及 URI；优先用 `user link` 按需取链 |
| 验证 | `vcl-fleet user show alice` · `vcl-fleet sync --full` |

### 查看 / 链接

```bash
python3 bin/vcl-fleet user list
python3 bin/vcl-fleet user show alice
python3 bin/vcl-fleet user link alice --node lax
```

`link` **输出 VLESS URI（敏感）**。仅在安全终端使用；不要贴到公开日志。

### 启用 / 停用 / 轮换（必须 `--node`）

```bash
python3 bin/vcl-fleet user disable alice --node tokyo
python3 bin/vcl-fleet user enable alice --node tokyo
python3 bin/vcl-fleet user rotate alice --node tokyo
```

没有「全舰队一键 disable」。`rotate` 会使该节点旧 URI 失效并打印新 URI（敏感）。

仅改 metadata 的 `user set` 不重启 sing-box；credential 变更会重启。

### 节点本地（无 Fleet 时）

```bash
sudo vcl user list --json
sudo vcl user rotate alice --json
```

`list`/`show` 的 `--json` **不含** VLESS uuid；`add`/`rotate` 的 URI 含 uuid。

---

## 9. 获取单节点 VLESS 链接

推荐：

```bash
python3 bin/vcl-fleet user link TAG --node NAME
```

或在 VPS：`sudo vcl user show TAG`（人类输出）/ 对应 rotate/add 的 JSON。

**警告：** URI 即访问凭证，按密钥保管。

---

## 10. sync、probe、status、verify

| 命令 | SSH？ | 写 cache？ | 用途 |
| --- | --- | --- | --- |
| `status` | 否 | 否（读已有） | 快速看上次 sync/full 健康 |
| `probe` | 是 | 否 | 现场健康；不更新 status cache |
| `verify` | 是 | — | identity + 状态 + 时钟偏移 |
| `sync` | 是 | 审计增量 | 拉 closed audit |
| `sync --full` | 是 | 是 | identity + health + users + audit |

```bash
python3 bin/vcl-fleet sync --full
python3 bin/vcl-fleet status
python3 bin/vcl-fleet probe
python3 bin/vcl-fleet verify
```

时钟：相对 Controller UTC，偏移 **>30s** 警告，**>300s** 失败（见技术手册常量）。

游标异常：`CURSOR_EXPIRED` / `CURSOR_AHEAD` → 对该节点 `sync --reseed NAME`（会清该节点本地 audit 缓存后再拉）。

---

## 11. WebUI

```bash
python3 bin/vcl-fleet ui
# 默认 http://127.0.0.1:8765
```

| 项 | 说明 |
| --- | --- |
| 绑定 | **仅 loopback**；非 loopback 拒绝 |
| 页面 | Overview、Nodes、Users、Traffic、Operations、Audit 等 |
| Command Builder | 选操作 → Generate → Copy → **在终端执行**；UI 不执行变更 |
| Refresh users | 确认后 SSH 刷新；列表以 sync 快照为主 |

手测清单与证据：[`evidence/0.4.4/SUMMARY.md`](evidence/0.4.4/SUMMARY.md)。

---

## 12. 流量统计与审计（approximate）

```bash
python3 bin/vcl-fleet stats …
python3 bin/vcl-fleet audit user TAG --from RFC3339 --to RFC3339
```

节点侧：`sudo vcl stats` / `sudo vcl audit`。

数字来自 Clash 轮询与已 sync 的 `fleet.db`，**近似**。详见技术手册 §Accounting。

---

## 13. 备份、恢复与 replace

### 节点备份

```bash
sudo vcl backup create --json
sudo vcl backup verify FILE --json
```

含密钥的 DR 备份必须 age：`--include-secrets --age-recipient FILE`。

### 高风险：`node replace`

| 项 | 说明 |
| --- | --- |
| 前置 | NEW_HOST 已 `sudo bash vincula.sh --runtime-only`；**无** `/etc/vincula/VERSION`；旧节点可达；`--host-key` |
| 是否改远端 | **是**（旧机 backup、新机 restore、改 registry） |
| 成功 | 同 `node_id`，新 `instance_id`；需分发 reissue CSV 中的新 URI |
| 敏感 | reissue CSV 含 VLESS URI（0600） |
| 验证 | `vcl-fleet probe` · `vcl-fleet sync --full` · `node instances NAME` |

```bash
python3 bin/vcl-fleet node replace NAME \
  --host NEW_HOST \
  --host-key 'SHA256:…'
```

完整检查表（B14）：[`operations/node-replace-runbook.md`](operations/node-replace-runbook.md)。
合同与 `--reissue-output`：[`technical-guide.md`](technical-guide.md) §Backup。

**不要**对已完整安装的主机做 replace；**不要**使用不存在的 `--replace-node` 旗标。

同实例只改 IP：`vcl-fleet node set NAME --host NEW`（凭据不变）。

---

## 14. Legacy single-user seed（保留旧客户端链接）

在 **fresh provision** 时把旧单用户 VLESS + Reality 私钥导入为非 `owner` 用户（需 Node **0.3.2**）。

```bash
python3 bin/vcl-fleet node provision NAME \
  --host HOST \
  --host-key 'SHA256:…' \
  --server ADVERTISED_HOST \
  --legacy-vless-uri-file ./legacy-user.uri \
  --legacy-reality-private-key-file ./reality-private.key \
  --legacy-user-tag existing-user
```

| 项 | 说明 |
| --- | --- |
| 前置 | 三文件/参数齐全；URI 与私钥匹配；tag ≠ `owner`；文件权限非组/其他人可读 |
| 是否改远端 | **是**（完整安装 + 双用户） |
| 成功 | 人类输出含 Node 版本与 legacy tag；用 `user link` 取链 |
| 敏感 | URI/私钥文件；勿提交到 git |
| 失败 | 校验失败 → **零安装**；多行 URI 文件拒绝 |

取链：`vcl-fleet user link existing-user --node NAME`。

---

## 15. 节点升级与观测

### 观测（0.5.0+ Node）

在 **Node 0.5.0+** 上：

```bash
vcl capabilities --json
vcl telemetry snapshot --json
```

从 Controller（需 SSH；observe 与 admin 凭据可分离绑定）：

```bash
# 显式绑定 observer（Spec：不得隐式共用 admin；可与 admin 相同但必须显式）
vcl-fleet access bind observe-default --identity-file ~/.ssh/id_ed25519_observe
vcl-fleet node set NODE --observe-credential-ref observe-default
# 或：vcl-fleet node set NODE --observe-identity-file ~/.ssh/id_ed25519_observe
# 清除：vcl-fleet node set NODE --clear-observe-credential-ref

vcl-fleet capabilities NODE --json
vcl-fleet telemetry NODE --json
```

AUTH_FAILED / ERROR 时上述 observation 命令 **exit 1**。0.3.x 节点返回 **UNSUPPORTED**（非 ERROR）；probe/sync/user 管理仍可用。

### 固件升级（Controller 编排）

```bash
vcl-fleet node upgrade plan NODE
vcl-fleet node upgrade apply NODE --yes
```

支持 **0.3.1 / 0.3.2 → 0.5.0**；保留 `node_id`、URI、accounting。升级前建议 `vcl backup create`。

手动原地升级仍可用：解开 `vincula-node-*.tar.gz`，校验后 `sudo bash vincula.sh`。细节见 CHANGELOG 与 [`evidence/0.5.0/SUMMARY.md`](evidence/0.5.0/SUMMARY.md)。

---

## 16. 常见故障

| 现象 | 排查 |
| --- | --- |
| SSH / host-key 失败 | 核对指纹；workspace `trust/known_hosts` |
| `busy: another vincula operation` | 等锁（约 30s）或查并发 |
| PARTIAL exit 2 | 看每节点状态；对失败节点单独重试 |
| `CURSOR_EXPIRED` | `sync --reseed NAME` |
| accounting STALE | 查远端 accountd / 时钟；`probe` |
| UI 打不开 | 确认只绑 127.0.0.1；本机访问 |
| Users 页用户不全 | 先 `sync --full`，再视需要 Refresh users |
| provision 端口占用 | preflight 检查 URI/安装端口；换端口或释放占用 |

---

## 17. 卸载

在 **节点** 上（破坏性）：

```bash
sudo vcl uninstall
```

会移除 Vincula 管理的单元与文件（以命令提示为准）。Controller 侧对节点：`node retire`（最终 sync 后标记 retired，保留历史）或从运维流程中停止使用；retire **不是**远端卸载。

---

## 18. 安全注意事项

1. 保护 SSH 私钥与 `access bind` 绑定。
2. 任何打印 VLESS URI 的命令视为密钥泄露面。
3. UI 与 Clash API 仅本机；勿改绑公网。
4. secretless 备份可辅助换机；含密钥备份必须 age，并限制传播。
5. 文档与工单中使用占位符，勿粘贴真实 URI / UUID / 私钥。
6. 生产 bootstrap 须 pin `RELEASE_SHA256`（传输损坏检测不够，需来源固定）。

---

## 命令索引（入口）

| 角色 | 入口 |
| --- | --- |
| 工作站 | `vcl-fleet` / `vcl-fleet.cmd` → `… -h` |
| 节点 | `sudo vcl …` → `vcl help` |

下一步：[`technical-guide.md`](technical-guide.md) · [`README.md`](../README.md) · [`docs/README.md`](README.md)。
