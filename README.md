# vincula V0.2.6

面向自有 Debian/Ubuntu VPS 的最小化 **sing-box** 部署与内部流量审计。

```text
协议固定：VLESS + REALITY + xtls-rprx-vision + TCP
sing-box 固定：1.13.18（不追 latest）
```

一次安装得到可导入的 VLESS URI；用 `vcl user` 管理用户；用 `vcl stats` 查看近似流量（**approximate / Clash polling**，非计费级）。

| 项目 | 值 |
| --- | --- |
| OS | Debian 12/13；Ubuntu 22.04/24.04/26.04 |
| Arch | amd64、arm64 |
| Init | systemd |
| 默认端口 | TCP 443 |
| 默认 REALITY SNI | `www.cloudflare.com` |
| Clash API | 仅 `127.0.0.1`（默认 9090 + secret） |
| 用户 registry | `users.json` schema 2 |
| Accounting | SQLite schema 2；raw 90 天 / daily 730 天 |

Gate / 已知限制：[`docs/release-readiness-0.2.6.md`](docs/release-readiness-0.2.6.md) · [`docs/known-issues-0.2.6.md`](docs/known-issues-0.2.6.md)

---

## 仓库结构

```text
vincula.sh                 # 安装 / 迁移入口
vincula-bootstrap.sh       # 从 URL 拉 tarball 安装
bin/vincula                # 运行时 CLI（安装为 vcl / vincula）
lib/                       # common / accountd / stats / unit / event schema
scripts/
  build-release.sh         # 从源码打 dist/ 产物（唯一推荐打包方式）
  gen-release-lock.sh      # 刷新 release.lock
  rc-*.sh                  # 远端 RC / 升级链测试
  freeze-*.sh              # 0.2.4 freeze 辅助（历史）
tests/test.sh              # 本地单元测试
docs/                      # 手册、gate、证据索引
dist/                      # 生成物（gitignore，勿手改）
```

源码以 **仓库根目录** 为准。部署只用 `scripts/build-release.sh` 生成的 `dist/vincula-<version>/`，不要手改 `dist/` 或旧 `release/`。

---

## 安装

### 1. 打发布包（开发机）

```bash
bash scripts/gen-release-lock.sh
bash scripts/build-release.sh
# → dist/vincula-0.2.6/  与  dist/vincula-0.2.6.tar.gz (+ .sha256)
```

### 2. 拷到 VPS 后安装

目录内至少包含：

```text
vincula.sh  vincula.sh.sha256  release.lock
bin/vincula
lib/vincula-common.sh
lib/vincula-accountd.py
lib/vincula-stats.py
lib/vincula-accountd.service
lib/vincula-event.schema.json
```

```bash
sha256sum -c vincula.sh.sha256
sudo bash vincula.sh
```

### 3. 可选：bootstrap 拉 tarball

```bash
sudo env RELEASE_URL='https://example.com/vincula-0.2.6.tar.gz' \
  RELEASE_SHA256='...' \
  bash vincula-bootstrap.sh
```

**不支持** `curl | bash` 单文件安装（必须同目录有 `bin/` + `lib/`）。

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

用户变更会 **restart sing-box**（连接可能短暂中断）。

### 流量（0.2.6+，UTC，approximate）

```bash
vcl accounting status
vcl accounting retention
vcl connections                 # 需 accountd active，否则 UNAVAILABLE

vcl stats today
vcl stats yesterday
vcl stats --days 7
vcl stats --month
vcl stats user alice --days 7
vcl stats department Eng --month
vcl stats host github.com --days 7
vcl stats top users --days 7 --limit 20
vcl stats top departments --month
vcl stats top hosts --days 7
vcl stats today --json
vcl stats today --csv /tmp/today.csv
```

部门按 **当前** `users.json` 归属（无历史部门维）。详见 [`docs/accounting-reliability.md`](docs/accounting-reliability.md)。

### 卸载

```bash
vcl uninstall --yes
```

会删除 Vincula 拥有的资源（含 `accounting.db`）；历史流量数据不可恢复。无 `--force`。

---

## 升级

同机重跑安装器：

- 同版本：校验双平面，不轮换凭据
- `0.1.0`–`0.1.5` 或 `0.2.0`–`0.2.5` → **0.2.6**：保留 Reality / UUID / `user_id` / accounting DB

不支持降级或跳未知版本。Fresh install 若已有 `/var/lib/vincula` 会拒绝（先卸载）。

远端升级链实测（Debian 13）：[`docs/rc-live-upgrade-0.2.4-0.2.6.md`](docs/rc-live-upgrade-0.2.4-0.2.6.md) · 证据 [`docs/evidence/0.2.4-0.2.6-live/SUMMARY.md`](docs/evidence/0.2.4-0.2.6-live/SUMMARY.md)

```bash
# 编排机示例
export VCL_RC_HOST=x.x.x.x VCL_RC_USER=root VCL_RC_PASS='...' VCL_SERVER=$VCL_RC_HOST
bash scripts/rc-live-upgrade-driver.sh
```

---

## 开发与本地测试

```bash
bash -n vincula.sh bin/vincula lib/vincula-common.sh
python3 -m py_compile lib/vincula-accountd.py lib/vincula-stats.py
bash tests/test.sh
bash scripts/gen-release-lock.sh   # 改过 first-party 后必跑
bash scripts/build-release.sh
# 可选（需下载 pinned sing-box）：
VCL_INTEGRATION=1 bash tests/test.sh
```

Source of Truth：`state.json`（节点/REALITY）+ `users.json`（credential UUID）+ `config.toml`（设置）。由此生成 `config.json` / `owner.uri`。

---

## 明确不做

Hysteria2/TUIC、公网 Web UI、订阅计费、HTTPS MITM、自动追 latest、fleet、Reliable/Billing-grade accounting、单文件 `curl|bash`、`vcl recover`、用户 purge/delete、tag rename。
