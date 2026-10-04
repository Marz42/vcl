# 0.5.3 Live acceptance — PENDING LIVE

日期2026-10-04。未执行真实VPS操作；按 [用户指令](../../plans/MANUAL_VALIDATION_DEFERRED.md)跳过手工等待。M1 Node Inspect fixture/WSL与制品证据见 [M1](M1_NODE.md)，不能替代本页现场记录。完整0.5.3的Controller/Drift/增强Verify仍待实现，现场候选未固定。

## 固定现场输入（待执行者补齐）

Node/Controller版本与SHA、源码commit与manifest、受管拓扑/节点数、OS/架构、observer路由、accountd运行身份、维护窗口、操作者、UTC起止时间均 **PENDING**。当前stamp0.5.2不表示完整0.5.3 RC。记录部署与恢复步骤后再执行，不能仅填最终截图。

| 场景 / AC | 现场需要的原始证据 | 状态 |
| --- | --- | --- |
| AC-5.3-01 支持OS/IPv4/IPv6 | 主机独立inventory与inspect分项对照，public/loopback/link-local/zone listener、缺工具/权限覆盖；每个支持OS与架构单列 | PENDING LIVE |
| AC-5.3-02/04 baseline与drift | 明确已接受baseline的来源/SHA/current instance；新增非预期listener、改受管非secret config/unit/runtime后Drift与Finding；恢复后MATCH/RESOLVED；缺测期间不误关ACTIVE | PENDING LIVE |
| Clash/Permissions | 实际Clash loopback-bind、配置模式/属主、observer命令拒绝与AUTH_FAILED不fallback；Netlink读取许可/实际firewall受限时UNKNOWN | PENDING LIVE |
| AC-5.3-03 只读前后对照 | 受管文件bytes/SHA/mtime、service restart count、实际客户端代理前后成功证据；排除正常业务计数变化，无隐式package update/restart/reconcile | PENDING LIVE |
| Verify交叉核对 | Identity/Configuration/Integrity/Permissions/Services/Listeners/Accounting/Data Plane分项与独立人工检查；缺工具/无实际probe不PASS | PENDING LIVE |
| 混合版本/换instance | 旧Node UNSUPPORTED、observe认证失败、Node replacement旧baseline UNKNOWN、新instance显式接受 | PENDING LIVE |

不公开secret config、UUID credential、Reality私钥、Clash secret或SSH key。Node/instance逻辑身份可用脱敏映射关联；原始敏感证据仅在受控位置保管，公开文档只记录非秘密结果与hash。
