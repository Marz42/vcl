# 现场验证采集器（非冻结输入）

这些脚本是阶段 A/B 现场执行用的采集器，**不属于冻结候选的固定输入集**（manifest 只覆盖 `tests/ lib/ scripts/ schemas/ bin/ .github/` 与若干根文件），因此放在 `docs/` 下随文档一起交付，便于在拥有 Fleet 与密钥的机器上复现同一套取证流程。脚本只做只读探测与证据收集；所有写操作都落在隔离目录或副本里。

| 脚本 | 用途 | sha256（2026-10-09） |
| --- | --- | --- |
| `where-is-production-workspace.py` | 只读体检：解析生产工作区/状态/绑定路径、模式、`fleet_id`、节点与 ref、缓存大小 | `4179d6346ecc6ea5587b4c6cfe147f7bb4897617e4b058d4c66237e9d38b7147` |
| `phase-a-batch1.sh` | 阶段 A 批 1/2：候选摘要校验、隔离导入、绑定模板（可预填）、只读基线、能力矩阵、生产指纹、脱敏报告 | `20c58ffa83ad6a1c700da5019c95d228f860b9bf79aa661564514bb5949e2f5c` |
| `phase-a-batch3.sh` | 阶段 A 批 3：大积压、限一页续传、`sync --full`、超时/超量/预算/锁/中断与恢复 | `9aaabc24864257abc5651913e307ab968c5f2aea0dff5d597a9a6d7faf6141e7` |
| `phase-b.sh` | 阶段 B：生产上下文的 `probe/verify/status` 对照、能力与遥测矩阵、2h monitor 序列、Node 侧只读复核、生产指纹 | `bd45a40945b69fc1d383be96b38581cbfa61ce0e2e7271ccd51a896654e3eb14` |

约定：

- 每个脚本都会先校验冻结候选 ZIP 的 sha256 `65dbcc7b…`（与[冻结候选](../CANDIDATE_FREEZE.md)一致），不匹配就拒绝继续。
- 隔离守卫：隔离的 `VCL_FLEET_HOME`/`VCL_FLEET_LOCAL_STATE`/`XDG_CONFIG_HOME` 不得等于生产路径。
- 阶段 B 额外使用生产工作区与状态/绑定的**副本**，生产根只被读取。
- 证据保存在脚本打印的 `$VERIFY_ROOT`/`$B_ROOT` 下，不进仓库；本目录只放脚本本身。
- 脚本不代替人工判断：`PASS OFFLINE` 不得填成 `PASS LIVE`。
