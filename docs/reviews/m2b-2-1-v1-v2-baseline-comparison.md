# M2B-2.1 V1 vs V2 Deterministic Baseline Comparison

This comparison measures deterministic grounding changes between `m2b_legacy_v1` and `m2b_legacy_v2`.

- left_seed_namespace: `m2b_legacy_v1`
- right_seed_namespace: `m2b_legacy_v2`

| case_id | v1_judgment | v2_judgment | matched_expected_delta | missing_expected_delta | unexpected_delta | improvement_summary | regression_risk |
|---|---|---|---:|---:|---:|---|---|
| dws-fox-boc-behavior-query | partial | partial | 0 | 0 | 0 | no_material_change | no |
| dws-renewal-loan-segment-query | partial | partial | 1 | -1 | 0 | improved | no |
| mx-app-profile-query | partial | partial | 2 | -2 | 0 | improved | no |
| mx-behavior-writeback | partial | pass | 1 | -1 | 0 | improved | no |
| mx-credit-profile-query | fail | pass | 5 | -5 | 0 | improved | no |
| mx-first-loan-never-overdue | partial | partial | 1 | -1 | 0 | improved | no |
| mx-glossary-combo-writeback | partial | pass | 2 | -2 | 0 | improved | no |
| mx-high-risk-cohort | partial | pass | 2 | -2 | 0 | improved | no |
| mx-mob1-settled-7d-churn | partial | partial | 1 | -1 | 0 | improved | no |
| mx-no-apply-cohort | partial | partial | 0 | 0 | 0 | no_material_change | no |
| mx-no-withdraw-cohort | partial | partial | 0 | 0 | 0 | no_material_change | no |
| mx-recent-7d-risk-users | partial | pass | 1 | -1 | 0 | improved | no |
| mx-withdraw-cohort | partial | partial | -1 | 1 | 0 | regressed | yes |
| ph-first-loan-never-overdue | partial | partial | 1 | -1 | 0 | improved | no |
| ph-withdraw-uuid-negative | partial | partial | 0 | 0 | 0 | no_material_change | no |
| th-ask-loan-risk-query | partial | partial | 1 | -1 | 0 | improved | no |
| th-asset-snapshot-query | partial | partial | 0 | 0 | 0 | no_material_change | no |
| th-risk-apply-query | partial | partial | 0 | 0 | 0 | no_material_change | no |
| th-third-party-risk-query | partial | partial | 0 | 0 | 0 | no_material_change | no |
