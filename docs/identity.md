# 身份合同（0.2.9-dev）

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

## `state.json` schema 1 → 2（0.2.9 保持 2）

| | 0.2.7 | 0.2.8 / 0.2.9 |
| --- | --- | --- |
| `state.json.schema_version` | `1`（无 `instance_id`） | **`2`**（`node.instance_id` 必填 UUID） |
| `users.json.schema_version` | `2` | `2`（不变；`--user-id` 是 CLI） |
| accounting `meta.schema_version` | `3` | **`3`**（无 DDL） |
| `fleet.json.schema_version` | — | 0.2.8 = `1`；**0.2.9 = `2`**（`status`） |
| `fleet.db` | — | 0.2.9 schema **`1`**（工作站本地） |

产品版本 bump **不**自动改 accounting schema。0.2.9 不提供自动 state 2→1 或 fleet.json 2→1；节点回滚 = 恢复 `backup_existing_install` 备份 + 0.2.8 安装器。

## NULL 含义（D5）

`connections.instance_id IS NULL` 固定表示：

```text
physical instance identity was not tracked at that time
```

0.2.7 历史行保持 NULL。禁止用 `node_id` 回填。

## mint 规则

```text
fresh install 0.2.8+:    node_id=UUID() 且 instance_id=UUID() 且 instance_id ≠ node_id
upgrade 0.2.7 → 0.2.8:   保留现有 node_id；为当前物理安装 mint instance_id=UUID()
upgrade 0.2.8 → 0.2.9:   保留 node_id 与 instance_id（不重 mint）
已是 0.2.8/0.2.9 再跑安装器: 保留 node_id 与 instance_id（幂等，不重 mint）
重装/替换（0.3.0）:      同 node_id，新 instance_id —— 0.2.9 只预留语义，不实现 replace-node
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
| `vincula_version` | string | 产品版本（开发戳 `0.2.9-dev`；freeze 为 `0.2.9`） |
| `node_id` | UUID | 逻辑节点 ID |
| `instance_id` | UUID 或 `null` | 当前物理安装；缺则 `null` 且 exit 1 |
| `node_name` | string | 可改的显示名 |
| `utc_now` | string | RFC3339 UTC，`Z` 后缀 |

```json
{
  "schema_version": 1,
  "vincula_version": "0.2.9-dev",
  "node_id": "<uuid>",
  "instance_id": "<uuid>",
  "node_name": "<str>",
  "utc_now": "<RFC3339 UTC, Z>"
}
```

## Fleet-global `user_id` 传播（0.2.9）

`users.json` schema **仍为 2**（已有 `user_id`）。下列 `schema_version` 是 **CLI JSON 合同**，不是 registry schema。0.2.8 → 0.2.9 **不**改 users/state/accounting schema。

身份规则（D16）：**逻辑用户 = 开通时注入的同一个 `user_id`**。tag 仅 UX。禁止用 `display_name` 静默合并。

```text
节点本地 vcl user add TAG（无 --user-id）
  → users_registry_mutate 生成新 user_id=UUID()（与 0.2.8 相同）

节点 vcl user add TAG --user-id UUID（advanced / controller）
  → 校验 UUID 格式
  → 同 registry 内 user_id 已存在 → 拒绝（含不同 tag）
  → 同 tag 已存在 → 仍拒绝（既有 "user tag already exists"）
  → 写入该显式 user_id；credential_id 与 VLESS uuid 仍由本节点新生成

控制器 vcl-fleet user add TAG --nodes a,b
  → controller 生成一个全局 user_id（或接受 --user-id 补救）
  → 对每个目标节点 SSH：vcl user add TAG --user-id GLOBAL --json ...
```

控制器开通前先 `vcl user show TAG --json`（或 list）做幂等：tag 不存在则 add；tag 存在且 `user_id` 相同 → 该节点 SUCCESS；tag 存在且 `user_id` 不同 → FAILED。节点 CLI 本身不幂等。

`vcl user list` 人类表增加 `USER_ID` 列（完整 UUID）。`list`/`show` 的 `--json` **不含** VLESS `uuid`；`add`/`rotate` 的 URI 已含 uuid，仅这些命令输出 URI。

工作站侧流程（PARTIAL、CSV、retire）见 [`fleet.md`](fleet.md)。

### `vcl user add TAG ... --json`（0.2.1）

| 字段 | 说明 |
| --- | --- |
| `schema_version` | `1` |
| `ok` | `true` / `false` |
| `tag` | 用户 tag |
| `user_id` | fleet-global 或本节点生成的 UUID |
| `credential_id` | 本节点新凭据 |
| `vless_uri` | 含 VLESS uuid 的 URI |
| `status` | `active` |
| `enabled` | `true` |

失败：`{"schema_version":1,"ok":false,"error":"..."}`。`error`：`invalid_user_id` \| `duplicate_user_id` \| `duplicate_tag` \| `invalid_tag` \| `failed`。

### `vcl user list --json`（0.2.2）

| 字段 | 说明 |
| --- | --- |
| `schema_version` | `1` |
| `users[].tag` | tag |
| `users[].display_name` | 显示名 |
| `users[].department` | 部门 |
| `users[].user_id` | 稳定 ID |
| `users[].enabled` | 是否启用 |
| `users[].active_credential_id` | 当前 active 凭据（非 VLESS uuid） |
| `users[].credentials` | `{count, active, revoked}` 汇总，不含 secrets |

### `vcl user show TAG --json`（0.2.3）

含 `user_id`、`enabled`、`created_at` 与 `credentials[]`：`credential_id` / `node_id` / `status` / `created_at` / `revoked_at`。凭据对象 **不含** `uuid`。

### `vcl user rotate TAG --json`（0.2.4）

与 add 同形（新 `credential_id` + 新 `vless_uri`；`user_id` 不变）。

`enable` / `disable --json`：`{"schema_version":1,"ok":true,"tag":"...","user_id":"...","enabled":true|false}`。
