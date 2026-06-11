# Orchestrator Agent Decomposition

- 状态：completed / current-reference
- 目标：把 `app/services/orchestrator_agent/agent_loop.py` 拆成兼容性优先、可渐进迁移、LangGraph-ready 的边界结构。

## 当前进度

- Phase 0：Done
- Phase 1：Done, cleanup in progress
- Phase 2：Done, cleanup in progress
- Phase 3：Done, cleanup in progress
- Phase 4A：Done
- Phase 4B：Done
- Phase 4C-1：Done
- Phase 4C-2：Done
- Phase 5：Done
- Phase 6：Done
- Phase 7：Done

## 当前契约

- `session_started -> turn_started -> run_started` 是正式 SSE 生命周期前缀。
- workspace reuse / reusable-results / read-only follow-up 也属于统一 run 生命周期。
- `select_known_flow()` 已开始返回真实候选 flow；当前包括 `answer_from_workspace -> AnswerWorkspaceFlow`、`need_clarification -> ClarifyScopeFlow`、`run_trace -> RunTraceFlow`、`profile_uid -> ProfileFlow`、`profile_batch -> ProfileFlow`、`query_data_then_profile -> QueryDataThenProfileFlow`、`general_chat -> GeneralChatFlow`。
- known intent 的已迁移主路径由对应 flow 接管；未迁移 intent 与 `can_handle=False` 场景仍可回退 fallback，但 `query_data_then_profile` 的首轮 legacy 主业务链已关闭为 defensive blocked fallback，`general_chat` 的 `can_handle=False` 也已收口为薄 defensive fallback。
- clarification 恢复执行已引入内部 `FlowControlSignal` 协议：前端只接收 SSE dict，resume 信号只在 `agent_loop.py` 内部消费。

## 核心边界

- `FlowContext`：只承载运行上下文与服务入口，不承载业务状态集合；当前已包含 `lifecycle` 注入点。
- `LoopDependencies`：承接 `agent_loop.*` monkeypatch 兼容路径，真实执行路径通过 `ctx.deps.*` 访问；当前已包含 availability、capability、repair prepare/execute 与 original repair helper seam。
- `runtime/`：session lifecycle、event recorder、trace store、human input、cancellation。
- `finalization/`：final text builder、workspace answer orchestration、message persistence。
- `planning/`：typed plan 与纯函数格式化，不执行 availability check。
- `flows/`：业务流程编排；当前已落地 `AnswerWorkspaceFlow`、`ClarifyScopeFlow`、`RunTraceFlow`、`ProfileFlow`、`QueryDataThenProfileFlow`，并通过 `can_handle()` 显式判断是否可处理；其中：
  - `QueryDataThenProfileFlow` 当前已接管：
    - deterministic guard shell：unsupported country 与 data acquisition disabled/unavailable
    - clarification resume 后 `auto_profile=false` 的 query-only 路径：复用 clarification trace，在同一 `execution_id` 上发第 2 次 `execution_plan`，并用 `DataQueryRunner` 执行 cohort 查询与 query-only final；当前已覆盖 approved、non-approved、failed、empty cohort、too-large cohort 与 no-ACK completed 分支
    - clarification resume 后 `auto_profile=true` 的 query→profile 路径：query phase 继续复用共享 `DataQueryRunner` 闭环；live path 当前优先级为 `success -> run_profile`、single-bucket `repair_ready -> RepairRunner bridge`、其他缺失场景先 `blocked_unavailable` terminal 收口；`empty_cohort` 与 `cohort_too_large` 也继续由 flow terminal 收口
    - no-repair partial 语义仍保留在 post-query no-repair helper / seam 中，当前 partial warning 继续复用 shared runtime 的 `data_acquisition_unavailable + partial_repair` issue 语义，后续如需更精确表达再参数化
    - post-repair recheck 当前固定使用 no-repair decision helper，禁止二次 repair；`success` 会继续进入 shared `_profile_runtime.py`，`partial_unavailable` 也会继续 partial profile，而 `blocked_unavailable` terminal 收口
    - 首轮 `mx + capability enabled=True` 的 full query path：first-turn `execution_plan` 不含 `clarify_scope`，并复用同一套 query 后 continuation 覆盖 success / partial / blocked / single-bucket repair / query terminal 分支
  - `ProfileFlow` 已覆盖 no-repair success path、`data_acquisition_unavailable` guard path、`uid_file / parse_uid_file` 路径，以及 repair path：
  - 单 UID / 单 bucket与双 bucket 顺序 repair
  - batch-like（`profile_batch` 或 `profile_uid + 多 UID`）/ 单 bucket与 mixed-bucket repair
  - `uid_file -> parse_uid_file -> resolved uids -> repair_ready` bridge，以及 non-approved / failed / still-unavailable / partial-runnable 收口
  - `uid_file + mixed-bucket` approved-success smoke
  当前仍未迁移的主范围为 `requested_missing > 2`、query repair 的 multi-bucket 主链，以及 general-chat 的 multi-tool / ReAct / tool-failure-continuation 路径；未迁移或不可处理的 intent 继续由 `agent_loop.py` 的窄 defensive fallback 兜底。
