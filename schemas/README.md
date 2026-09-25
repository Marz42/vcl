# VCL machine-readable contracts

JSON Schema 定义 Controller ↔ Node 的只读 observation 协议。

| Schema | 文件 | 引入版本 | 命令 |
| --- | --- | --- | --- |
| `capabilities/v1` | [`capabilities/v1.schema.json`](capabilities/v1.schema.json) | 0.5.0 | `vcl capabilities --json` |
| `telemetry/v1` | [`telemetry/v1.schema.json`](telemetry/v1.schema.json) | 0.5.0 | `vcl telemetry snapshot --json` |

**规则：**

- Schema 变更 MUST  bump 版本后缀（`v2`），不得 silent 破坏 `v1` 消费者。
- Fixture 正反例：`tests/fixtures/schemas/`。
- Secret MUST NOT 出现在任何 contract 字段中。
- 响应大小上限见 [`docs/specs/V0.5.0_Spec.md`](../docs/specs/V0.5.0_Spec.md) §4.2、§5.3。
