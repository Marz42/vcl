# 0.5.2 M2 续开发

日期：2026-10-04；当前分支 `codex/0.5.1`。用户设定持续目标：继续开发，跳过并记录所有需要用户手工验证的内容。[延期记录](../../plans/MANUAL_VALIDATION_DEFERRED.md)定义本轮执行边界。

状态：**M2 PASS OFFLINE / 当前 M3 IN PROGRESS / 完整 0.5.2 IN PROGRESS**。M1 的 1867 Bash/Fleet / 71 Python 与制品结果仅绑定其原 SOURCE_INPUTS；M2 由 [SOURCE_INPUTS_M2](SOURCE_INPUTS_M2.json) 的 111 个产品/测试/构建输入独立绑定，不覆盖随后 M3 修改。

本轮新增独立 `audit-health/v1` / `vcl telemetry audit --json`，保留严格 telemetry/v1 和公共 monitor/v1 形状。诊断使用只读 SQLite 与有界 quick_check，区分 MISSING、UNREADABLE、SCHEMA_MISMATCH、CORRUPT、UNKNOWN；响应仅 identity、时间、数值、固定状态，无 SQL/异常原文。

accountd 的 heartbeat_at 与 last_success_at 分离：失败 poll 仍有 loop heartbeat，不把空闲/失败采集猜成 daemon 消失。Controller 按 capability 协商、observe 路由和当前 instance 核验；诊断超时不丢弃已取得的 telemetry。受限 observer 只增加固定只读命令，零 admin fallback。

缓存内部保存诊断，公共 monitor/v1 不添加字段；Findings 显式消费内部诊断，补 SCHEMA_MISMATCH / ACCOUNTING_DB_CORRUPT、pruned watermark gap 与 EXPORT_SEQUENCE_REGRESSION。按同 instance 独立跟踪 export progression 和回放时间水位；stationary counter 合法，不因长连接或空闲误报。包含坏 DB 的新诊断也推进时间水位，防止旧健康响应误关较新的异常。

M1 新增 finding_write_errors 对运行汇总构成合同扩展，M2 将前台 monitor JSON 明确版本化为 monitor/v2；health/cache/API 保留 v1。已补正式 audit-health/v1、monitor/v2 schema、六个诊断 fixture 与真实 JSON 输出验证。

## 实际验证

| 验证 | 冻结 M2 候选结果 |
| --- | --- |
| Windows Python discovery | 86 项，80 PASS / 6 Linux 平台 skip，0 failure/error |
| WSL Ubuntu 24.04 root Python | **86/86 PASS，0 skip** |
| WSL 全量 Bash/Fleet | **All 1868 tests passed**；fake-SSH/fixture，不是实机 |
| Node/Controller 构建、lock/digest、独立 ZIP 黑盒 | PASS；包含 audit_health.py，无 repository/PYTHONPATH 依赖 |
| JS / git diff | PASS（M2 冻结时检查）；后续 M3 另有记录 |

新增 tests/test_audit_health.py 共 15 项：真实只读 SQLite/结构/损坏/权限/预算、失败 poll heartbeat、双层 schema 正反例、capability/身份/超时、私有缓存/公共 v1、gap/schema/heartbeat UNKNOWN、真实 v2 run、推进/静止/回退/回放/实例复位、回退 Finding 恢复和坏 DB 回放水位、旧/缺失诊断不误关告警。初期 debounce 用例将 UNKNOWN 后首次健康误认为 RECOVERING，已按原状态机调整并分别验证 DEGRADED→RECOVERING→HEALTHY；未改业务规则掩盖失败。旧 Bash commit-failure 注入改在第二次 commit 失败，继续覆盖采集事务而非提前止于新增 heartbeat commit。

原始本机 ignored 日志/制品：tmp/linux-validation-20261004-m2-final/，各步骤 exit_code=0；此前 M2 初始合同验证 82 Python / 1868 Bash 另在 tmp/linux-validation-20261004-m2/，不覆盖最终新增推进逻辑。SOURCE_DATE_EPOCH=1790679997；base commit fabe8f1f7cb5f39606b4fa8f76d7d9d40401b4ba；未提交/推送/发布。最终 SHA-256：

| 制品（stamp 仍 0.5.1） | SHA-256 |
| --- | --- |
| vincula-node-0.5.1.tar.gz | 754a02015c90f664c180872e7d94bf73bacbd5a4c42170ddde284980df6d4edf |
| vincula-controller-0.5.1.zip | 0757ede5cd03fa1783d04d73af202de49bee106b8dbe7dbb1bfb87b087c569f3 |
| payload-manifest.json | e3c73b75a3d9fa385aa46e21ed38a02de362acf8634547ca2b5d878ce4b4c032 |

后续 [M3_NODE](M3_NODE.md) 继续统计基线、Node 检测和 service lifecycle；用户级 detector 与完整版本收口仍待实现，不把 M2 子阶段通过当成整版交付。

**Human Gate：PENDING HUMAN；实机与 soak：PENDING LIVE；本轮跳过但不记 PASS。**
