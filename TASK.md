# TASK.md

## 功能清单
- [x] 项目基础设施（AGENTS.md + PLANNING.md + TASK.md；CLAUDE.md 仅历史兼容）— 已完成
- [x] Codex-first 开发指导迁移 — 已完成（AGENTS.md 主入口 + CLAUDE.md 兼容转发 + PLANNING.md Harness 门禁）
- [x] Harness Engineering 项目宪法 — 已完成（AGENTS.md 中文短入口 + docs/specs/harness-engineering-governance.md 详细治理指南）
- [x] BaseSkill + SkillRegistry 重构 — 已完成，68 测试全过
- [x] 默认 LLM 模式切换（mock → gemini）— 已完成
- [x] 依赖版本锁定 — 已完成
- [x] 安全清理（.gitignore + 移除追踪数据 + .env.example 清理）— 已完成
- [x] P0: 清理 Legacy `app/agents/` 目录 — 已完成（2026-04-28，68 测试全过）
- [x] P0: LLM 端到端打通验证 — 已完成（2026-04-28，vertex 模式打通，gemini-3.1-pro-preview，amberstar-gemini/global）
- [x] P1: 拆分 Comprehensive 为六步管线 → 完成（2026-04-28，docs/plans/comprehensive-refactor-plan.md）
- [x] P1: 补全 Behavior/Credit Pydantic Schema → ✅ 完成（2026-04-30，docs/plans/behavior-credit-schema-plan.md，b5f165e，348 passed）
- [x] P2: 新增产品策略 Agent（stage=2）— 完成（2026-04-30，docs/plans/operation-skills-plan.md，六步管线 + S1-S6 规则 + LLM 增强 + e2e 测试）
- [x] P2: 新增运营策略 Agent（stage=2）— 完成（2026-04-30，docs/plans/operation-skills-plan.md，六步管线 + S1-S6 规则 + churn 升档 + LLM 增强 + e2e 测试）
- [x] P3: LangGraph 迁移 → 评估完成，暂不迁移（2026-04-30，docs/specs/langgraph-migration-design.md）
- [x] P4: UI 前端分离 → ✅ 完成（2026-04-30，docs/plans/ui-separation-plan.md） → docs/plans/ui-separation-plan.md（Step 2 Design 已确认 docs/specs/ui-separation-design.md，3e94dbe；Step 3 架构 Stub 已落地）
- [x] data_acquisition_agent V1 — Design Doc 已确认（[docs/specs/data_acquisition_agent.md](docs/specs/data_acquisition_agent.md)，2026-04-29）
- [X] data_acquisition_agent V1 — demo0 凭据脱敏 mini-task — 已完成（2026-04-29，764a647）
- [X] data_acquisition_agent V1 — Step 3 架构设计 — 已完成（2026-04-29，caed309）
- [x] data_acquisition_agent V1 — Step 4 实现 Plan — 已确认并 commit（[docs/plans/data-acquisition-v1-plan.md](docs/plans/data-acquisition-v1-plan.md)，4c854c6）
- [x] data_acquisition_agent V1 — Step 5 TDD 实现完成（2026-04-29，e686404..c8793e3，72 tests）
- [x] data_acquisition_agent V2 — Design Doc 已确认（docs/specs/data_acquisition_agent_v2.md，2026-04-29）
- [x] data_acquisition_agent V2 — Step 3 架构 Stub 已落地（2026-04-29）
- [x] data_acquisition_agent V2 — Step 4 实现 Plan 已确认（[docs/plans/data-acquisition-v2-plan.md](docs/plans/data-acquisition-v2-plan.md)，2026-04-29）
- [x] data_acquisition_agent V2 — Step 5 TDD 实现完成（2026-04-30，916a2dd..5ef1699，71 tests，全量 163 passed）
- [x] data_acquisition_agent V2 — Step 7 交付完成（2026-04-30）
- [x] 前端：product_advice + ops_advice 展示 tab — 完成（2026-04-30，dd7c65f）
- [x] 前端：standardized_labels 标签概览卡 — 完成（2026-04-30，dd7c65f）
- [x] 前端：批量分析 S1-S6 客群分布统计 — 完成（2026-04-30，dd7c65f）
- [x] data_acquisition_agent V1+V2 白盒审计 — 完成（2026-04-30，ca375fa，docs/reviews/data-acquisition-v1v2-audit.md）
- [x] 行为画像：Quincena 发薪日分析 — 完成（2026-04-30，999fcf7..7b71d13，10 tests）
- [x] 重构：APP 分类词典抽到 country_packs/mx/ — 完成（2026-04-30，2ccd4d4..2b6cc36，3 tests）
- [x] E1 单用户埋点深度解析 → docs/plans/trace-analyzer-plan.md（2026-05-01）

## 当前进行中的功能
- [ ] M2A-Verify：真实业务样例验证 + Seed 质量补齐 — 进行中（2026-06-23）
  - plan / runbook / sample set / gap list：
    - `docs/plans/m2a-verify-knowledge-quality-plan.md`
    - `docs/reviews/m2a-verify-runbook-template.md`
    - `docs/reviews/m2a-verify-sample-set-round1.md`
    - `docs/reviews/m2a-verify-seed-gap-round1.md`
    - `docs/reviews/m2a-verify-round1-results.md`
    - `docs/reviews/m2a-verify-seed-patch1-results.md`
  - 首轮固定样例：
    - `mx` 高风险 cohort query
    - `mx` behavior bucket_writeback
    - `ph` 首贷从未逾期 cohort query
    - glossary 组合命中请求
    - error case 修复型请求
  - 首轮目标：
    - 记录 retrieval / assembled context / generated SQL / Safety Gate / review 结论
    - 识别 seed 缺口并形成下一轮补齐 backlog
  - Round 1 当前状态：
    - 已完成 5 条样例的首轮真实执行记录
    - 本轮未改 seed，只记录动态结果
  - Seed Patch 1 当前状态：
    - 已补第一批 catalog / glossary / example / error case seed
    - 已完成 patch 后 5 条样例的再次验证
    - 下一步应把剩余问题拆到 runtime quality follow-up，而不是继续混入 seed patch
  - Seed Patch 1.1 当前状态：
    - 已收紧 `example:behavior-writeback` active pattern
    - active example 现明确要求先限定 target cohort / uid，再 join behavior source table
    - 已把“直接扫 behavior 表 + LIMIT”从 active knowledge pattern 中移除
- [x] M2A：Data Agent Knowledge RAG — 首版实现完成并完成本地定向验证（2026-06-23）
  - design / plan：
    - `docs/specs/m2a-data-agent-knowledge-rag-design.md`
    - `docs/plans/m2a-data-agent-knowledge-rag-plan.md`
  - 已完成：
    - `app/data_knowledge/` 领域模块
    - DB-backed catalog / glossary / SQL example / error case store
    - seed importer 与最小管理 API
    - deterministic retriever 与 prompt context assembler
    - `DataAgentService.create_run()` / `revise_run()` 接入
    - approved + executed success -> draft SQL example
    - execute failure -> open error case
  - 本地验证：
    - `python -m compileall -q app data_acquisition_agent tests`
    - M2A 定向测试 `47 passed`
  - 下一步：
    - 进入 `M2A-Verify`
