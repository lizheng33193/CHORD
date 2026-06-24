# M2A-RQ-FU7 Structured SQL Plan Contract

## Summary

FU7 moves SQL control earlier in the Data Agent harness. Before SQL generation, the service now builds a deterministic internal `structured_sql_plan`, validates it, and only then allows SQL generation to continue. Invalid plans return stable `422` planning errors and do not create or mutate SQL review artifacts.

## Goals

- Add a machine-checkable internal SQL planning contract before generation.
- Keep `bucket_writeback` behavior strict, especially `output_bucket=behavior`.
- Preserve the existing under-specified writeback refusal code: `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`.
- Keep all plan data internal to `retrieval_snapshot_json`.

## Non-Goals

- No public API schema change.
- No database migration or new tables.
- No `M1` / `M1.5` / `query_data` / `orchestrator.py` changes.
- No retriever scoring, seed, embedding, vector DB, or rerank changes.
- No transition to `M2B`.

## Contract

`structured_sql_plan` is an internal dict with:

- `schema_version`
- `task_type`
- `output_bucket`
- `country`
- `target_cohort_conditions`
- `source_tables`
- `join_keys`
- `required_fields`
- `forbidden_patterns`
- `time_constraints`
- `source_filters_allowed`
- `fixed_dates_allowed`
- `uid_boundary_required`

`structured_sql_plan_validation` is an internal dict with:

- `valid`
- `code`
- `reason`
- `missing`
- `warnings`

## Validation Rules

- `bucket_writeback` requires `output_bucket`.
- under-specified writeback remains `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`.
- `behavior` writeback requires a grounded behavior table.
- `behavior` writeback requires grounded `uid`, `timestamp_`, and `eventname`.
- combo behavior writeback must keep both cohort and behavior tables.
- `cohort_query` stays conservative and does not hard fail on ordinary grounding gaps.

## Integration

- `DataAgentService` builds and validates the plan after retrieval and before generation.
- Valid plans are stored in `retrieval_snapshot_json`.
- `PromptContextAssembler` renders `# === structured_sql_plan_contract ===` from a plain dict.
- `plan_review.py` and `repair.py` prefer `structured_sql_plan`, then fall back to `sql_intent_plan_summary`.
