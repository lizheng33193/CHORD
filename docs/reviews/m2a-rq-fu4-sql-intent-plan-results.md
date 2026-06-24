# M2A-RQ-FU4 Canonical Field Policy & SQL Intent Plan Results

## Scope

本轮 `M2A-RQ-FU4` 只处理两类 runtime follow-up：

1. canonical field policy: prompt + warning
2. `bucket_writeback` combo request 的 prompt-side `sql_intent_plan`

本轮不改：

- `GenerateRequest` / `GenerateResponse` schema
- `data_acquisition_agent/orchestrator.py`
- `M1` SQL HITL 状态机
- `M1.5` Orchestrator Bridge
- `query_data`
- retriever scoring
- seed assets
- vector retrieval / embedding / rerank

## Implemented Changes

### 1. Code-level canonical field policy

新增：

- `app/data_knowledge/canonical_fields.py`

当前只覆盖 `dwd_w_apply` 的窄集合：

- `user_identifier`: prefer `uid`, alternative `user_uuid`
- `apply_time`: prefer `apply_time`, alternative `apply_create_at`
- `risk_level`: prefer `risk_level`, alternative `risk_label`

并统一 table normalize：

- `hive.dwd.dwd_w_apply` -> `dwd_w_apply`
- `` `dwd_w_apply` `` -> `dwd_w_apply`

### 2. Prompt-side canonical guidance

`app/data_knowledge/prompt_context.py` 新增：

- `# === canonical_field_guidance ===`

当前 prompt 会显式告诉模型：

- preferred fields 是什么
- grounded alternatives 是什么
- 不要因为 historical examples 切到 alternative family

`data_acquisition_agent/prompt_assembler.py` 也已把 canonical guidance 提升到全局 priority rules。

### 3. Warning-only NON_CANONICAL_FIELD

`app/data_agent/service.py` 现已支持：

- `UNSUPPORTED_FIELD`：未被当前 retrieved catalog/glossary 支撑
- `NON_CANONICAL_FIELD`：已被 grounding 支撑，但命中 `alternative -> preferred` 映射

当前保持 warning-only：

- 不改变 `safety_status`
- 不触发 blocked
- 不改变 approve / execute flow

### 4. Prompt-side SQL intent plan

`app/data_knowledge/prompt_context.py` 新增：

- `# === sql_intent_plan ===`

当前只在 `bucket_writeback` 且 request specified 时渲染：

- `task_type`
- `output_bucket`
- `target_cohort_conditions`
- `source_tables`
- `join_keys`
- `required_fields`
- `forbidden_patterns`

under-specified writeback 保持：

- `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`
- 不伪造 cohort plan
- 不生成 SQL

## Verification

### Targeted tests

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_agent/test_api.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py -q`

结果：

- `49 passed`

### Regression subset

- `pytest tests/data_knowledge/test_data_knowledge_retriever.py data_acquisition_agent/tests/test_orchestrator.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py -q`

结果：

- `70 passed`

## Live Rerun Samples

本轮继续使用真实 Data Agent create path + live LLM generation，复跑 3 条目标样例。

### 1. mx-high-risk-cohort

Request:

- `用 Data Agent 生成 SQL，查询最近 7 天高风险用户`

Retrieved context summary:

- table: `dwd_w_apply`
- grounded fields: `apply_time`, `risk_level`, `loan_count`, `max_overdue_days`
- 当前 snapshot 中没有 `uid` / `user_uuid`

Canonical field guidance:

- 当前 retrieval snapshot 没有形成 `canonical_alternative_to_preferred_by_table`
- 原因是 canonical policy 需要 preferred field 先被 grounding 支撑；本样例里 `uid` 没有被当前 retrieval 带出

SQL intent plan summary:

- `null`（query-only，不是 writeback）

Generated SQL:

```sql
SELECT
    user_uuid
FROM
    hive.dwd.dwd_w_apply
WHERE
    risk_level = 'high'
    AND CAST(apply_time AS DATETIME) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
    AND dt >= DATE_FORMAT(DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY), '%Y%m%d')
    AND dt <= DATE_FORMAT(CURRENT_DATE(), '%Y%m%d');
