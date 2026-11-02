# Vincula 代码审查（2026-10-26）

> 归档自 `tmp/code-review-2026-10-26.md`（2026-11-02）。审查对象为 `75071d8`；以下 R-01～R-16 均为**未修**问题，尚未排期。R-01/R-02 为 P1 记账时间语义问题；R-04/R-13 属凭据/身份范围，留给下一轮独立 SPEC 一并处理。


- 审查对象：`HEAD 75071d8`（2026-10-16，`docs(evidence): add a node journal exporter…`），工作树除未跟踪的 `sshkey.temp.epicfury` 外干净
- 审查日期：2026-10-26
- 方法：静态阅读 + 在控制器（Kali WSL，0.5.3）与生产节点（epicfury / urgentfury）上的**只读**动态验证；未修改、未提交任何代码
- 范围：`vincula.sh`、`bin/vincula`、`lib/vincula-fleet.py`、`lib/vincula-accountd.py`、`lib/vincula-audit.py`、`lib/vincula-stats.py`、`lib/vincula-backup.py`、`docs/evidence/0.5.3/tools/export-node-logs.sh`、`tests/`、`.github/workflows/ci.yml`
- 未覆盖：`lib/vincula-ui/` 前端、`scripts/` 构建链、live 升级/替换的端到端演练；`lib/vincula-fleet.py` 为定向审查（sync / 凭据 / 节点生命周期 / SQLite），未做逐函数通读

**严重度**：P1 = 数据正确性 / 静默丢数据；P2 = 运维误判或必须绕过受管路径；P3 = 工具与测试缺陷。

| ID | 严重度 | 主题 | 位置 |
| --- | --- | --- | --- |
| R-01 | P1 | `started_at` 保留本地时区偏移，日聚合与审计窗口错位 | `vincula-accountd.py:628-632,670,1366`、`vincula-audit.py:76,86` |
| R-02 | P1 | `daily_usage` 只从 `connections` 重建，raw 保留期一过日汇总即被删 | `vincula-accountd.py:1364-1379,1414-1426,1490-1517,1993-1998` |
| R-03 | P2 | 已装节点无法用受支持方式改端口/SNI，重跑安装脚本静默不生效 | `vincula.sh:2064-2077` |
| R-04 | P2 | `node replace --identity-file` 静默清空 observe 凭据引用 | `vincula-fleet.py:3112-3122,2999-3016` |
| R-05 | P2 | `backup verify` 对 `restore` 会拒绝的归档返回 OK | `vincula-backup.py:83,744-763,1745-1748` |
| R-06 | P2 | 无法解析 tag 的活跃连接被判为已关闭：字节丢失 + 连接重复计数 | `vincula-accountd.py:611-615,1951-1955` |
| R-07 | P2 | 控制器缓存库无修剪/压缩，长期无限增长 | `vincula-fleet.py:868-871,2025` |
| R-08 | P2 | `vcl diagnose` 在 `short_id` 为空时误报 REALITY 自检失败 | `bin/vincula:1482-1487` |
| R-09 | P3 | 日志导出脚本仓库路径推算错误，开箱即不可用 | `export-node-logs.sh:49-50` |
| R-10 | P3 | 导出清单里的 reimport 提示不可执行 | `export-node-logs.sh:187-190` |
| R-11 | P3 | `vincula-stats` 在错误路径创建空库并以 0 退出 | `vincula-stats.py:216-219,324-327` |
| R-12 | P3 | 非 root 用户跑测试套件固定 2 项失败，用例未跳过 | `tests/test_verify_extended.py:67,254` |
| R-13 | P2 | REALITY 私钥与 Clash secret 通过进程参数传递，本机其他用户可读 | `vincula-common.sh:346-356,440-442,1459-1461` |
| R-14 | P3 | runtime-only 安装无法用 `vcl uninstall` 卸载，也没有其他受支持拆除路径 | `bin/vincula:527-537`、`vincula.sh:2304-2312` |
| R-15 | P3 | 重跑安装器时"Clash API authentication ✓"只做正例，不做负例 | `vincula.sh:2017-2020,2047,2231-2237` |
| R-16 | P3 | VERSION 匹配的"verified"路径不做身份/凭据一致性校验 | `vincula.sh:1950-2062`、`bin/vincula:1185-1190` |

