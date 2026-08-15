# Vincula 0.2.4 — READY FOR RC 测试手册

面向把当前结论（`READY WITH DOCUMENTED LIMITATIONS`）推进到 **`READY FOR RC`** 的实机验收。  
配套：[`release-readiness-0.2.4.md`](release-readiness-0.2.4.md) · [`known-issues-0.2.4.md`](known-issues-0.2.4.md)。  
自动化基线：`bash tests/test.sh`（须全绿）。

**进度快照（2026-08-15）：** Debian 13 amd64 主路径 / R01–R02 / owner 记账 / user 生命周期 spot-check 已 PASS；其余见 known-issues。

**硬规则（与 Gate 一致）：**

- 未在真实环境执行的项只能标 `UNKNOWN`，不得写 `PASS`
- R01–R25 中若仍有**关键项** `UNKNOWN` / `FAIL` → **不得**给 `READY FOR RC`
- 最终结论只允许三选一：`READY FOR RC` | `READY WITH DOCUMENTED LIMITATIONS` | `NOT READY FOR RC`

---

## 0. 前置条件

### 0.1 环境

| 要求 | 说明 |
| --- | --- |
| OS 矩阵 | 至少：Debian 12 amd64、Ubuntu 22.04 amd64；理想再加 Debian 13 / Ubuntu 24.04；arm64 ≥ 1 台 |
| Root | 全部安装 / 迁移 / 故障注入以 `root` 执行 |
| 网络 | 可访问 GitHub releases（拉 pinned sing-box）、公网 IPv4 或显式 `VCL_SERVER=` |
| 客户端 | 一台能跑 VLESS+REALITY+vision 的客户端（或本机 self-test 之外再加外部客户端） |
| Python | 至少一台记录 `python3 --version`（Ubuntu 22.04 应为 3.10.x） |

### 0.2 待测制品

从干净 git tree 打出 release 目录（或 tarball）：

```text
vincula-0.2.4/
├── vincula.sh
├── vincula.sh.sha256
├── vincula-bootstrap.sh
├── release.lock
├── bin/vincula
└── lib/{vincula-common.sh,vincula-accountd.py,vincula-accountd.service,vincula-event.schema.json}
```

```bash
bash scripts/gen-release-lock.sh
sha256sum -c vincula.sh.sha256
bash -n vincula.sh bin/vincula lib/vincula-common.sh
python3 -m py_compile lib/vincula-accountd.py
bash tests/test.sh          # 期望 All N tests passed
```

### 0.3 记录模板（每条必填）

```text
ID:
Host: <os> <arch> <hostname>
Date:
Operator:
Status: PASS / FAIL / PARTIAL / UNKNOWN
Commands:
Output / evidence (paste or path to log):
Notes:
```

建议把所有证据存到 `evidence/0.2.4-rc/<host>/<ID>.txt`。

---

## 1. 自动化门禁（阻塞）

在开发机或 CI 先跑：

| Step | Command | Pass criteria |
| --- | --- | --- |
| A1 | `bash tests/test.sh` | 全部 PASS |
| A2 | `VCL_INTEGRATION=1 bash tests/test.sh`（可选但推荐） | 含官方 binary check / REALITY self-test 相关项 PASS |
| A3 | `bash scripts/gen-release-lock.sh` 后 `sha256sum -c` 对照 | lock 与文件一致 |

任一项 FAIL → 停止 RC 测试，修代码后再来。

---

## 2. Fresh-install 矩阵（阻塞）

对矩阵中**每一台**干净机（无 `/etc/vincula`、无 `sing-box.service`、无 `/var/lib/vincula`）：

### 2.1 安装

```bash
cd /path/to/vincula-0.2.4
sha256sum -c vincula.sh.sha256
sudo bash vincula.sh
# 或：sudo env VCL_SERVER=... VCL_PORT=443 bash vincula.sh
```

**Pass：**

- 退出码 0
- 输出含 `✓ sing-box.service active` 与 `✓ vincula-accountd.service active`
- `cat /etc/vincula/VERSION` → `0.2.4`
- `jq -r .node.node_id /etc/vincula/state.json` 为 UUID（非 `local`）
- `grep -E 'node_id|owner' /etc/vincula/state.json`：有 `node_id`，**无** `owner.uuid`
- `sqlite3 /var/lib/vincula/accounting.db "SELECT value FROM meta WHERE key='schema_version';"` → `2`

### 2.2 双平面 verify

```bash
sudo bash vincula.sh          # 同版本重跑
sudo vcl verify
sudo vcl status
sudo vcl accounting status
```

