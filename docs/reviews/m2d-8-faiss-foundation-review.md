# M2D-8 FAISS Foundation Review

## Summary

`M2D-8` landed CHORD-owned MySQL metadata persistence, real embedding runtime boundaries, and FAISS index foundation on top of canonical `KnowledgeChunk` inputs.

## Scope

This phase materializes indexing foundation only:

- chunk persistence
- embedding runtime boundaries
- FAISS build/save/load
- manifest and vector-mapping persistence

It does not start retrieval, rerank, `RiskKnowledgeService`, NL Chat integration, Profile Explanation integration, or API routes.

## Persistence Boundary

Added persistence artifacts:

- `knowledge_chunks`
- `knowledge_chunk_embeddings`
- `faiss_index_manifests`
- `faiss_vector_mappings`

Idempotency policy is explicit:

- same `version_id + chunk_id + content_hash` => idempotent success
- same `version_id + chunk_id` with different `content_hash` => `ChunkContentConflictError`
- same chunk/provider/model/dimension with conflicting embedding metadata => `EmbeddingMetadataConflictError`

`KnowledgeChunk` remains the canonical input contract. Persistence adapts from it and does not redefine it.

The persistence layer is MySQL-oriented through the project database/session configuration and SQLAlchemy model contract. Test wiring may use isolated database setup, but the production contract is not an in-memory repository.

## Embedding Boundary

Added CHORD-owned embedding runtime modules:

- `EmbeddingProvider`
- `EmbeddingBatchService`
- `OpenAICompatibleEmbeddingProvider`
- typed embedding errors

Default tests use a deterministic local provider and do not require network access.

Real-provider smoke remains opt-in behind `CHORD_RUN_REAL_EMBEDDING_TESTS=1`.

## FAISS Boundary

Added CHORD-owned FAISS foundation:

- `FaissIndexStore`
- `FaissIndexManifestDraft`
- `FaissIndexManifest`
- `build_faiss_fingerprint`

Stable vector-id policy is explicit:

- sort embeddings lexicographically by `chunk_id`
- assign int64 ids in that order

Manifest state includes checksum, artifact path, mapping path, record count, embedding metadata, and `build_fingerprint`.

## Explicitly Not Started

- retrieval service
- BM25 / RRF
- reranker
- evidence gate
- `RiskKnowledgeService`
- Redis indexing-job orchestration
- consumer integration
- API routes
- frontend changes
- SWXY runtime imports
- Elasticsearch adapter

## Validation

Validated with:

- persistence idempotency/conflict tests
- deterministic embedding contract tests
- FAISS fingerprint and mismatch tests
- targeted `risk_knowledge` + `knowledge_base` suites
- compileall
- `git diff --check`
- coupling guard over new M2D-8 directories

## Acceptance Closure

`M2D-8` is accepted at stage level.

Acceptance basis:

- FAISS is now the `M2D-8` mainline indexing foundation
- Elasticsearch remains only a future optional adapter
- MySQL-oriented metadata persistence has landed
- real embedding runtime boundaries have landed
- FAISS build/save/load foundation has landed
- manifest, mapping, and typed error contracts have landed
- no retrieval, rerank, `RiskKnowledgeService`, API runtime, frontend work, SWXY runtime import, or ES runtime was introduced

Pending but optional validation items:

- full repository regression has not been run in this closure pass
- real embedding smoke remains opt-in behind `CHORD_RUN_REAL_EMBEDDING_TESTS=1`

Workspace hygiene preserved:

- unrelated frontend edits remained untouched
- the unrelated untracked PDF remained untouched

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-8 FAISS foundation landed; no retrieval/rerank/RiskKnowledgeService/API runtime started`

Acceptance posture:

> `M2D-8 accepted at stage level; full repository regression and real embedding smoke remain optional/pending validation items`

## Next Step

`M2D-9` remains:

- indexing job runtime
- Redis task state / lock orchestration
- rebuild and retry flows
