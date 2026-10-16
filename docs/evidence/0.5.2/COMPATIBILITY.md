# 0.5.2 兼容性范围

当前源码 stamp 0.5.1，分支 codex/0.5.1，完整 0.5.2 尚未发布；行为按 capability 协商。

| 组合 / 合同 | 本地验证方式 | 结论 / 限制 |
| --- | --- | --- |
| 新 Controller + 无 audit-health/v1 capability 的 Node | 单元 fake-SSH：不发 audit 命令，UNSUPPORTED | PASS OFFLINE；telemetry/v1 原路径保留 |
| 新 Controller + audit-health/v1 Node | 实际 SQLite、身份/instance/capability、超时/错误/预算 fixture | PASS OFFLINE；真实 VPS PENDING LIVE |
| 新 Controller health/API 消费者 | 真实 cache 输出对 shipped monitor/v1 schema | PASS OFFLINE；私有 audit/progression/baseline 字段不泄漏 |
| 新 Controller 前台 monitor 汇总 | 真实 run_cli JSON 对 monitor/v2 schema | PASS OFFLINE；旧 v1 run 消费者必须升级解析，不能默默接收额外计数 |
| Node telemetry/v1 消费者 | 既有 schema/读只回归 | PASS OFFLINE；独立诊断不扩展 v1 |
| Linux Controller / 包 | Ubuntu 24.04 WSL root + 独立 ZIP 黑盒 | 以 CONTINUATION 对应候选日志为准；不是 VPS Live |
| Windows Controller / 包 | Python discovery，平台权限/socket skip 明列 | 以 CONTINUATION 对应候选日志为准；Windows GUI/SSH 实机未验收 |
| Debian 12/13、其他声明 OS/arch | 本轮未新触发远端 CI / 实机 | PENDING；历史 CI #84 不覆盖本轮修改 |

受限 observer 随 Node 包更新固定白名单；旧 Node 不强制升级。真实降权 daemon、restricted SSH 和升级保留 identity/accounting/URI 的矩阵继续 **PENDING LIVE，本轮跳过**，H05 **PENDING HUMAN**。
