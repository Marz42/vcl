# Fleet 恢复暴露的缺陷与 0.5.x 可靠性补丁候选

日期：2026-10-08。依据：用户在另一台电脑的0.5.0 Controller回传、当前本地0.5.3源码、精确0.5.0临时集成复现。当前恢复记录见[阶段记录](../operations/fleet-recovery-status.md)，此前本地修复见[0.5.x收口](../evidence/0.5.3/PHASE_05_CLOSEOUT.md)。本清单是评估和实施候选，不代表本轮已经修入产品、发布或现场验收通过；继续遵守停在0.6.x之前的范围。

当前用户回传：七台管理面probe均通过；先有neptunespear/hot-beam-1各1000条验证，后有七台连续追赶全部CAUGHT_UP_CLOSED_WINDOW，本轮处理1438369条。完整node/user缓存最终刷新也已全部OK，新增848条，七台缓存SSH/proxy/accounting/clock均OK，采样时刻为2026-10-07T17:06:51Z。epicfury/upperhand均核对为0.3.1-rc2，identity与安装文件MATCH。已知观测故障恢复阶段结束；这仍是0.5.0 mixed Fleet恢复，不能绑定为0.5.3验收。

## 已确认、尚未修入正式程序

| ID / 优先级 | 缺陷与实际影响 | 证据层级与当前状态 |
| --- | --- | --- |
| FR-01 / P1 | `_bind_identity_for_workspace`对未指定ref的绑定复用admin-default。为一个尚未绑定的Node设置不同key，可能改变已引用该ref的其他Node；observe convenience绑定也会复用默认ref | 精确0.5.0临时数据已复现另一节点绑定被改；当前0.5.3函数AST与0.5.0相同。恢复工具用每Node/每用途独立ref规避；产品源码未修 |
| FR-02 / P1 | 审计SSH导出不带Node已有的limit，固定20秒且未提供stdout字节上限；积压全部塞进单次请求，超时后不提交，反复重试同一大批 | 两台原始导出约71.8万/52.3万条超时；用户回传1000条/60秒有界请求各导入1000，游标推进。源码路径在当前0.5.3仍相同；未声称limit或timeout单独改变就足以解决所有场景，也未声称已发生内存耗尽 |
| FR-03 / P2 | `AUTH_MARKERS`未包含Too many authentication failures，observe transport将这类认证限制标成一般FAIL/ERROR，未提供针对密钥选择的原因 | 当前函数直接回归返回False，Permission denied对照返回True；用户原始probe是FAIL，临时doctor识别AUTH_LIMIT。分类代码未修；没有admin fallback行为证据 |
| FR-04 / P2 | `_ssh_failure_detail`直接使用远端stderr，human sync错误文本把结构化audit meta和timeout混在一起，带出端点及逻辑Node/instance ID，难以分类或直接分享 | 原始用户输出与当前源码均确认。需要结构化错误及可分享摘要；不据此声称私钥、用户credential或完整审计内容泄漏。机器合同需要的逻辑身份字段应继续保留 |

FR-01/02是新现场情景暴露的缺口，需要重新开启0.5.x补修和RC验证；先前RC的通过记录仍保留其原输入适用范围，不转写成覆盖这些场景。

## 当前待办与完成条件

下列未勾选项尚未完成；本次仅记录和提交，不将临时恢复成功记为正式修复。FR-01/02关闭前，不将0.5.x候选标为无P1或已满足G5。产品版本号与新增CLI/JSON合同在补修的G0确定，范围仍限于0.5.x。

