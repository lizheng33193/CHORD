# M2D Knowledge Base Module Design

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-9 indexing job runtime landed; no retrieval/rerank/RiskKnowledgeService/API runtime started`

This document remains the long-term management-side design source and is updated to align the current runtime foundation with the FAISS-based indexing mainline.

## 1. Purpose

This document defines the management-side module boundary required for `M2D`.

`M2D` is not a one-off document ingestion script. It must be designed as a reusable knowledge-base capability that can serve stable evidence retrieval for future agents.

## 2. Why M2D Needs a Knowledge Base Module

`M2D` must support more than a single import of one risk guide. It needs a knowledge-base module because future usage requires:

- multiple documents
- upload and re-upload
- document updates
- version management
- reindexing
- deprecating old versions
- retrieval testing
- ingest status tracking
- failure inspection

Without a management-side module boundary, the system would collapse back into temporary one-off RAG ingestion.

## 3. Module Boundary

`M2D` is divided into three future runtime roles:

- `Knowledge Base Module`
  - owns management concerns such as KB, document, version, status, and ingest lifecycle
- `Risk Domain RAG Engine`
  - owns parsing, chunking, persistence adaptation, embedding, FAISS indexing, retrieval, and rerank
- `RiskKnowledgeService`
  - owns the agent-facing evidence consumption boundary

This split keeps ingestion, retrieval, and consumer usage from collapsing into one mixed module.

## 4. Core Entities

The core entity model is:

- `knowledge_base`
- `document`
- `document_version`
- `chunk`
- `ingest_job`

## 5. Default Knowledge Base

The default `M2D` knowledge base is:

- `kb_id: risk_domain_knowledge`
- `kb_name: 风控领域知识库`
- `kb_type: risk_domain`

## 6. Document Lifecycle

The indexing-facing document-version lifecycle is:

`parsed -> indexing -> indexed -> active`

Supporting runtime states:

- `reindexing`
- `failed`

Governance-only archival states may still exist for management-side version retirement, but they are not mixed into indexing-job runtime state.

This lifecycle must be represented explicitly in future implementation rather than inferred from raw file presence.

## 7. Data Model Draft

The initial management-side table draft is:

- `knowledge_bases`
- `knowledge_documents`
- `knowledge_document_versions`
- `knowledge_chunks`
- `knowledge_ingest_jobs`

Suggested ownership by table:

- `knowledge_bases`
  - KB identity, name, type, status, ownership scope
- `knowledge_documents`
  - logical document identity, source metadata, current active version
- `knowledge_document_versions`
  - version state, parser/chunker metadata, ingest result summary
- `knowledge_chunks`
  - retrievable text unit plus retrieval metadata
- `knowledge_ingest_jobs`
  - upload, reindex, deprecate, failure, and status tracking

## 8. API Draft

The management API draft is:

- `POST /api/knowledge-bases`
- `GET /api/knowledge-bases`
- `GET /api/knowledge-bases/{kb_id}`
- `POST /api/knowledge-bases/{kb_id}/documents/upload`
- `GET /api/knowledge-bases/{kb_id}/documents`
- `GET /api/knowledge-bases/{kb_id}/documents/{doc_id}`
- `POST /api/knowledge-bases/{kb_id}/documents/{doc_id}/reindex`
- `POST /api/knowledge-bases/{kb_id}/documents/{doc_id}/deprecate`
- `DELETE /api/knowledge-bases/{kb_id}/documents/{doc_id}`
- `GET /api/knowledge-bases/{kb_id}/ingest-jobs/{job_id}`
- `POST /api/knowledge-bases/{kb_id}/retrieval-test`

These are draft contracts only. No route, schema, or service is implemented in this pass.

## 9. Indexing Foundation Design

The `M2D v1` indexing mainline is:

- metadata persistence in MySQL
- real embedding runtime selected by CHORD config
- FAISS artifact build/save/load
- manifest + vector mapping persistence

Elasticsearch is not the default `M2D-8` target anymore. If it is added later, it must be treated as an optional adapter rather than the mainline indexing boundary.

## 10. Upload / Reindex / Status Flow

The intended high-level flow is:

1. create or resolve target knowledge base
2. upload document and create durable ingest job
3. parse document into structured content
4. materialize canonical `KnowledgeChunk`
5. persist chunk and embedding/index metadata
6. build and save FAISS index artifacts
7. activate the manifest for the version in a short transaction
8. expose durable job state and Redis runtime state for management APIs

Reindex follows the same chain but starts from an existing logical document and either a new parsed version or persisted chunks, depending on the rebuild trigger.

## 11. M2D-9 Runtime State Split

`M2D-9` formalizes three separate state layers:

- `KnowledgeDocumentVersion.status`
  - durable document-version lifecycle state
- `KnowledgeIngestJob.status`
  - durable job lifecycle state
- Redis runtime state
  - ephemeral progress, heartbeat, latest-job pointer, and lock ownership

MySQL durable state is the source of truth. Redis must never be treated as the final durable status record.

## 12. quick_parse Boundary

`quick_parse` belongs to temporary session-style document Q&A and does not belong to the long-term knowledge-base mainline.

`M2D` must not adopt `quick_parse` as its ingestion or serving model.

## 13. RiskKnowledgeService Boundary

`RiskKnowledgeService` is the future consumer boundary.

The boundary rules are:

- agents do not call ES directly
- agents do not call FAISS or embedding artifacts directly
- agents do not call KB management APIs directly for retrieval
- agents do not assemble evidence from bare chunks
- retrieval, rerank, refusal, and evidence shaping must be mediated through the service boundary

## 14. Acceptance Criteria

Future implementation acceptance should require:

- KB, document, version, and ingest-job states are explicit
- active version and deprecated version behavior are distinguishable
- upload/reindex/status flows are observable
- `quick_parse` remains out of the long-term KB mainline
- consumers use `RiskKnowledgeService` rather than direct ES access
- SQL and Data Agent grounding remain outside this module boundary
