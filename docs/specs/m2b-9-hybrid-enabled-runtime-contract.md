# M2B-9 Hybrid Enabled Runtime Contract

## Core Invariant

`configured_mode=hybrid_enabled` 不等于 `effective_mode=hybrid_enabled`。

在 `M2B-9` 中，只有 gate 全部满足时，`hybrid_enabled` 才允许成为真正生效的 runtime mode。

## Future Enable Conditions

未来只有在以下条件同时满足时，才允许：

- `enabled=true`
- rollout allowlist hit
- `country=mx`
- `run_type=cohort_query`
- `sql_kind=query_only`
- vector artifact available
- accepted supplements available
- audit trace writable
- eval gate satisfied

以上任一条件不满足，都必须退回 `deterministic_only`。

## Fallback and Kill Switch Rules

以下条件必须立即触发回退：

- `HYBRID_RETRIEVAL_ENABLED=false`
- `HYBRID_RETRIEVAL_MODE=deterministic_only`
- rollout allowlist 为空或未命中
- vector artifact 不可读
- audit trace 不可写
- `country` / `run_type` / `sql_kind` 不支持
- eval gate 未满足

回退后的 contract 固定为：

- `effective_mode=deterministic_only`
- `fallback_applied=true`
- `fallback_reason=<reason>`

## Trace Contract

`hybrid_enabled` rollout 期间的 trace 至少定义以下字段：

- `configured_mode`
- `effective_mode`
- `fallback_applied`
- `fallback_reason`
- `kill_switch_applied`
- `rollout_gate_passed`

这些字段必须能解释：

- 为什么本次请求允许进入 `hybrid_enabled`
- 为什么本次请求被回退到 `deterministic_only`
- kill switch 是否参与了最终决策

## Non-authority Boundary

`hybrid_enabled` 是 grounding enhancement，不是执行授权。

因此它不得：

- 改变 public API schema
- 改变 SQL HITL / approve / execute 语义
- 绕过人工审核
- 放宽现有 safety boundary
