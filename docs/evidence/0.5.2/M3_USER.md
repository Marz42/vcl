# 0.5.2 M3 用户异常检测

日期：2026-10-04；分支codex/0.5.1；状态：**M3 User PASS OFFLINE / 后续 M4 独立验证**。上一阶段[M3_NODE](M3_NODE.md)的95 Python / 1869 Bash只绑定其113个输入，不能覆盖本页新增内容。

实现独立user-traffic/v1固定只读命令与capability、observe/身份/instance/共享deadline、有界SQLite一致事务采样。包含open与closed retained字节总和/current open count，hash逻辑用户，无destination/credential/SQL/异常回传。成功poll时间、heartbeat、retention水位与counter reset决定数据可比较性；UNKNOWN不是伪零。

USER_TRAFFIC_SPIKE、USER_CONNECTION_SPIKE、SUSTAINED_TRAFFIC_ANOMALY共享可解释统计规则与持久化用户subject，独立去重/开关/重开；缺测不关告警，连续异常需300s，显式旧缓存refresh不打断有效采样。新增schema2用户evaluation、事务迁移、4096用户容量拒绝准入/覆盖标记、128MiB及Finding32768上限；正式合同见[用户采样](../../specs/V0.5.2_User_Sampling_Design.md)。CLI/UI与Timeline显示node/tag，并保留cache-only边界。

新增tests/test_user_traffic.py 13项：真实SQLite长连接/关闭连接与只读脱敏、65用户/坏行/overflow、missing/schema/corrupt/权限/预算、成功poll冻结、真实Linux Bash命令/extra argv拒绝、用户波动/尖峰/300s与恢复、retention/reset/instance/missing/age、缺测打断持续与refresh不打断、observe/capability/identity/超时与公共monitor/v1、持久化/去重/改名/过滤/Timeline、容量与cap invariant、schema1→2/事务故障/CLI+UI只读、正式schema与七fixture。

最终 Windows **108 项，101 PASS / 7 平台 skip**；WSL Ubuntu 24.04 root **108/108 Python PASS，0 skip**；完整 Bash/Fleet **1870 项通过**；两端构建、lock/digest 与独立 ZIP findings/timeline 黑盒通过。全部绑定 [SOURCE_INPUTS_M3_USER](SOURCE_INPUTS_M3_USER.json) 的123个输入；原始本机日志/制品在 tmp/linux-validation-20261004-m3-user-final/，各步骤 exit_code=0，SOURCE_DATE_EPOCH=1790679997。

| M3 User 制品（stamp 0.5.1） | SHA-256 |
| --- | --- |
| vincula-node-0.5.1.tar.gz | 7bb006f3c95e55991c7fab1e9cb9c7197376786afd114c3c4e2c9aa6198b3375 |
| vincula-controller-0.5.1.zip | cb5225a1827855a86c99b9667e490d197373e977003266e3d29c95808c296586 |
| payload-manifest.json | eec19a45ac1e7af8d8b1b996a3d23a3f76cca1c5904e2c6395d0974f77081bca |

首轮Linux108项发现真实CLI新用例遗漏安装态VERSION、可执行binary和generated config，Node正确返回installation incomplete。补齐隔离安装fixture（binary被调用即exit86）并限制此项为Linux root；未放宽生产安装/权限校验。失败日志保存tmp/linux-validation-20261004-m3-user/python.log，随后复验另用m3-user-final，不覆盖失败证据。

M3 ZIP 黑盒仅加载 findings/timeline；M4 后续补 provision/upgrade 加载检查，发现原版本固定函数依赖未分发的 vincula.sh，已复现并单独修复/复验。不把本页有限黑盒结论扩展为所有打包路径通过。

**Human Gate：PENDING HUMAN；真实用户负载、长连接、retention、普通波动与soak：PENDING LIVE；本轮跳过并记录。**本页为历史 M3 输入；后续正式合同/0.5.2 stamp/打包收口见 [M4](M4.md)，未提交/推送/合并/发布。
