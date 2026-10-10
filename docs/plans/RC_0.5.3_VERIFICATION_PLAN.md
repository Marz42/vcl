# 0.5.3 新候选冻结与「Controller 优先」现场验证方案

**PREPARED / NOT EXECUTED。**本文件是待执行方案与操作手册，不是 PASS、不是验收结论，不构成部署、合并、tag、发布或 Node 升级授权。所有现场项初始状态为 **PENDING LIVE**，人工签署项为 **PENDING HUMAN**。

准备过程、准备期缺陷修复与本次回归/CI 计数见[现场验证准备记录](../evidence/0.5.3/VERIFICATION_PREP.md)。日期：2026-10-08（Asia/Shanghai）。适用分支 `codex/0.5.1`，当前本地修复结论文档见 [FR-02 记录](../evidence/0.5.3/FR02_BOUNDED_SYNC.md)、[FR-01 记录](../evidence/0.5.3/FR01_CREDENTIAL_ISOLATION.md)、[FR-03/04 记录](../evidence/0.5.3/FR03_FR04_ERROR_MODEL.md)；验收框架见[人工验收清单](VCL_0.5-0.7_Human_Acceptance.md)与[延期记录](MANUAL_VALIDATION_DEFERRED.md)。

## 0. 顺序、范围与红线

执行顺序（不可跳步）：

1. **阶段 F**：冻结新候选（源码/测试/schema/制品/证据重新绑定）；
2. **阶段 A**：只验证 Controller，**保留现有混合版本 Node 不动**；用隔离测试工作区做基线、大积压、限一页续传、`sync --full`、失败与恢复；
3. **阶段 B**：七台混合 Fleet 复验（只读观测 + 2h 受控矩阵）；
4. **阶段 C**：固定候选连续 24h soak；
5. **阶段 D**：H05 人工签署；
6. **之后**才判断是否进入 Node 分批升级（升级连续性 ≤3s 属该阶段，另行授权）。

红线（违反即停止并记录 FAIL）：

| # | 禁止事项 | 原因 |
| --- | --- | --- |
| R1 | 为制造积压而重置**生产**工作区/缓存的游标（`sync --reseed`） | 破坏生产审计连续性；积压应由**隔离**工作区从 cursor=0 自然产生 |
| R2 | 在生产 workspace / 生产缓存上跑预算、故障注入或 `--reseed` | 生产缓存是观测事实来源，不可作为试验场 |
| R3 | 验证期间改动 Node 的配置、服务、数据或游标 | 本轮只验证 Controller；Controller 对 Node 只做只读采集 |
| R4 | 把 fixture/离线结果、或"本次已关闭连接窗口追平"当作现场结论 | 前者不是现场证据，后者不代表以后不会再有数据 |
| R5 | 未获明确授权执行 merge / tag / release / production apply / Node 升级 | 本方案只准备验证 |
| R6 | 把失败的 run、命令或日志从记录中删除 | 保留失败是仓库既有约定 |

## 1. 隔离模型（阶段 A 之前必须先建立）

| 变量 / 路径 | 生产取值 | 隔离测试取值 | 隔离内容 |
| --- | --- | --- | --- |
| `VCL_FLEET_HOME` | 现有 Controller 工作区 | `$VCL_VERIFY_ROOT/ws` | `fleet.json`、`workspace.json`、`trust/known_hosts`、`history/instances.jsonl` |
| `VCL_FLEET_LOCAL_STATE` | `~/.local/state/vincula` | `$VCL_VERIFY_ROOT/state` | `<fleet_id>/fleet.db`（缓存 + `audit_events` + `sync_cursor`）、`ui-runtime/` |
| `XDG_CONFIG_HOME` | `~/.config` | `$VCL_VERIFY_ROOT/config` | `vincula/controllers/<fleet_id>/credential-bindings.json`（凭据**绑定**，机器本地，workspace 导出**不含**） |
| `TMPDIR` | 系统临时目录 | `$VCL_VERIFY_ROOT/tmp` | `workspace import` 的暂存目录（优先 `~/tmp`，不可用时回落系统临时目录） |

