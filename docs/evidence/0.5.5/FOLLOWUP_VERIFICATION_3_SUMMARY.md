# 0.5.5 preparation 第三轮收敛与未冻结候选

**结论：supervisor 暂停缺口已修复并通过定向复测；32 秒延迟已定位为 writer
自动 WAL checkpoint + 共享 IO 配额组合；checkpoint helper 兼容性已补
`--verify-only` 预检；已生成两个独立构建、哈希一致的未冻结候选。**
Live 仍 **BLOCKED**；未连接生产节点，未执行 apply/migrate/rollback，未修改冻结
`dist/`，候选未宣布冻结/发布。

上一轮总结保留为 [SUMMARY-r2.md](SUMMARY-r2.md)。

## 最终身份

| 项 | 值 |
| --- | --- |
| 最终 commit | `f86dd5e46f44411f539c0fb5dab5cc87172251d8` |
| 源码清单 | [source-manifest.txt](results/final-identity/source-manifest.txt) 393 文件，SHA256 `c98c3a4480d64c6b276b2a3deed3086d8cf566007f87c518cbe3f5e247924c51` |
| worktree | `/tmp/vcl-followup-wt`，clean |
| 补丁 01 | `8df53b738647994fddffcd48afdd893836423c0b5ccf2e60971ff28671ff456d` |
| 补丁 02 | `822af77f1933b94c8b0888e9351b1af06b4ea84d28ee73b2621fa0dfd402aebd` |
| 补丁 04（本轮） | `79d2370160b6beacf1c81e430b8d0c5e153b06521d3f6b0e06c6cd1d3cca1f44` |
| 候选 | [release-candidates/0.5.5-f86dd5e](/mnt/d/Repos/Vincula/release-candidates/0.5.5-f86dd5e) |

`01`（`9846b85..f86dd5e`）和 `02`（`4651064..f86dd5e`）均在独立 worktree
验证：应用后与最终 commit **0 差异文件**。两个干净测试副本各 393 文件，
逐文件与 source manifest 比对为 0 missing / 0 mismatch。

## 1. Supervisor 暂停缺口：已修复

最小方案：[SUPERVISOR_PAUSE_FIX_PLAN.md](SUPERVISOR_PAUSE_FIX_PLAN.md)。

实现职责：

- supervisor 仍是主期限所有者；
- worker 在启动 helper 前增加 **一个** daemon `deadline_guard` 线程，读取
  supervisor 传入的**同一个绝对** `VCL_PREPARE_DEADLINE_MONO`；不创建第二个
  预算、不在恢复时续期；
- 到点后原子写 `CANCELLED/PREPARATION_DEADLINE`（`deadline_owner=worker_guard`），
  设置 `deadline_fired` 阻止后续 `SUCCEEDED`，向 helper 进程组 TERM，最多
  5 秒后退出；worker 是 namespace PID 1，内核清理其余后代；
- 线程独立于主线程的 `proc.wait()`、`snapshot_sqlite()`、`verify_archive_fd()`，
  因此不是阶段之间的时间检查；
- supervisor 在 fork 后关闭自己的 lock fd；worker/helper 继承唯一 lock fd。
  这样 supervisor 被暂停时，worker 清理完成后锁可释放，新操作不会永久被
  旧 supervisor 的 fd 阻塞。

| 复测 | 结果 |
| --- | --- |
| 单独 SIGSTOP supervisor，40.15 s | 状态 `CANCELLED/PREPARATION_DEADLINE`；5/5 记录后代消失；**锁空闲**；`deadline_guarantee_gap=false`；SIGCONT 后无需再清理 |
| 单独 SIGSTOP worker | worker 状态 `T`；34.61 s 后 `CANCELLED`；34.54 s 全部后代消失；锁空闲；仍由 supervisor 清理 |
| worker 先 SIGKILL、supervisor 后 SIGKILL | 5/5 后代消失；`FAILED/WORKER_LOST`；锁空闲；无误报成功 |
| supervisor 先 SIGKILL、worker 后 SIGKILL | worker PDEATHSIG 先写失败；第二次 kill 为 `ProcessLookupError`；5/5 后代消失；锁空闲 |
| 清理期间启动新操作 | 第二次 start 返回 `UNKNOWN/PREPARATION_BUSY`，不创建 op 目录；旧锁释放后同一 op 才被接受 |
| 共享期限不重置 | 60 s 预算：checkpoint 在 40.61 s 开始，剩余 19.39 s；60.25 s 时 `CANCELLED`，未获得第二个 1200/900 s 预算 |
| 正常流程 | 20 MB smoke `SUCCEEDED`，checkpoint ok |

边界：全机冻结、supervisor 与 worker 同时暂停、永久 D state 不在本轮解决范围。
D state 下锁仍被持有，不得报告已安全清理，也不得绕过并发保护。

证据：[stop-supervisor-fixed](results/lifecycle2-stop-supervisor-fixed/result.json)、
[stop-worker-fixed](results/lifecycle2-stop-worker-fixed/result.json)、
[kill-worker-first-fixed](results/lifecycle2-kill-both-worker-first-fixed/result.json)、
[kill-supervisor-first-fixed](results/lifecycle2-kill-both-supervisor-first-fixed/result.json)、
[busy-overlap-fixed](results/lifecycle2-busy-overlap-fixed/result.json)、
[shared-short-fixed](results/shared-short-fixed/result.json)。

## 2. 32 秒延迟归因

