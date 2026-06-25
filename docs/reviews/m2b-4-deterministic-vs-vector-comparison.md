# M2B-4 Deterministic vs Vector Comparison

This is a fake/local vector prototype comparison, not a formal embedding benchmark.

- deterministic_baseline: `data_knowledge_eval/m2b/baseline_results.m2b_legacy_v3.deterministic.json`
- vector_results: `data_knowledge_eval/m2b/vector_results.m2b_legacy_v3.json`

| case_id | deterministic_judgment | vector_judgment | deterministic_only_matches | vector_only_matches | shared_matches | hybrid_potential | notes |
|---|---|---|---|---|---|---|---|
| mx-high-risk-cohort | pass | partial | field:risk_level, glossary:recent_7d, table:hive.dwd.dwd_w_apply | - | field:apply_time, field:dt, field:user_uuid, glossary:high_risk | medium | deterministic matched: 7; vector matched: 4 |
| mx-recent-7d-risk-users | pass | partial | field:risk_level, field:user_uuid, glossary:recent_7d, table:hive.dwd.dwd_w_apply | - | field:apply_time, glossary:high_risk | medium | deterministic matched: 6; vector matched: 2 |
| mx-first-loan-never-overdue | pass | partial | field:apply_time, table:hive.dwd.dwd_w_apply | - | field:overdue_days, field:user_uuid, field:withdraw_uuid, glossary:first_loan, glossary:never_overdue | medium | deterministic matched: 7; vector matched: 5 |
| mx-mob1-settled-7d-churn | partial | partial | field:apply_create_at, field:asset_grant_at, field:withdraw_uuid, glossary:fully_settled, table:hive.dwd.dwd_w_apply | - | example:mob1_churn_pattern, field:asset_finish_at, field:user_uuid, glossary:mob1, glossary:seven_day_no_reborrow_churn | medium | deterministic matched: 10; vector matched: 5 |
| mx-behavior-writeback | pass | partial | glossary:uid_cohort_required | - | example:behavior_writeback_pattern, field:eventname, field:timestamp_, field:uid, glossary:writeback_behavior, table:hive.dwb.dwb_b1_data_burying_point | medium | deterministic matched: 7; vector matched: 6 |
| mx-glossary-combo-writeback | pass | partial | field:eventname, field:risk_level, field:timestamp_, glossary:recent_7d, table:hive.dwd.dwd_w_apply | - | example:behavior_writeback_pattern, field:apply_time, field:uid, field:user_uuid, glossary:high_risk, glossary:writeback_behavior, table:hive.dwb.dwb_b1_data_burying_point | medium | deterministic matched: 12; vector matched: 7 |
| mx-no-apply-cohort | pass | partial | field:apply_time, table:hive.dwd.dwd_w_apply | - | field:user_uuid, glossary:no_apply, glossary:recent_30d, table:hive.dwd.dwd_w_user | medium | deterministic matched: 6; vector matched: 4 |
| mx-no-withdraw-cohort | partial | partial | field:user_uuid, table:hive.dwd.dwd_w_apply | glossary:no_withdraw | field:apply_time, field:withdraw_uuid | high | deterministic matched: 4; vector matched: 3 |
| mx-withdraw-cohort | pass | partial | field:asset_grant_at, field:withdraw_uuid, glossary:recent_7d, table:hive.dwd.dwd_w_apply | - | field:user_uuid, glossary:successful_withdraw | medium | deterministic matched: 6; vector matched: 2 |
| mx-app-profile-query | partial | partial | field:app_package | field:year_day | glossary:app_profile, table:hive.ods.ods_f_market_app_categories | high | deterministic matched: 3; vector matched: 3 |
| mx-credit-profile-query | pass | partial | table:hive.dwb.dwb_r_apply | - | field:apply_id, field:apply_status, field:user_uuid, glossary:credit_profile | medium | deterministic matched: 5; vector matched: 4 |
| ph-first-loan-never-overdue | partial | partial | field:loan_count, field:overdue_days, table:ph_apply_orders | - | glossary:first_loan, glossary:never_overdue | medium | deterministic matched: 5; vector matched: 2 |
| ph-withdraw-uuid-negative | partial | partial | field:loan_count, table:ph_apply_orders | - | glossary:never_overdue | medium | deterministic matched: 3; vector matched: 1 |
| th-asset-snapshot-query | partial | pass | - | field:finish_time, field:user_uuid, table:hive.dwt.dwt_asset_info_base_snap | field:asset_id, glossary:asset_snapshot | high | deterministic matched: 2; vector matched: 5 |
| th-risk-apply-query | partial | partial | - | - | field:apply_uuid, glossary:risk_apply, table:hive.dwt.dwt_rsk_apply_info_base_d | medium | deterministic matched: 3; vector matched: 3 |
| th-ask-loan-risk-query | pass | partial | field:apply_create_at, field:user_uuid | - | field:ask_loan_uuid, glossary:ask_loan_risk, table:hive.dwt.dwt_rsk_ask_loan_info_base_d | medium | deterministic matched: 5; vector matched: 3 |
| th-third-party-risk-query | partial | partial | - | - | glossary:credit_report, glossary:third_party_risk | medium | deterministic matched: 2; vector matched: 2 |
| dws-renewal-loan-segment-query | pass | partial | glossary:mob1 | - | field:cur_loan_cnt, field:last_finish_time, field:mob_code, field:user_uuid, glossary:settled_over_3m, table:dws.dws_user_renewal_loan_seg_d | medium | deterministic matched: 7; vector matched: 6 |
| dws-fox-boc-behavior-query | pass | pass | - | - | field:behavior_status_name, field:behavior_time, field:behavior_type, field:debtor_id, glossary:collection_behavior, glossary:contact_outcome, table:dws.dws_fox_boc_behavior_log_d | low | deterministic matched: 7; vector matched: 7 |