**必须同时隔离 `VCL_FLEET_LOCAL_STATE`**：把生产注册表导入到同一台机器的第二个工作区根时，机器本地的 workspace view 会看到同一个 `fleet_id` 来自两个根；此时 `workspace verify` 会报 `WORKSPACE_DIVERGED`（这是预期的冲突检测，不是数据损坏）。只要像 A1 那样把 `VCL_FLEET_LOCAL_STATE` 指向隔离目录，验证就会正常通过；**不要**为了让报错消失去删除生产 state 目录里的 view。

生产侧**先取证、后验证、再复核**（三段都要记录，证明生产没被改动）：

```bash
# 生产指纹（在未导出任何 VCL_* 覆盖变量的普通 shell 中执行）
PROD_WS="${VCL_FLEET_HOME:-$HOME/.config/vincula}"     # 若生产用 --workspace，请填实际路径
mkdir -p ~/vcl-verify-evidence
python3 "$PWD/lib/vincula-fleet.py" workspace show > ~/vcl-verify-evidence/prod-workspace-before.json 2>&1 || true
find "$PROD_WS" -type f -print0 | sort -z | xargs -0 sha256sum > ~/vcl-verify-evidence/prod-ws-before.sha256
find ~/.local/state/vincula -name 'fleet.db' -print0 2>/dev/null | sort -z \
  | xargs -0 -r sha256sum > ~/vcl-verify-evidence/prod-db-before.sha256
stat -c '%n %s %Y' $(find "$PROD_WS" -type f) > ~/vcl-verify-evidence/prod-stat-before.txt 2>/dev/null || true
```

验证结束后用同样三条命令生成 `*-after`，`diff` 必须为空；**任何差异都按 R3 违反处理**（除生产自己运行 monitor/sync 造成的正常变化，此时必须能解释）。

## 2. 阶段 F — 候选冻结（自动步骤，人工执行并记录）

> **2026-10-08 执行记录：阶段 F 已完成**，候选身份与全部离线证据见[冻结候选](../evidence/0.5.3/CANDIDATE_FREEZE.md)：Node `8abe989c` / Controller `65dbcc7b`、188 个固定输入（manifest `da84b695…`）、`SOURCE_DATE_EPOCH=1791513039`、远端 CI #100 七项全绿。阶段 A/B/C/D 仍未执行。下表保留为冻结流程的说明与复核清单。

| 步骤 | 命令 | 预期 | 证据 |
| --- | --- | --- | --- |
| F1 工作树干净 | `git status --short --branch`；`git log -1 --format='%H %cI'` | 无未提交改动；记下候选 SHA | 记录 SHA、分支 |
| F2 全量回归 | `bash tests/test-fleet.sh`；`SQLITE_TMPDIR=$PWD/tmp/sqlite-tmp bash tests/test.sh`；`python3 -B -m unittest discover -s tests -p 'test_*.py'` | 三条全绿、exit 0 | `tmp/` 下保存原始日志 |
| F3 固定制品 | `SOURCE_DATE_EPOCH=<固定值> bash scripts/build-release.sh`；`SOURCE_DATE_EPOCH=<固定值> bash scripts/build-controller.sh` | 产出 `dist/vincula-node-0.5.3.tar.gz(.sha256)`、`dist/vincula-controller-0.5.3.zip(.sha256)` | 记录 `sha256sum dist/*` 全部值 |
| F4 制品门禁 | `python3 -B scripts/check-controller-artifact.py dist/vincula-controller-0.5.3.zip`；`(cd dist/vincula-controller-0.5.3 && sha256sum --check controller.lock)`；`(cd dist/vincula-node-0.5.3 && sha256sum --check release.lock)` | 通过；含无 repo `lib/`、无 `PYTHONPATH` 的黑盒入口 | 原始日志 |
| F5 固定输入清单 | 生成/更新 `docs/evidence/0.5.3/SOURCE_INPUTS_<候选>.json`（源码/测试/schema/构建/CI 逐项 LF 字节 SHA256，不含自引用 commit） | 清单 SHA256 记录进证据页 | 清单文件 + 其 SHA256 |
| F6 远端 CI | 推送候选；`gh` 不可用时用 REST：`curl -s "https://api.github.com/repos/Marz42/vcl/actions/runs?per_page=1"` | 七个 job 全绿；失败 run 原样保留 | 脱敏 CI 快照 JSON（格式见 `REMOTE_CI_20261008_FR02_FIXES.json`） |
| F7 候选记录 | 在 `docs/evidence/0.5.3/` 新增/更新候选页 | 版本、SHA、制品 SHA、CI 号、测试计数 | 候选页 |

