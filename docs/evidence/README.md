# Evidence index

验收与 LIVE 证据目录。**只读**：不要为统一文风而改写历史记录（尤其含主机信息的 LIVE 原文）。

| 目录 | 说明 |
| --- | --- |
| [`0.5.3/`](0.5.3/SUMMARY.md) | 当前0.5.x候选；[2026-10-07收口](0.5.3/PHASE_05_CLOSEOUT.md)、Verify修复与CI绑定；[2026-10-08 FR-01凭据隔离](0.5.3/FR01_CREDENTIAL_ISOLATION.md)（`7836b14`，[远端CI #88](0.5.3/REMOTE_CI_20261008.json)全绿）、[FR-03/04认证分类与错误摘要](0.5.3/FR03_FR04_ERROR_MODEL.md)（`4e5d27f`，[远端CI #90](0.5.3/REMOTE_CI_20261008_FR0304.json)全绿）、[FR-02有界审计同步](0.5.3/FR02_BOUNDED_SYNC.md)（评审补修 `f37c50a`，[远端CI #97](0.5.3/REMOTE_CI_20261008_FR02_FIXES.json)全绿；未发布、现场未验）；历史RC/M1/CLOSEOUT保留；Human/实机/soak仍PENDING [现场验证准备（方案 + 准备期缺陷）](0.5.3/VERIFICATION_PREP.md)（PREPARED / NOT EXECUTED，[CI #99](0.5.3/VERIFICATION_PREP.md)）； [0.5.3 冻结候选](0.5.3/CANDIDATE_FREEZE.md)（Node `8abe989c`/Controller `65dbcc7b`，[CI #100](https://github.com/Marz42/vcl/actions/runs/37874931681)全绿；PREPARED→待现场）；[阶段 A Controller 隔离验证](0.5.3/PHASE_A_CONTROLLER.md)（2026-10-09 现场执行，EXECUTED / PASS WITH FINDINGS：七台基线 5 OK + 2 `AUTH_FAILED/AUTH_LIMIT`、隔离导入 `fleet_id` 一致、限一页续传 `0→…→1,280,175`、完整追平 254 页/1,269,177 行/1091s、`sync --full` 快照 fresh、超时/超量/预算/导入期锁回滚/中断恢复全部取得确切文本，生产指纹五轮一致；阶段 B/C/D 仍 PENDING；[CI #37938802704](0.5.3/REMOTE_CI_20261009_PHASE_A.json) 七 job 全绿）；[阶段 B 七台生产上下文复验](0.5.3/PHASE_B_FLEET.md)（2026-10-09/10，10h45m 窗口，EXECUTED / PASS：B1/B2 与阶段 A 无差异、五台可达节点覆盖率 0.91–0.97、0.3.x 亦有样本、两台 `AUTH_FAILED` 为观测盲区、Node 侧实例/重启/服务零变化、生产指纹两轮一致；F-4 停止时刻陈旧判定待阶段 C 复测；C/D 仍 PENDING）；[阶段 C 24h soak](0.5.3/SOAK.md)（2026-10-10 起：1000× telemetry 突发 + 节点状态增长 **PASS LIVE**（ok=1000、无重启、字节/FD/RSS 均在阈值内，digest `3132226…`），24h 连续观测腿 RUNNING；代理维度按执行人决定未覆盖；24h 收尾与 H05 仍 PENDING）； |
[现场验证准备（方案 + 准备期缺陷）](0.5.3/VERIFICATION_PREP.md)（PREPARED / NOT EXECUTED，[CI #99](0.5.3/VERIFICATION_PREP.md)）；
| [`0.5.2/`](0.5.2/SUMMARY.md) | 0.5.2历史候选；M1～M3历史验证、M4全量收口与输入绑定；Human Gate / 实机延期记录 |
| [`0.5.1/`](0.5.1/SUMMARY.md) | 0.5.1 本地开发交付；真实 VPS / 24h soak / 发布保留 PENDING |
| [`0.5.0/`](0.5.0/SUMMARY.md) | Observation Foundation 已有离线/Live/soak记录；以原文适用候选和测量限制为准 |
| [`0.4.5/`](0.4.5/SUMMARY.md) | Controller 0.4.5 / Node 0.3.2（含 LIVE） |
| [`0.4.4/`](0.4.4/SUMMARY.md) | UI v2 |
| [`0.4.3/`](0.4.3/SUMMARY.md) | Adopt / Provision |
| [`0.4.2/`](0.4.2/SUMMARY.md) | Workspace / sync --full |
| [`0.4.1/`](0.4.1/SUMMARY.md) · [`0.4.1-m05/`](0.4.1-m05/SUMMARY.md) | 0.4.1 系列 |
| [`0.3.1-final/`](0.3.1-final/SUMMARY.md) | Node 0.3.1 冻结 |
| [`0.3.1-live/`](0.3.1-live/SUMMARY.md) | B14 live replace **PASS** |
| [`0.3.1-rc2/`](0.3.1-rc2/README.md) | RC2 证据 |
| [`0.2.4-0.2.6-live/`](0.2.4-0.2.6-live/README.md) · [`0.2.4-freeze/`](0.2.4-freeze/README.md) | 更早 LIVE / freeze |

当前操作手册：[`../user-guide.md`](../user-guide.md)。历史 evidence 内可能仍链到已迁移的旧路径（如 `fleet.md`）；以本索引与新手册为准，不批量改写 evidence 正文。
