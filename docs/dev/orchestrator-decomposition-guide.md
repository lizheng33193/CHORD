# Orchestrator Decomposition Guide

当前 orchestrator 已完成 decomposition，`app/services/orchestrator_agent/agent_loop.py` 现为 **LangGraph-ready thin orchestrator shell**。这不代表项目已经迁入 LangGraph；当前系统仍是单 orchestrator、确定性 flow、受控本地 agentic decision points 的架构。

## 1. 当前职责边界

### `agent_loop.py`

只保留这些职责：

- `run_agent_loop` 顶层入口
- session / turn / run lifecycle setup
- `FlowContext` 与 `LoopDependencies` 构造
- flow dispatch
- 顶层 cancellation / exception boundary
- thin defensive fallback
- documented compatibility / monkeypatch seams

不再承载主业务链：

- `ProfileFlow` 主业务逻辑
- `QueryDataThenProfileFlow` 主业务逻辑
- `GeneralChatFlow` 主 tool loop
- `memory_write / memory_read` inline 逻辑

### `flows/`

`flows/` 负责业务流程编排与 request-shape ownership。当前主 flow 包括：

- `AnswerWorkspaceFlow`
- `ClarifyScopeFlow`
- `RunTraceFlow`
- `ProfileFlow`
- `QueryDataThenProfileFlow`
- `GeneralChatFlow`

### `execution/`

`execution/` 负责工具或阶段执行，不负责整体 flow finalization。当前典型 runner：

- `ToolRunner`
- `ProfileRunner`
- `DataQueryRunner`
- `RepairRunner`

### `runtime/`

`runtime/` 负责 session lifecycle、trace store、event recorder、human input、cancellation 等运行时支撑。flow 不应直接回退到手写 persistence。

## 2. LoopDependencies 规则

`LoopDependencies` 是当前保留的兼容 seam / 依赖注入入口。

使用规则：

- 仍被测试 monkeypatch 的 seam 可以继续通过 `LoopDependencies` 暴露
- 新业务逻辑不要为了方便继续把主执行链塞回 `agent_loop.py`
- 只有真正需要 monkeypatch / dependency injection 的能力，才保留在 dependencies 中

## 3. `can_handle()` 规则

所有 flow 的 `can_handle()` 必须满足：

- 纯读
- 无副作用
- 不写 session
- 不发 SSE event
- 不调用工具执行
- 不做持久化

如果需要额外校验，应尽量在 `run()` 内完成，而不是让 `can_handle()` 变成副作用入口。

## 4. Import Boundary

以下目录不得反向 import `agent_loop.py`：

- `app/services/orchestrator_agent/flows`
- `app/services/orchestrator_agent/execution`
- `app/services/orchestrator_agent/runtime`
- `app/services/orchestrator_agent/finalization`
- `app/services/orchestrator_agent/planning`

质量门由 `tests/orchestrator_agent/test_import_boundaries.py` 固化。

## 5. Runtime Observability

flow 可以写 internal trace metadata，但必须遵守下面的边界：

- 唯一推荐落点：`ExecutionTraceRecord.internal_metadata`
- internal metadata 只用于 runtime trace、developer diagnostics、test introspection
- 不得写入 `PlanStep`
- 不得写入 `RunEvent.payload`
- 不得泄漏到 `execution_plan` / `plan_step_status` / `review_result` / `final` 等 public SSE payload
- 不得泄漏到 frontend reducer 输入
- 不得通过普通 public session/chat response 直接返回

推荐最小 key：

- `flow_name`
- `flow_mode`
- `decision_mode`
- `fallback_reason`
- `terminal_reason`

推荐轻量上下文 key：

- `tool_name`
- `memory_operation`
- `ack_result`
- `auto_profile`
- `requested_missing`
- `repair_buckets`
- `execution_group_count`
- `uid_count`
- `parsed_uid_count`
- `cohort_size`
- `country`
- `trace_days`
- `clarification_resume`

语义约束：

- `terminal_reason` 是 internal terminal outcome reason，不等于 public failure status
- 它不能替代 `run.status`、`review_result.status` 或 `final_status`
- 新 flow 默认至少写 `flow_name`
- 有稳定 mode 分支的 flow 默认同时写 `flow_mode`

特殊 attribution 规则：

- `GeneralChatFlow` 的 defensive fallback 虽然从 `agent_loop.py` shell 发出，但 observability attribution 仍归 `GeneralChatFlow`

## 6. 新增 Flow Checklist

新增 flow 时必须满足：

- 不 import `agent_loop.py`
- `can_handle()` 纯读无副作用
- `run()` 一旦开始执行，不再回退 legacy 主链
- 不新增 public SSE event，除非有明确设计文档
- session mutation / persistence 通过 runtime helper 完成
- visible execution 有测试
- baseline / regression 有测试
- import boundary 不破坏

## 7. 新增 Runner Checklist

新增 runner 时必须满足：

- 明确 `ToolCallRecord` 生命周期
- `started / completed / error / cancelled` 语义完整
- 不直接拼 final
- 不直接持久化 assistant final
- 只负责执行，不负责整个 flow 的最终结论

## 8. Docs Truth Checklist

改动 active behavior 后，至少检查这些文件是否需要同步：

- `README.md`
- `PLANNING.md`
- `TASK.md`
- `docs/specs/orchestrator-agent-decomposition.md`
- `docs/specs/orchestrator-visible-execution-design.md`
- `docs/plans/orchestrator-agent-langgraph-ready-refactor.md`

历史文档可以保留旧描述，但必须明确是 `historical / superseded`，不能继续冒充当前事实。

## 9. 推荐回归命令

推荐回归命令以 `README.md` 为唯一主入口，分为三档：

- `Minimal PR Regression`
- `Orchestrator Full Regression`
- `Final Release Regression`

如果某些环境安装了 `ddtrace` 且 pytest 在 100% 后不退出，对同一命令追加 `-p no:ddtrace` 即可；不要把它写进 repo 级默认配置。