> 说明：`push` 事件本身不触发 `ci.yml`（只对 `main` 的 push 生效），运行来自 Draft PR #13 的 `pull_request`。Windows 的 unittest job 在本仓库出现过**与源码无关的偶发失败**（见 run 91、96）；重跑一次即可判定，但两次结果都要保留。

## 3. 阶段 A — Controller 隔离验证（详细人工步骤）

> **2026-10-09 执行记录：阶段 A 已完成（Controller 侧），PASS WITH FINDINGS。** 现场结果与确切错误模板见[阶段 A 记录](../evidence/0.5.3/PHASE_A_CONTROLLER.md)。要点：冻结候选摘要逐次校验一致；生产 `fleet_id 1633b697…`（rev 16，2.1 GB 缓存，7 节点）只读导出后隔离导入（rev 17）；基线 5 台 OK、`epicfury`/`hot-beam-1` 为 `AUTH_FAILED/AUTH_LIMIT`（无 ref → OpenSSH 默认身份），`upperhand` 0.3.1-rc2、`urgentfury` 0.3.2 的 `capabilities` 为 `UNSUPPORTED`；大积压完整追平 254 页/1,269,177 行/1091s（默认 `--budget 3600` 足够）；限一页续传链与 `sync --full` 快照（`synced_at` fresh）成立；超时、超量页、页前预算、导入期锁回滚（`audit_import`）、运行中 SIGINT（`rc=-2`）与中断后续传全部取得确切文本且不推进游标；每一步"起点游标==上次提交游标、无半页"成立；生产工作区/缓存/绑定指纹五轮一致。新发现 F-1（连接期锁不入预算，竞态）与 F-2（部分节点仍依赖默认身份）已记入[可靠性待办](Fleet_Recovery_Reliability_Backlog.md)。A5 的定向 `AUTH_DENIED` 未单独执行（现场以真实 AUTH_LIMIT 覆盖分类路径）；阶段 B/C/D 未开始。

**A0 前置条件**（全部满足才可开始；不满足就停在 PENDING）

- [ ] 候选已按阶段 F 冻结，制品 SHA 与候选页一致；
- [ ] 执行人已被告知：本次只读 Node，不改 Node 配置/服务/数据；不改生产工作区；
- [ ] 生产指纹（§1）已采集；
- [ ] 维护/观察窗口已确定并记录 UTC 起止；
- [ ] 至少一台真实 Node 可 SSH（admin 与 observe 身份各一），另有一台旧版本（0.3.1/0.3.2）可用于兼容观察；
- [ ] 生产 SSH key 路径已知（**不要把 key 内容写入任何文档或日志**）。

**A1 建立隔离环境并导入生产注册表**

```bash
export VCL_VERIFY_ROOT="$HOME/vcl-verify-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$VCL_VERIFY_ROOT"/{ws,state,config,tmp,evidence}
export VCL_FLEET_HOME="$VCL_VERIFY_ROOT/ws"
export VCL_FLEET_LOCAL_STATE="$VCL_VERIFY_ROOT/state"
export XDG_CONFIG_HOME="$VCL_VERIFY_ROOT/config"
export TMPDIR="$VCL_VERIFY_ROOT/tmp"
CTRL="python3 $PWD/lib/vincula-fleet.py"          # 或解包后的候选 <unpack>/bin/vcl-fleet

# 1) 生产侧导出（在未设置上述变量的 shell 中执行）
python3 "$PWD/lib/vincula-fleet.py" workspace export ~/vcl-verify-evidence/prod-ws-export.tgz
# 2) 隔离侧导入（manifest 缺省即可，import 会建立）
$CTRL workspace import ~/vcl-verify-evidence/prod-ws-export.tgz
$CTRL workspace show | tee "$VCL_VERIFY_ROOT/evidence/verify-workspace-show.json"
$CTRL node list | tee "$VCL_VERIFY_ROOT/evidence/nodes.txt"
```

