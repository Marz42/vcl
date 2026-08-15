# Changelog

协议始终是 `VLESS + REALITY + xtls-rprx-vision + TCP`。sing-box 固定 `1.13.18`。不做后台自动更新。

## 0.2.6

Accounting UX：统一查询/结果模型、导出与健康可见性。记账仍为 **approximate / Clash polling**（非计费级）。

### Stats CLI

- `vcl stats today|yesterday|--days N|--month`（UTC）
- `vcl stats user|department|host …` 与 `vcl stats top users|departments|hosts [--limit N]`
- `--json` / `--csv FILE`（原始整数字节）；单路径 `lib/vincula-stats.py`
- 部门分析使用 **current attribution**（`usage.user_id` → 当前 `users.json` department）
- IP-only 目标保留并标注 `[IP only] <ip>`；不丢弃
- 报告含 accounting mode / collector / freshness / hostname·IP coverage

### 运维

- `vcl connections`：accountd 非 active 时失败（UNAVAILABLE），不以 SQLite 伪装 live
- `vcl accounting status`：新鲜度与 coverage；`vcl accounting retention` 只读展示 raw/daily 天数

### 迁移

- 接受：`0.1.0`–`0.1.5` 与 `0.2.0`–`0.2.5` → `0.2.6`
- 无 DB schema bump（仍为 schema_version=2）

## 0.2.5

User provisioning & lifecycle：批量导入/导出、metadata、verify，以及 disable/enable/rotate 运维闭环。本版本**不新增** stats/analytics（留给 0.2.6）。

### 用户生命周期

- Tag 规则扩展：`^[a-z0-9][a-z0-9._-]{0,31}$`（允许点号，最长 32）
- `vcl user add`：成功后打印 User ID / Credential / Status / VLESS URI
- `vcl user set TAG --display-name/--department`：仅改 metadata
- `vcl user disable|enable|rotate`：沿用 registry→config 事务；重启前警告连接可能短暂中断
- `user remove/purge/delete`：0.2.5 明确拒绝（exit 2）；请用 disable
- `vcl user list` / `show`：人类可读格式，默认不打印 raw UUID

### 批量供应

- `vcl user import FILE [--dry-run] [--output credentials.csv] [--include-uuid]`：全量校验后一次提交；失败零变更
- `vcl user export [--credentials] [--output FILE] [--include-uuid]`：metadata CSV 可 stdout；credential export 必须 `--output` 且 `0600`
- `vcl user verify`：schema / 唯一性 / enabled↔active credential / registry↔sing-box inbound 对照

### 迁移

- 接受：`0.1.0`–`0.1.5` 与 `0.2.0`–`0.2.4` → `0.2.5`
- 保留 node identity、REALITY 密钥、全部 `user_id` / `credential_id` / UUID 与 accounting DB

## 0.2.4

Release gate：把 Accounting Plane 提升到与 Proxy Plane 同级的事务 / 迁移 / 校验保证；收敛数据模型与 packaging integrity。本版本**不新增** stats/功能面。

**Freeze (2026-08-15):** 门禁 V-MIG / V-RB / V-PY310 PASS；此后 **只接受 P0/P1 regression fix**。见 `docs/freeze-0.2.4.md`。

### 生命周期（P0）

- `enable_accountd_service` 硬失败：`systemctl enable --now` + `wait_for_accountd_healthy`（is-active、DB/`schema_version=2`、Clash API Bearer 成功；无 secret / 错 secret 必须失败）后才允许 `INSTALL_COMMITTED=1`
- 成功文案拆分：`✓ sing-box.service active` / `✓ vincula-accountd.service active`
- `preflight_clean_install`：`$VAR_LIB_VINCULA` / `accounting.db` / `events.jsonl` 任一存在即拒绝 fresh install（不猜测是否旧数据）
- Migration：先 stop accountd → 备份 core + accounting artifacts（py/unit/schema）、SQLite `.backup`、events、`SERVICE_STATE` → 安装 → health；失败 `rollback_migration` 恢复双平面
- `verify_existing_install` / `vcl verify`：`[Proxy Plane]` + `[Accounting Plane]`；任一组 FAIL 非零退出；collector `last_success_at` >5m 视为不健康
- 安装前静态校验：`python3 -m py_compile`、`python3 -m json.tool` schema、`systemd-analyze verify` unit（有 systemd 时）
- `clash_api_port`：`validate_port` + localhost 端口冲突检测
- `events.jsonl` 写入 `install.manifest`；uninstall 文案含 *historical accounting data will be permanently removed*
- `vcl stats` / `vcl connections`：accountd inactive 或 collector 过期时 stderr 警告 stale（非实时视图）

### 数据模型

