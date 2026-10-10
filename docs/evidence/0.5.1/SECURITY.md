# 0.5.1 安全证据与边界

此页区分源码约束、本地Linux权限实证与未执行的VPS检查；不回写0.5.0历史偏差记录。

| 面 | 本地证据 | 现场状态 |
| --- | --- | --- |
| accountd长期身份 | unit `User/Group=vincula-accountd`；无附加组；empty capability bounding；NoNewPrivileges/ProtectSystem等保留 | PENDING LIVE |
| 固定root准备步骤 | `ExecStartPre=+python3 -I accountd_runtime.py`；仅root规范文件→受限projection及固定accounting文件owner；拒绝symlink/hardlink | 本地真实权限测试PASS；服务启动链PENDING LIVE |
| Secret隔离 | 规范state/users/config仍root私有；projection只有逻辑身份映射、Clash凭据与必要设置，root:accountd 0640；非root不能修改 | 本地UID降权读写边界PASS；VPS ACL/owner PENDING LIVE |
| observer身份 | root控制home/.ssh/authorized_keys，锁定密码、无附加组；公钥restrict+固定命令；独立用户名需显式observe credential | 白名单/路由单测PASS；真实SSH权限PENDING LIVE |
| observer broker | 仅AF_UNIX，peer UID核验、固定命令allowlist、clean env；root只读sandbox，CAP_DAC_READ_SEARCH，2并发×64MiB/16tasks/10%单核 | Unix socket组权限/协议本地PASS；实际cgroup/systemd限制PENDING LIVE |
| listeners | 新增Node管理入口仅`/run/vincula-observer.sock`；probe临时SOCKS绑定127.0.0.1；无新增公网管理HTTP | 源码/配置检查；实际`ss`清单PENDING LIVE |
| no privilege fallback | observe user/ref独立；未配置ref拒绝；auth failure不改用admin，mutation仍admin | 本地测试PASS；真实密钥撤销PENDING LIVE |
| no direct fallback | probe仅有VLESS outbound；curl强制socks5h并清除环境绕过，缺配置/runtime UNKNOWN | 编译/mock测试PASS；真实流量PENDING LIVE |
| 输出/缓存脱敏 | metrics allowlist、固定reason codes、无raw SSH stderr；probe secret只在临时0600文件，argv仅路径；临时文件/进程清理 | 本地回归PASS；Live evidence仍须脱敏 |

## 历史偏差跟踪

- `SEC-050-01`：已实现accountd降权和最小输入，本地权限隔离通过；仍须真实fresh/upgrade/restore/rollback验证，**不宣布已完成现场关闭**。
- `SEC-050-02`：已实现observer key限制、独立用户名、Unix socket broker与资源上限；仍须核对目标sshd有效CA/外部key-command/Match配置并测试PTY/forward/sudo/mutation拒绝，**不宣布已完成现场关闭**。

## 明确保留的权限与限制

accountd的固定pre-start与observer broker仍为root权限组件。前者只生成受限配置/调整固定accounting文件；后者以只读sandbox运行固定既有JSON命令。不能把daemon降权描述为“Node没有root组件”。

Windows profile权限由当前用户ACL保护，POSIX 0600检查不能证明Windows ACL已通过；此项需在使用实际profile前核验。observe公钥替换会改变观察登录入口，按runbook显式操作；本轮未在任何VPS上执行。
