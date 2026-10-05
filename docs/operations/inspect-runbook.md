# Inspect / Baseline / Drift / Verify（0.5.3）

本地候选0.5.3，最低Node0.3.1，尚未发布。状态见[evidence](../evidence/0.5.3/SUMMARY.md)，合同见[SPEC](../specs/V0.5.3_Spec.md)。实机/24h soak PENDING LIVE，H05/H06/H07 PENDING HUMAN。

## 采集与只读查询

```bash
vcl capabilities --json
vcl inspect --json
vcl-fleet monitor NODE --once --timeout 15
vcl-fleet inspect NODE --json
vcl-fleet inspect --json
```

Node inspect有界且不执行受检binary、包更新/重启/修复。Controller monitor低频默认300秒采集Inspect（--inspect-interval 60～600）；capability/telemetry/diagnostics/inspect/identity共享每Node deadline。长时间monitor运行可持续更新；默认telemetry30秒。单次查询inspect、HTTP GET与UI不采集，仅读本机inspection.db；指定NODE提供完整脱敏snapshot，Fleet列表和UI显示摘要。旧Node能力缺失UNSUPPORTED，observe AUTH_FAILED不fallback。

OK只表示采集完整，不代表已验收、安全或代理可用。PARTIAL/UNKNOWN/UNREADABLE与reason/truncated一起查看；空数组不证明没有listeners/firewall。NON_LOOPBACK不证明公网可达；firewall base policy不代表所有规则，observer没有CAP_NET_ADMIN，覆盖可能UNKNOWN。

## 显式接受比较基线

检查snapshot内容与SHA，必要的listeners/services/versions/fingerprints必须完整；当前成功telemetry≤90秒、Inspect≤600秒。接受仅写本机缓存，不远程采集。下面的SHA使用上一条inspect实际输出，不能照抄占位值。

```bash
vcl-fleet baseline accept NODE --sha256 SNAPSHOT_SHA --json
vcl-fleet inspect NODE --json
vcl-fleet findings NODE --refresh --json
vcl-fleet timeline NODE --json
```

LOCAL_ACCEPTED表示明确选择参照，不签署Human Gate/实机验收。首次采集不会自动接受。预览后样本变化、跨instance/endpoint、陈旧或缺项会拒绝；重新查询新样本后再决定。替换基线仍需显式accept，独立记录BASELINE_ACCEPTED，不记为文件修复。清除时用当前baseline的baseline_sha256：

```bash
vcl-fleet baseline clear NODE --sha256 BASELINE_SHA --json
```

Drift七分项比较listeners/services/versions/config/units/runtime/binary。任一DRIFT优先，其余失测UNKNOWN；缺测保留ACTIVE Finding，完整MATCH恢复。秘密轮换不影响config非secret指纹，但增强Verify会检查配置内秘密一致性。baseline持久保留到显式替换/删除，latest7天，1024Node/128MiB容量拒绝新目标；损坏缓存不由GET修复。

## 八项增强 Verify

```bash
vcl verify --extended --json
vcl-fleet verify --extended --name NODE --json
vcl-fleet verify --extended --name NODE --json --probe-profiles /PRIVATE/probe-profiles.json
```

增强接口包含Identity/Configuration/Integrity/Permissions/Services/Listeners/Accounting/Data Plane。配置一致性、安装lock SHA、权限/服务/listener/poll不替代真实代理证据。无显式专用probe时Data Plane为UNKNOWN；probe需符合[专用profile约束](monitoring-runbook.md)，不要使用普通用户UUID或把私有profile放进portable Workspace。probe后再次核对identity，换机或budget不足保留UNKNOWN。Controller仅全部PASS返回0，其余返回2；Node已有FAIL返回1，UNKNOWN可返回0但必须读JSON状态。

旧`vcl verify --json`保持兼容，升级/恢复继续使用旧合同。没有自动reconcile/重启。支持OS实机对照、actual observer/accountd权限、文件与restart count/实际代理前后、人工Drift恢复和连续24h soak均待现场执行，不能以WSL或临时fixture签署PASS。
