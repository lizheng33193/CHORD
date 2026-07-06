# M4-1 Memory Type & Isolation Contract

## Purpose

M4-1 defines the production memory contract boundary before any M4 persistence,
retrieval, promotion, or dashboard work begins.

This stage exists to ensure different memory classes do not contaminate each
other across Profile, Risk QA, Data Agent SQL, user preference, and audit flows.

## In Scope

- `MemorySourceType`
- `MemoryAuthorityLevel`
- `MemoryUsePurpose`
- `MemoryCandidate`
- default allowed / forbidden use policy
- `validate_memory_use(...)`
- `ProfileMemorySnapshot -> MemoryCandidate` adapter
- skeleton adapters for Risk QA answers and SQL cases/errors
- focused tests and review docs

## Out Of Scope

- SQLite schema changes
- memory store refactor
- retrieval / ranking / vector memory
- automatic prompt injection
- automatic long-term writes
- dashboard / admin UI
- Data Agent SQL HITL runtime changes
- Risk Knowledge RAG runtime changes
- whole `M4` completion

## Contract

Every `MemoryCandidate` must carry:

- `content`
- `memory_source_type`
- `authority_level`
- `allowed_memory_use`
- `forbidden_memory_use`

Optional identity / provenance fields remain additive:

- `user_id`
- `project_id`
- `country`
- `session_id`
- `source_run_id`
- `source_artifact_id`
- `evidence_status`
- `importance`
- `confidence`
- `metadata`

Internal candidate objects must store `MemoryUsePurpose` enum values, not free
strings. JSON-facing contracts such as `ProfileMemorySnapshot` continue to emit
string lists using `MemoryUsePurpose.value`.

## Isolation Rules

- `profile_result` must not become Data Agent field grounding.
- `profile_result` must not become Risk Knowledge evidence or source document.
- `profile_result` must not ground SQL generation.
- `risk_qa_answer` may support follow-up recall, but must not become a source document.
- `data_agent_sql_error` may support repair hints / eval negatives, but must not become approved SQL truth.
- `user_preference` must not override safety, permission, HITL, or SQL validator policy.
- `audit_event` must stay audit-only.
- `UNVERIFIED` memory must not enter `production_grounding` when `production_context=True`.
- `SQL_GENERATION_GROUNDING` is allowed only for `DATA_AGENT_SQL_CASE + HUMAN_APPROVED`.

## Profile Snapshot Boundary

`ProfileMemorySnapshot` remains the only approved M4-facing profile artifact at
this stage. It is not a memory store record, retrieval payload, or promotion
artifact.

Its role is limited to exporting stable profile summary fields and explicit
memory-use boundaries for downstream M4 adapters.
