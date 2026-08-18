# Vincula 命令手册（0.3.1-dev）

面向操作员的 **完整 CLI 参考**：每条命令、每个参数、典型用法与失败语义。

合同与限制以 living-tree gate 为准：[`release-readiness-0.3.1.md`](release-readiness-0.3.1.md) · [`known-issues-0.3.1.md`](known-issues-0.3.1.md)。专题：身份 [`identity.md`](identity.md) · 备份/换机 [`backup.md`](backup.md) · 控制器运维 [`fleet.md`](fleet.md)。

记账始终是 **approximate / Clash polling**，不能当发票。节点 `vcl` **没有** `fleet` 子命令；工作站用 `vcl-fleet`。

---

## 目录

1. [怎么读](#how-to-read)
2. [角色、产物与权限](#roles)
3. [命名规则](#names)
4. [退出码](#exit-codes)
5. [安装器 `vincula.sh`](#installer)
6. [Bootstrap `vincula-bootstrap.sh`](#bootstrap)
7. [节点 CLI `vcl` / `vincula`](#node-cli)
8. [控制器 `vcl-fleet`](#fleet-cli)
9. [开发机脚本](#dev-scripts)
10. [环境变量总表](#env)
11. [常见流程](#playbooks)
12. [Local Audit UI 手动测试指南](#ui-manual-test)

---

## 怎么读 {#how-to-read}

- **节点命令**一律在 VPS 上以 root 跑（`sudo vcl …`），除非标明例外（`help` / `version`）。
- **控制器命令**在管理员工作站上跑，**不要** root。Unix：`python3 bin/vcl-fleet …` 或解压 zip 后的同路径；Windows 11：`bin\vcl-fleet.cmd …`。下文写 `vcl-fleet`。
- 方括号 `[…]` 表示可选；尖括号 `<…>` 或大写词是必填值。
- `--json` 成功时 stdout 一份 JSON 对象（`schema_version: 1`）；人类输出走表格/纯文本。失败时错误在 stderr，JSON 命令仍可能在 stdout 打 `ok: false`。

---

## 角色、产物与权限 {#roles}

| 角色 | 产物 | 入口 |
| --- | --- | --- |
| 开发机打包 | `dist/vincula-node-<version>.tar.gz` | `scripts/build-release.sh` |
| 开发机打包 | `dist/vincula-controller-<version>.zip` | `scripts/build-controller.sh` |
| VPS 安装 | 源树或解开的 node tarball | `sudo bash vincula.sh` |
| VPS 从 URL 安装 | 同上 + pin | `vincula-bootstrap.sh` |
| 节点日常 | 安装后的 `/usr/local/bin/vcl`（≡ `vincula`） | `sudo vcl …` |
| 工作站 | zip 内 `bin/vcl-fleet` / `vcl-fleet.cmd` + `lib/vincula-ui/` | 无 root、无 systemd、无公网管理口；`ui` 仅 localhost |

节点锁：`/run/lock/vincula.lock`（回退 `/var/lock/vincula.lock`），超时 30s → 退出 **4**，文案 `busy: another vincula operation in progress`。覆盖用户变更、restore、其它写 `users.json` 的路径。

控制器锁：`$FLEET_HOME/.lock`，超时 30s，同一 busy 文案、退出 **4**。覆盖 `node add/set/disable/enable/retire/replace`、`sync`、写 registry / `fleet.db`。

SSH：系统 OpenSSH。读探测超时 **20s**；用户/restore 等变更 **60s**；远端 `backup create` **120s**。

---

## 命名规则 {#names}

| 项 | 规则 |
| --- | --- |
| 用户 tag / 节点短名 | `^[a-z0-9][a-z0-9._-]{0,31}$`（小写、数字、`._-`，字母或数字开头，最长 32） |
| `display_name` / `department` | Unicode 与空格可以；禁止 ASCII 控制字符（含换行、TAB、DEL）；最长 **128** |
| UUID | 标准 8-4-4-4-12 小写 hex |
| `ssh_host` | DNS / IPv4 / 无括号 IPv6；拒绝控制字符与 shell 元字符 |
| `--host-key` | `SHA256:` + base64 指纹（写入用户 `known_hosts`） |

禁止 `user remove` / purge / delete / tag rename。停用请用 `disable`。

---

## 退出码 {#exit-codes}

| 码 | 谁 | 含义 |
| --- | --- | --- |
| **0** | 全部 | 成功（含「全部节点 SUCCESS」） |
| **1** | 多数 | 一般错误（校验、拒绝、远端 JSON `ok` 不为 true） |
| **2** | `vcl-fleet` 多节点 | **PARTIAL**：至少一个目标失败。无分布式 rollback |
| **3** | 节点 `vcl audit export` | `CURSOR_EXPIRED` 或 `CURSOR_AHEAD`（看 stderr meta.`error`） |
| **4** | 节点 / 控制器 | 操作锁 busy |
| **255** | 控制器 SSH | 传输层失败（连不上、超时、非 JSON）。变更命令还要求远端进程 **exit 0** |

---

## 安装器 `vincula.sh` {#installer}

非交互。同目录必须有 `bin/` + `lib/` + `release.lock` + `vincula.sh.sha256`。

```bash
sudo bash vincula.sh
sudo bash vincula.sh --runtime-only
bash vincula.sh --help
bash vincula.sh --version
```

### 参数

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| （无） | | 全新安装，或同版本校验双平面，或从 allowlist 源版本原地迁移 |
| `--runtime-only` | 否 | 只装运行时（sing-box、systemd、helper、Python 库）。**不写** `/etc/vincula/VERSION`，不生成身份。给 `vcl restore` / `vcl-fleet node replace` 用 |
| `--help` / `-h` | 否 | 帮助后退出 0 |
| `--version` | 否 | 打印版本后退出 0 |

`--runtime-only` 与环境变量 `VCL_RUNTIME_ONLY=1` 等价。

### 安装器环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `VCL_SERVER` | 试 `https://api.ipify.org` | 写入客户端 URI 的公网 IPv4 / 无括号 IPv6 / DNS |
| `VCL_PORT` | `443` | 监听端口，1–65535 |
| `VCL_REALITY_HOST` | `www.cloudflare.com` | REALITY handshake server + 客户端 SNI。部分域名在已知坏列表里会被拒绝 |
| `VCL_RUNTIME_ONLY` | 空 | `1` 等同 `--runtime-only` |

### 行为

- **全新**：已有 `/var/lib/vincula` 或半残安装会拒绝，报错里带确切清理命令。没有 `vcl recover`。
- **同版本再跑**：校验 `sing-box` + `vincula-accountd`，**不**轮换 UUID / Reality。
- **升级 allowlist**：`0.1.0`–`0.1.5` 与 `0.2.0`–`0.3.0` → 当前 `0.3.1-dev`。不含 `0.3.0-dev` / `0.3.1-dev`。不降级、不跳未知版本。升级 **不**重 mint `node_id` / `instance_id`，不旋转凭据与 Reality。
- 成功必须两个 unit 都 active，否则回滚。

```bash
sudo env VCL_SERVER=203.0.113.10 VCL_PORT=443 VCL_REALITY_HOST=www.cloudflare.com \
  bash vincula.sh

# 换机新机（不要写 VERSION）
sudo bash vincula.sh --runtime-only
```

---

## Bootstrap `vincula-bootstrap.sh` {#bootstrap}

从 URL 拉 node tarball、校验、再 exec `vincula.sh`。 **不是** `curl | bash` 单文件安装。

```bash
sudo env RELEASE_URL='https://example.com/vincula-node-<version>.tar.gz' \
  RELEASE_SHA256='<64-hex>' \
  bash vincula-bootstrap.sh
```

### 参数

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--allow-insecure-sibling-digest` | 否 | **仅非生产**。无 pin 时用 `${RELEASE_URL}.sha256` 当期望摘要。生产禁止 |

等价环境变量：`VCL_ALLOW_INSECURE_SIBLING_DIGEST=1`。

### 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `RELEASE_URL` | 生产必填（除非 embed） | tarball URL |
| `RELEASE_SHA256` | 生产必填（除非 embed） | 期望 SHA-256。与 archive 字节、以及拉下来的 `${URL}.sha256` **三者一致** |
| `EMBEDDED_RELEASE_URL` / `EMBEDDED_RELEASE_SHA256` | 否 | 发布工程可写进脚本的默认 pin |

从同一 URL 拉兄弟 `.sha256` **只能**发现传输损坏，**不能**发现源站把 tar 和 `.sha256` 一起换掉。生产必须把 digest 钉在环境 / 镜像 / embed。

拉下来之后仍走 `vincula.sh`，因此 `VCL_SERVER` / `VCL_PORT` / `VCL_REALITY_HOST` 同样生效。

---

## 节点 CLI `vcl` / `vincula` {#node-cli}

安装后：`/usr/local/bin/vcl` ≡ `/usr/local/bin/vincula`。

除 `help` / `version` 外需要 **root**。除 `help` / `version` / `uninstall` / `restore` 外还需要完整安装（存在 `VERSION`、sing-box 二进制、`config.json`）。`restore` 需要 root，但目标必须是 **fresh / runtime-only**（不能已有 `VERSION`）。

```bash
sudo vcl help
sudo vcl version
```

---

### `vcl help`

打印全部子命令摘要。无参数。

---

### `vcl version`

打印 Vincula 与 pinned sing-box 版本。无参数。不要求 root。

---

### `vcl info`

非密钥节点信息（地址、端口、SNI、用户数等）。无参数。不打印 Reality 私钥或 VLESS uuid。

```bash
sudo vcl info
```

---

### `vcl identity [--json]`

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--json` | 否 | JSON：`node_id`、`instance_id`、`node_name`、版本、schema |

人类输出同样这些字段。控制器 `node add` 会 SSH 这条命令。

```bash
sudo vcl identity
sudo vcl identity --json
```

---

### `vcl status [--json]`

检查 `sing-box` / `vincula-accountd`、端口是否在听、监听是否属于 sing-box。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--json` | 否 | 机器可读 |

```bash
sudo vcl status
sudo vcl status --json
```

---

### `vcl check`

快速静态检查：sing-box 二进制 SHA-256、配置语法。无参数。不跑 REALITY 探测。

```bash
sudo vcl check
```

---

### `vcl verify [--json]`

核对 canonical 状态（`state.json` / `users.json` / `config.toml`）与生成物（`config.json`、owner URI 等），含 accounting 平面。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--json` | 否 | 机器可读 |

```bash
sudo vcl verify
```

---

### `vcl diagnose`

运行时、出网、REALITY 自测（会用 SOCKS 走本机入站探测 SNI）。无参数。比 `check` 重。

```bash
sudo vcl diagnose
```

---

### `vcl restart`

校验配置后重启 `sing-box.service`。无参数。活跃连接会断。

```bash
sudo vcl restart
```

---

### `vcl logs [N | -f]`

`journalctl -u sing-box.service`。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| （无） | | 最近 **100** 行 |
| `N` | 否 | 最近 N 行（正整数） |
| `-f` / `--follow` | 否 | 跟随 |

```bash
sudo vcl logs
sudo vcl logs 200
sudo vcl logs -f
```

---

### `vcl link`

打印 **owner** 用户的 VLESS URI（含 uuid）。无参数。

```bash
sudo vcl link
```

---

### `vcl user add <tag> [选项]`

新增用户。会写 `users.json`、渲染 `config.json`、**restart sing-box**。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `<tag>` | 是 | 用户 tag（见命名规则）。已存在则拒绝 |
| `--user-id UUID` | 否 | 注入 fleet-global `user_id`。省略则本节点 `UUID()`。同节点 tag 或 `user_id` 冲突则拒绝 |
| `--display-name NAME` | 否 | 显示名；默认由 tag 派生 |
| `--department DEPT` | 否 | 部门；默认空 |
| `--json` | 否 | `schema_version` 1；**不含** VLESS uuid |

```bash
sudo vcl user add alice --display-name "Alice" --department Sales
sudo vcl user add alice --user-id 11111111-1111-4111-8111-111111111111 --json
```

---

### `vcl user set <tag> --display-name NAME [--department DEPT]`

只改 metadata。`--display-name` 与 `--department` 至少给一个。 **不** restart sing-box。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `<tag>` | 是 | 已有用户 |
| `--display-name NAME` | 二选一 | 新显示名 |
| `--department DEPT` | 二选一 | 新部门（可空字符串视实现写入） |

```bash
sudo vcl user set alice --display-name "Alice Chen" --department Eng
```

---

### `vcl user disable <tag> [--json]`

停用。用户留在 registry；活跃凭据不再进 inbound。会 restart sing-box。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `<tag>` | 是 | |
| `--json` | 否 | |

最后一个 enabled 用户不可 disable（节点不变量：至少保留 owner/最后一人，以实现为准）。

```bash
sudo vcl user disable alice --json
```

---

### `vcl user enable <tag> [--json]`

重新启用已 disable 的用户。会 restart sing-box。

```bash
sudo vcl user enable alice --json
```

---

### `vcl user rotate <tag> [--json]`

新发活跃 VLESS uuid + `credential_id`；旧活跃行标 `revoked`。会 restart sing-box。`--json` **不含** uuid（用 `vcl user link` 取 URI）。

```bash
sudo vcl user rotate alice
sudo vcl user rotate alice --json
```

---

### `vcl user list [--json]`

列出用户。人类输出含 `USER_ID` 列。`--json` 为 0.2.9 合同：`list`/`show` **不含** VLESS uuid。

```bash
sudo vcl user list
sudo vcl user list --json
```

---

### `vcl user show <tag> [--json]`

单个用户详情（状态、`user_id`、凭据历史不含 uuid，除非人类 link）。

```bash
sudo vcl user show alice
sudo vcl user show alice --json
```

---

### `vcl user link <tag>`

该用户 **当前活跃** 凭据的 VLESS URI。无 `--json`。

```bash
sudo vcl user link alice
```

---

### `vcl user import FILE [选项]`

CSV 批量开通。表头至少有 `tag`；可选 `display_name,department`。**先全量校验再提交**，失败零变更。会 restart sing-box。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `FILE` | 是 | CSV 路径 |
| `--dry-run` | 否 | 只打印计划，不写 |
| `--output FILE` | 否 | 写出凭据 CSV（含 URI），模式 **0600** |
| `--include-uuid` | 否 | 输出里带 uuid 列（敏感） |

```bash
sudo vcl user import staff.csv --dry-run
sudo vcl user import staff.csv --output /root/credentials.csv
```

---

### `vcl user export [选项]`

导出本节点用户。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--credentials` | 否 | 含 `credential_id` 与 VLESS URI。必须同时 `--output` |
| `--output FILE` | `--credentials` 时必填 | 写入文件，**0600**；省略则 stdout（无 credentials） |
| `--include-uuid` | 否 | 额外 uuid 列 |

```bash
sudo vcl user export --output users.csv
sudo vcl user export --credentials --output credentials.csv
```

---

### `vcl user verify`

核对 `users.json` 与 `config.json` 里每个 enabled 用户的 tag/uuid。无参数。

```bash
sudo vcl user verify
```

---

### `vcl connections [N]`

最近连接行。要求 `vincula-accountd` **active**；否则拒绝（不会把 SQLite 假装成 live）。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `N` | 否 | 行数，默认 **30**，正整数 |

```bash
sudo vcl connections
sudo vcl connections 50
```

---

### `vcl accounting status`

accountd 是否 active、Clash 地址、库路径、open/total connections、`last_success_at`、hostname vs IP-only 覆盖率。无参数。只读。

```bash
sudo vcl accounting status
```

---

### `vcl accounting check`

跑 accounting 平面检查（retention、schema、服务是否该 active）。无参数。

```bash
sudo vcl accounting check
```

---

### `vcl accounting retention`

打印 `accounting_raw_retention_days` / `accounting_daily_retention_days`（默认各 90）。只读；要改去编辑 `/etc/vincula/config.toml` 再重启 accountd。

```bash
sudo vcl accounting retention
```

---

### `vcl accounting cycle [--set N]`

账期起始日（UTC），用于 `vcl stats --month`。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| （无） | | 打印当前 `billing_cycle_start_day`（默认 1） |
| `--set N` | 否 | 写入 1–28 |

```bash
sudo vcl accounting cycle
sudo vcl accounting cycle --set 1
```

---

### `vcl stats …`

近似用量。窗口是 **UTC 日**。`--date` / `--from` / `--to` 不能与 `--days` / `--month` 混用。

公共可选：

| 参数 | 说明 |
| --- | --- |
| `--json` | JSON |
| `--csv FILE` | 写 CSV |
| `--days N` | 含今天的最近 N 个 UTC 日，`N ≥ 1` |
| `--month` | 从账期起始日到今天（UTC） |
| `--date YYYY-MM-DD` | 单日 |
| `--from YYYY-MM-DD` | 与 `--to` 成对 |
| `--to YYYY-MM-DD` | 与 `--from` 成对 |
| `--today` | 仅 `stats user`：今天 |
| `--limit N` | `top` 模式条数，默认 20 |
| `--top N` | 兼容：`stats user TAG --top N` → 该用户 top destinations |

子命令：

```bash
sudo vcl stats today
sudo vcl stats yesterday
sudo vcl stats --days 7
sudo vcl stats --month
sudo vcl stats --date 2026-08-16
sudo vcl stats --from 2026-08-01 --to 2026-08-16
sudo vcl stats user alice --days 7
sudo vcl stats user alice --today --top 10
sudo vcl stats department Sales --days 30
sudo vcl stats host www.example.com --days 7
sudo vcl stats top users --days 7 --limit 20
sudo vcl stats top departments --month
sudo vcl stats top hosts --days 7 --json
sudo vcl stats --days 7 --csv /tmp/stats.csv
```

部门统计用 **当前** `users.json` 归属，不是历史部门。

---

### `vcl audit user TAG --from RFC3339 --to RFC3339 [选项]`

按 tag 查连接。窗口：**`started_at < --to` 且 `COALESCE(closed_at, last_seen_at) ≥ --from`**。`--from`/`--to` 必须带时区（`Z` 或 offset）。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `user TAG` | 与 `--user-id` 二选一 | tag |
| `--user-id UUID` | 二选一 | 直接按 `user_id`（可写成 `vcl audit --user-id UUID --from … --to …`） |
| `--from RFC3339` | 是 | 窗口起点（连接结束时刻含边界） |
| `--to RFC3339` | 是 | 窗口终点（`started_at` 不含） |
| `--host HOST` | 否 | 过滤 destination host |
| `--ip IP` | 否 | 过滤 destination IP |
| `--node NODE_ID` | 否 | 过滤 `node_id`（本机通常只有自己） |
| `--json` | 否 | |

```bash
sudo vcl audit user alice \
  --from 2026-08-10T00:00:00Z --to 2026-08-16T00:00:00Z
sudo vcl audit --user-id 11111111-1111-4111-8111-111111111111 \
  --from 2026-08-10T00:00:00Z --to 2026-08-16T00:00:00Z --json
sudo vcl audit user alice --from 2026-08-10T00:00:00Z --to 2026-08-16T00:00:00Z \
  --host www.example.com
```

---

### `vcl audit export --after EVENT_ID --jsonl [选项]`

增量导出。**stdout = JSONL 连接行**；**stderr = 一行 meta**。控制器 `sync` 用这条。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--after EVENT_ID` | 是 | 开区间。`0` = 从当前窗口开头（即使 retention 已截断也算成功） |
| `--jsonl` | 是 | 必须 |
| `--limit N` | 否 | `N ≥ 1`，最多导出行数 |
| `--stamp-identity` | 否 | **只给 reseed 用。** 仅填充 **缺失** 的行 `node_id`/`instance_id`（来自本节点身份）。已有但不匹配 → 失败。**不写** `accounting.db` |

特殊退出 **3**：

- `CURSOR_EXPIRED`：`after > 0` 且窗口有洞（`MIN(event_id) > after+1` 或空库）
- `CURSOR_AHEAD`：`after > 0` 且 `after > MAX(event_id)`（控制器 cursor 新于恢复后的旧库）

两者 stdout 空；用 meta.`error` 区分，不要只看 exit 3。

```bash
sudo vcl audit export --after 0 --jsonl
sudo vcl audit export --after 1200 --jsonl --limit 500
sudo vcl audit export --after 0 --jsonl --stamp-identity   # 仅 reseed
```

---

### `vcl backup create [选项]`

默认 **secretless**：身份 + 审计 + accounting，**不含**有效密钥，**不需要** age。归档模式 **0600**，目录 `/var/backups/vincula` **0700**。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--include-secrets` | 否 | 三份 canonical **原样**（含 Reality 私钥、uuid、Clash secret），整包 age。必须 `--age-recipient` |
| `--age-recipient FILE` | secrets 时必填 | age recipient 公钥文件（`age -R`） |
| `--output FILE` | 否 | 输出路径。默认 `node-<node_id>-<UTC>.tar`；secrets 且路径不以 `.age` 结尾时会变成 `.tar.age` |
| `--json` | 否 | |

缺 age 二进制（secrets 模式）：精确 `ERROR: Secret-bearing backup requires age.`（可用 `VCL_AGE_BIN` 覆盖二进制路径）。**没有**口令模式（`age -p`）。

人类成功：`Backup written to PATH`。含密钥时 stderr 还有 WARNING。

```bash
sudo vcl backup create
sudo vcl backup create --json
sudo vcl backup create --output /var/backups/vincula/pre-replace.tar
sudo vcl backup create --include-secrets --age-recipient /root/age-recipient.txt
```

禁止例行 `scp` live `accounting.db`。快照只用本命令（SQLite Backup API）。

---

### `vcl backup verify FILE [选项]`

在任何 restore mutation 之前也会强制 verify。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `FILE` | 是 | `.tar` 或 `.tar.age` |
| `--age-identity FILE` | age 包必填 | age identity |
| `--json` | 否 | 失败形如 `{"ok": false, "error": "checksum_mismatch"}` |

```bash
sudo vcl backup verify /var/backups/vincula/node-….tar
sudo vcl backup verify FILE.tar.age --age-identity /root/age-identity.txt --json
```

---

### `vcl restore FILE [选项]`

**Fresh-node / runtime-only only。** 已有 `$STATE_DIR/VERSION` → `Refusing to overwrite an existing Vincula install.` **没有** `--replace-node`（传入即拒绝）。

Shell 是唯一对外 JSON 发射器。成功：`daemon-reload` → 两个 unit `enable --now` → `is-enabled`/`is-active` → health → **最后** `commit-version` → 一份 `ok: true`。任一步失败：回滚、不写 VERSION、一份 `ok: false`、非 0。systemd 回滚不全 → `rollback_partial`。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `FILE` | 是 | 已 verify 的归档 |
| `--reissue-output FILE` | 安全模式强烈建议 / 控制器必给 | 新凭据 CSV（`user,node,old_credential_id,new_credential_id,vless_uri`），**0600** |
| `--server HOST` | 否 | 覆盖写入 URI 的公网地址（换机时用新 IP） |
| `--include-secrets` | 否 | 复用归档密钥，仍 mint 新 `instance_id`；无新 uuid 的 reissue 行 |
| `--age-identity FILE` | secrets 时必填 | |
| `--json` | 否 | 成功/失败各 **一份** 对象 |

安全模式（默认）：保留备份 `node_id` / `user_id` / accounting `event_id`；新 `instance_id`（≠ `node_id`）；旋转 Reality、Clash、活跃 uuid。

```bash
# 新机已 runtime-only
sudo vcl restore /tmp/vincula-restore.tar \
  --reissue-output /tmp/reissue.csv \
  --server 203.0.113.18 \
  --json
```

不要对已 bootstrapped（有 VERSION）的主机跑 restore。换机请先 `--runtime-only`。

---

### `vcl uninstall [--yes]`

删除 Vincula 拥有的资源（含 `accounting.db`、备份根、helper、unit）。历史流量不可恢复。无 `--force`。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| （无） | | 交互确认 `[y/N]` |
| `--yes` | 否 | 跳过确认 |

```bash
sudo vcl uninstall
sudo vcl uninstall --yes
```

---

## 控制器 `vcl-fleet` {#fleet-cli}

工作站本地工具。数据在 `$FLEET_HOME`：

| 平台 | 默认目录 |
| --- | --- |
| Windows | `%APPDATA%\vincula\` |
| Linux / macOS | `${XDG_CONFIG_HOME:-~/.config}/vincula/` |
| 测试 / 覆盖 | `VCL_FLEET_HOME` |

内含 `fleet.json`（schema 2，**不存** `instance_id`）、`fleet.db`（schema 2，审计缓存 + `instance_history`）、`last-status.json`（最近一次 status/verify 探针缓存）、可选 `users-cache.json`（UI「Refresh users」写入）。

控制器 zip / 源树还带 `lib/vincula-ui/`（stdlib HTTP + 静态页），由 `vcl-fleet ui` 加载。运维专题见 [`fleet.md`](fleet.md)；验收矩阵 AC-3.1 见同文。

Windows：

```bat
py -3 bin\vcl-fleet.cmd help
bin\vcl-fleet.cmd version
bin\vcl-fleet.cmd ui
```

Unix：

```bash
python3 bin/vcl-fleet help
python3 bin/vcl-fleet version
python3 bin/vcl-fleet ui
```

全局：

| 参数 | 说明 |
| --- | --- |
| `-h` / `--help` | argparse 帮助 |
| 各子命令 `--json` | `schema_version` 1 |

`vcl-fleet version` 打印 `vcl-fleet <version>`。`vcl-fleet help` 等同总帮助。

---

### `vcl-fleet init`

创建空 `fleet.json`。已有非空 registry 则拒绝。无参数。

```bash
python3 bin/vcl-fleet init
```

---

### `vcl-fleet node add NAME --host HOST [选项]`

SSH `vcl identity --json`（除非 `--offline`）并写入 registry。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `NAME` | 是 | 短名（与 tag 同字符集） |
| `--host HOST` | 是 | SSH 主机 |
| `--user USER` | 否 | SSH 用户，默认 `root`（也可用 `user@host` 形式由实现解析） |
| `--port N` | 否 | 默认 22 |
| `--host-key SHA256:…` | 建议 | 钉指纹，写入用户 `known_hosts` |
| `--node-id UUID` | `--offline` 时必填 | 逻辑节点 ID；在线时通常以远端 identity 为准 |
| `--offline` | 否 | 不 SSH，必须 `--node-id` |
| `--instance-id UUID` | 否 | **接受并忽略**（不写入 `fleet.json`） |

```bash
python3 bin/vcl-fleet node add lax --host 203.0.113.10 --host-key SHA256:abcd…
python3 bin/vcl-fleet node add lab --host 192.0.2.8 --offline \
  --node-id aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
```

---

### `vcl-fleet node list`

表：`NAME NODE_ID SSH_HOST USER ENABLED STATUS`。无参数。

```bash
python3 bin/vcl-fleet node list
```

---

### `vcl-fleet node show NAME`

一个 registry 记录。

```bash
python3 bin/vcl-fleet node show lax
```

---

### `vcl-fleet node set NAME --host NEW_HOST [选项]`

**Endpoint rebind**：同一物理实例，只改 SSH 坐标。凭据 / Reality / `instance_id` **全部保留**。不是换机。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `NAME` | 是 | |
| `--host HOST` | 是 | 新 SSH 地址 |
| `--user USER` | 否 | 新 SSH 用户 |
| `--port N` | 否 | 新 SSH 端口 |

```bash
python3 bin/vcl-fleet node set lax --host 203.0.113.10
```

---

### `vcl-fleet node disable NAME` / `vcl-fleet node enable NAME`

`active` ↔ `disabled`。**retired 不能 enable**。disable 后默认 `sync`/`status` 不再 SSH（除非 `--all`）。

```bash
python3 bin/vcl-fleet node disable lax
python3 bin/vcl-fleet node enable lax
```

---

### `vcl-fleet node retire NAME`

先 **final sync**，快照 `$FLEET_HOME/retired/NAME/`（identity/cursor/last-status，**不是** 0.3.0 backup），远端 disable 用户（保留节点不变量），再标 `retired`。不卸载节点，不删 `fleet.db` 历史。不可达节点不能 retire（必须完成 final sync）。

```bash
python3 bin/vcl-fleet node retire lax
```

---

### `vcl-fleet node replace NAME --host NEW --host-key SHA256:… [选项]`

**物理换机**，同一逻辑 `node_id`。只走 **secretless** 备份。NEW_HOST 必须已 `vincula.sh --runtime-only` 且 **没有 VERSION**。远端 restore argv：

`vcl restore FILE --reissue-output FILE --server HOST --json`

远端必须 **exit 0** 且 JSON `ok: true`（`ok:true` 但非 0 也算失败，registry 不变）。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `NAME` | 是 | 逻辑节点名 |
| `--host HOST` | 是 | 新机 SSH |
| `--host-key SHA256:…` | 是 | 新机指纹 |
| `--output FILE` | 否 | 本地 reissue CSV，默认 `$FLEET_HOME/reissue-NAME-<UTC>.csv`，**0600** |
| `--from-backup FILE` | 否 | 旧机已死：跳过 final sync 与远端 `backup create`，用现成 secretless 包。可能丢 sync 尾巴 |
| `--json` | 否 | |

成功后：更新 `sync_cursor.instance_id`，**保留** `last_event_id`，**不**自动 `--reseed`。下一步 sync 若 cursor 超前恢复库 → `CURSOR_AHEAD` → `--reseed`。

Live 两台 VPS 证据尚未跑。夹具绿 ≠ live PASS。清单：[`live-replace-checklist.md`](live-replace-checklist.md)。

```bash
# 新机
ssh root@203.0.113.18 'bash vincula.sh --runtime-only'

# 工作站
python3 bin/vcl-fleet node replace lax \
  --host 203.0.113.18 \
  --host-key SHA256:… \
  --output ./reissue-lax.csv
```

---

### `vcl-fleet node instances NAME [--json]`

该逻辑节点的 `instance_history`（哪段时期哪台物理实例）。

```bash
python3 bin/vcl-fleet node instances lax
python3 bin/vcl-fleet node instances lax --json
```

---

### `vcl-fleet status [--json] [--all]`

探活表：NAME、NODE_ID、INSTANCE、SSH、PROXY、ACCOUNTING。默认只探 `active`。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--json` | 否 | |
| `--all` | 否 | 含 disabled / retired。retired 的 SSH=`-`，不 SSH |

时钟：skew `>30s` WARN，`>300s` FAIL（`audit-clock-health`）。不可调。

```bash
python3 bin/vcl-fleet status
python3 bin/vcl-fleet status --json --all
```

---

### `vcl-fleet verify [--json] [--all]`

聚合远端 `identity` / `status` / `verify` + 时钟。registry `node_id` 必须匹配。同一 `node_id` 新 `instance_id` → `WARN: instance changed, node_id stable`，**不**改 registry `node_id`。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--json` | 否 | 含 `warnings` / `checks` |
| `--all` | 否 | 同 status |

```bash
python3 bin/vcl-fleet verify
```

---

### `vcl-fleet user add TAG --node NAME | --nodes a,b [选项]`

同一 fleet-global `user_id` 开到多个节点。全部 SUCCESS → exit 0；任一 FAILED → **PARTIAL exit 2**，带每节点状态和可复制的 `--user-id` 补救。**不**做分布式 rollback。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `TAG` | 是 | |
| `--node NAME` | 与 `--nodes` 二选一 | 单节点 |
| `--nodes a,b` | 二选一 | 逗号分隔 |
| `--display-name NAME` | 否 | |
| `--department DEPT` | 否 | |
| `--user-id UUID` | 否 | 省略则生成一个全局 UUID。PARTIAL 补救必须带上同一个 |
| `--output FILE` | 否 | 凭据 CSV：`user,node,credential_id,vless_uri`，**0600** |
| `--json` | 否 | |

```bash
python3 bin/vcl-fleet user add alice --nodes lax,tokyo --display-name Alice --output alice.csv
# tokyo 失败后补救（同一 user_id）
python3 bin/vcl-fleet user add alice --node tokyo --user-id <SAME-UUID>
```

---

### `vcl-fleet user list [--json]`

从 **enabled** 节点聚合。某节点 SSH 失败 → PARTIAL exit 2。

```bash
python3 bin/vcl-fleet user list
python3 bin/vcl-fleet user list --json
```

---

### `vcl-fleet user show TAG [--json]`

每节点凭据状态（按稳定 `user_id`）。不要用 display_name 匹配。

```bash
python3 bin/vcl-fleet user show alice
```

---

### `vcl-fleet user enable TAG --node NAME [--json]`

**必须** `--node`。没有 fleets 范围的全局 enable。

```bash
python3 bin/vcl-fleet user enable alice --node lax --json
```

---

### `vcl-fleet user disable TAG --node NAME [--json]`

**必须** `--node`。禁止无 `--node` 的全局 disable。

```bash
python3 bin/vcl-fleet user disable alice --node lax
```

---

### `vcl-fleet user rotate TAG --node NAME [选项]`

**必须** `--node`。只转那一台的 uuid。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--node NAME` | 是 | |
| `--output FILE` | 否 | 凭据 CSV 0600 |
| `--json` | 否 | |

```bash
python3 bin/vcl-fleet user rotate alice --node lax --output alice-lax.csv
```

---

### `vcl-fleet user import FILE [选项]`

表头必须 **恰好** `tag,display_name,department,nodes`。`nodes` 为一名称或带引号的逗号列表 `"lax,tokyo"`。先校验全部行（tag、重复、节点必须已注册且 enabled），失败 exit 1、零 SSH。应用与 `user add` 相同（每行一个 `user_id`）。任一节点 FAILED → PARTIAL 2。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `FILE` | 是 | |
| `--dry-run` | 否 | 打印计划 |
| `--output FILE` | 否 | 凭据 CSV 0600 |

```bash
python3 bin/vcl-fleet user import users.csv --dry-run
python3 bin/vcl-fleet user import users.csv --output creds.csv
```

---

### `vcl-fleet user export [--credentials] [--output FILE]`

从 enabled 节点合并 CSV。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--credentials` | 否 | 含 URI；必须 `--output`，0600 |
| `--output FILE` | `--credentials` 时必填 | |

```bash
python3 bin/vcl-fleet user export --output users.csv
python3 bin/vcl-fleet user export --credentials --output creds.csv
```

---

### `vcl-fleet sync [选项]`

对 enabled 节点：读 `sync_cursor`（无则 `after=0`）→ SSH `vcl audit export --after CUR --jsonl` → 校验 meta/JSONL → 一事务 import → 成功才推进 cursor。

**普通 sync 不 stamp。** 缺 `node_id`、错身份、meta 缺身份 → 整批失败，**cursor 不变**，stderr 指向 `--reseed`。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--node NAME` | 否 | 只同步这一台（与 `--all` 互斥） |
| `--all` | 否 | 把 disabled 列入结果（标 DISABLED、不 SSH）。retired 仍跳过 |
| `--reseed NAME` | 否 | 删该节点本地 `audit_events` + `daily_usage`，cursor=0，再 `--after 0`，远端带 `--stamp-identity`。不删 `instance_history`。**不是** backup |
| `--json` | 否 | |

`CURSOR_EXPIRED` / `CURSOR_AHEAD` / 身份错误 → 该节点不 import，总体常为 exit **2**。`--reseed` 不是换机，也不是 snapshot。

```bash
python3 bin/vcl-fleet sync
python3 bin/vcl-fleet sync --node lax
python3 bin/vcl-fleet sync --all
python3 bin/vcl-fleet sync --reseed lax
python3 bin/vcl-fleet sync --json
```

---

### `vcl-fleet ui [--host 127.0.0.1] [--port 8765]` {#fleet-ui}

工作站 **localhost-only** 只读 Local Audit UI（**Overview / Audit / Health** 三页）。
Users / Nodes 只作 drill-down，不是独立管理台。默认监听
`http://127.0.0.1:8765`。仅允许 loopback（`127.0.0.1` / `::1`）；`0.0.0.0` /
公网绑定会 **立即失败退出**（exit **2**）。关闭 UI 进程 **不影响** VPS 节点。

**数据源：** `$FLEET_HOME` 本地缓存（`fleet.json` / `fleet.db` /
`last-status.json` / 可选 `users-cache.json`）。页面按钮
**Refresh status** / **Verify** / **Sync**（及 Overview 上的 **Refresh users**）
走与 CLI 相同的控制器路径（含 SSH）。审计检索与
`vcl-fleet audit user` 同一 interval-overlap 谓词；Top-N 与
`vcl-fleet stats top …` 同一 `daily_usage` 聚合。记账徽标为
**approximate**（Clash polling，不能当发票）。

**禁止（第一版）：** UI 内 add / rotate / retire / replace / restore / import /
**reseed**。突变与 reseed 一律 CLI；顶栏 **CLI recipes** 只复制命令、不代执行。
GET API 只读本地缓存（解析 tag 不 SSH）。所有 `/api/*` 要求
`X-Vincula-UI-Token`（注入首页 meta）+ loopback `Host`；POST 另要求
`Content-Type: application/json`；**若请求带 `Origin`，必须匹配** loopback
（浏览器 POST 会带 Origin；curl 等可省略）。默认页与 API
**不**展示 Reality 私钥、Clash secret、VLESS URI、reissue CSV、age identity。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 仅 loopback；`localhost` 归一为 `127.0.0.1`；`::1` 可用 |
| `--port` | `8765` | TCP 端口 `1..65535` |

```bash
python3 bin/vcl-fleet ui
python3 bin/vcl-fleet ui --host 127.0.0.1 --port 8765
python3 bin/vcl-fleet ui --host ::1 --port 8765
# 应失败：
python3 bin/vcl-fleet ui --host 0.0.0.0 --port 8765
# Windows:
bin\vcl-fleet.cmd ui
```

启动成功时 stdout 类似：

```text
Listening on http://127.0.0.1:8765
Local Audit UI (no identity mutations; Sync/Refresh write local cache; reseed is CLI-only). Ctrl+C to stop. Stopping does not affect VPS nodes.
```

#### 页面与动作

| 页 / 面板 | 内容 |
| --- | --- |
| 顶栏警告条 | 不健康 / ACCOUNTING STALE·FAIL / 时钟 / 无 status 缓存等 |
| **Overview** | KPI（节点数、健康占比）、7 日 Top users / Top destinations（approximate）、Warnings、用户摘要表 |
| **Audit** | 必填 user + `--from`/`--to`（RFC3339，窗口 ≤31 天）；默认最多 500 行；可选 node、destination 子串 |
| **Health** | `NAME \| SSH \| PROXY \| ACCOUNTING \| VERSION \| CLOCK \| LAST_SYNC`；点行开 Node 抽屉 |
| Node 抽屉 | `node_id` / instance 时间线 / endpoint / cursor；无 URI |
| User 抽屉 | tag / `user_id` / 节点分配 / credential **id**（非 uuid/uri）/ 近 7 日用量 |
| CLI recipes | 复制 init/node/user/backup 等命令模板 |

#### CLI → UI 归宿（全覆盖、不越权）

| CLI | UI |
| --- | --- |
| `status` / `verify` | Health + Overview warnings；按钮 Refresh / Verify |
| `sync` / `sync --reseed` | 顶栏 **Sync**（仅普通 sync）；`--reseed` **仅 CLI** |
| `node list/show/instances` | Health + Node 抽屉 |
| `user list/show` | Overview 用户表 + User 抽屉；Refresh users 写 `users-cache.json` |
| `audit user` | Audit 页 |
| `stats *` | Overview Top-N + 抽屉摘要 |
| `init` / `node add\|set\|replace\|retire\|enable\|disable` | CLI recipes only |
| `user add\|import\|export\|rotate\|enable\|disable` | CLI recipes only |
| `version` / `help` | 页脚版本 |

手测步骤见下文 [Local Audit UI 手动测试指南](#ui-manual-test)。

---

### `vcl-fleet audit user TAG --from RFC3339 --to RFC3339 [选项]`

查 **已 sync** 的 `fleet.db`，按稳定 `user_id` 跨节点合并。谓词与节点 `vcl audit` 相同。输出带 **node**。库里历史 unlabeled 行仍被 query 忽略。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `TAG` | 是 | 解析到 `user_id`；冲突则拒绝 |
| `--from` / `--to` | 是 | RFC3339，必须带时区 |
| `--node NAME` | 否 | 只看 registry 名 |
| `--json` | 否 | 含 `node_id,instance_id,user_id,event_id` |

```bash
python3 bin/vcl-fleet audit user alice \
  --from 2026-08-10T00:00:00Z --to 2026-08-16T00:00:00Z
python3 bin/vcl-fleet audit user alice \
  --from 2026-08-10T00:00:00Z --to 2026-08-16T00:00:00Z --node lax --json
```

---

### `vcl-fleet stats …`

只读 `daily_usage`（`started_at` 的 UTC 日）。与节点 `vcl stats` **不保证**字节一致。跨午夜连接没有按日拆分。`--days N` **必填**（含今天的 N 日）。

```bash
python3 bin/vcl-fleet stats user alice --days 30
python3 bin/vcl-fleet stats user alice --days 30 --json
python3 bin/vcl-fleet stats top users --days 7
python3 bin/vcl-fleet stats top hosts --days 7 --json
python3 bin/vcl-fleet stats node lax --days 30
```

`--json` 的合计在 `totals.by_node`。没有 `stats top departments`。

---

## 开发机脚本 {#dev-scripts}

在仓库根目录跑。改过节点 first-party 文件后必须先刷新 lock。

### `bash scripts/gen-release-lock.sh`

无参数。重写 `release.lock` 与 `vincula.sh.sha256`（9 个 first-party 文件的 SHA-256）。应在 **LF** 工作树上跑（Linux / CI）；Windows `core.autocrlf` 会改变字节。

### `bash scripts/build-release.sh`

无参数。生成 `dist/vincula-node-<version>/` 与 `.tar.gz` + `.sha256`，包内带 `release.lock`。

### `bash scripts/build-controller.sh`

无参数。生成 `dist/vincula-controller-<version>.zip` + sidecar `.sha256`；zip 内
`controller.lock`。成员含：

- `README-controller.md`
- `bin/vcl-fleet`、`bin/vcl-fleet.cmd`
- `lib/vincula-fleet.py`、`lib/vincula-audit.py`、`lib/vincula-backup.py`
- `lib/vincula-ui/server.py`
- `lib/vincula-ui/static/index.html`、`app.css`、`app.js`

解压后 `sha256sum -c controller.lock` 应通过。zip **不含** `vincula.sh` /
节点 `release.lock` / `vincula-accountd.service`。

### `bash scripts/rc-live-upgrade-driver.sh`

真机升级链。需要 `VCL_RC_HOST` / `VCL_RC_USER` / `VCL_RC_PASS` / `VCL_SERVER`。**不是** merge gate。

### `bash tests/test.sh` / `bash tests/test-fleet.sh`

单元测试。夹具 SSH，不是 live VPS。

---

## 环境变量总表 {#env}

生产/运维常用（不含测试注入）：

| 变量 | 用于 | 说明 |
| --- | --- | --- |
| `VCL_SERVER` | 安装器 | URI 公网地址 |
| `VCL_PORT` | 安装器 | 端口 |
| `VCL_REALITY_HOST` | 安装器 | REALITY SNI |
| `VCL_RUNTIME_ONLY` | 安装器 | `1` = `--runtime-only` |
| `RELEASE_URL` / `RELEASE_SHA256` | bootstrap | 生产 pin |
| `VCL_ALLOW_INSECURE_SIBLING_DIGEST` | bootstrap | 非生产 |
| `VCL_AGE_BIN` | 节点 backup | age 二进制路径 |
| `VCL_FLEET_HOME` | 控制器 | 覆盖数据目录 |
| `VCL_LOCK_TIMEOUT` | 节点 | flock 秒，默认 30 |
| `VCL_FLEET_LOCK_TIMEOUT` | 控制器 | flock 秒，默认 30 |

未文档化、仅测试：`VCL_RESTORE_FAIL_AFTER`、`VCL_RESTORE_SKIP_HEALTH`、`VCL_LOCK_FILE` 等。不要在生产使用。

---

## 常见流程 {#playbooks}

### 新 VPS

```bash
# 开发机
bash scripts/gen-release-lock.sh
bash scripts/build-release.sh
# 把 dist/vincula-node-<ver>/ 拷到 VPS

# VPS
sha256sum -c vincula.sh.sha256
sudo env VCL_SERVER=203.0.113.10 bash vincula.sh
sudo vcl status
sudo vcl link
```

### 本机加用户

```bash
sudo vcl user add bob --display-name Bob --department Eng
sudo vcl user link bob
```

### 工作站管多节点

```bash
python3 bin/vcl-fleet init
python3 bin/vcl-fleet node add lax --host 203.0.113.10 --host-key SHA256:…
python3 bin/vcl-fleet node add tokyo --host 203.0.113.20 --host-key SHA256:…
python3 bin/vcl-fleet user add alice --nodes lax,tokyo --output alice.csv
python3 bin/vcl-fleet sync
python3 bin/vcl-fleet status
python3 bin/vcl-fleet stats user alice --days 7
python3 bin/vcl-fleet ui   # 浏览器打开 http://127.0.0.1:8765
```

Windows 11：把上面的 `python3 bin/vcl-fleet` 换成 `bin\vcl-fleet.cmd`。

### 备份

```bash
sudo vcl backup create
sudo vcl backup verify /var/backups/vincula/node-….tar
```

### 换机（secretless）

1. 新机 `sudo bash vincula.sh --runtime-only`
2. 工作站 `vcl-fleet node replace NAME --host NEW --host-key SHA256:…`
3. 把 reissue CSV 发给用户
4. 停旧机
5. 若 sync 报 `CURSOR_AHEAD`：`vcl-fleet sync --reseed NAME`

不要用 `node set` 冒充换机。不要在已有 VERSION 的新机上 restore。

---

## Local Audit UI 手动测试指南 {#ui-manual-test}

面向管理员工作站（优先 **Windows 11**；Linux/macOS 同样适用）。自动化夹具在
`tests/test-fleet.sh`（AC-3.1）；本节是 **真人浏览器 + 真/假节点** 手测清单。
合同仍见 [`release-readiness-0.3.1.md`](release-readiness-0.3.1.md) —— B15 合上
**不**单独等于 READY FOR RC。

### 前置

| 项 | 说明 |
| --- | --- |
| Python | 3.10+（Win：`py -3` / `python`） |
| OpenSSH | 系统客户端（Win：可选功能「OpenSSH 客户端」） |
| 控制器 | 仓库 `bin/vcl-fleet` / `bin\vcl-fleet.cmd`，或解压后的 `vincula-controller-*.zip` |
| 数据目录 | 默认 `%APPDATA%\vincula` 或 `~/.config/vincula`；可用 `VCL_FLEET_HOME` 隔离测试 |
| 浏览器 | 本机任意现代浏览器；只访问 `127.0.0.1` / `[::1]` |

建议隔离目录（避免污染日常 registry）：

```bat
REM Windows
set VCL_FLEET_HOME=%TEMP%\vincula-ui-manual
mkdir "%VCL_FLEET_HOME%"
```

```bash
# Unix
export VCL_FLEET_HOME=/tmp/vincula-ui-manual
mkdir -p "$VCL_FLEET_HOME"
```

### A. 启动与绑定（AC-3.1-01 / 02 / 09）

1. **应成功：**

```bat
bin\vcl-fleet.cmd ui
```

```bash
python3 bin/vcl-fleet ui
```

   终端出现 `Listening on http://127.0.0.1:8765`。浏览器打开该 URL，见三页导航
   Overview / Audit / Health。

2. **应失败（立即 exit，勿监听）：**

```bat
bin\vcl-fleet.cmd ui --host 0.0.0.0 --port 8765
```

   stderr 含 `refuses non-loopback`；本机 `netstat` / 资源管理器无对应监听。

3. **可选 IPv6 localhost：** `ui --host ::1`，浏览器打开 `http://[::1]:8765`。

4. **关 UI：** 终端 Ctrl+C。节点上 `systemctl is-active sing-box vincula-accountd`
   仍为 active（若你有真节点）；关 UI **不**停远端服务（AC-3.1-09）。

### B. 有缓存时的只读面（AC-3.1-03 / 06 / 07 / 11）

若已有节点，先 CLI 铺缓存：

```bat
bin\vcl-fleet.cmd status --json
bin\vcl-fleet.cmd sync
bin\vcl-fleet.cmd ui
```

| 检查 | 期望 |
| --- | --- |
| Overview KPI | 节点数、healthy/unhealthy、上次 probe 时间 |
| approximate 徽标 | 可见；文案强调非计费 |
| Top users / destinations | 有 sync 数据时非空；声明 7d / approximate |
| 顶栏警告 | ACCOUNTING `STALE`/`FAIL`、时钟、无 status 等优先于图表 |
| Health 表 | 列含 SSH / PROXY / ACCOUNTING / VERSION / CLOCK / LAST_SYNC |
| 默认页源码/界面 | **无** `vless://`、Reality 私钥、Clash secret、成批凭据倾倒 |
| 主导航 | **仅**三页；无独立「Users 管理 / Nodes 编辑」页 |

### C. Refresh / Sync（AC-3.1-10）

| 动作 | 期望 |
| --- | --- |
| **Refresh status** | 走 SSH status；更新 `last-status.json`；Health/Overview 重绘 |
| **Verify** | 走 verify（含时钟等）；写回 last-status |
| **Sync…** | 确认后普通 sync（写 `fleet.db`）；**不会**问 reseed。reseed 用 CLI |
| **Refresh users** | SSH `user list`；写 `users-cache.json`；Overview 用户表更新；仍无 URI |

无节点或 SSH 失败时：UI 应报错/toast，**不得**假装 mutation 成功。

### D. Audit（AC-3.1-05 / 08）

1. 打开 Audit：未搜时为空状态（提示先 Sync / 选时间窗）。
2. 填 **user**（tag 或 `user_id`）、**From** / **To**（RFC3339，带 `Z` 或偏移）。
3. 可选 node、destination 子串 → Search。
4. 结果列：time / node / dest / up·down（整数人可读）/ total。
5. 与 CLI 对照（同一窗口应同序同类行）：

```bat
bin\vcl-fleet.cmd audit user alice --from 2026-08-01T00:00:00Z --to 2026-08-19T00:00:00Z --json
```

### E. Drill-down（AC-3.1-04）

| 操作 | 期望 |
| --- | --- |
| Health 点节点行 | 抽屉：`node_id`、instance 时间线、endpoint、cursor；无 URI |
| Overview 点用户行 | 抽屉：tag、`user_id`、节点分配、credential **id**（可有）、近 7 日用量 |
| 抽屉「Open Audit」 | 跳转 Audit 并预填 user/node |

### F. CLI recipes 与 API 鉴权

1. 打开 **CLI recipes**；确认 `--reseed` 标为 CLI-only。
2. **Copy** 后粘贴到终端可执行；UI **本身不执行**这些命令。
3. 从页面源码取 `meta[name=vcl-ui-token]`，再测：

```bash
# 无 token → 401
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/api/meta
# 带 token 的 reseed body → 400
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8765/api/sync \
  -H "Content-Type: application/json" -H "X-Vincula-UI-Token: TOKEN" \
  -d '{"reseed":"lax"}'
# 带 token 的 mutation → 405
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8765/api/user/add \
  -H "Content-Type: application/json" -H "X-Vincula-UI-Token: TOKEN" -d "{}"
```

### G. 控制器 zip 黑盒（可选）

```bash
bash scripts/build-controller.sh
# 解压到临时目录后：
cd /path/to/vincula-controller-0.3.1-dev
sha256sum -c controller.lock
# 确认存在 lib/vincula-ui/static/index.html
env VCL_FLEET_HOME=/tmp/ui-zip-home python3 bin/vcl-fleet ui
```

Windows：解压 zip → `bin\vcl-fleet.cmd ui`（需本机 Python + OpenSSH）。

### H. 快速否决项（任一失败即手测不通过）

- 能绑在 `0.0.0.0` 或局域网 IP
- UI 能 add/rotate/retire/replace/restore/**reseed**
- 无 token / 错 Host 仍能打 `/api/*`
- 默认 Overview/Health 出现 VLESS URI 或私钥
- 只有两页或出现独立「管理台」编辑页
- 关掉 UI 后远端 sing-box/accountd 被停掉

### I. 手测通过后记一笔（建议）

在工作笔记或 PR 描述中记录：

- 日期、工作站 OS、控制器来源（源树 / zip 版本）
- `VCL_FLEET_HOME` 是否隔离
- 是否对真实 VPS 点过 Refresh/Sync（是/否）
- AC-3.1-01…11 勾选结果

自动化已覆盖的绑定拒绝与 API 子集：**不**替代本节浏览器手测，尤其是 Win11
`vcl-fleet.cmd ui` 与真实 SSH Refresh。