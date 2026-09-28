# 0.5.1 续开发与验证

日期：2026-09-28；基线：`112dfd3338f28c1f9ecdedf4fbcbde5342ad2a95`，分支 `codex/0.5.1`。用户确认本轮完成代码与本地验证，现场验收另行安排。状态：**IN PROGRESS / PENDING LIVE / UNRELEASED**。

[分支清理记录](../../plans/BRANCH_CLEANUP_2026-09-28.md)保存删除前 SHA、合并依据和本机恢复备份。2026-09-27 的 TESTS / ARTIFACTS / SOURCE_INPUTS 是历史基线证据，不作为本轮修改后的测试或制品结果。

## 补齐的行为与回归

| Spec 要求 | 缺口与修复 | 新回归测试（`tests/test_monitor.py`） |
| --- | --- | --- |
| §2 单节点故障隔离、指数退避 | None/list/非法状态可能抛异常终止整轮；OK 坏 snapshot 会触发 probe 并错误重置退避。采集边界和 writer 复用验证，再调度 probe/backoff | `test_malformed_fetch_is_isolated_without_probe_or_raw_error` |
| §2 received_at、独立 probe deadline | received_at 原在缓存写入时取值，包含慢 probe 和其他节点写库等待。现为 telemetry fetch 完成时采集，probe 不改变该时间 | `test_received_at_is_capture_time_before_slow_probe` |
| §2 乱序/复位不产生伪速率 | 同 instance 内重复/倒退的 observed_at 曾替换有效基线。现按 TELEMETRY_STALE 降级 observation 并保留最后有效指标；恢复后从最后有效样本计算 | `test_delayed_and_replayed_samples_do_not_replace_rate_baseline` |
| §3 坏行隔离 | 深层 JSON 可能触发 RecursionError；latest reader 隔离、显式 monitor 可替换坏行；坏 rollup 不阻止新样本事务 | `test_deeply_nested_cache_row_is_isolated_and_replaceable`、`test_deeply_nested_rollup_does_not_abort_new_observation` |
| §3 latest 上限与截断 | 历史 registry 累计到 1024 个身份后，新节点永久无法写入。现按最旧 at 淘汰 latest 并记录 truncated_health_latest，raw 历史遵循原保留期 | `test_registry_churn_evicts_oldest_latest_with_truncation_marker` |
| §3 锁/满盘属于本机错误 | 增加真实 SQLite 写锁及事务末尾 SQLITE_FULL 注入；保留旧健康/历史，解除后恢复写入 | `test_locked_cache_preserves_health_and_recovers`、`test_disk_full_mid_transaction_rolls_back_samples_and_health` |
| G1 独立 probe 失败分类 | 增加 DNS/TLS/connect 返回码检查，确认仅代理维度降级，子进程回收且不暴露原始输出 | `test_dns_tls_and_connect_failures_only_degrade_proxy` |
| §4 缺 probe 证据为 UNKNOWN | 无效 reason 类型不再抛异常；缺配置/运行时不能因 false 标志而显示代理故障 | `test_malformed_or_unconfigured_probe_is_unknown` |

Linux root 权限测试增加 discovery 的平台条件：Windows/非 root 环境明确 skip；直接运行该独立测试文件仍拒绝不合适的环境。Linux CI root gate 继续实际执行这些测试。新增 Windows CI 检查，避免只覆盖 Linux Controller。

## 本地验证

当前主机为 Windows；可用 bundled Python，未安装可用 WSL。初次全量 unittest discovery 误运行 Linux root suite，出现平台 API 错误；增加显式平台条件后重新执行。

```powershell
python -m unittest discover -s tests -p 'test_*.py'
node --check lib/vincula-ui/static/app.js
git diff --check
```

结果：**52 tests，46 PASS，6 平台 skip，0 failure/error**。6 skip 为 5 项真实 Linux UID/GID 权限测试及 1 项 SO_PEERCRED，不能折算为 Windows 通过。JS 语法与 diff 检查通过。

新增关键回归先在旧实现上复现了乱序样本误判 HEALTHY、malformed fetch 中断/错误退避、probe 推迟 received_at、latest 无淘汰能力，再修复并通过。

Linux 全量 Bash/Fleet、root 权限和新候选制品通过 draft PR 的 CI 验证；实际结果与候选 SHA 待回填。未执行真实 VPS、2h/24h soak、升级回退、发布或主线合并。
