# M6B Policy-Gated Semantic Memory Retrieval Plan

## Summary

- Extend `app/services/memory/*` rather than building an orchestrator-private
  retrieval runtime.
- Keep SQLite as source of truth and M6A FAISS as a candidate-only layer.
- Enable semantic context injection only behind feature flags and only for the
  initial allowlist task types.

## Key Changes

1. Add M6B flags in `app/core/config.py`.
2. Add `app/services/memory/vector_index_adapter.py` as the only temporary seam
   into `app/services/orchestrator_agent/memory_vector/*`.
3. Extend retrieval contracts with `allow_vector`, `retrieval_method`,
   `raw_distance`, and `normalized_score`.
4. Add semantic retrieval, fusion, and hybrid runtime under
   `app/services/memory/*`.
5. Update `build_retrieved_memory_context()` to:
   - preserve exact legacy behavior when the flag is off
   - use the hybrid runtime only for allowlisted task types when the flag is on
6. Add hermetic `memory_semantic_retrieval` eval coverage and register it in
   `pr_acceptance` and `production_release`.

## Guardrails

- no raw unscoped `memory_id` load
- no semantic supplement for SQL/Data Agent prompts in M6B
- no prompt-visible `raw_distance` or policy internals
- no dependency on existing local vector artifacts

## Verification

- targeted memory / orchestrator / eval tests
- `tests/orchestrator_agent`
- compileall
- shared eval runner:
  - `memory_governance`
  - `memory_semantic_retrieval`
  - `pr_acceptance`
  - `production_release --strict`
