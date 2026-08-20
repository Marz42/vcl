# Vincula live upgrade RC — 0.2.4 → 0.2.5 → 0.2.6

面向 **远端 Debian amd64 VPS** 的升级链实机验收。

## 前置

```bash
export VCL_RC_HOST=x.x.x.x
export VCL_RC_USER=root
export VCL_RC_PASS='...'   # 或改用 SSH key / VCL_RC_SSH
export VCL_SERVER=$VCL_RC_HOST

# 编排机需 sshpass（密码登录时）
sudo apt-get install -y sshpass

bash scripts/rc-live-upgrade-driver.sh
```

制品由 [`scripts/rc-build-artifacts.sh`](../scripts/rc-build-artifacts.sh) 从 tag `v0.2.4` / `v0.2.5` / `v0.2.6` 组装，上传到 `/root/vcl-rc-trees/`。

主机证据：`/root/vcl-rc-evidence/upgrade-246/`。  
本地摘要：[`docs/evidence/0.2.4-0.2.6-live/`](../docs/evidence/0.2.4-0.2.6-live/)。

## Phase 与 Pass

| Phase | 内容 | Pass |
| --- | --- | --- |
| 00 | 卸载/清理 | 无 `/etc/vincula` `/var/lib/vincula` |
| 01 | Fresh 0.2.4 | VERSION、双服务、`vcl verify` |
| 02 | Baseline | Clash triad、status/check/link |
| 03 | → 0.2.5 | 身份不变；user verify/import；remove 拒绝 |
| 04 | → 0.2.6 | 身份不变；stats/csv/json；stale + connections UNAVAILABLE |
| 05 | Reboot | 双服务 + verify + verify |
| 06 | Broken 0.2.6 migrate | 非零；VERSION 回 0.2.5 |
| 07 | Clean reinstall 0.2.6 | verify PASS |

## 手动分步

```bash
# on host
env VCL_SERVER=... bash /root/rc-live-onhost.sh 00
env VCL_SERVER=... bash /root/rc-live-onhost.sh 01
# ...
```

## 安全

勿把 `VCL_RC_PASS` 写入仓库或证据文件；测完后轮换 root 密码。
