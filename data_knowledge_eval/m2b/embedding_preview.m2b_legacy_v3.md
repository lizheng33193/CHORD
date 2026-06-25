# M2B-3 Embedding Text Preview

- source_namespace: `m2b_legacy_v3`
- generated_at: `2026-06-25T00:00:00Z`
- sample_count: `8`

## `glossary.common.mob1.mx_runtime`

- asset_family: `glossary_term`
- country: `mx`
- title: `mob1`

```text
Asset family: glossary_term
Country: mx
Title: mob1
Definition: 首贷、完全结清、结清满七天且七天内无复借的流失客群语义。 runtime grounding 必须同时覆盖首贷、完全结清、结清满7天和7天内未复借四个条件。
Synonyms: mob1客群, mob1提取, 结清7天未复借, 首贷结清流失, settled 7d no reborrow, mob1 churn
Mapped tables: dwd_w_apply
Mapped fields: user_uuid, withdraw_uuid, asset_grant_at, asset_finish_at, apply_create_at
Suggested filters: first_loan, fully_settled, settlement_over_7d, no_reborrow_within_7d
```

## `field.mx.dwd_w_apply.withdraw_uuid`

- asset_family: `catalog_field`
- country: `mx`
- title: `dwd_w_apply.withdraw_uuid`

```text
Asset family: catalog_field
Country: mx
Title: dwd_w_apply.withdraw_uuid
Description: 提现流水号，真实借款判定核心字段。 提现流水号，真实借款/首贷判定和复借检测的核心借款单号字段。 提现/借款订单标识，用于关联申请、提现、放款、资产和首贷链路。
Business meaning: semantic=withdraw_identifier; usage=true_withdraw_detection, reborrow_detection; join_key=true 借款单号，用于识别真实提现、首贷借款链路和 7 天内是否复借。 提现订单号/借款订单号（loan order id / withdraw order id），用于首贷提现、成功提现、放款成立、首贷且从未逾期的借款订单识别以及复借排除。
Field type: varchar
Join hint: primary join key
Aliases: loan_uuid, 借款单号, 提现订单号, 提现订单, 借款订单, loan order id, withdraw order id, 首贷提现
Usage: true_withdraw_detection, reborrow_detection
Physical table names: none
```

## `field.mx.dwd_w_apply.user_uuid`

- asset_family: `catalog_field`
- country: `mx`
- title: `dwd_w_apply.user_uuid`

```text
Asset family: catalog_field
Country: mx
Title: dwd_w_apply.user_uuid
Description: 用户 ID。 借款链路用户 ID，适用于 cohort join、用户级聚合和跨表关联。 申请、提现、资产链路中的用户主标识，可作为 cohort 与资产联合分析的用户键。
Business meaning: semantic=user_identifier; aliases=uid; usage=cohort_join, user_level_grouping; join_key=true 用户主键，可对应 uid / borrower / cohort join。 用户主键，用于 apply/asset/user 主链路，不等价于 behavior 表 uid。
Field type: bigint
Join hint: primary join key
Aliases: uid, 用户ID, 借款用户, borrower_uuid, 用户唯一标识, user id, user_identifier
Usage: cohort_join, user_level_grouping
Physical table names: none
```

## `field.mx.dwd_w_apply.asset_finish_at`

- asset_family: `catalog_field`
- country: `mx`
- title: `dwd_w_apply.asset_finish_at`

```text
Asset family: catalog_field
Country: mx
Title: dwd_w_apply.asset_finish_at
Description: 资产或分期结清时间。 资产或分期结清时间，用于 fully_settled 和 7 天未复借流失观察。 资产或分期结清时间，用于判断完全结清、结清满7天观察期和 mob1 流失。
Business meaning: semantic=settlement_time; aliases=final_finish_at; usage=settlement_windowing, churn_observation; business_time=true 结清时间，用于 full settlement 与 7 天 churn 观察窗口。 结清时间，对应 fully_settled / settlement_over_7d / mob1 / no_reborrow_within_7d，也是结清满7天观察窗口的核心字段。
Field type: varchar
Join hint: none
Aliases: final_finish_at, 结清时间, 完全结清时间, settlement time, 还清时间, 结清满7天, settled over 7d
Usage: settlement_windowing, churn_observation
Physical table names: none
```

## `glossary.mx.credit_profile`

- asset_family: `glossary_term`
- country: `mx`
- title: `credit_profile`

```text
Asset family: glossary_term
Country: mx
Title: credit_profile
Definition: 面向征信、审核申请、审核结果与申请状态字段的查询语义。 应优先检索征信审核申请宽表字段。 用于回答墨西哥征信相关申请字段、审核申请状态与申请主键查询。
Synonyms: 征信画像, 审核申请字段, credit profile, 征信申请字段, 审核申请画像, 征信相关申请字段, 征信申请状态, 征信审核状态, 墨西哥征信字段, credit application fields, credit apply status
Mapped tables: dwb_r_apply
Mapped fields: apply_id, apply_user_uuid, apply_status
Suggested filters: apply_status, apply_created_at, apply_id
```

## `sql_pattern.mx.behavior_writeback_target_cohort`

- asset_family: `sql_example`
- country: `mx`
- title: `sql_pattern.mx.behavior_writeback_target_cohort`

```text
Asset family: sql_example
Country: mx
Title: sql_pattern.mx.behavior_writeback_target_cohort
Request: behavior writeback pattern
Pattern summary: build target_users CTE first | join behavior table by uid or mapped user identifier | keep event window relative to request or cohort business event | return only the required behavior payload columns return uid timestamp_ eventname as the minimum behavior writeback payload | preserve uid to user_uuid join semantics without treating them as globally equivalent fields
Tables used: none
Fields used: uid, timestamp_, eventname
Run type: bucket_writeback
Output bucket: behavior
Non-executable pattern guidance.
This record is not executable SQL.
```

## `field.multi.dws_fox_boc_behavior_log_d.behavior_status_name`

- asset_family: `catalog_field`
- country: `multi`
- title: `dws_fox_boc_behavior_log_d.behavior_status_name`

```text
Asset family: catalog_field
Country: multi
Title: dws_fox_boc_behavior_log_d.behavior_status_name
Description: 行为状态名称，例如是否接通。
Business meaning: semantic=contact_outcome; usage=contact_outcome_analysis
Field type: varchar
Join hint: none
Aliases: none
Usage: contact_outcome_analysis
Physical table names: none
```

## `field.multi.dws_fox_boc_behavior_log_d.behavior_time`

- asset_family: `catalog_field`
- country: `multi`
- title: `dws_fox_boc_behavior_log_d.behavior_time`

```text
Asset family: catalog_field
Country: multi
Title: dws_fox_boc_behavior_log_d.behavior_time
Description: 行为发生时间。
Business meaning: semantic=behavior_business_time; usage=contact_sequence_analysis; business_time=true
Field type: datetime
Join hint: none
Aliases: none
Usage: contact_sequence_analysis
Physical table names: none
```