**结论摘要**：两条 P1 都落在记账时间语义上——入库时间戳保留本地偏移（R-01），以及日汇总无法独立于原始连接留存（R-02）。这两条不会让服务宕机，但会让"日用量"和"审计区间"在非 UTC 节点上系统性偏差，且现有测试夹具全用 `Z`，覆盖不到。P2 集中在运维与凭据：改端口没有受支持入口（R-03）、替换后 observe 凭据静默消失（R-04）、备份预检与恢复准入不一致（R-05）、缓存库无界增长（R-07）、私钥/secret 走 argv（R-13）。

测试基线：`python3 -m unittest discover -s tests -p 'test_*.py'` 共 155 项，普通用户下 2 失败 8 跳过（见 R-12）；`bash -n` 与 `py_compile` 均通过。

---

## R-01 `started_at` 不是 UTC：日聚合与审计窗口静默错位（P1）

**位置**
- `lib/vincula-accountd.py:628-632`：`started = item.get("start") or utc_now_iso()`，只有 `int`/`float` 会被转成 UTC 字符串
- `lib/vincula-accountd.py:670`：原样写入 `started_at`
- `lib/vincula-accountd.py:1366`：`substr(COALESCE(closed_at, started_at), 1, 10) AS date`
- `lib/vincula-audit.py:76`：查询边界格式化为 `...Z`；`:86` 与 `:246` 用字符串比较 / 排序
- `lib/vincula-accountd.service`：没有固定 `TZ`

**现象**
Clash API 的 `start` 是 Go `time.Time` 序列化结果，带本机时区偏移（例如 `2026-10-26T02:39:54-07:00`）。字符串被原样存库，于是：
1. `daily_usage` 的 `date` 是**本地日期**，不是契约要求的 UTC 日期；
2. `audit` 的区间谓词 `started_at < '2026-10-25T18:00:00Z'` 是字典序比较，带 `-07:00` 的行会被错误地判在窗口之外；
3. 相同的 `substr(started_at,1,10)` 也出现在控制器 `lib/vincula-fleet.py:1379,1399`，会把本地日期传播到 fleet 侧 `daily_usage`。

**证据（已在生产节点实测）**
epicfury（PDT，`-07:00`）：
```
date → Mon Oct 26 02:40:01 AM PDT 2026
stored started_at 样本 → 2026-10-26T02:39:54.873626082-07:00
distinct suffixes → [('-07:00', 895929)]   # 全部 89.6 万行
clash live start → ['2026-10-26T02:37:19.444218947-07:00', ...]
daily dates → 2026-10-26 / 2026-10-25 / ...
```
同一时刻 UTC 为 `09:40`，而这些行被记到 `10-26` 的本地日。

**复现路径**
```bash
# 在任意非 UTC 节点上
python3 - <<'PY'
import sqlite3
c=sqlite3.connect('file:/var/lib/vincula/accounting.db?mode=ro',uri=True)
print(c.execute("select substr(started_at,-6), count(*) from connections group by 1").fetchall())
PY
# 期望：'Z'（UTC）；实际：类似 '-07:00' / '+08:00'
```
再用该节点导出的审计做区间查询，跨 UTC 日界的连接会缺失。

**影响**：日用量按本地日切分（对 `-07:00` 节点整体偏 7 小时）；跨日边界的审计记录在 `vcl audit` / fleet `stats` 中丢失或在错误日期出现。测试夹具只用 `...Z`（`tests/test.sh:3268`），所以套件发现不了。

**置信度**：代码缺陷高；生产载荷带偏移已在 epicfury 实测确认。

---

## R-02 `daily_usage` 无法比 raw 数据活得更久（P1）

