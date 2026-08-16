# vincula V0.2.8-dev

面向自有 Debian/Ubuntu VPS 的最小化 **sing-box** 部署与内部流量审计。

```text
协议固定：VLESS + REALITY + xtls-rprx-vision + TCP
sing-box 固定：1.13.18（不追 latest）
```

一次安装得到可导入的 VLESS URI；用 `vcl user` 管理用户；用 `vcl stats` / `vcl audit` 查看近似流量（**approximate / Clash polling**，非计费级）。

| 项目 | 值 |
| --- | --- |
| OS | Debian 12/13；Ubuntu 22.04/24.04/26.04 |
| Arch | amd64、arm64 |
| Init | systemd |
| 默认端口 | TCP 443 |
| 默认 REALITY SNI | `www.cloudflare.com` |
| Clash API | 仅 `127.0.0.1`（默认 9090 + secret） |
| 用户 registry | `users.json` schema 2 |
| Accounting | schema 3；raw 90 天 / daily 90 天 |

Gate / 已知限制：[`docs/release-readiness-0.2.7.md`](docs/release-readiness-0.2.7.md) · [`docs/known-issues-0.2.7.md`](docs/known-issues-0.2.7.md)

---

## 仓库结构

```text
vincula.sh                 # 安装 / 迁移入口
vincula-bootstrap.sh       # 从 URL 拉 tarball 安装
bin/vincula                # 节点运行时 CLI（安装为 vcl / vincula；无 fleet 子命令）
bin/vcl-fleet              # 工作站控制器（Unix）
bin/vcl-fleet.cmd          # 工作站控制器（Windows 11）
lib/                       # common / accountd / stats / audit / fleet / unit
lib/vincula-fleet.py       # 控制器实现（stdlib + 系统 OpenSSH）
scripts/
  build-release.sh         # 节点产物 dist/vincula-node-<ver>.tar.gz
  build-controller.sh      # 控制器产物 dist/vincula-controller-<ver>.zip
  gen-release-lock.sh      # 刷新节点 release.lock（8 个 first-party 文件）
  soak-0.2.7.sh            # LIVE-ONLY 24h soak 协议（不在 CI 跑）
  rc-*.sh                  # 远端 RC / 升级链测试
  freeze-*.sh              # 0.2.4 freeze 辅助（历史）
tests/test.sh              # 本地单元测试（source tests/test-fleet.sh）
docs/identity.md           # 身份合同
docs/fleet.md              # 控制器运维指南
dist/                      # 生成物（gitignore，勿手改）
```

源码以 **仓库根目录** 为准。节点部署只用 `scripts/build-release.sh` 生成的 `dist/vincula-node-<version>.tar.gz`；工作站控制器用 `scripts/build-controller.sh` 生成的 `dist/vincula-controller-<version>.zip`。不要手改 `dist/` 或旧 `release/`。

---

## 安装

### 1. 打发布包（开发机）

```bash
bash scripts/gen-release-lock.sh
bash scripts/build-release.sh
# → dist/vincula-node-0.2.8-dev/  与  dist/vincula-node-0.2.8-dev.tar.gz (+ .sha256)
bash scripts/build-controller.sh
# → dist/vincula-controller-0.2.8-dev/  与  dist/vincula-controller-0.2.8-dev.zip
```

### 2. 拷到 VPS 后安装

目录内至少包含：

```text
vincula.sh  vincula.sh.sha256  release.lock
bin/vincula
lib/vincula-common.sh
lib/vincula-accountd.py
lib/vincula-stats.py
lib/vincula-audit.py
lib/vincula-accountd.service
```

```bash
sha256sum -c vincula.sh.sha256
sudo bash vincula.sh
```

### 3. 可选：bootstrap 拉 tarball

```bash
sudo env RELEASE_URL='https://example.com/vincula-node-0.2.8-dev.tar.gz' \
  RELEASE_SHA256='...' \
  bash vincula-bootstrap.sh
```

