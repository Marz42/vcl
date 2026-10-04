# 0.5.3 Inspect / Drift / Verify — IN PROGRESS

日期：2026-10-04；分支codex/0.5.1；当前Node/Controller stamp0.5.2。

**M1 Node Inspect 已实现，完整0.5.3仍在开发；M1 PASS OFFLINE / UNRELEASED / PENDING LIVE / PENDING HUMAN。**固定只读命令、公开 inspect/v1、16项脱敏指纹、权限/缺工具/预算边界与安装/回滚/制品清单已接入；内部 Controller observe fetch 核对当前身份且无 admin fallback。Windows完整Python 126项，117通过/9平台skip；Linux126/126 Python、1874/1874 Bash/Fleet、两端构建/lock和独立ZIP黑盒通过；全部绑定 [152个固定输入](SOURCE_INPUTS_M1.json)，结果与制品SHA见 [M1](M1_NODE.md)。

Controller缓存/inspect CLI/UI、显式baseline、Drift Finding/Timeline、增强Verify与其兼容回归仍 **UNIMPLEMENTED**，继续按 [SPEC](../../specs/V0.5.3_Spec.md)推进。Node M1不是完整0.5.3完成；0.5.2的114 Python / 1873 Bash与制品只证明其 [M4固定输入](../0.5.2/SOURCE_INPUTS_M4.json)，不能覆盖本阶段。

| 手工项 | 状态 / 本轮处理 |
| --- | --- |
| AC-5.3-01 public/loopback listener与真实OS/主机核对 | PENDING LIVE；候选形成后固定版本/拓扑/测量窗口；本轮跳过等待 |
| AC-5.3-03 真实managed file hash/mtime、restart count与代理前后对照 | PENDING LIVE；本轮仅可实施自动化fixture，现场另记 |
| AC-5.3-04 人为listener、non-secret config/unit drift及恢复 | PENDING LIVE；明确可恢复维护步骤与原始证据后执行；本轮跳过 |
| AC-5.3-05 全Observation链24h RC soak、实际accountd/observer权限 | PENDING LIVE；不复用1000次fake-SSH当24h结果；本轮跳过 |
| H05签署 | PENDING HUMAN；[人工清单](../../plans/VCL_0.5-0.7_Human_Acceptance.md)；不代签 |

依 [用户指令/延期记录](../../plans/MANUAL_VALIDATION_DEFERRED.md)继续实现与离线验证。2026-10-04用户要求当前阶段收尾并本地提交，见 [CLOSEOUT](CLOSEOUT.md)；未操作真实节点、push/merge/tag或发布。候选、测试、制品、Live和H05 evidence随着实际实施补齐，不预填PASS。

具体待验收表：[LIVE](LIVE.md) · [SECURITY](SECURITY.md) · [SOAK](SOAK.md) · [H05](HUMAN_ACCEPTANCE.md)。这些页面均保留PENDING，不预填PASS。
