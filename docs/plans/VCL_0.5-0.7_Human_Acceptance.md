# VCL 0.5.x～0.7.x 大阶段人工验收

> 对应方案：[实施与验收方案](VCL_0.5-0.7_Implementation_Plan.md)。本文件是待执行清单与签署模板，不是已经通过的验收证据。
>
> 三个关卡初始状态均为 **PENDING HUMAN**。只有指定人工验收人检查具体候选与证据后，才能填写 PASS；工具、CI、实施代理不能代签。

## 1. 验收安排与入口条件

| 关卡 | 候选版本 | 人工验收目标 | 实际记录落点（执行时建立） | 初始状态 |
| --- | --- | --- | --- | --- |
| H05 | 0.5.3 / 0.5.x RC | 可信 Observation，不改变数据面 | `docs/evidence/0.5.3/HUMAN_ACCEPTANCE.md` | PENDING HUMAN |
| H06 | 0.6.4 / 0.6.x RC | 声明→计划→执行→验证→回滚，策略/出口隔离 | `docs/evidence/0.6.4/HUMAN_ACCEPTANCE.md` | PENDING HUMAN |
| H07 | 0.7.4 / 0.7.x RC | 静态两跳、人工切换、计量与容量 | `docs/evidence/0.7.4/HUMAN_ACCEPTANCE.md` | PENDING HUMAN |

每次提交人工验收前，实施者应完成：

- 固定候选 commit、Controller/Node 制品 digest、配置 revision、兼容矩阵，提供版本安装/升级/回滚说明。
- 完成该大阶段所有子版本的 G0～G5 必需项；必需 Live 项不能处于 PENDING；没有 P0/P1、未解释数据损坏或 secret 泄漏。
- 提供固定候选的 ≥24h 综合 soak 报告。历史/fixture/真实现场/保存快照复核分别标注；复用证据必须说明当前候选与原候选的关系及影响分析。
- 准备具体演示步骤、匿名节点与用户标识、可恢复的测试资源、维护窗口、前后状态、每个故障的恢复办法。
- 交付一页验收摘要：交付范围、关键风险、已知限制、未完成可选项、逐项证据链接以及建议结论；留空人工签署栏。

实施者负责准备与技术解释；现场执行者负责按步骤操作并恢复；人工验收人负责判断预期是否满足、用户工作流是否可用及最终签署。现场执行者与验收人可以是同一人，但自动化成功不能取代人工判断。

Live 只在明确选择的节点和测试身份上进行；通知测试使用已明确授权的测试接收端。H05/H06/H07 是未来验收关卡，本次写计划无需先取得现场操作授权。

## 2. 共同操作与记录规则

1. 开始前记录候选、拓扑、用户/Node/Path 匿名标识、时间窗口、baseline。敏感 profile/密钥只在受限环境比对，文档记录一致性结果，不粘贴 secret。
2. 健康类场景同时检查 CLI/UI 与真实代理流量；mutation 场景先审 plan，再显式批准执行；不只凭“命令返回成功”判断通过。
3. 故障注入后观察原始事实、状态迁移、Finding/通知、用户影响、journal；执行恢复并验证恢复态。不能恢复时停止后续受影响用例，记录 FAIL/BLOCKED。
4. 每行填写实际步骤、结果、时间、证据路径/digest、执行人及验收人结论；`PASS OFFLINE` 不填作 `PASS LIVE`，未操作不填 PASS。
5. 对 ≥24h soak、跨版本升级、benchmark 等长场景，人工可检查并见证已完成的合格记录，无需为了签署机械重跑；有候选/环境差异或证据缺口则补测。
6. Human case 与实施方案 AC 互相映射。这里是综合人工验收，不能替代子版本的全部 Live Matrix。

<a id="h05-05x-observation-plane"></a>

## H05：0.5.x Observation Plane

**前置环境：**至少一台可恢复的真实 0.5.x Node、独立 observe/admin identity、专用代理测试身份、真实 HTTPS 目标；旧 Node 0.3.1/0.3.2 的兼容/升级记录；≥10 节点受控混合监控矩阵及固定 RC 的 24h soak。

