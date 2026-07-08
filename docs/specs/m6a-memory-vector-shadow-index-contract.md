# M6A Memory Vector Shadow Index Contract

## Purpose

M6A adds a shadow-only semantic index beside SQLite long-term memory.

SQLite remains the relational source of truth.
FAISS is only a debug / evaluation semantic index in this stage.

## In Scope

- independent `MEMORY_VECTOR_*` configuration
- local FAISS shadow index under `outputs/memory/vector/<namespace>/`
- deterministic-by-default embedding provider boundary
- `memory_vector_sync` SQLite status table
- best-effort sync hooks on memory write / update / archive / restore / delete
- CLI-only `status` / `sync-all` / `rebuild` / `shadow-search`
- relational load + hard filter after vector retrieval

## Out Of Scope

- no prompt injection
- no replacement of SQLite FTS5 retrieval
- no vector + FTS fusion
- no HTTP debug API
- no dashboard
- no Qdrant / Milvus / pgvector backend
- no M4 requested-use policy integration in semantic retrieval
- no M6B context injection

## Core Boundary

- `app/services/orchestrator_agent/memory_store.py` remains the authoritative memory store.
- `memory_vector_sync` is shadow metadata and must never block the primary memory write path.
- vector candidates must always be loaded back from SQLite before returning.
- records with relational `status != active` must never be returned as shadow candidates.

## Compatibility Rules

Persisted vector artifacts are compatible only when all of these match current settings:

- `embedding_provider`
- `embedding_model`
- `embedding_dim`
- `namespace`
- `index_type`
- `distance_metric`

Any mismatch must fail closed and require rebuild.

## Sync Rules

- new active memory: `pending`
- active memory with changed `embedding_text_hash`: `stale`
- archived / deleted memory: `deleted`
- restore to active: `pending` or `stale`, then optional best-effort resync
- embedding / FAISS failure: `failed`
- empty or ineligible embedding text: `skipped`

When `MEMORY_VECTOR_ENABLED=1`, sync may best-effort call vector upsert/delete.
Failure still must not fail the relational memory operation.

## Sensitive Text Boundary

- secret-like metadata (`token`, `password`, `secret`, `api_key`, similar fields) must not enter embedding text
- `metadata_json.raw_sql` and `metadata_json.raw_citations` must not be appended into embedding text
- governed `memory.content` is still allowed to contain SQL case / error content

## Search Semantics

- vector retrieval uses FAISS `IndexFlatL2`
- debug `raw_distance` is returned directly
- debug `score = 1 / (1 + raw_distance)`
- score is not a calibrated production relevance score in M6A

## Stage Status

- `M5 completed`
- `M6A implemented / pending acceptance`
- `M6B not started`
