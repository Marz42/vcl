# 2026-10-26 UrgentFury 断连现场取证

> 归档自 `tmp/urgentfury-diag-20261026/SUMMARY.md`（2026-11-02）。原始 36h journal 与运行时快照已清理；本页保留时间线、结论与后续处置。


- 采集时间：2026-10-26T06:53:59Z（本地 14:53）
- 目标：`69.63.198.51:22`（root），Vincula 0.3.2，sing-box 1.13.18
- 窗口：`--since -36h`（覆盖 10-24 18:53 → 10-26 06:53 UTC）
- 方式：只读 SSH 流式读取，Node 上未写任何文件

## 产物

| 路径 | 内容 |
| --- | --- |
| `logs/` | 36h journal：可读 `journal-short-iso.txt.gz`、无损 `journal-export.gz`、`METADATA.txt`、`MANIFEST.txt`（sha256） |
| `evidence/runtime.txt` | `vcl status`、`vcl diagnose`、`vcl connections`、`ss -ltnp`、`config.toml`（已剔除私密字段） |

规模：4,268 行 / 842,532 字节明文，gz 约 52 KB，目录合计 316 KB。

## 时间线（UTC）

| 时刻 | 事件 |
| --- | --- |
| 10-25 全天 | 正常代理流量，逐小时 5–145 条成功连接 |
| 10-26 02:06:14 | **最后一条成功代理连接**（`vcl connections` 显示该连接 02:10:18 关闭） |
| 02:10 → 06:13 | 无任何成功连接，也无入站记录（断连窗口约 4 小时） |
| 06:13:41 | sing-box 与 vincula-accountd 同时 `Started`（重启，疑似人工尝试恢复） |
| 06:43:47 → 06:51:43 | 20687 收到 **161 个不同源 IP** 的失败握手（每个 IP 仅 1 次），属扫描/探测 |
| 06:53:59 | 本取证导出完成 |

## 运行时结论

- `vcl status`：sing-box active、TCP 20687 监听、listener 归属 sing-box。
- `vcl diagnose`：仅 `✗ REALITY end-to-end self-test` 一项失败，其余全绿。
  该项为**误报**：源码中只有 `short_id` 非空才执行端到端测试，本机 `short_id` 为
  空字符串，条件不满足直接记 FAIL，测试并未运行。
- REALITY 私钥推导公钥 = URI 的 `pbk`（`KDriClEe…`），配置与链接一致。
- `vcl connections` 最后一条记录停在 `2026-10-26T02:10:18Z`。

## 与网络侧证据的关系

同一时段的外部探测（见对话记录）：

- 国内 → `69.63.198.51:20687`：超时（DROP）；→ `:22/:443/:80`：RST（路径可达）。
- 境外（hot-beam-1）→ `:20687`：OPEN。
- 主机 `iptables` 全 ACCEPT、无 nft/ufw/firewalld。

因此断连原因为**国内路径对 `69.63.198.51:20687` 的端口级阻断**，服务器与配置均正常。
本目录保留的是断连前 36 小时与重启前后的原始证据，供改动端口前对照。
