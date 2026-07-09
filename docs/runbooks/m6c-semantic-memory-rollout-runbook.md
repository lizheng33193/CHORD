# M6C Semantic Memory Rollout Runbook

## Goal

Operate and troubleshoot M6B semantic memory safely while semantic context
injection remains default-off.

## Rollout Matrix

| Environment | `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED` | Allowed Task Types | Data Agent SQL | Notes |
| --- | --- | --- | --- | --- |
| local/dev | optional | `general_chat`, `profile_followup`, `risk_qa_followup` | disabled | developer verification |
| staging | optional allowlist | `general_chat`, `profile_followup`, `risk_qa_followup` | disabled | observe trace + metrics |
| production default | `0` | none by default | disabled | legacy FTS path |
| production canary | controlled | low-risk chat/followup only | disabled | requires release gate |

## What To Inspect

Primary internal trace surface:

- `execution_trace.internal_metadata["semantic_memory"]`

Supporting constraints:

- full trace remains metadata-only in shared memory runtime objects
- sanitized summary does not enter prompts
- public session API filters `_internal*` handoff fields
- M6C does not introduce a return-object refactor
- M6C does not introduce a DB audit stream

Expected fields:

- `enabled`
- `retrieval_mode`
- `requested_use`
- `fts_candidates`
- `vector_candidates`
- `relational_loaded`
- `policy_allowed`
- `policy_blocked`
- `injected`
- `fallback_used`
- `fallback_reason`
- `context_budget_used`
- `context_budget_limit`
- `latency_ms`
- `warnings_count`

## Fallback Reasons

- `vector_disabled`: vector path not requested
- `task_type_not_allowed`: task is outside the M6B allowlist
- `vector_search_error`: vector search failed and the runtime relied on legacy
  FTS behavior
- other canonical reasons should be treated as observability-only labels and
  must not imply changed runtime semantics

## Policy Block Reasons

- `status_not_active`
- `scope_mismatch`
- `project_mismatch`
- `country_mismatch`
- `forbidden_use`
- `allowed_use_missing`
- `authority_insufficient`

These are aggregated observability reasons. They are not prompt-visible and do
not expose raw policy internals.

## What Must Not Change During Rollout

- `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED` stays default-off unless explicitly
  enabled for validation
- SQL/Data Agent semantic supplement stays disabled
- retrieval / policy / fusion / context injection semantics are not changed by
  M6C closure

## Rollback Conditions

Rollback immediately if any of the following happens:

- unexpected fallback spike
- unexpected policy-block spike
- latency spike
- budget overflow behavior
- forbidden memory injection
- deleted memory injection
- scope leak
- any Data Agent / SQL semantic contamination

## Rollback Action

1. Set `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED=0`
2. Keep `MEMORY_VECTOR_ENABLED` / shadow index artifacts unchanged
3. Re-run:
   - `python -m app.eval.runner --suite memory_governance`
   - `python -m app.eval.runner --profile production_release --strict`
4. Confirm legacy FTS context path remains active

## Why SQL / Data Agent Semantic Supplement Stays Disabled

M6C is limited to rollout and observability of the accepted M6B chat/followup
semantic path. Extending SQL/Data Agent grounding would be a separate runtime
scope change and is explicitly out of scope for M6C.
