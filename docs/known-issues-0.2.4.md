# Vincula 0.2.4 — 现存问题清单

更新日期：2026-08-15  
Gate 结论（不变）：**READY WITH DOCUMENTED LIMITATIONS**（尚未 **READY FOR RC**）

本文只列**当前仍存在**的缺口与限制。已修复项见文末，避免与「未解决问题」混淆。

---

## 1. 阻塞 READY FOR RC 的验证缺口

这些不是“代码一定坏了”，而是 Gate 要求的实机证据尚未齐，**按规则不得标 READY FOR RC**。

| ID | 问题 | 现状 |
| --- | --- | --- |
| V-OS | Fresh-install OS 矩阵未完成 | 仅 **Debian 13 amd64** 实机打通；Debian 12 / Ubuntu 22.04 / 24.04 / arm64 **未跑** |
| V-MIG | 跨版本 migration 未验收 | `0.1.5` / `0.2.0`–`0.2.3` → `0.2.4` **未在实机验证** |
| V-RB | 强制 migration 失败 rollback | 至少一次 “中途失败 → 旧版可恢复、无 mixed-version” **未做** |
| V-F | 故障注入 F01–F04、F07–F09、F12 等 | Debian 13 上已做 F06（代码）、F10/F11/F13/F14/F15 及主路径；**破坏性注入与磁盘满等未齐** |
| V-BOOT | Packaging / bootstrap 篡改拒绝 | archive SHA + `release.lock` 被改后拒绝安装 **未实机测** |
| V-REBOOT | 重启后双平面 | `reboot` 后 `vcl verify` / accountd **未测** |
| V-PY310 | Ubuntu 22.04 / Python 3.10 | 目标平台声明有；实机多为 3.13；**未在 3.10 原生验证** |

操作手册：[`rc-test-manual-0.2.4.md`](rc-test-manual-0.2.4.md)。

---

## 2. 产品 / 架构已知限制（设计如此，非回归 bug）

| ID | 限制 | 说明 |
| --- | --- | --- |
| L-APPROX | Approximate accounting | Clash API **轮询**；短连接可漏记；**不是** Reliable / 计费级 |
| L-SCHEMA | Event schema 非运行时强制 | `vincula-event.schema.json` 安装时 `json.tool` + 文档契约；ingest 为手写解析 |
| L-ROOT | accountd 以 root 运行 | 需读 `0600` settings/DB；unit 已做部分 hardening，`systemd-analyze security` 仍因 root 曝光较高 |
| L-NORECOVER | 无 `vcl recover` | fresh install 遇遗留 `/var/lib/vincula` 直接拒绝，需 uninstall 或人工清理 |
| L-NOSINGLE | 不支持单文件 `curl\|bash` | 必须完整 release 目录或 bootstrap |
| L-IDNA | Destination 归一化有限 | 仅 lowercase + 去尾点；不做完整 IDNA 折叠 |
| L-MIDNIGHT | 跨 UTC 午夜计入规则 | 整段流量按 `closed_at` 所在 UTC 日记入 daily（raw 仍保留区间） |

详见 [`accounting-reliability.md`](accounting-reliability.md)。

---

## 3. 工程 / 仓库层面

| ID | 问题 | 说明 |
| --- | --- | --- |
| E-DUPL | `release/` 与仓库根双份树 | 部署用副本，易与 `lib/`/`bin/` 漂移；改代码后须同步并重跑 `scripts/gen-release-lock.sh` |
| E-EVID | 实机证据在 VPS 本地 | 例：`/root/vcl-rc-evidence/`；仓库内无完整矩阵附件 |
| E-SEC | 测试期间凭据曾暴露 | SSH 密码、Clash secret、VLESS URI 出现在聊天/日志时，须轮换；勿把密钥提交进 git |

---

## 4. 已修复（不再算作现存问题）

| 修复 | 说明 |
| --- | --- |
| sing-box 1.13 inbound `sniff` | 改为 `route.rules` → `"action":"sniff"`；`auth_user` 用 `"action":"route"` |
| `vcl user add/rotate` 失败 | `readonly USERS_FILE` 被赋值；改为向 render 显式传 staged `users.json` 路径 |

---

## 5. 建议优先级

1. **P0（RC）：** V-MIG + V-RB（一台机即可先做 0.2.3→0.2.4 + 强制 rollback）  
2. **P0（RC）：** V-OS 至少再补 Ubuntu 22.04 amd64  
3. **P1：** V-F 核心注入、V-REBOOT、V-BOOT  
4. **P2：** L-ROOT 非 root 方案、L-SCHEMA 运行时校验、Reliable Accounting（另立版本）
