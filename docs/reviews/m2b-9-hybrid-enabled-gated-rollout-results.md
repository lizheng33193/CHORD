# M2B-9 Hybrid Enabled Gated Rollout Results

## Outcome

`M2B-9` 已实现 `hybrid_enabled` 的极小范围 gated rollout。

当前结果是：

- `hybrid_enabled` 默认仍关闭
- 只有 `MX + cohort_query + query_only + project_id allowlist + eval gate + kill switch off` 才允许生效
- success path 使用 `supplemental_candidates_v1`
- deterministic 仍然是 primary context
- final-attempt provenance 与 deterministic rerun 机制保持不变

## What Changed

- 新增 runtime config：
  - `HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS`
  - `HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE`
  - `HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH`
- `hybrid_enabled` 现在支持：
  - pre-trace gate
  - post-trace gate
  - enabled-specific fallback reasons
  - `final_generation_pass=hybrid_enabled`
  - `source_context=hybrid_enabled_attempt`
- bounded `candidate_attempt` 继续复用，但 enabled flow 会写入 `attempted_mode=hybrid_enabled`

## Verified Invariants

- public API response schema unchanged
- SQL HITL / approve / execute semantics unchanged
- orchestrator routing unchanged
- accepted supplements / discarded SQL / `retrieval_snapshot_json` 不暴露到 public API
- `hybrid_candidate` 既有行为未回退

## Regression Coverage

已覆盖：

- default disabled
- kill switch / eval gate / rollout allowlist fallback
- unsupported scope fallback
- vector unavailable fallback
- no accepted supplements fallback
- audit trace unavailable fallback
- enabled success path provenance
- blank SQL deterministic rerun
- rerun final failure surfacing
- final SQL version only persists final attempt
