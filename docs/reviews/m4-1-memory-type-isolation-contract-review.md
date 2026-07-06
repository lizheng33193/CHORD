# M4-1 Memory Type & Isolation Contract Review

## 1. Scope

This PR implements M4-1 only.

It does not implement full M4 persistence, retrieval, promotion, vector memory,
dashboard, or prompt injection.

## 2. Background

`M3 Minimum Closure Before M4` already established that M4 may start only
through `ProfileMemorySnapshot` rather than raw profile internals.

M4-1 builds on that seam by locking:

- memory type
- authority level
- allowed / forbidden use
- deterministic isolation validation
- candidate adapters

## 3. Implemented Contract

- `MemorySourceType`
- `MemoryAuthorityLevel`
- `MemoryUsePurpose`
- `MemoryCandidate`
- `MemoryUseDecision`
- default policy constants
- `validate_memory_use(...)`

## 4. Implemented Adapters

- `ProfileMemorySnapshot -> profile_result MemoryCandidate`
- `Risk QA answer -> risk_qa_answer MemoryCandidate`
- `approved SQL -> data_agent_sql_case MemoryCandidate`
- `failed SQL -> data_agent_sql_error MemoryCandidate`

These adapters generate candidates only. They do not write to storage or attach
to runtime prompt injection.

## 5. Isolation Rules Confirmed

- `profile_result` cannot be used for Data Agent grounding.
- `profile_result` cannot become Risk Knowledge evidence or source document.
- `risk_qa_answer` cannot become a Risk Knowledge source document.
- `data_agent_sql_error` cannot become approved SQL truth.
- `user_preference` cannot override safety / permission / HITL / validator policy.
- `audit_event` cannot enter normal prompt context.
- `UNVERIFIED` cannot be used for production grounding.

## 6. Tests

Focused verification for this stage:

- `tests/test_memory_type_isolation_contract.py`
- `tests/test_profile_memory_snapshot.py`

Expected acceptance commands:

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `AUTH_ENABLED=0 pytest tests/test_memory_type_isolation_contract.py -q`
- `AUTH_ENABLED=0 pytest tests/test_profile_memory_snapshot.py -q`
- `git diff --check`

## 7. Known Limitations

- no memory persistence changes
- no write gate yet
- no retrieval / ranking
- no vector index
- no automatic context injection
- full `M4` remains incomplete

## 8. Decision

`M4-1 Memory Type & Isolation Contract` is implemented as a focused contract
slice.

`M4 full completion: not completed`

`M4-2 Memory Write Gate & Store Metadata: next`
