# FR-02 有界审计同步 — 本地实现与回归

日期：2026-10-08（Asia/Shanghai）。分支 `codex/0.5.1`，基线 `4bf2fcb`（FR-01/FR-03/FR-04 已推送）。范围：[可靠性待办](../../plans/Fleet_Recovery_Reliability_Backlog.md) 的 **FR-02 / P1**，即本轮补修的最后一项 P1。

**IMPLEMENTED / UNRELEASED / REMOTE CI PASS / PENDING LIVE / PENDING HUMAN。**`fd6ab89` 的远端 required CI 七个 job 全绿（[CI #94](https://github.com/Marz42/vcl/actions/runs/37755078557)，脱敏快照见 [REMOTE_CI_20261008_FR02.json](REMOTE_CI_20261008_FR02.json)）；现场混合 Fleet 复验、参数实测、24h soak 与 H05 仍未完成。

## 缺陷

- Controller 的 `vcl audit export` 调用不带 `--limit`，固定 20 秒超时，也没有 stdout 字节上限：一台有 50 万条以上积压的节点会把整段积压塞进单个请求，超时后整批不提交，下一次重试又拉同一大批。
- Node 端 `export_after()` 早已支持 `--limit`，`access.py` 也早已有带 deadline、stdout cap 与 stderr 上限的捕获实现；缺的是 Controller 侧的"单页处理器 + 有预算的追赶循环"。
- `MORE_PENDING` 之类的"还没追平"状态不存在，`sync_report()` 只把 `expired`/`error` 视为失败，因此"预算用尽、仍有积压"会被汇总为 `SUCCESS`。
- `retire`/`replace` 复用同步函数，但只检查"这一页成功了没有"，不检查是否追平，可能在审计仍落后时继续备份、替换或退役。
- `sync --full` 把 identity/status/users/audit 放在同一个单节点事务里：一次大批导入失败会连快照一起回滚，且失败信息无法说明审计是否已有进展。

## 设计

### 单页处理器 + 有预算的追赶循环

`ssh_audit_page()` 发出 `vcl audit export --after CURSOR --limit N --jsonl`，并带上每页 SSH deadline 与 stdout 上限。`catch_up_audit_pages()` 逐页循环：

1. 读已提交游标（不读远端水位作为起点，不自动 reseed，不跳到远端最大水位）；
2. 请求一页，解析最后一行的 Protocol v2 meta；
3. 用 `validate_export_batch()` 校验完整批次（protocol/cursor_kind/after/count/node_id/instance_id/export_seq 连续且唯一/next_cursor）；
4. 校验通过后**在同一个事务里**导入审计行、重建该节点的日汇总并推进持久游标（复用 `import_audit_batch`，每页一次 `BEGIN IMMEDIATE`/`COMMIT`）；
5. 只有"已提交游标 ≥ 本页 meta 的 `max_export_seq`"才算追平；页数或总预算用尽但仍有积压 → `MORE_PENDING`。

被拒页（超时、超量、JSON 坏、meta 说谎、身份不匹配、retention gap）整页不导入，**此前已提交的页保持原样**；循环不会把部分 stdout 当成有效批次。

### 参数（现场验证过的起点）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--page-size` | 1000 | 1..5000；1000 与 5000 都在现场验证过，5000 是最大已验证页 |
| `--max-pages` | 300 | 每节点最多提交页数 |
| `--timeout` | 60s | 每页 SSH deadline（临场用 `min(timeout, 剩余预算)`） |
| `--stdout-cap` | 16 MiB | 每页 stdout 上限；超量页整页拒收 |
| `--budget` | 3600s | 每节点**共享墙钟 deadline**，覆盖采集、分页、导入与最终快照 |

每节点只建立**一个** `deadline`，它同时约束：

- 每次 SSH 采集/分页的 timeout（`min(配置值, 剩余预算)`）；
- SQLite 工作：进入导入/快照事务前把 `busy_timeout` 收紧到剩余预算，并安装 progress handler，使长语句（如日汇总重建）可以按 deadline 中断；
- 页提交本身：事务提交前若预算已耗尽，该页**整页回滚**，此前已提交的页与游标保持不动。

预算停止与数据库失败是两种结果：预算耗尽 → `status=more_pending`、`error_code=BUDGET_EXHAUSTED`（phase 为 `audit_import`/`snapshot`/`collection`），可重试；预算未耗尽而 SQLite 报错 → `error_code=DATABASE_ERROR`。页数用尽是 `error_code=PAGE_CAP`，两者都不计入成功。默认值不是实测承诺，正式参数仍需现场复测。

### 状态与消费路径

新增 `more_pending` 状态，并同时接入：

- `sync_report()`：`expired`/`error`/`more_pending` 都计入非成功，`state=PARTIAL`、`ok=false`、进程退出码 2；新增 `more_pending`（节点名列表，**不是**精确剩余条数）。
- `nodes[].more_pending` / `nodes[].audit_pages`：机器字段，`audit_pages` 只统计本次真正提交的页。
- 人读表格：`MORE_PENDING after=… cursor=… pages=…` 加一行"审计尚未追平，先重跑 sync 再 retire/replace"。
- `remediation`：`rerun: vcl-fleet sync --node NAME`（提示可提高 `--max-pages`/`--budget`）。
- UI：`api_sync` 直接用报告状态写操作日志，因此 `MORE_PENDING` 记录为 `PARTIAL`/`ok=false`，不会再被记成成功。

完成判定绑定**已校验批次的水位**：报告给出 `after`/`last_export_seq`/`audit_pages`，不把 `max_export_seq - cursor` 说成剩余条数，也不把"本次连接窗口追平"说成以后不会再有数据。

`max_export_seq` 是完成合同的**必需**字段：它必须存在、为整数、非负、且不低于本页 `next_cursor`。缺失或非法时 `validate_export_batch` 直接以类型化协议错误拒绝（`META_MAX_EXPORT_SEQ_MISSING` 等），没有"短页即追平"的降级分支——短页不能代替水位证明。兼容性核验：最低兼容 Node **v0.3.1**（tag `v0.3.1`）已经包含 Export Protocol v2 与 `max_export_seq`（`git show v0.3.1:lib/vincula-audit.py | grep -c max_export_seq` → 14），所以此处没有旧版本降级合同的需要。

### FR-04 收口（本轮补齐）

- **所有** SSH 层失败（`exit 255`）都归入 transport 类并返回固定模板摘要（如 `SSH transport failed`）：端点、端口与远端文本不再出现在用户可见 detail 中；机器侧从 `facts` 读 `TRANSPORT`/`AUTH_*`/`TIMEOUT`/`HOST_KEY` 等码。
- 协议拒收改为类型化异常 `ExportProtocolError(code, summary, field, expected, actual)`：摘要一律是固定模板（如 `export meta node_id does not match the registry node`），预期/实际身份只保留在 `error_expected`/`error_actual` 机器字段里；JSONL 解析错误也不再拼接原始行内容。
- sync 行新增机器字段：`error_field`、`error_expected`、`error_actual`。

### final sync / retire / replace 门禁

`require_final_sync_ok()` 统一三个分支：`CURSOR_EXPIRED`（提示 `--reseed`）、`MORE_PENDING`（提示重跑 sync 到 ok 再操作）、其他非 ok（final sync failed，不标记退役／不创建备份）。`retire` 与 `replace` 都在做备份/改状态之前调用它。

### `sync --full` 事务合同调整（合同变化）

- 旧：identity/status/users/audit 挤在一个单节点事务；审计导入失败连快照一起回滚，无法说明审计是否有进展。
- 新（顺序即合同）：
  1. 先读一次 identity，**只**用于把审计批次绑定到某个 instance；
  2. 有界分页追赶（每页独立事务、独立提交）；
  3. 追赶**结束后重新采集** identity/status/users，并在提交前复核 `node_id` 与 `instance_id`；
  4. 用**实际采集时间**提交快照事务（不再沿用整轮 Fleet 启动时的时间戳）。
- 复核失败（读取失败、`node_id` 不符或追赶期间 `instance_id` 变化）：已提交的审计页与游标保留，快照保持上一次的值，返回明确失败（`IDENTITY_UNREACHABLE`/`IDENTITY_MISMATCH`/`IDENTITY_CHANGED`，`error_phase=identity`），并在行内报告 `audit advanced N page(s) to cursor C; snapshot refresh did not complete`。
- 快照事务失败时：同样保留已提交审计页与旧快照，`error_phase=snapshot`，并区分 `BUDGET_EXHAUSTED`（预算）与 `DATABASE_ERROR`（数据库）。
- 追赶阶段本身失败（超时/超量/坏 JSON/身份不匹配/retention gap）时不做快照刷新，直接返回对应状态。
- 追赶以 `more_pending` 结束时仍然刷新快照（审计有进展），但整行状态保持 `more_pending`，不汇总成成功。
- 测试注入点从 `VCL_SYNC_FULL_FAIL_AFTER=audit-import` 更名为 `=snapshot`（旧值仍作为别名注入到同一位置，但语义已是"此时审计页已提交"）。

### 节点边界

`sync_nodes_isolated()` 逐节点捕获 `sqlite3.Error`/`OSError`（锁、满盘、数据目录消失）：该节点变成 `DATABASE_ERROR` 行并写 WARNING，其他节点继续；失败状态写回本身是 best-effort（`mark_cursor_status_best_effort`），因为不能假设出错的数据库还能写入"失败状态"，真实状态已经在返回行里。

## 用例与结果

`tests/test-fleet.sh` 新增 42 项 FR-02 断言（含 14 项评审补修），并改写 F7-1 T2 的 `sync --full` 事务断言；`tests/fixtures/fake-ssh` 新增按页故障注入（`VCL_FAKE_EXPORT_FAIL_PAGE`/`HANG_PAGE`/`PRUNE_AFTER_PAGE`/`ALT_INSTANCE_AFTER_PAGE`/`PAD_BYTES`/`LIE_MAX_SEQ`/`DROP_MAX_SEQ`）、追赶期间远端漂移（`VCL_FAKE_IDENTITY_ALT_AFTER`/`ALT_VERSION`/`ALT_INSTANCE`、`VCL_FAKE_STATUS_ALT_AFTER`）与每别名调用计数。

| 用例 | 覆盖 |
| --- | --- |
| **评审补修：追赶后重新采集快照** | `sync --full` 中 5 条积压 / 每页 1 条，第 2 次 identity 读到 0.5.9 → 快照记 0.5.9（顺序证明） |
| **评审补修：追赶期间身份变化** | 追赶提交 3 页后第 2 次 identity 的 instance 变化 → `IDENTITY_CHANGED`、3 页与游标 8 保留、快照仍是旧的 0.3.1 |
| **评审补修：快照使用实际采集时间** | 打桩 `node_deadline_iso` 递增，断言 `synced_at` 是追赶之后的那次采集值，而非整轮启动时间 |
| **评审补修：预算覆盖导入/锁/快照** | `busy_timeout` 收紧并复原、长语句在 deadline 被 progress handler 中断；导入越预算 → 该页回滚且前页保留（`BUDGET_EXHAUSTED`/`audit_import`）；锁等待耗尽预算 → 同样预算停止；预算充足而 SQLite 报错 → `DATABASE_ERROR` |
| **评审补修：缺水位不得算追平** | 删除 `max_export_seq` → `META_MAX_EXPORT_SEQ_MISSING`、0 行导入、游标不动，且 `retire` 被拒 |
| **评审补修：摘要不再泄漏** | 普通连接失败（含 IP/端口）→ `SSH transport failed`/`TRANSPORT`；协议 `node_id` 不匹配 → 固定摘要 + `error_expected`/`error_actual`；probe 对不可达节点同样不含端点 |
| 多页追赶成功 | 5 条 / 每页 2 条 → 3 页、全部导入、游标 5、`ok` |
| 页数预算 → MORE_PENDING | 退出码 2、`state=PARTIAL`、`more_pending=[lax]`、只提交 1 页 |
| 从已提交游标续传 | 重跑后补齐到 5，证明"页级提交"可用 |
| 第二页失败 | 第一页保留（2 行、游标 2），整页拒收，`error_code=REMOTE_ERROR` |
| 第二页超时 | `error_code=TIMEOUT`、`retryable=true`，第一页保留 |
| 超量页 | `error_code=OUTPUT_LIMIT`，0 行导入、游标不动 |
| 页间身份变化 | `error_code=PROTOCOL_INVALID`，第一页保留 |
| 页间 retention gap | `status=expired`，第一页保留 |
| 锁/满盘 | `DATABASE_ERROR`、`retryable=true`、0 页；同一次运行中后续节点仍成功，整体 `PARTIAL` |
| MORE_PENDING 禁止 retire/replace | 两者均退出 1 并打印 `MORE_PENDING`；节点仍 `status=active`、endpoint 未变 |
| final-sync 门禁 | `more_pending`/`error`/`expired` 全部阻塞，只有 `ok` 放行 |
| `sync --full` 快照事务失败 | 快照与 instance_history 回滚、portable history 不半提交、行内报告"审计已有进展、full 刷新未完成" |

回归（本机 WSL2 / Debian 13.3 / Python 3.13.5）：

- `bash tests/test-fleet.sh`：**All 1129 tests passed，exit 0**。
- `SQLITE_TMPDIR=<workspace>/tmp/sqlite-tmp bash tests/test.sh`：**All 1947 tests passed，exit 0**。
- `python3 -m unittest discover -s tests -p 'test_*.py'`：155 项，2 项失败为 `test_verify_extended` 的 root 权限 fixture，已在 `5054e51` 原始工作树复现为既存环境限制。

## 远端 CI

`fd6ab89` 推送后由 Draft PR #13 触发 [CI #94](https://github.com/Marz42/vcl/actions/runs/37755078557)（`event=pull_request`，2026-10-08T09:12:48Z→09:21:52Z），**七个 job 全部 success**：Ubuntu、Debian 12/13、Windows、concurrency、failure-injection、artifact；脱敏快照见 [REMOTE_CI_20261008_FR02.json](REMOTE_CI_20261008_FR02.json)。

## 未关闭边界

- 默认参数（1000/5000 条、60 秒、16 MiB、300 页、3600 秒预算）来自现场小样本与既有上限，**尚未**在正式实现上重新实测；需要现场按大积压节点复测并可能调整。
- `rebuild_daily_usage_for_node()` 仍按页重建，大积压下导入放大问题属于独立的汇总性能优化项，本轮未做。
- 远端 required CI、现场混合 Fleet 复验、Live/H05、24h soak 仍 PENDING；本记录不构成 0.5.x 候选验收。
