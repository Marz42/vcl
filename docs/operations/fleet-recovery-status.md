# Fleet 观测恢复 — 当前阶段记录

证据来自用户在另一台电脑的 Kali/WSL 终端回传；现场 Controller 为 `release/0.5.0` / 0.5.0。本仓库代理未直接登录这些服务器。本页记录实际回传与待办，不作为当前0.5.3候选的Live/H05验收证据。

## 已回传的恢复结果

- `pass` 中 UpperHand/UrgentFury 两个条目恢复解密，均返回 `DECRYPT_OK`。设置当前交互终端的GPG_TTY并更新agent终端后成功；没有私钥损坏或丢失的证据。
- 保留现有SSH agent的12把密钥；使用两份公钥选择文件，为upperhand/urgentfury建立独立、显式的admin/observe引用。
- 凭据修改前本地配置备份返回OK；两台绑定均返回BOUND。五台原来正常的节点在复查中继续通过。

| 节点 | SSH / registry / proxy status / accounting | 版本及核对状态 | 凭据选择 |
| --- | --- | --- | --- |
| epicfury | 全部OK，用户回传 | 初次helper为UNKNOWN；后续核对0.3.1-rc2，两来源MATCH | OpenSSH默认 |
| upperhand | 全部OK，用户回传 | 初次helper为UNKNOWN；后续核对0.3.1-rc2，两来源MATCH | 显式admin/observe，均PINNED |
| eagleclaw | 全部OK，用户回传 | 0.5.0 | OpenSSH默认 |
| neptunespear | 全部OK，用户回传 | 0.5.0 | 原有显式admin/observe，均PINNED |
| hot-beam-1 | 全部OK，用户回传 | 0.3.1 | OpenSSH默认 |
| urgentfury | 全部OK，用户回传 | 0.3.2 | 显式admin/observe，均PINNED |
| fresh050 | 全部OK，用户回传 | 0.5.0 | admin默认、observe原有PINNED |

上述probe是管理面身份、Node status与accounting合同检查；probe本身不证明真实客户端代理、完整telemetry覆盖或审计缓存追平。审计与完整缓存恢复证据另列于下文。旧Node缺少新capability不等于节点故障；版本由实际回传记录，不作猜测。

## 2026-10-08 小批量审计同步回传

用户在原0.5.0 Controller执行`catch-up neptunespear hot-beam-1 --page-size 1000 --max-pages 1 --timeout 60`；SQLite备份返回OK。

| 节点 | 实际交付 / 插入 | 游标前后 | 最终状态 |
| --- | --- | --- | --- |
| neptunespear | 1000 / 1000 | 521173 → 522173 | BATCH OK / MORE_PENDING |
| hot-beam-1 | 1000 / 1000 | 425781 → 426781 | BATCH OK / MORE_PENDING |

两台已证明有界导出、既有Protocol v2校验和持久事务导入可行；没有以此声明全部历史积压已追平。后续从实际已提交游标继续，停止条件是当前已关闭连接窗口拉尽或达到每Node页数上限；任一失败保留已提交页。

## 2026-10-08 七台连续追赶回传

用户随后执行每页5000、每Node最多300页、SSH deadline60秒的七节点追赶；数据库备份OK，七台均报告CAUGHT_UP_CLOSED_WINDOW，已报告的BATCH未见异常。结构化汇总和原始附件SHA见[回传记录](fleet-recovery-20261008.json)。

| 节点 | 本轮交付处理条数 | 页数 | 最终游标 |
| --- | --- | --- | --- |
| neptunespear | 718028 | 144 | 1240201 |
| hot-beam-1 | 522111 | 105 | 948892 |
| upperhand | 169750 | 34 | 442867 |
| urgentfury | 27330 | 6 | 84059 |
| epicfury | 156 | 1 | 605345 |
| eagleclaw | 925 | 1 | 592514 |
| fresh050 | 69 | 1 | 44042 |

本轮delivered_total合计1438369；加上此前两台各1000条，共处理1440369条。该数是工具报告的交付处理量，不将未逐页输出的inserted/updated计数猜成精确净新增行数。各Node均在自己完成采样时拉尽已关闭连接窗口，不代表停止采集后不会再产生新记录。

随后使用`tmp/fleet-observation-finalize.py refresh-cache`调用原0.5.0完整identity/status/users/audit事务管线，审计仍限制每Node≤5000条、stdout≤16MiB、60秒deadline；缓存刷新结果如下。版本来源核对单独记录，保留最初UNKNOWN与后续查证的区别。

## 2026-10-08 完整缓存刷新回传

