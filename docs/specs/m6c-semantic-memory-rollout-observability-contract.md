# M6C Semantic Memory Rollout & Observability Contract

## Purpose

M6C does not extend semantic retrieval capability. It production-hardens the
merged M6B runtime with rollout visibility, debugability, rollback guidance,
and acceptance evidence.

The governing rule is:

- shared `app/services/memory/*` runtime emits the full semantic-memory trace
- Orchestrator stores only a sanitized summary in execution trace internal
  metadata
- prompt-visible memory context remains minimal and unchanged in semantics

## Scope

- `app/services/memory/observability.py` shared contracts and constants
- optional `run_id` / `request_id` / `trace_id` fields on
  `MemoryRetrievalRequest`
- semantic-memory trace in retrieval/context metadata
- session internal handoff into `execution_trace.internal_metadata`
- rollout/eval/runbook/docs updates for M6C

## Non-Goals

- no change to retrieval / policy / fusion / context injection semantics
- no default enablement of `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED`
- no Data Agent / SQL semantic supplement
- no `build_retrieved_memory_context()` return-object refactor
- no DB audit event or persistent audit stream
- no dashboard UI
- no M6 final closure in this step

## Runtime Boundary

M6C must preserve the accepted M6B behavior:

- `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED=0` keeps legacy FTS prompt/context
  output unchanged
- semantic supplement remains limited to:
  - `general_chat`
  - `profile_followup`
  - `risk_qa_followup`
- `data_agent_sql` and `sql_repair` keep their legacy non-semantic path

## Observability Contract

Full trace metadata may include only aggregated observability fields:

- trace identity
- requested use / retrieval mode
- candidate counts
- policy block counts and aggregated reasons
- fallback status and reason
- context budget usage
- latency and warnings

Full trace must not include:

- memory content
- raw `metadata_json`
- raw vector distances
- full candidate lists
- full forbidden-use payloads
- policy internals
- FAISS manifest / sync internals
- embedding text

## Execution Trace Summary Contract

The execution trace summary is sanitized and stored only in:

- `execution_trace.internal_metadata["semantic_memory"]`

It may include:

- enablement state
- retrieval mode
- requested use
- aggregated counts
- fallback status / reason
- budget usage
- latency
- warnings count

It must not include:

- warnings raw strings
- memory content
- raw metadata
- raw distances
- candidate details

## Session Handoff Boundary

The temporary handoff key is internal-only and not a business entity:

- key: `_internal_semantic_memory_trace_summary`
- it must not participate in entity extraction
- it must not affect retrieval input
- it must not enter prompt construction
- it must not appear in public session API payloads
- `create_execution_trace()` is the only canonical consumer and should `pop`
  the handoff when present

## Stage Status

- `M6A completed`
- `M6B completed / merged`
- `M6C implemented / pending acceptance`
- `M6 overall not completed`
- `M6 final closure not started`
