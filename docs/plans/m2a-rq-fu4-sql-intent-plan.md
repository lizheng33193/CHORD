# M2A-RQ-FU4 Canonical Field Policy & SQL Intent Plan Plan

## Summary

本轮只做两个 runtime follow-up：

1. canonical field policy 的 prompt + warning 收口
2. `bucket_writeback` 尤其 combo writeback 的 prompt-side SQL intent plan

本轮不进入 `M2B`，不改 public schema，不改 `M1` / `M1.5` / `query_data`。

## Planned Changes

### Docs and state

- 新增 `docs/specs/m2a-rq-fu4-sql-intent-plan-design.md`
- 新增 `docs/plans/m2a-rq-fu4-sql-intent-plan.md`
- 更新 `PLANNING.md`
- 更新 `TASK.md`

### Canonical field policy

- 新增 `app/data_knowledge/canonical_fields.py` 作为单一内部来源
- 在 `app/data_knowledge/prompt_context.py` 中新增 `canonical_field_guidance`
- 在 `app/data_agent/service.py` 中新增 `NON_CANONICAL_FIELD`
- table matching 统一走 normalize，支持 `hive.dwd.dwd_w_apply -> dwd_w_apply`

### SQL intent plan

- 在 `app/data_knowledge/prompt_context.py` 中新增 `sql_intent_plan`
- 只在 `run_type=bucket_writeback` 且 request specified 时渲染完整 plan
- `target_cohort_conditions` 只从明确 marker 归一化，不从泛动词猜测
- `required_fields` 只包含当前 retrieved grounding 已支撑字段
- `forbidden_patterns` 固定包含 placeholder / broad scan / historical drift 风险

### Prompt assembler alignment

- `data_acquisition_agent/prompt_assembler.py` 提升 canonical guidance 与 sql intent plan 到全局优先规则
- 与 `prompt_context.py` / `service.py` 对齐 under-specified writeback helper，避免词表漂移

## Verification

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py -q`
- `pytest tests/data_knowledge/test_data_knowledge_retriever.py data_acquisition_agent/tests/test_orchestrator.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py -q`
- live rerun:
  - `mx-high-risk-cohort`
  - `mx-behavior-writeback`
  - `mx-glossary-combo-writeback`

## Commit Order

- `docs: define m2a rq fu4 sql intent plan`
- `feat: add canonical field guidance for sql generation`
- `feat: add sql intent plan guidance for combo writeback`
- `docs: record m2a rq fu4 sql intent plan results`
