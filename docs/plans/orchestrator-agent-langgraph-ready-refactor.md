# Orchestrator Agent LangGraph-Ready Refactor

## Progress

- Phase 0: Done
- Phase 1: Done, cleanup in progress
- Phase 2: Done, cleanup in progress
- Phase 3: Done, cleanup in progress
- Phase 4A: Done
- Phase 4B profile_runner: Done
- Phase 4C-1 data_query_runner: Done
- Phase 4C-2 repair_runner: Done
- Phase 5: Done
- Phase 6A no-tool general answer: Done
- Phase 6B-1 general-chat run_trace single-tool loop: Done
- Phase 6B-2 general-chat query_data single-tool loop: Done
- Phase 6B-3/4 general-chat tool hardening + run_profile single-tool loop: Done
- Phase 6C memory / multi-tool / final general-chat cleanup: Done
- Phase 6C closeout persistence boundary + docs sync: Done
- Phase 7: Done

> Post-decomposition stabilization 作为后续独立阶段处理，不再计入本计划的 Phase 6/7。当前 baseline freeze、标准回归命令与开发者维护规则见 [README.md](/Users/zhengli/Desktop/workspace/CHORD/README.md) 与 [docs/dev/orchestrator-decomposition-guide.md](/Users/zhengli/Desktop/workspace/CHORD/docs/dev/orchestrator-decomposition-guide.md)。

## 当前落地范围