预期：`workspace show` 的 `fleet_id` 与生产一致、`revision` 为导入后 +1；`node list` 列出全部节点。
证据：`prod-ws-export.tgz` 与其 SHA256、`verify-workspace-show.json`。
判定：导入失败或 `fleet_id` 不一致 → 停止（不要手工改 JSON）。

**A2 在隔离 config 重新绑定凭据（关键：证明绑定是机器本地的）**

```bash
# 列出导入节点引用的 ref（脱敏：只打印 ref 名，不打印 key 路径以外的内容）
python3 - "$VCL_VERIFY_ROOT/ws/fleet.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for n in d["nodes"]:
    print(n["name"], n.get("admin_credential_ref"), n.get("observe_credential_ref"))
PY
# 为每个 ref 绑定真实 key（示例；按上一步输出逐个执行）
$CTRL access bind <admin_ref>   --identity-file /path/to/admin_key
$CTRL access bind <observe_ref> --identity-file /path/to/observe_key
ls -l "$VCL_VERIFY_ROOT/config/vincula/controllers/"*/credential-bindings.json
```

预期：隔离目录下出现 `credential-bindings.json`；生产目录的同名文件 mtime/SHA **不变**（`stat`/`sha256sum` 复核）。
判定：任何命令写到了生产 `credential-bindings.json` → 立即停止（R2 违反）。

**A3 只读基线（不写缓存）**

```bash
$CTRL probe   --json | tee "$VCL_VERIFY_ROOT/evidence/A3-probe.json"
$CTRL verify  --json | tee "$VCL_VERIFY_ROOT/evidence/A3-verify.json"
$CTRL status  --json | tee "$VCL_VERIFY_ROOT/evidence/A3-status.json"   # cache-only，首次为空属正常
```

预期：`probe` 每个节点四列有确定状态（OK/STALE/FAIL/UNKNOWN）；`probe`/`verify` **不写** `last-status.json`/`node_snapshot`（`status` 仍显示 EMPTY，除非之后跑了 `sync --full`）。
判定：出现无法解释的 FAIL/AUTH_FAILED/TIMEOUT → 先记录，按 A5 分类，不要跳过。

**A4 版本与能力矩阵（混合版本，不升级 Node）**

```bash
for n in $(python3 -c 'import json;print(" ".join(x["name"] for x in json.load(open("'"$VCL_VERIFY_ROOT"'/ws/fleet.json"))["nodes"]))'); do
  echo "== $n"; $CTRL capabilities "$n" --json | tee "$VCL_VERIFY_ROOT/evidence/A4-cap-$n.json"
done
```

预期：0.5.x 节点返回 `state=OK` 与能力列表；旧节点（如 0.3.1）缺 capability 时返回 `UNSUPPORTED` 而不是 FAIL；版本号与现场记录一致。
判定：旧节点被误报为故障 → FAIL，记录原始 JSON。

**A5 observe 认证负例（安全、必做；只在隔离 config 内做）**

```bash
# 用一把"故意错误"的 observe key 覆盖绑定（仅隔离 config）
ssh-keygen -t ed25519 -N '' -f "$VCL_VERIFY_ROOT/tmp/wrong_observe" >/dev/null
$CTRL access bind <observe_ref> --identity-file "$VCL_VERIFY_ROOT/tmp/wrong_observe"
$CTRL capabilities <node> --json | tee "$VCL_VERIFY_ROOT/evidence/A5-auth-failed.json"   # 期望 exit 1
# 恢复正确绑定
$CTRL access bind <observe_ref> --identity-file /path/to/observe_key
$CTRL capabilities <node> --json >/dev/null && echo "restored"
```

