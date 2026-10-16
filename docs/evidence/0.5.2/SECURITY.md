# 0.5.2 安全验证范围

完整0.5.2候选，2026-10-04；自动化边界与固定输入见 [M4](M4.md)，实际主机权限/服务检查保留PENDING LIVE。

Node增加固定 `telemetry audit --json`、`telemetry users --json`，observer不接受路径/SQL/任意argv；Controller通过observe路由、capability和node/instance核验，认证失败无admin fallback。SQLite只读URI、query_only、事务和有界查询/quick_check；锁/预算/格式错误仅输出固定类别，不能回显SQL/secret。

Findings/evaluations/timeline 对缓存再生成 allowlist，输出 hash subject、固定解释和有界数值/布尔/状态。诊断内部逻辑 identity 不传入 Finding evidence；未知字段、深 JSON、坏行、坏 journal 均隔离。UI 对文本/JSON evidence 转义。缓存锁/提交失败不丢 telemetry，不调用远端 mutation。

schema2缓存迁移只在显式writer事务中执行，读取不迁移；用户baseline容量/未知覆盖明确标记。Timeline拒绝主体类型错配。公开合同拒绝未知字段、私有detector_state/secret、重复截断标记和超限数组。Controller payload pin由controller.lock覆盖，构建核对Node stamp；独立ZIP无需installer，也不从可变manifest自证版本。

完整验证绑定 [M4](M4.md)；M1/M2/M3各自manifest是历史范围。真实VPS systemd/sshd、升级/回滚、压力预算和访问权限为 **PENDING LIVE，本轮跳过**，不能由Linux fixture推定通过。H05为 **PENDING HUMAN**。Node数据面监听范围和observer环境/本地broker安全边界未新增公开写接口。