**位置**
- `lib/vincula-accountd.py:1364-1379`：`_DAILY_USAGE_AGGREGATE_SELECT` 只从 `connections` 聚合
- `:1414-1426`：每轮 rollup `DELETE FROM daily_usage` 后从 `daily_usage_rebuild` 重插
- `:1490-1517`：raw 行按 `last_seen_at < cutoff` 删除
- `:1993-1998`：同一维护 tick 先 rollup、后 retention

**现象**
`daily_usage` 没有独立历史：每次 rollup 都整表重建，数据源只剩尚未被 raw 保留期删掉的 `connections`。因此：
- 配置 `raw=7d / daily=365d` 时，第 8 天那次 rollup 会把 7 天前的日汇总一起清掉；
- 即使默认 90/90，边界日也会因为 raw 按 `last_seen_at` 删、daily 按 `date` 删而提前一天归零。

Spec 明确允许两者独立设置并保留 `365/180/30` 等显式值（`docs/specs/V0.2.7-V0.3.1_spec.md:607-621,2686`），所以这不是预期行为。

**复现路径**
```bash
# 临时库，使用模块自带 SCHEMA_SQL
insert 一条 closed 连接，started_at=2026-10-23，100/200 字节
rollup_daily_usage(conn)                      # daily_usage = ('2026-10-23',100,200)
apply_retention(conn, raw_days=1, daily_days=365)
rollup_daily_usage(conn)                      # daily_usage 变空
```
实测输出：`raw rows left: 0` / `daily rows after next rollup (daily retention 365d): []`。

**影响**：把 daily 保留期设长于 raw 的运维意图完全失效，历史日汇总静默丢失。

**置信度**：高（代码路径 + 实跑复现）。

---

## R-03 已装节点无法通过受支持方式修改端口/SNI（P2）

**位置**：`vincula.sh:2064-2077`
```bash
handle_existing_install() {
  if [[ "$installed_project_version" == "$VINCULA_VERSION" ]]; then
    verify_existing_install      # 只校验，不重渲染
    return
  fi
```

**现象**
`VCL_PORT` / `VCL_REALITY_HOST` / `VCL_SERVER` 只在新装或版本迁移路径生效。同版本重跑安装脚本只做 dual-plane 校验，**不会**读取新的环境变量去重写 `config.toml` / `config.json`。`docs/` 中也没有任何"安装后改端口"的说明（全仓 grep `VCL_PORT` 只命中脚本自身注释）。

**复现路径**
```bash
# 在已装 0.3.2 的节点上
sudo VCL_PORT=443 VCL_REALITY_HOST=www.apple.com bash vincula.sh
# 输出以 "Existing vincula 0.3.2 installation verified; credentials preserved" 结束
grep '^port' /etc/vincula/config.toml   # 仍是旧端口
```
本次生产切换就是撞上这一点，最终只能手改 `config.toml` 再借 `vcl user add` 触发的重渲染落地——这是一条未文档化的隐式路径。

**影响**：运维会误以为配置已生效；端口封锁等场景下无法用受支持命令恢复，只能手改受管文件。

**置信度**：高（代码路径 + 本次实操）。

---

## R-04 `node replace --identity-file` 静默清空 observe 引用（P2）

**位置**
- `lib/vincula-fleet.py:3112-3122`：`new_node.pop("observe_credential_ref", None)`，注释写明"observe must be set explicitly after replace if needed"
- `lib/vincula-fleet.py:2999-3016`：`_emit_replace_result` 只输出 name / instance / ssh_host / reissue_csv，没有任何提示

**现象**
带 `--identity-file` 执行替换时，新节点记录会拿到新的 admin 引用，同时丢掉 observe 引用；命令成功返回且不提示。此后任何 observe 类操作都会**直接失败**：`lib/access.py:386-390` 规定"已有 admin 引用但无 observe 引用"时 `die("observe credential not configured for node")`。受影响命令包括 `verify --extended`（`lib/vincula-fleet.py:4190` 以 observe 类执行 `vcl verify`）、`telemetry`、`monitor`。

