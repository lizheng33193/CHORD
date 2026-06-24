# M2A-RQ-FU4 Canonical Field Policy & SQL Intent Plan Design

## Goal

在 `M2A-RQ-FU3` 的 field grounding 和 safe refusal 基础上，继续收紧两类 generation-control 问题：

1. canonical field policy：字段虽然被 retrieved catalog/glossary 支撑，但不一定是当前业务语义下的 preferred field
2. sql intent plan：`bucket_writeback` 尤其 combo writeback 请求，必须先形成稳定的 plan，再生成 SQL

## Fixed Boundaries

本轮不改：

- `GenerateRequest` / `GenerateResponse` schema
- `data_acquisition_agent/orchestrator.py`
- `M1` SQL HITL 状态机
- `M1.5` Orchestrator Bridge
- `query_data`
- retriever scoring
- seed assets
- vector retrieval / embedding / rerank
- knowledge schema / metadata / seed format

## Design Decisions

### 1. Canonical field policy = Prompt + Warning

FU4 继续不做 hard block。

原因：

- 当前目标是压 generation drift，而不是升级 knowledge schema
- 只靠 prompt 不够稳定，但直接进 metadata-driven 会明显扩大范围
- 当前更适合先让 prompt 和 reviewer 同时“看见 preferred vs alternative”

因此本轮策略是：

- 新增 code-level canonical field policy 单一来源
- prompt 中渲染 `preferred / alternatives` guidance
- SQL 生成后做 `NON_CANONICAL_FIELD` warning-only 检查

### 2. Canonical policy must have a single source of truth

本轮新增：

- `app/data_knowledge/canonical_fields.py`

它只承载内部 code-level policy：

- 不是 knowledge schema
- 不是 seed
- 不是 public API

本轮只覆盖当前已证实 drift 的窄集合：

- `dwd_w_apply.user_identifier`: `uid` preferred, `user_uuid` alternative
- `dwd_w_apply.apply_time`: `apply_time` preferred, `apply_create_at` alternative
- `dwd_w_apply.risk_level`: `risk_level` preferred, `risk_label` alternative

### 3. Table matching must normalize table names

canonical policy 与 runtime warning 不能直接拿 SQL 原文 table token 做精确字符串比较。

本轮统一 normalize：

- 去掉 catalog/schema prefix
- 去掉反引号和引号
- 安全情况下按 base table name 匹配

例如：

- `hive.dwd.dwd_w_apply` -> `dwd_w_apply`
- `` `dwd_w_apply` `` -> `dwd_w_apply`

### 4. NON_CANONICAL_FIELD and UNSUPPORTED_FIELD are different

边界写死：

- `UNSUPPORTED_FIELD`：字段未被当前 retrieved catalog/glossary 支撑
- `NON_CANONICAL_FIELD`：字段被当前 retrieved catalog/glossary 支撑，但命中 `alternative -> preferred` 映射

因此：

- `user_uuid` 若未被 grounding 支撑 -> `UNSUPPORTED_FIELD`
- `user_uuid` 若已被 grounding 支撑，且 policy 推荐 `uid` -> `NON_CANONICAL_FIELD`
- `uid` 若是 preferred -> 不 warning

### 5. NON_CANONICAL_FIELD remains warning-only

`NON_CANONICAL_FIELD` 只进入现有 `safety_result.warnings`：

- 不改变 `safety_status`
- 不触发 blocked
- 不改变 approve / execute flow
- 不改变 `M1` 状态机

### 6. SQL intent plan is an internal contract

`sql_intent_plan` 的定位是：

- prompt 内结构化 guidance
- retrieval snapshot 内部调试摘要
- rerun / review 文档中的分析依据

它不是：

- public API schema
- DB entity
- 前端依赖结构

### 7. Under-specified writeback still refuses early

如果 `bucket_writeback` 请求 under-specified：

- 继续返回 `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`
- 不伪造 cohort plan
- 不生成 SQL

`sql_intent_plan` 只在 writeback request 已 sufficiently specified 时渲染完整内容。

### 8. required_fields must be grounded

`sql_intent_plan.required_fields` 只能基于当前 retrieved context 已经 grounded 的字段渲染。

本轮对 `output_bucket=behavior` 的最小意图约束是：

- `uid`
- `timestamp_`
- `eventname`

但只有当这些字段已被当前 retrieved catalog/glossary 支撑时，才写入 `required_fields`。

若缺失：

- 不发明字段
- 只在 prompt / rerun 结果里保留 grounded-field gap 信息

## Expected Outcome

FU4 完成后：

- `mx-high-risk-cohort` 若仍使用 `user_uuid` / `apply_create_at`，至少能被解释为 grounded alternative，并以 `NON_CANONICAL_FIELD` 暴露给 reviewer
- `mx-behavior-writeback` 继续保持 safe refusal，不生成 broad scan / placeholder SQL
- `mx-glossary-combo-writeback` 在 prompt 中先形成 cohort / join / required fields / forbidden patterns，再约束 SQL generation
- 若 combo writeback 仍明显回退到 historical template SQL，则说明下一步需要 `FU5: Plan Validation / Plan-to-SQL Consistency Review`，而不是直接进入 `M2B`
