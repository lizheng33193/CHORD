# M2B-2.2 Missing Grounding Analysis

## Scope

- 分析输入：
  - `data_knowledge_eval/m2b/baseline_results.m2b_legacy_v2.deterministic.json`
  - `data_knowledge_eval/m2b/deterministic_coverage.m2b_legacy_v2.yaml`
- 本文档先于 `m2b_legacy_v3` patch 设计，用来约束每个 v3 enrichment 都必须有明确 gap 依据。

## Fair Comparison Rule

- 如果本阶段修改 baseline runner 的 matcher / dedupe / normalization / comparison，则必须用同一版 runner 复跑 `v2` 和 `v3`。
- 因此后续 `v2/v3` 对比以 `rerun_v2_baseline` 为准，而不是引用 M2B-2.1 的历史 v2 结果。

## V2 Rerun Baseline Snapshot

- overall: `5 pass / 14 partial / 0 fail`
- 重点 partial case：
  - `mx-first-loan-never-overdue`
  - `mx-mob1-settled-7d-churn`
  - `mx-no-apply-cohort`
  - `mx-no-withdraw-cohort`
  - `mx-withdraw-cohort`
  - `dws-fox-boc-behavior-query`
  - `dws-renewal-loan-segment-query`
  - `th-ask-loan-risk-query`

## Gap To Patch Mapping

- `mx-first-loan-never-overdue`
  - missing: `field:withdraw_uuid`
  - v3 patch:
    - strengthen `withdraw_uuid` aliases/business meaning
    - connect `first_loan` and `never_overdue` glossary to `withdraw_uuid`, `asset_grant_at`, `asset_overdue_days`
- `mx-mob1-settled-7d-churn`
  - missing: `field:withdraw_uuid`, `field:asset_finish_at`, `field:asset_grant_at`, `glossary:mob1`, `glossary:fully_settled`, `glossary:seven_day_no_reborrow_churn`
  - v3 patch:
    - strengthen `mob1` definition/synonyms/mapped_fields/suggested_filters
    - strengthen `asset_finish_at`, `asset_grant_at`, `withdraw_uuid`
    - keep `mob1` as composite lifecycle semantic, not just `first_loan`
- `mx-withdraw-cohort`
  - missing: `field:withdraw_uuid`, `field:asset_grant_at`, `glossary:successful_withdraw`
  - v3 patch:
    - strengthen `successful_withdraw` glossary
    - strengthen withdraw / grant-time field wording
- `mx-no-apply-cohort`
  - missing: `glossary:no_apply`, `field:user_uuid`
  - v3 patch:
    - expand `no_apply` glossary and `user_uuid` business meaning
- `dws-renewal-loan-segment-query`
  - missing: `glossary:settled_over_3m`
  - v3 patch:
    - add DWS lifecycle glossary mapping to `dws_user_renewal_loan_seg_d`
- `dws-fox-boc-behavior-query`
  - missing: `glossary:collection_behavior`, `glossary:contact_outcome`
  - v3 patch:
    - add behavior/contact glossary mappings to `dws_fox_boc_behavior_log_d`
- `th-ask-loan-risk-query`
  - missing: Thai ask-loan field grounding tail
  - v3 patch:
    - preserve Thai runtime visibility; avoid country-scope regression from MX-only glossary changes

## Guardrails Applied To V3

- `uid` and `user_uuid` remain non-equivalent globally.
- `dt` remains a partition field, not a business-time substitute.
- matcher may normalize and compare, but may not add synthetic retrieved assets.
- `business_rule / cohort_definition / canonical_field_policy` remain manifest-only and are not promoted into runtime seed family.