**复现路径**
```bash
vcl-fleet node show NODE            # observe_credential_ref=<ref>
vcl-fleet node replace NODE --host NEW --host-key SHA256:... --identity-file ~/.ssh/newkey
vcl-fleet node show NODE            # observe_credential_ref=-（无任何警告）
vcl-fleet verify --extended --name NODE   # die: observe credential not configured for node
```

**影响**：替换后监控与扩展校验静默失效，直到有人重新 `node set --observe-credential-ref`。

**置信度**：高（代码路径明确；未在 live 上执行替换）。

---

## R-05 `backup verify` 与 `restore` 的准入条件不一致（P2）

**位置**
- `lib/vincula-backup.py:83`：`REQUIRED_COMPONENTS = ("state.json", "users.json", "config.toml")` —— 全仓仅此一处，从未被引用
- `:744-763`：`_verify_members` 只校验 manifest schema、加密标志一致性、`files` 与 tar 成员集合相等
- `:1745-1748`：restore 直接 `members["users.json"]`，缺文件抛 `KeyError` → `invalid_archive`

**现象**
缺少 `users.json`（或 `state.json`）的归档可以通过 `verify` 并打印 `Backup OK`、退出 0，但真正 `restore` 到新机时才失败。`create_backup` 不会产出这种归档，所以受害面是截断包/第三方归档——正是校验要覆盖的场景。

**复现路径**
```bash
# 构造 manifest：included_components=["state.json"]，files 与 tar 成员一致，sha256 正确
python3 -c '...write_tar(...)'
python3 lib/vincula-backup.py verify ARCHIVE      # exit 0, ok=True
# 同一 ARCHIVE 走 restore → invalid_archive: 'users.json'
```

**影响**：预检失去意义；故障延迟到换机现场才暴露。

**置信度**：高（实跑 verify 返回 ok=True）。

---

## R-06 无法解析 tag 的活跃连接被强制关闭（P2）

**位置**
- `lib/vincula-accountd.py:611-615`：`resolve_user_id` 失败时 `parse_clash_connection` 返回 `None`
- `:1951-1955`：`live_ids = [ev["connection_id"] for ev in live]`，`live` 是**已解析**的列表
- `:1252-1263`：`apply_poll_delta` 把不在 `live_map` 里的跟踪连接标记 closed
- `:1069-1075` 的告警要求调用方不得在快照非权威时传空 live 集，但过滤发生在其上游

**现象**
某连接仍在 Clash 中传输，但 `users.json` 暂时解析不到它的 tag（例如用户在 provisioning 中、或 outbound 残留）时：
1. 该连接被写入 `closed_at`，盲窗期间的字节不再计入；
2. tag 恢复后它被当成新一代连接重新开基线，`connection_count` 重复计一次。

**复现路径**
```
poll: {"id":"c1","upload":500,"chains":["acct/alice"]}，TAG_TO_USER_ID={}
→ 行 (gen 0, closed, 0)
恢复映射后再 poll upload=900
→ 行 [(0, closed, 0), (1, open, 0)]；900 字节中 0 被记账
```

**影响**：计费/统计少记且连接数虚高；触发条件需要 users.json 与 sing-box 短暂不一致。

**置信度**：中（代码路径已确认，触发条件依赖运行时状态）。

---

## R-07 控制器缓存库无修剪/压缩（P2）

**位置**
- `lib/vincula-fleet.py:868-871`：`journal_mode=DELETE`、`synchronous=NORMAL`，无 `VACUUM`
- `:2025`：唯一的 `DELETE FROM audit_events` 在 `--reseed` 里，按节点整体清空
- 无任何按时间/条数修剪 `audit_events` / `daily_usage` 的命令

**现象**
`fleet.db` 只增不减，`--reseed` 是唯一删数据的手段（且清空该节点全部历史）。本次 12 天积压同步后：

| 指标 | 值 |
| --- | --- |
| `audit_events` | 5,843,602 行 |
| `fleet.db` | 2.9 GB |
| 可用磁盘 | 937 GB |

