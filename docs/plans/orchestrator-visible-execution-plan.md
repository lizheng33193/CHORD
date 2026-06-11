# Orchestrator Visible Execution Plan

## Goal

在不破坏现有 NL Chat / workspace snapshot / tool stream 的前提下，引入 visible execution、真实 bucket availability、repair 闭环和 deterministic review。

## V2 Hardening

在 V1 的 visible execution 基线上，继续补强：

- `RequestUnderstanding` 契约：把“我理解你的需求是什么、为什么走这条路径、是否需要工具”显式挂进 `execution_plan`
- 只读追问改走 `workspace_evidence_answer`，默认使用已有画像证据调一次受限 LLM
- `general_chat` 先发轻量 `execution_plan`
- `answer_from_workspace` 在没有可复用上下文时不再静默兜底；无 UID 直接 blocked
- repair 只修真实缺失该 bucket 的 UID
- 前端 trace 卡拆出“需求理解 / 路径说明 / 为什么这样做 / 观察结果”

## Reliability Hardening

在 V2 基线上继续收敛可靠性：

- router 改成 “deterministic extraction + routing classifier”，并修正中文紧贴 UID / trace days / rerun from workspace 等场景
- 保留 `data/id_files/...` 批量入口：命中 UID 文件时先走 `parse_uid_file`，再进入 per-UID 画像规划
- availability 从“文件存在”升级为“可画像”：记录 `usable_for_profile + checked_sources`，并修复 invalid JSON 遮蔽有效 CSV 的问题
- 模块规划严格尊重用户指定模块，默认 full 画像才尝试全链路；batch 改成 per-UID 规划
- visible execution 调用 `run_profile` 强制 `strict_data_mode=True`，禁止 sample fallback 污染结果
- repair 改成懒加载 Data Agent 执行依赖，并在写回后做 availability 复检
- review step id 统一为 `review_final`，general chat trace 至少包含 `general_answer`

## V3 Stability Pass

在 Reliability Hardening 基线上继续补齐生产稳定性：

- `query_data` 改成 no-write cohort path：只返回 UID 列表和 SQL 元信息，不再落任何 profile bucket
- `tools/__init__.py` 与 `tools/query_data.py` 改成 lazy import，普通 orchestrator 导入不再拉起 Data Agent 执行层依赖
- 所有 ACK 生命周期统一调整为 `open_ack -> awaiting_user_ack -> wait/execute`
- availability 新增列名归一化、prepared JSON 最低质量门槛、`quality_score / weak_reasons / row_count`
- general LLM tool loop 中若调用 `run_profile`，也强制注入 `strict_data_mode=True`
- review 改为读取 `profile_output` 实际结果，识别 `module_error / empty_summary / missing_structured_result / degraded_model_output`

## V4 Data Compatibility & Review Accuracy Pass

- credit availability 兼容真实 MX raw CSV：UID alias 与 `valor / nombrescore / consultas_detail_json / creditos_detail_json` 等字段不再误判 missing
- `query_data` 的 UID 提取支持 `user_uuid` / `customer_id` 等 alias
- review 从“是否跑满六模块”改成“是否满足用户请求”；单模块请求成功即 `pass`
- direct `repair_profile_data()` 保留为兼容层，但 ACK 顺序调整为先 `open_ack` 再触发 preview callback
- `app.main` 启动时不再硬依赖 Data Agent 执行层；缺依赖时直接不挂 `/api/data-acquisition/*`

## V5 Clarification & Cohort Repair Gating

- router 新增 `need_clarification`，只覆盖 cohort 意图明确但缺国家/时间范围的场景
- orchestrator 新增 `awaiting_resolution` 事件与 `/api/orchestrator/sessions/{id}/resolve` 回传接口
- clarification 走可恢复卡：补充 `country + time_window` 后，在同一 execution 内继续执行
- cohort 返回 UID `> 20` 且缺失 bucket `>= 2` 类时，先弹 repair 策略卡
- repair 策略固定为：
  - `analyze_existing_only`
  - `repair_behavior_only`
  - `repair_all_missing`
  - `refine_scope`
- 前端 reducer / trace card / ChatPanel 分离 `pendingResolution`，不复用 SQL ACK 状态

## V5 Production Hardening Pass

- credit repair 正式切到 raw-first：Data Agent 只负责返回 Buró 原始字段，Credit Profile 继续负责生成 `credit_score_band / repayment_status / risk_level`
- availability / Credit Profile 继续兼容 legacy summary credit 数据，但对 credit bucket 记录 `source_shape`
- `data_acquisition_agent/api.py` 去掉顶层执行依赖导入，保证 `router` 可轻量导入；`/execute` 运行时再局部加载 executor / connection
- behavior / credit 的 pre-write validation 前移到 output writer，uid-only 结果直接拒绝，不再先写 bucket 再靠 availability 兜底
- clarification 卡升级成可编辑表单，至少支持 `country / time_window / auto_profile`
- cohort repair strategy 触发条件收敛为任一命中：
  - UID 数量 `>= 10`
  - 缺失 bucket 类别 `>= 2`
  - 预计 repair SQL 次数 `>= 2`
- `query_data()` 单次调用返回真实 `rows_estimated`，与流式 cohort 路径保持一致
- `ack_bus / resolve_bus` 暂不做持久化改造，但在注释/契约层明确未来目标 key 为 `session_id + execution_id + step_id`

## V6 Consistency & Data Quality Pass

