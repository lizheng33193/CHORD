# M2B-2.2 Targeted Grounding Results

This is a diagnostic baseline for deterministic Data Knowledge retrieval only.

## Summary

- run_mode: `deterministic`
- retriever: `DataKnowledgeRetriever`
- seed_patch: `data_knowledge_seed/m2b/m2b_legacy_v3.yaml`
- pass: `11`
- partial: `8`
- fail: `0`

## Interpretation

- This baseline does not use embeddings, vector retrieval, hybrid retrieval, SQL generation, or SQL execution.
- Missing business rules, cohort definitions, or canonical policies may be expected when they are manifest-only in M2B-2.2.
- If deterministic recall remains weak after this seed patch, the next step should be `M2B-3` rather than jumping directly to vector retrieval.
- Recommended next step: `M2B-3`

## Top Missing Expectations

- `field:user_uuid` missing in `3` cases
- `glossary:first_loan` missing in `1` cases
- `glossary:no_withdraw` missing in `1` cases
- `field:category_name` missing in `1` cases
- `field:year_day` missing in `1` cases
- `table:hive.dwt.dwt_asset_info_base_snap` missing in `1` cases
- `field:finish_time` missing in `1` cases
- `field:ask_loan_uuid` missing in `1` cases
- `field:user_loan_label` missing in `1` cases
- `table:hive.third_party.thailand_sources` missing in `1` cases
- `field:supplier_name` missing in `1` cases
- `field:product_name` missing in `1` cases