- `FlowControlSignal`：known flow 的内部控制输出，用于类似 clarification resume 这类“继续 legacy 后半段”的非 SSE 调度信号。
- `execution/tool_runner.py`：Phase 4A 仅承接普通工具生命周期（`tool_call record -> tool_started -> execute -> tool_completed`），不处理 trace step、ACK、review、finalization、memory policy。
- `execution/profile_runner.py`：Phase 4B 承接 `run_profile` 的专用执行适配（`tool_started -> tool_progress -> tool_completed`），要求 pure executor、async stream 消费侧 logging/SSE、cancel 透传；不处理 trace step、review、finalization、query/repair 策略。
- `execution/data_query_runner.py`：Phase 4C-1 承接 known-intent `query_data` 的 HITL 执行适配（`tool_started -> awaiting_user_ack -> tool_completed` 或 cancel/block）；preview 结果通过显式协议进入 runner，ACK 等待必须先 streaming 再 wait，并通过 runtime helper 清理 `pending_ack` 与 `run.status`。
- `execution/repair_runner.py`：Phase 4C-2 承接 known-intent `repair_profile_data` 的 HITL 执行适配；真实 repair 走 `prepare -> awaiting_user_ack -> execute`，legacy fake/compat repair 走阻塞式 `before_ack` gate，由 runner 统一管理 ACK 状态、SSE 与 ToolCallRecord 收尾，并显式处理外部 `CancelledError` cleanup。
- `GeneralChatFlow` 的 tool observation 与 failed/error 类路径持久化现已通过 `SessionLifecycle.append_tool_observation(...)` / `mark_run_failed(...)` 收口，不再直接 `save_session`。
- 当前 `agent_loop.py` 最终职责已经收敛为：
  - `run_agent_loop` 顶层入口与 lifecycle setup
  - `FlowContext` / `LoopDependencies` 构造
  - flow dispatch 与顶层 cancellation / exception boundary
  - thin defensive fallback
  - documented compatibility / monkeypatch seams

## 强约束

- 新模块禁止 import `agent_loop.py`。
- flow 不直接 `save_session`。
- runner 不决定完整业务结局。
- deterministic review 仍然是主审核层。
- 第一轮不迁移 LangGraph runtime，不全面拆 `schemas.py`。

## 稳定化入口

- Post-decomposition 的默认质量门以 [README.md](/Users/zhengli/Desktop/workspace/CHORD/README.md) 中的三档回归为准：
  - `Minimal PR Regression`
  - `Orchestrator Full Regression`
  - `Final Release Regression`
- 日常维护规则、Flow / Runner checklist 与 import boundary 说明见 [docs/dev/orchestrator-decomposition-guide.md](/Users/zhengli/Desktop/workspace/CHORD/docs/dev/orchestrator-decomposition-guide.md)。
