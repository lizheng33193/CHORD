# M4-3 Memory Retrieval Boundary & Context Injection Review

## Scope

This PR implements M4-3 only.

It does not implement orchestrator runtime integration, feature flags, vector
memory, promotion, dashboard, or whole-`M4` completion.

## What Changed

- added task-type-based retrieval policies under `app/services/memory/`
- added isolated readable store adapters for in-memory and SQLite v1 retrieval
- added `MemoryRetrievalService` with multi-policy merge, scope checks,
  authority checks, and post-retrieval isolation validation
- added source-aware context bundle rendering with item-level truncation
- extended focused M4 tests for retrieval boundary and context rendering

## Retrieval Policy Matrix

- `general_chat`
  - `conversation -> conversation_context`
  - `user_preference -> response_style`
  - `user_preference -> report_format_preference`
- `profile_followup`
  - `profile_result -> profile_followup_context`
  - `conversation -> followup_context`
  - `user_preference -> response_style`
  - `user_preference -> report_format_preference`
- `risk_qa_followup`
  - `risk_qa_answer -> risk_qa_followup_context`
  - `conversation -> followup_context`
  - `user_preference -> response_style`
  - `user_preference -> report_format_preference`
- `data_agent_sql`
  - `data_agent_sql_case -> sql_generation_grounding`
  - authority must be `human_approved`
- `sql_repair`
  - `data_agent_sql_error -> sql_repair_hint`
  - `data_agent_sql_case -> sql_case_reference`
- `audit_review`
  - `audit_event -> audit_review`
- `eval_collection`
  - `eval_case -> eval_candidate`
  - `data_agent_sql_error -> eval_candidate`
  - `risk_qa_answer -> eval_candidate`

## Context Examples

Rendered memory context now preserves provenance in prompt-safe text:

```text
Retrieved Memories:

[1] source_type=user_preference | authority=user_provided | use=response_style | evidence=none | memory_id=pref-1
User prefers concise Chinese output.
```

Truncation happens at whole-item boundaries and records
`context_truncated + omitted_item_count`.

## Tests Run

- `AUTH_ENABLED=0 pytest tests/test_memory_type_isolation_contract.py tests/test_memory_write_gate.py tests/test_memory_store_metadata.py tests/test_memory_retrieval_boundary.py tests/test_memory_context_builder.py tests/test_profile_memory_snapshot.py -q`

## Known Limitations

- no orchestrator prompt injection
- no feature flag or runtime seam
- no vector / embedding retrieval
- no legacy chat-memory promotion into M4 retrieval
- no promotion policy
- full `M4` remains incomplete

## Decision

- `M4-1 Memory Type & Isolation Contract: completed`
- `M4-2 Memory Write Gate & Store Metadata: completed`
- `M4-3 Memory Retrieval Boundary & Context Injection: implemented / pending acceptance`
- `M4 full completion: not completed`
- `M4-4 Memory Promotion Policy & Acceptance Closure: next`

