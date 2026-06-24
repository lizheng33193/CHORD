# M2A-Verify Round 1 Results

## Scope

本轮在隔离的临时 auth DB 中执行了 5 条固定样例，真实走通：

- seed import
- `DataKnowledgeRetriever`
- `PromptContextAssembler`
- `DataAcquisitionOrchestrator.generate(...)`
- `run_sql_safety_gate(...)`

本轮没有修改 seed，只记录真实表现与 gap。

## Environment

- Date: 2026-06-23
- Branch: `codex/m2-data-agent-knowledge-rag`
- Model mode: `vertex`
- Model route observed in logs: `gemini-2.5-flash`
- Knowledge source: imported `common + mx + ph` seed bundle
- Special setup:
  - 为验证 error case recall，额外在隔离 DB 中插入了 1 条手工 `open` error case：
    - `case:ph-withdraw-uuid`

## Executive Summary

Round 1 的总体判断是：

- `ph` 的“首贷 + 从未逾期”基础 cohort 路径已经具备最小可用性。
- `ph` 的 error case recall 路径可验证，说明 M2A 的 repair memory 方向成立。
- `mx` 的高风险 cohort 与 behavior writeback 仍主要受知识覆盖不足影响。
- 结构化 JSON 生成链路存在真实模型不稳定性，5 条样例中有 2 条直接落入 `model output failed schema validation`。
- 当前 Safety Gate 只能判断“是否危险”，还不能识别 `uid IN ({uid_str})` 这类 unresolved placeholder 问题。

## Case 1

### Meta

- Case ID: `mx-high-risk-cohort`
- User request: `用 Data Agent 生成 SQL，查询最近 7 天高风险用户`
- Country: `mx`
- Run type: `cohort_query`
- Output bucket: `null`

### Retrieval Result

- Retrieved tables:
  - `dwd_w_apply`
- Retrieved fields:
  - `dwd_w_apply.uid`
- Retrieved glossary terms:
  - `写回 behavior`
  - `bucket 写回`
- Retrieved SQL examples:
  - none
- Retrieved error cases:
  - none

### Prompt Context

- 只拿到了 `dwd_w_apply` 和 `uid`
- 没有命中任何高风险、时间窗口、风险字段或风险表示例
- 反而误召回了 writeback glossary

### Generation Result

- Generated SQL: none
- Safety Gate: none
- Runtime result:
  - `OrchestratorError: model output failed schema validation`

### Human Review

- Verdict: `fail`
- Reason:
  - 这条样例在知识层就已经明显缺关键风险语义
  - 最终又叠加了模型 JSON 输出退化，无法进入 SQL 审核阶段

### Problem Classification

- `glossary_gap`
- `field_gap`
- `retriever_scoring_gap`
- `model_generation_gap`

### Seed Gap

- 缺 `高风险用户` glossary
- 缺风险字段与风险表
- 缺时间字段级 seed
- 当前关键词打分会把高风险 query 误拉到 writeback 术语

## Case 2

### Meta

- Case ID: `mx-behavior-writeback`
- User request: `用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior`
- Country: `mx`
- Run type: `bucket_writeback`
- Output bucket: `behavior`

### Retrieval Result

- Retrieved tables:
  - `dwd_w_apply`
- Retrieved fields:
  - `dwd_w_apply.uid`
- Retrieved glossary terms:
  - `写回 behavior`
  - `bucket 写回`
- Retrieved SQL examples:
  - none
- Retrieved error cases:
  - none

### Prompt Context

- 正确注入了：
  - `output_bucket=behavior`
  - `query_only SQL only`
  - `result must include uid`
- 但没有 behavior source table、join hint、行为字段、时间字段

### Generation Result

- Generated SQL kind: `query_only`
- Safety Gate: `passed`
- Generated SQL summary:
  - 使用了 `hive.dwb.dwb_b1_data_burying_point`
  - 走了 `ROW_NUMBER()` 截断逻辑
  - 包含 `uid IN ({uid_str})` unresolved placeholder
- Human review result:
  - `fail`

### Human Review

- Verdict: `fail`
- Reason:
  - SQL 虽然是 query_only，且包含 `uid`
  - 但它依赖 few-shot 里的工业化示例，而不是当前 knowledge seed
  - `{uid_str}` 是未解析占位符，不能直接进入真实审核执行
  - 当前没有 writeback 专用 example，也没有 behavior 表结构知识支持

### Problem Classification

- `catalog_gap`
- `join_hint_gap`
- `example_gap`
- `model_generation_gap`
- `safety_gate_gap`

### Seed Gap

- 缺 behavior source table
- 缺 behavior field / join hint / time field
- 缺 writeback 专用 active example
- Safety Gate 未来应考虑识别 unresolved placeholder

## Case 3

### Meta

- Case ID: `ph-first-loan-never-overdue`
- User request: `查询菲律宾首贷从未逾期用户`
- Country: `ph`
- Run type: `cohort_query`
- Output bucket: `null`

### Retrieval Result

- Retrieved tables:
  - `ph_apply_orders`
