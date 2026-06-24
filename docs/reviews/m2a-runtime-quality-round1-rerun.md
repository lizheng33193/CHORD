# M2A-Runtime Quality Round 1 Rerun

## Scope

本轮在 `main` 合入 `M2A-Runtime Quality` 后，从 `codex/m2a-runtime-quality-verify` 复跑 5 条固定样例，真实走通：

- seed import
- `DataKnowledgeRetriever`
- `PromptContextAssembler`
- `DataAcquisitionOrchestrator.generate(...)`
- `run_sql_safety_gate(...)`

目标是验证 runtime quality 收口后，是否已经满足进入 `M2B` 的条件。

## Environment

- Date: 2026-06-24
- Branch: `codex/m2a-runtime-quality-verify`
- Main merge baseline: `main@bc53873`
- Model mode: `vertex`
- Model route observed in logs: `gemini-2.5-flash`
- Knowledge source: imported `common + mx + ph` seed bundle
- Note:
  - `mx-glossary-combo-writeback` 首次尝试遇到 transient upstream model unavailable；第二次重跑成功，以下记录采用成功结果

## Executive Summary

本轮复测后的总体判断：

- unresolved placeholder 现在确实会被 Safety Gate 拦截，不再漏进可执行链路。
- `create_run` / `revise_run` 对 structured failure 与 non-SQL result 的 `HTTP 422` 边界已闭合。
- `mx high-risk cohort` 的 behavior false positive 已明显压下，但生成 SQL 仍保留较强 few-shot / historical pattern drift。
- `mx behavior writeback` 仍能召回正确 behavior assets，但生成 SQL 还会出现 placeholder 型 writeback 模板残留。
- `mx glossary combo writeback` 结构化输出已稳定到可生成，但生成 SQL 仍明显向 few-shot 熟悉结构回退。

结论：

- 当前不建议直接进入 `M2B`
- 下一步更合适的是 `M2A-RQ-FU2`
- `M2B` 应在 few-shot drift / broad-scan tendency 再收一轮后进入

## Case 1

### Meta

- Case ID: `ph-first-loan-never-overdue`
- User request: `查询菲律宾首贷从未逾期用户`
- Run type: `cohort_query`
- Output bucket: `null`

### Retrieval Result

- Retrieved tables:
  - `ph_apply_orders`
- Retrieved fields:
  - `ph_apply_orders.history_overdue_count`
  - `ph_apply_orders.loan_count`
- Retrieved glossary:
  - `term:never_overdue`
  - `term:first_loan`
- Retrieved examples:
  - `example:ph-first-loan-never-overdue`
- Retrieved error cases:
  - `case:ph-withdraw-uuid`

### Prompt Context

- Assembled prompt context summary:
  - 单表单例场景，命中了 `ph` cohort 所需的核心 glossary / field / example
  - context 包含 pattern guidance 与 `Do not copy example WHERE clauses`
  - 未出现无关 behavior 约束

### Generation Result

- Generated SQL kind: `query_only`
- Generated SQL:

```sql
SELECT
  uid,
  loan_count,
  history_overdue_count
FROM ph_apply_orders
WHERE
  loan_count = 1 AND history_overdue_count = 0;
```

- Safety Gate status: `passed`
- unresolved placeholder: `no`
- false positive: `no`
- literal copy / broad scan risk: `low`
- structured output stability: `stable`

### Human Judgment

- Verdict: `pass`
- Notes:
  - `loan_count` field gap 已关闭
  - country scope、glossary、example、generation 都稳定

## Case 2

### Meta

- Case ID: `ph-withdraw-uuid-negative-error-case`
- User request: `修复菲律宾首贷从未逾期 SQL，避免使用 withdraw_uuid`
- Run type: `cohort_query`
- Output bucket: `null`

### Retrieval Result

- Retrieved tables:
  - `ph_apply_orders`
- Retrieved fields:
  - `ph_apply_orders.uid`
  - `ph_apply_orders.history_overdue_count`
  - `ph_apply_orders.loan_count`
