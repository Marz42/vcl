# 0.5.3 完整本地 RC — PASS OFFLINE

**后续证据（2026-10-07）：**本页冻结2026-10-05本地输入和制品，不改写原始结果。该提交`a9655e2`已由[CI #86](https://github.com/Marz42/vcl/actions/runs/37327307690)七项通过；新的Verify修复、可复现制品门禁与最新候选另见[阶段收口](PHASE_05_CLOSEOUT.md)。旧SHA/测试数量不能绑定新的源码。
日期2026-10-05，分支codex/0.5.1；开发起点`dc7f0b24c3953f376c34abbf6907d410f7f94de4`。Node/Controller/payload stamp0.5.3，minimum Node0.3.1，sing-box1.13.18。M1–M3功能实现已收口；当前本地候选 **UNRELEASED / PENDING LIVE / PENDING HUMAN**，远端required CI NOT RUN。

## 自动化与固定输入

[固定186个源码/测试/构建/CI输入](SOURCE_INPUTS_RC.json) SHA256：`1c32ead7835be603820004bf4dd65845893be7c6c6b7a0aa9071d817f7e1e806`。所有输入逐项与最终工作树LF字节一致；包含最终release.lock与版本pin。正式schema v1文件未改写；新增7份合同和20个正反fixture，Controller共16份schema。Git提交信息以收尾提交记录为准，manifest保留测试起点，避免自引用commit hash。

| 验证 | 终态结果 |
| --- | --- |
| WSL Ubuntu24.04 / Python3.12.3，完整suite | 152/152 PASS，0 skip |
| Windows完整Python suite | 152项，141 PASS / 11平台skip；Linux权限、Bash CLI等由上一行覆盖 |
| Bash/Fleet全链 | 1874/1874 PASS，exit0；包含混合版本、升级/恢复/回滚、1000次fake-SSH与既有HTTP UI |
| Node / Controller构建及lock | PASS；Node release.lock18个成员；Controller锁定16份schema及所有新增库 |
| 独立ZIP black-box | PASS；无repo lib/PYTHONPATH，standalone provision/payload pin、Inspect observe/identity、cache-only findings/v2/timeline/v2/inspect、加载新cache/verification模块、embedded Node只读Inspect/Verify |
| JS / whitespace /文档链接 | PASS；无冻结v1 schema改写 |

原始日志与制品保存在`tmp/linux-validation-20261005-053-delivery/`，Windows日志`tmp/windows-validation-20261005-053-rc-final2.log`。各日志、制品及本地验证helper SHA在manifest；CI定义增加Linux完整Python/root权限suite，但本页不声称远端CI已执行。所有日志/包为本机生成物，未纳入Git，制品已复制到`dist/`并复核SHA。

| 最终制品 | SHA256 |
| --- | --- |
| vincula-node-0.5.3.tar.gz | `0e3bbfed91fdbbb0b1ddd30a94bff22ecfa197212fabff6d6c648f53201cd40b` |
| vincula-controller-0.5.3.zip | `c6dca74081608086bbb19c2d73cd319d5dd6fb3eae336b2eb088b2086aaa1628` |
| payload-manifest.json | `d9dcfd74d3e68b53b90c11624e9bb9893443c0b7287c259403d14e0ea38dd5b0` |

固定SOURCE_DATE_EPOCH=1790679997，Linux阶段文件使用Git模式与LF；原始包和sidecar保留。README-controller作为包成员也绑定最终输入，版本与候选状态一致。

## 实现范围及兼容

[M2](M2_CONTROLLER.md)：独立inspection.db，低频observe/shared deadline、cache-only CLI/API/UI、snapshot SHA CAS接受基线、当前instance/endpoint/freshness/coverage约束，baseline事件同事务；七类Drift Finding与UNKNOWN保留ACTIVE。容量拒绝新Node/Finding，避免驱逐已有ACTIVE；私有Findings schema2兼容。

[M3](M3_VERIFY.md)：八项verify/v2与fleet-verify/v2；旧Verify JSON保持升级/恢复消费兼容，扩展入口为--extended。Node不执行受检binary，Data Plane无显式probe则UNKNOWN；Controllerprobe后再次核对identity。新增collector进入安装/runtime-only/checkpoint/rollback/卸载/制品清单，0.5.2→0.5.3升级加入allowlist。

M1另修复真实installer嵌套state.node.instance_id；其历史证据仍保留。binary Integrity只对本机安装lock，canonical配置不执行sing-box语法检查，listeners不证明process归属/公网可达，Unix权限不替代所有systemd/ACL隔离。上述范围已写入[SPEC](../../specs/V0.5.3_Spec.md)与[runbook](../../operations/inspect-runbook.md)，实机仍待核对。

## 未通过运行保留

- 053-full：Linux CLI用例暴露旧require_install早退，Verify未输出JSON；扩展命令改为即使缺artifact仍输出UNKNOWN，并补实际CLI回归。
- 053-full-final：旧identity版本、UI page list和payload正则仍期待0.5.2；阶段失败，未记PASS。
- 053-rc：HTTP用例仍要求findings/timeline v1，扩展合同已为v2；阶段失败，未记PASS。
- 053-rc-final：升级模拟节点默认版本仍0.5.2，引起未asserted happy path提前退出；trap打印All1796但实际exit1，本页明确该次FAIL。修正fake默认3，补suite异常退出明确FAIL；最终delivery完整1874且exit0。
- Windows早期兼容测试断言已随合同/容量准则更新，最终完整suite141 PASS / 11平台skip；不把早期错误或跳过写成Linux PASS。

## 正式门禁

| 门禁 / 授权 | 状态 |
| --- | --- |
| AC-5.3-01支持OS/IPv4/IPv6、observer实际coverage与权限 | PENDING LIVE；[LIVE](LIVE.md)、[SECURITY](SECURITY.md) |
| AC-5.3-03真实文件/restart count/客户端代理前后对照 | PENDING LIVE |
| AC-5.3-04人为listener/config/unit Drift及恢复、Verify人工核对 | PENDING LIVE |
| AC-5.3-05连续24h全Observation RC soak | NOT RUN / PENDING LIVE；[SOAK](SOAK.md) |
| H05 / H06 / H07 | PENDING HUMAN；[H05](HUMAN_ACCEPTANCE.md)，未代签 |
| 当前remote required CI | NOT RUN；仅本地验证，未复用旧CI #84 |
| 本地阶段提交 | 同候选源码、固定证据与文档收尾；实际hash见Git |
| production apply / push / merge / tag / release | 未执行 |

按[用户指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)跳过人工等待，记录判据与后续证据位置。完成的是0.5.3本地实现和离线交付；人工/实机/soak未被替换成PASS。
