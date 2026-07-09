# M6C Semantic Memory Rollout & Observability Plan

## Summary

- Keep M6B runtime semantics stable.
- Add full trace in shared memory runtime metadata.
- Add sanitized execution-trace summary through session handoff.
- Extend eval coverage and acceptance docs without introducing new audit infra.

## Key Changes

1. Add `app/services/memory/observability.py` for:
   - shared trace/summary contracts
   - canonical metadata keys
   - reason normalization helpers
2. Extend `MemoryRetrievalRequest` with optional observability-only trace
   identity fields.
3. Update shared memory runtime:
   - `semantic_retrieval.py`
   - `hybrid_retrieval.py`
   - `context_builder.py`
   - `fusion.py` only if needed for counts
4. Keep `app/services/orchestrator_agent/memory_context.py` thin:
   - pass trace identity
   - write session internal handoff
5. Consume handoff centrally in:
   - `app/services/orchestrator_agent/runtime/trace_store.py`
6. Prevent `_internal*` handoff keys from leaking through:
   - `app/api/orchestrator_routes.py`
7. Add targeted M6C pytest coverage and extend:
   - `memory_semantic_retrieval` eval suite
8. Update README / PLANNING / TASK and add M6C review + runbook artifacts.

## Guardrails

- no prompt-visible trace payload
- no new persistent audit stream
- no Data Agent semantic supplement
- no default-on semantic injection
- no mainline retrieval/policy/fusion refactor

## Verification

- compileall
- semantic retriever / fusion / context injection / observability pytest
- memory boundary / context / isolation pytest
- `memory_governance`
- `memory_semantic_retrieval`
- `pr_acceptance`
- `production_release --strict`
- `git diff --check`