- Retrieved glossary:
  - `term:never_overdue`
  - `term:first_loan`
- Retrieved examples:
  - `example:ph-first-loan-never-overdue`
- Retrieved error cases:
  - `case:ph-withdraw-uuid`

### Prompt Context

- Assembled prompt context summary:
  - error case 正常进入 context
  - context 保留 pattern guidance，并把 `withdraw_uuid` 负例提醒一起注入

### Generation Result

- Generated SQL kind: `query_only`
- Generated SQL:

```sql
SELECT
  uid
FROM
  ph_apply_orders
WHERE
  loan_count = 1
  AND history_overdue_count = 0;
```

- Safety Gate status: `passed`
- unresolved placeholder: `no`
- false positive: `no`
- literal copy / broad scan risk: `low`
- structured output stability: `stable`

### Human Judgment

- Verdict: `pass`
- Notes:
  - `withdraw_uuid` 负例 recall 已自然生效
  - repair memory / error case 路径在 `ph` 场景下可用

## Case 3

### Meta

- Case ID: `mx-high-risk-cohort`
- User request: `用 Data Agent 生成 SQL，查询最近 7 天高风险用户`
- Run type: `cohort_query`
- Output bucket: `null`

### Retrieval Result

- Retrieved tables:
  - `dwd_w_apply`
- Retrieved fields:
  - `dwd_w_apply.apply_time`
  - `dwd_w_apply.risk_level`
  - `dwd_w_apply.loan_count`
  - `dwd_w_apply.max_overdue_days`
- Retrieved glossary:
  - `term:high_risk_user`
  - `term:last_7_days`
  - `term:first_loan`
  - `term:never_overdue`
- Retrieved examples:
  - `example:first-loan-never-overdue`
- Retrieved error cases:
  - none

### Prompt Context

- Assembled prompt context summary:
  - behavior false positive 已压下，context 中不再出现 behavior table / writeback glossary
  - context 仍混入了 `first_loan / never_overdue` 相关 glossary 和 example，说明 deterministic retrieval 还有弱相关扩张
  - pattern guidance 已注入

### Generation Result

- Generated SQL kind: `query_only`
- Generated SQL:

```sql
WITH recent_high_risk_applications AS (
    SELECT
        user_uuid,
        apply_create_at,
        risk_level,
        apply_source
    FROM
        hive.dwd.dwd_w_apply
    WHERE
        dt >= DATE_FORMAT(DATE_SUB(CURRENT_DATE(), 7), 'yyyyMMdd')
        AND CAST(apply_create_at AS DATETIME) >= DATE_SUB(CURRENT_DATE(), 7)
        AND risk_level = 'high'
        AND apply_source = 'MEX017'
)
SELECT DISTINCT
    user_uuid
FROM
    recent_high_risk_applications;
```

- Safety Gate status: `passed`
- unresolved placeholder: `no`
- false positive: `behavior=false`, `weak glossary/example spillover=true`
- literal copy / broad scan risk: `medium`
- structured output stability: `stable`

### Human Judgment

- Verdict: `partial`
- Notes:
  - retriever false positive 的核心问题已改善
  - 但 generated SQL 仍明显沿用 few-shot / historical field naming（`user_uuid`、`apply_create_at`、`apply_source=MEX017`）
  - 这说明下一步更像 generation-style follow-up，而不是 retrieval architecture 升级

## Case 4

### Meta

- Case ID: `mx-behavior-writeback`
- User request: `用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior`
- Run type: `bucket_writeback`
- Output bucket: `behavior`

### Retrieval Result

- Retrieved tables:
  - `dwb_b1_data_burying_point`
  - `dwd_w_apply`
- Retrieved fields:
  - `dwb_b1_data_burying_point.uid`
  - `dwb_b1_data_burying_point.eventname`
  - `dwb_b1_data_burying_point.timestamp_`
  - `dwd_w_apply.uid`
  - `dwd_w_apply.loan_count`
  - `dwd_w_apply.max_overdue_days`
  - `dwd_w_apply.risk_level`
  - `dwd_w_apply.apply_time`
