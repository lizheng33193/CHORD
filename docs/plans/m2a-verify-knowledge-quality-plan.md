# M2A-Verify Knowledge Quality Plan

## Goal

在不新增架构能力的前提下，验证 M2A 是否真实提升了 Data Agent 的 SQL 生成质量，并通过固定样例发现当前 seed / glossary / examples / error cases 的缺口。

本阶段明确不做：

- vector DB / embedding / rerank
- 新 public API
- orchestrator `query_data` 改造
- M1 SQL HITL 状态机改造
- M1.5 artifact contract 改造

## Outputs

M2A-Verify 首轮交付物固定为 3 类：

1. 固定样例集
2. 可复用验证记录模板
3. 首轮 seed gap 清单

相关文档：

- `docs/reviews/m2a-verify-runbook-template.md`
- `docs/reviews/m2a-verify-sample-set-round1.md`
- `docs/reviews/m2a-verify-seed-gap-round1.md`

## Verification Scope

首轮固定覆盖以下 5 类请求：

1. `mx` 高风险 cohort query
2. `mx` behavior bucket_writeback
3. `ph` 首贷从未逾期 cohort query
4. 需要 glossary 同时命中“首贷 / 从未逾期 / 写回 behavior”的请求
5. 需要召回 error case 的修复型请求

## Per-Case Checklist

每个样例都必须记录：

- 用户原始请求
- `country / run_type / output_bucket`
- retrieved tables
- retrieved fields
- retrieved glossary terms
- retrieved examples / error cases
- assembled knowledge prompt context
- generated SQL
- Safety Gate 结果
- 人工审核结论
- 是否需要补 seed

## Execution Flow

每条样例按以下顺序执行：

1. 准备请求输入与前置条件
2. 触发 `DataAgentService.create_run()` 或 `revise_run()`
3. 记录 knowledge retrieval 结果
4. 记录 assembled knowledge prompt context
5. 记录生成 SQL 与 Safety Gate 输出
6. 记录人工审核结论
7. 归纳 seed / glossary / example / error-case gap

## What Counts as a Good Verify Result

M2A-Verify 的目标不是“5 条样例一次全对”，而是系统性回答这些问题：

- 当前 deterministic retriever 能否稳定命中正确国家的表与字段
- glossary 是否足够支持首贷、逾期、writeback 等核心业务词
- SQL example memory 是否已经能对真实问题提供帮助
- error case memory 是否具备最小可验证路径
- 当前知识缺口主要落在 catalog、glossary、examples 还是 error cases

## Acceptance

完成首轮 M2A-Verify 的最低验收标准：

1. 5 条固定样例均有完整记录
2. 每条样例都有明确的 retrieval 结果与 gap 判断
3. 首轮 gap 清单按优先级分类
4. 能明确区分“代码问题”与“知识资产缺口”
5. 为后续 seed 补齐提供可直接执行的 backlog

## Out of Scope

本阶段暂不做：

- 将 draft examples 自动升级为 active
- 大规模 seed 扩库
- 线上真实执行成功率统计
- prompt 结构重写
- M2B 混合检索与语义检索
