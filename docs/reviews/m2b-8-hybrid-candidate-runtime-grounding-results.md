# M2B-8 Hybrid Candidate Runtime Grounding Results

`M2B-8.1` hardens `M2B-8` by sealing candidate-only failure fallback and final-attempt structured plan provenance.

## Outcome

- `hybrid_candidate` 已在严格门控下进入内部 prompt。
- deterministic retrieval 仍然是 primary context。
- accepted supplements 只会以 `supplemental_candidates_v1` 独立区块追加进入 prompt。
- `hybrid_shadow` 继续只写 trace；`hybrid_enabled` 继续强制 fallback。
- candidate-only failure fallback 与 final-attempt provenance 现已封口。

## What Changed

- `app/data_agent/hybrid_runtime.py`
  - `hybrid_candidate` mode evaluator 现已生效
  - `hybrid_candidate` 不再依赖 `shadow_sample_rate`
  - 新增 `supplemental_candidates_v1` section builder
  - trace 新增 `prompt_candidate_count`、`final_generation_pass`、`candidate_attempt`
- `app/data_agent/service.py`
  - `create_run()` / `revise_run()` 接入 candidate attempt
  - candidate empty / unusable SQL、candidate-only `HTTPException(422)`、candidate plan invalid、candidate result 非 `query_only` 时触发 deterministic rerun
  - 只持久化 final public SQL version
  - `structured_sql_plan_provenance` 与 `context_hash` 改为 final-attempt scoped
- `app/data_knowledge/prompt_context.py`
  - 新增 section append helper，用于保持 deterministic prompt 主体不变，只做追加
- docs
  - 更新 `M2B-6` runtime contract / audit schema
  - 新增 `M2B-8` plan / results
  - 更新 `PLANNING.md` / `TASK.md`

## Runtime Guarantees

- final output provenance invariant 已落地：
  - `effective_mode=deterministic_only`
    - final SQL / structured_sql_plan / SQL version / context_hash 必须来自 deterministic-only prompt
  - `effective_mode=hybrid_candidate`
    - final SQL / structured_sql_plan / SQL version / context_hash 才允许来自 candidate prompt
- discarded candidate attempt：
  - 不创建 reviewable SQL version
  - 不进入 approval flow
  - 不暴露给 public API
- discarded candidate snapshot 不会成为 final snapshot，本体只保留 bounded `candidate_attempt` summary
- candidate generation 失败时，若 deterministic 主链路可用，则自动 deterministic rerun

## Verification Snapshot

- `pytest tests/data_agent/test_hybrid_shadow_config.py tests/data_agent/test_hybrid_shadow_runtime.py -q`

覆盖：

- `hybrid_candidate` allowlist / mode wiring
- candidate prompt 注入
- candidate `sql=None` / blank / `_require_generated_sql()` 422 fallback
- `sql_kind` mismatch 时 deterministic rerun
- candidate generation failure fallback
- candidate plan invalid fallback
- final SQL version 只来自 final attempt
- final snapshot / `context_hash` / `structured_sql_plan_provenance` 与 final attempt 对齐
- `hybrid_enabled` 继续禁用

## Current Limits

- 当前 candidate rollout 仍只支持 `MX + cohort_query`
- `bucket_writeback` / `TH` 继续 fallback
- `M2B-9` 之前必须继续保持 final-attempt provenance invariant
- hybrid retrieval 仍然只是 grounding augmentation，不是 execution authority