- Retrieved fields:
  - `ph_apply_orders.history_overdue_count`
- Retrieved glossary terms:
  - `从未逾期`
  - `首贷`
- Retrieved SQL examples:
  - `example:ph-first-loan-never-overdue`
- Retrieved error cases:
  - none

### Prompt Context

- 国家范围正确，没有串到 `mx`
- glossary、table、example 都命中了
- 仍然缺 `loan_count` 的 catalog field 行

### Generation Result

- Generated SQL kind: `query_only`
- Safety Gate: `passed`
- Generated SQL:

```sql
SELECT
  uid,
  loan_count,
  history_overdue_count
FROM
  ph_apply_orders
WHERE
  loan_count = 1
  AND history_overdue_count = 0;
```

### Human Review

- Verdict: `pass_with_gap`
- Reason:
  - SQL 语义正确
  - 国家选择正确
  - 能明显看出 example + glossary 已经帮助模型收敛
  - 但 `loan_count` 只存在于 glossary/example，不在 catalog field 中

### Problem Classification

- `field_gap`

### Seed Gap

- 补 `ph_apply_orders.loan_count`

## Case 4

### Meta

- Case ID: `mx-glossary-combo-writeback`
- User request: `找出墨西哥首贷且从未逾期的用户，并写回 behavior`
- Country: `mx`
- Run type: `bucket_writeback`
- Output bucket: `behavior`

### Retrieval Result

- Retrieved tables:
  - `dwd_w_apply`
- Retrieved fields:
  - `dwd_w_apply.uid`
  - `dwd_w_apply.max_overdue_days`
- Retrieved glossary terms:
  - `写回 behavior`
  - `从未逾期`
  - `首贷`
  - `bucket 写回`
- Retrieved SQL examples:
  - none
- Retrieved error cases:
  - none

### Prompt Context

- glossary 组合命中是成功的
- writeback 约束也注入了
- 但依然没有 behavior source table，也没有 writeback example

### Generation Result

- Generated SQL: none
- Safety Gate: none
- Runtime result:
  - `OrchestratorError: model output failed schema validation`

### Human Review

- Verdict: `fail`
- Reason:
  - 这条样例说明 glossary 组合命中本身没有问题
  - 失败主要来自“缺 writeback example / 缺 behavior schema + 模型结构化输出退化”双重叠加

### Problem Classification

- `example_gap`
- `catalog_gap`
- `join_hint_gap`
- `model_generation_gap`

### Seed Gap

- 缺 writeback 专用 example
- 缺 behavior source table / join hint

## Case 5

### Meta

- Case ID: `ph-error-case-repair-recall`
- User request: `修复菲律宾首贷从未逾期 SQL，避免使用 withdraw_uuid`
- Country: `ph`
- Run type: `cohort_query`
- Output bucket: `null`

### Preconditions

- Manual setup:
  - 注入了 1 条 `open` error case：`case:ph-withdraw-uuid`

### Retrieval Result

- Retrieved tables:
  - `ph_apply_orders`
- Retrieved fields:
  - `ph_apply_orders.uid`
  - `ph_apply_orders.history_overdue_count`
- Retrieved glossary terms:
  - `从未逾期`
  - `首贷`
  - `bucket 写回`
- Retrieved SQL examples:
  - `example:ph-first-loan-never-overdue`
- Retrieved error cases:
  - `case:ph-withdraw-uuid`

### Prompt Context

- error case 成功进入 context
- context 明确包含：
  - `Philippines tables do not expose withdraw_uuid`
  - `Do not use mx-only field withdraw_uuid in ph cohort queries`

### Generation Result

- Generated SQL kind: `query_only`
- Safety Gate: `passed`
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

### Human Review

- Verdict: `pass_with_gap`
- Reason:
  - error case recall 确实生效了
  - SQL 避开了 `withdraw_uuid`
  - 国家差异约束已经能在 prompt 中发挥作用
  - 但当前这条验证依赖手工插入 error case，说明 seed / memory 里还没有自然基线

### Problem Classification

- `error_case_gap`
- `field_gap`

### Seed Gap

- 缺 seed 或自然沉淀的 `ph` 国家差异 error case 基线
- `loan_count` 仍应补 catalog field

## Confirmed Gaps After Round 1

Round 1 已把以下缺口从“静态推测”变成了“动态确认”：

1. `loan_count` field 缺失
2. `mx` 风险知识缺失
3. behavior writeback 缺 source table / join hint / example
4. `ph` 国家差异负例知识缺乏天然基线
5. unresolved placeholder 目前不会被 Safety Gate 拦住
6. retriever 对中文请求存在 false positive 术语误召回
7. Data Acquisition 结构化 JSON 输出在复杂请求上仍会退化

## Recommended Next Step

下一步应进入：

- `M2A-Verify Seed Patch 1`

但顺序上仍建议：

1. 先基于本轮结果确认 seed patch 范围
2. 再统一补第一批 catalog / glossary / examples / error cases
3. patch 后回跑这 5 条样例，比较前后变化