| ID | 人工操作或见证步骤 | 通过标准 | 证据/AC |
| --- | --- | --- | --- |
| H05-01 正常事实层 | 同时打开 Fleet/Node 视图与 CLI；现场比对资源、服务、telemetry age、真实代理 probe；检查 10 节点/2h 和 24h 记录 | 各健康维度、时间和缺测可解释；采样不拖垮整轮；代理可用由真实连接证明 | AC-5.1-01～03、05～06；monitor/soak/CLI/UI 记录 |
| H05-02 凭据与权限 | 独立 observer 读取；尝试其 shell/sudo/mutation/转发；撤销 observe 后再读，恢复后重试；核对 accountd 进程身份与文件访问边界 | 合法读取成功，越权拒绝；AUTH_FAILED 无 admin fallback；accountd 非 root 且无 secret 越权；SEC-050-01/02 已关闭 | AC-5.1-04；SECURITY、脱敏 SSH 拒绝结果 |
| H05-03 代理与审计分离 | 受控停止 sing-box，观察 Proxy Health；恢复后停止 accountd，同时持续真实用户流量；最后恢复 accountd | 代理故障被准确识别；accounting 降级/AUDIT_STALLED，但代理继续；恢复后 Health/Finding 正确恢复 | AC-5.1-02、05；AC-5.2-02、05 |
| H05-04 不可达与 Controller 离线 | 阻断测试 SSH 后恢复；再停止 Controller ≥5 分钟，同时持续真实用户代理 | SSH 故障按 SUSPECT→UNREACHABLE，恢复 RECOVERING→HEALTHY；Controller 离线不改变策略或中断既有代理服务 | 0.5.0 L5；AC-5.1-05～06；状态时间线、真实连接记录 |
| H05-05 Finding 与 Timeline | 注入流量/连接异常与正常波动对照；核对一次真实 service disruption；审阅 export gap/DB corrupt 用例 | 异常有证据和解释，正常波动无持续误报；去重/恢复正确；Timeline 能关联事件；无自动修复 | AC-5.2-01～06；Finding/Timeline/注入记录 |
| H05-06 Drift 与只读 | 显式新增测试 listener、修改受管非 secret unit/config，再 inspect/verify；恢复；比较前后文件与 restart count | 非预期 listener/drift 检出，恢复 MATCH；verify 与人工核对一致；观察过程零服务重启/配置写入 | AC-5.3-01～04；人工 inventory、指纹/mtime/重启计数 |
| H05-07 兼容与升级连续性 | 检查旧 Node 缺 capability 的行为；见证两来源版本的升级记录、身份/URI/accounting 对照及可用性时间序列 | 旧节点 UNSUPPORTED 不误报故障；原客户端 profile 可用；新连接不可用上界 ≤3s。只有“一秒轮询未见失败”不能代替精确补证 | 原 AC-5.0-03/13；实施方案 §4.1；补充 Live 数据 |
| H05-08 综合收口 | 审阅 1000 次 telemetry、各版本 gate、RC 24h soak、store 清理/损坏策略、手册；检查 release evidence 脱敏 | 必需项全通过，无 P0/P1/未知断流/状态无界增长；schema、能力、兼容与用户文档一致 | 原 AC-5.0-10；AC-5.3-05；各版本 SUMMARY/SECURITY |

**通过后：**可进入 0.6.0 的 G0/实现。未通过时先修复 0.5.x，H05 保持 PENDING/FAIL；不要代填“基本通过”。

<a id="h06-06x-declarative-controller"></a>

## H06：0.6.x Declarative Controller

**前置环境：**H05 已签署；可恢复的 0.6.x Node、两个独立测试用户、desired Workspace/备份、direct 与 SOCKS5 出口、授权通知接收端、维护窗口；QoS Research Gate、A/B/C benchmark 与 fixed RC 24h soak 已完成。

