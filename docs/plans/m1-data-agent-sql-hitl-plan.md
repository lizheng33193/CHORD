# M1 Data Agent SQL HITL Plan

## Execution Order

1. 文档与 auth/schema 基础
2. 后端 `app/data_agent/` 模型、仓储、service、API
3. 后端测试与现有 data acquisition 兼容
4. ChatPanel 显式 Data Agent 模式
5. 前端测试与回归验证

## Backend Tasks

### Task 1

- 新增 `data:bucket:writeback` 权限与 seed
- 让 auth schema 同时加载 `app.data_agent.models`
- 更新 `PLANNING.md` / `TASK.md`

### Task 2

- 新增 `app/data_agent/models.py`
- 新增 `app/data_agent/schemas.py`
- 新增 `app/data_agent/repository.py`
- 新增 `app/data_agent/safety.py`
- 新增 `app/data_agent/service.py`
- 新增 `app/data_agent/api.py`
- 在 `app/main.py` 注册 `/api/data-agent`

### Task 3

- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `POST /approve`
- `POST /edit`
- `POST /revise`
- `POST /reject`
- `POST /execute`

### Task 4

- `cohort_query` 执行 approved `query_only`，仅回结果
- `bucket_writeback` 复用 `data_acquisition_agent` 执行与写回
- 保证 edit/revise 后 approved hash 失效

## Frontend Tasks

### Task 5

- ChatPanel 新增显式 Data Agent 模式
- 新增 run form
- 新增 run list
- 新增 SQL review card

### Task 6

- 权限 gating
- run_type 分流按钮文案
- REST refetch 驱动状态更新

## Tests

后端：

- create/list/detail 权限
- approve/edit/revise/reject 状态机
- `build_table_script` review-only 边界
- `cohort_query` 与 `bucket_writeback` 执行权限差异
- hash mismatch 拒绝执行
- writeback event / audit event

前端：

- ChatPanel 出现 Data Agent 入口
- run form 字段与 run_type 切换
- SQLReviewCard 按权限显示按钮与 SQL
- execute 后显示结果摘要

