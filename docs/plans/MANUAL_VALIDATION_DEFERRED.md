# 手工验证延期记录

日期：2026-10-04。用户当前指令：**“继续在当前分支上开发，跳过但记录所有需要用户手工验证的内容。”**

执行规则：在当前 `codex/0.5.1` 分支继续可自动化的实现与离线验证，不因需要用户执行/签署的步骤而等待。手工项保持原始 PENDING 状态并记录依赖、判据和后续证据位置；这不是 PASS、风险豁免、发布或主线合并授权。实施计划中的人工放行顺序仍用于正式验收；本轮按最新用户指令跳过开发过程中的等待。

| 手工项 | 保留状态 | 记录位置 / 执行条件 |
| --- | --- | --- |
| 0.5.1 L1～L7，systemd/sshd、upgrade/rollback、2h/24h soak | PENDING LIVE；本轮跳过 | `docs/evidence/0.5.1/LIVE.md`、`SOAK.md`；真实 VPS 与固定候选 |
| 0.5.2 accountd 故障、用户负载、service disruption、真实资源异常与 soak | PENDING LIVE；本轮跳过 | `docs/evidence/0.5.2/LIVE.md`、`SOAK.md`；完整候选及受控客户端/节点 |
| H05（0.5.x）、H06（0.6.x）、H07（0.7.x）签署 | PENDING HUMAN；本轮跳过 | `VCL_0.5-0.7_Human_Acceptance.md`；由人工检查具体候选与证据，代理不代签 |
| 后续子版本的全部真实节点/客户端/拓扑、硬件/网络、持续 soak 验收 | PENDING LIVE；随实施逐项补清单 | `VCL_0.5-0.7_Implementation_Plan.md` 各 AC/G4/G5 与对应版本 evidence；不得用 fixture 代替 |
| QoS/transport 指定实机 research/benchmark 中需要用户提供的环境/数据 | PENDING LIVE / RESEARCH；本轮跳过等待 | 0.6.2 Research Gate、0.7.1 Transport Decision Gate；不从未验证 backend 推断生产可用 |
| 人工批准执行高风险生产策略/路径/升级/发布 | PENDING HUMAN；本轮不执行 | 仅实现可审查的本地 contract/plan/guard；实际执行另有授权与运行环境 |

新增手工项必须补到对应版本的证据矩阵；完成自动化仅可标 PASS OFFLINE。目标仍是继续整个授权开发范围，不将未实现功能记作“手工项已跳过”。

2026-10-05：0.5.3本地功能与离线RC收口见[RC](../evidence/0.5.3/RC.md)。支持OS/observer/accountd现场、listener/config/unit drift恢复与真实代理前后、AC-5.3-05连续24h soak均PENDING LIVE；H05/H06/H07 PENDING HUMAN，remote required CI NOT RUN。
