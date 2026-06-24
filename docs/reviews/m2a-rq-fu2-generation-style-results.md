# M2A-RQ-FU2 Generation Style Results

## Scope

本轮 `M2A-RQ-FU2` 只处理 generation style drift，不改：

- retriever scoring 大结构
- seed assets
- Safety Gate 主逻辑
- `M1` SQL HITL 状态机
- `M1.5` Orchestrator Bridge
- `query_data`
- public `GenerateRequest` / `GenerateResponse` schema
- `data_acquisition_agent/orchestrator.py`

本轮代码改动集中在：

- `app/data_knowledge/prompt_context.py`
- `data_acquisition_agent/prompt_assembler.py`
- `tests/data_knowledge/test_prompt_context.py`
- `data_acquisition_agent/tests/test_prompt_assembler.py`

## Implemented Prompt Contract Changes

### 1. Example anti-copy guidance

`retrieved_sql_examples` section 继续保持摘要型，不恢复 full SQL 注入，同时固定加入：

- current request is the source of truth
- examples are pattern guidance only
- do not copy literal dates, partition ranges, source filters, uid placeholders, table aliases, or WHERE clauses from examples unless grounded by the current request and retrieved catalog/glossary
- if the current request does not mention a source or channel filter, do not add one from examples
- if the current request uses a relative time window, keep it relative instead of replacing it with fixed example partitions
- prefer field names explicitly present in the retrieved catalog for the selected table and country
- do not substitute to a historical alias family unless that alias exists in the retrieved catalog or glossary for the current country/table

### 2. Writeback safe-refusal guidance

在 behavior writeback 约束中新增：

- define target cohort or use explicit uid list first
- do not emit unresolved uid placeholders
- do not broad-scan the behavior table
- for under-specified Data Agent bucket writeback requests, return `sql=null` and `sql_kind=query_only` instead of inventing placeholders or broad-scan SQL

### 3. Safety boundary statement

本轮只通过 prompt contract 降低 drift，不把 prompt 当作安全边界：

- prompt guidance 负责减少 drift
- unresolved placeholder 仍由现有 Safety Gate 做最终 enforcement

## Verification

### Rendering / prompt tests

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py -q`

结果：

- `15 passed`

### FU2 regression subset

- `pytest tests/data_knowledge/test_data_knowledge_retriever.py tests/data_agent/test_api.py data_acquisition_agent/tests/test_orchestrator.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py -q`

结果：

- `55 passed`

## Live Rerun Samples

本轮复跑 3 条目标样例：

1. `mx-high-risk-cohort`
2. `mx-behavior-writeback`
3. `mx-glossary-combo-writeback`

以下结论记录的是 FU2 prompt hardening 后的 live rerun 观察。

### 1. mx-high-risk-cohort

Request:

- `查询最近 7 天的高风险用户 cohort`

Observed prompt contract:

- `current request is the source of truth`: yes
- `do not copy literal dates`: yes
- `do not copy uid placeholders`: yes
- `prefer field names explicitly present in the retrieved catalog`: yes
- `do not inherit source filters from examples`: yes
- `keep relative time relative`: yes

Observed SQL:

```sql
SELECT
  user_uuid
FROM hive.dwd.dwd_w_apply
WHERE
  risk_level = 'high'
  AND apply_time >= date_sub(current_date, 7)
  AND dt >= date_format(date_sub(current_date, 7), 'yyyyMMdd');
```

Assessment:

- historical field drift: yes
- historical date/filter drift: no
- unresolved placeholder drift: no
- literal example-copy drift: no
- broad-scan risk: no

Conclusion:

- `partial`

Interpretation:

- FU2 已明显压下固定日期 / 固定 source filter 漂移
- 但 `user_uuid` 字段家族仍沿用历史风格，说明 field-family drift 还没完全收口

### 2. mx-behavior-writeback

Request:

- `用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior`

Observed prompt contract:

- current-request-first: yes
- anti-copy dates / source filters / placeholders: yes
- field grounding: yes
- under-specified writeback safe refusal: yes
- no broad scan guidance: yes

Observed generation result:

- `sql = null`
- structured output 最终未通过 schema 校验
- orchestrator 返回 `schema_validation_failed`

Assessment:

- historical field drift: no
- historical date/filter drift: no
- unresolved placeholder drift: no
- literal example-copy drift: no
- broad-scan risk: no

Conclusion:

- `partial`

Interpretation:

- FU2 已把 `{uid_str}` / `<target_users>` 这类 placeholder drift 压下
- 但当前 safe-refusal 仍以 `schema_validation_failed` 结束，而不是更平滑地形成可消费的 `sql=null` 结果
- 这不是 Safety Gate 问题，而是当前 structured output / writeback refusal 协调仍需 follow-up

### 3. mx-glossary-combo-writeback

Request:

- `结合 first_loan + never_overdue + behavior writeback 做 mx combo writeback`

Observed prompt contract:

- current-request-first: yes
- anti-copy dates / source filters / placeholders: yes
- field grounding: yes
- no source-filter inheritance: yes
- keep relative time relative: yes

Observed behavior:

- 组合意图仍被保留
- 生成 SQL 仍出现明显 historical family / historical filter 倾向
- 仍会回退到熟悉的 template-like SQL 结构

Assessment:

- historical field drift: yes
- historical date/filter drift: yes
- unresolved placeholder drift: no
- literal example-copy drift: yes
- broad-scan risk: no
- preserves combo intent: yes

Conclusion:

- `still_needs_runtime_followup`

Interpretation:

- FU2 没有破坏 combo intent
- 但模型仍会把多意图 writeback 请求拉回到熟悉的历史模板，说明 example-style drift 仍未完全被压住

## Overall Outcome

本轮 `M2A-RQ-FU2` 的结论是：

- historical date / source-filter drift：已明显改善
- unresolved placeholder drift：在 under-specified writeback 场景已明显降低
- few-shot literal-copy / historical field-family drift：仍然存在，尤其在 combo writeback 上最明显

整体状态：

- `still_needs_runtime_followup`

## Recommendation

当前不建议直接进入 `M2B`。

更合理的下一步是继续一个小范围 runtime follow-up，重点放在：

1. historical field-family drift 的进一步约束
2. combo writeback 的 anti-template guidance
3. under-specified writeback safe-refusal 与 structured output schema 之间的协调

只有当这 3 类问题继续收敛后，再进入 `M2B`，才更容易区分 retrieval 问题和 generation-style 问题。
