# M2B-6 Hybrid Audit Schema

## Goal

定义 hybrid retrieval 在 runtime 中的正式审计轨迹，确保 `hybrid_shadow` 与 `hybrid_candidate` 都可解释、可回退、可审核。

本文件在 `M2B-8.1` 更新为当前已落地 schema contract。

## Core Rule

审计 schema 只能记录 runtime 真实发生的 retrieval / fusion / candidate attempt 行为。

不得记录：

- `expected_*`
- `matched_expected`
- `missing_expected`
- 完整 prompt
- 完整 discarded candidate SQL

## HybridRetrievalAuditTraceV1

```text
HybridRetrievalAuditTraceV1
  schema_version
  configured_mode
  effective_mode
  source_namespace
  fallback_applied
  fallback_reason
  config_snapshot
  prompt_injection_mode
  prompt_candidate_count
  final_generation_pass
  candidate_counts
  candidate_attempt
  deterministic_candidates
  vector_candidates
  accepted_supplements
  rejected_candidates
```

## Top-level Fields

- `schema_version`
- `configured_mode`
- `effective_mode`
- `source_namespace`
- `fallback_applied`
- `fallback_reason`
- `config_snapshot`
- `prompt_injection_mode`
- `prompt_candidate_count`
- `final_generation_pass`
- `candidate_counts`
- `candidate_attempt`

## Prompt Injection Mode

当前固定枚举：

- `none`
- `supplemental_candidates_v1`

说明：

- `hybrid_shadow` 必须固定为 `none`
- `hybrid_candidate` 只有 final result 保留 candidate prompt 时，才允许 `supplemental_candidates_v1`

## Final Generation Pass

当前固定枚举：

- `deterministic`
- `hybrid_candidate`
- `deterministic_rerun`

## Candidate Attempt

`candidate_attempt` 是 `M2B-8` 新增并在 `M2B-8.1` hardened 的正式 contract：

```text
candidate_attempt
  attempted
  attempted_mode
  prompt_injection_mode
  prompt_candidate_count
  output_sql_kind
  output_sql_hash
  discarded
  discard_reason
```

### Candidate discard reason

当前至少支持：

- `post_sql_kind_mismatch`
- `candidate_sql_empty`
- `candidate_generation_failed`

## Fallback Reasons

当前至少支持：

- `hybrid_disabled`
- `mode_forced_deterministic`
- `country_not_allowlisted`
- `project_not_allowlisted`
- `unsupported_sql_kind`
- `unsupported_run_type`
- `vector_backend_unavailable`
- `vector_query_failed`
- `fusion_guard_failed`
- `audit_trace_unavailable`
- `config_invalid`
- `candidate_generation_failed`

## Candidate Collections

### Deterministic Candidate

- `family`
- `canonical_key`
- `source_key`
- `title`
- `rank`

### Vector Candidate

- `record_id`
- `source_key`
- `asset_family`
- `title`
- `score`
- `rank`

### Accepted Supplement

- `record_id`
- `source_key`
- `asset_family`
- `title`
- `score`
- `rank`
- `accepted_reason`

### Rejected Candidate

- `record_id`
- `source_key`
- `asset_family`
- `title`
- `score`
- `rank`
- `rejected_reason`

## Candidate Counts

至少记录：

- `deterministic_total`
- `vector_total`
- `accepted_total`
- `rejected_total`

## Final Output Provenance

trace 必须能够区分：

- configured mode
- attempted mode
- final effective mode
- final generation pass

这保证以下不变量可审计：

```text
最终 SQL / structured_sql_plan / SQL version / context_hash
必须来自 final generation attempt。
```

对应的 internal snapshot provenance contract 固定为：

```text
structured_sql_plan_provenance
  plan_generation_pass
  prompt_injection_mode
  source_context
```

固定枚举：

- `plan_generation_pass`
  - `deterministic`
  - `hybrid_candidate`
  - `deterministic_rerun`
- `prompt_injection_mode`
  - `none`
  - `supplemental_candidates_v1`
- `source_context`
  - `deterministic_attempt`
  - `hybrid_candidate_attempt`
  - `deterministic_rerun_attempt`

## Audit Metadata Summary

`_audit()` metadata 只允许写 bounded summary，不允许写候选明细。

当前 summary fields：

- `hybrid_configured_mode`
- `hybrid_attempted_mode`
- `hybrid_effective_mode`
- `hybrid_fallback_reason`
- `hybrid_final_generation_pass`
- `hybrid_prompt_injection_mode`
- `hybrid_prompt_candidate_count`
- `hybrid_candidate_attempted`
- `hybrid_candidate_discarded`
- `hybrid_candidate_discard_reason`
- `hybrid_trace_present`

## Data Boundary

必须继续保持：

- 不保存完整 prompt
- 不保存 raw PII
- 不保存大段 embedding text
- 不保存 raw docs 内容
- 不保存 SQL expected labels
- 不保存 discarded candidate SQL 正文
- 不保存完整 accepted supplements 明细到 audit metadata

允许保存：

- candidate SQL hash
- bounded candidate summary

## Persistence Rule

- `hybrid_trace` 写入 `retrieval_snapshot_json.hybrid_trace`
- discarded candidate 只能通过 bounded `candidate_attempt` summary 进入 final attempt snapshot
- discarded candidate 不得进入 public artifact / HITL / approve flow
- 若 trace 无法安全生成或无法持久化，必须降级：
  - `effective_mode=deterministic_only`
  - `fallback_applied=true`
  - `fallback_reason=audit_trace_unavailable`
