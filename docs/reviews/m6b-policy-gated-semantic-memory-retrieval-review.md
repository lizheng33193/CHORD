# M6B Policy-Gated Semantic Memory Retrieval Review

## Delivered

- added independent M6B runtime flags for semantic context injection
- added a single memory-layer adapter seam into M6A vector primitives
- extended retrieval provenance with `retrieval_method`, `raw_distance`, and
  `normalized_score`
- added policy-gated semantic retrieval and deterministic FTS/vector fusion
- wired Orchestrator memory context through the shared memory runtime
- kept SQL/Data Agent semantic injection out of scope for M6B
- added hermetic `memory_semantic_retrieval` eval coverage

## Guardrails Preserved

- SQLite remains source of truth
- vector candidates always relational-load before use
- `app/services/memory/*` remains the only policy / retrieval governance layer
- `build_retrieved_memory_context()` preserves exact legacy output when the M6B
  flag is off
- prompt provenance is minimized

## Verification

- targeted M6B tests
- memory contract / eval runner regressions
- full `tests/orchestrator_agent`

## Follow-Up

- M6C should decide rollout / observability / possible vector-module migration
- SQL/Data Agent semantic supplement remains blocked until a later phase
