# M2A-RQ-FU6 Plan-guided Regeneration / Repair

## Summary

This plan adds one bounded repair attempt for agent-generated SQL after first-pass plan review. The implementation must stay inside `DataAgentService.create_run()` and `revise_run()`, keep SQL HITL unchanged, and store all repair traces in existing `safety_result_json`.

## Implementation

1. Add `app/data_agent/repair.py`.
   - Build a deterministic repair instruction from first-pass SQL, repairable `PLAN_*` warnings, `sql_intent_plan_summary`, request text, and optional reviewer feedback.
   - Keep the output summarized and compact.

2. Extend `app/data_agent/service.py`.
   - Factor first-pass post-processing into a reusable helper that runs:
     - Safety Gate
     - unsupported / canonical warnings
     - plan review
   - Detect repairable warnings from the first-pass result.
   - Skip repair for:
     - hard Safety Gate blocked SQL
     - non-agent SQL
     - manual edit flow
     - zero repairable warnings
   - On repair:
     - call `_generate_sql_response(...)` once more with repair instruction
     - re-run the same review pipeline on the repaired candidate
     - adopt repaired SQL only if it satisfies FU6 success rules
     - otherwise keep the original SQL

3. Record repair traces in `safety_result["repair"]`.
   - `attempted`
   - `applied`
   - `attempt_count`
   - `trigger_categories`
   - `original_sql_hash`
   - `original_warning_categories`
   - `final_warning_categories`
   - `selection_reason` or `failure_reason`

4. Update docs/state.
   - `PLANNING.md`
   - `TASK.md`
   - `docs/reviews/m2a-rq-fu6-plan-guided-repair-results.md`

## Tests

1. Add `tests/data_agent/test_repair.py`.
   - repair instruction covers date drift
   - repair instruction covers source drift
   - repair instruction covers required-field missing
   - repair instruction covers broad scan risk
   - canonical-only warnings do not trigger repair
   - combo intent is preserved in the instruction

2. Extend `tests/data_agent/test_api.py`.
   - create flow repair success
   - create flow repair failure fallback
   - revise flow repair success
   - hard Safety Gate blocked SQL does not repair
   - combo intent loss causes fallback
   - manual edit remains manual-only

3. Run regression commands:
   - `python -m compileall -q app data_acquisition_agent tests`
   - `pytest tests/data_agent/test_api.py tests/data_agent/test_plan_review.py tests/data_agent/test_repair.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py -q`
   - `pytest tests/data_knowledge/test_data_knowledge_retriever.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_orchestrator.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py tests/data_agent/test_plan_review.py tests/data_agent/test_repair.py -q`

## Rerun

After code + tests pass, rerun:

- `mx-high-risk-cohort`
- `mx-behavior-writeback`
- `mx-glossary-combo-writeback`

Record:

- first-pass SQL
- first-pass warnings
- repair triggered or skipped
- repaired SQL or failure reason
- final warnings
- judgment = `pass | partial | fail | ready_for_m2b | needs_fu7`
