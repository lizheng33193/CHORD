# M2A-RQ-FU5 Plan-to-SQL Consistency Review Results

## Scope

本轮 `M2A-RQ-FU5` 只新增 deterministic plan-to-SQL consistency review：

- `PLAN_DATE_DRIFT`
- `PLAN_SOURCE_FILTER_DRIFT`
- `PLAN_CANONICAL_FIELD_DRIFT`
- `PLAN_REQUIRED_FIELD_MISSING`
- `PLAN_BROAD_SCAN_RISK`
- `PLAN_FORBIDDEN_PATTERN`

本轮保持不变：

- `GenerateRequest` / `GenerateResponse` schema
- `data_acquisition_agent/orchestrator.py`
- `M1` SQL HITL 状态机
- `M1.5` Orchestrator Bridge
- `query_data`
- retriever scoring
- seed assets
- knowledge schema
- vector retrieval / embedding / rerank

## Implemented Changes

### 1. New deterministic review helper

新增：

- `app/data_agent/plan_review.py`

当前 helper 只读取已有 `retrieval_snapshot_json`：

- `sql_intent_plan_summary`
- `canonical_alternative_to_preferred_by_table`
- `grounded_fields_by_table`

不调用模型、数据库、retriever 或任何外部服务。

### 2. Warning-only plan review integration

`app/data_agent/service.py` 当前按以下顺序合并 warnings：

1. Safety Gate
2. field grounding warnings
3. canonical field warnings
4. plan-to-SQL consistency warnings

`PLAN_*` warnings 只进入现有 `safety_result.warnings`：

- 不改变 `safety_status`
- 不改变 approve / revise / execute flow
- 不改变 `M1` 状态机

### 3. Regression coverage

新增：

- `tests/data_agent/test_plan_review.py`

扩展：

- `tests/data_agent/test_api.py`

当前测试覆盖：

- fixed historical date drift
- dynamic relative date not drift
- fixed source filter drift
- canonical alternative drift
- behavior required field missing
- behavior broad scan with `LIMIT`
- comparison operators `<=` / `>=` 不误报 placeholder
- create / revise 路径都能带出 `PLAN_*` warnings

## Verification

### Targeted tests

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_agent/test_api.py tests/data_agent/test_plan_review.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py -q`

结果：

- `60 passed`

### Regression subset

- `pytest tests/data_knowledge/test_data_knowledge_retriever.py data_acquisition_agent/tests/test_orchestrator.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py tests/data_agent/test_plan_review.py -q`

结果：

- `81 passed`

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
- 原因仍然是 canonical policy 需要 preferred field 先被 grounding 支撑；本样例里 `uid` 没有被当前 retrieval 带出

SQL intent plan summary:

- `null`

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

PLAN_* warnings:

- none

literal-copy drift:

- no obvious fixed historical date copy
- no fixed source filter

combo intent preserved:

- n/a

Judgment:

- `partial`

Interpretation:

- `FU5` 对这条 query-only 样例没有新增 plan drift warning，因为当前 request 保持了动态相对时间表达，且 snapshot 本身没有 `sql_intent_plan_summary`
- 剩余问题仍然是 retrieval grounding gap 导致的 field-choice control 不足

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

PLAN_* warnings:

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
- 没有伪造 plan

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
- 当前 snapshot 里仍未形成 grounded alternative map，因为 `user_uuid` 未被当前 retrieval grounding 带出

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
- 保留 combo intent
- 输出字段继续收敛在 `uid`, `timestamp_`, `eventname`
- 但仍保留明显 historical template drift：
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

PLAN_* warnings:

- `PLAN_DATE_DRIFT`: `20260201`, `20260228`, `20260315`
- `PLAN_SOURCE_FILTER_DRIFT`: `MEXI`, `MEXICASH`

literal-copy drift:

- still visible

combo intent preserved:

- yes

Judgment:

- `needs_fu6`

Interpretation:

- `FU5` 的核心目标已经达成：当前系统能把 combo writeback 中最主要的 historical template drift 以后验 warning 的形式稳定暴露给 reviewer
- 同时本轮也修掉了 placeholder pattern 对 `<=` / `>=` 的误报
- 但 `FU5` 仍然只是“发现 drift”，没有改善生成本身，因此下一步不该进 `M2B`

## Overall Conclusion

当前结论：

- `mx-high-risk-cohort`: `partial`
- `mx-behavior-writeback`: `pass`
- `mx-glossary-combo-writeback`: `needs_fu6`

因此：

- `FU5` 已完成第一轮 warning-only plan consistency review
- 当前不进入 `M2B`
- 下一步应进入 `FU6: Plan-guided Regeneration / Repair`

当前判断依据：

1. combo writeback 仍会生成明显 historical template drift
2. `PLAN_DATE_DRIFT` / `PLAN_SOURCE_FILTER_DRIFT` 已能稳定标出主要 drift
3. safe refusal 仍稳定
4. reviewer 可见性提升了，但生成本身尚未稳定遵守 plan
