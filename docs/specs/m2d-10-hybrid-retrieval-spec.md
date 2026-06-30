# M2D-10 Hybrid Retrieval Spec

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-10 hybrid retrieval foundation landed; no rerank/evidence gate/RiskKnowledgeService/API runtime started`

## 1. Goal

`M2D-10` lands the retrieval foundation on top of `M2D-9` active manifests and persisted chunk artifacts:

- query normalization
- one-shot query embedding
- active-scope FAISS retrieval
- active-scope BM25 retrieval
- RRF fusion
- hydrated retrieval candidates

This phase still does not implement reranking, evidence sufficiency, answer generation, `RiskKnowledgeService`, NL Chat, Profile Explanation, API routes, Elasticsearch, or SWXY runtime coupling.

## 2. Retrieval Scope Policy

`RetrievalQuery` accepts:

- `query`
- `kb_id`
- optional `document_id`
- optional `version_id`

Active scope resolution is fixed:

- `version_id` => explicit active version scope
- `document_id` without `version_id` => that document's current active version
- `kb_id` only => all active versions with active manifests in that KB

The retrieval layer does not invent a new document-active rule and does not fall back to `latest_manifest_index_id`.

## 3. Active Manifest Boundary

`ActiveManifestResolver` only resolves durable active scope and validates metadata compatibility:

- `embedding_provider`
- `embedding_model`
- `embedding_dimension`
- `distance_metric`

It does not load FAISS bytes or verify artifact checksums directly. Artifact verification stays inside FAISS loading.

## 4. Query Embedding Boundary

`QueryEmbeddingService` depends on the generic `EmbeddingProvider` contract only.

It sends one `EmbeddingInput` with:

- `input_type="query"`

Provider-specific translation, including DashScope query/document request differences, stays inside embedding-provider implementations.

Retrieval code must not import `dashscope` or read `DASHSCOPE_API_KEY`.

## 5. Retrieval Identity and Ranking

All retrieval channels use:

- `retrieval_key = "{manifest_index_id}:{chunk_id}"`

This prevents ambiguity when `kb_id`-only retrieval spans multiple active manifests.

Vector ranking is metric-aware:

- current supported metric: `l2`
- lower raw distance is better
- RRF consumes rank only, not raw vector score

`raw_score` remains diagnostic metadata.

## 6. Keyword Retrieval Boundary

`M2D-10` builds BM25 at query time over all active chunks in scope:

- one corpus per resolved retrieval scope
- optional in-process cache keyed by active-scope fingerprint
- no persisted BM25 artifact
- no `jieba` mainline dependency

Default tokenization is:

- Chinese unigram + bigram
- lowercase English/numeric word tokens
- punctuation filtered

## 7. Candidate Hydration Boundary

`RetrievalCandidateBuilder` hydrates fused hits from persisted chunk records using version-aware lookup.

It returns source-rich candidates with:

- `document_id`
- `version_id`
- `manifest_index_id`
- `chunk_id`
- `content_hash`
- chunk text and section/page metadata

It does not perform evidence sufficiency or refusal logic.

## 8. Explicit Non-Scope

This phase does not implement:

- reranker
- evidence gate
- `RiskKnowledgeService`
- NL Chat integration
- Profile Explanation integration
- answer generation
- API routes
- frontend changes
- Elasticsearch
- SWXY runtime imports

## 9. Acceptance Conditions

`M2D-10` is accepted only if:

- active scope resolves only active versions and active manifests
- no fallback to latest manifest exists
- query embedding happens once per retrieval request
- FAISS retrieval is checksum-verified through artifact load
- vector ranking is `l2`-aware
- RRF uses rank-based fusion
- candidates preserve `document_id / version_id / manifest_index_id / chunk_id / content_hash`
- real query embedding smoke remains opt-in
