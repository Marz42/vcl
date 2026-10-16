# 0.5.3 Inspect / Drift / Verify — 本地候选

**2026-10-07当前记录：**已复核完整0.5.x实现并修复Verify的坏heartbeat、准确loopback监听与probe后身份失效；独立ZIP的16份合同和四个cache-only入口检查纳入artifact CI。开发停在0.5.3，不进入0.6.x。最新本地输入/制品/回归与远端CI的适用范围见[PHASE_05_CLOSEOUT](PHASE_05_CLOSEOUT.md)；下列2026-10-05状态是当时快照。
日期2026-10-05；分支codex/0.5.1；Node/Controller/payload stamp0.5.3，minimum Node0.3.1。

**M1–M3 IMPLEMENTED / UNRELEASED / PENDING LIVE / PENDING HUMAN。**已完成Node只读Inspect、Controller低频采集与独立缓存、cache-only CLI/API/UI、显式基线SHA CAS与七类Drift Finding/Timeline、八项增强Verify及旧JSON兼容。当前完整离线验证、原始日志/制品SHA与固定输入见[RC](RC.md)。

[M2 Controller](M2_CONTROLLER.md)记录缓存/基线/Drift；[M3 Verify](M3_VERIFY.md)记录增强合同与边界。旧[M1](M1_NODE.md)、[当时CLOSEOUT](CLOSEOUT.md)及[SOURCE_INPUTS_M1](SOURCE_INPUTS_M1.json)保留为0.5.2 stamp的历史输入，不能替代当前RC。0.5.2 M4同样是历史快照。

| 尚待完成的正式验收 | 状态 / 本轮处理 |
| --- | --- |
| AC-5.3-01支持OS/IPv4/IPv6 listener与实际observer权限 | PENDING LIVE；离线fixture与WSL不替代真实主机 |
| AC-5.3-03真实文件hash/mtime、restart count、实际客户端代理前后对照 | PENDING LIVE；本轮仅临时文件只读回归 |
| AC-5.3-04人工listener/config/unit drift与恢复、Verify分项现场核对 | PENDING LIVE；保留可恢复维护步骤和原始证据要求 |
| AC-5.3-05全Observation连续24h soak、实际accountd/observer权限 | PENDING LIVE；1000次fake-SSH不是24h现场证明 |
| H05/H06/H07签署 | PENDING HUMAN；[人工清单](../../plans/VCL_0.5-0.7_Human_Acceptance.md)，未代签 |
| 当前候选remote required CI | NOT RUN；定义已扩展Linux完整Python suite，待推送后的远端执行 |
| 发布/生产apply/合并/tag | 未执行；本地候选与本地提交不等于正式发布 |

依[用户延期指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)跳过人工等待，保留PENDING；最新用户要求继续完成0.5.3。具体记录：[LIVE](LIVE.md) · [SECURITY](SECURITY.md) · [SOAK](SOAK.md) · [H05](HUMAN_ACCEPTANCE.md)。