预期：`state=AUTH_FAILED`，并带 `reason=AUTH_LIMIT|AUTH_DENIED`（若服务端认证次数耗尽则为 AUTH_LIMIT）、`hint`（明确公钥 + `IdentitiesOnly=yes`）；`detail`/摘要中**不出现** IP、端口、远端原文；即使 admin 绑定存在也**不得**回落到 admin（本步不提供 admin 通道即可证明）。
判定：出现 `state=OK`、摘要含端点、或提示要求"清空 agent/放宽服务端上限" → FAIL。

**A6 大积压有界追赶（隔离缓存从 cursor=0 自然产生积压，符合 R1）**

```bash
CMD=(sync --node <node> --page-size 5000 --max-pages 300 --timeout 60 \
     --stdout-cap 16777216 --budget 3600 --json)
start=$(date -u +%s); "${CMD[@]/sync/$CTRL sync}" > "$VCL_VERIFY_ROOT/evidence/A6-sync.json"; rc=$?; end=$(date -u +%s)
echo "rc=$rc elapsed=$((end-start))s"
python3 -c 'import json,sys;n=json.load(open(sys.argv[1]))["nodes"][0];print({k:n.get(k) for k in ("status","audit_pages","inserted","updated","last_export_seq","more_pending","error_code")})' \
  "$VCL_VERIFY_ROOT/evidence/A6-sync.json"
```

预期：`status=ok` 且 `more_pending=false`（追平当次已关闭连接窗口），或 `status=more_pending`+`error_code∈{PAGE_CAP,BUDGET_EXHAUSTED}`（说明预算/页数用尽，数据仍待续传）；两种都**不是**失败。
判定：`error_code=DATABASE_ERROR`、协议错误或摘要含端点/身份 → FAIL 并保留 JSON。
记录：页数、插入数、游标、墙钟时间、`--page-size` 等参数（这些默认值正是阶段 A 要实测的对象）。

**A7 限一页续传（MORE_PENDING → 续跑 → ok）**

```bash
# 新起一个隔离缓存（或对同一节点先记下游标/行数）
python3 - "$VCL_VERIFY_ROOT/state" <<'PY'   # 记录续传前状态（只读）
import glob, sqlite3, sys
for db in glob.glob(sys.argv[1] + "/*/fleet.db"):
    c = sqlite3.connect(db)
    print(db, c.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0],
          c.execute("SELECT last_export_seq FROM sync_cursor").fetchone())
    c.close()
PY
$CTRL sync --node <node> --page-size 5000 --max-pages 1 --json | tee "$VCL_VERIFY_ROOT/evidence/A7-page1.json"; echo "rc=$?（期望 2）"
$CTRL sync --node <node> --page-size 5000 --json | tee "$VCL_VERIFY_ROOT/evidence/A7-resume.json"; echo "rc=$?（期望 0）"
$CTRL status | tee "$VCL_VERIFY_ROOT/evidence/A7-status.txt"
```

预期：第一步 `state=PARTIAL`、`status=more_pending`、`error_code=PAGE_CAP`、`audit_pages=1`，游标=第 1 页末；第二步从该游标继续并最终 `ok`；`status` 的 CURSOR 列为 `ok`。
判定：第二步从头重导（`after` 回到 0）、出现协议错误、或第一步把 `more_pending` 汇总成 SUCCESS → FAIL。

**A8 `sync --full`：追赶后重新采集快照**

```bash
$CTRL sync --full --node <node> --page-size 5000 --json | tee "$VCL_VERIFY_ROOT/evidence/A8-full.json"
$CTRL status --json | tee "$VCL_VERIFY_ROOT/evidence/A8-status.json"
```

预期：`operation=sync_full`、`state=SUCCESS`（或审计未追平时 `more_pending`）；`status` 的 `synced_at` 落在本次运行**之后**（即追赶结束后采集），`instance_id` 与现场一致；`verify --json` 复核 identity 不报 `IDENTITY_*`。
判定：`error_code ∈ {IDENTITY_UNREACHABLE, IDENTITY_MISMATCH, IDENTITY_CHANGED, BUDGET_EXHAUSTED}` → 记录并按 A9 分类（身份变化需在一次性测试 Node 上复现，见 A9）。

**A9 失败与恢复（**只在隔离缓存**上做；每项都要有"崩溃前已提交页保留"的证据）

