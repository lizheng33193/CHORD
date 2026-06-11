# Orchestrator Visible Execution Design

## Goal

为 NL Chat 增加一条可审计、可恢复、可降级的显式执行链路，覆盖：

- 单 UID 画像分析
- 多 UID 批量画像分析
- cohort 查询后批量画像分析
- 只读画像追问
- trace 分析

系统对用户展示的是请求理解、数据完整性检查、执行计划、工具执行状态、规则审核和最终结论；不展示原始 CoT。

## Key Decisions

1. `run_agent_loop()` 继续作为统一入口。
2. 已知意图与 `general_chat` 均优先通过对应 Flow 接管；`GeneralChatFlow` 当前覆盖 no-tool 与受支持的单工具路径，复杂 multi-family prompt 进入薄 defensive fallback，不再重新进入已退役的全量通用聊天执行回路。
3. 数据可用性检查必须直接检查 `data/app|behavior|credit/by_uid` 的真实文件，不使用 sample fallback。
4. repair 流程不复用现有 `query_data` 语义，而是新增内部 `repair_profile_data` 能力。
5. repair 产物统一写 CSV，以保证 `LocalUserRepository` 能立即消费。
6. 所有 Data Agent 相关闭环首轮仅真支持 `mx`，其它国家显式 `blocked`。
7. `execution_traces` 作为 session 的 durable 审计层，与 `messages` / `tool_calls` 并存。
8. 只读画像追问默认走 `workspace_evidence_answer`：基于已有 `summary + structured_result` 调一次受限 LLM，而不是直接拼旧 summary。
9. `answer_from_workspace` 若没有可复用上下文：
   - 请求里显式带 UID：提升为 `profile_uid` / `profile_batch`
   - 请求里没有 UID：直接 visible blocked，不静默回退到 general chat
10. `general_chat` 也要先发一个轻量 `execution_plan`，至少说明“当前进入通用 Agent 模式”。
11. repair 以 bucket 为粒度，仅对真实缺失该 bucket 的 UID 发起补数。
12. Reliability hardening 继续沿用 visible execution 主架构，不引入 LangGraph / reflection，只收敛路由、数据判定、模块规划和 strict data mode。
13. Hybrid routing：先做确定性信号提取，再只对模糊请求启用轻量 routing classifier；classifier 低置信度时必须回退到 deterministic 结果。
14. V3 stability pass 中，`query_data_then_profile` 的 cohort 查询只返回 UID 列表和 SQL 元信息，不写任何 `data/*/by_uid` bucket。
15. 所有 ACK 生命周期统一收口到 `agent_loop`：先 `open_ack`，再发送 `awaiting_user_ack`，最后才进入等待或执行。
16. deterministic review 从“执行完整性”升级为“结果质量审核”，必须能看见模块级错误、空 summary、空 structured_result 与模型降级痕迹。
17. V4 数据兼容中，credit availability 必须兼容真实 MX raw CSV 字段（如 `user_uuid / valor / nombrescore / consultas_detail_json / creditos_detail_json`），不能只认 summary CSV。
18. review 的 pass/warning 口径以“是否满足用户请求”优先；显式单模块请求成功时，不因未请求 bucket 缺失而降级。
19. `app.main` 在 Data Agent 执行依赖缺失时仍需正常启动，但不挂载 `/api/data-acquisition/*` 路由。
20. V5 新增两类可恢复交互：`need_clarification` 用于 cohort 信息不足时的澄清卡；大 cohort 且缺 2+ bucket 时先弹 repair 策略卡，再继续 repair / profile。
21. V5 production hardening 中，credit repair 正式主契约切到 raw Buró 字段；legacy summary 只保 availability / Credit Profile 兼容读取。
22. `data_acquisition_agent/api.py` 自身也必须保持轻量导入，`/execute` 的执行依赖仅在运行时局部加载。
23. behavior / credit 的最小 schema 校验前移到 output writer，post-write availability 复检仅作为第二道保险。
24. clarification 卡升级为可编辑表单；cohort repair gating 改成 “UID 数量 / 缺失 bucket 类别 / 预计 repair SQL 次数” 组合阈值。
25. clarification 中若用户关闭 `auto_profile`，同一 execution 仅执行 `query_data`，直接返回 UID 列表与 SQL/行数元信息，不再进入 availability / repair / profile。
26. Data Agent capability 改为 tri-state：`unset=auto`、`false=disabled`、`true=required`；query-data / repair / router 挂载共用一套判定。
27. credit 可画像信号拆成 strong / weak：`timestamp_ / code / apply_risk_id / folioconsulta` 只能参与 raw shape 判定，不能单独让 credit bucket 通过。
28. output writer 在字段校验之外，还必须做 uid 实际列解析和 behavior / credit 行级非空校验，避免“列存在但数据为空”落盘。

