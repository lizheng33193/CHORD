# M2A-Verify Seed Gap Round 1

## Summary

基于当前 `data_knowledge_seed/`、`app/data_knowledge/retriever.py` 与 `PromptContextAssembler` 的静态审阅，M2A 已具备最小可验证骨架，但距离真实业务可用还有明显知识缺口。

当前 seed 的主要问题不是“方向错”，而是覆盖面过窄：

- `mx` / `ph` 都只有 1 张 catalog table
- glossary 只覆盖了 `首贷 / 从未逾期 / 写回 behavior / bucket 写回`
- SQL examples 只覆盖了 `首贷从未逾期`
- 没有任何 seed 级 open error case

## P0 Gaps

### 1. `loan_count` 被 glossary/example 依赖，但 catalog field 未落 seed

- Impact:
  - `mx-first-loan-never-overdue`
  - `ph-first-loan-never-overdue`
  - glossary combo requests
- Current state:
  - `mx/glossary.yaml` 和 `mx/sql_examples.yaml` 都使用了 `loan_count`
  - `ph/glossary.yaml` 和 `ph/sql_examples.yaml` 也使用了 `loan_count`
  - 但 `mx/catalog.yaml` 与 `ph/catalog.yaml` 的 `fields` 中都没有 `loan_count`
- Recommendation:
  - 补 `dwd_w_apply.loan_count`
  - 补 `ph_apply_orders.loan_count`

### 2. 缺风险相关 glossary / table / field，`mx` 高风险样例无法有效验证

- Impact:
  - `mx-high-risk-cohort`
- Current state:
  - 没有 `高风险` / `risk` / `risk_user` 相关 glossary
  - 没有风险评分、风险等级、命中策略等字段
- Recommendation:
  - 至少补一个 `high_risk_user` glossary
  - 至少补一个 `mx` 风险字段或表说明

### 3. 缺 behavior writeback 源表与 join hint

- Impact:
  - `mx-behavior-writeback`
  - `mx-glossary-combo-writeback`
- Current state:
  - 有 `bucket 写回` 和 `写回 behavior` glossary
  - 但没有 behavior 源表、行为字段、join 路径、时间字段
- Recommendation:
  - 增加 behavior source table seed
  - 增加核心 behavior fields
  - 增加 writeback 所需 join hint

### 4. 缺菲律宾国家差异负例知识

- Impact:
  - `ph-first-loan-never-overdue`
  - `ph-error-case-repair-recall`
- Current state:
  - 没有任何 seed 明确表达“菲律宾不要使用 withdraw_uuid”或类似国家差异
- Recommendation:
  - 补一个 `ph` glossary 或 error case，用于表达该类负例约束

### 5. 缺可验证的 open error case 基线

- Impact:
  - `ph-error-case-repair-recall`
- Current state:
  - 当前 seed 里没有 error case
  - retriever 虽支持 open error case，但首轮验证没有天然样本
- Recommendation:
  - 在 verify 环节人工创建一条 open error case
  - 或补一个最小 manual error case fixture

## P1 Gaps

### 6. 缺 `apply_time` 的字段级 seed

- Impact:
  - `mx-high-risk-cohort`
  - 任意 `最近 7 天` 请求
- Current state:
  - `catalog table` 有 `time_field=apply_time`
  - 但 fields 列表没有 `apply_time`
- Recommendation:
  - 补 `apply_time` field seed，并注明时间过滤语义

### 7. 缺时间类 glossary

- Impact:
  - `最近 7 天`
  - `注册同周`
- Current state:
  - 当前没有相对时间窗口 glossary
- Recommendation:
  - 补最小时间类 glossary 或在样例执行时记录为 expected gap

### 8. 缺 bucket_writeback 专用 SQL example

- Impact:
  - `mx-behavior-writeback`
  - `mx-glossary-combo-writeback`
- Current state:
  - 现有 example 只有 cohort query
- Recommendation:
  - 增加一个 `bucket_writeback + behavior` 示例

## P2 Gaps

### 9. 通用 glossary 覆盖面偏窄

- Current state:
  - `common/glossary.yaml` 只覆盖 `bucket 写回`
- Recommendation:
  - 后续可考虑把高频跨国家业务词逐步沉淀到 common

### 10. Prompt context 当前只输出摘要，不输出 example SQL pattern 细节

- Current state:
  - `PromptContextAssembler` 只输出 example request / summary / tables / fields
- Verify implication:
  - 如果 retrieval 命中了 example，但生成质量仍弱，需要区分是“example 不够”还是“example 注入粒度不够”

## Recommended Immediate Backlog

首轮 verify 前最值得优先补齐的 seed：

1. `mx/ph` 的 `loan_count` field
2. `mx` 的 `apply_time` field
3. `mx` 的最小 risk glossary / field
4. `mx` behavior writeback source table + join hint
5. `ph` 的国家差异负例知识
6. 至少 1 条可验证的 open error case 样本
