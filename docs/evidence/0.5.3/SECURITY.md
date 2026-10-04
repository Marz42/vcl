# 0.5.3 Security / coverage — PENDING LIVE

日期2026-10-04。M1仅离线验证Node Inspect合同与秘密边界；完整0.5.3、实机权限与增强Verify尚待完成。当前候选unreleased，remote required CI未执行。

| 项目 | 离线证据 / 实际限制 | 现场状态 |
| --- | --- | --- |
| 秘密投影 | 严格managed-config/v1白名单；credential UUID/Reality私钥和short-id/Clash secret不进入指纹输出；secret rotation不改hash；未知shape拒绝 | PENDING LIVE |
| observer命令 | exact argv、peer身份、固定执行与stdout预算；observe认证失败不fallback | PENDING LIVE |
| observer网络读取 | unit允许AF_NETLINK用于ss/tc，capability仍仅CAP_DAC_READ_SEARCH；不给CAP_NET_ADMIN，nft/iptables读取可能UNKNOWN/COMMAND_FAILED | PENDING LIVE |
| binary/文件 | 不执行受检sing-box，仅实际SHA匹配安装版本record；regular/symlink/size/读取变化检查；返回固定name与hash/权限，不返回自由路径 | PENDING LIVE |
| root broker/systemd隔离 | 实际ProtectSystem/ProtectHome/PrivateTmp/地址族/CPU/内存/Task限制效果未在生产验证；目录视图与权限可能造成部分覆盖 | PENDING LIVE |
| baseline/Drift/cache/UI | M2尚未实现；须覆盖CAS、cache-only、秘密注入/损坏、容量、Unknown保留ACTIVE、换instance与正式schema版本化 | IMPLEMENTATION PENDING |
| Verify/Data Plane | 增强Verify尚未实现；服务active/listener存在不能证明真实代理成功，需显式probe证据 | IMPLEMENTATION + LIVE PENDING |

Node可返回OK只表示采集完整，不等于配置安全或Human Gate验收。权限/工具失测不当健康零；现场缺firewall覆盖须记录，不能用本地root fixture代替observer route。

现场trace与证据hash见 [LIVE](LIVE.md)（待执行），24h指标见 [SOAK](SOAK.md)（待执行）。按 [用户指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)继续实现并跳过人工等待，不代签、不改写历史0.5.0安全记录。
