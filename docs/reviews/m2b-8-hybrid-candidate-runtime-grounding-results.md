# M2B-8 Hybrid Candidate Runtime Grounding Results

## Outcome

- `hybrid_candidate` 已在严格门控下进入内部 prompt。
- deterministic retrieval 仍然是 primary context。
- accepted supplements 只会以 `supplemental_candidates_v1` 独立区块追加进入 prompt。
- `hybrid_shadow` 继续只写 trace；`hybrid_enabled` 继续强制 fallback。

## What Changed

- `app/data_agent/hybrid_runtime.py`
  - `hybrid_candidate` mode evaluator 现已生效
  - `hybrid_candidate` 不再依赖 `shadow_sample_rate`
  - 新增 `supplemental_candidates_v1` section builder
  - trace 新增 `prompt_candidate_count`、`final_generation_pass`、`candidate_attempt`
- `app/data_agent/service.py`
  - `create_run()` / `revise_run()` 接入 candidate attempt
  - candidate result 非 `query_only` 时触发 deterministic rerun
  - 只持久化 final public SQL version
- `app/data_knowledge/prompt_context.py`
  - 新增 section append helper，用于保持 deterministic prompt 主体不变，只做追加
- docs
  - 更新 `M2B-6` runtime contract / audit schema
  - 新增 `M2B-8` plan / results
  - 更新 `PLANNING.md` / `TASK.md`

## Runtime Guarantees

- final output provenance invariant 已落地：
  - `effective_mode=deterministic_only`
    - final SQL 必须来自 deterministic-only prompt
  - `effective_mode=hybrid_candidate`
    - final SQL 才允许来自 candidate prompt
- discarded candidate attempt：
  - 不创建 reviewable SQL version
  - 不进入 approval flow
  - 不暴露给 public API
- candidate generation 失败时，若 deterministic 主链路可用，则自动 deterministic rerun

## Verification Snapshot

- `pytest tests/data_agent/test_hybrid_shadow_config.py tests/data_agent/test_hybrid_shadow_runtime.py -q`

覆盖：

- `hybrid_candidate` allowlist / mode wiring
- candidate prompt 注入
- `sql_kind` mismatch 时 deterministic rerun
- candidate generation failure fallback
- final SQL version 只来自 final attempt
- `hybrid_enabled` 继续禁用

## Current Limits

- 当前 candidate rollout 仍只支持 `MX + cohort_query`
- `bucket_writeback` / `TH` 继续 fallback
- structured SQL plan 仍沿用 deterministic artifact 路径，未改其构造来源
- hybrid retrieval 仍然只是 grounding augmentation，不是 execution authority
