# 0.5.2 Findings / Audit / Anomalies / Timeline

日期：2026-10-04；当前分支 `codex/0.5.1`；起点 `fabe8f1f7cb5f39606b4fa8f76d7d9d40401b4ba`。开始时工作区干净，本地/远端branch heads一致。

**后续开发标注：**工作区已开始 [0.5.3 Node Inspect](../0.5.3/SUMMARY.md)。本页 M4 的114/1873与140输入只对应当时冻结候选，现有新代码需独立验证，不能当成当前完整工作区的结果。

**当前0.5.2候选：IMPLEMENTED / PASS OFFLINE / PENDING LIVE / PENDING HUMAN / UNRELEASED。**Node/Controller/common/service/provision payload pin为0.5.2，最低Node仍0.3.1。M4验证时未提交/推送/合并/tag/发布；当前用户已要求0.5.2与0.5.3 M1一并收尾并本地提交，见 [阶段收尾](../0.5.3/CLOSEOUT.md)。远端required CI尚未执行，不复用旧CI #84。

交付14类Node/User Finding、稳定去重/恢复/重开、独立audit-health/v1和user-traffic/v1、rolling median/MAD与持续时长、UNKNOWN保留ACTIVE、schema2缓存迁移/容量覆盖、cache-only CLI/UI及本地Timeline。正式findings/v1、timeline/v1与全部公开schema随Controller ZIP锁定分发；修复独立ZIP provision版本加载依赖源码installer的问题。

最终Linux **114/114 Python PASS，0 skip**；Windows **114项，107 PASS / 7平台skip**；Bash/Fleet **1873项通过**；两端构建、lock/digest、扩大的独立ZIP黑盒、JS和diff检查通过。全部绑定 [140个源码/测试/构建/CI输入](SOURCE_INPUTS_M4.json)，制品digest、失败修复记录与AC映射见 [M4](M4.md)。WSL/fake-SSH/SQLite fixture不能替代真实VPS或24h soak。

| 当前关卡 | 状态 / 证据 |
| --- | --- |
| 合同、实现、自动化集成/失败/权限边界和打包 | PASS OFFLINE；M4与固定manifest |
| 实际主机安全与G4实机 | PENDING LIVE，本轮跳过；[LIVE](LIVE.md)、[SECURITY](SECURITY.md) |
| G5 soak/发布 | PENDING LIVE / UNRELEASED；[SOAK](SOAK.md)；远端required CI未执行 |
| H05（0.5.x），H06/H07 | PENDING HUMAN，本轮跳过等待，不代签；[人工清单](../../plans/VCL_0.5-0.7_Human_Acceptance.md) |
| 后续开发 | 继续0.5.3 Inspect/Drift/Verify，再推进规划内安全实现；未实现功能不归为手工跳过 |

按用户指令“继续在当前分支上开发，跳过但记录所有需要用户手工验证的内容”，所有手工项保留PENDING并记录依赖，见 [延期记录](../../plans/MANUAL_VALIDATION_DEFERRED.md)。0.5.1原实机/soak状态也不改写。

规格：[SPEC](../../specs/V0.5.2_Spec.md)；用户采样：[合同](../../specs/V0.5.2_User_Sampling_Design.md)；操作：[runbook](../../operations/findings-runbook.md)。

历史阶段各自只证明对应冻结输入：M1 [TESTS](TESTS.md) / [ARTIFACTS](ARTIFACTS.md) / [SOURCE_INPUTS](SOURCE_INPUTS.json)；M2 [CONTINUATION](CONTINUATION.md)；M3 [Node](M3_NODE.md) / [User](M3_USER.md)。这些阶段stamp曾为0.5.1；当前候选以M4为准，保留原始失败和验证范围。
