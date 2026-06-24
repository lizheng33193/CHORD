# M2A-RQ-FU5 Plan-to-SQL Consistency Review Design

## Summary

`M2A-RQ-FU5` 新增 deterministic、warning-only 的后验 review 层：

```text
generated SQL
  -> Safety Gate
  -> Field Grounding Warning
  -> Canonical Field Warning
  -> Plan-to-SQL Consistency Warning
  -> SQL HITL
```

`FU4` 已经为 writeback request 生成 `sql_intent_plan`，但 live rerun 说明最终 SQL 仍可能绕过 plan，继续带入 fixed historical dates、fixed source filters、alternative field family 或 broad behavior scan。`FU5` 的任务不是继续加强 prompt，也不是进入 `M2B`，而是让系统在生成后显式指出 SQL 是否偏离了当前 plan。

## Scope

本阶段只做 generated SQL vs `sql_intent_plan` 的一致性审查：

- review 结果只进入现有 `safety_result.warnings`
- 不改 `GenerateRequest` / `GenerateResponse`
- 不改 `data_acquisition_agent/orchestrator.py`
- 不改 `M1` SQL HITL 状态机
- 不改 `M1.5` Orchestrator Bridge
- 不改 `query_data`
- 不改 retriever scoring、seed、knowledge schema、embedding/vector/rerank
- 第一阶段 warning-only，不 hard block

## Design

### 1. Pure deterministic review helper

新增：

- `app/data_agent/plan_review.py`

核心函数：

```python
def review_sql_against_intent_plan(
    *,
    sql_text: str,
    retrieval_snapshot: dict,
    natural_language_request: str,
    run_type: str,
    output_bucket: str | None,
) -> list[dict]:
    ...
```

该 helper 必须保持纯 deterministic：

- 不调用模型
- 不访问数据库
- 不调用 retriever
- 不访问外部服务

只读取已有 `retrieval_snapshot_json`：

- `sql_intent_plan_summary`
- `canonical_alternative_to_preferred_by_table`
- `grounded_fields_by_table`

### 2. Warning categories

`FU5` v1 支持以下 warning：

- `PLAN_DATE_DRIFT`
- `PLAN_SOURCE_FILTER_DRIFT`
- `PLAN_CANONICAL_FIELD_DRIFT`
- `PLAN_REQUIRED_FIELD_MISSING`
- `PLAN_BROAD_SCAN_RISK`
- `PLAN_FORBIDDEN_PATTERN`

warning shape：

```json
{
  "category": "PLAN_DATE_DRIFT",
  "risk_level": "medium",
  "message": "SQL contains fixed date partition not requested by the current request or sql_intent_plan.",
  "evidence": "20260201"
}
```

`evidence` 只允许短 SQL 片段、字段名、日期字面量或 pattern 名称，不允许 raw prompt、raw model output 或 chain-of-thought。

### 3. Drift rules

#### PLAN_DATE_DRIFT

只拦固定历史日期或分区，例如：

- `dt >= '20260201'`
- `dt <= '20260228'`
- `dt = '20260315'`

如果 request 没要求这些 fixed historical dates，且 plan 也没允许，则输出 warning。

动态相对时间表达不能误报，例如：

- `CURRENT_DATE`
- `DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)`
- `dt >= date_format(date_sub(current_date, 7), 'yyyyMMdd')`

#### PLAN_SOURCE_FILTER_DRIFT

只在 request 和 `sql_intent_plan` 都未要求 source/channel filter 时触发。

若 request 明确提到 `MEX017`、`MEXI`、`MEXICASH` 或其它 source/channel，则不触发。

#### PLAN_CANONICAL_FIELD_DRIFT

该 warning 复用 `app/data_knowledge/canonical_fields.py` 作为单一来源，不允许在 `plan_review.py` 中重复维护 canonical mapping。

它与 `NON_CANONICAL_FIELD` 的区别是：

- `NON_CANONICAL_FIELD`：字段命中 alternative -> preferred 映射
- `PLAN_CANONICAL_FIELD_DRIFT`：字段选择还偏离了当前 plan / generation guidance

#### PLAN_REQUIRED_FIELD_MISSING

第一版只对 `output_bucket=behavior` 生效。

检查对象必须是 SQL 的 `SELECT` 输出字段，而不是字段是否在 `WHERE` / `JOIN` 中出现。`eventname` 只出现在过滤条件里，不等于写回结果已经包含 `eventname`。

#### PLAN_BROAD_SCAN_RISK

第一版只对 `output_bucket=behavior` 生效。

如果 SQL 直接扫行为表，缺少 target cohort、uid join 或明确 cohort filter，则输出 warning。`LIMIT` 不是合法 cohort constraint，不能抑制该 warning。

#### PLAN_FORBIDDEN_PATTERN

该 warning 作为兜底层，覆盖：

- `unresolved_uid_placeholder`
- `broad_behavior_scan`
- `historical_date_copy`
- `historical_source_filter`
- `literal_example_copy`
- `unsupported_field_family`

能归类到更细 warning 的，优先输出更细 warning。

### 4. Service integration

`app/data_agent/service.py` 在生成 SQL 后按以下顺序汇总 warning：

1. `run_sql_safety_gate(...)`
2. field grounding warnings
3. canonical field warnings
4. plan-to-SQL consistency warnings

`PLAN_*` warnings 只进入现有 `safety_result.warnings`，不改变：

- `safety_status`
- approve / reject / revise / execute transitions
- `M1` state machine

### 5. Future boundary

`FU5` 只负责发现偏离 plan 的地方，不负责自动修复。

如果 FU5 后 drift 仍频繁发生，但 warning 已能稳定标出，则下一步应进入：

- `FU6: Plan-guided Regeneration / Repair`

只有在生成控制稳定、剩余问题主要转为 retrieval coverage / quality 时，才进入：

- `M2B Hybrid Retrieval`
