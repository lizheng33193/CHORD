# M2A-RQ-FU7 Structured SQL Plan Results

## Summary

FU7 moved planning in front of SQL generation and added an internal `structured_sql_plan` gate. The key live result is that `mx-glossary-combo-writeback` no longer fails early with `SCHEMA_VALIDATION_FAILED`; it now builds a valid structured plan and reaches a reviewable SQL artifact.

## Case Results

### `mx-high-risk-cohort`

- request: `找最近 7 天高风险用户`
- structured plan:
  - `task_type=cohort_query`
  - `target_cohort_conditions=high_risk,recent_7d`
  - `source_tables=dwd_w_apply`
  - `fixed_dates_allowed=false`
  - `source_filters_allowed=false`
- plan validation: `valid=true`
- generated SQL: reviewable, no planning failure
- Safety Gate: `passed`
- warnings:
  - `UNSUPPORTED_FIELD user_uuid`
  - `UNSUPPORTED_FIELD apply_create_at`
  - `UNSUPPORTED_FIELD dt`
- repair: not attempted
- judgment: `partial`
- note: residual issue is now mainly grounding / canonical retrieval quality

### `mx-behavior-writeback`

- request: `帮我查询并写回 behavior`
- structured plan: not admitted to generation
- plan validation:
  - `valid=false`
  - `code=DATA_AGENT_WRITEBACK_REQUIRES_COHORT`
  - `stage=data_agent_sql_planning`
- generated SQL: none
- Safety Gate: not reached
- repair: not attempted
- judgment: `pass`

### `mx-glossary-combo-writeback`

- request: `给首贷且从未逾期用户补齐行为数据`
- structured plan:
  - `task_type=bucket_writeback`
  - `output_bucket=behavior`
  - `target_cohort_conditions=first_loan,never_overdue`
  - `source_tables=dwd_w_apply,dwb_b1_data_burying_point`
  - `join_keys=uid`
  - `required_fields=uid,timestamp_,eventname`
  - `fixed_dates_allowed=false`
  - `source_filters_allowed=false`
- plan validation: `valid=true`
- generated SQL: reviewable, no planning failure
- Safety Gate: `passed`
- warnings: none in this run
- repair: not attempted
- judgment: `ready_for_m2b`
- note: combo case now reaches the SQL review path and no longer copies fixed historical dates or source filters

## Decision

FU7 achieved its primary goal:

- combo behavior writeback now builds a valid structured plan
- combo live case now reaches reviewable SQL instead of failing at structured output
- under-specified writeback still stops early with the dedicated refusal code

The next stage should be `M2B Hybrid Retrieval`, with the main residual input being high-risk cohort grounding/canonical quality rather than generation-path instability.
