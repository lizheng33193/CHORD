# M1 Data Agent SQL HITL Design

## Goal

在 M0 登录、权限与审计基础层之上，新增一条受控的 Data Agent SQL 审核闭环：

- 生成 SQL 草稿
- 跑 SQL Safety Gate
- 人工 approve / edit / revise / reject
- 仅允许 approved `query_only` SQL 执行
- 按需返回 cohort 结果或写回 `data/*/by_uid`
- 全流程保留 actor、hash、权限与审计信息

## Scope

M1 首版只覆盖：

- `sql_kind=query_only` 的 approve-for-execution 与 execute
- `run_type=cohort_query`
- `run_type=bucket_writeback`
- ChatPanel 显式 Data Agent 模式
- Auth DB 中的 run/version/review/execution/writeback 持久化

M1 首版明确不做：

- `build_table_script` 在线执行
- Vanna / Schema RAG
- orchestrator 自动路由改造
- 新 SSE/Data Agent streaming
- 复杂 RBAC 后台或字段级权限

## Runtime Model

### SQL Kind

- `query_only`
  - 可生成
  - 可审核
  - 可批准执行
  - 可执行
- `build_table_script`
  - 可生成
  - 可展示
  - 可 edit / revise / reject
  - `safety_status=review_only`
  - 不可 approve-for-execution
  - 不可 execute

### Run Type

- `cohort_query`
  - 执行 approved `query_only`
  - 返回 `uids / rows_actual / rows_estimated / preview_rows`
  - 不写 `data/*/by_uid`
- `bucket_writeback`
  - 执行 approved `query_only`
  - 调现有 `data_acquisition_agent` write pipeline
  - 写 `data/{bucket}/by_uid`
  - 返回 artifact / written uid count

### Run Status

- `draft_generated`
- `awaiting_review`
- `revising`
- `approved`
- `rejected`
- `executing`
- `executed`
- `failed`
- `cancelled`

### Safety Status

- `passed`
- `blocked`
- `review_only`

## Persistence

新增 `app/data_agent/` 领域层，并复用 `app.auth.database.Base`。

表：

1. `data_agent_runs`
2. `data_agent_sql_versions`
3. `data_agent_review_events`
4. `data_agent_execution_events`
5. `data_agent_writeback_events`

`create_auth_schema()` 继续通过 `Base.metadata.create_all(...)` 一次性创建，不引入迁移框架。

## Safety Gate

统一入口：

`run_sql_safety_gate(sql_text, sql_kind, target_country) -> SQLSafetyResult`

行为：

- `query_only`
  - 复用 `data_acquisition_agent.executor.enforce_pre_execution_gates(...)`
  - 失败返回 `blocked`
  - 成功返回 `passed`
- `build_table_script`
  - 复用静态扫描与 hash 归一化
  - 固定返回 `review_only`
  - 附带 `build_table_script execution is not supported in M1`

约束：

- 只有 `approved_sql_version_id + approved_sql_hash` 对应版本可执行
- edit / revise 后必须新建 version、重跑 gate，并清空旧 approved 绑定
- execute 前再次校验当前 version hash 与 approved hash 一致

## Permissions

- create run：`data:query:generate` + `data:query:view_sql`
- view SQL text：`data:query:view_sql`
- approve / edit / revise / reject：`data:query:review`
- execute `cohort_query`：`data:query:execute`
- execute `bucket_writeback`：`data:query:execute` + `data:bucket:writeback`

M1 新增权限：

- `data:bucket:writeback`

角色变化：

- `data_admin` 增加 `data:bucket:writeback`
- `analyst` 不增加
- `viewer` 不增加

## API

新增：

- `POST /api/data-agent/runs`
- `GET /api/data-agent/runs`
- `GET /api/data-agent/runs/{run_id}`
- `POST /api/data-agent/runs/{run_id}/approve`
- `POST /api/data-agent/runs/{run_id}/edit`
- `POST /api/data-agent/runs/{run_id}/revise`
- `POST /api/data-agent/runs/{run_id}/reject`
- `POST /api/data-agent/runs/{run_id}/execute`

接口契约：

- create 返回 run 概览 + current version + safety result
- list 返回当前用户在当前 `project_id + country` 下的最近 runs
- get detail 根据 `data:query:view_sql` 决定是否返回 `sql_text`
- approve 仅允许 `query_only + safety_status=passed`
- execute 根据 `run_type` 分流

## Frontend

首版仅接入 `ChatPanel`，不改 orchestrator 自动路由。

新增显式 Data Agent 模式：

- 顶部模式切换或新建入口
- `DataAgentRunForm`
- `DataAgentRunsList`
- `SQLReviewCard`

UI gating：

- 无 `data:query:view_sql`：隐藏 SQL 明文
- 无 `data:query:review`：隐藏审核动作
- 无 `data:query:execute`：隐藏 cohort execute
- 缺 `data:bucket:writeback`：禁用 `Execute & Write Back`

## Audit

固定事件：

- `data.query.run_created`
- `data.query.sql_generated`
- `data.query.sql_edited`
- `data.query.sql_revised`
- `data.query.approved`
- `data.query.rejected`
- `data.query.executed`
- `data.query.failed`
- `data.bucket.writeback`

每条至少带：

- `user_id`
- `project_id`
- `country`
- `run_id`
- `run_type`
- `sql_kind`
- `sql_hash`
- `approved_sql_hash`
- `output_bucket`
- `output_format`

