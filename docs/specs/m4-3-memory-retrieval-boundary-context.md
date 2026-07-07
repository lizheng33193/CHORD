# M4-3 Memory Retrieval Boundary & Context Injection Contract

## Purpose

M4-3 turns the M4-1 isolation boundary and the M4-2 metadata envelope into an
executable retrieval contract.

This stage exists to answer:

- which task types may retrieve which memory source types
- which `requested_use` each source enters context under
- why a retrieved record was accepted or rejected
- how retrieved memory is rendered without losing provenance

## Scope

- `MemoryRetrievalTaskType`
- `MemoryRetrievalPolicy`
- `MemoryRetrievalRequest`
- `MemoryRetrievedItem`
- `MemoryRejectedRetrievalItem`
- `MemoryRetrievalResult`
- `MemoryContextItem`
- `MemoryContextBundle`
- isolated in-memory and SQLite v1 retrieval adapters
- deterministic task-type policy resolution
- post-retrieval isolation validation before context rendering

## Non-Goals

- no vector memory
- no embedding retrieval
- no reranking beyond deterministic ordering
- no promotion
- no dashboard
- no default orchestrator prompt injection
- no feature flag or runtime seam in this stage
- no changes to legacy orchestrator memory retrieval
- no whole-`M4` completion

## Contracts

`MemoryRetrievalRequest.user_id` is required and must fail closed when missing.

`project_id` and `country` remain optional request inputs, but missing values
must surface as retrieval warnings / metadata.

Each accepted retrieval item must preserve:

- `memory_id`
- `memory_source_type`
- `authority_level`
- `requested_use`
- `use_decision`
- `evidence_status`
- `source_run_id`
- `source_artifact_id`
- traceable content / metadata

Each rejected retrieval item must explain why it was blocked after entering the
retrieval pipeline.

## Retrieval Boundary

Task types may resolve to multiple retrieval policies. This is required when
different source types need different `requested_use` values.

Locked policy matrix:

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

Additional retrieval rules:

- `request.max_items` is the final global return limit after multi-policy merge
- `rejected_items` only records rows that entered the retrieval pipeline and
  were blocked by metadata, policy, scope, authority, or isolation checks
- store-layer source filtering does not need to emit `rejected_items`

## SQLite Boundary

`SQLiteV1MemoryRetrievalAdapter` is isolated only.

It may read only M4-governed records, identified by the metadata envelope.
Records lacking any of the following must not be treated as M4 memory:

- `m4_contract_version`
- `memory_source_type`
- `authority_level`
- `allowed_memory_use`
- `forbidden_memory_use`
- `write_gate`

Legacy chat-memory rows remain outside M4 retrieval in this stage.

## Context Rendering

Rendered context must preserve:

- `source_type`
- `authority_level`
- `requested_use`
- `evidence_status`
- traceable index or `memory_id`

Rendered context must not dump the full `forbidden_memory_use` list into the
prompt.

Truncation is item-level only:

- if the next whole item would exceed `max_chars`, omit that whole item
- add `context_truncated` warning
- record `omitted_item_count`

## Existing Runtime Boundary

Existing orchestrator memory retrieval remains unchanged.

This stage must not modify:

- `app/services/orchestrator_agent/agent_loop.py`
- `app/services/orchestrator_agent/memory_context.py`
- `app/services/orchestrator_agent/tools/memory.py`

## Stage Status

- `M4-1 Memory Type & Isolation Contract: completed`
- `M4-2 Memory Write Gate & Store Metadata: completed`
- `M4-3 Memory Retrieval Boundary & Context Injection: implemented / pending acceptance`
- `M4 full completion: not completed`
- `M4-4 Memory Promotion Policy & Acceptance Closure: next`