- [x] M1.5：Orchestrator ↔ Data Agent Tool Bridge → 已完成首版 bridge（2026-06-12）
  - design / plan：
    - `docs/specs/m1-5-orchestrator-data-agent-bridge-design.md`
    - `docs/plans/m1-5-orchestrator-data-agent-bridge-plan.md`
  - 后端已完成：
    - `create_data_agent_run` / `clarify_data_request` intent
    - deterministic keyword routing
    - `create_data_agent_run_tool`
    - `DataAgentRunFlow`
    - `ClarifyDataRequestFlow`
    - `orchestrator.data_agent_run.created` 审计
  - 前端已完成：
    - `final.artifacts` 持久化到 assistant turn
    - 普通 chat 渲染 `data_agent_run -> SQLReviewCard`
    - `fetchDataAgentRun(runId)` + shared run cache
  - 保持不变：
    - M1 SQL HITL 状态机
    - 显式 Data Agent mode
    - M1 approve / edit / revise / reject / execute API
    - GeneralChatFlow broad tool autonomy
- [ ] M1：Data Agent SQL HITL — 进行中（2026-06-12）
  - design / plan：
    - `docs/specs/m1-data-agent-sql-hitl-design.md`
    - `docs/plans/m1-data-agent-sql-hitl-plan.md`
  - 后端目标：
    - 新增 `app/data_agent/` 领域层与 auth DB 持久化表
    - 新增 SQL version / review / approve hash / execute / writeback 状态机
    - 新增 `/api/data-agent/runs*`
    - 新增 `data:bucket:writeback` 权限
  - 前端目标：
    - ChatPanel 显式 Data Agent 模式
    - run form / run list / SQLReviewCard
    - 基于 `view_sql / review / execute / bucket:writeback` 的 UI gating
  - 当前边界：
    - `query_only` 可执行
    - `build_table_script` review-only
    - `cohort_query` 不写回
    - `bucket_writeback` 写 `data/*/by_uid`
- [x] M0：Identity & Permission Foundation → 已完成第一阶段闭环（2026-06-11）
  - design / plan：
    - `docs/specs/m0-identity-permission-foundation-design.md`
    - `docs/plans/m0-identity-permission-foundation-plan.md`
  - 后端：
    - `app/auth/`（SQLAlchemy auth DB、seed、JWT、password、`/api/auth/*`）
    - `app/core/user_context.py` / `request_context.py` / `audit.py`
    - `AUTH_ENABLED` + demo user fallback
    - 关键 API 权限保护：`/api/analyze*`、`/api/trace/*`、`/api/orchestrator/*`、`/api/data-acquisition/*`
  - Agent Harness 接入：
    - Orchestrator session 持久化 `user_context_snapshot` / `request_context`
    - execution trace `internal_metadata` 增加 actor / session / request 信息
    - Data Acquisition execute 强制记录当前审批人
  - 前端：
    - `AuthGate`、登录/注册页、`authStore`、`httpClient`
    - Bearer token、401 自动退出、国家/项目 header 自动透传
    - Dashboard / Chat / Memory Inspector 已绑定真实登录身份与权限可见性
  - 2026-06-11 hardening closure：
    - `401/403` 语义拆分完成，非法 scope 不再误触发前端登出
    - `mx/mexico`、`th/thailand` country alias 已统一到同一套授权判断
    - `query_data` chat preview 前已收紧到 `data:query:view_sql + data:query:execute`
    - Data Acquisition generate / execute 已补国家 scope 校验
    - Orchestrator session 已改为 `user + project + country` 三元组可见性
    - Memory `project/global` scope 已改为真实共享语义，并补共享去重
    - runtime audit 已覆盖 `profile.run`、`trace.view`、`memory.*`、`data.query.generate/preview/execute`
    - 前端 scope selector 已改为 `/api/auth/my-projects` + `/api/ui-config.supported_countries`