- [x] **FR-01 / P1：隔离凭据引用。**本地已修复并回归：默认ref按Node+用途分配，换钥copy-on-write，adopt/provision先校验后提交，replace新旧凭据分离，写入顺序为绑定先于registry。19项新用例+F7-3预期改写，`tests/test-fleet.sh` 1077项全通过，见[FR-01记录](../evidence/0.5.3/FR01_CREDENTIAL_ISOLATION.md)。远端required CI已在`7836b14`全绿（[CI #88](https://github.com/Marz42/vcl/actions/runs/37731099502)，脱敏快照见[REMOTE_CI_20261008.json](../evidence/0.5.3/REMOTE_CI_20261008.json)）；现场混合Fleet复验仍归入下方两项，未在本次完成。
- [x] **FR-02 / P1：正式有界同步。**本地已修复并回归：`--limit`分页＋每页deadline与stdout cap＋页数/总运行预算，每页一个事务提交审计/日汇总/持久游标，被拒页整页不导入且保留已提交页；新增`MORE_PENDING`并接入汇总（`PARTIAL`/`ok=false`/退出码2）、UI操作记录、人读表格与`remediation`，`retire`/`replace`未追平即停止；`sync --full`改为先分页追赶再刷快照，快照事务失败保留已提交审计页并明确报告；锁/满盘在节点边界处理，不终止其他节点。见[FR-02记录](../evidence/0.5.3/FR02_BOUNDED_SYNC.md)（评审补修后绑定 `f37c50a`，[远端CI #97](../evidence/0.5.3/REMOTE_CI_20261008_FR02_FIXES.json)全绿）。默认参数仍需现场按大积压节点复测。
- [x] **FR-03 / P2：补齐认证失败分类。**本地已修复并回归：顶层仍为`AUTH_FAILED`，新增`reason=AUTH_LIMIT|AUTH_DENIED`；补充Too many authentication failures并移除过宽的独立`publickey`匹配；capabilities/probe/verify给出固定模板的密钥选择提示（明确公钥+`IdentitiesOnly=yes`），假SSH只对observe键失败即证明未回退admin。见[FR-03/04记录](../evidence/0.5.3/FR03_FR04_ERROR_MODEL.md)（`4e5d27f`，[远端CI #90](../evidence/0.5.3/REMOTE_CI_20261008_FR0304.json)全绿）；现场复验仍归入下方两项。
- [x] **FR-04 / P2：结构化、可分享的错误摘要。**本地已修复并回归：`ssh_transport`新增phase/code/state/retryable/summary(/hint)统一错误对象，本地transport事实（超时、stdout超量）优先于远端文本；audit meta继续按协议数据解析；失败不再回显stdout；摘要用固定模板且不含端点或逻辑身份，`node_id/instance_id`保留在机器合同；sync行新增`error_code/error_phase/retryable`。见[FR-03/04记录](../evidence/0.5.3/FR03_FR04_ERROR_MODEL.md)（`4e5d27f`，[远端CI #90](../evidence/0.5.3/REMOTE_CI_20261008_FR0304.json)全绿）。
- [ ] **最小诊断入口与版本格式。**支持agent公钥选择与本地doctor，默认只读、零SSH；版本报告保留来源并接受0.3.1-rc2等已知格式，未知格式明确说明，不能静默改写。详细验收见下方功能候选2/3/5。
- [ ] **补修候选离线交付。**上述变更完成后，重新绑定源码、测试、schema、Node/Controller制品与独立ZIP验证结果；原始失败记录保留，新增提交单独核对远端CI。
- [ ] **补修候选现场与阶段验收。**固定候选后，以现有混合版本Fleet执行对应Live/权限/升级兼容、24h soak与H05；保留PENDING LIVE/PENDING HUMAN直到实际完成。当前恢复回传不替代这些验收。

同步状态/缓存来源、完整版本与升级报告、恢复快照/reseed预览、增量汇总性能仍为下方功能候选，尚未冻结实施合同。性能项先测量再决定改动；0.6.x功能不列入本轮实现。

## 已在本地 0.5.3 修复的缺陷

提交`79f54bf`已修复：accounting heartbeat为NULL/非法时间造成增强Verify中断JSON；Clash其他loopback地址被误判为配置地址；Controller probe后身份失效仍保留旧snapshot，以及矛盾probe结果被当成有效失败证据。完整离线验证见原收口报告。这些是0.5.3增强接口修复，现场Controller仍为0.5.0，尚未部署该候选。

## 不能直接判为程序缺陷的现象

- 12把SSH agent key配合OpenSSH默认选择达到认证上限，属于当前凭据选择环境；Node已有显式key能力。缺少agent友好入口/doctor是可改善的产品流程，错误分类问题另列FR-03。
- pass解密失败随GPG_TTY/agent终端更新恢复，指向本机GPG会话链路；没有私钥丢失/损坏证据。
- epicfury/upperhand版本UNKNOWN均已定位为临时doctor只接受裸x.y.z的格式限制；后续两台的两来源均返回0.3.1-rc2并MATCH，属于诊断工具缺口，不列作已确认的产品故障。版本报告应区分字段缺失、格式过滤与实际安装状态。
- 0.3.1/0.3.2缺少0.5.x新capability是兼容边界，不能直接当作服务故障；升级前要展示支持矩阵。
- `import_audit_batch`每页调用全Node daily_usage重建的实现已确认；大库多页的耗时/磁盘影响尚无测量。可列性能风险和benchmark项，不称作已测得的性能故障或数据错误。

## 功能候选、优先级与验收

| 顺序 / 候选 | 范围与价值 | 最低验收条件 |
| --- | --- | --- |
| 1. 正式有界catch-up | 将临时分页流程纳入Controller CLI与既有sync/full管线；配置每页大小、单次deadline、总页数/运行预算与stdout cap；持久续传、单Node失败隔离、进度及明确MORE_PENDING | 多页成功/第二页超时/中断恢复/满盘/锁/超量/身份或endpoint变化/retention gap都保持已提交数据；不自动reseed；1000与5000页大小验证；新机器结果合同冻结且不破坏旧消费者 |
| 2. agent公钥选择与凭据作用范围 | 一等入口绑定public selector，先签名测试与远端identity校验；新Node/新用途默认独立ref；显式共享可保留，更新共享ref时显示受影响节点 | 两Node不同key、四个用途ref互不覆盖；已显式共享的既有绑定不被node级变更悄悄改写；覆盖add/adopt/provision/set/replace调用方；保留observe/admin边界、host-key校验和已有OpenSSH默认模式 |
| 3. fleet doctor | 默认只检查本机Workspace、key/ref路径、agent可用性、pinentry/TTY与缓存；显式--live读取identity/capabilities/status；给出AUTH_LIMIT/AGENT_UNAVAILABLE/HOST_KEY/TIMEOUT等原因和下一步 | 默认零SSH/零修复；诊断和建议不输出私钥、credential UUID、URI或自由远端stderr；不清空agent、不自动读取pass秘密、不隐式使用admin替代observe；坏配置逐Node隔离 |
| 4. 同步状态和缓存来源 | CLI/UI区分当前live probe、最后一次成功采集、最后一次审计导入、最后一次full缓存刷新；显示本地cursor/远端水位、积压未清与陈旧原因 | GET保持cache-only；水位差不能伪装成准确剩余条数，未知ETA保持未知；MORE_PENDING与OK/ERROR分清；一次失败不清掉有效历史；必要公共字段版本化 |
| 5. 版本/能力与升级验收报告 | 展示Controller、helper、installed VERSION、sing-box manifest版本/指纹与capabilities来源；基于已有typed upgrade准备前后身份、私有客户端profile一致性、accounting和真实专用probe的验收清单 | UNKNOWN、格式不支持、来源矛盾分别说明；保留0.3.1/0.3.2样本；来源版本不明不生成可执行升级承诺；只读报告不自动安装、重装或修改策略，不代签Live/H05 |
| 6. 本机恢复快照与reseed预览 | 正式复用现有备份/归档能力，提供一致SQLite快照、registry/binding元数据快照、磁盘预检、校验与恢复说明；reseed前展示删除范围和缺口 | 备份失败或空间不足零删除；源DB含WAL时一致；快照不进portable Workspace的secret-sensitive部分、不混入私钥；恢复需核对fleet/Node身份和schema，重置游标仍显式操作 |
| 7. 增量汇总性能 | 在前述可靠性收口后，用10万/100万合成历史行对比1000/5000条批次；考虑只重算受影响date/user/destination组 | 新旧daily_usage结果一致，重放/更新幂等，失败原子回滚；记录实际耗时、扫描/写入与磁盘成本，依据数据冻结性能阈值，不从源码猜测已达标 |

Monitoring、Health、Findings、Inspect、Drift、Timeline和增强Verify已在本地0.5.1～0.5.3实现，以上功能优先连接这些能力与实际恢复工作流。Desired/Reconcile、策略自动修复、QoS、Egress和后续通知系统仍属于原0.6.x范围，本轮不开始实现。

## 建议执行顺序

1. 七台连续追赶、有界full缓存刷新和两个版本来源核对已完成；保留原始失败与复验结果。保留0.3.1-rc2、0.3.1、0.3.2和0.5.0版本样本，先制定补修和分批升级验收计划，无需因本次已恢复的观测故障立即整体重装。
2. 修FR-01，再交付FR-02的正式有界同步；同时修FR-03/04和最小agent/doctor入口。
3. 按现有回归/制品/独立ZIP合同门禁生成新的0.5.x RC；现场使用同一Fleet复验，保留旧Node作为升级兼容样本。候选已冻结（见[冻结候选](../evidence/0.5.3/CANDIDATE_FREEZE.md)）；候选冻结、隔离测试工作区、Controller 单侧验证（大积压/限一页续传/full 刷新/失败恢复）、七台复验、24h soak 与 H05 的人工步骤见[验证方案](RC_0.5.3_VERIFICATION_PLAN.md)（PREPARED / NOT EXECUTED；禁止为造积压重置生产游标）。
4. 接入同步状态/版本兼容/验收报告与恢复预览；性能改动先benchmark再实施。
5. 所有新候选的远端CI、支持OS/权限、24h soak和H05仍需独立绑定，不复用当前恢复结果宣布0.5.3正式验收或发布。
