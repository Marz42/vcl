# 0.5.3 M3 — Extended Verify

日期2026-10-05；IMPLEMENTED。完整回归、固定输入和独立制品证据见[RC](RC.md)。

Node固定命令`vcl verify --extended --json`、capability verify/v2；observer仅允许exact argv。共享8秒Inspect/文件/SQLite预算，缺安装artifact仍输出UNKNOWN，不受旧require_install早退影响。旧`verify --json`及identity/proxy/accounting/utc_now未变，升级/恢复保留旧消费路径。

Identity、Configuration、Integrity、Permissions、Services、Listeners、Accounting、Data Plane八项PASS/FAIL/UNKNOWN/UNSUPPORTED。整体有FAIL则FAIL，否则失测为UNKNOWN；只有全部PASS才PASS。Configuration比较受管完整canonical配置，包括内部秘密一致性但不输出秘密；Integrity仅实际binary对安装lock，不执行受检binary；Permissions核对Linux可见权限；Clash实际bind/自定义端口暴露检查不假定9090；accounting只读结构/quick_check/heartbeat/successful poll。

Node Data Plane固定UNKNOWN/NO_PROBE。Controller`verify --extended --name NODE --json`仅observe，旧capability降级；显式`--probe-profiles`沿用私有专用代理profile、固定客户端版本与HTTPS探测。RPC/probe及probe后identity同用Node deadline。只有探测成功且后验identity相符才PASS；探测失败FAIL，缺配置/runtime/身份变更/超时UNKNOWN；单Node失败隔离。

自动化覆盖实际installer嵌套node身份、canonical配置的凭据/秘密/路由不一致、binary漂移不执行替换binary、Clash自定义端口与非loopback暴露、缺工具/权限/安装artifact、accounting陈旧/损坏、root权限、schema秘密与伪PASS拒绝、observe降级/认证/时间/身份、显式probe成功/失败/换instance、真实临时CLI argv与文件bytes/mtime不变。verify/v2及fleet-verify/v2正式schema/正反fixture随Controller打包。

限制：canonical一致性不是sing-box语法执行；binary lock不是管理员不可改写的信任根；listener不核对process归属或公网可达；权限与services摘要不代表完整systemd隔离；accounting不证明计费级准确。Inspect固定runtime投影仍为M1的10项，新增Verify collector由制品lock和Node生命周期清单覆盖。真正代理前后对照与OS/observer现场PENDING LIVE，H05 PENDING HUMAN。

2026-10-07后续：修复NULL/非法heartbeat容错、Clash准确地址核对、矛盾probe结果UNKNOWN及任何probe尝试后的身份再绑定。后验身份失败现在返回AUTH_FAILED/TIMEOUT/ERROR并丢弃整个旧snapshot；不再发布换机前分项。新增失败用例、原始FAIL及复验见[阶段收口](PHASE_05_CLOSEOUT.md)，以最新[SPEC](../../specs/V0.5.3_Spec.md)为准。
