# M2B-9 Hybrid Enabled Gated Rollout Plan

## Goal

让 `configured_mode=hybrid_enabled` 仅在严格 gated rollout 条件全部满足时，成为 `effective_mode=hybrid_enabled`；否则一律回退到 `deterministic_only`。

## Scope

本阶段只支持：

- `country=mx`
- `run_type=cohort_query`
- request-scope `sql_kind=query_only`
- normalized `ctx.project_id` allowlist 命中
- eval gate passed
- kill switch off

本阶段明确不支持：

- global default
- TH / 多国家
- writeback / bucket writeback
- public API schema change
- approve / execute / SQL HITL 语义变更
- orchestrator routing change
- real vector DB integration

## Runtime Design

- pre-trace gate 只判断 mode / country / run_type / query-only scope / allowlist / eval gate / kill switch
- post-trace gate 继续判断 vector artifact、accepted supplements、audit trace serialization
- success path 继续使用 `supplemental_candidates_v1`
- deterministic 仍然是 primary context
- `hybrid_enabled` 复用 M2B-8.1 deterministic rerun 机制

## Persistence and Provenance

- success path：
  - `final_generation_pass=hybrid_enabled`
  - `source_context=hybrid_enabled_attempt`
- rerun path：
  - `final_generation_pass=deterministic_rerun`
  - `source_context=deterministic_rerun_attempt`
- final snapshot、SQL、SQL version、`structured_sql_plan_provenance`、`context_hash` 全部保持 final-attempt scoped

## Verification

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `pytest tests/data_agent/test_hybrid_shadow_config.py tests/data_agent/test_hybrid_shadow_runtime.py tests/data_agent/test_hybrid_candidate_guardrails.py tests/data_agent/test_hybrid_enabled_rollout.py tests/data_agent/test_api.py tests/data_agent/test_plan_review.py tests/data_knowledge/test_data_knowledge_service.py tests/data_knowledge/test_data_knowledge_retriever.py tests/data_knowledge/test_prompt_context.py -q`
- `git diff --check`
- `git ls-files docs/knowledge-base`
