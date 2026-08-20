# vincula V0.3.1-rc2

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
| Accounting | schema **4**（`export_seq`）；raw 90 天 / daily 90 天 |

Gate / 已知限制：[`docs/release-readiness-0.3.1.md`](docs/release-readiness-0.3.1.md) · [`docs/known-issues-0.3.1.md`](docs/known-issues-0.3.1.md) · 命令手册：[`docs/manual.md`](docs/manual.md) · 备份：[`docs/backup.md`](docs/backup.md)  
历史冻结门禁：[`docs/legacy/`](docs/legacy/)

---

## 仓库结构

```text
vincula.sh                 # 安装 / 迁移入口
vincula-bootstrap.sh       # 从 URL 拉 tarball 安装
bin/vincula                # 节点运行时 CLI（安装为 vcl / vincula；无 fleet 子命令）
bin/vcl-fleet              # 工作站控制器（Unix）
bin/vcl-fleet.cmd          # 工作站控制器（Windows 11）
lib/                       # common / accountd / stats / audit / backup / fleet / unit / ui
lib/vincula-backup.py      # 备份格式 / verify / restore plan（stdlib）
lib/vincula-fleet.py       # 控制器实现（stdlib + 系统 OpenSSH）
lib/vincula-ui/            # Local Audit UI（stdlib HTTP + static；vcl-fleet ui）
scripts/
  build-release.sh         # 节点产物 dist/vincula-node-<ver>.tar.gz
  build-controller.sh      # 控制器产物 dist/vincula-controller-<ver>.zip
  gen-release-lock.sh      # 刷新节点 release.lock（9 个 first-party 文件）
  soak-0.2.7.sh            # LIVE-ONLY 24h soak 协议（不在 CI 跑）
  rc-*.sh                  # 远端 RC / 升级链测试
  freeze-*.sh              # 0.2.4 freeze 辅助（历史）
tests/test.sh              # 本地单元测试（source tests/test-fleet.sh）
.github/workflows/ci.yml   # merge gate（unit / concurrency / failure-injection / artifact）
docs/identity.md           # 身份合同
docs/fleet.md              # 控制器运维指南
docs/backup.md             # 备份 / restore / replace
docs/manual.md             # 全量命令手册（参数与用法）
docs/live-replace-checklist.md  # B14 live VPS 操作清单（PASS 2026-08-18）
docs/release-readiness-0.3.1.md # living-tree gate（NOT READY：缺 live 升级证据）
docs/known-issues-0.3.1.md      # living-tree 已知限制
docs/legacy/               # 历史 freeze / readiness / known-issues（只读）
dist/                      # 生成物（gitignore，勿手改）
```

源码以 **仓库根目录** 为准。节点部署只用 `scripts/build-release.sh` 生成的 `dist/vincula-node-<version>.tar.gz`；工作站控制器用 `scripts/build-controller.sh` 生成的 `dist/vincula-controller-<version>.zip`。不要手改 `dist/` 或旧 `release/`。

---

## 安装

### 1. 打发布包（开发机）

```bash
bash scripts/gen-release-lock.sh
bash scripts/build-release.sh
# → dist/vincula-node-<version>/  与  dist/vincula-node-<version>.tar.gz (+ .sha256)
bash scripts/build-controller.sh
# → dist/vincula-controller-<version>.zip (+ .sha256) 与 zip 内 controller.lock
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
lib/vincula-backup.py
lib/vincula-accountd.service
```

```bash
sha256sum -c vincula.sh.sha256
sudo bash vincula.sh
```

### 3. 可选：bootstrap 拉 tarball

生产必须带外部 pin（`RELEASE_SHA256` 或发布工程写入的 `EMBEDDED_RELEASE_SHA256`）。缺 pin 会直接拒绝。脚本还会拉 `${RELEASE_URL}.sha256`：pin、该文件、archive 三者必须一致。

从同一 URL 拉 `.sha256` **只能**发现传输损坏，**不能**发现源站把 tar 和 `.sha256` 一起换掉。生产必须把 digest 钉在环境变量 / 镜像 / embed 里，不要把兄弟 `.sha256` 当成 pin。

```bash
sudo env RELEASE_URL='https://example.com/vincula-node-<version>.tar.gz' \
  RELEASE_SHA256='...' \
  bash vincula-bootstrap.sh
```

非生产才允许 `--allow-insecure-sibling-digest`（无 pin 时用兄弟 `.sha256`）。不要在生产用。

**不支持** `curl | bash` 单文件安装（必须同目录有 `bin/` + `lib/`）。