- Retrieved glossary:
  - `term:writeback_behavior`
  - `term:first_loan`
  - `term:never_overdue`
  - `term:high_risk_user`
  - `term:last_7_days`
- Retrieved examples:
  - `example:behavior-writeback`
- Retrieved error cases:
  - none

### Prompt Context

- Assembled prompt context summary:
  - behavior source table、field、writeback example 都正确进入 context
  - context 包含 pattern guidance、no-literal-copy 提示与 cohort-first / no-broad-scan behavior constraint

### Generation Result

- Generated SQL kind: `query_only`
- Generated SQL:

```sql
WITH user_behavior_raw AS (
  SELECT
    a.uid,
    a.servertimestamp,
    a.timestamp_,
    a.scenetype,
    a.processtype,
    a.eventname,
    a.extend,
    a.clientmodel,
    a.clientosversion,
    a.url,
    a.refer,
    a.ip,
    ROW_NUMBER() OVER(PARTITION BY a.uid ORDER BY a.timestamp_ DESC) as rn
  FROM hive.dwb.dwb_b1_data_burying_point a
  WHERE a.uid IN ({uid_str})
    AND a.dt >= '20260201' AND a.dt <= '20260315'
    AND a.source IN ('MEXI', 'MEXICASH')
)
SELECT
  uid,
  servertimestamp,
  timestamp_,
  scenetype,
  processtype,
  eventname,
  extend,
  clientmodel,
  clientosversion,
  url,
  refer,
  ip
FROM user_behavior_raw
WHERE rn <= 500;
```

- Safety Gate status: `blocked`
- blocked reasons:
  - `SQL contains unresolved placeholders: {uid_str}`
- unresolved placeholder: `yes`
- false positive: `no`
- literal copy / broad scan risk: `medium`
- structured output stability: `stable`

### Human Judgment

- Verdict: `partial`
- Notes:
  - retrieval 和 prompt context 方向正确
  - unresolved placeholder 现在已被 Safety Gate 正确挡住，说明 runtime boundary 生效
  - 但 generation 仍保留 few-shot 型 behavior template 残留，不能视为已完全稳定

## Case 5

### Meta

- Case ID: `mx-glossary-combo-writeback`
- User request: `找出墨西哥首贷且从未逾期的用户，并写回 behavior`
- Run type: `bucket_writeback`
- Output bucket: `behavior`

### Retrieval Result

- Retrieved tables:
  - `dwb_b1_data_burying_point`
  - `dwd_w_apply`
- Retrieved fields:
  - `dwb_b1_data_burying_point.uid`
  - `dwb_b1_data_burying_point.eventname`
  - `dwb_b1_data_burying_point.timestamp_`
  - `dwd_w_apply.uid`
  - `dwd_w_apply.max_overdue_days`
  - `dwd_w_apply.loan_count`
  - `dwd_w_apply.risk_level`
  - `dwd_w_apply.apply_time`
- Retrieved glossary:
  - `term:writeback_behavior`
  - `term:never_overdue`
  - `term:first_loan`
  - `term:high_risk_user`
  - `term:last_7_days`
- Retrieved examples:
  - `example:behavior-writeback`
- Retrieved error cases:
  - none

### Prompt Context

- Assembled prompt context summary:
  - combo writeback 请求仍能召回 behavior assets
  - context 含 pattern guidance、no-literal-copy 提示与 behavior no-broad-scan 约束
  - 首次尝试遇到 transient upstream model unavailable；重跑后结构化输出成功

### Generation Result

- Generated SQL kind: `query_only`
- Generated SQL:

