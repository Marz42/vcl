# Controller 0.5.4 — SSH credential management

**LOCAL IMPLEMENTATION / PASS OFFLINE / CI PASS (run 41484183321) / UNRELEASED / PENDING LIVE / PENDING HUMAN。**本页记录 Controller 0.5.4 的 SSH 凭据管理实现与离线验证，不授权 push/merge/tag/release，也不替代现场与 H05。

日期：2026-11-02（Asia/Shanghai）。分支 `codex/0.5.1`，功能提交 `3f48cba`，Windows 路径修复 `2c5036d`（最终制品包含该修复）。**Controller `0.5.4`；Node 保持 `0.5.3`**；最低兼容 Node `0.3.1`。

## 范围

- `credential-bindings.json` schema v2：
  - `agent`：`fingerprint` + 机器本地 `keys/<ref>.pub` 公钥选择器；
  - `identity_file`：本机私钥路径；
  - v1 `identity_file` 按 v2 语义读取；v1 `openssh-default` 转为 `migration_required`。
- 所有 SSH/SCP 统一 `-F <os.devnull>`、显式 `-i`、`IdentitiesOnly=yes`、`PreferredAuthentications=publickey`。
- 删除 `access bind --openssh-default`；新增：
  - `vcl-fleet access agent list [--json]`
  - `vcl-fleet access bind REF --agent [--fingerprint SHA256:...]`
  - `vcl-fleet access migrate [--node NAME] [--purpose admin|observe|both] [--agent [--fingerprint]] [--identity-file PATH] [--json]`
  - `vcl-fleet access verify [--json]`
  - `vcl-fleet node set NAME --admin-credential-ref REF --observe-credential-ref REF`
- 错误码：`CREDENTIAL_UNBOUND`、`AGENT_UNAVAILABLE`、`AGENT_KEY_MISSING`、`IDENTITY_FILE_MISSING`；状态行另带 `credential_state`（含 `CREDENTIAL_MIGRATION_REQUIRED`）。

## 安全边界

- 私钥内容与 Agent Socket 不进入 Workspace、备份、审计日志或 evidence；Agent 绑定只落公钥选择器。
- Host Key Trust 保留：workspace 下仍使用 `trust/known_hosts` + `StrictHostKeyChecking=yes`。
- `~/.ssh/config` 被显式忽略，避免其中额外 `IdentityFile` 被 OpenSSH 遍历；代价是 `ProxyJump`/`ProxyCommand`/Host 别名不适用于 VCL 连接。

## 离线验证

| 检查 | 结果 |
| --- | --- |
| 完整 Bash / Fleet 套件（`SQLITE_TMPDIR=… bash tests/test.sh`） | **All 1964 tests passed，exit 0** |
| Python 套件 | **162 项**；152 PASS / 8 skip / 2 个既有 root-only 用例失败（本机无 sudo；CI ubuntu job 用 `sudo -n` 覆盖） |
| 新增 credential 单元测试 | `tests/test_access.py` 7/7 PASS；`tests/test_observer.py` 通过 seam 适配 |
| Controller 构建 | `build-controller.sh` PASS；`controller.lock` + ZIP sidecar 校验通过 |
| 独立 ZIP 黑盒 | `scripts/check-controller-artifact.py` → `PASS OFFLINE`（version 0.5.4、schema 16、cache-only 入口 4、`node_cli=NOT RUN`，本机非 root） |
| 跨版本检查 | `check-controller-artifact.py` 已支持 Controller 0.5.4 与 Node payload 0.5.3 不同版本 |
| 远端 required CI | [run 41484183321](https://github.com/Marz42/vcl/actions/runs/41484183321) 七个 job 全绿（含 Windows 与 artifact），`head_sha=2c5036d`；快照见 [`REMOTE_CI_20261103_CREDENTIALS.json`](REMOTE_CI_20261103_CREDENTIALS.json) |

新增测试覆盖：Agent 指纹 >10 把、Agent 绑定、Identity File 绑定、v1 schema 迁移、legacy identity_file 状态、CREDENTIAL_UNBOUND/migration、`-F`/`-i`/`IdentitiesOnly` 的 SSH/SCP argv、node refs、`access migrate`、`access verify --json`。

## 制品

构建固定 `SOURCE_DATE_EPOCH=1793612077`；Node 内容与 MPTCP 记录一致。

| 制品 | SHA256 |
| --- | --- |
| `dist/vincula-node-0.5.3.tar.gz` | `06e133fb9d67fc711aad6cab63e235e470c9c1a0e58da6765aa762f4b03837ec` |
| `dist/vincula-controller-0.5.4.zip` | `a643b5a21e07edf5c2b625ca4be41fcfb3dc726e7c785c30fea73b4a0b8cd2ba` |
| `dist/vincula-controller-0.5.4/payload/payload-manifest.json` | `da60d9a41f3538a387ce5f2065b3951fab189a61ad0d9dd6d65fac40d2edb451` |

payload manifest：`controller_version=0.5.4`、`node_payload_version=0.5.3`、`sha256=06e133fb…`。Controller ZIP 内含更新后的 `access.py` / `ssh_transport.py` / `vincula-fleet.py`，以及带 MPTCP 加固的 Node payload。

## 正式边界

- 真实 VPS 上的 Agent/Identity File、observer 权限、SSH config 行为：**PENDING LIVE**。
- H05：**PENDING HUMAN**；本次不代签、不发布。
- 远端 required CI：[run 41484183321](https://github.com/Marz42/vcl/actions/runs/41484183321) 七个 job 全绿；首次 Windows 失败与修复记录在快照的 `earlier_runs`。
