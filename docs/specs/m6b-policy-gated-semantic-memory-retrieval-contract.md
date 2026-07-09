# M6B Policy-Gated Semantic Memory Retrieval Contract

## Purpose

M6B connects semantic memory retrieval to Orchestrator context injection without
creating a second memory-governance stack.

The governing rule is:

- `app/services/memory/*` is the only policy / retrieval / provenance truth
- SQLite remains the source of truth
- vector search returns candidates only
- every vector candidate must relational-load back from SQLite before use

## Scope

- `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED` and related M6B flags
- temporary `app/services/memory/vector_index_adapter.py` seam into M6A
- policy-gated semantic retrieval under `app/services/memory/*`
- hybrid FTS + vector fusion for allowlisted task types
- provenance-preserving context injection
- hermetic `memory_semantic_retrieval` eval suite

## Non-Goals

- no HTTP debug API
- no new orchestrator-private memory runtime
- no Data Agent SQL semantic grounding expansion in M6B
- no Risk Knowledge RAG changes
- no memory promotion or write-path changes
- no non-FAISS production vector backend

## Runtime Boundary

`MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED=0` must preserve the legacy
`build_retrieved_memory_context()` output exactly under fixed seed data.

When the flag is enabled:

- hybrid retrieval is allowed only for:
  - `general_chat`
  - `profile_followup`
  - `risk_qa_followup`
- `data_agent_sql` and `sql_repair` keep existing behavior
- vector failures fall back to FTS when `MEMORY_VECTOR_FALLBACK_TO_FTS=1`
- policy failures fail closed for the candidate only

## Dependency Guardrail

M6A vector primitives still live under
`app/services/orchestrator_agent/memory_vector/*`.

M6B may import that code only through:

- `app/services/memory/vector_index_adapter.py`

No other `app/services/memory/*` module may directly depend on
`orchestrator_agent.memory_vector`.

## Provenance Contract

Prompt-visible memory context may include only:

- `memory_id`
- `memory_source_type`
- `authority_level`
- `requested_use`
- `retrieval_method`
- `evidence_status`
- `content`

Prompt-visible context must not include:

- full `forbidden_memory_use`
- policy internals
- `metadata_json` raw payload
- `raw_distance`
- vector sync internals

## Stage Status

- `M6A implemented`
- `M6B accepted / ready to merge`
- `M6C not started`
