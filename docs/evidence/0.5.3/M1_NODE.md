# 0.5.3 M1 — Node Inspect / Read-only Contract

日期2026-10-04，分支codex/0.5.1，base fabe8f1f7cb5f39606b4fa8f76d7d9d40401b4ba。**NODE IMPLEMENTED / PASS OFFLINE / FULL 0.5.3 IN PROGRESS / UNRELEASED**。Node/Controller stamp仍0.5.2，minimum Node0.3.1；本阶段新增源码独立验证，0.5.2 M4为历史候选。

## 实现范围

- `lib/inspect_snapshot.py`：固定Linux inventory、16项受管SHA/权限指纹、严格managed-config/v1秘密投影、完整inspect/v1 schema/runtime校验；固定输入与共享6秒预算，无raw config/argv/stderr输出、不执行受检binary。
- Node `vcl inspect --json` / inspect/v1 capability 与受限observer固定argv；安装/runtime-only/manifest/checkpoint/rollback/卸载列表和release.lock接入。
- 内部 `lib/observation/inspection.py`：observe transport、能力降级、当前node/instance核对、完整wire清洗；Controller ZIP纳入两个模块与inspect schema。调用方总deadline集成在后续M2证明。
- Controller inspect CLI/cache/UI、baseline/Drift Finding/Timeline、增强Verify均未实现。后续设计见 [M2草案](../../specs/V0.5.3_Baseline_Design.md)，不能将本切片当完整0.5.3 PASS。

## 最终自动验证

Windows Python3.12：全量126 tests，117 PASS / 9 platform skip；Linux WSL Ubuntu24.04 root Python3.12：126/126 PASS，0 skip。专项12 tests覆盖支持OS矩阵、缺文件/权限/工具/超时、非健康零、secret rotation、有效配置drift、10k用户配置/4MiB拒绝、IP family/scope/zone、array cap、正式schema与秘密注入、observe身份/认证不fallback、Linux flood/timeout/子进程退出/FIFO/symlink、真实临时Node CLI只读及非法argv。

最终Linux Bash/Fleet **1874/1874 PASS**；Node/Controller build、release.lock17成员、controller.lock与全部九份公开schema、独立ZIP黑盒通过。黑盒仅使用分发ZIP，核对provision/upgrade payload pin、Node Inspect CLI与原始文件不变、packaged observe fetch身份绑定/无admin fallback、cache-only Findings/Timeline。JS syntax与diff whitespace检查通过。VCL_INTEGRATION未启用，无真实sing-box代理/REALITY外部网络测试。

[152个固定输入/结果/制品/日志hash](SOURCE_INPUTS_M1.json)在最终快照后逐项核对未变。LF规范化、Git executable mode恢复，SOURCE_DATE_EPOCH=1790679997；原始本地报告保留在 `tmp/linux-validation-20261004-053-m1-final3/`，Windows日志 `tmp/windows-validation-20261004-053-m1-final3.log`。manifest SHA256：`fcde7c0763a66301793d5f5378a50167bb5e1e37a72324bdf4e5a37b021718fd`。

| 制品（阶段stamp仍0.5.2） | SHA256 |
| --- | --- |
| Node tar.gz | `df0086a0d38b9c46378257fe7efb5840cf92ed35a87215b10c3b5a3148f25327` |
| Controller zip | `1e115aefb623c0c5177e527ed203bc9d8fa61599dc4752095279e845a9fef2e4` |
| payload-manifest.json | `6503e73f5dbb0cd6304aab90308b9be31c8f7014efc561b065c2d98246ae3022` |

这些制品是M1固定输入的本地候选，不是完整0.5.3，也不是已发布0.5.2更新。后续M2代码需要单独验证，不能复用本表PASS。

## 已修复与保留的失败记录

1. 初次Linux126测试中listener fixture将分项改为PARTIAL却保留root OK；完整validator正确拒绝。修正fixture root状态，并增加正式schema/runtime双验证负例；不放宽合同。日志 `tmp/linux-validation-20261004-053-m1/python.log` 保留。
2. 资源复核将interface枚举限制为65项读取，config从普通1MiB预算分离为4MiB；新增10k用户/超限测试。文件路径替换核对在Windows发现fstat/path stat的ctime语义差异，路径交叉核对使用dev/inode/size/mtime，打开文件前后仍比较ctime；Windows最终回归通过。
3. 首轮全Bash因旧断言仍要求16个release.lock成员失败2项、通过1872项；加入Inspector后正确成员数17。修正两个断言，保留 `tmp/linux-validation-20261004-053-m1-final/bash.log`，不能将该轮记PASS。
4. 复核observer unit发现ss/tc所需AF_NETLINK被排除；补地址族许可，保留CAP_DAC_READ_SEARCH并断言没有CAP_NET_ADMIN。旧final2隔离快照在运行Bash时停止，未完成不计PASS；最终final3重新冻结源码并全量验证。firewall权限限制仍可能UNKNOWN，完整现场覆盖待Live。
5. Windows默认沙箱阻止测试临时目录写入；一次运行只报权限错误，未作为测试结果。自动权限审查允许临时目录测试后重新运行完整suite通过；没有真实节点操作。

## AC 与人工项

| 项目 | 当前证据 / 状态 |
| --- | --- |
| AC-5.3-01 | Node inspect正反schema、OS/listener/隐私fixture通过；增强Verify与现场核对仍待完成 |
| AC-5.3-02 | config/binary hash变化与秘密轮换fixture；完整baseline/Drift尚未实现 |
| AC-5.3-03 | 真实临时Node CLI前后文件bytes/mtime不变、工具命令白名单；真实service restart count/代理对照PENDING LIVE |
| AC-5.3-04 | 人为现场listener/config/unit drift、Finding恢复与人工Verify一致性PENDING LIVE |
| AC-5.3-05 | 全链路24h RC soak、实际accountd/observer权限PENDING LIVE |
| H05/H06/H07 | PENDING HUMAN，按[用户指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)跳过开发等待，未代签 |

WSL root及临时fixture不是支持OS实机矩阵；1000次fake-SSH不是24h soak。远端required CI未执行，不复用旧CI #84。验证时没有commit/push/merge/tag/发布或production apply。后续用户已授权阶段收尾并本地提交，见 [CLOSEOUT](CLOSEOUT.md)；本页验证事实与固定输入不变。
