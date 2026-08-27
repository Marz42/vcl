# Vincula 文档导航

当前稳定基线：**Controller 0.4.5** · **Node 0.3.2** · 最低兼容 Node **0.3.1**。

## 按受众阅读

| 你是… | 先读 |
| --- | --- |
| 新用户 / 想 10 分钟了解项目 | 根目录 [`README.md`](../README.md) |
| 日常用终端管 VPS 的管理员 | [`user-guide.md`](user-guide.md) |
| 维护者 / 要对齐实现与合同 | [`technical-guide.md`](technical-guide.md) |
| 做换机等高风险操作 | [`operations/node-replace-runbook.md`](operations/node-replace-runbook.md) |
| 核对规格或验收 | [`specs/`](specs/README.md) · [`evidence/`](evidence/README.md) |
| 查历史冻结 / 旧 known-issues | [`legacy/`](legacy/README.md)（只读，非当前操作依据） |

## 目录结构

```text
docs/
  README.md                 # 本页
  user-guide.md             # 用户手册（操作权威）
  technical-guide.md        # 技术手册（架构与合同权威）
  operations/               # 高风险独立 runbook
  release-readiness-0.3.1.md
  known-issues-0.3.1.md
  specs/                    # 设计规格
  evidence/                 # 验收证据（勿改写失真）
  legacy/                   # 历史材料
```

## 单一权威原则

| 主题 | 权威文档 |
| --- | --- |
| 安装与日常工作流 | `user-guide.md` |
| 版本兼容、身份、backup、accounting、UI 边界 | `technical-guide.md` |
| replace 逐步检查表 | `operations/node-replace-runbook.md` |
| CLI 全参数 | 各命令 `--help` |
| 产品版本戳 | 代码中的 `VCL_FLEET_VERSION` / `VINCULA_VERSION` |

同一事实不要在多份「当前手册」里各维护一份；用链接引用权威章节。

## Gate 与限制（Node 线）

- [`release-readiness-0.3.1.md`](release-readiness-0.3.1.md)
- [`known-issues-0.3.1.md`](known-issues-0.3.1.md)
- Controller 0.4.5：[`evidence/0.4.5/SUMMARY.md`](evidence/0.4.5/SUMMARY.md)
