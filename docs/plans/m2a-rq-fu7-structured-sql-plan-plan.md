# M2A-RQ-FU7 Structured SQL Plan Contract Plan

## Summary

Implement a deterministic internal SQL plan layer in front of generation. The work stays inside the Data Agent harness and keeps SQL HITL unchanged.

## Steps

1. Add `app/data_agent/sql_plan.py` with deterministic plan models, builder, and validator.
2. Extend `PromptContextAssembler` to accept a plain-dict structured plan and render `structured_sql_plan_contract`.
3. Update `DataAgentService._build_generation_context()` to:
   - retrieve context
   - build base snapshot
   - build structured plan
   - validate structured plan
   - raise stable `422` planning errors on invalid plans
   - write valid plan + validation into `retrieval_snapshot_json`
4. Update prompt priority rules so structured plan overrides historical examples.
5. Update plan review and repair helpers to prefer structured plan with legacy fallback.
6. Add and update tests for:
   - deterministic plan build / validation
   - planning-stage `422`
   - snapshot persistence
   - prompt rendering and priority rules
7. Run targeted regression and live rerun the three FU cases.

## Acceptance

- valid combo behavior writeback produces a structured plan and reaches SQL generation
- under-specified writeback returns `DATA_AGENT_WRITEBACK_REQUIRES_COHORT` before generation
- invalid behavior writeback returns `DATA_AGENT_SQL_PLAN_INVALID` before generation
- revise invalid plan does not mutate current SQL state
- prompt, plan review, and repair all use structured plan as the primary internal contract
