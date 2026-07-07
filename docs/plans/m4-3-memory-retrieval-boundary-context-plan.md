# M4-3 Memory Retrieval Boundary & Context Injection Plan

## Goal

Implement an isolated retrieval boundary layer that reads only M4-governed
memory records, resolves task-type-specific retrieval policies, reruns
isolation validation before context entry, and renders source-aware context
without changing existing orchestrator runtime behavior.

## Implementation Steps

1. Add `app/services/memory/retrieval_policy.py` with task types, retrieval
   policy contracts, and multi-policy resolution.
2. Add `app/services/memory/retrieval_adapter.py` with:
   - `MemoryStoredRecord`
   - `MemoryReadableStoreAdapter`
   - `InMemoryMemoryRetrievalAdapter`
   - isolated `SQLiteV1MemoryRetrievalAdapter`
3. Add `app/services/memory/retrieval.py` with request/result item contracts and
   `MemoryRetrievalService.retrieve(...)`.
4. Add `app/services/memory/context_builder.py` with source-aware context bundle
   rendering and item-level truncation.
5. Extend `app/services/memory/policy.py` / `__init__.py` exports only as
   needed for additive M4 coverage.
6. Add focused tests:
   - `tests/test_memory_retrieval_boundary.py`
   - `tests/test_memory_context_builder.py`
7. Update M4 stage docs and project status:
   - `docs/specs/m4-3-memory-retrieval-boundary-context.md`
   - `docs/reviews/m4-3-memory-retrieval-boundary-context-review.md`
   - `PLANNING.md`
   - `TASK.md`

## Files To Change

- `app/services/memory/retrieval_policy.py`
- `app/services/memory/retrieval_adapter.py`
- `app/services/memory/retrieval.py`
- `app/services/memory/context_builder.py`
- `app/services/memory/policy.py`
- `app/services/memory/__init__.py`
- `tests/test_memory_retrieval_boundary.py`
- `tests/test_memory_context_builder.py`
- `docs/specs/m4-3-memory-retrieval-boundary-context.md`
- `docs/plans/m4-3-memory-retrieval-boundary-context-plan.md`
- `docs/reviews/m4-3-memory-retrieval-boundary-context-review.md`
- `PLANNING.md`
- `TASK.md`

## Test Plan

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `AUTH_ENABLED=0 pytest tests/test_memory_type_isolation_contract.py tests/test_memory_write_gate.py tests/test_memory_store_metadata.py tests/test_memory_retrieval_boundary.py tests/test_memory_context_builder.py tests/test_profile_memory_snapshot.py -q`
- `git diff --check`

## Non-Goals

- no orchestrator runtime integration
- no feature flag / runtime seam
- no vector memory
- no embedding retrieval
- no promotion
- no dashboard
- no whole-`M4` completion

## Acceptance Criteria

- task types retrieve only allowed source types under valid `requested_use`
- `data_agent_sql` accepts only `human_approved data_agent_sql_case`
- malformed M4 metadata is rejected
- legacy chat memory is excluded from M4 retrieval by default
- context rendering preserves provenance labels
- truncation occurs at item boundaries with explicit warnings
- existing M4-1 / M4-2 focused tests remain green

