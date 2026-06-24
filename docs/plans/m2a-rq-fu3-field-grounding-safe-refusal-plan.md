# M2A-RQ-FU3 Field Grounding & Safe Refusal Plan

## Summary

本轮只做两个 follow-up：

1. stronger field grounding with warning-only unsupported-field risk
2. normalize under-specified writeback refusal into a Data Agent specific `422`

本轮不进入 `M2B`，不改 public schema，不改 `M1` / `M1.5` / `query_data`。

## Planned Changes

### Prompt grounding

- 在 `PromptContextAssembler` 中新增 `table -> allowed fields` section
- 强化 field grounding 规则：
  - selected table fields must come from retrieved catalog/glossary
  - do not switch to historical alias families unless grounded
  - do not invent new base-table fields from historical examples

### Warning-only field risk

- 在 Data Agent SQL review/safety detail 中新增 `UNSUPPORTED_FIELD` warnings
- 只标高置信 base-table field
- warning-only，不改变 `safety_status`，不改变 approve / execute 状态机

### Safe refusal normalization

- 新增 `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`
- 只用于 under-specified `bucket_writeback`
- create/revise 保持现有 “不落 run/version” 或 “不改 current version” 语义

## Verification

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py -q`
- live rerun:
  - `mx-high-risk-cohort`
  - `mx-behavior-writeback`
  - `mx-glossary-combo-writeback`

## Commit Order

- `docs: define m2a rq fu3 field grounding and safe refusal plan`
- `feat: add field grounding prompt and risk warnings`
- `feat: normalize under-specified writeback refusal`
- `docs: record m2a rq fu3 rerun results`