```sql
WITH user_base AS (
    SELECT
        user_uuid,
        user_create_time,
        apply_source
    FROM
        hive.dwd.dwd_w_user
    WHERE
        dt >= '20260201' AND dt <= '20260228'
        AND apply_source = 'MEX017'
),
first_loan_identification AS (
    SELECT
        user_uuid,
        withdraw_uuid,
        withdraw_created_at,
        ROW_NUMBER() OVER(PARTITION BY user_uuid ORDER BY withdraw_created_at ASC) AS rn_loan
    FROM
        hive.dwd.dwd_w_apply
    WHERE
        dt >= '20260201' AND dt <= '20260228'
        AND apply_source = 'MEX017'
        AND withdraw_uuid IS NOT NULL
        AND withdraw_uuid != ''
),
first_loan_info AS (
    SELECT
        fli.user_uuid,
        fli.withdraw_uuid AS first_loan_withdraw_uuid,
        fli.withdraw_created_at AS first_loan_time
    FROM
        first_loan_identification fli
    WHERE
        fli.rn_loan = 1
),
first_loan_periods_overdue_status AS (
    SELECT
        a.user_uuid,
        a.withdraw_uuid,
        MAX(CASE WHEN a.asset_overdue_days > 0 THEN 1 ELSE 0 END) AS has_overdue_period
    FROM
        hive.dwd.dwd_w_apply a
    INNER JOIN
        first_loan_info fli
    ON
        a.user_uuid = fli.user_uuid
        AND a.withdraw_uuid = fli.first_loan_withdraw_uuid
    WHERE
        a.dt >= '20260201' AND a.dt <= '20260228'
        AND a.apply_source = 'MEX017'
    GROUP BY
        a.user_uuid,
        a.withdraw_uuid
),
first_loan_never_overdue_users AS (
    SELECT
        ub.user_uuid,
        ub.user_create_time
    FROM
        user_base ub
    INNER JOIN
        first_loan_info fli
    ON
        ub.user_uuid = fli.user_uuid
    INNER JOIN
        first_loan_periods_overdue_status flpos
    ON
        ub.user_uuid = flpos.user_uuid
        AND flpos.has_overdue_period = 0
)
SELECT
    CAST(b.uid AS VARCHAR) AS uid,
    b.timestamp_,
    b.eventname
FROM
    hive.dwb.dwb_b1_data_burying_point b
INNER JOIN
    first_loan_never_overdue_users flnu
ON
    CAST(b.uid AS VARCHAR) = CAST(flnu.user_uuid AS VARCHAR)
WHERE
    b.dt >= '20260201' AND b.dt <= '20260315'
    AND b.source IN ('MEXI', 'MEXICASH')
    AND FROM_UNIXTIME(CAST(b.timestamp_ / 1000 AS BIGINT)) >= CAST(flnu.user_create_time AS DATETIME);
```

- Safety Gate status: `passed`
- unresolved placeholder: `no`
- false positive: `no`
- literal copy / broad scan risk: `high`
- structured output stability: `stable after rerun`

### Human Judgment

- Verdict: `partial`
- Notes:
  - combo retrieval 与 structured output 已明显好于 Round 1
  - 但 SQL 仍 heavily shaped by historical/few-shot structures（`dwd_w_user`、`withdraw_uuid`、固定日期范围、渠道过滤）
  - 这类 drift 还不适合直接交给 `M2B` 去掩盖

## Decision Gate

逐项对照进入 `M2B` 条件：

1. placeholder 能被 Safety Gate 拦截：`yes`
2. structured failure 和 non-SQL result 都返回 `HTTP 422`：`yes`
3. `mx high-risk cohort` 不再明显误召回 behavior writeback：`yes`
4. behavior writeback 仍能召回正确 active example：`yes`
5. prompt context 不再明显诱导 literal copy / broad scan：`not yet`
6. Round 1 rerun 大多数为 `pass` 或 `partial`：`yes`

## Final Recommendation

当前推荐：

- 不直接进入 `M2B`
- 先进入 `M2A-RQ-FU2`

优先 follow-up 方向：

1. 进一步压制 few-shot / historical SQL literal drift
2. 强化 writeback 场景对 cohort source / user list source 的显式约束
3. 收紧 combo writeback 场景中无关 historical field family 的生成倾向

原因：

- retrieval baseline 现在已经足够清晰
- 当前剩余主要问题在 generation style / pattern overfit
- 这类问题不应靠 embedding / rerank 提前掩盖