- [x] Data Agent 本地 MySQL 沙盒（目标 1）→ 已落地 `DA_LOCAL_DEV` 路由修复、4 表 local_dev 知识库、Docker MySQL 资产、chunked CSV 导入脚本与 by_uid 闭环验证入口（2026-06-05）
- [x] Data Agent 本地 MySQL “开机即测”联调脚本 → 已新增 `.env.local-mysql.example`、`scripts/local_mysql/local_stack.py`、`dev_up/dev_smoke/dev_down.sh` 与 quickstart 文档，支持一键 `up / smoke / down`（2026-06-05）
- [x] ModelClient 重构 → [docs/plans/01-model-client-refactor-plan.md](docs/plans/01-model-client-refactor-plan.md)（[complete] a949830 2026-05-02）
- [x] explainer/trace 切 Claude → [docs/plans/02-explainer-trace-claude-migration-plan.md](docs/plans/02-explainer-trace-claude-migration-plan.md)（[complete] 874c305 2026-05-02）
- [x] Orchestrator Agent → [docs/plans/03-orchestrator-agent-plan.md](docs/plans/03-orchestrator-agent-plan.md)（[complete] 8fb3377 2026-05-03）
- [x] 前端对话 Tab → [docs/plans/04-nl-chat-tab-frontend-plan.md](docs/plans/04-nl-chat-tab-frontend-plan.md)（[complete] 92771ee 2026-05-04 + hotfix 路由 2026-05-04，349 tests + HTTP smoke 全绿）
- [x] Orchestrator Memory V1 → SQLite + FTS5 长期记忆、Memory 管理 API / Inspector、离线评估集与 runner（2026-05-25，baseline checkpoint `3c10d85`，contract: docs/specs/memory-behavior-contract.md）
- [x] Memory recovery audit → 确认 Memory 管理/评估功能仍在，恢复本地 `.env/key.json/data` 运行文件，并记录不可恢复的本地 SQLite runtime state（2026-05-25，docs/reviews/memory-recovery-audit-2026-05-25.md）
- [x] Orchestrator Chat progress + memory/session UI contract → 模块级 `tool_progress`、短期会话历史列表、长期记忆心智澄清（2026-05-26；docs/specs/orchestrator-chat-progress-memory-ui-contract.md；plan: docs/plans/orchestrator-chat-progress-memory-ui-plan.md）
- [x] NL Chat workspace snapshot + history restore split → 历史会话仅切右侧 transcript、显式恢复左侧 workspace、sessionStorage 同 tab 恢复、read-only 追问优先复用已有画像结果（2026-05-27；docs/plans/orchestrator-chat-workspace-snapshot-plan.md）
- [x] Visible execution + repair loop → execution traces、deterministic known-intent executor、真实 bucket availability、repair 闭环、deterministic review、chat trace card（2026-05-28；docs/specs/orchestrator-visible-execution-design.md + docs/plans/orchestrator-visible-execution-plan.md）
- [x] Visible execution V2 hardening → `RequestUnderstanding`、`workspace_evidence_answer`、general-chat lightweight plan、精准 repair 范围、trace 卡解释块（2026-05-28）
- [x] Visible execution reliability hardening → hybrid routing、usable_for_profile availability、strict_data_mode、per-UID module planning、lazy repair imports、review_final（2026-05-29）
- [x] Visible execution V3 stability pass → lazy `query_data` imports、no-write cohort、ACK 时序修复、字段归一化、prepared JSON 质量门槛、profile-output review、general strict guard（2026-05-29）
- [x] Visible execution V4 data compatibility & review accuracy → credit raw CSV aliases、`query_data` user_uuid、single-module review pass、repair direct ACK 对齐、`app.main` Data Agent 路由隔离（2026-05-29）
- [x] Visible execution V5 clarification & cohort repair gating → `need_clarification`、`awaiting_resolution`、`/resolve`、cohort repair 策略卡、前端 `pendingResolution`（2026-05-29）
- [x] Visible execution V5 production hardening → raw-first credit repair、Data Agent API lazy import、behavior/credit pre-write validation、clarification form、repair gating 阈值优化（2026-05-29）
- [x] Visible execution V6 consistency & data quality pass → `auto_profile=false` query-only、required-bucket-only review、credit strong/weak signal、output writer 行级校验、Data Agent tri-state gating（2026-05-29）
- [x] NL Chat 回合化执行流 + run 级取消 → `turn/run/trace` 权威 ID、`turns[]` 前端归并、run cancel API、turn-scoped 结果卡、历史回合折叠（2026-05-29）
- [x] NL Chat 回合化执行流稳定性收尾（验收版）→ cancel 检查点、legacy `/chat` 最小保护、strict ACK 绑定、`run_events` fallback、cancelled tool UI、workspace evidence 边界（2026-05-30）
- [x] NL Chat UX 回归修复 → optimistic turn 即时显示、`profile_module_completed` 即时推送左侧模块、停止中反馈、渐进式 trace 展示、完成后自动收缩（2026-05-30）
- [x] Orchestrator Agent Phase 5A kickoff → RepairRunner 外部 cancel hardening、`KnownFlow.can_handle()`、`AnswerWorkspaceFlow`、known-intent flow/legacy fallback dispatch（2026-06-01）
- [x] Orchestrator Agent Phase 5B kickoff → `ClarifyScopeFlow`、`FlowControlSignal`、clarification shell/resume legacy handoff、pending_resolution cancel cleanup（2026-06-01）
- [x] Orchestrator Agent Phase 5C kickoff → `RunTraceFlow`、known-intent `run_trace` flow/ToolRunner 接管、lazy tools.run_trace、无 UID legacy fallback（2026-06-01）
- [x] Orchestrator Agent Phase 5D-1 kickoff → `RunTraceFlow` cancel parity、`ProfileFlow` minimal success path、`profile_uid` 单 UID/availability OK/no-repair flow 接管（2026-06-01）
- [x] Orchestrator Agent Phase 5D-2A kickoff → `ProfileFlow` multi-UID / `profile_batch` no-repair success path、mixed batch per-UID module planning 接管、`uid_file` / repair / `query_data_then_profile` 继续 legacy（2026-06-01）
- [x] Orchestrator Agent Phase 5D-2B kickoff → `ProfileFlow` 现已接管 `uid_file / parse_uid_file` 的 no-repair 路径：仅限 capability disabled/unavailable、parse 成功后可闭环到 success / partial_unavailable / blocked_unavailable；capability enabled 的 `uid_file`、repair、`query_data_then_profile` 继续 legacy（2026-06-01）
- [x] Orchestrator Agent Phase 5D-2B.1 kickoff → `uid_file` 路径双 `execution_plan` 契约正式固定：第 1 次为 pre-parse plan，第 2 次为 parse 后 plan update；parse 成功、空 UID、parse 失败均补充基线测试与文档（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4A kickoff → `ProfileFlow` 新增最小 `repair_ready` gate，并接入单 UID / 单 missing bucket / `mx` / approved success 的 `RepairRunner` repair path；`profile_batch`、多 UID、多 bucket、`uid_file + repair`、`query_data_then_profile` 继续 legacy（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4A.1 Test Contract Cleanup → `visible_execution` 中的 repair-failure baseline 显式 patch capability enabled，避免误落入 `partial_unavailable`（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4B branch closure → 补齐 repair non-approved / failed / post-repair still unavailable 的 baseline 与 visible_execution 契约，保持 non-approved 沿用 cancel 语义（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4C kickoff → `ProfileFlow` 的 `repair_ready` 现已接管单 UID / 恰好 2 个 missing buckets 的顺序 repair approved success path，并补齐“第二个 repair failed 不进入 `run_profile`”的最小 safety case；`requested_missing > 2`、多 UID、`profile_batch`、`uid_file + repair` 继续 legacy（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4D-1 kickoff → `ProfileFlow` 的 `repair_ready` 现已接管 batch-like（`profile_batch` 或 `profile_uid + 多 UID`）/ 单 missing bucket / approved success path；repair 输入只传该 bucket 的实际缺失 UID，repair 后统一 recheck availability 并重算 batch `execution_groups`；mixed bucket、multi-bucket batch、`uid_file + repair`、`query_data_then_profile` 继续 legacy（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4D-2 branch closure → batch-like / 单 bucket repair 的 non-approved / failed / still-unavailable 矩阵已补齐；non-approved 继续沿用 cancel semantics，failed / still-unavailable 继续由 `ProfileFlow` terminal 收口，并保持不 fallback legacy（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4D-3A kickoff → batch-like / 单 bucket repair 在 post-repair recheck 后若仍非完整 success，但存在 runnable `execution_groups`，现已进入 partial profile 路径；post-repair decision 不再返回 `repair_ready` / `legacy_repair`，而是固定归类到 `success / partial_unavailable / blocked_unavailable`（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4D-3B：mixed bucket / batch approved success path 已落地，`profile_batch` 与 `profile_uid + 多 UID` 都会按 `credit -> behavior -> app` 顺序 repair，且 repair 输入仅包含该 bucket 的实际缺失 UID（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4D-3C：mixed bucket / batch-like repair 的 failed、non-approved、still-unavailable、partial-runnable 分支已补齐；non-approved 继续沿用 cancel semantics，failed 与 still-unavailable 保持 terminal fail/block，不 fallback legacy（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4E-1：`uid_file + repair` approved-success bridge 已落地；`uid_file_path + capability enabled/disabled` 都会先 parse，parse 后单 UID / batch-like single-bucket repair 可复用既有 repair path，并保持双 `execution_plan` 契约；`uid_file + repair` 的 non-approved / failed / still-unavailable / partial-runnable / mixed-bucket 继续留给 5D-4E-2（2026-06-02）
- [x] Orchestrator Agent Phase 5D-4E-2：`uid_file + repair` 的 non-approved / failed / still-unavailable / partial-runnable 分支已补齐，并锁定 mixed-bucket approved-success smoke；parse 后继续复用共享 repair path，不 fallback legacy（2026-06-02）
- [x] Orchestrator Agent Phase 5E-1：`QueryDataThenProfileFlow` minimal guard shell 已落地；unsupported country 与 data acquisition disabled/unavailable 现由 flow 接管，`mx + capability enabled=True`、clarification 后 query-only、完整 query-data/profile/repair 主链仍继续 legacy（2026-06-02）
- [x] Orchestrator Agent Phase 5E-2：clarification 后 `auto_profile=false` 的 query-only approved-success path 已迁入 `QueryDataThenProfileFlow`；复用原 clarification execution，第二次 `execution_plan` 只含 `clarify_scope / query_data / review_final`，ACK `approved` 后由 `DataQueryRunner` 执行 cohort 查询并直接产出 query-only final；`rejected / expired / cancelled` 已在 flow 内按 cancel semantics 收口（2026-06-02）
- [x] Orchestrator Agent Phase 5E-3：clarification 后 `auto_profile=false` 的 query-only branch closure 已补齐；`rejected / expired / cancelled`、preview failed、execute failed、empty cohort、too-large cohort、以及 preview 直接 `completed` 的 no-ACK path 全部由 `QueryDataThenProfileFlow` 自行收口，不 fallback legacy，也不进入 `check_data / run_profile / repair_*`（2026-06-02）
- [x] Orchestrator Agent Phase 5E-4：clarification 后 `auto_profile=true` 的 query→profile no-repair success path 已迁入 `QueryDataThenProfileFlow`；query phase 复用共享 `_run_query_data_phase(...)`，query 成功后仅在 post-query `decision.mode == success` 时进入 `check_data -> run_profile -> review/final`，并通过共享 `_profile_runtime.py` 执行 no-repair profile；`empty_cohort`、`cohort_too_large`、`repair_ready`、`blocked_unavailable` 现也由 flow 自行 terminal 收口，不 fallback legacy，也不提前进入 repair（2026-06-02）
- [x] Orchestrator Agent Phase 5E-5A：clarification 后 `auto_profile=true` 的 post-query no-repair decision 已正式扩展为 `success / partial_unavailable / blocked_unavailable`；partial runnable 现会继续 `run_profile -> review(warning) -> final`，blocked 继续 terminal fail/block，repair-aware seam 仍保留但 live path 不进入 `RepairRunner`；当前继续复用 shared runtime 的 `data_acquisition_unavailable + partial_repair` issue 语义，下一阶段入口为 5E-5B（2026-06-02）
- [x] Orchestrator Agent Phase 5E-5B：clarification 后 `auto_profile=true` 的 query→profile live path 已正式切到 single-bucket repair approved-success bridge；single-bucket missing 现优先进入 `RepairRunner`，repair 输入只传真实缺失 UID，repair success 后重新 availability recheck，且 post-repair 仅 `success` 继续 `run_profile`，其余结果先 blocked；`requested_missing > 1`、repair non-approved / failed / post-repair partial 继续留给 5E-5C（2026-06-02）
- [x] Orchestrator Agent Phase 5E-5C：clarification 后 `auto_profile=true` 的 single-bucket query repair branch closure 已补齐；`rejected / expired / cancelled` 现按 cancel semantics 收口、repair execute failed 现进入 terminal fail、post-repair partial runnable 现会继续 `run_profile -> review(warning) -> final`、post-repair blocked 继续 terminal fail/block；post-repair recheck 继续禁止二次 repair，`requested_missing > 1` 仍保守 blocked（2026-06-02）
- [x] Orchestrator Agent Phase 5E-6：首轮 `query_data_then_profile + mx + capability enabled=True` 已进入 `QueryDataThenProfileFlow`，不再走 `_run_known_request()` legacy 主链；first-turn plan 不含 `clarify_scope`，并复用 query 后 continuation 覆盖 success / partial / blocked / single-bucket repair / query failed / empty / too-large / no-ACK completed / non-approved cancel（2026-06-02）
- [x] Orchestrator Agent Phase 5F：`agent_loop.py` 中首轮 `query_data_then_profile` legacy 主业务分支已关闭为 defensive blocked fallback；`execute_query_data_cohort` / `_complete_query_data_cohort` 仅作为 `LoopDependencies` 与 monkeypatch compatibility shim 保留，general-chat `query_data` tool path 不在本轮清理范围内（2026-06-02）
- [x] Orchestrator Agent Phase 6A：`GeneralChatFlow` skeleton 已落地并接管明确 no-tool 的 `general_chat` 普通回答；严格 gate 要求 `request_understanding.answer_mode == "general_chat"` 且 `requires_tools is False`，成功时 `general_answer -> run_completed -> final`，失败时仅 `run_failed/error`；general-chat tool loop / `get_tool_registry` / query-profile-trace-memory 工具路径继续留给 6B/6C（2026-06-02）
- [x] Orchestrator Agent Phase 6B-1：`GeneralChatFlow` 已接管 trace-like `general_chat -> run_trace` 单工具链路；`run_trace` tool_call 先校验 `RunTraceInput`，再 lazy 调用 `tools.get_tool_registry()` 并复用 `ToolRunner` 产出 `tool_started/tool_completed`，成功后追加 tool observation 并只允许一次 LLM continuation final；unsupported tool / invalid args / registry missing / tool error / 第二个 tool_call 均由 flow 自己 failed 收口，无普通 final、无 legacy fallback（2026-06-02）
- [x] Orchestrator Agent Phase 6B-2：`GeneralChatFlow` 已接管 query-like `general_chat -> query_data` 单工具 query-only 链路；`query_data` 不调用 `get_tool_registry()`，而是复用 `DataQueryRunner + LoopDependencies` 保留 SQL preview / ACK / execute 契约，成功后追加 tool observation 并只允许一次 LLM continuation final；ACK rejected / expired / cancelled、invalid args、execute failed、continuation 第二个 tool_call 均由 flow 自己收口，不进入 profile / repair（2026-06-02）
- [x] Orchestrator Agent Phase 6B-3/4：`GeneralChatFlow` 已完成已迁工具 hardening 并接管 profile-like `general_chat -> run_profile` 单工具链路；`run_profile` 不调用 `get_tool_registry()`，而是复用 `ProfileRunner` 保留 `tool_started / tool_progress / tool_completed`，成功后追加 tool observation 并只允许一次 continuation final；query+profile 复合 prompt 继续 legacy seam，memory / multi-tool / tool failure continuation 留给 6C（2026-06-02）
- [x] Orchestrator Agent Phase 6C：`GeneralChatFlow` 已接管 `memory_write / memory_read`，`MemoryFacade` 现绑定 `user_id / project_id / detected_country or session.country or "mx"` scoped wrapper；`memory_write` 成功固定 `final("已记住。")`、`memory_read` 成功走 observation + 单次 continuation final、empty result 仍视为 retrieval success；multi-family prompt 现保守不接管且不会被 `no_tool` 吞掉，continuation 第二个 `tool_call` 统一 blocked；`agent_loop.py` 的旧 general-chat 主 LLM/tool loop 已删除，只保留 dispatch、defensive fallback 与兼容 alias。6C closeout 现已完成：`GeneralChatFlow` 不再 direct `save_session`，tool observation / failed persistence 已收口到 `SessionLifecycle`；Phase 6 可标记 Done，随后进入 Phase 7 final cleanup（2026-06-03）
- [x] Orchestrator Agent Phase 7A：`agent_loop.py` final cleanup audit + docs truth sync 已完成；新增 import boundary 静态测试，并删除 `agent_loop.py` 中已证实无 live caller 的 snapshot helper cluster。`flows/` 的 `save_session|session_store` 审计结果继续保持 clean，`general_chat.py` 的 6C persistence boundary 不回归（2026-06-03）
- [x] Orchestrator Agent Phase 7B：compat helper / shim contraction 已完成；`_call_tool_with_optional_progress` 与 `_log_run_profile_progress` 这两个仅在 `agent_loop.py` 内部使用的本地 shim 已删除，`ProfileRunner` 现直接接到 `execution.profile_runner` 的真实实现；`_run_known_request`、`_run_clarification_resume_legacy`、`_run_general_chat_defensive_fallback` 继续保留为已标注的 legacy / defensive seam（2026-06-03）
- [x] Orchestrator Agent Phase 7C：final shim reduction / README & active docs final sync 已完成；最终审计确认 `agent_loop.py` 剩余 helper 均有 live caller 或明确 seam 价值，因此 7C 以“零额外删除”收官。README 与 active docs 现已同步为 `Phase 7 Done`，并明确当前 orchestrator 为 LangGraph-ready thin shell，而非 LangGraph-migrated / multi-agent 架构（2026-06-03）
- [x] Post-Decomposition Stabilization（first pass）：已完成 `S0 + S1 + S2 + S3 + S4`。当前 decomposition baseline 已冻结到 `HEAD=6f0ef37eca1d1153f290215b4ce7dacc8798a51c`；本地工作区在冻结时为 dirty state，因此 baseline 记录同时保留 `git status --short` 语义。最小 `pytest.ini` 已新增并注册 `timeout` marker；README 已标准化 minimal/full/release 三档回归命令，并补充 `ddtrace` teardown hang 的命令层处理策略；新增开发者指南 `docs/dev/orchestrator-decomposition-guide.md`，用于固定 flow/runner/import-boundary/checklist 规则（2026-06-03）
- [x] Phase S3 Runtime Observability & Trace Quality：已完成 internal trace metadata 审计与最小落地；`ExecutionTraceRecord.internal_metadata` 现作为唯一 observability landing zone，helper 仅 mutate trace、不单独 save；`flow_name / flow_mode / decision_mode / fallback_reason / terminal_reason` 已接入 `GeneralChatFlow`、`ProfileFlow`、`QueryDataThenProfileFlow` 及简单 flows，且 SSE / frontend payload / public session response shape 保持不变（2026-06-03）
- [x] S5 Post-Decomposition Quality Backlog：已完成状态同步与 backlog 文档落地；`docs/plans/post-decomposition-quality-backlog.md` 现作为 D1 / P1 / M1 / LG-0 的统一入口，并已固定优先级、scope、out-of-scope、tests 与 acceptance。S5 是 backlog planning phase，不直接实施 Data Agent / Profile / Memory / LangGraph 改造；下一阶段推荐先做 `D1-0 + D1.1`，并行纳入 `D1.4 SQL Safety / Audit` guard 审计（2026-06-03）
- [x] D1-0 Current State Audit：已完成 `query_data` / Text-to-SQL 当前状态审计，落地文档 `docs/reviews/data-agent-text-to-sql-current-state-audit.md`；当前 `QueryDataInput` public contract 仍保持 `request + country`，`QueryDataThenProfileFlow` / `GeneralChatFlow query_data_tool_loop` ownership、ACK 语义、empty / too-large 语义与 fake-vs-real Data Agent 差异已固定记录（2026-06-03）
- [x] D1.1 Query Request Normalization first slice：已新增 internal-only `app/services/orchestrator_agent/planning/query_request_normalizer.py` 与 `NormalizedQueryRequest`，并接入 `QueryDataThenProfileFlow._run_query_data_phase(...)` 与 `GeneralChatFlow._run_query_data_tool_loop(...)`；normalizer 仅 enrich 内部执行时 request text，不改变 `QueryDataInput`、`NormalizedRequest`、`awaiting_user_ack`、`execution_plan` 或 frontend payload shape（2026-06-03）
- [x] D1.1.1 Country Alias Boundary Fix：已修复拉丁国家别名的 token-boundary 匹配，`th` 不再误匹配 `the / other / cohort` 这类普通英文词；同时收紧 query execution country 优先级，`QueryDataThenProfileFlow` 与 `GeneralChatFlow query_data_tool_loop` 现优先使用 flow/tool 显式 country，再把 normalizer 推断值作为 fallback。`QueryDataInput` public contract、`awaiting_user_ack` / `tool_started.input` / SSE / frontend shape 保持不变（2026-06-03）
- [x] D1.4 SQL Safety / Audit：首轮已完成 guard audit，落地文档 `docs/reviews/data-agent-sql-safety-audit.md`；当前 authoritative safety boundary 仍在 `data_acquisition_agent/executor.py` + `data_acquisition_agent/output_scanner.py`，`tools/query_data.py::_PROHIBITED_SQL` 只作为 shallow guard 记录。现阶段未发现需要立即修改 `data_acquisition_agent/` 的阻塞性安全缺口，因此 first slice 停在 audit + coverage 确认（2026-06-03）
- [x] D1.4-1 SQL Safety Guard Coverage Closure：已补齐 `query_only` 危险类与正向 safe-select coverage，并基于 failing tests 做最小 hardening：`output_scanner.py` 现将 `query_only` 收紧为 `SELECT / WITH` 窄通道，拒绝 `CALL / EXEC / LOAD DATA / INTO OUTFILE`，且不再误伤字符串字面量；`executor.py` 的多语句 split 已避开字符串内分号；`tools/query_data.py` 修复 `None` UID 不再被当作 `"None"` 进入 cohort。另已补 flow-level coverage，锁定 invalid cohort output 不会继续进入 `run_profile`。deferred 项保持为 table allowlist / denylist、`information_schema` policy、approved-SQL audit trace、UID validation centralization（2026-06-03）
- [x] D1.3 Empty / Too-Large Cohort UX：已完成 `empty cohort / too-large cohort` 的 UX 优化，落地文档 `docs/reviews/data-agent-empty-too-large-ux-audit.md`；`QueryDataThenProfileFlow` 的 query-only / query-profile 终态文案现更明确地区分“没有命中用户、不会继续画像、可放宽条件”和“命中过多、已安全阻断、请缩小范围”，`GeneralChatFlow query_data` 的 empty / too-large 结果则继续保持 observation + continuation final 架构，只增强 tool observation prose，不新增 flow-level blocked/fail 分支。`QueryDataInput`、ACK / SSE / frontend shape、too-large threshold、DataQueryRunner 执行方式均未变化（2026-06-03）
- [x] D1.2 SQL Preview Explainability：已完成 `query_data` ACK 前 preview explainability 优化，落地文档 `docs/reviews/data-agent-sql-preview-explainability-audit.md`；`awaiting_user_ack.sql_text` / `pending_ack.sql_text` 现改为 display preview text（可读摘要 + 筛选条件 + 确认提示 + 原始 SQL 区块），但 approve 后执行 SQL 仍只来自 internal `raw_preview["sql_text"]`。`awaiting_user_ack` / `pending_ack` 字段结构、ACK / SSE / frontend reducer shape、消息流与 single-shot `QueryDataOutput.sql_text` 均未变化，也未新增 assistant 说明消息（2026-06-03）

