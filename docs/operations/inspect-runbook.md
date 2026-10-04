# Node Inspect（0.5.3 M1 开发中）

当前 stamp 仍0.5.2；[阶段状态](../evidence/0.5.3/SUMMARY.md)与[冻结合同](../specs/V0.5.3_Spec.md)是适用范围。仅 Node 命令及内部 observe fetch 已实现；Controller缓存/Drift/增强Verify继续开发。

在开发候选已安装的 Node 上，固定命令为：

```bash
vcl capabilities --json
vcl inspect --json
```

受限 observer 仅允许这个固定 Inspect argv；附加文件路径或 refresh 参数拒绝。旧 Node 不含 inspect/v1，返回 UNSUPPORTED；不要改用管理凭据绕过 observe 认证失败。

结果含固定环境分项、规范 listener 与16项受管指纹。OK 只表示采集完整，不能当作基线验收、配置安全或代理可用证明。PARTIAL/UNKNOWN/UNSUPPORTED/UNREADABLE、reason 与 truncated 必须一起查看；空数组在缺工具/权限/预算失败时不等于没有 listener/防火墙。NON_LOOPBACK 地址不证明公网可达，base policy 不证明全部规则效果。observer允许Netlink读取，但不赋予CAP_NET_ADMIN；防火墙可能UNKNOWN/COMMAND_FAILED，现场覆盖另验。

资源预算默认6秒、每命令1秒、stdout/output 64KiB；数组最多64项，普通文件1MiB、config4MiB、binary256MiB。sing-box 版本通过安装 lock 与实际 hash 匹配，不执行受检 binary；更新信息来自已有缓存，不 refresh packages。字段含义和受管严格投影见合同，不拉取完整 secret config。

实机操作尚未执行。本轮所有支持OS现场核对、service restart count/文件hash/mtime/实际代理前后对照、listener/config/unit 人为drift恢复和24h soak均 **PENDING LIVE**；H05/H06/H07 **PENDING HUMAN**。依 [延期记录](../plans/MANUAL_VALIDATION_DEFERRED.md)跳过手工等待，现场结果另补，不将临时文件/WSL/fake-SSH测试写成现场PASS。