**复现路径**
```bash
# 反复执行全量同步，观察库大小
du -h ~/.local/state/vincula/<fleet_id>/fleet.db
python3 - <<'PY'
import sqlite3; c=sqlite3.connect('file:...fleet.db?mode=ro',uri=True)
print(c.execute('select count(*) from audit_events').fetchone())
PY
```
没有任何 CLI 能在不丢整节点历史的前提下缩减它。

**影响**：磁盘、备份体积、UI/查询延迟随运行时间线性增长；`DELETE` 模式删除后不归还空间。

**置信度**：高（实测 2.9 GB；代码无修剪路径）。

---

## R-08 `vcl diagnose` 在空 `short_id` 时误报 REALITY 失败（P2）

**位置**：`bin/vincula:1482-1487`
```bash
if [[ -n "$uuid" && -n "$private_key" && -n "$public_key" && -n "$short_id" && -n "$reality_host" ]] \
  && run_reality_self_test ...; then
  diag_ok "REALITY end-to-end self-test"
else
  diag_fail "REALITY end-to-end self-test"
fi
```

**现象**
`short_id` 为空是合法配置（URI 里 `sid=`），但自检用 `-n "$short_id"` 作为前置条件；条件不满足时自检根本没跑，却被记为 `✗`，最终 `Overall: FAIL`。

**复现路径**
```bash
# urgentfury：reality_short_id = ""
vcl diagnose | tail -6
# ✗ REALITY end-to-end self-test  /  Overall: FAIL
openssl s_client -connect 69.63.198.51:443 -servername www.apple.com </dev/null \
  | openssl x509 -noout -subject   # 返回真实 Apple 证书，说明 REALITY 正常
```

**影响**：健康节点被判红，运维可能据此做不必要的"修复"。

**置信度**：高（代码 + 本次实测）。

---

## R-09 日志导出脚本的仓库路径推算错误（P3）

**位置**：`docs/evidence/0.5.3/tools/export-node-logs.sh:49-50`
```bash
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
FLEET=${VCL_FLEET_BIN:-$REPO/bin/vcl-fleet}
```
脚本位于 `docs/evidence/0.5.3/tools/`，`../../..` 得到的是 `docs/`，因此默认路径是 `docs/bin/vcl-fleet`。

**复现路径**
```bash
bash docs/evidence/0.5.3/tools/export-node-logs.sh NODE --dry-run
# missing vcl-fleet: <repo>/docs/bin/vcl-fleet
```
必须显式 `VCL_FLEET_BIN=<repo>/bin/vcl-fleet` 才能用。

**影响**：随文档交付的采集器开箱即失败，现场取证时容易误判为环境问题。

**置信度**：高（本次实操）。

---

## R-10 导出清单的 reimport 提示不可执行（P3）

**位置**：`docs/evidence/0.5.3/tools/export-node-logs.sh:187-190`
```bash
echo "reimport_hint=journalctl --no-pager -o short-iso < zcat $OUT/journal-short-iso.txt.gz"
```
`< zcat ...` 不是合法的重定向；且 `journal-export.gz` 是 `-o export` 文本流，不能直接 `journalctl --file` 读取，需 `systemd-journal-remote` 转换。

**复现路径**
```bash
cat node-logs-*/MANIFEST.txt
# 按提示执行 → "zcat: No such file or directory" 或语法错误
```

**影响**：取证包的可复现性说明失真（低）。

**置信度**：高（本次已实测 `< zcat` 与 `journalctl --file` 均失败）。

---

## R-11 `vincula-stats` 在错误路径建库并成功退出（P3）

**位置**：`lib/vincula-stats.py:216-219`（`sqlite3.connect(path)` 无 `mode=ro`、无存在性检查）、`:324-327`（缺表只打一条 stderr 后 `SystemExit(0)`）

**现象**
路径写错时 SQLite 会创建空文件，命令打印一行提示后以 0 退出。只检查退出码的调用方会把"空报告"当作成功。

