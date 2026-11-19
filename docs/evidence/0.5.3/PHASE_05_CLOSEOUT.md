# 0.5.x 本地开发收口 — 停在 0.6.x 之前

日期：2026-10-07（Asia/Shanghai）。分支 `codex/0.5.1`，开发起点 `a9655e2e5234deb88a1215ba99d4c630aae928c0`。Node / Controller / embedded payload 均为 **0.5.3**，minimum Node **0.3.1**，sing-box **1.13.18**。

**LOCAL DEVELOPMENT CLOSED / PASS OFFLINE / UNRELEASED / PENDING LIVE / PENDING HUMAN。**用户要求继续完成0.5.x并停在0.6.x之前；本轮完成实现复核、可复现缺陷修复、离线回归、制品门禁与文档交付，不开始0.6.x。实机/持续soak/人工签署依[延期约定](../../plans/MANUAL_VALIDATION_DEFERRED.md)保留PENDING。

## 当前主线与阶段进度

| 范围 | 当前进度 | 证据适用范围 |
| --- | --- | --- |
| 远端 `main` | `d8734eb`，Controller/Node 0.5.0 | 本轮经GitHub API读取；未合入开发分支 |
| 本地 `main` | `f38b292`，比远端多规划提交 | 本轮Git核对；不作为0.5.3代码分支 |
| 开发分支 | 起点`a9655e2`，已有0.5.1～0.5.3实现，本轮追加修复 | 当前提交身份以Git为准；固定输入见下文 |
| 0.5.1 Monitoring / Health / restricted observer | 本地实现完成并保留；四维Health、有界poll/cache、独立probe、accountd降权与observer边界 | [0.5.1历史交付](../0.5.1/SUMMARY.md)，本轮全回归；实际权限/混合矩阵/soak仍PENDING LIVE |
| 0.5.2 Findings / Audit / Anomalies / Timeline | 本地实现完成并保留；审计/用户独立采样、统计基线、14类Finding与稳定生命周期 | [0.5.2历史M4](../0.5.2/M4.md)，本轮全回归；真实负载/故障/soak仍PENDING LIVE |
| 0.5.3 Inspect / Baseline / Drift / Verify | 本地实现完成；独立cache、显式SHA CAS、七类Drift、八项Verify，本轮缺陷修复和制品门禁完成 | 本记录与新固定输入；[旧RC](RC.md)保留原始SHA和测试数量 |
| 0.6.x | 本轮未开始实现 | 现有计划/SPEC只保留为后续文档 |