| 场景 | 命令 | 预期 |
| --- | --- | --- |
| 第二页超时 | `$CTRL sync --node N --page-size 5000 --timeout 1 --budget 60 --json` | `error_code=TIMEOUT`、`retryable=true`，已提交页与游标保留 |
| 预算停止（页前） | `$CTRL sync --node N --page-size 5000 --budget 2 --json` | `more_pending` + `BUDGET_EXHAUSTED`，0 或已提交页保留 |
| 预算停止（导入中） | 同上但 `--page-size 5000 --budget 15` 且节点积压很大 | `BUDGET_EXHAUSTED`、`error_phase=audit_import`；该页回滚，前一页保留 |
| 超量页 | `$CTRL sync --node N --page-size 5000 --stdout-cap 1024 --json` | `error_code=OUTPUT_LIMIT`，0 行导入，游标不动 |
| 锁等待耗尽预算 | 见下方"锁"步骤 | `BUDGET_EXHAUSTED`（非 `DATABASE_ERROR`） |
| 运行中中断 | 启动多页运行后按 `Ctrl-C` | 已提交页保留；重跑不得报协议错误或重复导入 |

锁（隔离缓存独占，不动生产）：

```bash
DB=$(ls "$VCL_VERIFY_ROOT"/state/*/fleet.db | head -1)
python3 - "$DB" <<'PY' &
import sqlite3, sys, time
c = sqlite3.connect(sys.argv[1]); c.execute("BEGIN EXCLUSIVE"); time.sleep(20); c.rollback()
PY
sleep 1
$CTRL sync --node N --page-size 5000 --budget 5 --json | tee "$VCL_VERIFY_ROOT/evidence/A9-lock.json"; echo "rc=$?"
wait
```

每步都要记录：JSON、退出码、续跑后的 `status`（CURSOR/LAST_SYNC）、以及 `SELECT COUNT(*)` 与游标的前后值（python 单行即可）。
判定：任何一步出现"未提交页被计入游标"、"已提交页丢失"、或把预算停止报成 `DATABASE_ERROR` → FAIL。

**A10 收尾复核（必做）**

```bash
# 生产未被改动
find "$PROD_WS" -type f -print0 | sort -z | xargs -0 sha256sum > ~/vcl-verify-evidence/prod-ws-after.sha256
find ~/.local/state/vincula -name 'fleet.db' -print0 2>/dev/null | sort -z | xargs -0 -r sha256sum > ~/vcl-verify-evidence/prod-db-after.sha256
diff ~/vcl-verify-evidence/prod-ws-before.sha256 ~/vcl-verify-evidence/prod-ws-after.sha256 && echo "prod ws unchanged"
diff ~/vcl-verify-evidence/prod-db-before.sha256 ~/vcl-verify-evidence/prod-db-after.sha256 && echo "prod db unchanged"
```

Node 侧无副作用（由执行人在被测 Node 上执行；只读检查）：

```bash
systemctl show -p NRestarts sing-box vincula-accountd 2>/dev/null
sha256sum /etc/sing-box/config.json 2>/dev/null; stat -c '%n %Y' /etc/sing-box/config.json 2>/dev/null
```

预期：restart count 与配置文件哈希/时间戳在验证前后一致（除非执行人另做授权操作）。

## 4. 阶段 B — 七台混合 Fleet 复验

> **2026-10-09/10 执行记录：阶段 B 已完成，PASS。** 生产上下文（工作区/状态/绑定全部取副本，生产根只读）跑了 10h45m22s（38,722 s，`--interval 60 --inspect-interval 300`）。B1/B2 与阶段 A **无差异**；B3 三个 cache-only 视图 `cache_state=OK`，窗口内 61 条事件，五台可达节点覆盖率 0.91–0.97、最大间隔 ≤72 s，0.3.x 两台也有 610+ 样本，两台 `AUTH_FAILED` 只有 130 个退避样本（监控盲区，已并入 FR-01 待办）；B4 显示 `instance_id` 未变、`restart_count` 0→0、服务 active 不变，`uptime` 与窗口一致，流量为业务自然增长；生产工作区/缓存/绑定指纹两轮 4/4 一致。新发现 F-4（停止前尾部 814 s 无样本、停止后 health 全 `UNKNOWN` 并写入一批陈旧 finding；日志缓冲丢失未能定因，阶段 C 用无缓冲日志复测）与 F-5（某次遥测快照缺 `connection_count`）。完整记录见[阶段 B](../evidence/0.5.3/PHASE_B_FLEET.md)。

