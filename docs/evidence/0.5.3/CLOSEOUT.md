# 2026-10-04 阶段历史收尾

分支 `codex/0.5.1`，开发起点 `fabe8f1f7cb5f39606b4fa8f76d7d9d40401b4ba`。用户本次要求：**“检查目前开发状态，把当前阶段做一个收尾然后提交。”**本记录与阶段源码一起提交；实际提交身份与hash以Git记录为准。

## 封存范围

- 0.5.2 Findings / Audit / Anomalies / Timeline 的完整离线实现：14类Node/User Finding、稳定生命周期、独立audit/user sampling、rolling median/MAD、持久化与cache-only CLI/UI、公开合同及独立制品加载修复。
- 0.5.3 M1 Node Inspect：有界只读inventory、16项受管脱敏指纹、inspect/v1、observer固定argv与Netlink读取许可、安装/manifest/升级checkpoint/rollback/卸载、两端制品和内部身份绑定observe fetch。
- Node/Controller及payload pin保留 `0.5.2`，最低Node `0.3.1`；没有将未完成的完整0.5.3提前标为交付。M2 cache/baseline/Drift与增强Verify仍未实现，当前只有[设计草案](../../specs/V0.5.3_Baseline_Design.md)。本次收尾不扩展M2。

## 提交前核对

[最新M1 evidence](M1_NODE.md)与[152个固定源码/测试/构建/CI输入](SOURCE_INPUTS_M1.json)逐项hash一致；原始制品和日志hash一致，版本pin一致。功能源码没有在测试后继续修改，因此复用已绑定的通过结果，未为本次文档收尾重复跑长循环。

| 核对项 | 已证明的结果 |
| --- | --- |
| Linux Python | 126/126 PASS，0 skip |
| Windows Python | 126项，117 PASS / 9平台skip |
| Bash/Fleet | 1874/1874 PASS |
| Node/Controller构建与lock | PASS；Node release.lock17成员，Controller附带九份公开schema |
| 独立ZIP黑盒 | PASS；payload/provision/upgrade pin、Node Inspect只读、packaged observe身份绑定、cache-only Findings/Timeline |
| JS、whitespace、文档链接 | PASS；Git待提交blob另与固定输入核对，保留原有executable mode |

0.5.2的[M4](../0.5.2/M4.md)与140输入作为历史快照保留；不能将其结果当成现有新增Inspect源码的验证。未完成或失败的测试运行均保留原始记录，不改写成PASS。

## 正式验收与后续边界

| 项目 | 状态 / 记录 |
| --- | --- |
| 本地阶段提交 | 用户已明确授权；本记录随源码提交，hash见Git |
| 支持OS/VPS现场、实际observer/accountd权限、listener/config/unit drift与代理前后对照 | PENDING LIVE；[LIVE](LIVE.md)、[SECURITY](SECURITY.md) |
| 连续24h全Observation RC soak | PENDING LIVE；[SOAK](SOAK.md) |
| H05 / H06 / H07 | PENDING HUMAN；[H05](HUMAN_ACCEPTANCE.md)、[阶段人工清单](../../plans/VCL_0.5-0.7_Human_Acceptance.md) |
| 当前新提交的远端required CI | NOT RUN；未推送，不复用旧CI #84 |
| push / merge / tag / release / production apply | 未执行；本次仅本地提交 |
| 后续开发 | M2缓存与显式baseline/CAS/Drift、增强Verify、完整0.5.3RC，然后按原实施计划继续；未实现项不归为手工跳过 |

人工等待仍按[原用户指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)跳过并记录；本地提交不等于实机、Human Gate或发布通过。

2026-10-05后续：用户要求继续完成0.5.3，M2/M3与完整本地RC见[RC](RC.md)。本页封存当时事实；当前stamp与剩余门禁以[SUMMARY](SUMMARY.md)为准。
