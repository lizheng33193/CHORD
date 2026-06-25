# M2B-2 Seed Promotion Review

This review records the M2B-2 promotion decisions for M2B-1 candidate assets.

## Summary

- source_namespace: `m2b_legacy_v3`
- total candidate assets: `128`
- promote_now: `108`
- defer_needs_review: `11`
- eval_only: `9`
- future_profile_skill_only: `0`
- rejected: `0`
- import_now: `96`
- manifest_only: `12`
- not_imported: `20`

## Runtime Seed Families

- catalog_tables: `10`
- catalog_fields: `61`
- glossary_terms: `28`
- sql_examples: `2`
- sql_error_cases: `0`

## Asset-Type Decisions

- `business_rule`: promote_now=6, defer_needs_review=0, eval_only=0, import_now=0, manifest_only=6, not_imported=0
- `canonical_field_policy`: promote_now=0, defer_needs_review=4, eval_only=0, import_now=0, manifest_only=0, not_imported=4
- `catalog_field`: promote_now=61, defer_needs_review=4, eval_only=0, import_now=61, manifest_only=0, not_imported=4
- `catalog_table`: promote_now=10, defer_needs_review=1, eval_only=0, import_now=10, manifest_only=0, not_imported=1
- `cohort_definition`: promote_now=6, defer_needs_review=0, eval_only=0, import_now=0, manifest_only=6, not_imported=0
- `glossary_term`: promote_now=23, defer_needs_review=0, eval_only=0, import_now=23, manifest_only=0, not_imported=0
- `sql_error_case`: promote_now=0, defer_needs_review=0, eval_only=9, import_now=0, manifest_only=0, not_imported=9
- `sql_example_pattern`: promote_now=2, defer_needs_review=2, eval_only=0, import_now=2, manifest_only=0, not_imported=2

## Notes

- Pattern examples are non-executable guidance, not SQL candidates.
- Canonical policies marked `needs_human_review` stay out of runtime seed import.
- Business rules and cohort definitions remain manifest-only in M2B-2 because the current runtime seed schema does not support them directly.
- Eval-only error cases remain outside the runtime deterministic retriever unless a later phase adds a safe import shape.