- `node_id`：永久 UUID（fresh：`sing-box generate uuid`）；可变 `node_name`（默认 hostname）；禁止正式使用 `"local"`；migrate 时缺失/`local` 生成一次并写回 credentials
- Credential UUID 唯一 SoT = `users.json`；`state.json` 不再写入 `owner.uuid`
- Accounting schema_version=2：`connections` / `daily_usage` 以 `user_id` 为长期主键 + 可选 `user_tag`；启动时 `users.json` 建 tag→user_id；migrate 失败 fail-closed
- 损坏 DB：拒绝启动，不自动抹成空库
- 正确性基线：UTC 日界；跨午夜按 `closed_at` UTC 日计入 daily；destination 小写去尾点、无 rDNS；IP-only 允许 host NULL；poll 首次见连接记 baseline；counter 回落=新世代；只记正增量

### Packaging / hardening

- `release.lock`（first-party SHA-256）；installer 在 source `vincula-common.sh` **之前**校验
- `vincula-bootstrap.sh`：下载 archive → 校验 archive SHA → 解压 → 校验 `release.lock` → exec `vincula.sh`
- README：废弃单文件 / `curl|bash` 路径；推荐完整目录或 bootstrap
- `vincula-accountd.service`：保持 `User=root`（读 `0600` settings/DB）；`NoNewPrivileges` / `PrivateTmp` / `ProtectSystem=strict` / `ProtectHome` / `ReadWritePaths=/var/lib/vincula` / 空 `CapabilityBoundingSet` 等
- SQLite：`WAL`、`busy_timeout=5000`、`foreign_keys=ON`、显式 transaction
- 目标 Python：**Ubuntu 22.04 / 3.10+**（避开 3.11+-only 特性）

### 产品声明

- Retention（产品决策）：raw **90** 天 / daily **730** 天
- 仍为 **approximate polling accounting**；Reliable Accounting **未完成**（见 `docs/accounting-reliability.md`）
- 迁移接受：`0.1.0`–`0.1.5` 与 `0.2.0`–`0.2.3` → `0.2.4`

### 文档与验证

- Gate 报告：`docs/release-readiness-0.2.4.md`（R01–R25 / F01–F15）
- RC 测试手册：`docs/rc-test-manual-0.2.4.md`
- 现存问题：`docs/known-issues-0.2.4.md`
- 自动化：`bash tests/test.sh`（207+）

### Fixes（RC 实机）

