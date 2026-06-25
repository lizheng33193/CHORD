# M2B-2.1 Deterministic Grounding Results

This is a diagnostic baseline for deterministic Data Knowledge retrieval only.

## Summary

- run_mode: `deterministic`
- retriever: `DataKnowledgeRetriever`
- seed_patch: `data_knowledge_seed/m2b/m2b_legacy_v2.yaml`
- pass: `3`
- partial: `16`
- fail: `0`

## Interpretation

- This baseline does not use embeddings, vector retrieval, hybrid retrieval, SQL generation, or SQL execution.
- Missing business rules, cohort definitions, or canonical policies may be expected when they are manifest-only in M2B-2.1.
- If deterministic recall remains weak after this seed patch, the next step should be `M2B-2.2` rather than jumping directly to vector retrieval.
- Recommended next step: `M2B-2.2`

## Top Missing Expectations

- `field:withdraw_uuid` missing in `4` cases
- `field:user_uuid` missing in `3` cases
- `field:overdue_days` missing in `2` cases
- `field:asset_grant_at` missing in `2` cases
- `example:behavior_writeback_pattern` missing in `2` cases
- `field:asset_finish_at` missing in `1` cases
- `glossary:mob1` missing in `1` cases
- `glossary:fully_settled` missing in `1` cases
- `glossary:seven_day_no_reborrow_churn` missing in `1` cases
- `example:mob1_churn_pattern` missing in `1` cases
- `table:hive.dwd.dwd_w_user` missing in `1` cases
- `glossary:no_apply` missing in `1` cases
