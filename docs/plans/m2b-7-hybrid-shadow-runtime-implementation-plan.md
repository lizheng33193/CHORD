# M2B-7 Hybrid Shadow Runtime Implementation Plan

## Summary

- `M2B-7` 只实现 `hybrid_shadow` runtime skeleton。
- deterministic retrieval 继续作为唯一生效输入。
- hybrid 只生成 bounded internal audit trace，并写入 `retrieval_snapshot_json.hybrid_trace`。
- 默认关闭；任意异常、越界或配置不满足都回退 `deterministic_only`。

## Scope

- 允许：
  - env-backed raw settings
  - `HybridRetrievalMode` / `HybridFallbackReason` / `HybridRetrievalConfigV1`
  - shadow-only vector artifact reader
  - bounded `HybridRetrievalAuditTraceV1`
  - `DataAgentService.create_run()` / `revise_run()` shadow wiring
  - runtime audit metadata summary
- 禁止：
  - `hybrid_candidate`
  - `hybrid_enabled`
  - prompt text 注入
  - SQL plan / review / approve / execute 语义变化
  - public API schema 变化
  - runtime retriever scoring/top-k/filtering 改造
  - orchestrator 自动路由

## Implementation Outline

1. 在 `app/core/config.py` 增加 raw env-backed settings。
2. 新增 `app/data_agent/hybrid_runtime.py`：
   - config loader
   - effective mode evaluator
   - shadow-only vector query helper
   - bounded supplement selector
   - trace builder / post-generation sql_kind fallback
3. 在 `app/data_agent/service.py` 保持 deterministic 主链路不变，仅追加 shadow trace 构建。
4. 仅把 `hybrid_trace` 写入 `retrieval_snapshot_json`，不进入 prompt，不暴露给前端。
5. 在 `_audit()` metadata 中追加最小 summary：
   - `hybrid_trace_present`
   - `hybrid_effective_mode`
   - `hybrid_fallback_reason`

## Runtime Rules

- `enabled=false` 优先级最高。
- `allow_countries=[]` / `allow_project_ids=[]` 默认拒绝全部 runtime hybrid。
- `country` 与 `project_id` 必须来自结构化 metadata，不得从自然语言猜测。
- 若配置 `hybrid_candidate` 或 `hybrid_enabled`，本阶段强制：
  - `effective_mode=deterministic_only`
  - `fallback_reason=mode_forced_deterministic`
- `run_type != cohort_query` 直接：
  - `effective_mode=deterministic_only`
  - `fallback_reason=unsupported_run_type`
- 若 post-generation 判定 `sql_kind != query_only`：
  - 保留 shadow attempt 审计信息
  - 最终 trace 写成 deterministic fallback

## Bounded Trace Contract

- `deterministic_candidates <= 20`
- `vector_candidates <= 10`
- `accepted_supplements <= 3`
- `rejected_candidates <= 20`
- `title <= 200`
- `source_key <= 300`
- 严禁保存：
  - 完整 prompt
  - raw PII
  - embedding text
  - raw docs 内容
  - `expected_* / matched_expected / missing_expected`

## Verification

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `pytest tests/data_agent/test_hybrid_shadow_runtime.py tests/data_agent/test_hybrid_shadow_config.py tests/data_agent/test_api.py tests/data_agent/test_plan_review.py tests/data_knowledge/test_data_knowledge_service.py tests/data_knowledge/test_data_knowledge_retriever.py -q`
- `git diff --check`
- `git ls-files docs/knowledge-base`

## Non-goals

- 不证明 hybrid 已具备线上收益。
- 不引入真实向量库或 embedding API。
- 不让 supplements 进入 prompt/context。
- 不进入 TH runtime rollout。
- 不进入 writeback rollout。