### Phase 7 Final Audit Snapshot（after 7C）

| Symbol | Final Status | Why Kept | Notes |
|---|---|---|---|
| `run_agent_loop` | live shell | 顶层入口、turn/run 初始化、flow dispatch、异常/取消边界 | decomposition 完成后继续保留 |
| `build_loop_dependencies` | dependency factory / monkeypatch seam | `LoopDependencies` 入口与测试 seam | 不在 7C 收缩 |
| `execute_query_data_cohort` | compat / LoopDependencies seam | live flow caller + 大量测试 monkeypatch | 保留 |
| `_complete_query_data_cohort` | compat / LoopDependencies seam | live flow caller + 测试 monkeypatch | 保留 |
| `_build_memory_facade` | live shell helper | 为 `GeneralChatFlow` 绑定 scoped memory facade | 保留 |
| `_detect_country` | shell-local adapter | `run_agent_loop` live caller | 保留 |
| `_input_schema_for` | shell-local adapter | `run_trace` / `parse_uid_file` 参数校验 | 保留 |
| `_promote_workspace_request_to_profile` | shell-local adapter | workspace 追问提升到 profile | 保留 |
| `_clarified_request_from_answers` | clarification helper | legacy clarification fallback 仍复用 | 保留 |
| `_review_step_summary` | local rule adapter | fallback / compat review step 文案适配 | 保留 |
| `_build_profile_review` | local rule adapter | fallback / compat review 构造 | 保留 |
| `_append_data_acquisition_issue` | local rule adapter | fallback / compat review 增补 issue | 保留 |
| `_build_llm_input` | compat alias | 测试与 legacy alias surface 依赖 | 真实实现位于 `runtime.llm_input` |
| `get_tool_registry` | compat surface | monkeypatch surface 仍在 | 保留 |
| `_run_known_request` | temporary compatibility / defensive seam | 仅服务未被迁移 Flow 接住的请求形态 | 已迁主路径不应进入 |
| `_run_clarification_resume_legacy` | temporary clarification fallback seam | 仅服务 prepare/resume 接不住的 clarification 兜底 | query_data_then_profile 主路径不依赖它 |
| `_run_general_chat_defensive_fallback` | thin defensive fallback | 复杂 unsupported general_chat 的 terminal 收口 | 不执行 registry/tool/final |

