# 0.5.1 兼容性证据

| Controller | Node | 能力/路径 | 方法 | 状态 |
| --- | --- | --- | --- | --- |
| 0.5.1 | 0.3.1 / 0.3.2 | 旧管理；新observation缺失为UNSUPPORTED | 既有mixed-version fake-ssh回归 | PASS fixture；真实环境PENDING LIVE |
| 0.5.1 | 0.5.0 | capabilities/v1、telemetry/v1合同可消费；无新Node硬化 | schema/服务单元测试，版本不用于猜feature | PASS local contract；真实环境PENDING LIVE |
| 0.5.1 | 0.5.1 | monitor、capability/telemetry、observe/admin用户名路线 | 0.5.1 fake Node +服务/UI测试 | PASS fixture；真实环境PENDING LIVE |
| 0.5.1 | 0.3.1 / 0.3.2 / 0.5.0 → 0.5.1 | typed upgrade allowlist；后验/rollback | allowlist单测及既有upgrade failure injection回归 | PASS offline；真实升级/≤3s PENDING LIVE |
| 旧Controller | 0.5.1 | legacy单节点管理子集 | 本轮未验证 | PENDING；不宣称独立observe用户名完整兼容 |

最低兼容Node仍为0.3.1；不自动强制Fleet升级。Node身份、URI和accounting保留仍是升级验收要求，不能只由allowlist通过推断Live已保留。

本轮实际本地环境为Windows Controller Python测试和Debian WSL2；Debian 12/13 CI、其他声明OS/arch与实际VPS需要各自证据。仓库已有CI矩阵不等于本次远端CI已运行。
