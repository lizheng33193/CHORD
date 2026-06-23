# M2A-Verify Sample Set Round 1

## Purpose

这 5 条样例用于验证 M2A 当前 deterministic retrieval + prompt context assembly 是否已经具备最小业务可用性。

## Case 1

- Case ID: `mx-high-risk-cohort`
- User request: `用 Data Agent 生成 SQL，查询最近 7 天高风险用户`
- Country: `mx`
- Run type: `cohort_query`
- Output bucket: `null`
- Expected retrieval focus:
  - 与 `mx` 相关的申请 / 风险 / 时间过滤表
  - “高风险用户” glossary 或近义词
  - `最近 7 天` 的时间字段与过滤线索
- Expected validation focus:
  - 不跨国家召回
  - 能否拿到可用于风险定义的字段
  - 能否拿到时间字段与 cohort SQL 模式
- Current likely gap hypothesis:
  - 缺 `高风险` glossary
  - 缺风险相关表/字段
  - 缺 `apply_time` 字段级 seed

## Case 2

- Case ID: `mx-behavior-writeback`
- User request: `用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior`
- Country: `mx`
- Run type: `bucket_writeback`
- Output bucket: `behavior`
- Expected retrieval focus:
  - `bucket 写回` 通用 glossary
  - `写回 behavior` 的 `mx` glossary
  - `uid` 必须返回
  - behavior 相关表和 join hints
- Expected validation focus:
  - prompt context 是否注入 `query_only` 与 `must include uid`
  - retrieval 是否能给出 behavior writeback 所需表结构
- Current likely gap hypothesis:
  - 缺 behavior source table
  - 缺 join path / grain / time field 说明
  - 缺 behavior writeback SQL example

## Case 3

- Case ID: `ph-first-loan-never-overdue`
- User request: `查询菲律宾首贷从未逾期用户`
- Country: `ph`
- Run type: `cohort_query`
- Output bucket: `null`
- Expected retrieval focus:
  - `ph_apply_orders`
  - `loan_count`
  - `history_overdue_count`
  - 菲律宾国家范围内的 example
- Expected validation focus:
  - 不串到 `mx`
  - 能否稳定命中 `ph` glossary 与 example
- Current likely gap hypothesis:
  - `loan_count` 在 glossary/example 中被引用，但 catalog field 未落 seed
  - 缺显式的菲律宾差异提醒

## Case 4

- Case ID: `mx-glossary-combo-writeback`
- User request: `找出墨西哥首贷且从未逾期的用户，并写回 behavior`
- Country: `mx`
- Run type: `bucket_writeback`
- Output bucket: `behavior`
- Expected retrieval focus:
  - glossary 同时命中：`首贷` / `从未逾期` / `写回 behavior`
  - `uid` writeback 约束
  - 首贷/逾期 cohort SQL example
- Expected validation focus:
  - 多 glossary term 是否能组合进入 context
  - example 是否与 writeback 约束一起工作
- Current likely gap hypothesis:
  - 缺 writeback 专用 example
  - 缺 behavior writeback 所需源表与字段

## Case 5

- Case ID: `ph-error-case-repair-recall`
- User request: `修复菲律宾首贷从未逾期 SQL，避免使用 withdraw_uuid`
- Country: `ph`
- Run type: `cohort_query`
- Output bucket: `null`
- Expected retrieval focus:
  - open error case
  - 菲律宾申请表
  - 首贷 / 从未逾期 glossary
- Expected validation focus:
  - error case recall 是否生效
  - prompt context 是否出现“避免使用 withdraw_uuid”类负例提醒
- Current likely gap hypothesis:
  - 当前没有可复用的 open error case 基线
  - 缺国家差异负例 seed

## Round 1 Success Criteria

首轮不要求 5/5 直接生成正确 SQL，但要求：

1. 每条样例都能明确看到 retrieval 命中了什么
2. 每条样例都能归因到“知识够不够”而不只是“模型写得好不好”
3. 每条样例都能产出下一轮 seed 补齐建议
