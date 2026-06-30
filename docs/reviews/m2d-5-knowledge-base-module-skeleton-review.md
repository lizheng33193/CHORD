# M2D-5 Knowledge Base Module Skeleton Review

## Summary

This phase lands a CHORD-native `app/knowledge_base` management-side skeleton for `M2D`.

It introduces strict domain contracts, lifecycle helpers, repository protocols, in-memory repositories, and metadata-only services without starting SWXY ingestion, ES indexing, retrieval, API wiring, or Agent integration.

Current top-level project reading for `M2D` is:

> `M2D implementation in progress`

Current subphase reading is:

> `M2D-5 knowledge base module skeleton landed; no ingestion/retrieval runtime started`

## Scope

This phase is intentionally limited to:

- knowledge-base domain schemas
- document and document-version metadata schemas
- ingest-job schema and status helpers
- chunk schema-only contract
- lifecycle transition helpers
- repository protocols
- in-memory repository implementations for tests
- metadata-only services

This phase does not start ingestion, retrieval, indexing, or consumer integration.

## Added Runtime Boundary

This phase adds the following CHORD-native runtime boundary:

- `app/knowledge_base/`

The subtree contains:

- config constants for the default risk-domain KB contract
- Pydantic domain contracts
- lifecycle transition helpers
- deterministic ID helpers
- repository protocols
- in-memory repositories
- metadata-only services

## Core Entities

The skeleton now defines the following core entities:

- `knowledge_base`
- `document`
- `document_version`
- `chunk`
- `ingest_job`

`chunk` is included only as a schema-level contract in this phase.

## Lifecycle Contract

The skeleton explicitly represents the version/job lifecycle:

`uploaded -> parsing -> parsed -> chunking -> embedding -> indexing -> indexed -> active`

Additional supported transitions are:

- `active -> deprecated`
- `deprecated -> deleted`
- `active -> reindexing -> indexed -> active`
- processing states may transition to `failed`

Only version/job lifecycle helpers are implemented in this phase. No ingestion runtime is attached.

## Default Knowledge Base

The default management contract is:

- `kb_id: risk_domain_knowledge`
- `kb_name: 风控领域知识库`
- `kb_type: risk_domain`
- `index_alias: chord_m2d_risk_knowledge_active`

`ensure_default_risk_domain_knowledge_base()` is idempotent.

Default-KB drift detection is deferred.

## Repository Boundary

This phase introduces repository boundaries for:

- `KnowledgeBaseRepository`
- `KnowledgeDocumentRepository`
- `KnowledgeIngestJobRepository`

The only implementation in this phase is in-memory test storage.

There is no DB repository, no SQLAlchemy integration, and no migration in this phase.

`KnowledgeChunkRepository` is intentionally not implemented in `M2D-5`.

## Service Boundary

This phase introduces metadata-only services for:

- knowledge-base management
- document/document-version metadata management
- ingest-job state management

These services do not:

- parse files
- call SWXY
- create chunks
- generate embeddings
- connect Elasticsearch
- expose HTTP routes
- serve consumer-facing retrieval

## Explicitly Not Started

The following remain intentionally not started:

- SWXY ingestion adapter
- SWXY retrieval adapter
- ES runtime integration
- chunk repository/service implementation
- `RiskKnowledgeService`
- upload/reindex/status API
- `app/risk_knowledge`
- NL Chat integration
- Profile Explanation integration

## Validation

The following validation commands were run:

- `pytest -q tests/knowledge_base`
  - result: `55 passed`
- `python - <<'PY' ... importlib.util.find_spec(...) ... PY`
  - result: representative `app.knowledge_base` modules were discoverable
- `python - <<'PY' ... ast.parse(...) ... PY`
  - result: syntax check passed for `app/knowledge_base` and `tests/knowledge_base`
- `rg --files app | rg "risk_knowledge"`
  - result: no `app/risk_knowledge` runtime tree was added
- precise coupling guard search for SWXY / ES / DashScope / `RiskKnowledgeService`
  - result: no forbidden imports or runtime calls found in `app/knowledge_base` or `tests/knowledge_base`

## Status

`M2D implementation in progress`

`M2D-5 knowledge base module skeleton landed; no ingestion/retrieval runtime started`

## Next Step

`M2D-6 SWXY Ingestion Adapter`
