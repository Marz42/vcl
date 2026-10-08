# FR-03 / FR-04 认证分类与结构化错误摘要 — 本地实现与回归

日期：2026-10-08（Asia/Shanghai）。分支 `codex/0.5.1`，基线 `7836b14`（FR-01 已推送并通过 [CI #88](REMOTE_CI_20261008.json)）。范围：只处理 [可靠性待办](../../plans/Fleet_Recovery_Reliability_Backlog.md) 的 **FR-03 / P2** 与 **FR-04 / P2**；FR-02 有界同步仍未实现。

**IMPLEMENTED / UNRELEASED / PENDING CI / PENDING LIVE / PENDING HUMAN。**本记录是本地源码与测试证据；远端 required CI、现场混合 Fleet 复验、24h soak 与 H05 仍未完成。

## 缺陷

**FR-03：认证失败只有一个笼统状态。**`AUTH_MARKERS` 不含 `Too many authentication failures`，服务端认证次数耗尽被归入一般 FAIL/ERROR；同时 `"publickey"` 作为独立 marker 过宽，普通诊断文本（如 `no matching publickey type`）会被误判成认证失败。现场回传的 observe probe 只显示 FAIL，只有临时 doctor 能识别 `AUTH_LIMIT`。

**FR-04：错误详情是原始远端文本。**`_ssh_failure_detail` 直接返回 stderr，stderr 为空时回退 stdout；同步表格再把该字符串原样展示，于是结构化 audit meta、timeout 文本、端点与逻辑 Node/instance ID 混在同一行，既难分类也难分享；失败时把 stdout（可能含审计正文）当错误详情同样不可接受；也不能因为 stderr 里出现 `"ok":true` 片段就当成成功。

## 设计

### 两层输出，顶层状态不变（FR-03）

- 顶层 `state` 仍是 `AUTH_FAILED`，capabilities / probe / verify / telemetry 的既有消费路径不变。
- 新增 `reason`：`AUTH_LIMIT`（服务端认证尝试耗尽）或 `AUTH_DENIED`（身份被拒）。
- 收紧 marker：移除独立的 `"publickey"`，`Permission denied (publickey).` 仍通过 `permission denied` 命中；新增 `too many authentication failures`。
- 最小密钥选择诊断：`hint` 使用固定模板，说明"为该节点选择明确的 agent 公钥并使用 `IdentitiesOnly=yes`；提供过多 agent 密钥可能耗尽服务端认证尝试"——表述为可能原因，不断言环境。`capabilities`/`probe`/`verify` 的人类输出打印 reason 与 next 提示；JSON 增加 `reason`/`hint`（capabilities）与 `ssh_reason`（probe/verify）。
- 不通过清空 agent 或放宽服务端上限规避问题；认证失败仍不回退 admin。

### 结构化事实 + 安全摘要（FR-04）

`lib/ssh_transport.py` 新增统一错误对象：

| 字段 | 含义 |
| --- | --- |
| `phase` | identity / capabilities / audit_export / status / users / verify / inspect / telemetry / remote |
| `code` | AUTH_LIMIT、AUTH_DENIED、TIMEOUT、OUTPUT_LIMIT、HOST_KEY、UNSUPPORTED、PROTOCOL_INVALID、REMOTE_ERROR、TRANSPORT、UNKNOWN |
| `state` | AUTH_FAILED / TIMEOUT / UNSUPPORTED / ERROR |
| `retryable` | 仅 TIMEOUT、TRANSPORT 为 true |
| `summary` | 固定模板文案，不含端点、逻辑身份或远端原文 |
| `hint` | 仅认证类代码附带 |

处理顺序固定为**本地 transport 结果 → 远端协议校验 → 错误分类 → 安全摘要**：

- 超时/输出超量由 `lib/access.py` 通过 `ssh_transport` 的共享 marker（`ssh timed out after` / `scp timed out after` / `stdout exceeds`）显式标记；分类时本地事实优先于任何远端文本。
- audit meta 继续用 `parse_export_meta` 作为协议数据解析，不再整体拼进错误字符串。
- 摘要全部来自允许字段与固定模板；不对任意 stderr 做 IP/UUID 正则清洗。
- `node_id`/`instance_id` 保留在机器合同里（sync 行、`machine_failure_facts`），摘要本身可分享；机器 JSON 不被称为"可分享报告"。
- 失败时 `_ssh_failure_detail` 只取 stderr，stdout 一律不作为错误详情；stderr 为空时回退为 `exit N`。
- 成功仍只由 stdout 的协议 JSON 决定，stderr 中出现 `"ok":true` 不构成成功。

**保留原始文本的边界**：非认证、非本地 transport 的远端错误（如 `CURSOR_EXPIRED`、安装脚本报错）仍把 stderr 作为操作者诊断信息展示，但不会把 stdout 或协议 meta 混入；auth / timeout / output-limit / host-key / transport 五类一律只给固定模板。

### 合同影响

- `fleet sync --json` 的行新增 `error_code`、`error_phase`、`retryable`；`schema_version` 仍为 1，属附加字段；`error` 现在是固定模板摘要而不是原始 stderr。
- `verify --json` / `status --json` 的节点新增 `ssh_reason`（成功时为 `null`）。
- `capabilities --json` 在 AUTH_FAILED/ERROR 时新增 `reason`、`hint`。
- 人类同步表格在 `ERROR:` 行后新增 `CODE: <code> phase=<phase> retryable=<bool>`；probe/verify 表格新增 `ssh_reason=` 与 `next:` 两行。

## 用例与结果

`tests/test-fleet.sh` 新增 10 项断言，并更新 verify JSON 形状用例的字段集合：

| 用例 | 覆盖 |
| --- | --- |
| 分类器区分 limit / denial / 普通诊断文本 | 新 marker、移除过宽 `publickey`、AUTH_LIMIT hint |
| 本地 transport 事实优先 | 混合文本（连接关闭 + timeout）判为 TIMEOUT/tryable |
| capabilities 保持 AUTH_FAILED 并附 AUTH_LIMIT | 顶层状态兼容 + reason/hint |
| capabilities detail 不含远端原文/端点 | `Received disconnect`、IP、原始 marker 均不出现 |
| probe / verify 输出 AUTH_FAILED + ssh_reason=AUTH_LIMIT | 假 SSH 只对 observe 键失败，因此 AUTH_FAILED 本身即证明未回退 admin |
| 失败详情不回显 stdout | 审计正文留在 stdout 时 detail 为 `exit 1` |
| 摘要不含端点与逻辑身份 | 从混合 detail 生成的摘要丢弃 IP/node_id/instance_id/CURSOR_EXPIRED |
| 机器字段保留 | `machine_failure_facts` 保留 node_id/instance_id，摘要仍可分享 |
| sync 行携带 code/phase/retryable 且表格展示 | `_sync_result` + `format_sync_table` |
| stderr 出现 `"ok":true` 不产生成功 | `require_exit_0` 下仍为 FAIL，payload 为 None |

回归（本机 WSL2 / Debian 13.3 / Python 3.13.5）：

- `bash tests/test-fleet.sh`：**All 1087 tests passed，exit 0**（含本轮新增 10 项，0 失败）。
- `SQLITE_TMPDIR=<workspace>/tmp/sqlite-tmp bash tests/test.sh`：**All 1905 tests passed，exit 0**（本机沙箱需指定可写的 SQLite 临时目录，理由与 FR-01 记录相同）。
- `python3 -m unittest discover -s tests -p 'test_*.py'`：155 项，2 项失败均为 `test_verify_extended` 的 root 权限 fixture，已在 `5054e51` 原始工作树复现为既存环境限制，与本轮改动无关。

## 未关闭边界

- FR-02 有界审计同步（分页、deadline、stdout cap、续传、MORE_PENDING 汇总）未在本轮实现。`sync_report` 目前仍只把 EXPIRED/ERROR 判为失败，MORE_PENDING 状态接入属于 FR-02 合同变更。
- 远端 required CI、现场混合 Fleet 复验、Live/H05、24h soak 仍 PENDING；本记录不构成 0.5.x 候选验收。
- 非认证类远端错误仍展示 stderr 原文，这是操作者诊断的有意保留，不是"可分享摘要"；如需对外分享，应使用 `summary` 投影。
