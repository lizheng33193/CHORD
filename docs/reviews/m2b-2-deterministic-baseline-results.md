# M2B-2 Deterministic Baseline Results

This is a diagnostic baseline for deterministic Data Knowledge retrieval only.

## Summary

- run_mode: `deterministic`
- retriever: `DataKnowledgeRetriever`
- seed_patch: `data_knowledge_seed/m2b/m2b_legacy_v1.yaml`
- pass: `0`
- partial: `18`
- fail: `1`

## Interpretation

- This baseline does not use embeddings, vector retrieval, hybrid retrieval, SQL generation, or SQL execution.
- Missing business rules, cohort definitions, or canonical policies may be expected when they are manifest-only in M2B-2.
- If deterministic recall remains weak after this seed patch, the next step should be `M2B-2.1` rather than jumping directly to vector retrieval.
- Recommended next step: `M2B-2.1`

## Top Missing Expectations

- `field:user_uuid` missing in `6` cases
- `glossary:recent_7d` missing in `4` cases
- `field:withdraw_uuid` missing in `4` cases
- `glossary:high_risk` missing in `3` cases
- `field:overdue_days` missing in `2` cases
- `glossary:first_loan` missing in `2` cases
- `field:apply_create_at` missing in `2` cases
- `field:asset_grant_at` missing in `2` cases
- `example:behavior_writeback_pattern` missing in `2` cases
- `field:dt` missing in `1` cases
- `field:asset_finish_at` missing in `1` cases
- `glossary:fully_settled` missing in `1` cases
