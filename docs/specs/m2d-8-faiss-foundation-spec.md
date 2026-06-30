# M2D-8 FAISS Foundation Spec

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading before this phase starts:

> `M2D-7 metadata and evidence builder landed; no embedding/retrieval/ES runtime started`

## 1. Goal

`M2D-8` turns `M2D-7`'s in-memory `KnowledgeChunk` outputs into a real indexing foundation by adding:

- MySQL metadata persistence
- real embedding runtime
- FAISS index build/save/load
- manifest and vector mapping persistence

This phase does not implement retrieval, rerank, `RiskKnowledgeService`, NL Chat integration, Profile Explanation integration, or management APIs.

## 2. Canonical Input Boundary

`KnowledgeChunk` remains the single canonical chunk domain object.

Persistence, embedding, and indexing layers must adapt from `KnowledgeChunk`. They must not define a second competing chunk schema as the main runtime truth.

## 3. Persistence Boundary

`M2D-8` persists:

- `knowledge_chunks`
- `knowledge_chunk_embeddings`
- `faiss_index_manifests`
- `faiss_vector_mappings`

`knowledge_documents` and `knowledge_document_versions` remain the parent records already defined by the knowledge-base skeleton.

Idempotency policy is fixed:

- same `version_id + chunk_id + content_hash` => idempotent success
- same `version_id + chunk_id` with different `content_hash` => explicit conflict
- conflicting re-embedding metadata for the same chunk => explicit conflict

## 4. Embedding Boundary

`M2D-8` adds a CHORD-owned `EmbeddingProvider` boundary with one real provider implementation:

- `OpenAICompatibleEmbeddingProvider`

Configuration uses CHORD-specific env names and must not reuse SWXY runtime names.

Default tests must not require network access. Real embedding smoke tests run only behind an explicit env flag.

## 5. FAISS Boundary

`M2D-8` uses FAISS as the mainline vector artifact format.

Required behaviors:

- build a real FAISS index from persisted embedding records
- save/load artifacts
- persist stable `vector_id -> chunk_id -> embedding_id` mappings
- persist a manifest with checksum and `build_fingerprint`

`vector_id` policy is fixed to stable int64 ids generated from lexicographically sorted `chunk_id` order.

## 6. Explicit Non-Scope

This phase does not implement:

- Elasticsearch adapter
- SWXY runtime imports
- retrieval service
- BM25 / RRF
- reranker
- evidence gate
- `RiskKnowledgeService`
- NL Chat or Profile Explanation integration
- API routes
- frontend changes

## 7. Acceptance Conditions

`M2D-8` is accepted only if:

- chunk persistence is explicit and idempotent
- embedding/model/dimension metadata are explicit
- FAISS artifacts can be built, saved, and loaded
- manifest and vector mapping behavior are explicit
- coupling guards prove no SWXY / ES / DashScope / consumer-service pollution enters the phase