### Post-Decomposition Stabilization Baseline（first pass）

- Baseline `HEAD`: `6f0ef37eca1d1153f290215b4ce7dacc8798a51c`
- Working tree at freeze time: `dirty`
- Baseline interpretation:
  - `agent_loop.py` decomposition complete
  - `Phase 6`: Done
  - `Phase 7`: Done
  - current orchestrator is a LangGraph-ready thin shell with documented compatibility / defensive seams
- Frozen seam snapshot:
  - `run_agent_loop`
  - `build_loop_dependencies`
  - `execute_query_data_cohort`
  - `_complete_query_data_cohort`
  - `_build_memory_facade`
  - `_build_llm_input`
  - `get_tool_registry`
  - `_run_known_request`
  - `_run_clarification_resume_legacy`
  - `_run_general_chat_defensive_fallback`

### Phase S3 Audit Result

- Internal metadata landing zone：`app/services/orchestrator_agent/schemas.py::ExecutionTraceRecord.internal_metadata`
- Public SSE surface intentionally unchanged：
  - `runtime/trace_store.py::build_execution_plan_event`
  - `runtime/trace_store.py::update_trace_step`
  - `runtime/event_recorder.py::decorate_event`
- Public session response exclusion 已显式固定：
  - `app/api/orchestrator_routes.py::get_session_endpoint` 会排除 `execution_traces[*].internal_metadata`
