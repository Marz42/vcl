# 0.5.3 Security / coverage — PENDING LIVE

2026-10-07补充：增强Verify现拒绝其他loopback地址代替实际配置地址；非法审计时间保持JSON/UNKNOWN；probe尝试后身份失效时清除旧snapshot，且observe AUTH_FAILED/TIMEOUT不fallback。本地回归与新制品见[阶段收口](PHASE_05_CLOSEOUT.md)。`a9655e2`的CI #86已PASS；以下2026-10-05状态保留，当前修复另待远端CI，实际权限仍PENDING LIVE。
日期2026-10-05。M1–M3本地实现完成，新增cache/CAS/Drift/Verify离线证据见[RC](RC.md)；实机权限待完成。当前候选unreleased，remote required CI未执行。

| 项目 | 离线证据 / 实际限制 | 现场状态 |
| --- | --- | --- |
| 秘密投影 | 严格managed-config/v1白名单；credential UUID/Reality私钥和short-id/Clash secret不进入指纹输出；secret rotation不改hash；未知shape拒绝 | PENDING LIVE |
| observer命令 | exact argv、peer身份、固定执行与stdout预算；observe认证失败不fallback | PENDING LIVE |
| observer网络读取 | unit允许AF_NETLINK用于ss/tc，capability仍仅CAP_DAC_READ_SEARCH；不给CAP_NET_ADMIN，nft/iptables读取可能UNKNOWN/COMMAND_FAILED | PENDING LIVE |
| binary/文件 | 不执行受检sing-box，仅实际SHA匹配安装版本record；regular/symlink/size/读取变化检查；返回固定name与hash/权限，不返回自由路径 | PENDING LIVE |
| root broker/systemd隔离 | 实际ProtectSystem/ProtectHome/PrivateTmp/地址族/CPU/内存/Task限制效果未在生产验证；目录视图与权限可能造成部分覆盖 | PENDING LIVE |
| baseline/Drift/cache/UI | M2已实现并离线覆盖CAS、cache-only、秘密注入/损坏、容量、UNKNOWN保留ACTIVE、换instance与schema版本化 | PENDING LIVE |
| Verify/Data Plane | 增强Verify已实现，Node Data Plane UNKNOWN；Controller仅显式probe并核对后验identity，真实现场代理仍待测 | PENDING LIVE |

Node可返回OK只表示采集完整，不等于配置安全或Human Gate验收。权限/工具失测不当健康零；现场缺firewall覆盖须记录，不能用本地root fixture代替observer route。

现场trace与证据hash见 [LIVE](LIVE.md)（待执行），24h指标见 [SOAK](SOAK.md)（待执行）。按 [用户指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)继续实现并跳过人工等待，不代签、不改写历史0.5.0安全记录。
