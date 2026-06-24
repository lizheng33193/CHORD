# M2A-Runtime Quality Baseline

## Scope

本基线文档只提炼 `M2A-Verify Round 1` 与 `Seed Patch 1/1.1` 之后仍然存在的运行时问题。

它不是设计文档，不定义实现方案；只固定下一阶段为什么需要启动 `M2A-Runtime Quality`。

来源文档：

- `docs/reviews/m2a-verify-round1-results.md`
- `docs/reviews/m2a-verify-seed-patch1-results.md`

## Confirmed Current State

截至 `Seed Patch 1/1.1`，以下事实已被确认：

- `M2A` 的 DB-backed knowledge store、deterministic retriever、prompt context assembler、`DataAgentService.create_run()` / `revise_run()` 接入已经成立。
- `ph` 的 `loan_count` field gap 已关闭。
- behavior source table / fields / example 已进入 writeback context。
- `ph` 国家差异 error case recall 不再依赖手工注入。
- `mx` 高风险与时间窗口知识已经能进入 context。

## Remaining Runtime Quality Problems

### 1. unresolved placeholder 未被 Safety Gate 拦截

`Seed Patch 1` 已确认模型仍可能生成：

- `{uid_list_placeholder}`
- `{uid_str}`

这类 SQL 已经有文本，但不是可审核、可执行 SQL。

当前问题不是 knowledge seed 缺失，而是 Safety Gate 缺少 dedicated placeholder rule。

### 2. retriever 仍存在 table-level false positive

`Seed Patch 1` 已确认：

- `mx high-risk cohort` 仍可能召回 `dwb_b1_data_burying_point`

这说明 deterministic retriever 目前仍会把弱相关 behavior table 放进高风险 cohort context。

### 3. SQL example / few-shot 风格仍然过强

`Seed Patch 1` 已确认：

- behavior writeback 场景虽然已命中正确 example
- 但模型生成仍 heavily shaped by historical few-shot patterns
- 复杂 combo writeback 场景仍会向熟悉的 few-shot 结构回退

当前问题不再是“有没有 example”，而是“example 如何影响生成风格”。

### 4. structured output fallback 仍需独立工程项

`Round 1` 曾出现结构化 JSON 失败。

`Seed Patch 1` 虽然改善了样例结果，但当前运行时仍缺少独立、可验证的 structured output fallback：

- fenced JSON
- JSON 前后夹杂说明文字
- 缺字段 / 字段类型错误
- 非 JSON 输出

这些仍需要明确 parser / validation / controlled failure 语义。

## What This Stage Does Not Mean

启动 `M2A-Runtime Quality` 不意味着：

- 继续伪装成 seed patch
- 开始 `M2B`
- 引入 vector DB / embedding / reranker
- 重构 `M1 SQL HITL`
- 改动 `M1.5 Orchestrator Bridge`

## Baseline Acceptance For Next Stage

本基线确认后，下一阶段应聚焦：

1. placeholder safety check
2. retriever false positive 收敛
3. prompt context / example pattern guidance
4. structured output fallback 与可解释失败
