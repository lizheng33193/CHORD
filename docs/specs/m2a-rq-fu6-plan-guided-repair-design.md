# M2A-RQ-FU6 Plan-guided Regeneration / Repair

## Summary

`FU6` extends the `FU5` warning-only plan review by allowing exactly one bounded repair generation during `DataAgentService.create_run()` and `revise_run()`. The repair path is only used when the first-pass SQL is still reviewable and has repairable `PLAN_*` warnings. The repaired SQL must still pass through the existing Safety Gate, field grounding warnings, canonical warnings, and plan review before it enters SQL HITL.

This stage does not change public schemas, does not change `M1` / `M1.5` / `query_data`, and does not auto-execute SQL. It remains fully inside the generation side of the existing review loop.

## Boundaries

- Repair only runs for agent-generated SQL in `create_run()` and `revise_run()`.
- `edit_run()` must never auto-repair manually edited SQL.
- `approve_run()` and `execute_run()` must never trigger repair.
- `max_repair_attempts = 1`.
- Hard Safety Gate blocks for dangerous SQL, credential leakage, or other non-plan safety issues must not trigger repair.
- No DB migration and no new public API fields.
- Repair traces live only inside `safety_result_json`.

## Repair Trigger Policy

The first pass may trigger a second generation only when both are true:

1. The first-pass SQL is reviewable.
2. The first-pass warnings contain at least one repairable `PLAN_*` warning.

Repairable warnings in v1:

- `PLAN_DATE_DRIFT`
- `PLAN_SOURCE_FILTER_DRIFT`
- `PLAN_REQUIRED_FIELD_MISSING`
- `PLAN_BROAD_SCAN_RISK`
- `PLAN_FORBIDDEN_PATTERN`

Non-triggering warnings in v1:

- `NON_CANONICAL_FIELD`
- `PLAN_CANONICAL_FIELD_DRIFT`

Canonical drift can still be included as a low-priority repair instruction, but it must not be the sole reason to trigger repair.

## Repair Instruction

`app/data_agent/repair.py` builds a deterministic instruction string from:

- current SQL
- repairable warning categories and short evidence
- `sql_intent_plan_summary`
- current request text
- optional reviewer feedback

The instruction must:

- preserve the current request intent
- preserve `output_bucket`
- preserve target cohort + behavior join intent for combo writeback
- forbid fixed historical dates unless explicitly requested
- forbid inherited source/channel filters unless explicitly requested
- forbid unresolved placeholders
- forbid broad behavior scans
- require `required_fields` when `output_bucket=behavior`

The instruction must not include raw prompt text, raw model output, or chain-of-thought.

## Success and Failure

Repair success requires more than a lower warning count. The repaired SQL must:

1. be non-empty
2. not regress Safety Gate severity
3. reduce or remove the repair-triggering `PLAN_*` warnings
4. avoid introducing more severe warnings
5. preserve request intent
6. preserve `output_bucket`
7. preserve target cohort markers
8. preserve required behavior fields when applicable
9. preserve combo intent

Failure reasons use stable categories:

- `generation_error`
- `empty_sql`
- `safety_regression`
- `repairable_warnings_not_reduced`
- `introduced_more_severe_warning`

If repair fails, the original first-pass SQL remains the current reviewable SQL version.

## Trace Shape

Repair metadata is stored in `safety_result["repair"]` only:

```json
{
  "attempted": true,
  "applied": true,
  "attempt_count": 1,
  "trigger_categories": ["PLAN_DATE_DRIFT"],
  "original_sql_hash": "sha256...",
  "original_warning_categories": ["PLAN_DATE_DRIFT", "UNSUPPORTED_FIELD"],
  "final_warning_categories": ["UNSUPPORTED_FIELD"],
  "selection_reason": "repair_removed_trigger_warnings"
}
```

or

```json
{
  "attempted": true,
  "applied": false,
  "attempt_count": 1,
  "trigger_categories": ["PLAN_BROAD_SCAN_RISK"],
  "original_sql_hash": "sha256...",
  "original_warning_categories": ["PLAN_BROAD_SCAN_RISK"],
  "final_warning_categories": ["PLAN_BROAD_SCAN_RISK", "PLAN_REQUIRED_FIELD_MISSING"],
  "failure_reason": "introduced_more_severe_warning"
}
```

## Verification Focus

`FU6` verification must prove:

- repair triggers only once
- hard Safety Gate blocked SQL does not repair
- manual edit does not repair
- revise keeps reviewer feedback higher priority than repair instruction
- repaired SQL is adopted only when it actually improves plan adherence
- repair failure falls back to the original SQL
