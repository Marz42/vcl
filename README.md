# vincula V0.2.5

`vincula` 是面向自有 Debian/Ubuntu VPS 的最小化 sing-box bootstrap。V0.2 仍只部署一种固定协议：

```text
VLESS + REALITY + xtls-rprx-vision + TCP
```

目标工作流：在干净 VPS 上执行一次安装脚本，得到可导入客户端的 VLESS URI；再用 `vcl user` 管理内部用户身份与 credential（含批量导入）；用本机 accounting 观察 User × Destination × Traffic。脚本不安装面板、不申请证书、不修改防火墙，也不追踪 sing-box `latest`。

## 当前实现基线

| 项目 | V0.2.5 固定值 |
| --- | --- |
| vincula | 0.2.5 |
| sing-box | 1.13.18 stable |
| OS | Debian 12/13；Ubuntu 22.04/24.04/26.04 |
| Architecture | amd64、arm64 |
| Init | systemd |
| Default port | TCP 443 |
| Default REALITY host/SNI | `www.cloudflare.com` |
| users.json | schema_version 2（Identity registry；credential UUID 唯一 SoT） |
| node_id | 永久 UUID（禁止 `"local"`）；`node_name` 默认可变 hostname |
| Clash API | `127.0.0.1` only（默认 9090 + secret） |
| Accounting | `vincula-accountd` → SQLite schema 2（主键 `user_id`） |
| Retention | raw 90 天 / daily 730 天（**产品决策**） |
| Accounting 声明 | **approximate polling**；Reliable Accounting **未完成** |

sing-box 的官方下载 URL、文件大小和 SHA-256 同时记录在 [`sing-box.lock`](sing-box.lock) 与 `vincula.sh` 中。脚本不会查询或安装新版本。

**0.2.5 gate：** [`docs/release-readiness-0.2.5.md`](docs/release-readiness-0.2.5.md) / [`docs/known-issues-0.2.5.md`](docs/known-issues-0.2.5.md) — User Provisioning API 冻结候选。  
**0.2.4 freeze（基线）：** [`docs/freeze-0.2.4.md`](docs/freeze-0.2.4.md)。  
产物构建：`bash scripts/build-release.sh` → `dist/`（勿手改）。

## 推荐安装方式

```bash
# Canonical source is the repo root. Build deployable artifacts:
bash scripts/build-release.sh
# → dist/vincula-<version>/  and  dist/vincula-<version>.tar.gz (+ .sha256)
# Never edit dist/ (or legacy release/) by hand.
```

把 **完整 Release 目录**放到 VPS（至少含下列文件）：

```text
vincula.sh
bin/vincula
lib/vincula-common.sh
lib/vincula-accountd.py
lib/vincula-accountd.service
lib/vincula-event.schema.json
release.lock
vincula.sh.sha256
```

```bash
sha256sum -c vincula.sh.sha256
# 若存在 release.lock，installer 会在 source common 之前校验 sibling hashes
sudo bash vincula.sh
```

发布 tarball 可用 [`vincula-bootstrap.sh`](vincula-bootstrap.sh)：

```bash
sudo env RELEASE_URL='https://example.com/vincula-0.2.5.tar.gz' \
  RELEASE_SHA256='...' \
  bash vincula-bootstrap.sh
```

（下载 archive → 校验 archive SHA-256 → 解压 → 校验 `release.lock` 逐文件 → exec `vincula.sh`。）

Installer 必须能从同目录读取 `bin/` 与 `lib/`，因此 **不支持** 仅 `curl | bash` 的单文件管道安装。本地/开发请直接从完整树运行 `sudo bash vincula.sh`，或使用 `dist/` 产物。

默认路径非交互。必要时可通过环境变量覆盖：

```bash
sudo env \
  VCL_SERVER=node.example.com \
  VCL_PORT=8443 \
  VCL_REALITY_HOST=www.cloudflare.com \
  bash vincula.sh
```

