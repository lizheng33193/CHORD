# M1.5 Orchestrator ↔ Data Agent Tool Bridge Plan

## 范围

本阶段只做一件事：

把 Data Agent SQL HITL 作为 Orchestrator 的一个受控工具桥接回来。

不做：

- 自动 approve
- 自动 execute
- 普通 chat 全量自动路由到 Data Agent
- Vanna / RAG
- M1 SQL HITL 状态机改造

## 实施步骤

1. 扩展 `KnownIntent / NormalizedRequest`
2. 在 `request_router.py` 增加 deterministic keyword routing
3. 新增 `create_data_agent_run_tool`
4. 新增 `DataAgentRunFlow`
5. 新增 `ClarifyDataRequestFlow`
6. 把两个 flow 接入 `select_known_flow()`
7. 扩展 `persist_final_message(...)` 支持 artifacts
8. 前端 reducer 接住 `final.artifacts`
9. ChatPanel 普通 chat 渲染 `SQLReviewCard`
10. 前端添加 `fetchDataAgentRun(runId)` 与共享 run cache
11. 新增 `orchestrator.data_agent_run.created` 审计
12. 补定向后端 / 前端回归测试

## 已落地的实现约束

- `create_data_agent_run_tool` 不进入 `get_tool_registry()`
- tool input schema 使用 `extra="forbid"`
- `sql_text / approved_sql / manual_sql` 会直接校验失败
- assistant final turn 才允许挂 `artifacts`
- `clarify_data_request` resolution 必须保留 original prompt
- `bucket_writeback` 必须显式命中写回意图和 bucket

## 测试清单

### 后端

- 明确 Data Agent 请求 -> `create_data_agent_run`
- 明确 writeback + bucket -> `create_data_agent_run`
- 模糊“查数据” -> `clarify_data_request`
- `DataAgentRunFlow` 只 create，不 approve / execute
- `ClarifyDataRequestFlow` 选 `create_sql_review_task` 时复用 original prompt
- general tool registry 不暴露 `create_data_agent_run_tool`
- tool input schema 拒绝 `sql_text / manual_sql`

### 前端

- reducer 把 `final.artifacts` 挂到 assistant turn
- restore session 保留 `turn.artifacts`
- ChatPanel 普通 chat 识别 `data_agent_run` artifact
- 普通 chat 与显式 Data Agent 模式共用 run cache

## 验收结果

完成后应支持：

1. 普通 Chat 输入显式 Data Agent 请求
2. Orchestrator 创建 `data_agent_run`
3. assistant final turn 挂 `data_agent_run` artifact
4. ChatPanel 渲染复用 `SQLReviewCard`
5. 后续 approve / edit / revise / reject / execute 仍走 M1 API
