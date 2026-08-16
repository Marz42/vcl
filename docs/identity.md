# 身份合同（0.2.8）

`node_id` 是逻辑节点身份，永久冻结。`instance_id` 是一次物理安装。二者均为 UUID，且 **不得相等**。

## `node_id` vs `instance_id`

| | `node_id` | `instance_id` |
| --- | --- | --- |
| 含义 | 逻辑服务节点 / 线路 | 该逻辑节点的一次物理部署 |
| 寿命 | 节点存在期间不变 | 随重装 / 替换而变（替换见 0.3.0） |
| 可变操作 | `name` 可改；改 IP / hostname **不**改 `node_id` | 当前安装 mint 一次后幂等保留 |
| 禁止 | **禁止重铸**；不引入第二套逻辑 ID | **禁止**复制 `node_id` |

现有 UUID `node_id`（已写入 `state.json` `node.node_id`、`config.toml` `node_id`、`users.json` credentials、accounting）**就是**逻辑节点 ID（D4）。0.2.8 冻结该语义。

## 单一事实来源（SoT）

`instance_id` 的 canonical SoT 是 **`/etc/vincula/state.json` → `node.instance_id`**。

| 存储 | `instance_id` |
| --- | --- |
| `state.json` `node.instance_id` | **SoT**。schema 2 必填 UUID |
| `config.toml` | **不写**。继续只镜像 `node_id`（历史双写，0.2.8 不扩大） |
| `accounting.db` `connections.instance_id` | 新 INSERT 从 SoT 读取后写入；**不**把 DB 当 SoT |
| `fleet.json` | **不存** `instance_id`（远程节点才是当前物理实例的权威） |

accountd 通过 `VCL_STATE_FILE`（默认 `/etc/vincula/state.json`）读 `node.instance_id`。读不到 → SQL NULL（少计身份）。**禁止**回退复制 `node_id`。

`ON CONFLICT UPDATE` 不得改已有行的 `instance_id`（继续的 0.2.7 世代保持 NULL）。

## `state.json` schema 1 → 2

| | 0.2.7 | 0.2.8 |
| --- | --- | --- |
| `state.json.schema_version` | `1`（无 `instance_id`） | **`2`**（`node.instance_id` 必填 UUID） |
| `users.json.schema_version` | `2` | `2`（不变） |
| accounting `meta.schema_version` | `3` | **`3`**（列已存在；只改写入值，无 DDL） |

产品版本 bump **不**自动改 accounting schema。0.2.8 不提供自动 state 2→1；回滚 = 恢复 `backup_existing_install` 备份 + 0.2.7 安装器。

## NULL 含义（D5）

`connections.instance_id IS NULL` 固定表示：

```text
physical instance identity was not tracked at that time
```

0.2.7 历史行保持 NULL。禁止用 `node_id` 回填。

## mint 规则

```text
fresh install 0.2.8:     node_id=UUID() 且 instance_id=UUID() 且 instance_id ≠ node_id
upgrade 0.2.7 → 0.2.8:   保留现有 node_id；为当前物理安装 mint instance_id=UUID()
已是 0.2.8 再跑安装器:   保留 node_id 与 instance_id（幂等，不重 mint）
重装/替换（0.3.0）:      同 node_id，新 instance_id —— 0.2.8 只预留语义，不实现 replace-node
0.2.7 历史 accounting 行: instance_id IS NULL 保持 NULL
新 INSERT（新连接或新 generation）: 写入当前 instance_id
```

mint 后若偶然 `instance_id == node_id`，再 mint 一次；仍相等则失败。禁止 `instance_id = node_id` 复制。

## UUID 格式

`node_id`、`instance_id` 均为小写 RFC 4122 UUID：

```text
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$
```

由 `uuid.uuid4()` 生成。非法 / 空 / 等于 `node_id` 的 `instance_id` 视为未 mint。

## `vcl identity --json`

字段合同（CLI 在 Phase 4e 落地；本页冻结字段）。`schema_version` 是 **identity JSON** 合同版本，不是 `state.json` schema。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `vincula_version` | string | 产品版本（冻结为 `0.2.8`） |
| `node_id` | UUID | 逻辑节点 ID |
| `instance_id` | UUID 或 `null` | 当前物理安装；缺则 `null` 且 exit 1 |
| `node_name` | string | 可改的显示名 |
| `utc_now` | string | RFC3339 UTC，`Z` 后缀 |

```json
{
  "schema_version": 1,
  "vincula_version": "0.2.8",
  "node_id": "<uuid>",
  "instance_id": "<uuid>",
  "node_name": "<str>",
  "utc_now": "<RFC3339 UTC, Z>"
}
```