> **2026-10-09 准备：阶段 B 采集器已入库** `docs/evidence/0.5.3/tools/phase-b.sh`（两段式：准备段做副本与 B1/B2 并启动 2h monitor，`--collect` 段做 B3 序列、B4 复核与生产指纹）。**隔离口径**：生产工作区、状态库与凭据绑定都取**副本**（状态用 SQLite 在线备份，含 `fleet.db`/`observation.db`/`findings.db`/`inspection.db`），生产根只被读取；因此 monitor/verify 的写入全部落在 `$B_ROOT`。B1 与阶段 A 结果自动对照（`PHASE_A_SUMMARY=`）。

前置：阶段 A 全部 PASS；生产指纹仍一致；窗口与脱敏映射已记录。

| 步骤 | 操作 | 预期/证据 |
| --- | --- | --- |
| B1 | 在生产工作区跑 `probe --json` / `verify --json`（只读），与阶段 A 的隔离结果对照 | 状态一致、无新增 FAIL；JSON 存档 |
| B2 | 逐节点 `capabilities --json`，记录版本与能力矩阵 | 旧版本 UNSUPPORTED 不误报；矩阵表 |
| B3 | 2h 受控矩阵：`monitor --interval <s> --inspect-interval <s>` 覆盖 monitor→health→finding→inspect→timeline | 采样不拖垮整轮；`health/findings/timeline --json` 有连续时间序列 |
| B4 | 只读副作用复核：被测 Node 的 restart count、受管文件哈希/mtime、实际代理连通性 | 前后一致（业务流量自然增长单独记录） |
| B5 | 保留失败与异常 run | 不删除、不美化 |

## 5. 阶段 C — 24h soak

> **2026-10-10 准备：阶段 C 采集器已入库** `docs/evidence/0.5.3/tools/phase-c.sh`（两段式）。**隔离口径同阶段 B**：生产工作区/状态/绑定取副本（状态用 SQLite 在线备份四库），生产根只读；`monitor`/`soak` 的写入全部落在 `$C_ROOT`。三件仪器并用：
>
> 1. `scripts/soak-0.5.0-telemetry.sh <node> --iterations 1000 --live`：遥测突发 + BEFORE/AFTER 节点快照（`/var/lib/vincula` 字节与文件数、`accounting.db`、sing-box/accountd `is-active`/`NRestarts`/RSS/FD），产出 `SUMMARY.txt` + `DIGEST.json`（`PASS LIVE`/`FAIL LIVE`，不含 IP/密钥）。前置：目标节点必须支持 `telemetry/v1` 且有可用 observe 凭据 → 只能是 `neptunespear`/`fresh050`/`eagleclaw`；`epicfury`/`hot-beam-1` 因 `AUTH_FAILED` 无法预检，0.3.x 两台不支持遥测。解包副本已 `chmod +x`（ZIP 不保留可执行位）。
> 2. `monitor --interval 60 --inspect-interval 300 --concurrency 2 --json` 跑 24h：连续健康/发现/检查样本（`observation.db`/`findings.db`/`inspection.db` 都在副本里）。注意**连续 monitor 不打印 stdout**（只有 `--once` 打印 `run` 计数），因此写失败计数在收尾时用一次 `monitor --once` 取样。
> 3. 5 分钟采样器：`health`/`findings`/`timeline` 的 `cache_state`、每节点 observation/proxy 状态与 proxy 成功/失败计数、发现数与类型、时间线事件数、四库字节、`audit_events`/`daily_usage` 行数、遥测年龄；收尾报告另外关联 `inspection.db.events` 与序列尾部空档（用于判定阶段 B 的 F-4）。
>
> **代理维度需要授权**：`真实代理成功/失败与断流窗口`需要私有 `probe-profiles/v1` 文件（见 `docs/operations/monitoring-runbook.md`，含每节点专用 `vcl-probe-*` 测试用户、Reality 参数与 HTTPS 目标）加本机固定版本 `sing-box`；这要求在 **Node 上新建专用测试用户**（属 Node 侧变更）。未获授权时 `PROBE_PROFILES` 留空，代理状态保持 `UNKNOWN`，该维度按“缺一不填 PASS”如实记为未覆盖。