## Request Classes

- `answer_from_workspace`
- `profile_uid`
- `profile_batch`
- `query_data_then_profile`
- `need_clarification`
- `run_trace`
- `general_chat`

其中：

- `answer_from_workspace` 用于已有画像结果上的只读追问。
- `profile_uid` / `profile_batch` 先做 availability，再决定 repair 和 `run_profile`。
- `query_data_then_profile` 先生成 cohort UID，再做 availability / repair / `run_profile`。
- clarification 后若用户显式关闭 `auto_profile`，同一 execution 只继续 `query_data`，直接返回 cohort UID / SQL 元信息 / 继续画像提示，不进入 availability / repair / `run_profile`；当前已锁定 approved、non-approved、failed、empty cohort、too-large cohort 与 no-ACK completed 的可见执行语义。
- clarification 后若用户显式开启 `auto_profile`，同一 execution 会先执行 `query_data`；query 成功后第 2 次 `execution_plan` 展开为 `clarify_scope / query_data / check_data / run_profile / review_final`，若命中 single-bucket repair 会更新为 `clarify_scope / query_data / check_data / repair_<bucket> / run_profile / review_final`。
- 首轮 `query_data_then_profile + mx + capability enabled=True` 直接进入 `QueryDataThenProfileFlow`，first-turn `execution_plan` 固定不含 `clarify_scope`，初始为 `query_data / check_data / run_profile / review_final`，命中 single-bucket repair 时更新为 `query_data / check_data / repair_<bucket> / run_profile / review_final`。
- `query_data_then_profile` 当前已锁定可见执行语义：
  - query failed / empty cohort / too-large cohort 会直接 terminal，不出现 `check_data done`，也不启动 `run_profile`
  - no-repair success 会继续 `check_data done -> run_profile -> review_result(pass) -> final`
  - partial runnable 会继续 `run_profile -> review_result(warning) -> final`
  - blocked / `requested_missing > 1` 会 `run_profile blocked -> review_result(fail) -> final`
  - single-bucket repair 会进入 `repair_<bucket>`；repair non-approved 按 cancel semantics 收口，repair failed 进入 fail final，post-repair partial / blocked 由 flow 自行收口
- 当前 direct profile repair 的渐进迁移边界：
  - 单 UID：已覆盖单 bucket与双 bucket 顺序 repair
  - batch-like（`profile_batch` 或 `profile_uid + 多 UID`）：已覆盖单 bucket、mixed bucket，以及 non-approved / failed / still-unavailable / partial-runnable 分支
  - `uid_file`：已覆盖 `parse_uid_file` 的双 `execution_plan` 契约，以及 parse 后 single-bucket repair、核心异常分支与 mixed-bucket approved-success smoke
  - `requested_missing > 2`、query repair multi-bucket 主链、general-chat profile 与 general-chat query_data tool path 仍由 legacy 或保守 blocked 路径处理

每个 request 还会附带 `RequestUnderstanding`：

- `intent`
- `route_label`
- `rewritten_goal`
- `focus`
- `requires_tools`
- `route_reason`
- `answer_mode`
- `missing_slots`
- `clarification_prompt`
- `candidate_defaults`

`profile_batch` 还可以携带 `uid_file_path`，用于先执行 `parse_uid_file`，再进入同一条 visible execution 批量画像链路。

## Data Availability Rules

每个 UID 都独立检查三个 bucket：

- `app`
- `behavior`
- `credit`

判定来源：

- `app`: `data/app/by_uid/<uid>.csv`
- `behavior`: `data/behavior/by_uid/<uid>.csv` 或有效 prepared json
- `credit`: `data/credit/by_uid/<uid>.csv` 或有效 prepared json / legacy json

检查结果必须记录：

