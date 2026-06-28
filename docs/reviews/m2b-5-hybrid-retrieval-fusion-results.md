# M2B-5 Hybrid Retrieval Fusion Results

This stage validates offline hybrid fusion only. It does not change runtime retrieval or Data Agent behavior.

## Summary

- fusion_strategy: `primary_merge_v1`
- source_namespace: `m2b_legacy_v3`
- pass: `13`
- partial: `6`
- fail: `0`
- improved_cases_vs_deterministic: `3`

## Interpretation

- deterministic remains the primary retrieval source in `primary_merge_v1`.
- vector supplements are accepted only through conservative rank, threshold, and cap guards.
- fusion selection does not read golden expected/missing labels; golden signals are only used after fusion for evaluation.

## Cases With Hybrid Gains

- `mx-no-withdraw-cohort` -> glossary:no_withdraw
- `mx-app-profile-query` -> field:year_day
- `th-asset-snapshot-query` -> field:finish_time, field:user_uuid, table:hive.dwt.dwt_asset_info_base_snap
