# M2A-RQ-FU2 Generation Style Drift Design

## Summary

`M2A-Runtime Quality` 第一轮和 `RQ-FU1` 已完成，当前剩余问题主要来自 generation style drift，而不是 seed 覆盖或 deterministic retrieval 缺失。

本阶段只处理：

- historical field-family drift
- historical date / source-filter drift
- unresolved placeholder drift
- few-shot literal-copy / broad-scan drift

本阶段不处理：

- retriever scoring 大结构
- seed 资产补齐
- `M1` SQL HITL 状态机
- `M1.5` Orchestrator Bridge
- `query_data`
- vector retrieval / embedding / rerank

## Problem Statement

当前 runtime rerun 已确认：

1. `mx-high-risk-cohort` 已能召回正确风险相关知识，但生成 SQL 仍会沿用历史 few-shot 中的字段别名、日期范围和 source filter。
2. `mx-behavior-writeback` 已能召回正确 behavior 资产，但生成 SQL 仍会产出 `{uid_str}` 这类模板变量。
3. `mx-glossary-combo-writeback` 已能保留组合意图，但会回退到熟悉的历史模板 SQL 结构。

这类问题说明当前瓶颈不在 retrieval，而在 prompt contract 仍允许 model 把 example 当作事实来源。

## Design Principles

1. 当前请求优先于历史 example。
2. example 只提供 pattern guidance，不提供默认日期、默认过滤器、默认 uid 模板。
3. 字段名选择必须由当前 retrieved catalog / glossary 支撑，不能仅凭历史 SQL 风格偷换字段家族。
4. prompt 负责减少 drift，Safety Gate 仍负责 unresolved placeholder enforcement。
5. 对 under-specified writeback 请求，优先安全拒绝，不生成 broad-scan 或 placeholder SQL。

## Planned Changes

### PromptContextAssembler

继续保持 SQL example 摘要化，不恢复 full SQL 注入。

新增固定 guidance：

- current request is the source of truth
- examples are pattern guidance only
- do not copy literal dates, partition ranges, source filters, uid placeholders, table aliases, or WHERE clauses from examples unless explicitly required by the current request and grounded by retrieved catalog/glossary
- prefer field names explicitly present in the retrieved catalog for the selected table and country
- do not substitute to a historical alias family unless that alias is present in retrieved catalog or glossary for the current country/table

behavior writeback 额外 guidance：

- define target cohort or use explicit uid list first
- join behavior source table by uid
- return uid plus requested behavior fields
- do not emit unresolved uid placeholders
- do not broad-scan the behavior table
- if the request has no cohort condition and no explicit uid list, return `sql=null` rather than inventing placeholders

### Prompt Assembler

在 Data Agent retrieved context 存在时，引入 `Current Request Priority Rules`：

- current user request is the source of truth
- retrieved examples are references, not requirements
- do not inherit dates, source codes, partition filters, table aliases, uid placeholders, or field-family substitutions unless explicitly required by the current request and grounded by retrieved context
- prefer field names explicitly present in retrieved catalog/glossary for the selected table and country
- do not invent placeholders for missing uid lists or cohorts

`sql=null` 拒绝指导只在 Data Agent SQL generation、尤其 `bucket_writeback` 且请求 under-specified 的场景出现。

## Safety Boundary

本阶段不改变 Safety Gate 主逻辑。

明确边界：

- prompt guidance 负责减少 drift
- Safety Gate 仍是 unresolved placeholder 的 enforcement layer
- 即使 FU2 后模型仍生成 placeholder，也必须继续由现有 Safety Gate blocked

## Acceptance Targets

重点 live rerun 样例：

1. `mx-high-risk-cohort`
2. `mx-behavior-writeback`
3. `mx-glossary-combo-writeback`

目标：

- `mx-high-risk-cohort` 不再明显继承无关 first-loan / never-overdue SQL 风格
- `mx-behavior-writeback` 不再生成 unresolved placeholder；若 under-specified，则 `sql=null`
- `mx-glossary-combo-writeback` 保留组合意图，但不回退到历史模板 SQL
