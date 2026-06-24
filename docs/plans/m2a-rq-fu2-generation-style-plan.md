# M2A-RQ-FU2 Generation Style Plan

## Goal

在不进入 `M2B`、不改 retrieval 架构的前提下，减少 Data Agent SQL generation 的 few-shot / historical drift。

## Hard Boundaries

本阶段不改：

- `GenerateRequest` / `GenerateResponse` schema
- `M1` SQL HITL 状态机
- `M1.5` Orchestrator Bridge
- `query_data`
- retriever scoring
- seed assets
- Safety Gate 主逻辑
- vector retrieval / embedding / rerank
- 默认不改 `data_acquisition_agent/orchestrator.py`

## Work Items

### 1. Docs kickoff

- 新增 FU2 design / plan 文档
- 更新 `PLANNING.md`
- 更新 `TASK.md`

### 2. Prompt context anti-copy guidance

修改 `app/data_knowledge/prompt_context.py`：

- 保持 example 摘要化
- 加入 current-request-first guidance
- 加入 anti-copy guidance
- 加入 field-family grounding guidance
- 加入 writeback under-specified safe refusal guidance

### 3. Prompt assembler current-request priority rules

修改 `data_acquisition_agent/prompt_assembler.py`：

- 在 retrieved Data Agent context 存在时，注入 current-request priority rules
- 防止 model 继承 example 的 literal dates / source filters / placeholders / alias family
- `sql=null` 指导仅在 writeback under-specified 场景出现

### 4. Rendering tests

- 新增 `tests/data_knowledge/test_prompt_context.py`
- 更新 `data_acquisition_agent/tests/test_prompt_assembler.py`

覆盖：

- current request is the source of truth
- do not copy literal dates
- do not copy uid placeholders
- prefer field names explicitly present in the retrieved catalog
- do not broad-scan behavior table
- `return sql=null` 只在 writeback under-specified guidance 出现

### 5. Regression checks

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py -q`
- `pytest tests/data_knowledge/test_data_knowledge_retriever.py tests/data_agent/test_api.py data_acquisition_agent/tests/test_orchestrator.py -q`

### 6. Live rerun and results doc

复跑：

- `mx-high-risk-cohort`
- `mx-behavior-writeback`
- `mx-glossary-combo-writeback`

记录到：

- `docs/reviews/m2a-rq-fu2-generation-style-results.md`

每条样例固定记录：

- historical field drift
- historical date/filter drift
- unresolved placeholder drift
- literal example-copy drift
- broad-scan risk
- 是否保留当前请求组合意图
- 结论：`pass / partial / fail / still_needs_runtime_followup / ready_for_m2b`