**复现路径**
```bash
python3 lib/vincula-stats.py --db /tmp/typo/missing.db --users /dev/null --mode summary --days 7
echo $?            # 0
ls -l /tmp/typo/missing.db   # 0 字节文件被创建
```
同目录的 `vincula-audit.py:117-132` 与 `vincula-accountd.py:1535-1541` 都是 `mode=ro` + fail-closed。

**影响**：误建文件 + 误报成功（低）。

**置信度**：高（已复现）。

---

## R-12 非 root 跑测试固定失败 2 项（P3）

**位置**：`tests/test_verify_extended.py:67`（断言 `state == UNKNOWN`）、`:254`（断言 stdout 非空）；`.github/workflows/ci.yml:41` 的 Linux 套件用 `sudo -n` 运行

**现象**
普通用户执行 `python3 -m unittest discover -s tests -p 'test_*.py'`：
- `permissions` 检查输出 `FAIL / PERMISSION`（无法以普通用户判定 root 属主），整体变成 `FAIL` 而不是 `UNKNOWN`；
- `bin/vincula verify --extended` 的 root guard 使子进程 stdout 为空，断言失败。

**复现路径**
```bash
python3 -m unittest discover -s tests -p 'test_*.py'
# FAILED (failures=2, skipped=8)
```
CI 的 Linux 作业以 root 运行，所以远端不会暴露；本地开发者会看到红。

**影响**：本地对 CI 的信任度下降；`permissions` 在特权不足时返回 FAIL 而非 UNKNOWN 也会误导脚本调用方。

**置信度**：高（本机实测；属测试/信号问题，非运行时缺陷）。

---

## R-13 私钥与 Clash secret 出现在进程参数中（P2）

**位置**
- `lib/vincula-common.sh:346-356`：`curl -H "Authorization: Bearer ${secret}"`
- `lib/vincula-common.sh:440-442`、`:1459-1461`：`python3 - "$output" … "$private_key" … "$clash_secret"`
- `bin/vincula:3265-3268`：restore 参数 `--new-reality-private` / `--new-clash-secret`
- 调用点：`vincula.sh:1002-1003`（安装/迁移渲染）、`vincula.sh:2018`、`vincula.sh:2231-2235`（健康探测）、`bin/vincula:1361-1365`（verify）、`bin/vincula:1648-1650`（用户变更）

**现象**
REALITY 私钥与 Clash API secret 通过 argv 传给 `python3` / `curl`。Linux 下 `/proc/<pid>/cmdline` 默认对所有用户可读（`hidepid=0`），因此 0600 的状态文件保护被绕过：本机任何可执行用户都能在进程存续期间读到私钥（可冒充 REALITY 服务端）与 Clash secret（可读取 127.0.0.1:9090 的全部连接元数据）。

**复现路径**
```bash
# 已装节点，以非特权用户运行，同时由 root 触发一次变更
while :; do ps -eww -o args= | grep -E 'Authorization: Bearer|reality-private'; sleep 0.1; done
# 另开 root：sudo vcl user rotate owner    → 明文 secret 出现在输出里
```
（代码已确认；未在 live 上实跑。）

**影响**：长期私钥泄露面；仅在主机存在其他登录用户时可达，但一旦成立影响是服务端身份被冒充。

**置信度**：高（代码路径明确）。

---

## R-14 runtime-only 安装缺少受支持的卸载路径（P3）

**位置**
- `bin/vincula:527-537`：`verify_uninstall_preflight` 要求 `VERSION_FILE`、`state.json`、manifest 等存在，否则 `refuse_uninstall`
- `vincula.sh:2304-2312`：`--runtime-only` 只写 `.runtime-only` 标记，不生成 `VERSION` / `state.json`

**现象**
`--runtime-only` 正是 `node replace` 新机的准备状态。若替换在 restore 之前失败、或运维想放弃该主机，`vcl uninstall` 会以 "Vincula VERSION is missing; refusing destructive uninstall." 退出 2；重跑安装器也拒绝（无 VERSION 走新装路径会撞上已存在文件）。唯一出路是手工删除 unit/二进制/账号，而 `vcl uninstall` 是文档给出的移除方式。

