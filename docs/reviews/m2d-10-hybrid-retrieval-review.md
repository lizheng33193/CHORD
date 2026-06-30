# M2D-10 Hybrid Retrieval Review

## Summary

`M2D-10` landed CHORD-owned retrieval foundation on top of `M2D-9` active manifests, persisted chunks, and FAISS artifacts.

## Scope

This phase adds:

- query normalization
- query embedding through the existing embedding boundary
- active-scope FAISS retrieval
- active-scope BM25 retrieval
- RRF fusion
- hydrated retrieval candidates

It does not add reranker, evidence gate, `RiskKnowledgeService`, NL Chat integration, Profile Explanation integration, answer generation, API routes, Elasticsearch, or SWXY runtime imports.

## Retrieval Boundary

Added retrieval runtime modules under `app/risk_knowledge/retrieval`:

- typed retrieval schemas and errors
- active manifest resolver
- query embedding service
- FAISS vector retriever
- BM25 tokenizer/index/retriever
- RRF fusion
- retrieval candidate builder
- hybrid retriever

The retrieval layer depends on existing embedding and indexing abstractions instead of provider-specific or runtime-specific imports.

## Active Scope Contract

Scope resolution is explicit:

- `version_id` => explicit active version
- `document_id` => current active version for that document
- `kb_id` only => all active manifests for active versions in that KB

`latest_manifest_index_id` is not used as a retrieval fallback.

## Ranking and Identity

Retrieval identity is fixed as:

- `retrieval_key = "{manifest_index_id}:{chunk_id}"`

Vector ranking is metric-aware and currently supports:

- `l2`

RRF consumes ranks only. Raw vector distance remains diagnostic data.

## Validation

Validated with:

- query normalizer tests
- tokenization tests
- BM25 ranking test
- active scope resolution tests
- vector retrieval test over saved FAISS artifacts
- keyword retrieval test
- hybrid retriever hydration test
- opt-in real query embedding smoke gate

Default tests remain offline. Real query embedding smoke still requires local opt-in configuration.

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-10 hybrid retrieval foundation landed; no rerank/evidence gate/RiskKnowledgeService/API runtime started`

Acceptance posture:

> `M2D-10 accepted at stage level after targeted retrieval foundation validation;`
> `real query embedding smoke remains opt-in;`
> `no rerank/evidence gate/RiskKnowledgeService/API runtime started.`

## Next Step

`M2D-11` remains:

- reranker
- evidence gate
- citation-quality evidence shaping before consumer integration
