# M6A Memory Vector Shadow Index Plan

## Goal

Add a shadow-only FAISS semantic index for SQLite long-term memory without changing production prompt injection or FTS5 retrieval.

## Delivered Work

1. Add `app/services/orchestrator_agent/memory_vector/` with:
   - schemas
   - embedding text builder
   - deterministic / wrapped embedding provider boundary
   - local FAISS store
   - sync service
   - shadow search
   - CLI entrypoint
2. Extend `SQLiteMemoryStore.initialize()` with `memory_vector_sync`.
3. Add low-level best-effort sync-state hooks in `SQLiteMemoryStore.add/update/set_status`.
4. Keep vector sync non-blocking for relational writes.
5. Keep shadow search CLI-only and relationally filtered.
6. Update README / PLANNING / TASK and add M6A review artifact.

## Verification

- targeted new tests for:
  - embedding text
  - FAISS store
  - sync service
  - shadow search
- targeted existing memory/orchestrator regression tests
- memory governance eval
- `pr_acceptance` shared profile
- `compileall`
- `git diff --check`

## Guardrails

- do not change `build_retrieved_memory_context()`
- do not route vector results into prompts
- do not replace SQLite FTS5 retrieval
- do not add HTTP debug APIs
- do not introduce non-FAISS production backends in M6A