- `VCL_SERVER`：写入客户端 URI 的公网 IPv4、无方括号 IPv6 或 DNS 名称。
- `VCL_PORT`：1–65535，默认 `443`。
- `VCL_REALITY_HOST`：REALITY handshake server 和客户端 SNI。未设置时使用 `www.cloudflare.com`。显式指定失败就报错，不会偷偷换网站。

针对 pinned sing-box `1.13.18`，`www.microsoft.com` 在 known-bad 列表中（[SagerNet/sing-box#4290](https://github.com/SagerNet/sing-box/issues/4290)）。名单是版本相关知识。

未提供 `VCL_SERVER` 时，脚本用 `curl -4` 访问 `https://api.ipify.org` 读取公网 IPv4。得不到可用公网 IPv4 时要求显式 `VCL_SERVER=`。

安装 / 迁移成功后应同时看到：

```text
✓ sing-box.service active
✓ vincula-accountd.service active
```

任一方健康检查失败都会 **回滚 / die**，不会写成“安装成功但无 accounting”。

## Canonical state（Source of Truth）

- `state.json`：节点身份与 REALITY 状态（`node_id` / `node_name`；**不含** credential UUID / `owner.uuid`）
- `users.json`：用户身份与 credential（schema 2；**UUID 唯一 SoT**）
- `config.toml`：非秘密管理员设置（含 `node_id`、`clash_api_port` / `clash_api_secret`、accounting retention）

由此 **生成** `config.json`、`owner.uri`、systemd unit。不要反过来读 `config.json` 猜用户列表。

Identity ≠ Credential：`tag` / `user_id` 稳定；UUID 只是可轮换的 credential。禁止跨节点共用 UUID。`node_id` 为永久 UUID，禁止正式使用 `"local"`。

## 本机 Accounting / Stats

安装后启用 `vincula-accountd`（`User=root`，因需读写 `0600` settings/DB）：轮询本机 Clash API，按 `acct/<tag>` outbound 映射到 `user_id`，写入 SQLite。

**近似 accounting，不是精确计费；Reliable Accounting 尚未完成。** 短连接可能在两次 poll 之间漏记。详见 [`docs/accounting-reliability.md`](docs/accounting-reliability.md)。可选：向 `/var/lib/vincula/events.jsonl` 追加 `connection_closed` 事件以降低漏记（schema 见 `lib/vincula-event.schema.json`；运行时为手写解析，非 JSON Schema 库强制校验）。

正确性约定（0.2.5）：

| 主题 | 决策 |
| --- | --- |
| 日界 | UTC |
| 跨午夜 | 按 `closed_at` 所在 UTC 日计入 daily |
| destination | lowercase + 去尾点；不做 rDNS |
| IP-only | `destination_host` 可为 NULL |
| poll baseline | 首次见到活跃连接只记 baseline，不当增量 |
| counter 回落 | 新世代，不写负 delta |

保留期（产品决策）：raw connections **90** 天；daily_usage **730** 天。

```bash
vcl connections
vcl accounting status
vcl stats today
vcl stats user alice --today --top 20
vcl stats --days 7
vcl stats department eng --days 30
```

若 `vincula-accountd` 未运行或 `last_success_at` 超过约 5 分钟，`vcl stats` / `vcl connections` 会在 stderr 警告：**当前是历史 SQLite 视图，不是实时状态**。

## 管理命令

`vincula` 与 `vcl` 等价：

```bash
vcl info
vcl status
vcl check
vcl verify
vcl diagnose
vcl restart
vcl logs
vcl logs 200
vcl logs -f
vcl link
vcl user add <tag> [--display-name NAME] [--department DEPT]
vcl user set <tag> --display-name NAME [--department DEPT]
vcl user disable <tag>
vcl user enable <tag>
vcl user rotate <tag>
vcl user list
vcl user show <tag>
vcl user link <tag>
vcl user import FILE [--dry-run] [--output credentials.csv]
vcl user export [--credentials] [--output FILE]
vcl user verify
vcl connections
vcl accounting status
vcl stats today
vcl uninstall
vcl uninstall --yes
vcl version
```

用户变更走事务：备份 → 改 registry → 从 registry 生成 config → `sing-box check` → 原子安装 → restart（会警告连接可能短暂中断）→ health；失败回滚。`owner` 不可删除；`user remove` 在 0.2.5 拒绝；不能 disable 最后一个 enabled 用户。

`vcl verify` 检查节点 Reality 身份一致、用户 registry 与 config 一致，以及 Accounting Plane 基本健康。漂移则 FAIL，不静默修复。

`vcl check` 只做二进制 SHA-256 与 `sing-box check`。

## 重复执行与迁移

- 同版本重跑：双平面校验，不轮换凭据。
- 已安装 `0.1.0`–`0.1.5` 或 `0.2.0`–`0.2.4`：显式 migration 到 0.2.5，保持 Reality keys / short ID / owner credential UUID；若 `node_id` 缺失或为 `local` 则生成永久 UUID 并同步 credentials。
- known-bad REALITY target 必须显式 `VCL_REALITY_HOST=` 才能在迁移时更换。
- 不支持降级或跨未知版本。
- Fresh install 若机器上已有 `/var/lib/vincula` 或 accounting 文件会直接拒绝（需先 `vcl uninstall` 或人工清理；本版不提供 `vcl recover`）。

## 卸载

`vcl uninstall` / `vcl uninstall --yes` 只删除 Vincula 能证明拥有的资源。先 stop `vincula-accountd` 与 `sing-box` 并确认 inactive，再删文件（含 `accounting.db` / `events.jsonl`）；**historical accounting data will be permanently removed**；purge 带 marker 的 `/var/backups/vincula` 迁移备份。无 `--force`。

## 安装后的文件

```text
/etc/vincula/
├── VERSION
├── config.toml
├── install.manifest
├── owner.uri
├── sing-box.binary.sha256
├── state.json
└── users.json

/etc/sing-box/config.json
/etc/systemd/system/sing-box.service
/etc/systemd/system/vincula-accountd.service
/usr/local/bin/sing-box
/usr/local/bin/vincula
/usr/local/bin/vcl
/usr/local/lib/vincula/
├── sing-box.lock
├── vincula-common.sh
├── vincula-accountd.py
└── vincula-event.schema.json
/var/lib/vincula/
├── accounting.db
└── events.jsonl   # optional telemetry ingest
```

## 开发与验证

```text
vincula.sh
vincula-bootstrap.sh
release.lock
bin/vincula
lib/vincula-common.sh
lib/vincula-accountd.py
lib/vincula-accountd.service
lib/vincula-event.schema.json
docs/accounting-reliability.md
docs/release-readiness-0.2.5.md
docs/known-issues-0.2.5.md
docs/release-readiness-0.2.4.md
docs/freeze-0.2.4.md
scripts/gen-release-lock.sh
scripts/build-release.sh
tests/test.sh
CHANGELOG.md
.gitignore
```

```bash
bash -n vincula.sh bin/vincula lib/vincula-common.sh
python3 -m py_compile lib/vincula-accountd.py
bash tests/test.sh
bash scripts/gen-release-lock.sh
bash scripts/build-release.sh
VCL_INTEGRATION=1 bash tests/test.sh
```

改动 first-party 文件后务必重跑 `scripts/gen-release-lock.sh`，并用 `scripts/build-release.sh` 生成 `dist/` 部署产物（勿手改 `dist/` / `release/`）。


## 明确不做

不做：Hysteria2/TUIC、公网 Web UI、订阅计费、HTTPS MITM、自动追 latest、fleet 聚合（V0.3+）、billing-grade / Reliable Accounting、单文件 `curl|bash` 安装、`vcl recover`。
