# M2A-RQ-FU3 Field Grounding & Safe Refusal Design

## Goal

在 `M2A-RQ-FU2` 的 prompt anti-copy 基础上，继续收紧两个 runtime 边界：

1. field grounding：让 SQL 字段选择更明确受 retrieved catalog/glossary 支撑，并把未支撑字段显式暴露给 reviewer
2. under-specified `bucket_writeback`：把当前 `schema_validation_failed` 型安全拒绝，归一成 Data Agent 专属 `422` 业务语义

## Fixed Boundaries

本轮不改：

- `GenerateRequest` / `GenerateResponse` schema
- `data_acquisition_agent/orchestrator.py`
- `M1` SQL HITL 状态机
- `M1.5` Orchestrator Bridge
- `query_data`
- retriever scoring 大结构
- seed assets
- vector retrieval / embedding / rerank

## Design Decisions

### 1. Field grounding = Prompt + Risk

第一阶段不做 hard block。

原因：

- catalog 覆盖率尚不足以支撑全量强阻断
- CTE / alias / derived field / ambiguous field ownership 容易误杀
- 当前更适合让 reviewer 先“看见问题”，而不是让系统直接拒绝

因此本轮策略是：

- prompt 中输出 `table -> allowed fields`
- SQL 生成后做保守的 unsupported-field risk 检查
- 只标 warning / medium risk，不改变 `approve / execute` 状态机

### 2. Unsupported-field checker must be conservative

只标高置信 base-table field：

- `alias.field` 且 alias 能映射到 retrieved base table
- 单表 SQL 中的 unqualified field

不标 unsupported：

- 多表 SQL 中 table ownership 不明确的 unqualified field
- CTE 输出字段
- `SELECT ... AS ...` 派生字段
- 聚合别名
- 窗口函数别名
- 子查询输出字段
- 任何无法高置信映射到 retrieved base table 的字段

### 3. No global field bans

不全局 ban `user_uuid` / `apply_create_at` / 历史 alias 字段。

字段是否 unsupported，只由以下条件决定：

- 当前 selected table 是否在 retrieved catalog 中
- 当前字段是否被该 table 的 retrieved catalog/glossary 支撑

### 4. Safe refusal = Data Agent business error

under-specified `bucket_writeback` 不是普通 schema failure，也不是普通 non-SQL generation。

它的真实语义是：

- 写回请求缺少 explicit uid list 或 cohort 条件
- 系统不能安全生成 writeback SQL

因此对外使用新的 Data Agent 专属 `422` code：

- `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`

并保持：

- create：不创建 run / version
- revise：不创建新 version，不改变当前 run/version

### 5. Prompt is not the safety boundary

prompt guidance 只负责减少 drift：

- unresolved placeholder 的最终 enforcement 仍然由现有 Safety Gate 负责
- FU3 不修改 placeholder block 规则

## Expected Outcome

FU3 完成后：

- `mx-high-risk-cohort` 若仍发生 unsupported field-family drift，review detail 至少可显式看到 warning
- under-specified `mx-behavior-writeback` 不再对外表现成 `SCHEMA_VALIDATION_FAILED`
- `mx-glossary-combo-writeback` 若仍有 template drift，至少能暴露 unsupported-field 风险，帮助后续继续收口
