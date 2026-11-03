# 2026-10-26 Fleet 状态巡检与日志导出

> 归档自 `tmp/fleet-logs-20261026/SUMMARY.md`（2026-11-02）。原始 journal `.gz`、临时脚本与节点日志为本地未入库产物，已清理；本页保留巡检结论、统计与待办。原始 probe JSON：[2026-10-26-probe.json](2026-10-26-probe.json)。


- 执行环境：`kali-linux` WSL，`VCL_FLEET_HOME=/home/marz/vincula-fleet-live`
- 控制器：`/home/marz/vcl-phase-c-20261010T023206Z/ctrl/vincula-controller-0.5.3/bin/vcl-fleet`
- 日志窗口：`--since -24h`（各 Node 本地时区不同，下表已折算为 UTC）
- 采集方式：只读 SSH 流式读取，Node 上未写任何文件

## probe 结果

`probe --json` → `ok: true`，exit 0，`controller_utc=2026-10-26T06:36:04Z`。

| 节点 | SSH | PROXY | ACCOUNTING |
| --- | --- | --- | --- |
| epicfury | OK | OK | OK |
| upperhand | OK | OK | OK |
| eagleclaw | OK | OK | OK |
| neptunespear | OK | OK | OK |
| hot-beam-1 | OK | OK | OK |
| urgentfury | OK | OK | OK |
| fresh050 | OK | OK | OK |

### 从 5/7 到 7/7 的原因

首次 probe（`bash -lc` 非交互）报 4 台 `AUTH_DENIED`；加载 ssh-agent 后仍有 2 台
（epicfury、hot-beam-1）报 `AUTH_LIMIT`：

- Kali 的 `~/.ssh/config` 是 0 字节空文件（旧备份 `config.bak.20260819123719` 里有
  `Host 104.194.90.172 → IdentityFile … IdentitiesOnly yes` 的钉定，后来丢失）。
- agent 持有 13 把密钥，逐一尝试超过 sshd 默认 `MaxAuthTries=6`，还没轮到正确密钥就断开。
- 带显式 ref 的 5 台不受影响（`vcl-agent-selectors/` 下已有 `upperhand.pub`/`urgentfury.pub`）。

处置（用户确认后执行）：

1. 备份：`~/.ssh/config` → `~/.ssh/config.bak.20261026-before-pin`（原文件 0 字节）。
2. 由既有密钥派生公钥选择器，只放公钥，不复制私钥：
   - `/home/marz/.ssh/vcl-agent-selectors/hot-beam-1.pub`（`SHA256:mb5stFiE…`）
   - `/home/marz/.ssh/vcl-agent-selectors/epicfury.pub`（`SHA256:Posh11D…`）
3. 写入两个 `Host` 块（`IdentityFile` + `IdentitiesOnly yes` + `User root`），`chmod 600`。
4. 复验 probe → 7/7 OK。

## 日志产物

根目录：`tmp/fleet-logs-20261026/<node>/`，每台含
`journal-short-iso.txt.gz`（可读）、`journal-export.gz`（无损）、`METADATA.txt`、
`MANIFEST.txt`（sha256）。

| 节点 | 本地偏移 | 行数 | 明文 | gz | 版本 | UTC 窗口 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| epicfury | -07:00 | 47,055 | 8.8 MB | 499 KB | 0.3.1-rc2 | 10-25 06:38 → 10-26 06:37 |
| upperhand | -07:00 | 73,266 | 13.3 MB | 746 KB | 0.3.1-rc2 | 10-25 06:38 → 10-26 06:38 |
| eagleclaw | -07:00 | 96,637 | 17.6 MB | 902 KB | 0.5.0 | 10-25 06:38 → 10-26 06:37 |
| neptunespear | -07:00 | 124,312 | 23.7 MB | 1397 KB | 0.5.0 | 10-25 06:38 → 10-26 06:38 |
| hot-beam-1 | +00:00 | 1,232 | 0.3 MB | 20 KB | 0.3.1 | 10-25 06:40 → 10-26 06:35 |
| urgentfury | +00:00 | 2,637 | 0.5 MB | 30 KB | 0.3.2 | 10-25 06:42 → 10-26 06:13 |
| fresh050 | +08:00 | 29,531 | 5.3 MB | 243 KB | 0.5.0 | 10-25 06:41 → 10-26 06:39 |

合计 69.5 MB 明文 / 约 25 MB 落盘，18 项 PASS，0 FAIL。

## 观察

1. **时区不统一**：4 台 `-07:00`（太平洋时间）、2 台 `+00:00`、1 台 `+08:00`。
   按原始时间戳看「停在昨天」是错觉，折算 UTC 后窗口都到当前时刻。跨 Node 关联事件时
   必须先归一化时区。
2. **版本仍为混合**：0.3.1 / 0.3.1-rc2 / 0.3.2 / 0.5.0，与既有升级计划一致，未升级。
3. **urgentfury 今晨重启**：`2026-10-26T06:13:41Z`（本地 14:13）sing-box 与
   vincula-accountd 同时 `Started`，窗口内无 CrashLoop / 失败痕迹。建议确认是否为计划内
   操作。
4. **日志量差异极大**：neptunespear 12.4 万行 vs hot-beam-1 1.2 千行；ERROR 行主要为
   REALITY 无效握手（与 hot-beam-1 上一轮结论一致），属公网探测噪声。
5. `status` 缓存显示 7 台 `last_sync` 停在 2026-10-14（约 11.8 天前），与本次实时
   probe 的 7/7 OK 不矛盾：前者是本地缓存年龄，需执行 `sync --full` 才回填。

## 复现

```bash
export VCL_FLEET_HOME=/home/marz/vincula-fleet-live \
       VCL_FLEET_LOCAL_STATE=/home/marz/.local/state/vincula \
       XDG_CONFIG_HOME=/home/marz/.config
C=/home/marz/vcl-phase-c-20261010T023206Z/ctrl/vincula-controller-0.5.3/bin/vcl-fleet
python3 $C probe --json
```

日志导出脚本见 `tmp/export-one.sh`（单台）与 `tmp/export-remaining.sh`（批量）。注意：
`export-node-logs.sh` 内置 `REPO` 按 `tmp/` 位置推算，放在 `docs/evidence/0.5.3/tools/`
下会得到 `docs/bin/vcl-fleet`，必须显式传 `VCL_FLEET_BIN`。
