# 0.5.2 M1 离线验证

本页为冻结 M1 的历史结果；当前 M2/M3 代码不能复用这些结论。最新验证见 [CONTINUATION](CONTINUATION.md)、[M3_NODE](M3_NODE.md)，按各阶段 SOURCE_INPUTS 绑定。

日期：2026-10-04。起点为 `fabe8f1`；本轮新增/修改源码以 SOURCE_INPUTS manifest 绑定，旧 CI #84 不适用于这些改动。

## 当前记录

新增 `tests/test_findings.py` 覆盖 19 项：stall/idle 正反例、合法 export 跳号/expired gap、同步 lag/cursor instance/protocol、压力 hysteresis/缺值、陈旧/回放、detector 纯函数与脱敏、去重/未知/恢复/重开、倒退输入、节点改名、坏行/深 JSON、坏库、真实 SQLite 写锁与事务末尾故障、并发、retention/cap、service/probe、monitor 故障隔离、CLI/UI cache-only、显式本地 refresh、稳定 Timeline 与坏 journal。

初次 Windows 沙箱运行受临时目录权限限制，不能作为代码测试结果；随后普通权限环境新增 19 项通过。完整 Windows 回归首次发现 monitor run 新增计数字段使旧 exact-result 断言失败；更新该断言覆盖 `finding_write_errors=0`，保留此失败记录。最终复验结果追加于下。

WSL Ubuntu 24.04 可用，默认用户为 root。Windows checkout 的 CRLF 会使 Bash 解析失败，故复制 **Git tracked + 非 ignored 新文件**到 `/tmp/vcl-validation-20261004`，仅在验证副本恢复 LF 与 Git 执行位；实际源码 SHA 按 LF 内容生成，不改原目录的其他文件。

Linux 完整回归最初为 1866 PASS / 1 FAIL：旧 UI 测试把 Operations 的 `r.at` 禁用断言应用于整个 JS，误拦 Timeline 的合法时间字段。修正为只检查 `operationTimeCell`，并补齐八页 `/api/meta` 与真实 HTTP 读取用例。随后新 HTTP 测试漏传 token，实际返回 401（认证边界生效）；改用既有带 token 的 `get` helper。两次失败保留于本地日志，不改写为通过。复验时另将 Finding cap 调整为 16384，并断言覆盖 1024 节点 × 全部 detector，避免容量不足导致同类活动告警反复淘汰/重开。

一次后续 WSL 调用发现先前 `/tmp` staging 已不存在，未将该调用记录为测试失败或通过。最终采用单个 WSL 会话完成 staging、测试、构建和黑盒，日志保存在工作区 `tmp/linux-validation-20261004-verified/`；旧两轮失败日志另存，不覆盖。

## 最终结果

| 验证 | 实际结果 | 边界 |
| --- | --- | --- |
| Windows Python discovery | 71 项：65 PASS / 6 skip，0 failure/error | 5 项 Linux UID/GID、1 项 SO_PEERCRED 明确 skip |
| WSL Ubuntu 24.04 root Python discovery | 71/71 PASS，0 skip | 含真实临时文件 UID/GID 与 Unix socket 权限；不是 VPS systemd/sshd 验收 |
| WSL Bash/Fleet `bash tests/test.sh` | **All 1867 tests passed** | 含新 suite 顶层断言与 1000 次 fake-SSH telemetry；root 环境按既有条件省略两条非 root seed 检查 |
| Node / Controller 构建 | PASS | 固定 SOURCE_DATE_EPOCH=1790679997；Node stamp/payload 合同未变 |
| Node release.lock、Controller controller.lock、sidecar digest | PASS | 含新 findings.py 制品成员；摘要见 ARTIFACTS |
| ZIP 黑盒 | PASS | 独立临时目录，清除 PYTHONPATH/PYTHONHOME；`-I` 运行包内 CLI；init、findings、timeline、完整性与空缓存读取不创建 DB |
| JS / diff 检查 | PASS | `node --check lib/vincula-ui/static/app.js`；默认 Git 换行处理下 `git diff --check` |

新增 19 项 Finding 测试已包含在上述 Python discovery 与 Bash 子套件中，不重复计数。Bash 中标作 LIVE 的测试名称使用 fake-SSH/临时目录，不是本轮实机结果。未新跑 Debian CI、未触发远端 CI；0.5.1 CI #84 仍只绑定历史代码。

最终日志在 `tmp/linux-validation-20261004-verified/`，步骤 exit_code 全为 0；先前两次 Linux UI 失败分别保留在 `tmp/linux-validation-20261004/`、`tmp/linux-validation-20261004-final/`。原始日志与制品为本机 ignored 文件，未上传；本目录保存结论、源码 manifest 和摘要。

[SOURCE_INPUTS.json](SOURCE_INPUTS.json) 绑定 101 个产品、测试、schema 与打包输入，按 LF 内容校验，与最终工作树完全一致。后续纯状态文档修改不影响产品/制品输入。实机、24h soak、人工签署及远端 CI 不在本地通过结论中。