- 是否可用
- 是否可画像（`usable_for_profile`）
- 质量分数（`quality_score`）
- 弱数据原因（`weak_reasons`）
- 行数（`row_count`）
- 状态：`available | missing | invalid | unsupported`
- 来源类型
- 已检查来源列表
- 路径
- 附加说明
- credit 形态来源（例如 `raw_buro | summary | mixed | prepared`）

source precedence:

- valid prepared JSON → 直接可用
- prepared / legacy JSON schema mismatch → 继续检查 CSV
- valid CSV → 可用
- 所有来源都不满足最小画像要求 → `invalid` 或 `missing`

CSV / prepared JSON 质量门槛：

- CSV 列名统一做 lowercase + 去非字母数字归一，兼容 snake_case / camelCase / MX 原始别名字段。
- behavior CSV 至少需要 `uid + 时间字段 + 事件/页面字段`，且目标 UID 至少一条有效记录。
- credit CSV 至少需要 `UID alias + 一个信用信号字段`，且目标 UID 至少一个非空信号值。
- credit strong raw signals 为 `valor / nombrescore / razones / consultas_detail_json / creditos_detail_json`。
- credit weak meta fields 为 `timestamp_ / code / apply_risk_id / folioconsulta`，只能用于 `raw_buro` 形态识别，不能单独作为可画像依据。
- credit raw repair contract 采用 `uid / user_uuid / valor / nombrescore / razones / consultas_detail_json / creditos_detail_json / timestamp_`；`folioconsulta / code / apply_risk_id` 为可选增强字段。
- behavior prepared JSON 不能只看 schema 外壳，至少要有 `event_count / total_events / timeline_sections` 中的一项有效。
- credit prepared JSON 不能只看 schema 外壳，至少要有 `total_accounts / total_delinquent_accounts / repayment timeline / source_meta.row_count` 中的一项有效。

## Execution Model

### Shared flow

1. 归一化请求
2. 若命中 `uid_file_path`，先执行 `parse_uid_file`
3. 生成 `RequestUnderstanding`
4. 生成可见计划并发送 `execution_plan`
5. 对只读追问优先尝试 `workspace_evidence_answer`
6. 逐步更新 `plan_step_status`
7. 如有工具调用，继续发送现有 `tool_started` / `tool_progress` / `awaiting_user_ack` / `tool_completed`
8. 执行 deterministic review，发送 `review_result`
9. 产出最终回答

### Clarification / Resolution

- 当 cohort 意图明确，但缺国家或时间范围时，router 产出 `need_clarification`
- orchestrator 会发送 `execution_plan` 后进入 `awaiting_resolution`
- 前端通过 `POST /api/orchestrator/sessions/{id}/resolve` 回传 `answers` 或 `selected_option`
- clarification 会在同一 execution 内继续执行；原 clarification step 标记为 `done`
- 若 clarification answers 中 `auto_profile=false`，则只执行 `query_data` 并在同一 execution 内结束，不追加 `check_data / repair / run_profile`

### Direct profile capability gating

- direct profile / known UID 场景下，只有“缺失 bucket 与本次请求相关”时，才进入 Data Agent capability 判断
- 若 capability 不可用：
  - 不生成任何 `repair_*` step
  - 新增独立步骤 `data_acquisition_unavailable`
  - 仍有相关基础模块可运行时，step status 为 `skipped`，继续 partial profile
  - 用户请求的必要模块完全不可满足时，step status 为 `blocked`，不进入 `run_profile`
- `app` 单模块请求不会因为非请求的 `behavior / credit` 缺失而出现 unavailable 噪音
- `comprehensive / product / ops` 是否满足，继续按 `app + behavior + credit` 基础依赖判断；若仅能输出基础模块证据，review/final 只能 `warning` 或 `blocked`

### Cohort repair gating

- 当 cohort 命中以下任一条件时，不直接进入 repair：
  - UID 数量 `>= 10`
  - 缺失 bucket 类别 `>= 2`
  - 预计 repair SQL 次数 `>= 2`
- 先展示 repair 策略卡，固定四个选项：
  - `analyze_existing_only`
  - `repair_behavior_only`
  - `repair_all_missing`
  - `refine_scope`
- `refine_scope` 会阻断当前执行，并提示用户缩小条件后重试
- clarification 卡至少允许用户编辑 `country`、`time_window` 与 `auto_profile`

对于 general LLM fallback：

