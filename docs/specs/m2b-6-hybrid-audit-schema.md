# M2B-6 Hybrid Audit Schema

## Goal

定义 future runtime hybrid retrieval 的审计轨迹，确保任何 hybrid 行为都可解释、可回退、可审核。

## Core Rule

审计 schema 只能记录 runtime 真实发生的 retrieval / fusion 行为。

不得记录：

- `expected_*`
- `matched_expected`
- `missing_expected`

这些字段只允许用于 offline evaluation，不允许出现在 runtime audit trace 中。

## HybridRetrievalAuditTraceV1

建议 schema：

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
  candidate_counts
  deterministic_candidates
  vector_candidates
  accepted_supplements
  rejected_candidates
```

## Field Requirements

### Top-level

- `schema_version`
- `configured_mode`
- `effective_mode`
- `source_namespace`
- `fallback_applied`
- `fallback_reason`
- `config_snapshot`
- `prompt_injection_mode`
- `candidate_counts`

### Candidate Collections

- `deterministic_candidates`
- `vector_candidates`
- `accepted_supplements`
- `rejected_candidates`

## Fallback Reasons

至少支持以下枚举：

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

## Candidate Audit Shape

### Deterministic Candidate

建议保留 bounded fields：

- `family`
- `canonical_key`
- `source_key`
- `title`
- `rank`

### Vector Candidate

建议保留 bounded fields：

- `record_id`
- `source_key`
- `asset_family`
- `title`
- `score`
- `rank`

### Accepted Supplement

承接 M2B-5 输出字段：

- `record_id`
- `source_key`
- `asset_family`
- `title`
- `score`
- `rank`
- `accepted_reason`

### Rejected Candidate

承接 M2B-5 输出字段：

- `record_id`
- `source_key`
- `asset_family`
- `title`
- `score`
- `rank`
- `rejected_reason`

## Prompt Injection Mode

建议固定枚举：

- `none`
- `shadow_only`
- `supplemental_candidates_experimental`
- `hybrid_context_enabled`

## Candidate Counts

建议至少记录：

- `deterministic_total`
- `vector_total`
- `accepted_total`
- `rejected_total`

## Data Boundary

future runtime trace 中必须保持以下边界：

- `uid` 与 `user_uuid` 不做全局等价
- `dt` 不作为业务时间字段替代
- 不保存完整 prompt
- 不保存 raw PII
- 不保存大段 embedding text
- 不保存 raw docs 内容
- 不保存 SQL expected labels

## Snapshot Size Boundary

`retrieval_snapshot_json.hybrid_trace` 只能保存 bounded top-k 审计字段。

不允许：

- 全量候选原文
- 大段长文本 embedding records
- 未裁剪的 vector candidate 列表

## Persistence Rule

future runtime 若启用 hybrid audit：

- `hybrid_trace` 写入 `retrieval_snapshot_json.hybrid_trace`
- 若 trace 无法安全生成或无法持久化，必须降级：
  - `effective_mode=deterministic_only`
  - `fallback_applied=true`
  - `fallback_reason=audit_trace_unavailable`
