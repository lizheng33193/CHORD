# M2B-2.2 V2 vs V3 Deterministic Baseline Comparison

This comparison measures targeted deterministic grounding changes between `m2b_legacy_v2` and `m2b_legacy_v3`.

- left_seed_namespace: `m2b_legacy_v2`
- right_seed_namespace: `m2b_legacy_v3`

| case_id | v2_judgment | v3_judgment | matched_expected_delta | missing_expected_delta | unexpected_delta | improvement_summary | regression_risk |
|---|---|---|---:|---:|---:|---|---|
| dws-fox-boc-behavior-query | partial | pass | 2 | -2 | 0 | improved | no |
| dws-renewal-loan-segment-query | partial | pass | 1 | -1 | 0 | improved | no |
| mx-app-profile-query | partial | partial | 0 | 0 | 0 | no_material_change | no |
| mx-behavior-writeback | pass | pass | 0 | 0 | 0 | no_material_change | no |
| mx-credit-profile-query | pass | pass | 0 | 0 | 0 | no_material_change | no |
| mx-first-loan-never-overdue | partial | pass | 1 | -1 | 0 | improved | no |
| mx-glossary-combo-writeback | pass | pass | 0 | 0 | 0 | no_material_change | no |
| mx-high-risk-cohort | pass | pass | 0 | 0 | 0 | no_material_change | no |
| mx-mob1-settled-7d-churn | partial | partial | 5 | -5 | 0 | improved | no |
| mx-no-apply-cohort | partial | pass | 2 | -2 | 0 | improved | no |
| mx-no-withdraw-cohort | partial | partial | 1 | -1 | 0 | improved | no |
| mx-recent-7d-risk-users | pass | pass | 0 | 0 | 0 | no_material_change | no |
| mx-withdraw-cohort | partial | pass | 3 | -3 | 0 | improved | no |
| ph-first-loan-never-overdue | partial | partial | 0 | 0 | 0 | no_material_change | no |
| ph-withdraw-uuid-negative | partial | partial | 0 | 0 | 0 | no_material_change | no |
| th-ask-loan-risk-query | partial | pass | 1 | -1 | 0 | improved | no |
| th-asset-snapshot-query | partial | partial | 0 | 0 | 0 | no_material_change | no |
| th-risk-apply-query | partial | partial | 0 | 0 | 0 | no_material_change | no |
| th-third-party-risk-query | partial | partial | 0 | 0 | 0 | no_material_change | no |