- Phase 0：文档、`FlowContext`、`LoopDependencies`、`HumanInputResult`、`MemoryFacade`、`flows/select_known_flow.py` skeleton。
- Phase 1：抽离 `finalization/` 中的 final message builder、message persistence、workspace answer helper。
- Phase 2：抽离 `runtime/` 中的 session lifecycle、event recorder、trace store、human input、cancellation。
- Phase 3：抽离 `planning/` 中的 availability summary 与纯 plan helper。
- Phase 4A：抽离 `execution/tool_runner.py` 的普通工具生命周期，并接入 `run_trace`、`parse_uid_file`、`general_chat` 普通工具调用。
- Phase 4B：抽离 `execution/profile_runner.py` 的 `run_profile` 专用执行适配，并接入 known-intent 主路径；progress callback 只入队，`progress_logger` 与 `tool_progress` 只在 async stream 消费侧执行。
- Phase 4C-1：抽离 `execution/data_query_runner.py` 的 known-intent `query_data` HITL 执行适配，并把 ACK 等待、`pending_ack` 清理、cancel-aware wait 下沉到 runner；query 后的 cohort 阻断、review、finalization 仍保留在 `agent_loop.py`。
- Phase 4C-2：抽离 `execution/repair_runner.py` 的 known-intent `repair_profile_data` HITL 执行适配；真实 repair 走 `prepare_then_execute`，legacy fake/compat repair 走阻塞式 `before_ack` gate，repair strategy / review / finalization 仍保留在 `agent_loop.py`。
- Phase 4C-2.1：补齐 `execution/repair_runner.py` 外部 `CancelledError` cleanup；对齐 `DataQueryRunner` 的 pending ACK / run status / ToolCallRecord cancelled 语义。
- Phase 5A：引入 `KnownFlow.can_handle()` gate，新增 `flows/answer_workspace.py`，只接管 `answer_from_workspace` 中已有 workspace/reusable evidence 可直接回答，以及旧语义仍属于 workspace guard answer 的 read-only 子路径。
- Phase 5B：新增 `flows/clarify_scope.py`，只接管 `need_clarification` 的交互等待壳；通过 `FlowControlSignal(kind="clarification_resume")` 把完整 answers 交回 `agent_loop.py` 的 legacy clarification-resume 后半段。
- Phase 5C：新增 `flows/run_trace.py`，只接管 known-intent `run_trace` 分支；复用 `ToolRunner` 执行 `run_trace`，保持旧 review/final 语义、lazy `tools.run_trace` 与无 UID legacy fallback。
- Phase 5D-1：新增 `flows/profile.py`，先接管 `profile_uid` 的最小成功路径；仅限单 UID、非 UID 文件、availability 可直接跑且无需 repair 的请求，复用 `ProfileRunner`、deterministic review 与 finalization helper。
- Phase 5D-2A：将 `ProfileFlow` 扩展到 multi-UID / `profile_batch` 的 no-repair 成功路径，继续复用 per-UID module planning；`uid_file`、repair、`query_data_then_profile` 仍保留 legacy。
- Phase 5D-2A.1 + 5D-3：为 `ProfileFlow` 引入私有 gate decision 与 Data Agent capability seam；将 `data_acquisition_unavailable` 的 partial / blocked guard path 迁入 flow，而 repair-required 请求继续回退 legacy。
- Phase 5D-2B：将 `uid_file / parse_uid_file` 的 no-repair 路径迁入 `ProfileFlow`；仅接 capability disabled/unavailable 的文件画像请求，parse 成功后复用既有 `success / partial_unavailable / blocked_unavailable` 逻辑，capability enabled 的 `uid_file` 继续 legacy。
- Phase 5D-2B.1：固定 `uid_file` 路径双 `execution_plan` 契约；第 1 次表示 pre-parse plan，第 2 次表示 parse 后 plan update。
- Phase 5D-4A：将 `ProfileFlow` 扩展到最小 repair approved success path；仅接 `profile_uid` 单 UID、单 missing bucket、`mx`、非 `uid_file`，并通过 `RepairRunner` 的 `prepare_then_execute` 模式接到 `run_profile`。
- Phase 5D-4B：补齐单 bucket repair 的 non-approved / failed / still-unavailable 分支；non-approved 继续沿用 cancel semantics，failed / recheck still unavailable 由 `ProfileFlow` terminal 收口。
- Phase 5D-4C：将 `ProfileFlow` 的 `repair_ready` 扩展到单 UID / 恰好 2 个 missing buckets；按 bucket 顺序调用 `RepairRunner`，全部 repair 成功后统一 recheck availability，再决定是否进入 `run_profile`；`requested_missing > 2`、多 UID、`profile_batch`、`uid_file + repair` 继续保留 legacy。
- Phase 5D-4D-1：将 `ProfileFlow` 的 `repair_ready` 扩展到 batch-like（`profile_batch` 或 `profile_uid + 多 UID`）/ 单 missing bucket approved success path；repair 输入只传该 bucket 实际缺失 UID，repair success 后统一 recheck availability 并重算 batch `execution_groups`；mixed bucket、multi-bucket batch、`uid_file + repair`、`query_data_then_profile` 继续保留 legacy。
- Phase 5D-4D-2：补齐 batch-like / 单 bucket repair 的 non-approved / failed / still-unavailable 分支；non-approved 沿用 cancel semantics，failed / still-unavailable 继续由 `ProfileFlow` terminal 收口，不 fallback legacy。
- Phase 5D-4D-3A：在 batch-like / 单 bucket repair success 后，引入 post-repair partial runnable 语义；recheck 若仍非完整 success，但存在 runnable `execution_groups`，则继续 partial profile。post-repair recheck 使用专用 decision 语义，不再返回 `repair_ready` / `legacy_repair`，仅允许 `success / partial_unavailable / blocked_unavailable`。
- Phase 5D-4D-3B：将 `ProfileFlow` 的 `repair_ready` 扩展到 batch-like / 恰好 2 个 mixed buckets 的 approved success path；按 `credit -> behavior -> app` 顺序 repair，repair 输入只传该 bucket 的实际缺失 UID。
- Phase 5D-4D-3C：补齐 mixed bucket / batch-like repair 的 failed、non-approved、still-unavailable 与 partial-runnable 分支；non-approved 继续沿用 cancel semantics，failed / still-unavailable 保持 terminal fail/block。
- Phase 5D-4E-1：将 `uid_file / parse_uid_file` 从 no-repair 路径扩到 approved-success repair bridge；`uid_file_path + capability enabled/disabled` 都先 parse，parse 后 single-UID / batch-like single-bucket repair 复用既有 `_run_repair_path(..., trace=parse_trace)`。
- Phase 5D-4E-2：补齐 `uid_file + repair` 的 non-approved / failed / still-unavailable / partial-runnable 分支，并锁定 `uid_file + mixed-bucket` approved-success smoke；parse 后 repair 继续由 `ProfileFlow` 闭环收口，不 fallback legacy。
- Phase 5E-1：新增 `QueryDataThenProfileFlow` minimal guard shell，只接 `query_data_then_profile` 的 unsupported country 与 data acquisition disabled/unavailable 两条 deterministic blocked path；`mx + capability enabled=True`、clarification 后 query-only、以及完整 query/profile/repair 主链继续保留 legacy。
- Phase 5E-2：将 clarification 后 `auto_profile=false` 的 query-only 执行链迁入 `QueryDataThenProfileFlow`；复用 clarification trace 与原 `execution_id`，第 2 次 `execution_plan` 只含 `clarify_scope / query_data / review_final`，ACK `approved` 后由 `DataQueryRunner` 执行 cohort 查询并直接产出 query-only final；`rejected / expired / cancelled` 也在 flow 内按 cancel semantics 收口。
- Phase 5E-3：补齐 clarification 后 `auto_profile=false` 的 query-only branch closure；`rejected / expired / cancelled`、preview failed、execute failed、empty cohort、too-large cohort、以及 preview 直接 `completed` 的 no-ACK path 现都由 `QueryDataThenProfileFlow` 自行收口，不 fallback legacy，也不进入 `check_data / run_profile / repair_*`。
- Phase 5E-4：将 clarification 后 `auto_profile=true` 的 query→profile no-repair success 路径迁入 `QueryDataThenProfileFlow`；query phase 与 query-only 共用 `_run_query_data_phase(...)`，query 成功且 post-query `decision.mode == "success"` 时，复用共享 `_profile_runtime.py` 执行 `check_data -> run_profile -> review/final`；`empty_cohort`、`cohort_too_large`、`repair_ready`、`blocked_unavailable` 当前也已由 flow terminal 收口，但不正式进入 repair / partial / blocked 主链。
- Phase 5E-5A：将 clarification 后 `auto_profile=true` 的 post-query no-repair decision 正式扩展为 `success / partial_unavailable / blocked_unavailable`；clarification-resume live path 现显式使用 no-repair decision helper，partial runnable 会继续复用共享 `_profile_runtime.py` 执行 `run_profile -> review(warning) -> final`，blocked 继续 terminal fail/block，不 fallback legacy，也不启动 `RepairRunner`。当前 partial warning 继续复用 `data_acquisition_unavailable + partial_repair` issue payload，作为 5E-5B 前的阶段性语义复用。
- Phase 5E-5B：将 clarification 后 `auto_profile=true` 的 query→profile live path 从 no-repair partial 优先级切到 single-bucket repair approved-success bridge；post-query single-bucket missing 现优先进入 `RepairRunner`，repair 输入只传该 bucket 的真实缺失 UID，repair success 后统一 recheck availability，并且 post-repair 只允许 `success` 继续 `run_profile`。`requested_missing > 1`、repair non-approved / failed、post-repair partial 继续留给 5E-5C。
- Phase 5E-5C：补齐 clarification 后 `auto_profile=true` 的 single-bucket query repair branch closure；`rejected / expired / cancelled` 现按 cancel semantics 收口、repair execute failed 现进入 terminal fail、post-repair partial runnable 现会继续复用 shared `_profile_runtime.py` 执行 `run_profile -> review(warning) -> final`、post-repair blocked 继续 terminal fail/block。post-repair recheck 继续禁止二次 repair，`requested_missing > 1` 仍保守 blocked。
- Phase 5E-6：首轮 `query_data_then_profile + mx + capability enabled=True` 已进入 `QueryDataThenProfileFlow`，first-turn `execution_plan` 固定不含 `clarify_scope`，并复用 query 后 continuation 覆盖 no-repair success、partial、blocked、single-bucket repair approved success、repair non-approved / failed smoke、query failed / empty / too-large / no-ACK completed。
- Phase 5F：`agent_loop.py` 中首轮 `query_data_then_profile` legacy 主业务分支已关闭为 defensive blocked fallback；正常首轮与 clarification resume 的 `query_data_then_profile` 都应由 `QueryDataThenProfileFlow` 接管，`execute_query_data_cohort` / `_complete_query_data_cohort` 仅作为 `LoopDependencies` 与 monkeypatch compatibility shim 保留。
- Phase 6A：新增 `flows/general_chat.py`，只接管明确 no-tool 的 `general_chat` 普通回答；严格 gate 要求 `request_understanding.answer_mode == "general_chat"`、`requires_tools is False`，且无 `uids / uid_file_path / query_request`。no-tool success 由 flow 产出 `general_answer done -> run_completed -> final`；LLM exception、budget exceeded、缺失/空 `final_message` 或返回 `tool_call` 时只发 `run_failed/error`，不发普通 final。
- Phase 6B-1：`GeneralChatFlow` 已接管 trace-like `general_chat -> run_trace` 单工具链路；`run_trace` tool_call 先校验 `RunTraceInput`，再 lazy 调用 `tools.get_tool_registry()` 并复用 `ToolRunner` 产出 `tool_started/tool_completed`，成功后追加 tool observation 并只允许一次 LLM continuation final。unsupported tool、invalid args、registry missing、tool error、continuation 第二个 tool_call 均由 flow failed 收口，不发普通 final。
- Phase 6B-2：`GeneralChatFlow` 已接管 query-like `general_chat -> query_data` 单工具 query-only 链路；`query_data` tool_call 先校验 `QueryDataInput`，再复用 `DataQueryRunner + LoopDependencies` 执行 SQL preview / ACK / execute，不调用 `get_tool_registry()`。成功后追加 tool observation 并只允许一次 LLM continuation final；ACK non-approved、invalid args、execute failed、continuation 第二个 tool_call 均由 flow failed/cancel 收口，不发普通 final。
- Phase 6B-3/4：`GeneralChatFlow` 已完成已迁 `run_trace / query_data` 工具路径 hardening，并接管 profile-like `general_chat -> run_profile` 单工具链路；`run_profile` 复用 `ProfileRunner` 保留 `tool_started / tool_progress / tool_completed`，不调用 `get_tool_registry()`、不嵌套 `ProfileFlow.run()`。query-like + profile-like 复合 prompt 继续 legacy seam，避免 query-only 路径误吞复杂意图。
- Phase 6C：`GeneralChatFlow` 已接管 `memory_write / memory_read`，并通过 `ctx.memory.write/read` 绑定 session-scoped memory facade。`memory_write` 成功后固定 `final("已记住。")`，`memory_read` 成功后走 observation + 单次 continuation final；empty result 仍视为 retrieval success。multi-family prompt 与 continuation 第二个 tool_call 现统一保守阻断，`agent_loop.py` 的旧 general-chat 主 LLM/tool loop 已收口为薄 defensive fallback。6C closeout 现已完成：`GeneralChatFlow` 不再 direct `save_session`，tool observation / failed persistence 统一改走 `SessionLifecycle`。

