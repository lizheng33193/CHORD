# M2B-8 Hybrid Candidate Runtime Grounding Plan

## Summary

- `M2B-8` 只打开 `hybrid_candidate` 的受控 prompt grounding。
- deterministic retrieval 仍是 primary context，vector accepted supplements 只作为 `supplemental_candidates_v1` 独立区块追加进 prompt。
- `hybrid_shadow` 继续只审计不入 prompt；`hybrid_enabled` 继续禁用。

## Runtime Contract

- rollout 只允许：
  - `country=mx`
  - `run_type=cohort_query`
- `hybrid_candidate` 必须满足：
  - `HYBRID_RETRIEVAL_ENABLED=true`
  - `HYBRID_RETRIEVAL_MODE=hybrid_candidate`
  - allowlist 命中
  - config 有效
  - vector artifact 可读
  - accepted supplements `> 0`
- 任何异常或越界都必须回退 `deterministic_only`

## Prompt Injection

- supplemental section 命名固定为 `supplemental_candidates_v1`
- section 只能追加，不能覆盖 deterministic context
- section 明确声明：
  - supplemental only
  - deterministic 优先
  - conflict 时 deterministic 胜出

## Final Output Provenance

```text
最终 SQL / SQL plan / SQL version，
必须来自 final effective_mode 对应的 prompt。
```

## Rerun Rule

- candidate attempt 若 `sql_kind == query_only`
  - 保留 candidate result
  - `final_generation_pass=hybrid_candidate`
- candidate attempt 若 `sql_kind != query_only`
  - 丢弃 candidate result
  - 用 deterministic-only prompt rerun
  - 只持久化 rerun 结果
  - `final_generation_pass=deterministic_rerun`

## Boundaries

- 不改 public API schema
- 不改 SQL HITL / approve / execute
- 不改 runtime retriever scoring
- 不接真实 embedding 或外部向量库
