# M2A-RQ-FU5 Plan-to-SQL Consistency Review Plan

## Summary

`FU5` 在 `FU4` 的 `sql_intent_plan` 之上新增 deterministic post-generation review。目标不是让模型生成新的 plan，而是检查生成后的 SQL 是否真正遵守当前 plan，并把 drift 以 warning-only 方式暴露给 reviewer。

## Implementation

### 1. Docs and status

- 新增 FU5 design / plan 文档
- 更新 `PLANNING.md`
- 更新 `TASK.md`

### 2. New review helper

新增：

- `app/data_agent/plan_review.py`

核心函数：

```python
def review_sql_against_intent_plan(
    *,
    sql_text: str,
    retrieval_snapshot: dict,
    natural_language_request: str,
    run_type: str,
    output_bucket: str | None,
) -> list[dict]:
    ...
```

helper 只读取现有 snapshot，不访问 DB、模型或 retriever。

### 3. Warning categories

第一版支持：

- `PLAN_DATE_DRIFT`
- `PLAN_SOURCE_FILTER_DRIFT`
- `PLAN_CANONICAL_FIELD_DRIFT`
- `PLAN_REQUIRED_FIELD_MISSING`
- `PLAN_BROAD_SCAN_RISK`
- `PLAN_FORBIDDEN_PATTERN`

### 4. Service integration

在 `app/data_agent/service.py` 中，将 plan review warnings 合并到现有 `safety_result["warnings"]`：

1. Safety Gate
2. field grounding warnings
3. canonical field warnings
4. plan-to-SQL consistency warnings

`PLAN_*` warnings 只进入 review metadata，不改变 `safety_status` 或 SQL HITL 状态流。

### 5. Tests

新增：

- `tests/data_agent/test_plan_review.py`

扩展：

- `tests/data_agent/test_api.py`

重点覆盖：

- fixed date drift
- dynamic relative date not drift
- fixed source filter drift
- canonical alternative drift
- behavior required field missing
- behavior broad scan risk
- clean cohort + behavior join SQL does not drift

### 6. Live rerun

新增：

- `docs/reviews/m2a-rq-fu5-plan-sql-consistency-results.md`

复跑：

- `mx-high-risk-cohort`
- `mx-behavior-writeback`
- `mx-glossary-combo-writeback`

## Verification

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_agent/test_api.py tests/data_agent/test_plan_review.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py -q`
- `pytest tests/data_knowledge/test_data_knowledge_retriever.py data_acquisition_agent/tests/test_orchestrator.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py tests/data_agent/test_plan_review.py -q`

## Commit order

1. `docs: define m2a rq fu5 plan sql consistency`
2. `feat: add plan to sql consistency warnings`
3. `test: cover plan sql consistency review`
4. `docs: record m2a rq fu5 rerun results`