- Persistence 语义：
  - `runtime/trace_metadata.py::update_internal_trace_metadata(...)` 只 mutate trace
  - 不单独 `save_session()`
  - 依赖既有 `update_trace_step / set_trace_review / finalize_trace / save_trace` 落盘
- Leakage contract：
  - `internal_metadata` 不进入 SSE event payload
  - `internal_metadata` 不进入 frontend reducer 输入
  - `internal_metadata` 不进入普通 public HTTP/session response

### Known Non-Blocking Warnings / Test-Environment Notes

- `pytest.mark.timeout` warning 已通过根目录 `pytest.ini` 注册 marker 消除。
- 某些本地环境若安装 `ddtrace`，pytest 可能在 100% 后 teardown hang；推荐对同一命令追加 `-p no:ddtrace`，不写入 repo 级默认配置。
- FastAPI / Pydantic deprecation warnings 当前归入 dependency modernization backlog，不视为本轮业务失败。

## 已完成（最近）
- [x] Visible execution reliability hardening（2026-05-29）
  - router 修复中文紧贴 UID、workspace rerun 补 UID、trace days 解析，并仅对模糊请求启用轻量 routing classifier
  - `data/id_files/...` 批量路径恢复显式 `parse_uid_file -> run_profile`，保持文件批量画像链路可审计
  - availability 改成“可画像”语义：`usable_for_profile + checked_sources`，修复 invalid JSON 遮蔽 CSV
  - behavior / credit CSV 最小 schema 校验收紧，不再只靠 `uid` 通过
  - visible execution 调 `run_profile` 强制 `strict_data_mode=True`，禁止 sample fallback 污染
  - batch 模块执行改成 per-UID 规划，严格尊重用户请求模块和依赖链
  - repair 改成懒加载 Data Agent 执行依赖，并在写回后做 availability 复检
  - execution trace 统一 `review_final`，general chat 至少带 `general_answer` step
- [x] Visible execution V3 stability pass（2026-05-29）
  - `tools/query_data.py` 改成 no-write cohort 执行，不再通过 output writer 写入 `data/*/by_uid`
  - `tools/__init__.py` 与 `query_data` 全链路 lazy import，普通 orchestrator 导入不再放大 `pymysql` 依赖
  - ACK 生命周期统一调整为 `open_ack -> awaiting_user_ack -> wait/execute`
  - availability 增加列名归一化、prepared JSON 最低质量门槛、`quality_score / weak_reasons / row_count`
  - review 升级为读取 `profile_output` 实际结果，识别 `module_error / empty_summary / missing_structured_result / degraded_model_output`
  - general LLM tool loop 中若调用 `run_profile`，强制注入 `strict_data_mode=True`
- [x] Visible execution V4 data compatibility & review accuracy（2026-05-29）
  - availability 的 credit CSV 改为兼容真实 MX raw 字段与 UID alias，不再把本地 raw credit 误判成缺失
  - `query_data` UID alias 扩到 `user_uuid / customer_id` 等真实 SQL 列名
  - review 改成围绕“请求模块及其依赖是否满足”判定；单模块请求成功即 `pass`
  - direct `repair_profile_data()` 的 ACK 顺序改成先 `open_ack` 再触发 preview callback
  - `app.main` 在缺 Data Agent 执行依赖时仍可启动，但不挂 `/api/data-acquisition/*`
- [x] Visible execution V5 clarification & cohort repair gating（2026-05-29）
  - router 新增 `need_clarification`，cohort 信息不足时走可恢复 clarification 卡
  - 新增 `awaiting_resolution` SSE 事件与 `/api/orchestrator/sessions/{id}/resolve`
  - clarification 补完 `country + time_window` 后在同一 execution 内继续执行
  - cohort 返回 UID `> 20` 且缺失 bucket `>= 2` 类时，先弹 repair 策略卡
  - 前端 reducer / ChatPanel 新增 `pendingResolution`，与 SQL ACK 分离
- [x] Visible execution V5 production hardening（2026-05-29）
  - credit repair 正式切到 raw-first，prompt / required columns 不再要求画像摘要字段
  - `data_acquisition_agent/api.py` 改成 `/execute` 局部导入执行层依赖，轻量导入 `router`
  - `output_writer` 前移 behavior / credit 最小 schema 校验，阻止 uid-only 脏数据落盘
  - clarification 卡升级成可编辑表单，支持 `country / time_window / auto_profile`
  - cohort repair strategy 阈值改成 `UID >= 10` 或 `missing buckets >= 2` 或 `estimated repairs >= 2`
  - `query_data()` 单次调用改为优先返回真实 `rows_estimated`
- [x] Visible execution V6 consistency & data quality pass（2026-05-29）
  - clarification answers 中 `auto_profile=false` 改成 query-only 收束，不再自动继续画像
  - review 的 weak bucket warning 只检查 required buckets，避免 App-only 被 credit fallback 误伤
  - credit signal contract 拆成 strong raw / weak meta / summary，并统一到 availability + output writer
  - `output_writer` 新增 `uid_column -> actual column` 解析与 behavior / credit 行级非空校验
  - Data Agent capability 改成 tri-state，并统一作用于 router 挂载、query-data 与 repair
- [x] NL Chat 回合化执行流 + run 级取消（2026-05-29）
  - `OrchestratorSession` 新增 `turns / run_events / active_run lock`
  - SSE 统一补齐 `event_id / event_seq / turn_id / run_id / trace_id`
  - 已知请求路径与 general chat 都开始写入 run-scoped tool / trace / final 归属
  - 前端 `chatReducer` 改成 `turns[]` 归并，工具流与执行轨迹不再固定在聊天底部
  - 输入框运行中切换为停止按钮，新增 `/api/orchestrator/sessions/{id}/runs/{run_id}/cancel`
  - cancelled run 不再自动提交 workspace，也不作为默认只读追问证据来源
- [x] NL Chat 回合化稳定性收尾（P0 + P1，2026-05-30）
  - `send_message` 新增 pending-prompt 409 保护，避免 stream 启动前第二条消息覆盖
  - ACK 改为严格匹配 `ack_id or tool_call_id`；resolution 提交强制要求 `resolution_id`
  - `TurnRunRecord` 新增 `pending_ack / pending_resolution`，等待态刷新恢复不再只靠 trace 猜测
  - reducer 新增 `event_id` 去重、run 级 `event_seq` 防旧事件回滚、同序号不同类型补丁兼容
  - ACK / Resolution 卡片下沉到所属 run 内；cancel accepted 后前端先本地进入 `cancel_requested`
  - cancelled run 的 partial tool/artifact 不进入默认 `answer_from_workspace` evidence bundle
