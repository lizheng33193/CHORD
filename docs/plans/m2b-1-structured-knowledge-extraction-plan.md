# M2B-1 Structured Knowledge Extraction Plan

## Goal

Deliver the first `M2B-1` extraction batch without touching runtime retrieval or Data Agent runtime behavior.

## Boundaries

This phase does:

- extract first-batch sanitized candidate assets from `docs/knowledge-base/`
- keep extraction golden-set-driven and high-confidence only
- generate an asset validator and coverage report
- record extracted, partial, deferred, and inventory-only source status

This phase does not:

- import seeds into the runtime knowledge store
- modify `app/data_knowledge/retriever.py`
- modify `app/data_agent/service.py`
- modify `app/data_agent/sql_plan.py`
- modify SQL HITL, approve, execute, or orchestrator bridge
- build embeddings or vector indices
- commit raw legacy documents
- inject extracted assets into runtime prompt assembly

## Implementation Steps

1. Create `data_knowledge_eval/m2b/extracted_assets/` as the candidate-asset staging directory.
2. Extract first-batch `catalog_table`, `catalog_field`, `glossary_term`, `business_rule`, `cohort_definition`, `sql_example_pattern`, `sql_error_case`, and `canonical_field_policy` assets.
3. Keep `few.md` and `all_examples .md` limited to sanitized patterns and anti-patterns only.
4. Add `asset_source_map.yaml` with `extracted`, `partial`, `deferred`, `inventory_only`, and `future_profile_skill_only` statuses for every valid raw source file.
5. Add `scripts/validate_m2b_extracted_assets.py` to enforce schema, uniqueness, sanitization, dirty-pattern rejection, and golden-set coverage generation.
6. Add `tests/test_m2b_extracted_assets.py` to lock validator behavior and committed asset integrity.
7. Generate `docs/reviews/m2b-1-golden-set-coverage.md` and `data_knowledge_eval/m2b/extracted_assets/extraction_coverage.yaml`.
8. Update `PLANNING.md` and `TASK.md` to mark `M2B-1` as the active post-`M2B-0` phase.

## Verification

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `python scripts/validate_m2b_extracted_assets.py --assets-dir data_knowledge_eval/m2b/extracted_assets --golden-set data_knowledge_eval/m2b/golden_set.yaml --coverage-output docs/reviews/m2b-1-golden-set-coverage.md --coverage-yaml data_knowledge_eval/m2b/extracted_assets/extraction_coverage.yaml`
- `pytest tests/test_m2b_inventory_tools.py tests/test_m2b_extracted_assets.py tests/data_knowledge/test_data_knowledge_retriever.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py tests/data_agent/test_sql_plan.py tests/data_agent/test_plan_review.py tests/data_agent/test_repair.py -q`
- `git diff --check`
- `git ls-files docs/knowledge-base`
- `git diff --name-only main...HEAD`

## Exit Criteria

- candidate extracted assets exist with stable YAML schema
- `asset_id` values are globally unique
- no sensitive literals or dirty SQL templates survive validation
- every valid raw source file is represented in `asset_source_map.yaml`
- at least 8 priority golden cases reach `partial` or better first-batch coverage
- raw docs remain untracked and runtime retrieval files remain unchanged