```

Safety Gate status:

- `passed`

UNSUPPORTED_FIELD warnings:

- `user_uuid`
- `dt`

NON_CANONICAL_FIELD warnings:

- none

literal-copy drift:

- no obvious fixed source filter
- relative 7-day time window kept

combo intent preserved:

- n/a

Judgment:

- `partial`

Interpretation:

- FU4 没有把这条高风险 query 推回历史 source filter
- 但由于当前 retrieval snapshot 没把 `uid` grounding 出来，canonical policy 无法把 `user_uuid` 降级成 `NON_CANONICAL_FIELD`
- 剩余问题仍然不是纯 retrieval recall，而是 “retrieval grounding gap + field-choice control” 的组合问题

### 2. mx-behavior-writeback

Request:

- `用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior`

Retrieved context summary:

- under-specified writeback

Canonical field guidance:

- not applicable

SQL intent plan summary:

- not rendered

Generated SQL:

- none

Safety Gate status:

- no SQL generated

UNSUPPORTED_FIELD warnings:

- none

NON_CANONICAL_FIELD warnings:

- none

literal-copy drift:

- not observed

combo intent preserved:

- n/a

Judgment:

- `pass`

Interpretation:

- under-specified `bucket_writeback` 继续稳定返回 `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`
- 没有 broad scan
- 没有 placeholder
- 没有伪造 intent plan

### 3. mx-glossary-combo-writeback

Request:

- `找出墨西哥首贷且从未逾期的用户，并写回 behavior`

Retrieved context summary:

- tables: `dwb_b1_data_burying_point`, `dwd_w_apply`
- grounded fields:
  - `dwb_b1_data_burying_point`: `uid`, `eventname`, `timestamp_`
  - `dwd_w_apply`: `uid`, `max_overdue_days`, `loan_count`, `risk_level`, `apply_time`

Canonical field guidance:

- prompt 中已渲染 `dwd_w_apply` preferred field guidance
- 当前 snapshot 里仍未形成 grounded alternative map，因为 `user_uuid` / `apply_create_at` 未被当前 retrieval grounding 带出

SQL intent plan summary:

- `task_type=bucket_writeback`
- `output_bucket=behavior`
- `target_cohort_conditions=first_loan,never_overdue`
- `source_tables=dwb_b1_data_burying_point,dwd_w_apply`
- `join_keys=uid`
- `required_fields=uid,timestamp_,eventname`
- `forbidden_patterns=unresolved_uid_placeholder,broad_behavior_scan,historical_date_copy,historical_source_filter,literal_example_copy,unsupported_field_family`

Generated SQL 特征：

- 先建 cohort，再 join behavior table
- 保留了 combo intent
- 第二轮 rerun 在更强的 `sql_intent_plan` priority rule 下，已明显收敛：
  - 最终只保留 `uid`, `timestamp_`, `eventname`
  - 不再展开整套 historical behavior 字段列举
- 但仍残留明显 historical template drift：
  - `user_uuid AS uid`
  - 固定日期分区 `20260201` / `20260228` / `20260315`
  - 固定 source filter `MEXI / MEXICASH`
  - `concat(customer_type, distribute_type) = 'newDISTRIBUTE'`

Safety Gate status:

- `passed`

UNSUPPORTED_FIELD warnings:

- `dt`
- `source`

NON_CANONICAL_FIELD warnings:

- none

literal-copy drift:

- still visible

combo intent preserved:

- yes

Judgment:

- `needs_fu5`

Interpretation:

- FU4 已经把 combo request 的 cohort / join / required fields / forbidden patterns 明确写进 prompt 和 snapshot
- 第二轮 rerun 说明更强的 `sql_intent_plan` priority rule 已经开始起效：模型不再把 behavior 部分扩成整套 historical template 字段族
- 但 SQL 仍没有稳定遵守 plan：
  - 仍保留历史日期分区
  - 仍保留历史 source filter
  - 仍用 `user_uuid AS uid` 规避 canonical preference
- 这说明下一轮主要问题已经变成：`plan 已开始约束结构，但仍缺少 plan-to-sql consistency validation`

## Overall Conclusion

当前结论：

- `mx-high-risk-cohort`: `partial`
- `mx-behavior-writeback`: `pass`
- `mx-glossary-combo-writeback`: `needs_fu5`

因此：

- `FU4` 不足以让阶段进入 `M2B`
- 下一步应进入 `FU5: Plan Validation / Plan-to-SQL Consistency Review`

当前判断依据：

1. combo writeback 仍明显回退历史模板
2. canonical policy 只有在 preferred field 已被 retrieval grounding 带出时才有稳定约束力
3. SQL intent plan 已形成，但还缺少 “generated SQL 是否遵守 plan” 的后验一致性检查