- [x] NL Chat 回合化执行流验收版收口（2026-05-30）
  - long-running known/general tool path 统一补齐“结果返回后、写入前”的 cancel 检查，`run_trace / run_profile / repair / query_data / general LLM final` 不再在停止后继续写 output 或 final
  - SQL ACK timeout 改为 `ack_expired + run_cancelled` 语义，不再走普通 error final
  - legacy `/api/orchestrator/chat` 新增 active-run / pending-prompt 最小保护，避免旧入口绕过会话锁
  - `run_events` fallback 恢复已接入前端，显式 pending 字段缺失时仍能恢复未闭合 `awaiting_user_ack / awaiting_resolution`
  - cancelled tool call 现已在实时流和刷新恢复后都显示 `CANCELLED`，不再误报为运行中
- [x] Visible execution V2 hardening（2026-05-28）
  - `execution_plan` 新增 `request_understanding`：显式展示 route label / rewritten goal / focus / answer mode / route reason
  - 只读追问默认基于已有画像证据调一次受限 LLM；模型失败回退模板式 summary
  - `general_chat` 也先发 lightweight execution trace，不再完全黑盒
  - 无 reusable workspace 且无 UID 的只读追问直接 blocked，不再静默回退 general chat
  - repair 仅对真实缺失该 bucket 的 UID 执行
  - 前端 trace 卡新增“需求理解 / 路径说明 / 为什么这样做 / 观察结果”
- [x] Orchestrator Agent Phase 5A kickoff（2026-06-01）
  - `execution/repair_runner.py` 外部 `CancelledError` 现已显式清理 `pending_ack / run.status / ToolCallRecord`
  - `flows/base.py` 新增 `KnownFlow.can_handle()`，known flow 接管改成“候选 flow + 可处理性判断 + legacy fallback”
  - `flows/answer_workspace.py` 已开始接管 `answer_from_workspace` 中 evidence 充足的 workspace answer 子路径
  - `answer_from_workspace` 中 evidence 不足但需要 promote/rerun profile 的路径继续保留 legacy 行为
- [x] Visible execution + repair loop（2026-05-28）
  - known-intent 请求走确定性执行器，general chat 保留原有 LLM loop 兜底
  - `execution_traces` 持久化并接入会话恢复 / SSE / 前端 trace 卡
  - `query_data_then_profile` 支持 cohort -> availability -> repair -> profile 两段式闭环
  - repair 拒绝 / 非 `mx` Data Agent / 零基础 bucket 走显式 blocked 或降级回答
  - review step 与 review_result 对齐，不再残留 `pending`
- [x] NL Chat 状态分层修复（2026-05-27）
  - workspace state / chat session / reusable workspace snapshot 三层显式分离
  - 历史会话点击不再整页跳转，不再清空左侧画像
  - 新增“恢复该次分析结果”，按历史 `tool_calls` 重建左侧 workspace
  - 只读追问命中已有画像结果时，agent loop 直接模板化回复，不再默认重跑 `run_profile`
- [x] 前端渐进加载迁移（参考项目融合）→ docs/plans/frontend-progressive-loading-plan.md（2026-05-02）
  - 后端：shared_orchestrator 单例 + 模块级缓存 + `/api/analyze-module` + `/api/ui-config`
  - 前端：SSE → 模块级渐进加载 + 假动画过渡 + ModuleStatusPanel 四态重试 + trace 独立加载
  - AppPanel 大模型分析报告卡片（已存在）
  - BehaviorPanel 中文乱码修复 + 大纲 LLM 摘要
  - 270 passed 0 failed
- [x] A1 Golden Test 评估框架（behavior 4 case + comprehensive 1 case smoke）— 完成（2026-05-01，docs/specs/golden-test-design.md + docs/plans/golden-test-plan.md）
- [x] Memory Eval V1（policy / recall@8 / no-leak / redaction / management gates）— 完成（2026-05-25，tests/golden/memory_eval.py + tests/fixtures/golden/memory/eval_set.json）
- [x] D2 SSE 进度推送 → docs/plans/sse-progress-plan.md（2026-05-01，[complete] sse-progress-plan，235 tests passed）
  - Step 2 Design Doc：docs/specs/sse-progress-design.md（Q1-Q6 全锁）
  - Step 3 架构 Stub
  - Step 4 Plan：8 Task TDD
  - Step 5+ 执行：Task 1-8 全部完成
    - Task 1: SkillRegistry.run_all 加 progress_callback
    - Task 2: Orchestrator 透传 callback + analysis_progress 事件
    - Task 3: SSE 端点骨架 (queue 桥接 + heartbeat)
    - Task 4: 总超时 watchdog + stream_error 兜底
    - Task 5: 前端 analyzeByUidStream SSE 解析
    - Task 6: 前端 ProgressView 组件
    - Task 7: app.jsx 集成 streaming view（删除假 LOADING_TEXTS 动画）
    - Task 8: 路由挂载 + LOAD_ORDER 注册

## 历史进行中
- 功能：data_acquisition_agent V1+V2 收尾
- V1 收尾：
  - prompt/security hardening → 已完成（5183809）
  - real LLM JSON 稳定性 → ✅ 已修复（2026-04-30，3/3 成功，commit 32d64e0）
  - Step 8 白盒审计 → 待做
  - Step 8 面试技术总结 → 待做
- V2 状态：Step 5 TDD 全量完成（2026-04-30，163 passed, 1 skipped, 0 failed）
  - 待做：Step 7 交付（push + PLANNING.md 更新）
  - 待做：Step 8 白盒审计 + 面试技术总结

## 待做
- [x] V1 follow-up: stabilize real LLM structured JSON output — 已修复（2026-04-30，32d64e0）
  - 修复：_parse_json_text 预转义裸换行 + schema required 5 key + NL→sql_kind 一致性检查
  - 结果：real LLM 3/3 成功（修复前 0/3），278 passed 0 failed
- [x] V2 Step 3：架构设计 — 已完成（2026-04-29）
- [x] V2 Step 4：Plan — 已确认（2026-04-29，docs/plans/data-acquisition-v2-plan.md）
- [x] V2 Step 5：TDD 实现 — 已完成（2026-04-30，71 tests，全量 163 passed）
- [x] V2 Step 7：交付 → ✅ 完成（2026-04-30）
- [ ] V2 Step 8：白盒审计 + 面试技术总结
- [x] V7 Capability Gating Follow-up：测试 capability 显式控制、direct profile planning gating、`data_acquisition_unavailable` step、credit `source_shape` 收紧、`rows_per_uid` numeric UID 修复（2026-05-29）
- [x] Orchestrator Phase 5D-3：`ProfileFlow` 引入 `_ProfileGateDecision` 与 `get_data_acquisition_capability` seam，接管 `data_acquisition_unavailable` 的 partial / blocked guard path；repair-required 请求继续 legacy fallback（2026-06-01）
- [x] Orchestrator Phase 5D-3 Test Contract Cleanup：移除未显式绑定 capability 前提的旧 `repair_required` baseline；repair fallback 测试统一显式 patch `enabled=True`，unavailable guard 测试统一显式 patch `enabled=False/unavailable`（2026-06-01）
- [x] Orchestrator Phase 5D-4C.1：补齐双 bucket repair 的边界收口，包括 `requested_missing > 2` legacy fallback、第一个 repair failed、第二个 repair non-approved、以及双 repair success 后仍 unavailable 的 terminal/cancel 契约（2026-06-02）
- [x] Orchestrator Phase 5D-4D-3B：扩展到 mixed bucket / batch approved success path，处理不同 UID 缺不同 bucket 的 repair 输入分组与顺序编排（2026-06-02）
- [x] Orchestrator Phase 5D-4D-3C：收口 mixed bucket / batch-like repair 的异常矩阵，包括 first failed、second failed、first rejected、second rejected/expired/cancelled、still unavailable 与 partial runnable smoke（2026-06-02）
- [x] Orchestrator Phase 5D-4E-1：打通 `uid_file -> parse_uid_file -> resolved uids -> repair_ready -> approved repair -> run_profile` 主链路，并补齐 `enabled=True` 下的 parse terminal 保护与 post-parse unsupported repair scope blocked 语义（2026-06-02）
- [x] Orchestrator Phase 5D-4E-2：收口 `uid_file + repair` 的 non-approved / failed / still-unavailable / partial-runnable 分支，并补齐 `uid_file + mixed-bucket` approved-success smoke 与 visible execution 契约（2026-06-02）