| ID | 人工操作或见证步骤 | 通过标准 | 证据/AC |
| --- | --- | --- | --- |
| H06-01 声明与计划 | 声明缺失用户，查看 Desired/Observed Diff 与 plan；未批准先观察，再批准 apply/verify；随后重复 reconcile | 默认无 mutation；plan 清楚说明改动/风险/回退；批准后达成 desired；重复 NOOP，零重复写配置/重启 | AC-6.0-01～02、05～06；plan、journal、前后状态 |
| H06-02 过期计划与未知 | 生成 plan 后人工改变测试 Node/Workspace；使用旧 plan；另检查观测缺失和旧 capability 节点 | PLAN_STALE 零 mutation；UNKNOWN 不猜测执行；缺能力节点不被强制升级/错误应用 | AC-6.0-03、06；兼容矩阵、拒绝日志 |
| H06-03 配置事务与回滚 | 注入 staged invalid config；再制造 activation health fail；见证中途 crash、rollback fail 的恢复记录 | invalid 零 activation；LKG 成功恢复并可用；无法回滚明确 PARTIAL 与恢复指引；无半写配置假成功 | AC-6.0-04～05；故障注入、hash、真实代理结果 |
| H06-04 告警生命周期 | 制造 outage/recovery/flapping；维护窗口 reboot；在窗口内制造无关故障；测试 silence 到期及渠道失败 | 聚合告警/恢复通知正确；只抑制相关事件；到期恢复；渠道失败不影响 monitor/代理，队列有界 | AC-6.1-01～05；接收端记录、Finding、journal、soak |
| H06-05 逐用户 QoS | 审阅选型数据；并行跑 Alice/Bob；批准限速、移除、重启/rollback；见证异常 Finding→recommendation | 冻结的限速/隔离数值达标；Bob 不被误限；规则归属明确；未批准不执行；移除/回滚恢复 | AC-6.2-01～06；用户吞吐时间序列、规则 diff、资源记录 |
| H06-06 逐用户出口 | Alice 走 SOCKS、Bob direct；比对实际出口 IP；破坏 SOCKS auth/可达性；核对 DNS/UDP/QUIC 和 A/B/C benchmark | Alice 按策略出口或显式失败，Bob 正常；零 silent direct fallback/串用户；协议行为明确；性能异常有解释 | AC-6.3-01～06；出口/协议结果、benchmark、Finding |
| H06-07 维护与受限管理 | 见证 minor upgrade、health-fail rollback、planned reboot、Controller 中断恢复；受限 operator 尝试任意 shell；检查 cleanup | canary 失败不扩散；回滚/恢复状态真实；身份/URI/accounting 保留；shell 越权拒绝；不删除非 VCL-owned 数据 | AC-6.4-01～05；维护计划、journal、备份/恢复核对 |
| H06-08 综合安全与持续运行 | 运行已有 QoS/Egress 时停止 Controller；审阅 24h RC soak、secret scan、用户工作流与兼容表 | 现有数据面保留有效状态；无未批准策略变化、不可恢复损坏/泄漏/P0/P1；所有必要 gate 通过 | AC-6.0-06；AC-6.4-06；全阶段 evidence |

**通过后：**可进入 0.7.0 的 G0/实现。签署必须覆盖 QoS 与 Egress 的真实隔离、失败行为和维护恢复；“plan 能生成”不足以通过 H06。

<a id="h07-07x-programmable-data-plane"></a>

## H07：0.7.x Programmable Data Plane

**前置环境：**H06 已签署；具备对应 capability 的 Entry、主 Egress、备 Egress（执行默认至少 3 个真实节点）、direct/两跳两个测试用户、可控 TCP/UDP/HTTP3 目标、DNS/MTU 测试条件、Node credential/ACL；transport ADR、≥24h 综合 soak 和 accounting 对账已完成。

| ID | 人工操作或见证步骤 | 通过标准 | 证据/AC |
| --- | --- | --- | --- |
| H07-01 Node 身份与授权 | 检查默认 transit 关闭；未授权 A→B、授权、rotate、revoke；尝试普通用户 credential 作为 transit | 默认关闭、未授权拒绝；授权后成功；撤销后新连接失败；用户 credential 不可当 Node credential，普通用户仍正常 | AC-7.0-01～05；ACL/credential 生命周期、listener、安全审阅 |
| H07-02 编译与静态路径 | 先提交超 2-hop/loop/缺 capability/无 credential 的 Path，再编译合法 A→B；检查 direct 用户；移除/重复 apply | 非法输入拒绝；合法两跳真实可用，direct 用户仍单跳；plan deterministic/NOOP；移除仅转到显式指定出口 | AC-7.1-02～03；plan、出口、服务配置摘要 |
| H07-03 协议与传输选择 | 审阅 transport ADR 和 0/1/3% loss 数据；见证 TCP/UDP/QUIC/HTTP3、DNS leak/CDN、MTU/MSS/PMTU/大文件 | 各协议与冻结范围一致；无静默降级/出口泄漏；核心要求无未解决缺口；性能/运维选型证据完整 | AC-7.1-01、04；benchmark/协议矩阵/ADR |
| H07-04 故障与离线 | 重启 Entry/Egress；注入单侧 apply 失败；停止 Controller ≥5 分钟；检查新连接、既有静态路径与恢复 | 故障如实呈现；PARTIAL 有可执行恢复，零未知半配置/静默 direct；Controller 离线静态路径继续 | AC-7.1-03、05～06；代理时间序列、恢复/journal |
| H07-05 链路观测 | 注入 link loss、停 Egress、恢复；停止 measurement；查看拓扑；审阅 100 节点调度和开销记录 | DEGRADED/UNAVAILABLE/HEALTHY 迁移正确，缺测 UNKNOWN；拓扑只读 cache；无 full mesh/gossip/probe storm，测量故障不改转发 | AC-7.2-01～05；调度计数、Health、CPU/网络对照 |
| H07-06 人工主备切换 | primary 故障生成 recommendation，先不批准，再批准；恢复 primary；人工切回；另用健康双路做旧会话连续性测试 | 未批准零切换；新连接走 backup；健康旧会话不被主动迁移；恢复不自动切回；backup 不 ready 拒绝；多轮无 drift | AC-7.3-01～05；会话/路径标识、plan、journal |
| H07-07 计量与容量 | 运行已知大小单用户两跳流量；核对 Entry/transit/egress/Fleet；中途切换后查旧/新 path；制造 capacity pressure | Fleet user-total 只计 Entry；transit 独立；switch 前后归属正确；近似计量差异有解释；压力仅 Finding/recommendation，不迁移用户 | AC-7.4-01～05；对账表、rollup、Finding |
| H07-08 总体完成审阅 | 审阅固定 RC ≥24h 全链路 soak、三阶段 evidence、运行/回退手册、兼容表、限制和 secret scan | 无 P0/P1、双计、泄漏、未知断流、静默 fallback；User→Entry→Egress→Internet 可操作可解释；未实现自动路由如实说明 | AC-7.4-06；SUMMARY/SECURITY/COMPATIBILITY/SOAK |