工作站控制器是另一个产物（zip，无 installer / 无节点 `release.lock`）。zip 内有 `controller.lock`（各成员 sha256），旁边有 `vincula-controller-<ver>.zip.sha256`。解压后在 Windows 11 上跑 `bin\vcl-fleet.cmd`，在 Linux 上跑 `python3 bin/vcl-fleet`。需要本机 **Python 3.10+** 与 **系统 OpenSSH**。zip 含 `lib/vincula-ui/`（`vcl-fleet ui`）。运维步骤、host-key、user/sync/retire/replace、UI 与 AC-3.0/3.1 见 [`docs/fleet.md`](docs/fleet.md)；手测清单见 [`docs/manual.md#ui-manual-test`](docs/manual.md#ui-manual-test)。

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

每条命令的参数、退出码与例子：[`docs/manual.md`](docs/manual.md)。

### 节点

```bash
vcl info | status | check | verify | diagnose
vcl restart
vcl logs | vcl logs 200 | vcl logs -f
vcl link          # owner VLESS URI
vcl version
```

### 用户（0.2.5+；`--json` 为 0.2.9）

```bash
vcl user add alice --display-name "Alice" --department Sales
vcl user add alice --user-id UUID --json   # advanced/controller：注入 fleet-global user_id
vcl user set alice --display-name "Alice Chen" --department Eng
vcl user list
vcl user list --json
vcl user show alice
vcl user show alice --json
vcl user link alice
vcl user disable alice
vcl user disable alice --json
vcl user enable alice --json
vcl user rotate alice
vcl user rotate alice --json

vcl user import staff.csv --dry-run
vcl user import staff.csv --output credentials.csv   # 0600，含 URI
vcl user export --output users.csv
vcl user export --credentials --output credentials.csv
vcl user verify
```

导入 CSV 最少一列 `tag`，可选 `display_name,department`。全量校验后一次提交，失败则零变更。  
`user remove` / purge / delete **不支持**（请用 `disable`）。

仅会影响代理配置的用户变更才会 **restart sing-box**（连接可能短暂中断）；仅改 metadata 的 `user set` 不重启。

`--json`（CLI 合同 `schema_version` 1，不是 `users.json` schema）给控制器用：`list`/`show` **不含** VLESS uuid；`add`/`rotate` 的 URI 已含 uuid。`users.json` schema **仍为 2**。详见 [`docs/identity.md`](docs/identity.md)。

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

### 备份 / 恢复（0.3.0）

默认备份是 **secretless**（身份 + 审计 + accounting，不含 Reality 私钥 / VLESS uuid / Clash secret），**不**要求 age：

```bash
sudo vcl backup create
sudo vcl backup create --json
sudo vcl backup verify /var/backups/vincula/node-<node_id>-<UTC>.tar
sudo vcl restore FILE --server 203.0.113.18 --reissue-output /var/backups/vincula/reissue.csv
```

`vcl restore` 只接受 **fresh node**（无 `$STATE_DIR/VERSION`）。已安装则拒绝覆盖。没有 `--replace-node` 节点旗标。

含密钥备份必须 age（recipient 文件，不是口令）：

```bash
sudo vcl backup create --include-secrets --age-recipient /root/age-recipients.txt
sudo vcl backup verify FILE.tar.age --age-identity /root/age-identity.txt
sudo vcl restore FILE.tar.age --include-secrets --age-identity /root/age-identity.txt
```

缺 age：`ERROR: Secret-bearing backup requires age.`  
物理换机：`vcl-fleet node replace NAME --host NEW --host-key SHA256:…`。新机先
`sudo bash vincula.sh --runtime-only`（装运行时、**不**写 VERSION），再由控制器
`vcl restore FILE --reissue-output FILE --server HOST`。不要用 `node set` 冒充换机。
节点侧也可在 **runtime-only / fresh host** 上手动 `vcl restore FILE --reissue-output FILE`。
节点 **没有** `--replace-node` 旗标。夹具合同已对齐（B10）；**两台真 VPS live replace 已 PASS（B14，2026-08-18）**：
[`docs/live-replace-checklist.md`](docs/live-replace-checklist.md) · 证据 [`docs/evidence/0.3.1-live/SUMMARY.md`](docs/evidence/0.3.1-live/SUMMARY.md)。
格式、CSV、DR 清单：[`docs/backup.md`](docs/backup.md)。

### 卸载

```bash
vcl uninstall --yes
```

会删除 Vincula 拥有的资源（含 `accounting.db`）；历史流量数据不可恢复。无 `--force`。

---

## 身份

现有 UUID `node_id`（`state.json` `node.node_id` / `config.toml` `node_id` / `users.json` credentials / accounting）**就是逻辑节点 ID**，永久冻结。`name` 可改；改 IP / hostname **不**改 `node_id`。**禁止重铸**，也不引入第二套逻辑 ID。

`instance_id` 表示一次物理安装。单一事实来源（SoT）是 `state.json` 的 `node.instance_id`。升级 `0.2.7` → `0.2.8` 才为当前安装 mint；**禁止**把 `node_id` 复制进 `instance_id`。`0.2.8` → `0.2.9` → `0.3.0` → `0.3.1-rc2` 升级 **不**重 mint。重装/替换（`vcl restore` / `vcl-fleet node replace`）保留 `node_id`，新 mint `instance_id`。

Fleet-global `user_id`：节点本地 `vcl user add` 仍生成 UUID；控制器注入同一 `--user-id` 到每个节点。详见 [`docs/identity.md`](docs/identity.md)。

---

## Fleet Users & Audit（工作站控制器）

0.3.0+ 提供 **vcl-fleet**（SPEC 里的 `vcl fleet <sub>` ≡ `vcl-fleet <sub>`）。跑在管理员工作站上：无 root、无 systemd、无公网管理端口；用系统 OpenSSH 开通用户、增量同步审计、查询 stats、退役节点。**`node replace`** 走 runtime-only 新机上的真实 `vcl restore --reissue-output`。**0.3.1** 另有 localhost-only 只读 Local Audit UI：`vcl-fleet ui`（Overview / Audit / Health；突变仍走 CLI）。

节点 `vcl` **没有** `fleet` 子命令。完整 CLI、Windows 11 用法、`--host-key`、PARTIAL / `CURSOR_EXPIRED` / retire / replace / UI：[`docs/fleet.md`](docs/fleet.md)。命令手册与 **UI 手测清单**：[`docs/manual.md`](docs/manual.md#ui-manual-test)。

AC 夹具证据是 **fake-ssh 多节点**（lax + tokyo；replace 用 lax2）。**B14 live replace 已 PASS**（两台真 VPS + AC-3.0-11 + 真机 `age` + Win11 `vcl-fleet.cmd`）：[`docs/live-replace-checklist.md`](docs/live-replace-checklist.md) · [`docs/evidence/0.3.1-live/SUMMARY.md`](docs/evidence/0.3.1-live/SUMMARY.md)。发行建议仍是 **NOT READY**（剩余：live `0.3.0 → 0.3.1-rc2` upgrade + Schema 4 真机 re-sync）：
[`docs/release-readiness-0.3.1.md`](docs/release-readiness-0.3.1.md)。

```bash
python3 bin/vcl-fleet version
python3 bin/vcl-fleet init
python3 bin/vcl-fleet node add lax --host 203.0.113.10 --host-key SHA256:...
python3 bin/vcl-fleet status
python3 bin/vcl-fleet verify

python3 bin/vcl-fleet user add alice --nodes lax,tokyo --display-name Alice
python3 bin/vcl-fleet user list
python3 bin/vcl-fleet user rotate alice --node lax
python3 bin/vcl-fleet user disable alice --node lax   # --node 必填

python3 bin/vcl-fleet sync
python3 bin/vcl-fleet sync --reseed lax              # CURSOR_EXPIRED / unlabeled；不是 backup
python3 bin/vcl-fleet audit user alice --from 2026-08-10T00:00:00Z --to 2026-08-16T00:00:00Z
python3 bin/vcl-fleet stats user alice --days 7
python3 bin/vcl-fleet ui                             # http://127.0.0.1:8765 ；仅 loopback

python3 bin/vcl-fleet node set lax --host 203.0.113.10   # rebind：同一实例，凭据保留
python3 bin/vcl-fleet node replace lax --host 203.0.113.18 --host-key SHA256:...
python3 bin/vcl-fleet node instances lax
python3 bin/vcl-fleet node retire lax                 # 先 final sync，再标 retired；不删历史
```

---

## 升级

同机重跑安装器：

- 同版本：校验双平面，不轮换凭据
- `0.1.0`–`0.1.5` 或 `0.2.0`–`0.2.6` → **0.2.7**：保留 Reality / UUID / `user_id` / accounting DB
- `0.2.6` → `0.2.7`（accounting schema 2→3，不可逆）
- `0.2.7` → **0.2.8**：保留 `node_id`，mint `instance_id`；accounting schema 仍为 3
- `0.2.8` → **0.2.9**：保留 `user_id` / `node_id` / `instance_id`（不重 mint）；state/users/accounting schema 不变；工作站 `fleet.json` 1→2（加 `status`），新建 `fleet.db`
- `0.2.9` → **0.3.0**：保留 `user_id` / `node_id` / `instance_id`（不重 mint，不旋转 Reality）；state/users/accounting/`fleet.json` schema 不变；工作站 `fleet.db` 1→2（`instance_history`）；新 backup schema 1。`instance_id` 仅在 `vcl restore` / `vcl-fleet node replace` 时新 mint
- `0.3.0` → **0.3.1-rc2**：同架构 milestone；保留 `user_id` / `node_id` / `instance_id` / Reality（不重 mint、不旋转凭据）；accounting **schema 3→4**（开库迁移）。升级后每节点一次 `vcl-fleet sync --reseed NAME`。**真机升级证据尚未跑**（阻塞 READY FOR RC）

不支持降级或跳未知版本。Fresh install 若已有 `/var/lib/vincula` 会拒绝（先卸载）。

远端升级链实测（Debian 13，止于 0.2.6）：[`docs/legacy/rc-live-upgrade-0.2.4-0.2.6.md`](docs/legacy/rc-live-upgrade-0.2.4-0.2.6.md) · 证据 [`docs/evidence/0.2.4-0.2.6-live/SUMMARY.md`](docs/evidence/0.2.4-0.2.6-live/SUMMARY.md)

Live secretless replace / AC-3.0-11 / 真机 `age` / Win11 `vcl-fleet.cmd`：[`docs/live-replace-checklist.md`](docs/live-replace-checklist.md)（B14 **PASS** 2026-08-18；证据 [`docs/evidence/0.3.1-live/SUMMARY.md`](docs/evidence/0.3.1-live/SUMMARY.md)）。

```bash
# 编排机示例
export VCL_RC_HOST=x.x.x.x VCL_RC_USER=root VCL_RC_PASS='...' VCL_SERVER=$VCL_RC_HOST
bash scripts/rc-live-upgrade-driver.sh
```

---

## 开发与本地测试

```bash
bash -n vincula.sh bin/vincula lib/vincula-common.sh
python3 -m py_compile lib/vincula-accountd.py lib/vincula-stats.py lib/vincula-audit.py lib/vincula-backup.py lib/vincula-fleet.py
bash tests/test.sh
bash scripts/gen-release-lock.sh   # 改过节点 first-party 后必跑
bash scripts/build-release.sh      # vincula-node-<ver>.tar.gz
bash scripts/build-controller.sh   # vincula-controller-<ver>.zip
# 可选（需下载 pinned sing-box）：
VCL_INTEGRATION=1 bash tests/test.sh
```

Source of Truth：`state.json`（节点/REALITY）+ `users.json`（credential UUID）+ `config.toml`（设置）。由此生成 `config.json` / `owner.uri`。

---

## CI

Merge gate is GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). All jobs must be green to merge. The workflow does not use repository secrets.

| Job | What it runs |
| --- | --- |
| **unit** | Host `ubuntu-latest`: `bash tests/test.sh` (sources fleet). Debian 12 / Debian 13 containers run `tests/test.sh` with `python3` installed. Fleet tests are not run a second time as a standalone step (that doubled wall-clock under the 30-minute cap). No Ubuntu 26.04 runner is added until GitHub provides one; `ubuntu-latest` is the Ubuntu matrix entry. |
| **concurrency** | Fail-closed if B6 flock tests are missing, then `bash tests/test.sh` (parallel `user add` / lock busy). |
| **failure-injection** | `bash tests/test.sh`, which includes `VCL_RESTORE_FAIL_AFTER` (stage / install / health and later boundaries), P1-03 upgrade preflight injects, and P1-05 bad Clash envelopes. |
| **artifact** | `bash scripts/build-release.sh` and `bash scripts/build-controller.sh`; black-box unzip of `dist/vincula-controller-*.zip` with no repo `lib/`; `sha256sum --check` on the zip sidecar and `controller.lock`; node tarball listing + `release.lock`. |

Live `scripts/rc-live-upgrade-driver.sh` (real VPS / upgrade chain) stays **manual**. It is not a merge gate. Local `act` is optional and is not the CI source of truth. B14 live secretless replace is **PASS** ([`docs/evidence/0.3.1-live/SUMMARY.md`](docs/evidence/0.3.1-live/SUMMARY.md)); remaining manual gate is live `0.3.0 → 0.3.1-rc2` upgrade.

---

## 明确不做

Hysteria2/TUIC、公网 Web UI、订阅计费、HTTPS MITM、自动追 latest、Reliable/Billing-grade accounting、单文件 `curl|bash`、`vcl recover`、用户 purge/delete、tag rename。
（工作站 **localhost-only** Local Audit UI 已在 0.3.1：`vcl-fleet ui`。）
全新安装若发现残留路径会拒绝，并在报错中打印确切的 `rm -f` / `rmdir` 清理命令；仍然没有 `vcl recover`。