用户执行`refresh-cache --page-size 5000 --timeout 60`，本地数据库备份OK；七台均返回CACHE_REFRESH OK，汇总nodes=7、not_complete=0。缓存中的SSH、proxy、accounting、clock七台全部OK。统一cached_last_sync_at为`2026-10-07T17:06:51Z`，即Asia/Shanghai的2026-10-08 01:06:51。

| 节点 | 本次交付 / 插入 / 更新 | 缓存游标 |
| --- | --- | --- |
| epicfury | 213 / 213 / 0 | 605558 |
| upperhand | 176 / 176 / 0 | 443043 |
| eagleclaw | 152 / 152 / 0 | 592666 |
| neptunespear | 299 / 299 / 0 | 1240500 |
| hot-beam-1 | 0 / 0 / 0 | 948892 |
| urgentfury | 0 / 0 / 0 | 84059 |
| fresh050 | 8 / 8 / 0 | 44050 |

本次明确新增848条、更新0条；包括之前两台小批量验证和七台连续追赶，共报告交付处理1441217条，仍不将整个恢复的处理量称为精确净新增量。两台交付0条的缓存检查正常，表示本次没有新的已关闭连接记录可导入，不能据此判断实时业务流量。

截至上述采样时刻，0.5.0 Fleet的管理面探测、审计积压追赶和完整本地缓存刷新均已恢复。尚未执行UI视觉复核、真实客户端流量验收或当前0.5.3候选的Live/H05验收；节点未升级或重装。此成功依赖临时有界同步工具，未证明原生无界sync缺陷已修复。

## 2026-10-08 版本来源核对回传

用户执行`versions epicfury upperhand`，先后回传两台结果：identity的vincula_version与安装态`/etc/vincula/VERSION`均为`0.3.1-rc2`，比较方式EXACT_VERSION_TEXT，state=MATCH。两台可选的identity.version字段均为MISSING；本次比较使用vincula_version与安装文件，缺少该可选字段不构成版本矛盾。

最初诊断工具仅允许裸`x.y.z`，会将`0.3.1-rc2`过滤为UNKNOWN；已核对本地工具的正则源码。因此两台的UNKNOWN属于临时诊断工具的格式限制，没有证据据此判断节点安装异常。两台结果已齐，命令退出码未另行回传。

当前版本分布：epicfury/upperhand为0.3.1-rc2；hot-beam-1为0.3.1；urgentfury为0.3.2；eagleclaw/neptunespear/fresh050为0.5.0；Controller为0.5.0。七台已知管理面与审计观测故障恢复阶段结束。保留混合版本作为后续升级兼容样本，先修正式凭据引用和有界同步，再冻结候选与前后验收清单，最后执行用户确定的分批升级；本次未执行升级、重装或生产策略变更。

## 已确认的恢复工具与源码缺口

恢复工具为本机`tmp/fleet-observation-recover.py`，已交付用户在实际Controller环境执行。它复用现有身份/Protocol v2批次校验、导入事务和持久游标，仅读Node，写本机缓存。分页请求带`--limit`，单次stdout≤16MiB，失败不跳过游标、不reseed、不补写事件身份；配置与SQLite备份保存在实际fleet.db旁的recovery-backups目录。

纯临时0.5.0集成验证已覆盖：两页续传、失败/超量时游标保持、SQLite一致备份、legacy公钥绑定、Workspace两台不同公钥/四个独立引用、现有admin-default不变及脱敏输出。本机临时OpenSSH agent另验证stdin公钥派生和`ssh-add -T`签名；这些离线检查不替代实际批次回传。

1. 原Controller审计导出不带limit，默认20秒；最初用户回传neptunespear/hot-beam-1分别有约71.8万/52.3万条待导出记录并超时。先有两台1000条验证，后有七台5000条连续追赶至当前窗口的成功回传；原生源码缺陷仍未修复。
2. 0.5.0 `_bind_identity_for_workspace`在未指定ref时复用admin-default；便利node set可覆盖另一个节点的共享绑定，已在临时数据中复现。恢复工具使用节点专属引用规避；产品源码修复仍待后续处理。

已确认缺陷、已修/待查边界及功能优先级见[可靠性补丁候选清单](../plans/Fleet_Recovery_Reliability_Backlog.md)。原生密钥绑定与审计导出路径在当前本地0.5.3中仍与0.5.0相同；临时工具绕过不代表产品缺陷已修复。

## 后续评估

- 七台有界完整缓存同步和缓存健康复核已完成；UI显示效果尚未实际查看。
- 两个UNKNOWN版本来源均已核对MATCH，均为0.3.1-rc2；没有剩余版本来源待办。
- 优先修FR-01/02，再评估分批升级，保留0.3.x与0.3.1-rc2兼容样本；当前未重装、升级节点或执行生产策略变更。
