# M2A-RQ-FU6 Plan-guided Regeneration / Repair Results

## Summary

`FU6` added one bounded repair attempt for agent-generated SQL in `create_run()` and `revise_run()`. The repair attempt is deterministic on the harness side:

- first-pass SQL still runs through Safety Gate
- `UNSUPPORTED_FIELD` / `NON_CANONICAL_FIELD` / `PLAN_*` warnings are still collected
- repair triggers only once and only for repairable `PLAN_*` warnings
- repair traces stay in `safety_result["repair"]`
- repair failure falls back to the original first-pass SQL

Fresh local verification for the implementation:

- `pytest tests/data_agent/test_repair.py -q` -> `6 passed`
- `pytest tests/data_agent/test_api.py -q` -> `36 passed`
- `pytest tests/data_agent/test_api.py tests/data_agent/test_plan_review.py tests/data_agent/test_repair.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py -q` -> `71 passed`
- `pytest tests/data_knowledge/test_data_knowledge_retriever.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_orchestrator.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py tests/data_agent/test_plan_review.py tests/data_agent/test_repair.py -q` -> `92 passed`

## 1. mx-high-risk-cohort

request:

```text
查询最近 7 天高风险用户
```

retrieved context summary:

- `dwd_w_apply`
- grounded fields: `apply_time`, `risk_level`, `loan_count`, `max_overdue_days`
- `sql_intent_plan_summary`: none

canonical field guidance:

- none grounded for `user_uuid -> uid`

sql_intent_plan summary:

- none

first-pass SQL:

```sql
SELECT
  user_uuid
FROM
  hive.dwd.dwd_w_apply
WHERE
  risk_level = 'high'
  AND apply_time >= DATE_SUB(CURRENT_DATE(), 7)
  AND dt >= DATE_FORMAT(DATE_SUB(CURRENT_DATE(), 7), 'yyyyMMdd')
  AND dt <= DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd')
```

first-pass warnings:

- `UNSUPPORTED_FIELD`: `user_uuid`
- `UNSUPPORTED_FIELD`: `dt`

repair triggered? why?

- no
- no repairable `PLAN_*` warning was produced

final Safety Gate status:

- `passed`

final warnings:

- `UNSUPPORTED_FIELD user_uuid`
- `UNSUPPORTED_FIELD dt`

literal-copy drift:

- no obvious fixed historical date/source filter drift

combo intent preserved:

- not applicable

judgment:

- `partial`

notes:

- This case remains primarily a retrieval grounding gap.
- `FU6` correctly does not force repair when the issue is not a repairable plan drift.

## 2. mx-behavior-writeback

request:

```text
帮我查询并写回 behavior
```

retrieved context summary:

- request remains under-specified for writeback

canonical field guidance:

- not applicable

sql_intent_plan summary:

- not constructed because the request is under-specified

generated SQL:

- none

Safety Gate status:

- not reached

warnings:

- none

result:

- `HTTP 422 DATA_AGENT_WRITEBACK_REQUIRES_COHORT`

judgment:

- `pass`

notes:

- `FU6` does not weaken the existing safe-refusal path.

## 3. mx-glossary-combo-writeback

request:

```text
给首贷且从未逾期用户补齐 behavior
```

retrieved context summary:

- same `mx` + `common` knowledge bundles as prior FU4/FU5 reruns
- combo writeback retrieval remained available

canonical field guidance:

- expected to stay inside FU4/FU5 guidance if generation succeeds

sql_intent_plan summary:

- expected combo writeback plan with target cohort + behavior join

first-pass SQL:

- none captured in this rerun

first-pass warnings:

- none captured in this rerun

repair triggered? why?

- not reached

final Safety Gate status:

- not reached

final warnings:

- none

result:

- `HTTP 422 SCHEMA_VALIDATION_FAILED`
- model output failed schema validation before a reviewable SQL artifact was created

literal-copy drift:

- not evaluable in this rerun because no SQL artifact was produced

combo intent preserved:

- not evaluable in this rerun because no SQL artifact was produced

judgment:

- `needs_fu7`

notes:

- This case failed twice on `2026-06-24` with upstream structured-output instability before FU6 repair could execute.
- The bounded repair harness is validated by deterministic tests, but the live combo case is still not stable enough to treat generation control as solved.

## Conclusion

Current decision after FU6:

- do **not** enter `M2B`
- keep `mx-high-risk-cohort` categorized as retrieval grounding gap
- keep `mx-behavior-writeback` as a stable refusal pass
- treat `mx-glossary-combo-writeback` as still not production-stable

Recommended next step:

- `FU7: Structured SQL Plan Contract`

Reason:

- `FU6` proves the harness can do bounded repair deterministically
- but the live combo case still does not reliably produce a repairable SQL artifact
- the remaining instability is still on the generation-control side, not retrieval quality
