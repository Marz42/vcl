# 2026-10-26 hot-beam-1 状态巡检

> 归档自 `tmp/node-logs/hot-beam-1-20261026T062009Z/SUMMARY.md`（2026-11-02）。原始 journal 导出与 `tmp/` 包装脚本已清理；复现命令中的本地路径仅作历史记录。


- 采集时间：2026-10-26 06:20 UTC / 14:20 CST
- 目标：`hot-beam-1` = `104.194.90.172:22`（root，`~/.ssh/key`，ED25519）
- 主机密钥指纹：`SHA256:yUgP2j8Cr5RFIuz/B+Onyld4g1nfxNuqucV9heoD86k`
- 采集方式：只读 SSH 流式读取，Node 上未写任何文件

## 系统状态

| 项 | 值 |
| --- | --- |
| 主机名 | hot-beam-1.localdomain |
| 系统 / 内核 | Debian 13 / 6.12.101+deb13-amd64 |
| 运行时长 | 25 天 4 小时 |
| 负载 (1/5/15m) | 0.00 / 0.00 / 0.00 |
| CPU | 2 vCPU |
| 内存 | 1031 MiB 中已用 264 MiB（available 766 MiB） |
| Swap | 544 MiB 中已用 26 MiB |
| 磁盘 | `/` 19G，已用 3.7G（22%） |
| Vincula 版本 | 0.3.1 |
| sing-box | 1.13.18（Go 1.25.12） |
| sing-box.service | active / enabled，自 2026-10-01 02:03:47 UTC 起，重启 0 次 |
| vincula-accountd.service | active / enabled，自 2026-10-01 02:03:47 UTC 起，重启 0 次 |
| 监听 | 0.0.0.0:443 (sing-box)、127.0.0.1:9090 (sing-box/clash api)、0.0.0.0:22 (sshd) |

结论：管理面与代理服务均正常，资源余量充足，无重启。

## 日志导出

- 范围：`--since -24h`，单位 `sing-box.service` + `vincula-accountd.service`
- 实际窗口：2026-10-25T06:21:15Z → 2026-10-26T06:12:01Z
- 行数：1260（273,768 字节明文）
- 单位分布：sing-box 1260 行；vincula-accountd 0 行（期间无输出）

| 文件 | 说明 |
| --- | --- |
| `journal-short-iso.txt.gz` | 可读格式（short-iso），gzip |
| `journal-short-iso.txt` | 同上，解压后明文，未纳入 MANIFEST 校验 |
| `journal-export.gz` | 无损格式（`-o export`，1260 条记录），为文本序列化；需 `systemd-journal-remote` 转回 journal 文件，不能直接 `journalctl --file` |
| `METADATA.txt` | 身份/版本/log 配置/unit 属性/unit 文件/journald 限制/boots/窗口 |
| `MANIFEST.txt` | 各产物 sha256、行数、导出时间、reimport 提示 |

## 需要关注

1. **REALITY 无效握手占一半日志**：1260 行中 630 条为
   `inbound/vless[vless-reality-in]: TLS handshake: REALITY: processed invalid connection`，
   来自 189 个不同源 IP。这是公网 REALITY 入口被扫描/探测时的预期拒绝行为，
   服务本身未崩溃；但噪声会掩盖真实故障，建议按需降级该日志或做审计聚合。
2. **SSH 暴力尝试**：`172.238.29.173` 在 10-25 20:29–21:21 多次对 root 及
   `debian`/`admin`/`tpcheck` 等账户爆破，均被 `maximum authentication attempts exceeded` 拦截。
   该 IP 同时也是 REALITY 探测源。建议确认 sshd 是否已禁用密码登录、是否需要 fail2ban。
3. **journald 无上限**：已占用 1.7G，`/var/log/journal` 为持久存储，journald.conf
   未设置 `SystemMaxUse`/`MaxRetentionSec`。19G 磁盘上长期运行存在膨胀风险。
4. `vincula-accountd` 24 小时内零日志：服务 active 且 0 重启，但没有输出可佐证
   计费/审计活动，建议按其日志级别确认是否本就静默。

## 复现命令

```bash
cd /mnt/d/Repos/Vincula
VCL_FLEET_HOME=$PWD/tmp/ws-node1 \
VCL_FLEET_BIN=$PWD/bin/vcl-fleet \
SSH_BIN=$PWD/tmp/ssh-hb1 \
bash docs/evidence/0.5.3/tools/export-node-logs.sh node1 --since "-24h"
```

注意：`export-node-logs.sh` 内置的 `REPO` 按 `tmp/` 位置推算，放在
`docs/evidence/0.5.3/tools/` 下会得到 `docs/bin/vcl-fleet`，必须显式传
`VCL_FLEET_BIN`。另外本机 `~/.ssh/key` 能登录，但 fleet 注册表里 node1 的
`admin_credential_ref` 为 `-`，脚本自身解析不到私钥，故用 `SSH_BIN` 包装器注入。