**不支持** `curl | bash` 单文件安装（必须同目录有 `bin/` + `lib/`）。

工作站控制器是另一个产物（zip，无 installer / 无 `release.lock`）。解压后在 Windows 11 上跑 `bin\vcl-fleet.cmd`，在 Linux 上跑 `python3 bin/vcl-fleet`。需要本机 **Python 3.10+** 与 **系统 OpenSSH**。运维步骤、host-key 与 AC-2.8 见 [`docs/fleet.md`](docs/fleet.md)。

### 环境变量

```bash
sudo env \
  VCL_SERVER=203.0.113.10 \
  VCL_PORT=443 \
  VCL_REALITY_HOST=www.cloudflare.com \
  bash vincula.sh
```

| 变量 | 说明 |
| --- | --- |
| `VCL_SERVER` | 写入客户端 URI 的公网 IPv4 / 无括号 IPv6 / DNS；缺省尝试 `api.ipify.org` |
| `VCL_PORT` | 1–65535，默认 `443` |
| `VCL_REALITY_HOST` | REALITY server name + 客户端 SNI；默认 `www.cloudflare.com` |

成功时应同时看到：

```text
✓ sing-box.service active
✓ vincula-accountd.service active
```

任一方失败会回滚 / 退出，不会“装上但无 accounting”。

---

## 日常管理（`vcl` ≡ `vincula`）

### 节点

```bash
vcl info | status | check | verify | diagnose
vcl restart
vcl logs | vcl logs 200 | vcl logs -f
vcl link          # owner VLESS URI
vcl version
```

### 用户（0.2.5+）

```bash
vcl user add alice --display-name "Alice" --department Sales
vcl user set alice --display-name "Alice Chen" --department Eng
vcl user list
vcl user show alice
vcl user link alice
vcl user disable alice
vcl user enable alice
vcl user rotate alice

vcl user import staff.csv --dry-run
vcl user import staff.csv --output credentials.csv   # 0600，含 URI
vcl user export --output users.csv
vcl user export --credentials --output credentials.csv
vcl user verify
```

导入 CSV 最少一列 `tag`，可选 `display_name,department`。全量校验后一次提交，失败则零变更。  
`user remove` / purge / delete **不支持**（请用 `disable`）。

仅会影响代理配置的用户变更才会 **restart sing-box**（连接可能短暂中断）；仅改 metadata 的 `user set` 不重启。

### 流量（0.2.6+，UTC，approximate）

```bash
vcl accounting status
vcl accounting check
vcl accounting retention
vcl accounting cycle            # 账期起始日，默认 1
vcl accounting cycle --set 5
vcl connections                 # 需 accountd active，否则 UNAVAILABLE

vcl stats today
vcl stats yesterday
vcl stats --days 7
vcl stats --month
vcl stats --date 2026-08-14
vcl stats --from 2026-08-01 --to 2026-08-15
vcl stats user alice --days 7
vcl stats user alice --date 2026-08-14
vcl stats department Eng --month
vcl stats host github.com --days 7
vcl stats top users --days 7 --limit 20
vcl stats top departments --month
vcl stats top hosts --days 7
vcl stats today --json
vcl stats today --csv /tmp/today.csv

vcl audit user alice --from 2026-08-10T09:00:00Z --to 2026-08-10T18:00:00Z
vcl audit user alice --from 2026-08-10T09:00:00Z --to 2026-08-10T18:00:00Z --json
```

`--month` 从 `billing_cycle_start_day` 起算（默认 1；用 `vcl accounting cycle` 查看/设置）。  
部门按 **当前** `users.json` 归属（无历史部门维）。  
`vcl audit` 是连接级 RFC3339 interval-overlap（不是 stats 的 UTC 日粒度）；无 `--csv`。  
详见 [`docs/accounting-reliability.md`](docs/accounting-reliability.md)。

### 卸载

```bash
vcl uninstall --yes
```

会删除 Vincula 拥有的资源（含 `accounting.db`）；历史流量数据不可恢复。无 `--force`。

---

## 身份