**复现路径**
```bash
sudo bash vincula.sh --runtime-only
sudo vcl uninstall --yes      # exit 2, "Vincula VERSION is missing"
```

**影响**：替换失败后的清理无受支持路径，容易留下残留 unit 与服务。

**置信度**：高（静态路径确认）。

---

## R-15 重跑安装器的 "Clash API authentication ✓" 缺少负例（P3）

**位置**
- `vincula.sh:2017-2020`：一次带 secret 的成功请求同时打印 `✓ Clash API reachable` 与 `✓ Clash API authentication`
- `vincula.sh:2231-2237`：`wait_for_accountd_healthy` 里才做负例（空 Bearer、错误 secret 必须失败）
- `vincula.sh:2047`：`wait_for_accountd_healthy || true`，负例结果被丢弃

**现象**
若 `config.json` 的 `secret` 与 `config.toml` 漂移（手工改动、部分恢复），重跑安装器仍会打印认证 ✓ 并宣称 "verified"，但 API 实际未鉴权；`vcl verify` 会正确报 ✗（`bin/vincula:1361-1370`）。

**复现路径**
```bash
# 把 /etc/sing-box/config.json 的 "secret" 置空并重启 sing-box，然后
sudo bash vincula.sh      # "✓ Clash API authentication"
sudo vcl verify           # "✗ Clash API authentication"
```

**影响**：给出错误的安全结论；本地任何用户可无鉴权读取连接元数据。

**置信度**：中高（代码路径确认，未实跑）。

---

## R-16 VERSION 匹配时的 "verified" 不做身份/凭据一致性校验（P3）

**位置**
- `vincula.sh:1950-2062`：`verify_existing_install` 只查二进制校验和、`sing-box check`、监听、unit/accountd、Clash/DB 健康
- `vincula.sh:1900`：`verify_identity_consistency` 仅在**迁移**路径调用
- `bin/vincula:1185-1190`：`vcl verify` 才做 state/settings/config/owner.uri/users 的交叉校验

**现象**
若一次 `vcl user rotate` 在 `atomic_install_file` 之间被中断（config.json/users.json 已更新、owner.uri 仍旧），服务仍在跑，重跑安装器会输出 "verified; credentials preserved"，而客户端拿到的是过期 URI，直到有人执行 `vcl verify`。

**复现路径**
```bash
# rotate 后把 owner.uri 换回旧副本（模拟中断），然后
sudo bash vincula.sh     # "Existing … verified; credentials preserved"
sudo vcl verify          # "✗ UUID consistent"
```

**影响**：中断后的不一致被"已验证"背书，扩大故障窗口。

**置信度**：行为高、严重度中。

---

## 已排除项（文档化行为，非缺陷）

| 项 | 依据 |
| --- | --- |
| `node set --host` 不更新 `trust/known_hosts` | `docs/technical-guide.md:153` 已明确"需再次 pin 或手改" |
| 记账为近似值、短连接可能漏计 | `docs/known-issues-0.3.1.md` 明示 |
| `CURSOR_AHEAD` / `CURSOR_EXPIRED` 失败关闭 | 设计如此，需 `--reseed` |
| `--reseed` 清空节点历史 | `known-issues` 已记录语义 |
| `sync` 在缺 `SSH_AUTH_SOCK` 时返回 PARTIAL | 预期：agent-backed 选择器需要 agent；`ssh_transport.py:75-85` 的 remediation 提示准确 |

## 复现环境

- 控制器：Kali WSL，`vincula-controller-0.5.3`（phase C 构建），Python 3.12
- 节点：epicfury（PDT，`-07:00`）、urgentfury（UTC，`reality_short_id` 为空）
- 所有动态验证均为只读；临时试验在 `/tmp` 下用独立 SQLite 库完成，未触碰仓库文件