- 固定候选（Controller/Node 版本 + 制品 SHA + 源码 manifest）、拓扑、账户身份、间隔、UTC 窗口先记录。
- 采样项（缺一不填 PASS）：telemetry/poll/heartbeat/inspect freshness 与失败计数；sing-box/accountd/observer service active/restart/RSS/FD；数据库大小、retention/capacity/truncation、锁/写失败；Finding 生命周期与 Timeline；真实代理成功/失败与断流窗口。
- 可复用既有驱动（先读用法再执行）：

```bash
VCL_SOAK_LIVE=1 VCL_FLEET_HOME=<ws> VCL_FLEET_BIN=<候选 bin/vcl-fleet> \
  bash scripts/soak-0.5.0-telemetry.sh <NODE> --iterations 1000
# 离线复核已保存证据（不发 SSH）
VCL_FLEET_HOME=<ws> bash scripts/soak-0.5.0-telemetry.sh <NODE> --recheck-evidence
```

- 起止 UTC、候选 SHA、测量、故障、恢复、原始日志 hash 与结论写入 [SOAK](../evidence/0.5.3/SOAK.md)；失败或中断必须保留，不得把分段时长换算成连续 24h。

## 6. 阶段 D — H05 人工验收

按[人工清单](VCL_0.5-0.7_Human_Acceptance.md) H05-01～H05-08 逐项见证并填写[候选页](../evidence/0.5.3/HUMAN_ACCEPTANCE.md)。执行者负责准备与解释，验收人负责判断与签署；**代理不代签**，`PASS OFFLINE` 不得填成 `PASS LIVE`。

## 7. 证据与命名

| 位置 | 内容 |
| --- | --- |
| `~/vcl-verify-evidence/`（现场，不进仓库） | 生产指纹 before/after、workspace export、A1–A10 原始 JSON/日志、soak 原始数据 |
| `docs/evidence/0.5.3/` | 脱敏结论：候选页、`LIVE.md`、`SOAK.md`、`HUMAN_ACCEPTANCE.md`、CI 快照 JSON、源码输入 manifest |
| `docs/operations/` | 需要长期保留的操作手册更新（如发现新的恢复步骤） |

规则：每个证据文件记录 SHA256；日志保留原始字节；脱敏只做"删除/替换敏感值并标注"，不改写结论；失败 run 与成功 run 并存。

## 8. 判定、停止与回退

- 每阶段 PASS 需要：该阶段全部必需步骤完成、证据齐全、无未解释 FAIL；阶段 A 额外要求生产指纹前后一致。
- **立即停止**条件：生产工作区/缓存被改动；Node restart count 或配置哈希异常变化；出现数据丢失或未提交页计入游标；认证/协议错误无法归类；secret 出现在任何日志或文档中。
- 回退：阶段 A 的回退就是**丢弃隔离目录**（`rm -rf "$VCL_VERIFY_ROOT"`），生产不受影响；生产侧任何动作按既有 runbook（如 [node-replace](../operations/node-replace-runbook.md)）执行。

## 9. 待定参数与开放项

1. `--page-size` / `--timeout` / `--stdout-cap` / `--max-pages` / `--budget` 的默认值（当前 1000 / 60s / 16 MiB / 300 / 3600s）需要用 A6 的实测数据确认或调整，并回写文档。
2. 日汇总按页重建（`rebuild_daily_usage_for_node`）的导入放大属独立性能项，本轮只测量、不改实现。
3. 身份变化与 retention gap 的现场覆盖：只在**一次性测试 Node**或已授权的可恢复节点上做；否则明确标注 offline-covered，不假装覆盖。
4. Node 升级连续性（新连接不可用 ≤3s）属分批升级阶段，需另行授权与补证。
