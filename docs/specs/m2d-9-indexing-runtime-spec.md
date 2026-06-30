# M2D-9 Indexing Runtime Spec

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-9 indexing job runtime landed; no retrieval/rerank/RiskKnowledgeService/API runtime started`

## 1. Goal

`M2D-9` turns the already-landed M2D-7 and M2D-8 foundations into a real indexing workflow runtime:

- `ParsedDocument / RawParsedChunk`
- `KnowledgeChunk` materialization
- MySQL chunk persistence
- embedding execution
- FAISS build/save
- manifest activation
- Redis runtime state / heartbeat / lock
- retry and rebuild flow

This phase still does not implement retrieval, rerank, `RiskKnowledgeService`, NL Chat, Profile Explanation, or API routes.

## 2. State Split

`M2D-9` uses three separate state layers:

- `KnowledgeDocumentVersion.status`
  - `PARSED`
  - `INDEXING`
  - `INDEXED`
  - `ACTIVE`
  - `REINDEXING`
  - `FAILED`
- `KnowledgeIngestJob.status`
  - `PENDING`
  - `RUNNING`
  - `COMPLETED`
  - `FAILED`
  - `CANCELED`
- Redis runtime state
  - `queued`
  - `running`
  - `completed`
  - `failed`

MySQL durable state is the source of truth. Redis is runtime-only.

## 3. Redis Boundary

Redis is used only for:

- version-level lock
- runtime progress
- heartbeat
- latest-job pointer

Redis must not become the durable job-state truth.

Lock behavior is fixed:

- `SET NX EX` for acquire
- compare-and-renew for renew
- compare-and-delete for release
- lock loss raises `IndexingLockLostError`
- losing the lock blocks manifest activation

## 4. Orchestration Boundary

Public orchestration entry points are:

- `start_initial_index(...)`
- `start_retry(...)`
- `start_rebuild_from_parsed(...)`
- `start_rebuild_from_persisted_chunks(...)`

The runtime remains in-process and does not introduce Celery, RQ, or a distributed worker queue in this phase.

## 5. Transaction and Artifact Safety

`M2D-9` uses step-level transactions only.

Long-running work such as embedding, FAISS build, file writing, checksum calculation, and Redis lock renewal must not be wrapped in one long database transaction.

FAISS artifact safety is fixed:

- write temp files first
- checksum temp artifacts
- atomically rename to final paths
- persist and activate manifest only after artifact verification

## 6. Retry / Rebuild Policy

Retry lineage is explicit:

- each retry creates a new `job_id`
- `root_job_id`, `retry_of_job_id`, and `attempt` are persisted
- only retriable failures are eligible for automatic retry

Rebuild modes are explicit:

- `rebuild_from_parsed`
  - rebuild from parsed inputs
- `rebuild_from_persisted_chunks(force=False)`
  - skip chunk rematerialization and allow manifest reuse when fingerprint matches

Forced rebuild is reserved for future extension and is not the default behavior in this phase.

## 7. Explicit Non-Scope

This phase does not implement:

- retrieval
- BM25 / RRF
- reranker
- evidence gate
- `RiskKnowledgeService`
- NL Chat integration
- Profile Explanation integration
- API routes
- frontend changes
- Elasticsearch adapter
- SWXY runtime imports

## 8. Acceptance Conditions

`M2D-9` is accepted only if:

- MySQL durable state remains the source of truth
- Redis lock blocks same-version concurrent indexing
- losing the Redis lock blocks manifest activation
- runner can execute the full indexing chain end to end
- manifest activation is transactional at version level
- FAISS artifacts are atomically written and checksum-verified before activation
- retry lineage is preserved through `root_job_id / retry_of_job_id / attempt`
- rebuild does not call parser runtime or reintroduce SWXY runtime coupling
