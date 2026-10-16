# VCL machine-readable contracts

JSON Schema 定义 Controller ↔ Node 的只读 observation 协议。

| Schema | 文件 | 引入版本 | 命令 |
| --- | --- | --- | --- |
| `capabilities/v1` | [`capabilities/v1.schema.json`](capabilities/v1.schema.json) | 0.5.0 | `vcl capabilities --json` |
| `telemetry/v1` | [`telemetry/v1.schema.json`](telemetry/v1.schema.json) | 0.5.0 | `vcl telemetry snapshot --json` |
| `monitor/v1` | [`monitor/v1.schema.json`](monitor/v1.schema.json) | 0.5.1 开发中 | Controller `health --json` / `GET /api/monitor`（本机派生视图） |
| `audit-health/v1` | [`audit-health/v1.schema.json`](audit-health/v1.schema.json) | 0.5.2 M2 开发中 | Node `vcl telemetry audit --json`（独立诊断，不扩展 telemetry/v1） |
| `monitor/v2` | [`monitor/v2.schema.json`](monitor/v2.schema.json) | 0.5.2 M2 开发中 | Controller `monitor --json`（前台运行计数）；只读 health/API 保持 v1 |
| `user-traffic/v1` | [`user-traffic/v1.schema.json`](user-traffic/v1.schema.json) | 0.5.2 M3 开发中 | Node `vcl telemetry users --json`（含 open 的 retained 字节和成功 poll 来源） |
| `inspect/v1` | [`inspect/v1.schema.json`](inspect/v1.schema.json) | 0.5.3 | Node `vcl inspect --json`；Controller低频observe采集 |
| `findings/v1` | [`findings/v1.schema.json`](findings/v1.schema.json) | 0.5.2 | Controller `findings --json` / `GET /api/findings`（Node/User 生命周期、脱敏评估） |
| `timeline/v1` | [`timeline/v1.schema.json`](timeline/v1.schema.json) | 0.5.2 | Controller `timeline --json` / `GET /api/timeline`（本地事件与白名单 operation） |

| `inspect-cache/v1` | [`inspect-cache/v1.schema.json`](inspect-cache/v1.schema.json) | 0.5.3 | Controller `inspect [NODE] --json` / GET /api/inspect |
| `baseline/v1` | [`baseline/v1.schema.json`](baseline/v1.schema.json) | 0.5.3 | 本机显式接受的脱敏source snapshot，PRIVATE DB内部合同 |
| `findings/v2` | [`findings/v2.schema.json`](findings/v2.schema.json) | 0.5.3 | 当前Findings，增加七类DRIFT_* |
| `timeline/v2` | [`timeline/v2.schema.json`](timeline/v2.schema.json) | 0.5.3 | 当前Timeline，增加显式baseline事件 |
| `monitor/v3` | [`monitor/v3.schema.json`](monitor/v3.schema.json) | 0.5.3 | 当前前台monitor计数，增加inspection写失败 |
| `verify/v2` | [`verify/v2.schema.json`](verify/v2.schema.json) | 0.5.3 | Node `verify --extended --json`，八分项 |
| `fleet-verify/v2` | [`fleet-verify/v2.schema.json`](fleet-verify/v2.schema.json) | 0.5.3 | Controller `verify --extended --json`，可选专用probe |

v1/v2历史monitor及findings/timeline v1合同保留；0.5.3当前命令使用表中更高版本。`scripts/gen-053-contracts.py`从冻结旧合同和runtime生成扩展合同，正反fixture校验；旧Node `verify --json`无改动。

**规则：**

- Schema 变更 MUST  bump 版本后缀（`v2`），不得 silent 破坏 `v1` 消费者。
- Fixture 正反例：`tests/fixtures/schemas/`。
- Controller ZIP 的 `schemas/` 附带上述全部合同，纳入 controller.lock 与成员验证；runtime 还检查稳定 hash、父级关联和时间顺序，JSON Schema 不替代这些语义约束。
- Secret MUST NOT 出现在任何 contract 字段中。
- 响应大小上限见 [`docs/specs/V0.5.0_Spec.md`](../docs/specs/V0.5.0_Spec.md) §4.2、§5.3。
