# M2B-4 Vector Index Prototype Results

This is a fake/local vector prototype, not a real embedding benchmark.

## Summary

- run_mode: `vector_prototype`
- vectorizer_name: `local_hashing_bow_v1`
- source_namespace: `m2b_legacy_v3`
- top_k: `10`
- pass: `2`
- partial: `17`
- fail: `0`
- vector_only_cases: `3`

## Vector-only Signals

- `mx-no-withdraw-cohort` -> glossary:no_withdraw (`hybrid_potential=high`)
- `mx-app-profile-query` -> field:year_day (`hybrid_potential=high`)
- `th-asset-snapshot-query` -> field:finish_time, field:user_uuid, table:hive.dwt.dwt_asset_info_base_snap (`hybrid_potential=high`)

## Interpretation

- This stage only validates whether M2B-3 embedding records can support an offline vector retrieval chain.
- The local vectorizer is deterministic and reproducible, but it does not represent the ceiling of a real embedding model.
- The current vector-only baseline should not replace deterministic retrieval because its pass count remains lower.
- Recommended next step: `M2B-5 Hybrid Retrieval Fusion`

