# M2B-9 Hybrid Enabled Runtime Contract

## Core Invariant

`configured_mode=hybrid_enabled` 不等于 `effective_mode=hybrid_enabled`。

`hybrid_enabled` 只有在 pre-trace gate 与 post-trace gate 全部通过时，才允许成为真正生效的 runtime mode；否则必须回退到 `deterministic_only`。

## Pre-trace Gate

`evaluate_effective_mode()` 只负责 pre-trace gate，允许判定的条件固定为：

- `HYBRID_RETRIEVAL_ENABLED=true`
- config valid
- `HYBRID_RETRIEVAL_MODE=hybrid_enabled`
- `HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH=false`
- `country=mx`
- `run_type=cohort_query`
- request-scope `sql_kind=query_only`
- `HYBRID_RETRIEVAL_ALLOW_PROJECT_IDS` 命中
- `HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS` 命中
- `HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE=true`

其中 `HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS` 只匹配 normalized `ctx.project_id` exact match：

- 不匹配 `project_code`
- 不匹配 `apply_source`
- 不支持 alias / wildcard / prefix / contains / fuzzy

如果 `ctx.project_id` 为空或未命中 rollout allowlist，必须回退：

- `effective_mode=deterministic_only`
- `fallback_reason=hybrid_enabled_rollout_not_allowlisted`

## Post-trace Gate

即使 pre-trace gate 已允许尝试 `hybrid_enabled`，post-trace 阶段仍然可以把最终结果降回 `deterministic_only`。

以下任一条件不满足时，runtime 必须回退：

- vector artifact 不可读
- accepted supplements 为空
- audit trace 不可序列化 / 不可写

对应 fallback reason 固定为：

- `hybrid_enabled_vector_unavailable`
- `hybrid_enabled_no_accepted_supplements`
- `hybrid_enabled_audit_unavailable`

## Success Path

成功路径必须固定为：

```json
{
  "effective_mode": "hybrid_enabled",
  "final_generation_pass": "hybrid_enabled",
  "prompt_injection_mode": "supplemental_candidates_v1",
  "structured_sql_plan_provenance": {
    "plan_generation_pass": "hybrid_enabled",
    "prompt_injection_mode": "supplemental_candidates_v1",
    "source_context": "hybrid_enabled_attempt"
  }
}
```

不允许出现 `effective_mode=hybrid_enabled` 但 provenance 仍写成 `hybrid_candidate` 的混合语义。

## Rerun Contract

`hybrid_enabled` 复用 M2B-8.1 的 deterministic rerun 机制。

以下任一情况出现时，必须丢弃 enabled attempt 并 rerun deterministic：

- SQL `None` / blank
- candidate-only `HTTPException(422)`
- structured plan invalid
- generated `sql_kind != query_only`
- enabled generation failure

rerun 成功时，只持久化 rerun 的 final snapshot / SQL / SQL version / provenance。
rerun 失败时，返回 rerun 的最终错误，不落库半成品。

## Trace Contract

`hybrid_enabled` rollout 期间的 trace 至少定义以下字段：

- `configured_mode`
- `effective_mode`
- `fallback_applied`
- `fallback_reason`
- `kill_switch_applied`
- `rollout_gate_passed`
- `eval_gate_passed`
- `prompt_injection_mode`
- `final_generation_pass`
- `candidate_attempt`

`candidate_attempt` 在 v1 继续复用 bounded audit 结构，但 enabled flow 必须写死：

```json
{
  "candidate_attempt": {
    "attempted": true,
    "attempted_mode": "hybrid_enabled"
  }
}
```

## Non-authority Boundary

`hybrid_enabled` 是 grounding enhancement，不是执行授权。

因此它不得：

- 改变 public API schema
- 改变 SQL HITL / approve / execute 语义
- 改变 orchestrator routing
- 绕过人工审核
- 放宽现有 safety boundary