## 当前主路径说明

- `select_known_flow()` 已不再永远返回 `None`；当前包括 `answer_from_workspace -> AnswerWorkspaceFlow`、`need_clarification -> ClarifyScopeFlow`、`run_trace -> RunTraceFlow`、`profile_uid -> ProfileFlow`、`profile_batch -> ProfileFlow`、`query_data_then_profile -> QueryDataThenProfileFlow`、`general_chat -> GeneralChatFlow`。
- known intent 的已迁移主路径由对应 flow 接管；`can_handle=False` 与未迁移 intent 仍可回落 fallback，但 `query_data_then_profile` 的首轮 legacy 主业务链已关闭为 defensive blocked fallback，`general_chat` 的 `can_handle=False` 也已收口为薄 defensive fallback。
- `answer_from_workspace` 中 evidence 不足且需要 promote/rerun profile 的路径，当前先经 `can_handle()` 拒绝，再由 legacy path 接管 promote 逻辑。
- `need_clarification` 的等待壳已迁入 `flows/clarify_scope.py`；完整 answers 后的 `apply answers -> re-normalize -> refine -> continue known intent` 仍暂时保留在 `agent_loop.py`。
- known-intent `run_trace` 已迁入 `flows/run_trace.py`；general-chat 中 trace-like `run_trace` 单工具路径已迁入 `GeneralChatFlow`，多工具 continuation 与 tool failure continuation 留给后续。
- known-intent `profile_uid` 的单 UID、以及 multi-UID / `profile_batch` 的 no-repair 成功路径与 `data_acquisition_unavailable` guard path 已迁入 `flows/profile.py`；`uid_file / parse_uid_file` 路径也已迁入，并正式保留双 `execution_plan` 作为 parse 后 plan update 契约。`ProfileFlow` 的 repair path 当前已覆盖：
  - 单 UID / 单 bucket与双 bucket顺序 repair
  - batch-like / 单 bucket与 mixed-bucket repair，包括 non-approved / failed / still-unavailable / partial-runnable
  - `uid_file + repair` 的 approved-success bridge、non-approved / failed / still-unavailable / partial-runnable，以及 mixed-bucket approved-success smoke
  当前仍主要保留旧逻辑的范围为 `requested_missing > 2`、`query_data_then_profile` 的完整 query/profile 主链，以及 general-chat profile。