**通过后：**可以声明本方案 0.5.x～0.7.x 范围验收完成。发布/tag/推送仍需按实际授权执行并记录其真实结果；不得因验收通过而虚报已发布。

## 3. 单项执行记录模板

在实际候选的 `HUMAN_ACCEPTANCE.md` 为每项追加以下信息；原始失败记录保留，复验另加记录。

```markdown
### Hxx-yy：<场景>
- 候选：Controller / Node 版本；source commit；artifact SHA256；Workspace revision
- 环境：匿名节点、OS/arch、capabilities、拓扑、测试用户/路径标识
- 执行人 / 人工验收人：待填写
- 执行时间和测量窗口：待填写（含时区）
- 前置检查与恢复方案：待填写
- 实际操作：待填写
- 预期结果：引用本清单及对应 AC
- 实际结果与测量值：待填写，不填推测
- 恢复后状态：待填写
- 脱敏证据：文件/记录链接、digest、原始数据保存位置
- 结论：PENDING HUMAN / PASS / FAIL / BLOCKED
- 缺陷及复验范围：待填写
- 复验记录：时间、候选、变化、结果；保留原结果
```

## 4. 大阶段签署模板与放行规则

| 字段 | 待填写内容 |
| --- | --- |
| 关卡 | H05 / H06 / H07 |
| 候选版本 | Controller / Node；source commit；artifact digest；配置 revision |
| 门禁材料 | G0～G5、required CI、AC 映射、COMPATIBILITY、SECURITY、LIVE、SOAK 链接 |
| 单项结果 | PASS 数 / FAIL 数 / PENDING 数 / BLOCKED 数；必需项列表 |
| 缺陷 | P0/P1 必须为 0；其他缺陷编号、影响和处置 |
| 非阻塞限制 | 仅限 SPEC 允许的 SHOULD/MAY 偏差；理由、期限、后续版本、验收人确认 |
| 人工结论 | 初始 `PENDING HUMAN`；实际签署为 `PASS` / `FAIL` / `BLOCKED` |
| 人工验收人 | 待用户或指定验收人填写 |
| 签署时间 | 待填写，含时区 |
| 放行范围 | 仅下一大阶段实现 / 本范围验收完成；另列明确授权的发布动作 |
| 实际发布状态 | 未执行 / 已执行及结果；与人工验收结论分开记录 |

判定规则：

- 所有必需单项 PASS、G0～G5 完整、P0/P1 为零，且人工明确签署，才可把大阶段状态改为 `ACCEPTED`。
- 任何必需项 FAIL、PENDING LIVE、PENDING HUMAN、BLOCKED 均不能放行；不使用“有条件通过”掩盖未满足的 MUST。
- H05/H06 未通过时，仅继续本阶段修复或下一阶段只读设计；不得进入下一大阶段实现。
- 修复后按影响范围复验并取得补充签署；更换候选或改变打包内容时，重新核对原签署是否仍适用。
- 不要求验收人重新手工执行全部单元测试；要求其核对证据适用性，执行/见证关键业务、安全和故障恢复流程。