**Pass：** `[Proxy Plane]` / `[Accounting Plane]` 全绿；`vcl verify` 退出 0。

### 2.3 Clash API 暴露与鉴权（R01 / R02）

```bash
ss -ltnp | tee /tmp/vcl-ss.txt
# 期望：*:443（或所选端口）由 sing-box；127.0.0.1:9090（或 clash_api_port）由 sing-box
# 禁止：0.0.0.0:9090 或 :::9090 上的 clash

SECRET=$(grep '^clash_api_secret' /etc/vincula/config.toml | cut -d'"' -f2)
PORT=$(grep '^clash_api_port' /etc/vincula/config.toml | awk '{print $3}')

# 无 secret → 必须失败
curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/connections" && echo FAIL_OPEN || echo OK_NO_SECRET

# 错 secret → 必须失败
curl -fsS --max-time 5 -H "Authorization: Bearer wrong" \
  "http://127.0.0.1:${PORT}/connections" && echo FAIL_WRONG || echo OK_WRONG

# 正确 secret → 必须成功
curl -fsS --max-time 5 -H "Authorization: Bearer ${SECRET}" \
  "http://127.0.0.1:${PORT}/connections" | head -c 200; echo
```

**Pass：** 仅 localhost 绑定；无/错 secret 失败；正确 secret 成功。

### 2.4 客户端与 accounting 主路径（R03 / R04 / R14 声明）

```bash
sudo vcl user add alice --display-name Alice --department eng
sudo vcl user link alice   # 导入客户端
# 用 alice 产生若干分钟真实流量后：
sudo vcl connections
sudo vcl stats today
sudo vcl stats user alice --today --top 20
```

**Pass：**

- SQLite 行含稳定 `user_id`（可用 `sqlite3` 查 `connections`）
- `user_tag` 可为 `alice`；rotate 后历史仍挂同一 `user_id`（见 §4）
- 文档/输出不宣称 Reliable / 精确计费

### 2.5 卸载 / 干净重装（R23）

```bash
sudo vcl uninstall --yes
# 确认文案含 historical accounting data will be permanently removed
test ! -e /var/lib/vincula/accounting.db
sudo bash /path/to/vincula-0.2.4/vincula.sh
```

**Pass：** 卸载后无遗留 managed 文件（或仅合法保留项）；可再次 fresh install。

### 2.6 OS 勾选表

| OS | arch | Fresh install | Verify | R01/R02 ss+curl | Client+stats | Uninstall+reinstall | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Debian 12 | amd64 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| Ubuntu 22.04 | amd64 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| Debian 13 | amd64 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| Ubuntu 24.04 | amd64 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| （任选） | arm64 | ☐ | ☐ | ☐ | ☐ | ☐ | |

**RC 最低线：** Debian 12 amd64 + Ubuntu 22.04 amd64 两行全 PASS；其余未跑标 UNKNOWN 并写入报告“覆盖缺口”。若关键 OS 标 UNKNOWN → 不能 `READY FOR RC`。

---

## 3. Migration 验收（阻塞）

至少覆盖：

| From | To | Host |
| --- | --- | --- |
| 0.1.5 | 0.2.4 | 一台 |
| 0.2.0 或 0.2.2 | 0.2.4 | 一台 |
| 0.2.3 | 0.2.4 | 一台（有 accounting.db 更佳） |

### 3.1 Happy path

记录迁移前：

```bash
OWNER_UUID=$(jq -r '.users[] | select(.tag=="owner") | .credentials[-1].uuid' /etc/vincula/users.json 2>/dev/null || true)
# 0.1.x 可能路径不同：按当时 SoT 记录 UUID / reality public key / short_id
REALITY_PK=$(jq -r .node.reality_public_key /etc/vincula/state.json)
SHORT=$(jq -r .node.reality_short_id /etc/vincula/state.json)
cp -a /var/lib/vincula/accounting.db /tmp/acct-before.db 2>/dev/null || true
```

```bash
sudo bash /path/to/vincula-0.2.4/vincula.sh
```

**Pass：**

- UUID / Reality keypair / short_id 保持
- `node_id` 为 UUID（若旧为 `local`/缺失则新生成且之后稳定）
- `sing-box` + `vincula-accountd` active；`schema_version=2`
- 旧 accounting 行仍在（若有）；`user_id` 已回填
- `vcl verify` PASS

### 3.2 Forced failure → rollback（P0-3）

在 migration 提交前制造失败（示例：备份后、commit 前）：