## 已完成
- Phase 0 / Task 0.0 — 添加 pyyaml 依赖（1bfac61）
- Phase 0 / Task 0.1 — 填 mexico.yaml 真实知识库路径（4bb3d26）
- Phase 1 / Task 1.1 — schemas: 要求 sql 或 python 至少一非空（739b985）
- Phase 1 / Task 1.2 — schemas: sql_kind ↔ high_risk_ddl 联动 validator（02602d7）
- Phase 2 / Task 2.1 — manifest: CountryManifest YAML loader（b253add）
- Phase 3 / Task 3.1 — redactor: L1 凭据脱敏（11 family，15 tests）（06cdf41）
- Phase 4 / Task 4.1 — output_scanner: L2 凭据回扫（400d6c6）
- Phase 4 / Task 4.2 — output_scanner: Python 危险代码黑名单（d6c7bf1）
- Phase 4 / Task 4.3 — output_scanner: SQL DDL 二分策略（cf2af70）
- Phase 5 / Task 5.1 — prompt_assembler: CJK 加权 token 估算（740bfd2）
- Phase 5 / Task 5.2 — prompt_assembler: assemble_prompt + 800K 阈值护栏（b63dc6d）
- Phase 6 / Task 6.1 — orchestrator: 骨架 + request_id + happy path（3eaaf1d）
- Phase 6 / Task 6.2 — orchestrator: 输出策略三类分流（b7aa784）
- Phase 6 / Task 6.3 — orchestrator: response 异常兜底 → schema_validation_failed（dfc907b）
- Phase 7 / Task 7.1 — api: 接 orchestrator + ErrorType→HTTP 映射（ca3f708）
- Phase 7 / Task 7.2 — app/main.py 挂载 da-agent router（8163d73）
- Phase 8 / Task 8.1 — e2e mock LLM happy-path 集成测试 [complete]（c8793e3）
- V1 prompt/security hardening — prompt 注入 analyst_private_prefix + 默认 query_only + 禁止 Python DB client；ErrorResponse / OrchestratorError 改为固定安全短消息，避免泄漏 SQL / Python / LLM payload（5183809）
- V2 Phase 1 / Task 1.1 — ExecuteRequest validators（15c8c68）
- V2 Phase 2 / Task 2.1 — starrocks connection layer（b65b28d）
- V2 Phase 3 / Task 3.1 — pre-execution gates（18ccef1）
- V2 Phase 3 / Task 3.2 — count precheck（67339ab）
- V2 Phase 3 / Task 3.3 — execute_query（8cbaa4b）
- V2 Phase 4 / Task 4.1 — bucket schema validation（6485e5d）
- V2 Phase 4 / Task 4.2 — per-uid payload builder（1c02b38）
- V2 Phase 4 / Task 4.3 — atomic per-uid writer（142d592）
- V2 Phase 4 / Task 4.4 — resolve bucket dir（a891a87）
- V2 Phase 5 / Task 5.1 — execute pipeline（c59dfa9）
- V2 Phase 5 / Task 5.2 — wire api /execute to pipeline（178faff）
- V2 Phase 6 / Task 6.1 — T1 build_table_script no-connect（72c7a8f）
- V2 Phase 6 / Task 6.2 — T2 query_only DDL/DML reject（e02bd45）
- V2 Phase 6 / Task 6.3 — T3 connection no secret leak（6567230）
- V2 Phase 6 / Task 6.4 — T4 fixed error messages（b26dc08）
- V2 Phase 6 / Task 6.5 — e2e mock executor happy path [complete]（5ef1699）

## 开发中发现
- [ ] **behavior_profile fixture 中文乱码**：tests/fixtures/golden/behavior_profile/*.json 的 `evidence.behavior_profile_narrative.behavior_summary` 是乱码字节（GBK / latin-1 误解 UTF-8 字节流），影响 L3-d 跨 case quincena 关键词断言（当前 G1/G3 quincena_mentions 双 0，已 warning skip 严格大于）。根因推测在 ModelClient → Vertex SDK 的 protobuf decode 环节。修复后需重跑 `pytest tests/test_golden_behavior_comprehensive.py --refresh-fixtures` 重录 fixture（2026-05-01，A1 Golden Test 落地时发现）
- [x] `app/schemas/behavior_profile.py` 与 `app/schemas/credit_profile.py` 字段稀疏，大量字段藏在 `dict[str, Any]` 中（细节 Plan 阶段确认）— ✅ 已通过 P1 补全（2026-04-30，b5f165e）
- [x] 已发现：Pydantic v1 的 `@root_validator` 有 deprecation warning，迁移到 v2 的具体落点待 Plan 阶段确认
- [ ] `app/ui/live_frontend.py` 2256 行 HTML/JS 嵌入 Python 字符串，待前端分离（关联 P4：docs/specs/ui-separation-design.md / docs/plans/ui-separation-plan.md）
- [x] behavior_profile / credit_profile 的 `structured_result` 顶层未回传 `model_trace`，与 app_profile / comprehensive_profile 不一致 —— 影响 used_llm 可观测性（2026-04-28 P0-2 验证发现）
- [x] behavior_timeline_summary 在端到端运行中触发 1 次 json_parse retry（"Unterminated string"），retry 后仍 fallback 到 model_unavailable —— 需关注稳定性（2026-04-28 P0-2 验证发现）
- [x] data_acquisition_agent V2 — 连接 StarRocks 执行审核后 SQL + 数据落到 data/ per-uid 文件 — Step 5 TDD 完成（2026-04-30，71 tests）
- [x] v7 follow-up 已收敛 direct profile gating：Data Agent disabled/unavailable 时，仅对本次请求相关缺失 bucket 发出 `data_acquisition_unavailable`；可运行基础模块继续 partial profile，不再先生成 `repair_*` 再执行期失败（2026-05-29）
- [x] NL Chat UX v4 验收补丁：补 `run_failed` 前端终态、stop feedback 闭环、`tool_completed.status=cancelled` 兼容、历史 trace pending 摘要文案修正（2026-05-30）

## 阻塞项
（空）

## P0-2 验证结果（2026-04-28）
- 环境：执行 `pip install -r requirements.txt` 装入 google-genai-1.73.1（之前缺包）
- 配置：MODEL_MODE=vertex，model=gemini-3.1-pro-preview，project=amberstar-gemini，location=global，credentials=key.json
- ModelClient 探针：HTTP 200，JSON 解析成功（status=ok，reply=OK）
- 端到端 orchestrator.analyze(['824812551379353600'])：总耗时 ~163s，4 个 skill 全部 status=ok
  - app_profile：used_llm=True（model_trace 在 sr 顶层）
  - comprehensive_profile：used_llm=True（model_trace 在 sr 顶层）
  - behavior_profile：日志显示调用 LLM 成功（含 1 次 retry 因 json_parse），但 sr 顶层无 model_trace 字段
  - credit_profile：日志显示调用 LLM 成功，但 sr 顶层无 model_trace 字段
- 开发中发现新增条目见下
