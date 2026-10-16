# 2026-09-28 分支清理与开发基线

按用户要求仅保留 `main` 和主力开发分支 `codex/0.5.1`。清理前工作区干净，无其他 worktree；先 `git fetch --prune origin` 核对远端，再制作完整 Git bundle，最后使用 atomic push 和每条 ref 的 exact-SHA lease 删除，避免覆盖并发更新。

## 保留

| 分支 | 清理时 HEAD | 用途 |
| --- | --- | --- |
| `main` | `d8734ebd2f41a87c0fd874bb7f21604e6e708248` | 已合并 0.5.0 的主线 |
| `codex/0.5.1` | `112dfd3338f28c1f9ecdedf4fbcbde5342ad2a95` | 本轮后续开发基线；继续在此分支提交 |

## 已删除的远端分支

| 分支 | 删除前 HEAD | 核对依据 |
| --- | --- | --- |
| `release/0.4.3` | `44360f16d973e3776cb3fe65dc94136dcbff18d3` | PR #8 squash 到 `2288310`，两者完整 tree 相同 |
| `release/0.4.4` | `df2c5f8678abc436fd69cf1878c1f3a93d5bc66f` | PR #9 squash 到 `b1ac716`，两者完整 tree 相同 |
| `release/0.4.5` | `b22e7f009cad01661aa034025b431c664010d677` | PR #10 squash 到 `c36fb8e`，两者完整 tree 相同 |
| `docs/pre-0.5-documentation` | `fe3b7cd98c7ace0887418fd69e0e7d0f859ef67d` | PR #11 squash 到 `156b500`，两者完整 tree 相同 |
| `release/0.5.0` | `f48c40be0e724575be37780c2e2fb1157d6eefdb` | 已是 `main` 的祖先 |
| `dependabot/github_actions/actions/checkout-7.0.1` | `cd1f73cf51fde55714aa4a4115af551b4b35e0f3` | 未采纳的旧提案；按仅保留两分支要求删除，不表示已合并 |
| `dependabot/github_actions/actions/upload-artifact-7.0.1` | `6254ca0655f9f22fd2cc67f3afde30b8544e26c3` | 未采纳的旧提案；按仅保留两分支要求删除，不表示已合并 |

`git ls-remote --heads origin` 已确认远端仅剩两条保留分支；本地也仅有这两条。历史 tag 保留。Dependabot 配置未修改，未来仍可能生成新的升级提案。

## 恢复与追溯

本机恢复备份：`tmp/branches-before-cleanup-20260928.bundle`（忽略、不入 Git）。`git bundle verify` 已通过，包含完整历史及删除前 refs。SHA-256：`ee04317a856dc347f6ee8247ada3ac755e476b9d3b2b7eeea4de8be41bee03f3`。

如需恢复，例如：

```bash
git fetch tmp/branches-before-cleanup-20260928.bundle refs/remotes/origin/release/0.4.3:refs/heads/recovery/0.4.3
```

此备份是本机文件，其他机器不能依赖它自动存在；已合并内容可直接从上述主线提交查阅。不要清理该 bundle，除非已有替代备份。

## 本轮边界

用户明确选择先完成代码与本地验证，真实 VPS 验收另行安排。0.5.1 的 L1–L7、24h soak 与发布保持待完成；主线不因分支清理而自动合入候选。后续结果见 [0.5.1 续开发记录](../evidence/0.5.1/CONTINUATION.md)。
