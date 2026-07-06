# M4-2 Memory Write Gate & Store Metadata Review

## Scope

This PR implements M4-2 only.

It does not implement retrieval, context injection, vector memory, promotion,
dashboard, orchestrator auto-write integration, or whole-`M4` completion.

## What Changed

- added M4-2 write-decision and record-draft contracts
- added deterministic dedupe-key generation
- added narrow secret rejection for obvious secret-like content
- added `MemoryWriteGate.evaluate(...)` and `MemoryWriteGate.write(...)`
- added `InMemoryMemoryStoreAdapter` as the source of truth for focused
  duplicate-behavior coverage
- added isolated `SQLiteV1MemoryStoreAdapter` to prove M4 metadata can persist
  into legacy SQLite v1 `metadata_json`

## SQLite Compatibility Boundary

The SQLite adapter is isolated only.

It reuses existing `MemoryRecord` / `SQLiteMemoryStore` public behavior and
does not modify schema or existing orchestrator memory flows.

Existing orchestrator auto-write remains untouched.

SQLite duplicate detection uses existing v1 public behavior and is
intentionally limited to compatibility scope.

## Tests

Focused verification for this stage:

- `tests/test_memory_write_gate.py`
- `tests/test_memory_store_metadata.py`
- `tests/test_memory_type_isolation_contract.py`
- `tests/test_profile_memory_snapshot.py`
- `tests/orchestrator_agent/test_sqlite_memory_store.py`

Expected verification commands:

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `AUTH_ENABLED=0 pytest tests/test_memory_type_isolation_contract.py tests/test_profile_memory_snapshot.py tests/test_memory_write_gate.py tests/test_memory_store_metadata.py -q`
- `AUTH_ENABLED=0 pytest tests/orchestrator_agent/test_sqlite_memory_store.py -q`
- `git diff --check`

## Known Limitations

- no retrieval or context injection yet
- no vector memory
- no promotion policy
- no dashboard
- no auto-write integration into orchestrator chat memory
- full `M4` remains incomplete

## Decision

- `M4-1 Memory Type & Isolation Contract: completed`
- `M4-2 Memory Write Gate & Store Metadata: implemented / pending acceptance`
- `M4 full completion: not completed`
- `M4-3 Memory Retrieval Boundary & Context Injection: next`