同一 400 MiB/5 commits/s/10 MiB/s/冷读，只切换 writer 的
`wal_autocheckpoint`：

| | 默认 1000 pages | 0 |
|---|---|---|
| 长 commit | 1 次 **32,650 ms**（seq 601，checkpoint） | **无**，max 0.267 ms |
| backlog >1 s | **159 commits**，max 32.45 s | 0 |
| 状态采样 | 1,615 `D` / 1 `R` | 全 `R` |
| busy_timeout | 10,000 ms；32.65 s 大于它 | 10,000 ms |
| checkpoint 写锁探测 | 204/204 `BEGIN IMMEDIATE` 成功 | 206/206 成功 |
| WAL | 4,115,912 → 4,128,272 B | 5,265,392 B |
| IO | 10 MiB/s，pressure some/full avg10 92.59/87.19 | 同限额，84.19/78.62 |

结论：**writer 自身在 1000-page 阈值触发的自动 WAL checkpoint** 是触发点；
长读快照使 WAL 无法 reset，auto-checkpoint 在 10 MiB/s 共享配额下等待到快照
结束，commit 进入 D state。不是 DB 写锁（写锁探测全部成功）、不是 SQLite
busy timeout（32 s > 10 s），也不只是普通 IO 竞争（auto=0 同样 IO 无 stall）。

这是 **commit 吞吐尾部**，不是 32 s 代理停机：没有失败，但有 159 个计划提交
被积压。最小建议是让 accountd writer 在 preparation 期间
`wal_autocheckpoint=0`，准备结束/读快照释放后用有界 passive checkpoint 回收
WAL，并保留 WAL 上限；若该 commit 位于实际请求必经路径，再做代码修复；否则
记录为资源受限吞吐限制，并用实机端到端探测判断 ≤3 s 目标。详见
[ANALYSIS.md](results/latency-400/ANALYSIS.md)。

## 3. Checkpoint helper 版本兼容

| 路径 | helper | 结果 |
| --- | --- | --- |
| preparation 生成 checkpoint | staged candidate `/tmp/payload/bin/vincula`，SHA256 `8314b538…15f8` | 写 manifest |
| checkpoint 内嵌 | `<checkpoint>/upgrade-rollback-helper`，同一 candidate 字节 | manual fallback |
| 自动回滚 | 安装的 `/usr/local/bin/vcl`（candidate） | 先 `--verify-only`，再实际 rollback |
| 旧 helper（`9ea55c6`） | SHA256 `aca00a20…3348` | 忽略 manifest，**确实接受被篡改 checkpoint 并改写目标** |
| 新 helper verify-only | candidate | 篡改/缺 manifest 时 rc=1 `checkpoint_integrity_failed`，发生在停服务和目标写入前；目标哈希不变 |

`node_upgrade.py:_attempt_post_upgrade_rollback` 现在先调用
`vcl upgrade rollback <ck> --verify-only --json`；旧 helper 不认识该选项则
preflight 失败，**不会**继续执行未验证的 mutation，而是返回 PARTIAL，保留
内嵌 candidate helper 的人工恢复路径。新 helper 的成功路径仍执行实际
rollback；单元测试覆盖 preflight 成功/失败，以及旧 helper 的危险行为复现。

“无 manifest 的历史 checkpoint 被拒绝”不会移除当前支持路径的回滚能力：
candidate checkpoint 带 manifest，candidate `vcl` 通过 preflight 和实际
rollback；旧 checkpoint 只能由旧 helper 显式处理，不属于当前支持矩阵。

## 4. 未冻结候选构建

两个独立 `git archive f86dd5e` 目录，构建 epoch **1794384920**，执行同一
`gen-release-lock.sh` / `build-release.sh` / `build-controller.sh`：

| 制品 | A/B SHA256 | 一致 |
| --- | --- | --- |
| `vincula-node-0.5.5.tar.gz` | `34a46feeca3975a4a7a93aee355d7c04495ae76fe9c0e6680995dcfba81aa14e` | 是 |
| `vincula-controller-0.5.5.zip` | `b4f51881155f6e14a00a63874dbbec7f0ec2eb68ee081f3889ad927520868b41` | 是 |

两个包的 `release.lock` / `controller.lock` 校验通过；Node 解包后
`bin/vincula`、`lib/upgrade_prepare.py`、`lib/vincula-backup.py` 哈希与源码
一致，包含 deadline guard、WAL-only 拒绝、checkpoint manifest 和
`--verify-only`；Controller 包含 `node_upgrade.py` preflight。Node/Controller
`--help` 冒烟 rc=0。候选在
`/mnt/d/Repos/Vincula/release-candidates/0.5.5-f86dd5e/`，包含
`BUILD_INPUTS.json`、两次 build log、lock 校验、SOURCE_MANIFEST 与
`SHA256SUMS`；**未冻结、未发布**。

## 5. 回归与边界

- Python：**225 passed，10 skipped，0 failed**。
- 普通用户 Bash：**1970 passed，0 failed**；namespace root Bash：**1968 passed，0 failed**。
- 原 worktree 的 392 pass / 11 冻结 dist 环境失败保留，不计通过。
- 未验证：真实 VPS/systemd/容器、物理块设备/独立 VM、D state、全机冻结、
  supervisor+worker 同时暂停、多节点 fleet、manifest 同时伪造、Live。
- 非 WAL 仍明确拒绝；checkpoint manifest 只是损坏检测，不是签名。
