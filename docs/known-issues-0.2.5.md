# Vincula 0.2.5 — Known issues / limitations

更新日期：2026-08-15  
Gate：**READY WITH DOCUMENTED LIMITATIONS**

## 政策

User Provisioning API 冻结候选。只接受 P0/P1 regression。Stats/analytics → 0.2.6。

## 已关闭（相对规格 Part I）

| 项 | 状态 |
| --- | --- |
| `user set` / `import` / `export` / `verify` | 已实现 |
| Bulk import 全量校验 + 失败零变更 | 已实现 |
| Tag 允许 `.` | 已实现 |
| `user remove` | 明确拒绝（exit 2） |
| `build-release.sh` → `dist/` | 已实现 |

## 仍开放 / 文档债

| 项 | 说明 |
| --- | --- |
| Live 0.2.4→0.2.5 migration 证据 | 需 RC 主机补跑；代码允许 0.2.4 源 |
| Reboot / 完整 OS 矩阵 | 沿用 0.2.4 缺口 |
| `--skip-existing` on import | P1，未做 |
| `user list --json` / department filter | P1，未做 |
| sing-box reload vs restart | 仍 restart；CLI 已警告连接可能中断 |
| Approximate accounting | 未改变；短连接仍可能漏记 |

## 安全提示

Credential CSV / `user link` 输出含认证材料，须 `0600` 保管；勿提交到 git。
