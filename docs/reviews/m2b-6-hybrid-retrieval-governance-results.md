# M2B-6 Hybrid Retrieval Governance Results

## Summary

M2B-6 只完成治理设计，不进入 runtime 实现。

本阶段的核心结论是：

- `M2B-5` 已证明 hybrid retrieval 在离线 baseline 上有稳定收益
- 但 future runtime 接入前，必须先把 mode、fallback、audit、gate、rollout、SQL safety 边界定死
- 首个实际 rollout boundary 必须保守收口在 `MX + query_only + cohort_query`

## Key Decisions

- 默认值必须是：
  - `enabled=false`
  - `retrieval_mode=deterministic_only`
- `effective_mode` 只能等于或低于 `configured_mode`
- 任何 vector/hybrid 异常都必须回退 deterministic
- `hybrid_shadow` 不影响 prompt，只写 audit
- `hybrid_candidate` 不改变 public API shape，不向前端暴露 hybrid 候选
- `MX bucket_writeback` 与 `TH cohort_query` 只保留 future gate
- `TH bucket_writeback` 继续 out of scope

## Safety Position

核心安全语句固定为：

> Hybrid retrieval is a grounding enhancement, not an execution authority.

因此：

- hybrid retrieval 不能绕过 SQL HITL
- hybrid retrieval 不能直接生成或执行 SQL
- hybrid retrieval 不能降低现有 deterministic review

## Next Step

后续若要接入 runtime，必须作为 `M2B-7` 或等价阶段单独实现：

- 接 mode/config wiring
- 接 fallback enforcement
- 接 audit trace persistence
- 接 rollout allowlist

但不在 M2B-6 本阶段实施