- known-intent `query_data_then_profile` 已迁入 `flows/query_data_then_profile.py`：
  - deterministic guard：unsupported country 与 data acquisition disabled/unavailable
  - clarification 后 `auto_profile=false` 的 query-only：approved / non-approved / failed / empty / too-large / no-ACK completed 均由 flow 收口
  - clarification 后 `auto_profile=true`：query→profile success / partial / blocked、single-bucket repair approved success、repair non-approved / failed、post-repair partial / blocked 均由 flow 收口
  - first-turn full query-data-then-profile：`mx + capability enabled=True` 直接进入 flow，plan 不含 `clarify_scope`
  - `requested_missing > 1` 的 query repair 仍保守 blocked，不启动 multi-bucket repair
- `general_chat` 的明确 no-tool 普通回答、trace-like `run_trace`、query-like `query_data`、profile-like `run_profile`、以及 `memory_write / memory_read` 单工具路径均已迁入 `GeneralChatFlow`。
- `GeneralChatFlow` 现统一限制为 single-tool ownership：最多一次 tool_call、一次 tool observation、一次 continuation final；`memory_write` 成功后固定 `final("已记住。")`，不走 continuation。
- `GeneralChatFlow` 现通过 `SessionLifecycle.append_tool_observation(...)` 与 `mark_run_failed(...)` 处理 session mutation / persistence，不再直接依赖 `session_store.save_session(...)`。
- `general_chat` 的 multi-family prompt（如 query+profile、query+memory、trace+memory）现会在 `no_tool` 之前被保守拦下；`can_handle=False` 时只进入薄 defensive fallback，不再落回旧 general-chat 主 LLM/tool loop。
- `request.uids` 已存在、`uid_file_path`、`query_request`、`query_data -> profile / repair`、`memory -> query/profile`、多工具 continuation、tool failure continuation 与多轮 ReAct 仍不由 `GeneralChatFlow` 接管。
- 正式 SSE 生命周期前缀为 `session_started -> turn_started -> run_started`。
- `ToolRunner` 采用 `start/execute` 两阶段，保证 `tool_started` 可及时 streaming 给前端。
- Phase 7C closeout 已完成：最终审计确认 `agent_loop.py` 剩余 helper 均有 live caller 或明确 seam 价值，因此以零额外删除收官；README 与 active docs 已同步为 `agent_loop.py decomposition complete` / `LangGraph-ready thin orchestrator shell achieved`。后续若迁移 LangGraph，应视为新阶段。

