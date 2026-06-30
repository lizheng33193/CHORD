# M2D-7 Metadata & Evidence Builder Review

## Summary

M2D-7 lands pure CHORD-owned metadata and evidence builders that materialize in-memory `KnowledgeChunk` and draft `RiskEvidence` contracts from `ParsedDocument / RawParsedChunk` plus explicit document/version metadata.

It does not persist chunks, call repositories or services, invoke SWXY, write Elasticsearch, embed content, retrieve, rerank, expose APIs, or integrate with Agents.

Current top-level project reading for `M2D` is:

> `M2D implementation in progress`

Current subphase reading is:

> `M2D-7 metadata and evidence builder landed; no embedding/retrieval/ES runtime started`

## Scope

This phase is intentionally limited to:

- content hash normalization and hashing
- `RawParsedChunk -> KnowledgeChunk` materialization
- `KnowledgeChunk -> RiskEvidence` draft materialization
- pure builder-side identity and status validation
- fake parsed-document-driven tests

## Builder Boundary

Builders use `Pure Inputs` only:

- `ParsedDocument`
- `KnowledgeDocument`
- `KnowledgeDocumentVersion`

The builders:

- do not query repositories
- do not call `DocumentService` or `IngestJobService`
- do not modify `M2D-6` parser-side contracts
- do not call SWXY or downstream retrieval/indexing infrastructure

## Added Contracts

This phase adds:

- `app/risk_knowledge/schemas.py`
- `RiskEvidence`
- `RiskEvidenceScore`
- `EvidenceUsage`
- `MetadataBuildResult`
- `EvidenceBuildResult`
- `app/risk_knowledge/metadata/`

`KnowledgeChunk` is extended with source-facing metadata fields:

- `source_type`
- `source_uri`
- `source_metadata`

These remain metadata-only contract fields. Their presence does not mean embedding, ES indexing, or retrieval runtime has started.

## Hash Contract

`content_hash.py` defines the stable rule for `content_hash`:

- normalize line endings to `\n`
- trim each line individually
- preserve line order
- preserve empty lines
- final digest format is `sha256:<hex>`

## Evidence Contract

`M2D-7` produces draft evidence only:

- `evidence_id = "ev_" + chunk_id`
- `score = None`
- `usage = supporting_evidence`

Retrieval-time scores remain deferred:

- `fulltext_score`
- `vector_score`
- `rerank_score`
- `final_score`

## Explicitly Not Started

The following remain intentionally not started:

- repository lookup inside builders
- service calls inside builders
- `KnowledgeChunk` persistence
- embedding
- ES indexing
- retrieval
- rerank
- `RiskKnowledgeService`
- upload/reindex/status API
- NL Chat integration
- Profile Explanation integration

## Validation

The following validation commands were run:

- `pytest -q tests/risk_knowledge/metadata tests/knowledge_base`
- coupling guard over `app/risk_knowledge/metadata` and `tests/risk_knowledge/metadata`
  - forbidden runtime coupling terms: `file_parse_core`, `retrieval_core`, `elasticsearch`, `dashscope`, `RiskKnowledgeService`, `app.third_party.swxy_rag`

## Status

`M2D implementation in progress`

`M2D-7 metadata and evidence builder landed; no embedding/retrieval/ES runtime started`

## Next Step

`M2D-8 ES Hybrid Index Adapter`