```bash
# 示例：临时破坏 accountd 使其 health 失败（具体注入点见 §5 F03/F04）
# 期望：非零退出；旧 VERSION / config / DB 恢复；旧服务可再 active
```

**Pass：**

- `/var/backups/vincula/...` 存在完整 accounting 备份
- 回滚后旧版本可 `systemctl is-active sing-box`（及旧 accountd 若有）
- **无** core=新 / accountd=旧 的 mixed-version 残留

至少 **一次** forced rollback PASS 才可申请 RC。

---

## 4. 身份与连续性（R05 / R06 / F14 / F15）

在已安装 0.2.4 节点上：

```bash
# R05 / F14
sudo vcl stats user alice --days 7 | tee /tmp/before-rotate.txt
sudo vcl user rotate alice
# 旧 UUID 客户端应连不上；新 link 可连
sudo vcl user link alice
# 再产生流量
sudo vcl stats user alice --days 7 | tee /tmp/after-rotate.txt
sqlite3 /var/lib/vincula/accounting.db \
  "SELECT user_id, SUM(upload_bytes+download_bytes) FROM connections WHERE user_tag='alice' GROUP BY 1;"
```

**Pass：** 同一 `user_id` 上 A+B 流量合计连续；inbound 仅新 UUID。

```bash
# R06 / F15
sudo vcl user disable alice
# 客户端重连必须失败
sudo vcl stats user alice --days 7   # 历史仍在
sudo vcl user enable alice
```

**Pass：** disable 后连接失败；历史统计不消失。

---

## 5. 故障注入 F01–F15（阻塞核心项）

在**可丢弃**的测试机上执行。每项记录 expected vs actual。

| ID | 注入方法（建议） | Expected | 记录 |
| --- | --- | --- | --- |
| F01 | 安装前把 staged 树中 `lib/vincula-accountd.py` 改成语法错误再 `bash vincula.sh` | `py_compile`/validate 失败；不 commit | ☐ |
| F02 | 破坏 `lib/vincula-accountd.service`（非法 directive）后安装 | `systemd-analyze verify` 或 enable 失败；不 commit | ☐ |
| F03 | `systemctl mask vincula-accountd.service` 后重跑 enable 路径 / 或 install 中途 mask | die；rollback | ☐ |
| F04 | install 末段前 `systemctl stop sing-box` 使 Clash 不可达 | health 失败；不 commit / rollback | ☐ |
| F05 | 手改 `clash_api_secret` 与 config 不一致后 `wait`/`verify` | auth 失败 | ☐ |
| F06 | `sudo mkdir -p /var/lib/vincula; sudo touch /var/lib/vincula/accounting.db` 后 fresh `vincula.sh` | preflight die | ☐ |
| F07 | 0.2.3（有 DB）→ 0.2.4 | DB 备份存在；schema→2；数据可查 | ☐ |
| F08 | 造一张仅有未知 `user_tag`、无对应用户的旧 DB，再启动 accountd | fail-closed；不抹库 | ☐ |
| F09 | migration 中 `kill -TERM` 主 installer PID（`INSTALL_COMMITTED=0` 时） | `rollback_migration`；旧版可用 | ☐ |
| F10 | 有活跃流量时 `systemctl restart vincula-accountd` | 不把已有 counter 当全量增量（基线） | ☐ |
| F11 | 有活跃流量时 `systemctl restart sing-box` | 无负 delta / 无天文数字 | ☐ |
| F12 | 将 `/var/lib/vincula` 放到小 loop 文件系统写满，或 `chmod a-w` DB | 明确报错；不静默“成功” | ☐ |
| F13 | `echo garbage \| sudo tee /var/lib/vincula/accounting.db` 后 restart accountd | 拒绝启动；日志含 corrupt；不重建空库吞历史 | ☐ |
| F14 | 见 §4 rotate | 历史按 `user_id` 连续 | ☐ |
| F15 | 见 §4 disable | 重连失败；历史保留 | ☐ |

**RC 最低线：** F01–F08、F10–F11、F13–F15 必须 PASS；F09/F12 强烈建议 PASS，若跳过须在报告标 UNKNOWN 并说明为何不阻塞（默认：**阻塞**）。

---

## 6. 其余 R 项速查

