# 0.5.1 — 本地开发交付

状态：**LOCAL DELIVERY / PENDING LIVE / UNRELEASED**。用户于2026-09-27明确要求本轮只完成本地交付、文档与一次提交，真实VPS验收暂不执行。

Controller：`0.5.1`；Node payload：`0.5.1`；minimum Node：`0.3.1`。基线提交：`f38b29260a459b8b252df9dd0774d5f754401946`；本次交付提交可由 `git log -1 -- docs/evidence/0.5.1/SUMMARY.md`定位。构建以逐文件source-input manifest绑定实际代码，避免将未提交工作树的测试错误归给旧HEAD。

本地结果：**全量1868项通过；新增Linux Python 37项通过；另5项真实UID/GID权限测试通过；Node/Controller构建、digest/lock、打包unit静态检查通过**。Windows新增测试36项通过、1项Unix专属skip，该项在Linux通过。详见[TESTS](TESTS.md)与[ARTIFACTS](ARTIFACTS.md)。

SPEC：[V0.5.1](../../specs/V0.5.1_Spec.md)；操作说明：[monitoring runbook](../../operations/monitoring-runbook.md)。

## 已交付内容

- 前台monitor、每节点总SSH deadline、有界并发/jitter/backoff、同缓存独占监控锁，单节点失败隔离。
- Node/Observation/Proxy/Accounting分层Health与固定原因；真实代理probe缺配置/运行时时明确UNKNOWN，进程active不冒充服务可用。
- `observation.db`样本/5m/hourly rollup、保留期/容量限制、坏记录隔离、事务恢复；CLI `health`与UI GET只读cache。
- 独立VLESS/Reality代理probe：私有配置、唯一代理出口、禁用curlrc/环境proxy绕过、超时清理子进程与临时凭据。
- Node accountd独立用户、最小运行时投影、用户变更/恢复刷新；固定root准备步骤与非root daemon分离。
- 独立observer SSH用户、Ed25519 forced-command、公钥root管理、固定只读Unix socket broker；observe/admin用户名与凭据路线隔离。
- 新库/unit纳入Node制品、manifest、checkpoint/rollback；Controller包包括完整monitor/probe服务。

## 门禁与证据范围

| Gate / AC | 本地状态 | 尚未覆盖 |
| --- | --- | --- |
| G0 | SPEC、monitor/v1 schema、兼容与Live矩阵已定义 | — |
| G1 | 最终结果见[TESTS](TESTS.md)及[制品记录](ARTIFACTS.md) | 远端required CI未触发/未核对，不能声明CI全绿 |
| G2 | 调度、坏cache、状态恢复、用户名路由、升级旧回归、cache-only API有本地测试 | 真实Controller/Node服务crash、真实升级/代理故障矩阵 |
| G3 | [SECURITY](SECURITY.md)：源码/本地权限测试与systemd静态检查 | VPS实际listeners、systemd sandbox、sshd认证策略与转发拒绝 |
| G4 | **PENDING LIVE** | 全部0.5.1必需现场场景，见[LIVE](LIVE.md) |
| G5 | **PENDING LIVE / UNRELEASED** | ≥24h类生产soak、required CI、现场门禁、发布 |
| AC-5.1-01～03 | 实现与本地测试覆盖；具体方法见TESTS | ≥10节点受控混合矩阵2h及真实服务状态对照 |
| AC-5.1-04 | 本地降权/Unix socket隔离通过；SEC-050-01/02不再仅有计划 | 必须保留现场验证缺口，不能把旧安全偏差标为完全关闭 |
| AC-5.1-05～06 | **PENDING LIVE** | 故障恢复与24h soak |
| H05 | **PENDING HUMAN** | 仍在0.5.3大阶段收尾，不由本次提交代签 |

## 限制与交接

- 未连接真实VPS、未执行现场升级/故障注入、未发送通知，未push/tag/publish。
- Node 0.5.0可继续telemetry监控；新降权/observer能力要求升级Node 0.5.1。旧Controller不理解独立observe用户名，不宣称该配置可完整回退给旧Controller。
- probe profile的专用身份由显式配置和人工核验保证；代码不自动读取/复用普通用户credential。Windows私有profile ACL与真实sing-box/curl组合待现场确认。
- monitor采集启动时的启用节点集合；registry改变后重启monitor。无自动修复、通知、reconcile或策略变更。
- 原0.5.0“≤3秒升级断流”精确补证仍需后续执行；原历史evidence不被本次本地测试覆盖或改写。
- observer安装/替换公钥为显式admin操作；现有sshd外部key-command/CA/Match策略需Live核对。保留root broker与root pre-start的真实权限边界，不声称所有进程均无root。

后续从[LIVE矩阵](LIVE.md)启动现场验收；本地交付完成不等于0.5.1发布门禁通过。