现有 UUID `node_id`（`state.json` `node.node_id` / `config.toml` `node_id` / `users.json` credentials / accounting）**就是逻辑节点 ID**，永久冻结。`name` 可改；改 IP / hostname **不**改 `node_id`。**禁止重铸**，也不引入第二套逻辑 ID。

`instance_id` 表示一次物理安装。单一事实来源（SoT）是 `state.json` 的 `node.instance_id`。升级 `0.2.7` → `0.2.8` 才为当前安装 mint；**禁止**把 `node_id` 复制进 `instance_id`。

详见 [`docs/identity.md`](docs/identity.md)。

---

## Fleet Foundation（工作站控制器）

0.2.8 提供 **vcl-fleet**（SPEC 里的 `vcl fleet <sub>` ≡ `vcl-fleet <sub>`）。跑在管理员工作站上：无 root、无 systemd、无公网管理端口；用系统 OpenSSH 对节点做只读 `vcl identity|status|verify --json`。

节点 `vcl` **没有** `fleet` 子命令。完整 CLI、Windows 11 用法、`--host-key`、status/verify 含义：[`docs/fleet.md`](docs/fleet.md)。

```bash
python3 bin/vcl-fleet version
python3 bin/vcl-fleet init
python3 bin/vcl-fleet node add lax --host 203.0.113.10 --host-key SHA256:...
python3 bin/vcl-fleet status
python3 bin/vcl-fleet verify
```

---

## 升级

同机重跑安装器：

- 同版本：校验双平面，不轮换凭据
- `0.1.0`–`0.1.5` 或 `0.2.0`–`0.2.6` → **0.2.7**：保留 Reality / UUID / `user_id` / accounting DB
- `0.2.6` → `0.2.7`（accounting schema 2→3，不可逆）
- `0.2.7` → **0.2.8-dev**：保留 `node_id`，mint `instance_id`；accounting schema 仍为 3

不支持降级或跳未知版本。Fresh install 若已有 `/var/lib/vincula` 会拒绝（先卸载）。

远端升级链实测（Debian 13，止于 0.2.6）：[`docs/rc-live-upgrade-0.2.4-0.2.6.md`](docs/rc-live-upgrade-0.2.4-0.2.6.md) · 证据 [`docs/evidence/0.2.4-0.2.6-live/SUMMARY.md`](docs/evidence/0.2.4-0.2.6-live/SUMMARY.md)

```bash
# 编排机示例
export VCL_RC_HOST=x.x.x.x VCL_RC_USER=root VCL_RC_PASS='...' VCL_SERVER=$VCL_RC_HOST
bash scripts/rc-live-upgrade-driver.sh
```

---

## 开发与本地测试

```bash
bash -n vincula.sh bin/vincula lib/vincula-common.sh
python3 -m py_compile lib/vincula-accountd.py lib/vincula-stats.py lib/vincula-audit.py lib/vincula-fleet.py
bash tests/test.sh
bash scripts/gen-release-lock.sh   # 改过节点 first-party 后必跑
bash scripts/build-release.sh      # vincula-node-<ver>.tar.gz
bash scripts/build-controller.sh   # vincula-controller-<ver>.zip
# 可选（需下载 pinned sing-box）：
VCL_INTEGRATION=1 bash tests/test.sh
```

Source of Truth：`state.json`（节点/REALITY）+ `users.json`（credential UUID）+ `config.toml`（设置）。由此生成 `config.json` / `owner.uri`。

---

## 明确不做

Hysteria2/TUIC、公网 Web UI、订阅计费、HTTPS MITM、自动追 latest、完整 fleet 用户开通 / incremental sync / UI（0.2.9+；0.2.8 仅 Fleet Foundation）、Reliable/Billing-grade accounting、单文件 `curl|bash`、`vcl recover`、用户 purge/delete、tag rename。
全新安装若发现残留路径会拒绝，并在报错中打印确切的 `rm -f` / `rmdir` 清理命令；仍然没有 `vcl recover`。
