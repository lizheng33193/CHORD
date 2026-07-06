# M4-2 Memory Write Gate & Store Metadata Plan

## Goal

Implement an isolated M4-2 write-governance layer that converts
`MemoryCandidate` into an auditable `MemoryRecordDraft`, enforces dedupe and
secret rejection, and proves M4 metadata can persist into SQLite v1
`metadata_json` without changing existing orchestrator auto-write behavior.

## Implementation Steps

1. Add `app/services/memory/records.py` for M4-2 decision and draft types.
2. Add `app/services/memory/dedupe.py` for normalized content hashing.
3. Add `app/services/memory/redaction.py` for narrow secret detection.
4. Add `app/services/memory/store_adapter.py` with:
   - `InMemoryMemoryStoreAdapter` for focused duplicate behavior tests
   - isolated `SQLiteV1MemoryStoreAdapter` for compatibility persistence tests
5. Add `app/services/memory/write_gate.py` with `evaluate(...)` and `write(...)`
   split semantics.
6. Export the new M4-2 surface from `app/services/memory/__init__.py`.
7. Add focused tests:
   - `tests/test_memory_write_gate.py`
   - `tests/test_memory_store_metadata.py`
8. Update project status docs:
   - `PLANNING.md`
   - `TASK.md`
   - M4-2 spec / plan / review docs

## Acceptance Criteria

- valid profile candidates produce accepted drafts
- `evaluate()` never returns `deferred`
- `write()` returns `deferred` when persistence is intentionally skipped
- obvious secrets are rejected
- duplicate detection works through `InMemoryMemoryStoreAdapter`
- M4 envelope fields persist in SQLite `metadata_json`
- existing orchestrator SQLite v1 memory tests remain green

## Non-Goals

- no retrieval or context injection
- no vector memory
- no promotion
- no dashboard
- no orchestrator auto-write integration
- no whole-`M4` completion