[Draft PR #13](https://github.com/Marz42/vcl/pull/13)当前head为起点`a9655e2`，尚未合并；其旧标题/描述仍以0.5.1为主。本轮不修改远端PR或发布状态。

## 本轮修复与可复现门禁

- `verify_snapshot.py`：accounting metadata的heartbeat为NULL、非法文本/字节或无时区时间时输出UNKNOWN/INVALID，不再因AttributeError中断JSON；保持SQLite只读。
- Listeners：比较配置的准确Clash loopback地址/端口与VLESS bind；其他IPv4或IPv6 loopback地址不能代替配置地址，等价IP表示按规范地址比较。仍不证明进程归属或公网可达。
- Controller Verify：复用Health的probe一致性规则，矛盾success/reason为UNKNOWN；每次probe尝试后均在共享deadline内复核observe identity，包括probe异常、runtime不可用和非法结果。认证失败/超时/换instance分别返回AUTH_FAILED/TIMEOUT/ERROR，清除整个旧snapshot，保留单Node隔离，无admin fallback。
- `scripts/check-controller-artifact.py`：从ZIP解包到临时目录、复制检查脚本并以isolated Python运行；验证Controller/Node锁、payload pin/digest、16份schema及Inspect/Verify生成规则，实际运行四个有注册Node的cache-only CLI/函数并设置SSH tripwire，比较Fleet文件bytes/mtime；root临时fixture运行embedded Node Inspect/Verify CLI，不执行受检binary。
- artifact CI已接入上述检查。Node CLI需要root，仅对临时fixture使用sudo；不安装或修改真实Node。旧artifact检查保留。

Node/Controller stamp和公开schema版本未改变，旧Verify JSON消费路径保留。增强失败语义与限制已同步到[SPEC](../../specs/V0.5.3_Spec.md)、[runbook](../../operations/inspect-runbook.md)、README/CHANGELOG/文档索引与阶段计划。

## 最终自动化与制品

[187个固定源码/测试/构建/CI输入](SOURCE_INPUTS_CLOSEOUT.json)按LF规范字节绑定，manifest SHA256：`0aec3bfda6cc13fc012cf991c62e656f584bd8f1a0f0e3eec4fc323af5015271`。清单包含最终release.lock、Controller README及制品检查脚本，不自引用最终commit hash。

| 验证 | 最终结果 / 实际环境 |
| --- | --- |
| 完整Linux Python suite | **155/155 PASS，0 skip**；Debian13.3 WSL2 / Python3.13.5，root临时权限fixture |
| 完整Windows Python suite | **155项，144 PASS / 11平台skip**；Python3.11.9；Linux权限/CLI由上一行覆盖 |
| Bash / Fleet全链 | **All 1874 tests passed，exit0**；隔离HOME/Workspace，包含1000次fake-SSH；不是真实节点soak |
| Node / Controller构建、sidecar与lock | **PASS**；Node18个lock成员，Controller16份schema |
| 独立ZIP black-box | **PASS OFFLINE**；四个cache-only入口、无repo lib/PYTHONPATH、payload pin/锁、embedded Node只读CLI；详情在原始artifact-final2.log |
| Python / JS syntax、whitespace与更新文档链接 | **PASS**；不将静态检查记为真实UI验收 |

原始日志：`tmp/linux-validation-20261007-053/`、`tmp/windows-20261007-053-final.log`。各日志、失败运行、helper和制品SHA见manifest；本机日志/包为ignored生成物。完整回归后仅调整Controller README、制品检查与CI调用；runtime及测试字节未变，重新构建ZIP并复验制品，无需重复无关长回归。

固定 `SOURCE_DATE_EPOCH=1791210662`。最终制品在 `dist/`：

| 制品 | SHA256 |
| --- | --- |
| `vincula-node-0.5.3.tar.gz` | `35abb6e688dfe5948e273aba7177a8552f6598fc5d0b1776a5f2318b1c7ecf18` |
| `vincula-controller-0.5.3.zip` | `ca82fb8093209e573fa634893e8e1c2e3b204bdd6825dd8ab1e9871c78fd930e` |
| `payload-manifest.json` | `1d60d55f1eca05a183759f611804385d0e97d8e19c1a30a4b11b49188fe65386` |

原始Node/Controller sidecar均重新核对；旧[RC](RC.md)、SOURCE_INPUTS_RC.json与失败记录保留，不替换成新候选证据。

## 远端CI与未通过记录

本轮读取[CI #86](https://github.com/Marz42/vcl/actions/runs/37327307690)，七项全部success：Ubuntu、Debian12/13、Windows、concurrency、failure-injection、artifact。全部head_sha为`a9655e2e5234deb88a1215ba99d4c630aae928c0`；脱敏快照见[REMOTE_CI_20261007.json](REMOTE_CI_20261007.json)。远端main要求的六个原有context均包括在内。**本轮新增修复和CI定义尚未推送，其远端CI为NOT RUN**；不将#86复用于新源码。

保留的未通过记录：

- 初次Windows沙箱运行被临时文件replace与loopback socket权限限制；改用仓库tmp并在本机授权运行后155项最终144 PASS / 11 skip。没有为环境限制改写功能或删除用例。
- `verify-20261007-before-fix.log`：13项新旧Verify用例，10个subtest FAIL / 1 ERROR / 2平台skip；其中NULL heartbeat崩溃、错误loopback PASS和旧snapshot泄漏已复现。修复后13项11 PASS / 2平台skip，全Linux suite亦覆盖。
- 第一次artifact检查仅schema的描述性title与生成器规范title不同；按生成器规范title后保留所有validation规则逐项比对。原`artifact.log`的FAIL保留。
- 下一次artifact检查的Node fixture缺VERSION/可执行binary/config，触发既有require_install；建立完整临时安装标记与binary执行tripwire后成功。原`artifact-final.log`的FAIL保留，新结果独立写`artifact-final2.log`。
- Windows直接检查旧dist时包不存在，`artifact-20261007-script-smoke.log`保留失败；不能据此描述旧制品或Windows Node CLI通过。

## 正式验收与停点

| 尚待完成项 | 状态 / 后续证据 |
| --- | --- |
| 支持OS实机、IPv4/IPv6 listener inventory、observer/accountd实际权限及systemd/sshd隔离 | **PENDING LIVE**；[LIVE](LIVE.md)、[SECURITY](SECURITY.md)，含前序0.5.1/0.5.2现场矩阵 |
| 真实文件hash/mtime、restart count、客户端代理前后对照，手工listener/config/unit Drift与恢复 | **PENDING LIVE**；AC-5.3-01/03/04 |
| ≥10节点受控混合矩阵2h、固定最新RC连续24h全Observation soak、升级不可用≤3s补证 | **PENDING LIVE**；前序LIVE/SOAK与[本阶段SOAK](SOAK.md) |
| H05人工签署 | **PENDING HUMAN**；[候选页](HUMAN_ACCEPTANCE.md)、[人工清单](../../plans/VCL_0.5-0.7_Human_Acceptance.md)，未代签 |
| 新本地修复的远端required CI | **NOT RUN**；#86仅覆盖起点commit |
| push / merge / tag / release / production apply | 本轮未执行 |
| 下一阶段 | **停在0.6.x实现之前**；后续仅在新的明确范围下推进 |

本轮交付的是完整0.5.x本地开发候选；正式0.5.x ACCEPTED/发布仍依赖现场和H05，不用本地PASS替代这些门禁。
