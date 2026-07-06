# M4-2 Memory Write Gate & Store Metadata Contract

## Purpose

M4-2 turns the M4-1 `MemoryCandidate` contract into an isolated write-governance
boundary.

This stage decides whether a candidate may be written, why it was accepted or
rejected, how duplicates are blocked, how obvious secrets are rejected, and how
M4 metadata survives persistence into the existing SQLite v1 memory store.

## In Scope

- `MemoryWriteStatus`
- `MemoryWriteRejectReason`
- `MemoryWriteDecision`
- `MemoryRecordDraft`
- deterministic dedupe key generation
- hard-secret write rejection
- metadata envelope generation
- `MemoryWriteGate.evaluate(...)`
- `MemoryWriteGate.write(...)`
- `InMemoryMemoryStoreAdapter`
- isolated `SQLiteV1MemoryStoreAdapter`
- focused tests and review docs

## Out Of Scope

- retrieval
- context injection
- promotion
- vector memory
- dashboard
- orchestrator auto-write integration
- SQLite schema migration
- Data Agent SQL HITL runtime changes
- Risk Knowledge RAG runtime changes
- whole `M4` completion

## Write-Gate Contract

`evaluate(candidate)` may return only:

- `accepted`
- `rejected`
- `skipped_duplicate`

`write(candidate)` may return:

- `accepted`
- `rejected`
- `skipped_duplicate`
- `deferred`

`accepted=True` means the gate passed.

`persisted=True` means an actual store write succeeded.

`accepted=True` does not imply persistence.

## Rejection Rules

The gate rejects for:

- empty content
- invalid candidate shape
- missing `allowed_memory_use`
- missing `forbidden_memory_use`
- missing `user_id` when `require_scope=True`
- secret-like content
- importance below threshold
- confidence below threshold

Duplicate candidates are not rejected as invalid input; they return
`skipped_duplicate`.

## Metadata Envelope

Every accepted draft must persist a minimum envelope in `metadata_json`:

- `m4_contract_version = "m4-2"`
- `memory_source_type`
- `authority_level`
- `allowed_memory_use`
- `forbidden_memory_use`
- `source_run_id`
- `source_artifact_id`
- `evidence_status`
- `candidate_metadata`
- `scope_warnings`
- `write_gate.status`
- `write_gate.reject_reason`
- `write_gate.redacted`
- `write_gate.dedupe_key`
- `write_gate.decision_reason`

Legacy SQLite compatibility fields such as `category`, `memory_type`, and
`source` are only compatibility shims. M4 truth lives in `metadata_json`.

## Store Compatibility

M4-2 adds an isolated SQLite v1 adapter only.

It reuses existing `MemoryRecord` and `SQLiteMemoryStore` public behavior and
does not alter legacy schema or the existing orchestrator chat-memory flows.

The adapter must not be wired into:

- `app/services/orchestrator_agent/memory_context.py`
- `app/services/orchestrator_agent/memory_policy.py`
- `app/services/orchestrator_agent/agent_loop.py`
- existing memory flush or memory tool auto-write paths

## Stage Status

- `M4-1 Memory Type & Isolation Contract: completed`
- `M4-2 Memory Write Gate & Store Metadata: implemented / pending acceptance`
- `M4 full completion: not completed`
- `M4-3 Memory Retrieval Boundary & Context Injection: next`