- 若 LLM 决定调用 `run_profile`，orchestrator 仍会强制注入 `strict_data_mode=True`
- 因此 strict mode 不再只靠 known-intent fast path 保障

### Workspace follow-up

证据来源优先级：

1. 当前 session 成功 `run_profile` / `run_trace` 的 durable output
2. `workspace_snapshot`

回答约束：

- 只使用命中的模块 `summary + structured_result`
- 不允许二次取数、补数或重跑画像
- 模型失败时退回模板式 summary fallback

### General chat

`general_chat` 现在先进入 `GeneralChatFlow`：

- no-tool 直接回答
- single-tool `run_trace / query_data / run_profile / memory_read / memory_write`
- 复杂 multi-family prompt 走保守 defensive fallback
- tool observation 与 failed/error 类路径的 session 持久化统一经 `SessionLifecycle`，`GeneralChatFlow` 不再 direct `save_session`

无论哪条 general-chat 子路径，前端都会先看到一条带 `general_answer` step 的轻量 `execution_plan`。`memory_write` 成功后事件顺序为 `execution_plan -> tool_started -> tool_completed -> plan_step_status(done) -> run_completed -> final("已记住。")`；`memory_read` success 则保留 `tool_started -> tool_completed -> continuation final` 的可见执行契约。

### Profile downgrade

如果 repair 不支持、被拒绝或失败：

- 仍有基础 bucket 可用：只跑对应基础模块
- 任一基础 bucket 缺失：不跑 `comprehensive / product / ops`
- 三个基础 bucket 都不可用：整体 `blocked`

### Strict profile execution

- visible execution fast path 调用 `run_profile` 时必须传 `strict_data_mode=True`
- strict mode 下 `LocalUserRepository` 不允许 sample fallback
- Chat 发起画像时优先复用 `workspace_snapshot.applicationTime`
- batch 场景按 UID 独立规划模块；只在模块集合一致时合并执行
- explicit single-module request 成功即视为请求满足；review 不再因为未请求模块缺失而自动标记 `partial_profile`

## Repair Flow

`repair_profile_data` 输入：

- `uids`
- `country`
- `bucket`
- `reason`

执行步骤：

1. 生成面向 Data Agent 的自然语言修复请求
2. 生成 SQL
3. `agent_loop` 先注册 ACK，再发送 `awaiting_user_ack`
4. 审批通过后执行 SQL
5. 以 CSV 写入对应 `by_uid` bucket
6. 写入前先做 behavior / credit 最小 schema 校验；明显不可画像的数据直接阻断，不落 bucket
7. 重新执行 availability 复检；仍不可画像则直接失败
8. 返回写入 UID、文件名、SQL 摘要和行数信息

session 级 Data Agent 取消语义沿用现有 `query_cancelled`。
同一 bucket 的 repair 只面向真实缺失该 bucket 的 UID，不对整批 UID 一刀切补数。

## Session And UI Contract

`OrchestratorSession.execution_traces` 每条记录保存：

- execution id
- prompt / request summary / intent
- request understanding
- availability
- steps
- review
- final status / final message

前端展示：

- 请求理解
- 数据完整性检查
- 步骤状态
- clarification / repair strategy 等待态
- review 结果

现有工具流展示继续保留，作为低层执行明细。

`query_data_then_profile` 审计边界：

- cohort 查询只在 trace / tool output 中保留 SQL 文本、估算行数、返回 UID 数量
- 不再把 cohort 查询结果落到 `data/behavior/by_uid` 或其它 profile bucket

Data Agent API 启动边界：

- `/api/data-acquisition/*` 仅在执行依赖可导入时挂载
- `DATA_ACQUISITION_ENABLED=false` 时即使依赖存在也不挂载 router，且 visible execution 中的 query-data / repair 能力统一 blocked
- `DATA_ACQUISITION_ENABLED=true` 时若依赖缺失，启动直接报错，而不是静默 skip
- 缺依赖时主应用保留 orchestrator / profile / trace 路由，不因 `pymysql` 等执行依赖而启动失败
- `data_acquisition_agent.api` 模块本身也必须可被轻量导入；只有真正调用 `/execute` 时才局部加载执行层依赖

## Non-Goals

- 不展示 raw CoT
- 不做 LangGraph 迁移
- 不引入无限 reflection loop
- 不在首轮支持非 `mx` 的 repair 闭环
