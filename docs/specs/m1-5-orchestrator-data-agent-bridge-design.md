# M1.5 Orchestrator ↔ Data Agent Tool Bridge Design

## 目标

把 M1 的 Data Agent SQL HITL 能力挂回主 Orchestrator，但只开放“创建任务”能力：

- Orchestrator 可以创建 `data_agent_run`
- Orchestrator 不可以 approve SQL
- Orchestrator 不可以 execute SQL
- SQL 生成、审核、执行、写回继续由 M1 Data Agent API 与权限模型兜底

## 允许路径

`User Chat -> deterministic router -> DataAgentRunFlow -> create_data_agent_run_tool -> DataAgentService.create_run -> ConversationTurn.artifacts -> SQLReviewCard -> M1 APIs`

## 禁止路径

- `Orchestrator -> approve`
- `Orchestrator -> execute`
- `GeneralChatFlow broad tool calling -> create_data_agent_run_tool`
- `Orchestrator -> sql_text / approved_sql / manual_sql`

## 路由边界

### 明确 Data Agent 请求

命中以下显式语义时，进入 `create_data_agent_run`：

- `Data Agent`
- `SQL 审核任务`
- `生成 SQL`
- `帮我写 SQL`
- `创建 SQL 任务`

### 写回请求

只有同时满足以下条件，才推断为 `bucket_writeback`：

1. 有明确写回意图：`补数 / 写回 / 回填 / writeback / 修复缺失数据`
2. 有明确 bucket：`app / behavior / credit`

否则进入 `clarify_data_request`，不猜 bucket。

### 模糊数据请求

以下请求进入 `clarify_data_request`：

- `查数据`
- `帮我查一下数据`
- `取一下数据`

resolution card 只提供两个选项：

- `profile_chat`
- `create_sql_review_task`

## Tool Bridge

新增 `create_data_agent_run_tool`：

- 输入：
  - `natural_language_request`
  - `target_country`
  - `run_type`
  - `output_bucket`
  - `output_format`
- 输出：
  - `type`
  - `run_id`
  - `status`

约束：

- 仅调用 `DataAgentService.create_run(...)`
- 输入 schema `extra="forbid"`
- 拒绝 `sql_text / approved_sql / manual_sql`
- 使用当前 `UserContext`
- 工具自行打开 auth DB session

## Flow 设计

### DataAgentRunFlow

固定执行：

1. 权限与 country access 检查
2. 调用 `create_data_agent_run_tool`
3. 写 assistant final turn + `data_agent_run` artifact

返回文案：

`我已为你创建一个 Data Agent SQL 审核任务，请在下方卡片中确认 SQL。`

### ClarifyDataRequestFlow

只用于模糊“查数据”场景：

1. 发出 `clarify_data_request` resolution
2. 若用户选 `create_sql_review_task`，使用 original prompt 创建 run
3. 若用户选 `profile_chat`，不创建 run，回到普通画像/对话引导

## Artifact 契约

assistant final turn 挂：

```json
{
  "type": "data_agent_run",
  "run_id": "..."
}
```

artifact 只存引用，不嵌入 SQL 文本或安全结果。

## SSE / Session 持久化

final SSE payload 与 session turn 持久化统一使用：

```json
{
  "type": "final",
  "final_message": "...",
  "artifacts": [
    { "type": "data_agent_run", "run_id": "..." }
  ]
}
```

## 前端

- 普通 chat turn 支持渲染 `data_agent_run` artifact
- `SQLReviewCard` 复用 M1 显式模式组件
- 显式 Data Agent mode 与普通 chat artifact card 共用 run cache
- run detail 通过 `/api/data-agent/runs/{run_id}` 懒加载

## 审计

新增事件：

- `orchestrator.data_agent_run.created`

metadata 至少包含：

- `user_id`
- `project_id`
- `country`
- `session_id`
- `run_id`
- `run_type`
- `sql_hash`

不记录 SQL 明文。

## Out of Scope

- 不做 auto-approve
- 不做 auto-execute
- 不改 M1 SQL HITL 状态机
- 不改 `bucket_writeback` 权限模型
- 不做 Vanna / RAG
- 不给 GeneralChatFlow 增加新的 Data Agent broad tool autonomy
