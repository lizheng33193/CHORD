# M2A-Runtime Quality Results

## Scope

本轮完成了 `M2A-Runtime Quality` 的 5 个运行时质量收敛目标：

1. unresolved placeholder Safety Gate 拦截
2. deterministic retriever false positive 收敛
3. SQL example / few-shot pattern guidance 强化
4. structured output fallback 与可解释失败
5. 结果文档与中等范围回归验证

本轮没有做：

- vector DB / embedding / reranker
- `query_data` 接入 `M2A`
- `M1 SQL HITL` 状态机改造
- `M1.5 Orchestrator Bridge` contract 改造

## Implemented Changes

### 1. Safety Gate placeholder blocking

`app/data_agent/safety.py` 现已新增 unresolved placeholder 检测：

- angle-bracket placeholders：`<target_users>`、`<table_name>`、`<start_date>`
- brace placeholders：`{name}`、`{{name}}`、`${name}`
- placeholder keywords：`TODO`、`TBD`、`PLACEHOLDER`、`replace_me`、`your_table`

当前行为：

- 有 placeholder 的 SQL 会进入 `safety_status=blocked`
- run / version 仍可落库供审核与审计查看
- `approve / execute` 会被拒绝
- 正常比较如 `amount < 100`、`dt > '2026-01-01'` 不会误杀

### 2. Retriever false positive tightening

`app/data_knowledge/retriever.py` 现已增加 section-aware deterministic scoring：

- `run_type` 与 `output_bucket` 参与 `sql_examples` / `error_cases` 初筛
- behavior domain table/field/glossary 在非 writeback 场景下降权
- pure `cohort_query` high-risk 请求不再召回 behavior writeback example
- combo writeback 请求仍可召回 behavior glossary/table/example

当前效果：

- `mx high-risk cohort` 不再把 `dwb_b1_data_burying_point` 带进 catalog tables
- `term:writeback_behavior` 不再出现在纯 high-risk cohort glossary
- combo behavior writeback 请求仍能保留 behavior assets

### 3. Prompt context pattern guidance

`app/data_knowledge/prompt_context.py` 已强化 example section：

- 保留摘要型 example，不恢复完整 SQL 注入
- 新增 pattern guidance 指导语
- 明确禁止 literal copy example WHERE clauses
- 对 behavior writeback 增加 cohort-first / join-by-uid / no broad scan 约束

### 4. Structured output fallback and 422 semantics

`data_acquisition_agent/orchestrator.py` 已新增最小 structured output repair：

- fenced JSON 可解析
- JSON 前后夹杂说明文字可提取
- 非 JSON 或无法恢复 payload 返回受控 schema failure

`app/data_agent/service.py` 现已明确区分两类失败：

- Safety Gate blocked：有 SQL，可落 run/version，但 `safety_status=blocked`
- structured output unrecoverable：
  - `create_run -> HTTP 422`，不创建 `DataAgentRun`
  - `revise_run -> HTTP 422`，不创建新 version，旧 run/version 保持不变

错误响应现固定包含：

- `detail.code`
- `detail.stage`
- `detail.request_id`

同时不暴露 raw LLM output / prompt / internal context。

## Verification

### Targeted checks

- `git diff --check`
- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_agent/test_safety.py tests/data_knowledge/test_data_knowledge_retriever.py data_acquisition_agent/tests/test_orchestrator.py tests/data_agent/test_api.py -q`

结果：

- `39 passed`

### Regression subset

- `pytest tests/auth/test_seed.py tests/auth/test_permissions.py tests/data_knowledge/test_data_knowledge_service.py tests/data_knowledge/test_data_knowledge_api.py tests/data_knowledge/test_data_knowledge_retriever.py tests/data_agent/test_api.py data_acquisition_agent/tests/test_prompt_assembler.py data_acquisition_agent/tests/test_orchestrator.py -q`

结果：

- `58 passed`

## Outcome By Problem

### unresolved placeholder

状态：已收口

- placeholder SQL 会被 Safety Gate blocked
- comparison operator 不误杀

### table-level false positive

状态：已明显改善

- `mx high-risk cohort` 的 behavior false positive 已被定向压下
- combo writeback 仍可命中 behavior assets

### few-shot 风格过强

状态：已收口第一轮

- prompt context 已改为更强的 pattern guidance
- broad scan behavior pattern 已不再被 prompt context 隐式鼓励

残余风险：

- seed 中 historical SQL example 仍然存在，模型在真实 LLM 场景下仍可能保留部分旧风格漂移

### structured output fallback

状态：已收口第一轮

- fenced JSON / explanatory-text JSON 可恢复
- non-JSON 走可解释 `HTTP 422`
- Data Agent run 生命周期与 pre-HITL generation failure 已明确分离

## Remaining Risks

本轮仍未处理：

- 更复杂的 JSON repair 变体，例如多段 JSON 候选、深层字段名漂移
- 真实模型在长 prompt 下的风格漂移评估
- `M2B` hybrid retrieval / semantic retrieval

## Recommendation

当前可以把 `M2A-Runtime Quality` 视为已完成第一轮 runtime 收口。

推荐下一步：

1. 如需继续验证真实生成质量，可补一轮新的 fixed-sample rerun
2. 若运行时结果稳定，再进入 `M2B` 设计：hybrid retrieval / embedding / rerank
