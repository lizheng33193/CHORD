# M2B-1 Structured Knowledge Extraction Results

## Summary

`M2B-1` completed a first-batch, golden-set-driven extraction pass over the legacy raw knowledge sources under `docs/knowledge-base/`.

This phase produced sanitized candidate assets only. Nothing here has been promoted into the runtime knowledge store, prompt assembly, or deterministic retriever.

## Extracted Asset Counts

- `catalog_table`: 11
- `catalog_field`: 65
- `glossary_term`: 23
- `business_rule`: 6
- `cohort_definition`: 6
- `sql_example_pattern`: 4
- `sql_error_case`: 9
- `canonical_field_policy`: 4

Total candidate assets: 128

## Coverage Outcome

- valid raw source files tracked in `asset_source_map.yaml`: 26
- priority golden cases with `partial` or better first-batch coverage: 14
- coverage report:
  - `docs/reviews/m2b-1-golden-set-coverage.md`
  - `data_knowledge_eval/m2b/extracted_assets/extraction_coverage.yaml`

High-value cases now covered or partially covered include:

- `mx-high-risk-cohort`
- `mx-recent-7d-risk-users`
- `mx-first-loan-never-overdue`
- `mx-mob1-settled-7d-churn`
- `mx-behavior-writeback`
- `mx-glossary-combo-writeback`
- `mx-app-profile-query`
- `mx-credit-profile-query`
- `th-asset-snapshot-query`
- `th-risk-apply-query`
- `th-ask-loan-risk-query`
- `th-third-party-risk-query`
- `dws-renewal-loan-segment-query`
- `dws-fox-boc-behavior-query`

## What Was Intentionally Deferred

This phase did not try to fully extract every legacy file.

Deferred or inventory-only sources remain recorded in `asset_source_map.yaml`, including:

- broad Thailand dictionary index docs whose scope exceeds the first-batch cases
- Thailand user-domain breadth docs not required by the current priority golden set
- `gem prompt.md`, which remains design reference only and never becomes runtime grounding

## Known Gaps

- `risk_level` remains a visible grounding gap in the Mexico high-risk cases.
- Philippines-specific table grounding is still partial and not part of the current priority extraction target.
- `canonical_field_policy` entries are intentionally conservative and still carry `needs_human_review` where business-time or identity semantics have historical drift.

## Runtime Boundary Check

This phase did not:

- modify runtime retrieval files
- modify Data Agent runtime behavior
- import seeds into the runtime store
- build embeddings, vector indices, or hybrid retrieval logic
- commit raw docs from `docs/knowledge-base/`

## Next Step

`M2B-2: Seed Import / Knowledge Store Update`

That phase is the first point where these candidate assets may be reviewed for promotion into formal seeds and runtime-facing storage.