- clarification answers 中 `auto_profile=false` 时，`query_data_then_profile` 改成 query-only 收束：返回 UID 列表与 SQL/行数元信息，不进入 availability / repair / profile
- review 的 `missing_data / weak_*` 只检查本次请求 required buckets；App-only 请求不再被 legacy credit weak bucket 降级
- credit signal 统一成 shared contract：strong raw、weak meta、summary signal 三层，availability 与 output writer 共用同一规则
- output writer 新增 `requested uid_column -> actual DataFrame column` 解析，以及 behavior / credit 行级非空校验
- Data Agent capability 改成 tri-state，并统一作用于 `/api/data-acquisition/*`、query-data、repair、clarification 后 cohort 执行

## V7 Capability Gating Follow-up

- fake Data Agent 正常流测试统一显式 patch模块内已导入的 `get_data_acquisition_capability`，不再依赖本机是否安装执行依赖
- direct profile / known UID 缺 bucket 时，planning 阶段就尊重 capability
  - capability 不可用且缺失 bucket 与本次请求相关：不再生成 `repair_*`
  - visible execution 改为独立 `data_acquisition_unavailable` 步骤
  - 仍有相关基础模块可运行时继续 partial profile；否则直接 blocked
- review 追加结构化 issue `data_acquisition_unavailable`，但长文案只保留在 step result / final message
- credit `source_shape` 改成只由 strong raw / summary 决定，weak meta-only 不再标成 `raw_buro / mixed`
- executor `rows_per_uid` 统一按字符串比较，修复 numeric UID metadata 计数错误

## V8 Turn/Run Sessionization & Cancelability

- NL Chat 从全局消息/轨迹/工具流改为 `turn -> run -> trace/tool/final` 的回合模型
- 引入后端权威 `turn_id / run_id / trace_id`，并给 SSE 事件统一补齐 `event_id / event_seq`
- `OrchestratorSession` 新增 `turns / run_events / active_turn_id / active_run_id / active_run_status`
- 新增 run 级取消接口：`POST /api/orchestrator/sessions/{session_id}/runs/{run_id}/cancel`
- ACK / resolution 改成 run scoped：`ack_id / resolution_id` 与具体 run 绑定
- 前端 reducer 新增 `turns[]` 归并；执行轨迹、工具调用、最终回答都落到所属 turn 内
- 历史 turn 默认折叠执行过程，仅保留最终回答与结果入口
- 画像结果入口卡改成跟随所属 turn 渲染，不再固定在聊天底部
- cancelled run 不覆盖当前 workspace snapshot，也不参与默认 `answer_from_workspace` 证据复用

## Implementation Slices

1. 文档与契约
   - 新增 visible execution spec / plan
   - 在 `app/services/orchestrator_agent/schemas.py` 增加 execution trace、availability、review、`RequestUnderstanding` 相关模型

2. 后端 deterministic executor
   - 新增请求归一化、`RequestUnderstanding` 构建、availability 检查和 repair helper
   - 在 `run_agent_loop()` 中接入 known-intent 快路径
   - 对只读追问新增 `workspace_evidence_answer`
   - 对 known-intent 发送 `execution_plan` / `plan_step_status` / `review_result`
   - 对 `general_chat` 也发送 lightweight `execution_plan`

3. repair 与 session 增强
  - 新增 `repair_profile_data`
  - repair 仅针对真实缺失该 bucket 的 UID 执行
  - `OrchestratorSession` 持久化 `execution_traces`
  - `GET /api/orchestrator/sessions/{id}` 返回 traces
   - V8 追加：持久化 `turns / run_events / active_run lock`

4. 前端 chat 增强
  - reducer 支持 enriched execution trace 事件
  - 执行轨迹组件渲染 request understanding / route reason / step observation
  - 历史恢复同时恢复 traces
   - V8 追加：按 turn 渲染 tool/result card，移除全局底部结果区

5. 验证
  - 后端单测：intent / request understanding / workspace follow-up / availability / repair / executor / route
  - 前端静态与 reducer 测试
  - 回归现有 orchestrator chat tests
  - V3 追加：lazy import、ACK 顺序、no-write cohort、字段归一化、prepared 质量、profile-output review
- V5 production 追加：raw-first credit repair、output writer pre-write validation、Data Agent API 轻量导入、clarification 表单、repair gating 新阈值、query_data rows_estimated 对齐
- V6 追加：clarification query-only 分支、required-bucket-only review、credit strong/weak signal、row-level output validation、tri-state capability gating
- V8 追加：turn/run event contract、run cancel API、history rebuild、turn-scoped artifacts

## Guardrails

- 只做加法扩展，不破坏现有 `tool_calls` / `messages` / snapshot 恢复协议
- 非 `mx` repair 一律显式 `blocked`
- `query_data_then_profile` 返回 UID 数量大于 200 时直接阻断
- repair 输出强制 CSV，避免 `da_agent_v2` JSON wrapper 进入画像链路
- cohort 查询结果不写 `data/*/by_uid`，避免污染行为 / 征信 / App bucket
- 不展示 raw CoT，不引入 reflection loop
- cancelled run 不提交为当前 workspace，也不自动参与后续只读追问证据复用

## 2026-05-30 Acceptance Closure Notes

- 验收版已补齐 6 类收口问题：cancel 检查点、known request cancel event 边界、legacy `/chat` 并发保护、cancelled tool 前端显示、`run_events` fallback 恢复、ACK legacy confirm 严格绑定。
- SQL ACK timeout 的默认语义现为 `ack_expired + run_cancelled`，不再生成普通 error final。
- pending 字段只表示“当前仍在等待”；历史状态全部沉淀到 `run_events`。
- cancelled partial artifacts 只保留在当前 turn / run 可见执行上下文内，不进入默认 `answer_from_workspace` evidence bundle。