## 兼容策略

- `build_loop_dependencies()` 必须从 `agent_loop.py` 当前 module namespace 取对象。
- `select_known_flow.py` 不 import `agent_loop.py`；候选 flow 只按 intent 选择，业务可处理性由 `flow.can_handle()` 判断。
- `FlowControlSignal` 只用于 flow -> `agent_loop.py` 的内部控制，不得作为 SSE 事件发给前端。
- `_complete_query_data_cohort` 保留旧名兼容；`LoopDependencies.complete_query_data_cohort` 绑定到旧 helper。
- `runtime/llm_input.py` 提供与旧 `_build_llm_input` 等价的 LLM 输入拼接；`agent_loop.py` 仅保留 alias，`GeneralChatFlow` 通过 `FlowContext.system_prompt` 消费已拼好的 prompt。

## 验证

- monkeypatch compatibility tests
- selector legacy fallback tests
- runtime persistence ownership tests
- 现有 `visible_execution / chat_routes / phase3 / memory_sqlite` 回归
- `data_query_runner` 单元测试
- `repair_runner` 单元测试
- `tool_runner` 单元测试
- `profile_runner` 单元测试
- `answer_workspace` flow 接管 / fallback / 无工具隔离 / final 单次持久化测试
- `clarify_scope` flow 的 `awaiting_resolution` / timeout blocked final / internal resume signal / cancel cleanup 测试
- `run_trace` flow 的 selector / can_handle / success / failure / no-tool-registry / fallback 测试
- `ProfileFlow` minimal success path + availability-unavailable guard path 的 selector / can_handle / fallback / success / partial / blocked / final-once / no-tool-registry 测试
- `agent_loop.py` 行数收缩记录：`3488 -> 2652 -> 2630 -> 2618 -> 2501 -> 2459`
- Phase 6A no-tool `general_chat` selector / gate / success / failure / legacy tool-loop smoke 测试
- Phase 6B-1 trace-like `general_chat -> run_trace` selector / gate / direct final / success / invalid args / registry missing / unsupported tool / tool error / continuation second tool_call，以及 visible execution success/failure 测试
- Phase 6B-2 query-like `general_chat -> query_data` selector / gate / direct final / ACK approved success / invalid args / unsupported tool / ACK rejected-expired-cancelled / no-ACK completed / execute failed / continuation second tool_call，以及 visible execution success/failure 测试
- Phase 6B-3/4 profile-like `general_chat -> run_profile` selector / gate / direct final / success with `ProfileRunner` progress / invalid args / unsupported tool / tool error / continuation second tool_call / `ensure_context_fits` failure，以及 visible execution success/failure 测试
