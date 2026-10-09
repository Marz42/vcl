# 现场验证准备记录 — 2026-10-08

**PREPARED / NOT EXECUTED。**本页记录"新候选冻结 + Controller 优先现场验证"的准备工作与其中一个准备期缺陷的修复；它不是现场结果，不改写任何 PENDING 状态，也不授权升级或发布。

## 本轮产出

| 产出 | 位置 |
| --- | --- |
| 冻结与验证方案（含逐条人工步骤） | [RC_0.5.3_VERIFICATION_PLAN.md](../../plans/RC_0.5.3_VERIFICATION_PLAN.md) |
| 方案入口 | [docs/README.md](../../README.md)、[可靠性待办](../../plans/Fleet_Recovery_Reliability_Backlog.md)、[延期记录](../../plans/MANUAL_VALIDATION_DEFERRED.md) |
| 准备期缺陷修复 | `lib/workspace.py`（`_import_staging_dir`）、`tests/test-fleet.sh` F7-2 T3 |

方案要点：阶段 F 冻结候选（回归、固定 `SOURCE_DATE_EPOCH` 制品、`check-controller-artifact.py`、固定输入清单、远端 CI 快照）；阶段 A **只验证 Controller**，用隔离的 `VCL_FLEET_HOME` / `VCL_FLEET_LOCAL_STATE` / `XDG_CONFIG_HOME` 三元组覆盖基线、能力矩阵、observe 认证负例、大积压有界追赶、限一页续传、`sync --full` 与失败恢复（超时/预算/超量页/锁等待/中断）；阶段 B/C/D 为七台混合复验、24h soak 与 H05 签署。红线明确写入：不得为造积压重置生产游标、不得在生产缓存上做故障注入、验证期间不改 Node、未授权不发布不升级。

## 准备期发现的缺陷（已修复并回归）

在按方案验证隔离流程时发现：`workspace import` 的暂存目录优先取 `~/tmp`（F7-2 设计），当该路径已存在但不可写时，`tempfile.mkdtemp` 抛出裸 `PermissionError`，导入以未处理异常结束；而同一个 `fleet_id` 导入到第二台工作区根、且没有隔离 `VCL_FLEET_LOCAL_STATE` 时，`workspace verify` 报 `WORKSPACE_DIVERGED`（预期冲突检测，方案已写明处理方式）。

修复：新增 `_import_staging_dir()`，`~/tmp` 不可用时回落到系统临时目录，两者都不可用时以单行明确报错，不再输出裸回溯。回归：`F7-2 T3 import falls back when ~/tmp is unusable`（构造 `$HOME/tmp` 为普通文件，断言导入成功、验证通过、注册表保留）。

## 验证与远端 CI

- `bash tests/test-fleet.sh`：**All 1132 tests passed，exit 0**。
- `SQLITE_TMPDIR=<workspace>/tmp/sqlite-tmp bash tests/test.sh`：**All 1950 tests passed，exit 0**。
- 远端 required CI：[run #99](https://github.com/Marz42/vcl/actions/runs/37873004977)（`944238c`）七个 job 全绿。

## 适用范围与后续

- FR-02 的源码绑定仍是 `f37c50a`（[FR-02 记录](FR02_BOUNDED_SYNC.md)，[CI #97](https://github.com/Marz42/vcl/actions/runs/37766606635)），本页只新增 `lib/workspace.py` 的暂存回落与验证方案文档；**最终候选绑定在阶段 F 重新生成**，不复用本页计数。
- 现场项仍为 **PENDING LIVE**（隔离 Controller 验证、七台复验、24h soak），H05 仍为 **PENDING HUMAN**；执行人按方案逐步操作并把原始证据放在受控的现场目录，仓库只保留脱敏结论。
