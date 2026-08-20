# Vincula 0.2.4 — 现存问题清单

更新日期：2026-08-15（freeze）  
Gate：**READY WITH DOCUMENTED LIMITATIONS**（freeze candidate；V-MIG / V-RB / V-PY310 已 PASS）

**政策：** 0.2.4 已冻结，只接受 P0/P1 regression fix。详见 [`freeze-0.2.4.md`](freeze-0.2.4.md)。

---

## 1. 仍开放的验证缺口（非本次冻结门禁）

| ID | 问题 | 现状 |
| --- | --- | --- |
| V-OS | Fresh-install 多 OS 矩阵 | Debian 13 amd64 PASS；Ubuntu 22.04 仅 Python 3.10 容器；Debian 12 / Ubuntu 24.04 / arm64 **未跑** |
| V-F | 故障注入 F01–F04、F07–F09、F12 等 | 部分 PASS；磁盘满等 **未齐** |
| V-BOOT | Packaging / bootstrap 篡改拒绝 | **未实机测** |
| V-REBOOT | 重启后双平面 | **未测** |

已关闭（freeze）：

| ID | 结果 |
| --- | --- |
| V-MIG | **PASS**（0.2.3-shaped → 0.2.4；legacy sniff P0） |
| V-RB | **PASS**（破坏 accountd.py → rollback → VERSION=0.2.3） |
| V-PY310 | **PASS**（Ubuntu 22.04 Docker，Python 3.10.12 `py_compile`） |

---

## 2. 产品 / 架构已知限制（设计如此）

| ID | 限制 | 说明 |
| --- | --- | --- |
| L-APPROX | Approximate accounting | Clash API **轮询**；短连接可漏记 |
| L-SCHEMA | Event schema 非运行时强制 | 安装时 JSON 校验 + 手写解析 |
| L-ROOT | accountd 以 root 运行 | 需读 `0600` settings/DB |
| L-NORECOVER | 无 `vcl recover` | 遗留 `/var/lib/vincula` 拒绝 fresh install |
| L-NOSINGLE | 不支持单文件 `curl\|bash` | 完整 release 目录或 bootstrap |
| L-IDNA | Destination 归一化有限 | lowercase + 去尾点 |
| L-MIDNIGHT | 跨 UTC 午夜 | 按 `closed_at` UTC 日记入 daily |

---

## 3. 工程

| ID | 问题 | 说明 |
| --- | --- | --- |
| E-023 | 无官方 0.2.3 git tag | 冻结用 morph / `scripts/build-reconstructed-0.2.3.sh` |
| E-DUPL | `release/` 部署副本 | gitignore；从仓库根打包 |
| E-SEC | 测试凭据曾暴露 | 须轮换 SSH / Clash / UUID |

---

## 4. 已修复（freeze 含）

| 修复 | 说明 |
| --- | --- |
| inbound `sniff` → route action | sing-box 1.13 |
| `readonly USERS_FILE` user mutation | staged path 显式传入 |
| `vcl stats yesterday` | 已实现 |
| migration legacy inbound pre-check | 1.13 FATAL 时警告并重生 config；跳过旧 config health wait |
| owner UUID via registry | `owner_active_uuid_from_registry` |