- sing-box **1.13** 已移除 inbound 遗留字段：生成配置不再写 `inbounds[].sniff`，改为 `route.rules` 的 `"action": "sniff"`；`auth_user` 路由改为 `"action": "route"` + `outbound`（见 [migration](https://sing-box.sagernet.org/migration/#migrate-legacy-inbound-fields-to-rule-actions)）
- `vcl user add|rotate|…`：`user_mutation_apply` 不再对 `readonly USERS_FILE` 赋值；改为把 staged `users.json` 路径显式传给 `render_config_from_registry` / `regenerate_owner_uri`
- 实现 `vcl stats yesterday`（usage 已文档化但此前未接解析）
- **Freeze P0：** migration 对 sing-box 1.13 legacy inbound（`sniff`）预检失败时警告并继续，跳过旧 config health wait，从 SoT 重生配置；owner UUID 经 `owner_active_uuid_from_registry`
- Debian 13：0.2.3-shaped → 0.2.4 migration + 强制 rollback PASS；Ubuntu 22.04 Docker：Python 3.10.12 `py_compile` PASS
- Debian 13 amd64 实机：主路径 / Clash 鉴权 / owner 记账 / user 生命周期部分 PASS；完整 RC 矩阵仍见 `docs/known-issues-0.2.4.md`

## 0.2.3

Reliable accounting path（不 fork sing-box binary）。

- 文档：`docs/accounting-reliability.md` — Clash API 轮询缺口评估与未来 telemetry 方案
- 可选文件 ingest：`/var/lib/vincula/events.jsonl`（`connection_closed`），存在时优先于 poll-close
- 事件 schema：`lib/vincula-event.schema.json`
- 迁移接受 `0.1.0`–`0.1.5` 与 `0.2.0`–`0.2.2`

## 0.2.2

Analytics：日常汇总与查询。

- `daily_usage` rollup（date × user × destination）
- 保留期：`accounting_raw_retention_days` / `accounting_daily_retention_days`
- CLI：`vcl stats today`、`vcl stats user <tag> [--today] [--top N]`、`vcl stats --days N`、`vcl stats department <name>`

## 0.2.1

Local Accounting：本机 Clash API + 近似流量采集。

- `experimental.clash_api` 仅绑定 `127.0.0.1`（`clash_api_port`，默认 9090）
- 每用户 `acct/<tag>` outbound + `auth_user` 路由；`route.final` 仍为 `direct`
- `vincula-accountd`（Python 3 stdlib）轮询 `/connections`，写入 `/var/lib/vincula/accounting.db`
- systemd：`vincula-accountd.service`；`vcl connections` / `vcl accounting status`
- 明示：轮询 accounting ≠ 精确计费；短连接可能漏记

## 0.2.0

Identity：从「一个 owner 链接」升级到有身份的用户系统。

- 拆出 `bin/vincula` 与 `lib/vincula-common.sh`（安装时复制，不再用巨大 heredoc）
- `users.json` schema 2：`user_id` / `tag` / `display_name` / `department` / credential 轮换历史
- `config.json` 从 registry 生成多用户 inbound（`name` = tag）
- `vcl user add|remove|disable|enable|rotate|list|show|link`
- 用户变更事务：备份 → 生成 → check → restart → verify；失败回滚
- `vcl verify` 扩展到用户 tag/UUID 与 config 一致
- 迁移 `0.1.0`–`0.1.5` → `0.2.0`，保持 owner UUID 与 Reality keys
- 安装需完整 release 目录（含 `bin/`、`lib/`），不再支持仅 stdin 管道安装

## 0.1.5

发布前修复 v0.1.4 的阻塞问题。

- REALITY self-test 用 `curl --help all` 检测 SOCKS5，避免 `curl --help` 截断导致误判、fresh install 失败
- `vcl uninstall` 删除 `/var/backups/vincula` 中带 marker 的迁移备份（含私钥）；不再留下 secret residue
- 卸载必须先 stop 并确认服务 inactive / MainPID=0，失败则不删除任何文件
- 公网地址改为 `curl -4 https://api.ipify.org`，避免双栈 VPS 被 api64 返回 IPv6 而安装失败
- known-bad REALITY target（如 Microsoft）不再“成功迁移”；必须显式 `VCL_REALITY_HOST=` 才能更换 SNI
- service account 持久化 UID/GID/home/shell，卸载前身份不一致则保留账号
- 生产监听改为 `0.0.0.0`（IPv4-first）

## 0.1.4

Clean uninstall，让同一台 VPS 可以反复 `install → uninstall → reinstall`。

- 新增 `vcl uninstall` / `vcl uninstall --yes`
- 安装时写入 `install.manifest` 和 systemd `# Managed-By: vincula`
- `state.json` 持久化 service account 是否由 Vincula 创建
- 卸载前校验 ownership、二进制 SHA-256、unit / helper 标记；失败则不做任何删除
- 只删除 Vincula 拥有的文件；非空目录、外来 `vcl`、预先存在的 `sing-box` 账号予以保留
- 不卸载 apt 依赖，不提供 `--force`

## 0.1.3

解决升级和状态一致性。

- 已安装 `0.1.0`–`0.1.2` 时再跑新脚本：校验 → 备份 → 从 canonical state 生成配置 → 健康检查 → commit；失败回滚
- 迁移保持 UUID、REALITY key、short ID
- 明确 Source of Truth：`state.json` / `users.json` / `config.toml` 生成 `config.json`、URI、unit
- 新增 `vcl verify`：检查节点身份在各份状态文件中是否一致
- 公网地址 fail closed：得不到公网 IPv4 时要求 `VCL_SERVER=`，不再写出 `10.x` 这类不可用链接
- 安装成功信息改为「本机检查通过」，并明确未验证外部 TCP/443

## 0.1.2

区分静态检查和诊断。

- `vcl check` 仍只做二进制 SHA-256 与 `sing-box check`
- 新增 `vcl diagnose`：安装、配置、服务、REALITY target、本机 e2e self-test、网络；标出本机无法验证的外部连通性
- 安装时增加 localhost REALITY self-test，失败即停止，不静默换 target

## 0.1.1

修已知会踩的坑。

- 默认 REALITY host 改为 `www.cloudflare.com`
- `www.microsoft.com` 列入当前 pinned sing-box 的 known-bad 列表（SagerNet/sing-box#4290）
- 显式 `VCL_REALITY_HOST` 失败就报错，不再偷偷换成另一个网站
- `vcl status` 确认监听端口由 sing-box 持有
- systemd `ExecStartPre=sing-box check`
- `vcl logs` 支持行数和 `-f`

## 0.1.0

初始版本。

- Debian 12/13、Ubuntu 22.04/24.04/26.04；amd64 / arm64
- 固定协议、固定 sing-box 版本与 SHA-256
- 一次性安装，输出 owner VLESS URI
- helper：`vcl info` / `status` / `check` / `restart` / `logs` / `link`
- 同版本重跑只校验、不轮换凭据
