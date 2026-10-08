# FR-01 凭据引用隔离 — 本地实现与回归

日期：2026-10-08（Asia/Shanghai）。分支 `codex/0.5.1`，基线 `5054e51`。范围：只处理 [可靠性待办](../../plans/Fleet_Recovery_Reliability_Backlog.md) 的 **FR-01 / P1**；FR-02/03/04 未在本轮实现。

**IMPLEMENTED / UNRELEASED / REMOTE CI PASS / PENDING LIVE / PENDING HUMAN。**本地源码与测试证据加上 `7836b14` 的远端 required CI 全绿，但不替代现场混合 Fleet 复验、24h soak 或 H05；产品版本号仍为 0.5.3 候选，未发布。

## 缺陷与复现

修复前 `_bind_identity_for_workspace` 在未指定 ref 时写入 `admin-default`，指定 ref 时直接覆盖该 ref 的绑定：

- 给一个尚未绑定的 Node 设置新 key 会复用 `admin-default`，改变其他引用同一 ref 的 Node；`node set --identity-file`/`--observe-identity-file` 同样原地覆盖。
- `node adopt` 在远端 `vcl identity` 校验之前就写好绑定，校验失败也会留下副作用。
- `node replace` 先改写旧 ref，再对旧主机做 final sync/backup；旧 Node 通过同一 ref 解析密钥，会拿到新 key 访问旧服务器。
- 既有测试（F7-3 T1）明确断言新 Node 使用 `admin-default`，等于把互相覆盖当成预期。

## 修复设计

1. **每 Node、每用途独立引用。**`lib/access.py` 新增 `allocate_node_credential_ref` / `plan_node_credential_binding`：默认 ref 为 `<slug>-admin` / `<slug>-observe`，取用前合并"已绑定 ref + registry 已引用 ref"全集，冲突则递增后缀。
2. **copy-on-write 换钥。**节点级换钥分配全新 ref 并只切换目标 Node 的目标用途；旧 ref 及其绑定原样保留，其他消费者继续解析旧凭据。同一 key 重复设置且该 ref 未被其他 Node/用途引用时复用，避免无谓 churn。
3. **先校验、后提交。**`_node_identity_binding` 不再绑定任何 ref；`adopt` 在远端 identity 校验与 node_id 比对通过后才写绑定并提交 registry；`provision` 只在远端安装与 verify 成功后的 registry 提交回调内绑定（`bind_admin_at_commit`）。
4. **replace 全程区分新旧凭据。**新 endpoint 使用新 ref；`old_node` 保留旧 ref，final sync、backup create、`disable_remote_users_except_last` 全部走旧凭据；registry 只在 restore 复核通过后切换。
5. **显式共享保留在 `access bind`。**`access bind` 是唯一有意改写既有 ref 的入口，并在 stderr 列出受影响的 `node:purpose`；不自动拆分既有共享绑定。
6. **写入顺序。**绑定文件先落盘、registry 后落盘；两者都在 fleet op lock 内。registry 提交失败时最多留下未被引用的绑定，不会出现 registry 指向不存在绑定的悬空引用。

## 用例与结果

`tests/test-fleet.sh` 新增 19 项 FR-01 断言，并改写 F7-3 T1 的旧预期：

| 用例 | 覆盖 |
| --- | --- |
| 两 Node × 两用途四个独立 ref 且路径各自正确 | 默认隔离、admin/observe 同 key 也分 ref |
| 换钥后旧 ref 仍指向旧 key、新 ref 指向新 key | copy-on-write 不原地覆盖 |
| 显式共享 ref 在另一用途换钥后不被改写 | 共享消费者不受影响 |
| 同一 key 重复设置复用 ref | 无无谓 churn |
| 远端校验失败的 adopt 非零退出且 registry/bindings 字节不变 | 先校验后提交 |
| 失败的 replace 保留旧 endpoint 与旧 ref，候选 ref 未被引用 | 旧主机全程使用旧凭据 |
| 模拟 registry 写失败：绑定已写、registry 未动、无悬空引用 | 两文件写入顺序 |
| `access verify` / `workspace verify` | 引用与绑定一致 |

回归（本机 WSL2 / Debian 13.3 / Python 3.13.5）：

- `bash tests/test-fleet.sh`：**All 1077 tests passed，exit 0**（含本轮新增 19 项，0 失败）。
- `SQLITE_TMPDIR=<workspace>/tmp/sqlite-tmp bash tests/test.sh`：**All 1895 tests passed，exit 0**。
- `python3 -m unittest discover -s tests -p 'test_*.py'`：155 项，2 项失败均要求 root（`test_verify_extended` 的 root 权限 fixture），已在 `5054e51` 原始工作树复现为既存环境限制，与本轮改动无关。

本机沙箱下 SQLite 默认临时目录不可写，会让 node 侧 100k 行 `top_users` 用例以 `sqlite3.OperationalError: unable to open database file` 失败并中断 `test.sh`；该失败在 `5054e51` 原始工作树同样复现（两处均为 594 passed / 1 failed 后停止），指定可写的 `SQLITE_TMPDIR`（或 CI 环境）后 1895 项全通过。这是执行环境差异，不是源码或测试缺陷。

## 远端 CI

`7836b14` 推送后由 Draft PR #13 触发 [CI #88](https://github.com/Marz42/vcl/actions/runs/37731099502)（`event=pull_request`，全程 2026-10-08T05:11:07Z→05:19:14Z），**七个 job 全部 success**：Ubuntu、Debian 12/13、Windows、concurrency、failure-injection、artifact。artifact 的构建、sidecar/release.lock 校验、独立 ZIP 黑盒与 0.5.3 合同检查步骤均为 success。脱敏快照见 [REMOTE_CI_20261008.json](REMOTE_CI_20261008.json)。

`push` 事件本身不触发 CI（`ci.yml` 只对 `main` 的 push 生效）；本分支靠 PR #13 的 `pull_request` 事件运行。后续仅证据/文档的提交不会改变本 run 的绑定。

## 未关闭边界

- 本记录不构成 0.5.3 或新 0.5.x 候选的验收：现有混合版本 Fleet 现场复验、Live/H05、24h soak 仍 PENDING。
- 远端 CI #88 只覆盖 `7836b14` 的源码与测试字节；任何后续源码提交都需要新的 run。
- FR-01 的产品行为已在本地修复并回归；FR-02/03/04 仍按待办清单未实现。
- 旧 ref 与未引用绑定不会自动清理；显式共享的更新入口与受影响范围提示保留在 `access bind`。