| ID | 实机动作 | Pass criteria |
| --- | --- | --- |
| R07 | Ubuntu 22.04：`python3 --version`；`python3 -m py_compile /usr/local/lib/vincula/vincula-accountd.py` | 3.10.x + compile OK |
| R08 | `systemctl show -p User vincula-accountd`；说明 root 原因 | User=root；DB/settings 0600 可访问 |
| R09 | `systemd-analyze security vincula-accountd.service` 存档 | ProtectSystem/Home、NoNewPrivileges、PrivateTmp、CapabilityBoundingSet、ReadWritePaths 符合 unit |
| R10 | 代码已举证；实机可 `PRAGMA journal_mode` | WAL 等已启用 |
| R11–R13 | 见 F10/F11 + 可选 sqlite 抽样 | 无重复全量 / 无负值 |
| R14 | 可选：&lt;1s/1s/2s/5s 短连接抽样 | 允许漏记；报告写明 approximate |
| R15–R18 | 跨午夜 / IP-only / `GitHub.com.` 归一 | 符合 UTC / NULL host / lowercase |
| R19 | 见 F12 | 明确失败 |
| R20 | 见 F13 | fail-closed |
| R21 | 大 DB 时观察 retention tick | 不长期阻塞 collector（可 PARTIAL） |
| R22 | `meta.schema_version` | 显式版本，非无限 CREATE IF NOT EXISTS |
| R23 | 见 §2.5 | 文案 + 删除 DB |
| R24 | `systemctl stop vincula-accountd; vcl stats today` | stderr 含 unavailable/stale 警告 |
| R25 | 确认 schema 文件存在；知悉运行时非 jsonschema 强制 | 文档诚实即可（PARTIAL 可接受，不宣称 runtime enforce） |

---

## 7. Packaging / bootstrap（推荐阻塞）

```bash
# 在构建机
tar czf vincula-0.2.4.tar.gz vincula.sh vincula-bootstrap.sh release.lock vincula.sh.sha256 bin lib
sha256sum vincula-0.2.4.tar.gz | tee vincula-0.2.4.tar.gz.sha256

# 在干净机
sudo env RELEASE_URL='file:///path/vincula-0.2.4.tar.gz' \
  RELEASE_SHA256='<hash>' \
  bash vincula-bootstrap.sh
```

**Pass：** archive 校验失败则拒绝；`release.lock` 单文件 mismatch 则拒绝；成功则进入正常 install。

篡改测试：改 `lib/vincula-accountd.py` 一字节后带 lock 安装 → 必须 die。

---

## 8. Reboot / 恢复

```bash
sudo reboot
# 回来后：
sudo vcl status
sudo vcl verify
sudo vcl accounting status
```

**Pass：** 双服务自动起来；verify PASS；`last_success_at` 在阈值内恢复。

---

## 9. RC 签字清单

全部勾选后，更新 `docs/release-readiness-0.2.4.md`（或追加日期附录），并把结论改为三者之一。

| Gate | Done |
| --- | --- |
| 自动化 `tests/test.sh` 全绿 | ☐ |
| Fresh-install 最低 OS 矩阵 PASS | ☐ |
| Migration ≥3 路径 PASS + 1× forced rollback PASS | ☐ |
| R01/R02 实机 ss + curl 三元组 PASS | ☐ |
| R05/R06（rotate/disable）PASS | ☐ |
| F01–F15 按 §5 最低线 PASS | ☐ |
| R07 Python 3.10 实机 PASS | ☐ |
| R09 `systemd-analyze security` 已存档 | ☐ |
| R24 stale 警告 PASS | ☐ |
| Packaging/bootstrap 篡改拒绝 PASS | ☐ |
| Reboot 后双平面 PASS | ☐ |
| 已知限制仍文档化（approximate accounting 等） | ☐ |

**仅当上表无关键 UNKNOWN/FAIL 时：**

```text
Release recommendation: READY FOR RC
```

否则保持：

```text
READY WITH DOCUMENTED LIMITATIONS
```

或：

```text
NOT READY FOR RC
```

并列出阻塞 ID。

---

## 10. 快速命令备忘

```bash
# 版本与服务
cat /etc/vincula/VERSION
systemctl is-active sing-box vincula-accountd
vcl verify
vcl accounting status

# Clash
grep clash_api /etc/vincula/config.toml
ss -ltnp | grep -E '443|9090'

# DB
sqlite3 /var/lib/vincula/accounting.db "SELECT * FROM meta;"
sqlite3 /var/lib/vincula/accounting.db "PRAGMA journal_mode; PRAGMA foreign_keys;"

# 安全
systemd-analyze verify /etc/systemd/system/vincula-accountd.service
systemd-analyze security vincula-accountd.service

# 日志
journalctl -u sing-box -u vincula-accountd -n 100 --no-pager
```
