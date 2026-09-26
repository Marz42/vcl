# 0.5.1 Monitoring 开发版操作说明

当前为 Controller/Node 0.5.1 开发候选。监控、accountd降权与observer白名单已有实现，真实VPS升级、权限/SSH策略与soak尚待验收，不能按已发布版本理解。Node 0.5.0仍可用于telemetry监控，但没有本次Node权限改动。

## 采集与查看

在既有 Fleet/Workspace 与显式 observe credential 已配置的前提下：

```bash
vcl-fleet monitor --once --json
vcl-fleet monitor NODE --interval 30 --timeout 5 --concurrency 8
vcl-fleet health --json
```

monitor 默认前台持续运行，Ctrl-C 停止并等待有界在途调用清理。只有一个 monitor 可持有同一缓存的监控锁，不占用 Fleet mutation lock。`--once` 执行一轮；`--json` 在本轮完成或前台进程停止时输出一个最终 JSON。采集节点来自进程启动时的启用节点清单，新增/停用节点后重启 monitor。

`health` 与 WebUI Nodes 页的 Monitoring 表只读本地 `observation.db`，不触发 SSH。未采集、坏行、陈旧数据均不显示为正常；表中 Age 是 telemetry 自身时间的年龄。受控关闭 Controller 不会向 Node 发送停止服务操作。

observation.db 位于同 Fleet 的 machine-local fleet.db 旁边，独立于 fleet-cache/v4；默认保留24h原样本、7d的5分钟聚合、90d小时聚合，另受行数/256MiB限制。cache_state=PARTIAL/CACHE_CORRUPT 需要检查本机缓存，不能当成 Node 损坏；不会通过 GET 自动修复。满盘/锁超时写入失败返回非零退出码。正常 accounting 仍使用原 fleet.db。

## 独立真实代理探测

为每个待测 Node 显式创建仅用于监测的 `vcl-probe-*` 测试用户，不复制普通用户的 UUID。将其连接参数保存到**本机私有文件、位于 portable Workspace 之外**；不要提交到 Git。Windows 使用仅当前用户可读 ACL，Linux 使用0600。以下是字段示意，尖括号不是可用凭据：

```json
{
  "schema": "probe-profiles/v1",
  "nodes": {
    "example-node": {
      "node_id": "<registered-node-id>",
      "purpose": "synthetic-probe",
      "user_tag": "vcl-probe-health",
      "server": "<Node-public-IP>",
      "server_port": 443,
      "uuid": "<dedicated-test-user-uuid>",
      "server_name": "<Reality-SNI>",
      "public_key": "<Reality-public-key>",
      "short_id": "<Reality-short-id>",
      "url": "https://<known-endpoint>/"
    }
  }
}
```

安装并校验与项目固定版本兼容的本地 sing-box 与支持 SOCKS5 的 curl，再运行：

```bash
vcl-fleet monitor NODE --once --timeout 10 \
  --probe-profiles /private/path/probe-profiles.json \
  --probe-sing-box /verified/path/sing-box --json
```

该操作显式连接指定HTTPS目标。profile中的 server 当前要求 IP，HTTPS URL 不允许 userinfo/query/fragment；只有 2xx/3xx 视为成功。每次 probe 临时建立127.0.0.1 SOCKS listener，流量只通过 VLESS outbound；不会持久化监听或回退 direct。关闭/超时后清理子进程与临时私有配置。`connect_ms` 是经代理完成目标 TLS handshake 的时间（包含本机 SOCKS 连接与路径建立），不是纯 Node TCP RTT。

未配置 profile、Node id 不一致或缺运行时均显示 UNKNOWN；sing-box active 只证明进程状态。probes 执行周期会产生少量专用用户流量，不与普通用户凭据混用。日志和UI只展示固定失败分类与数值，不记录原始URI/UUID/工具stderr。

## 尚需完成的验收

- ≥10节点受控混合矩阵、真实代理故障、accountd/Controller/SSH故障恢复、24h soak。
- 专用 probe 身份、Windows ACL、实际 sing-box/curl 组合验证。
- Node accountd de-root、observer受限用户和broker的实际systemd/SSH验证，以及安装/升级/回滚权限迁移；本地源码/权限测试不能替代VPS实测。
- 0.5.0升级 ≤3秒精确补证以及最终H05人工验收。

## Node权限与受限observer接入

升级前检查备份与维护窗口，使用Controller已有`node upgrade plan/apply`；0.5.1支持0.3.1/0.3.2/0.5.0来源。新accountd以`vincula-accountd`用户运行；启动前固定root helper生成最小输入并将accounting DB权限交给daemon。canonical配置、Reality私钥和用户UUID文件仍保持root私有。

observer默认不自动配置SSH key或开启socket。使用专用Ed25519观察密钥，将**公钥文件**交给已授权的Node管理员后，由其执行：

```bash
sudo vcl observer install-key --file /admin/path/observer.pub
```

此操作显式替换该observer用户的管理公钥，保持admin登录凭据不变；替换前确认旧观察客户端的迁移安排。观察用户密码必须锁定、无附加组，home/.ssh/authorized_keys由root控制。服务通过本机Unix socket提供五类固定只读命令；broker是受sandbox约束的root读进程，不是开放root shell。

Controller在已有Workspace中绑定观察密钥并指定独立用户名：

```bash
vcl-fleet node set NODE --observe-identity-file /private/path/observer_key \
  --observe-ssh-user vincula-observer
vcl-fleet capabilities NODE --json
vcl-fleet telemetry NODE --json
```

若已有machine-local observe credential_ref，也可使用`--observe-credential-ref REF`。单独设置observe用户名而无显式observe凭据会拒绝读取，不回退admin。部署时必须人工检查sshd有效认证配置，验证没有其他authorized-keys来源/CA绕过key上的forced-command，并实际测试PTY/forward/sudo/mutation被拒。
