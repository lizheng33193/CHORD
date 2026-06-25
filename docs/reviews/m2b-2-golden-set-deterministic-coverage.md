# M2B-2 Golden Set Deterministic Coverage

| case_id | judgment | matched_expected | missing_expected | notes |
|---|---|---|---|---|
| mx-high-risk-cohort | partial | table:hive.dwd.dwd_w_apply, field:user_uuid, field:risk_level, field:apply_time | field:dt, glossary:high_risk, glossary:recent_7d | not_runtime_imported_in_m2b_2:cohort.mx.high_risk_recent_7d; not_runtime_imported_in_m2b_2:canonical.mx.apply_business_time |
| mx-recent-7d-risk-users | partial | table:hive.dwd.dwd_w_apply, field:user_uuid, field:risk_level, field:apply_time | glossary:high_risk, glossary:recent_7d | - |
| mx-first-loan-never-overdue | partial | table:hive.dwd.dwd_w_apply, field:user_uuid, field:apply_time, glossary:never_overdue | field:withdraw_uuid, field:overdue_days, glossary:first_loan | not_runtime_imported_in_m2b_2:cohort.mx.first_loan_never_overdue |
| mx-mob1-settled-7d-churn | partial | table:hive.dwd.dwd_w_apply, field:user_uuid, glossary:mob1 | field:withdraw_uuid, field:apply_create_at, field:asset_finish_at, field:asset_grant_at, glossary:first_loan, glossary:fully_settled, glossary:seven_day_no_reborrow_churn, example:mob1_churn_pattern | not_runtime_imported_in_m2b_2:rule.common.full_settlement; not_runtime_imported_in_m2b_2:rule.common.seven_day_no_reborrow; not_runtime_imported_in_m2b_2:cohort.mx.mob1_settled_7d_churn |
| mx-behavior-writeback | partial | table:hive.dwb.dwb_b1_data_burying_point, field:uid, field:timestamp_, field:eventname, glossary:writeback_behavior, glossary:uid_cohort_required | example:behavior_writeback_pattern | - |
| mx-glossary-combo-writeback | partial | table:hive.dwd.dwd_w_apply, table:hive.dwb.dwb_b1_data_burying_point, field:user_uuid, field:risk_level, field:apply_time, field:uid, field:timestamp_, field:eventname, glossary:writeback_behavior | glossary:high_risk, glossary:recent_7d, example:behavior_writeback_pattern | - |
| mx-no-apply-cohort | partial | table:hive.dwd.dwd_w_apply, field:user_uuid, field:apply_time, glossary:recent_30d | table:hive.dwd.dwd_w_user, glossary:no_apply | - |
| mx-no-withdraw-cohort | partial | table:hive.dwd.dwd_w_apply, field:user_uuid, field:apply_time | field:withdraw_uuid, glossary:no_withdraw | - |
| mx-withdraw-cohort | partial | table:hive.dwd.dwd_w_apply, field:user_uuid, glossary:successful_withdraw | field:withdraw_uuid, field:asset_grant_at, glossary:recent_7d | - |
| mx-app-profile-query | partial | glossary:app_profile | table:hive.ods.ods_f_market_app_categories, field:app_package, field:category_name, field:year_day | - |
| mx-credit-profile-query | fail | - | table:hive.dwb.dwb_r_apply, field:apply_id, field:user_uuid, field:apply_status, glossary:credit_profile | - |
| ph-first-loan-never-overdue | partial | table:ph_apply_orders, field:loan_count, glossary:first_loan, glossary:never_overdue | field:user_uuid, field:overdue_days | - |
| ph-withdraw-uuid-negative | partial | table:ph_apply_orders, field:loan_count, glossary:never_overdue | field:user_uuid | - |
| th-asset-snapshot-query | partial | field:asset_id, glossary:asset_snapshot | table:hive.dwt.dwt_asset_info_base_snap, field:user_uuid, field:finish_time | - |
| th-risk-apply-query | partial | table:hive.dwt.dwt_rsk_apply_info_base_d, field:apply_uuid, glossary:risk_apply | field:ask_loan_uuid, field:user_loan_label | - |
| th-ask-loan-risk-query | partial | table:hive.dwt.dwt_rsk_ask_loan_info_base_d, field:ask_loan_uuid, glossary:ask_loan_risk | field:user_uuid, field:apply_create_at | - |
| th-third-party-risk-query | partial | glossary:third_party_risk, glossary:credit_report | table:hive.third_party.thailand_sources, field:supplier_name, field:product_name, field:parse_table_name | - |
| dws-renewal-loan-segment-query | partial | table:dws.dws_user_renewal_loan_seg_d, field:mob_code, field:last_finish_time, field:cur_loan_cnt, glossary:mob1 | field:user_uuid, glossary:settled_over_3m | - |
| dws-fox-boc-behavior-query | partial | table:dws.dws_fox_boc_behavior_log_d, field:debtor_id, field:behavior_type, field:behavior_time, field:behavior_status_name | glossary:collection_behavior, glossary:contact_outcome | - |
