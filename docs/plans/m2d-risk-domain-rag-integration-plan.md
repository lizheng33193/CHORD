# M2D Risk Domain RAG Integration Plan

## Summary

This plan defines the full staged path for `M2D`, with the current implementation having progressed through `M2D-7`.

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-7 metadata and evidence builder landed; no embedding/retrieval/ES runtime started`

## Current Status

Current project reading for `M2D`:

- scope clarified
- SWXY identified as reusable engine asset source
- contract/review/design closure landed
- M2D-4 to M2D-7 code has landed
- no NL Chat integration started
- no Profile Explanation integration started

## Key Decisions

- `M2D` is `Risk Domain Knowledge RAG`, not `Data Agent Knowledge RAG`
- SWXY is a reusable RAG engine asset, not an application subsystem to import whole
- `M2D` requires a `Knowledge Base Module`
- `M2D v1` keeps Elasticsearch hybrid retrieval as the default direction
- `user_id/session_id -> index_name` coupling must be removed

## Phase Breakdown

### M2D-0 Current State & Scope Review

- 目标
  - calibrate current CHORD knowledge landscape and define `M2D` scope
- 输入
  - `PLANNING.md`
  - `TASK.md`
  - existing `M2A/M2B/M2C/M3` docs
- 输出
  - `docs/reviews/m2d-current-state-and-scope-review.md`
- 禁止事项
  - no runtime changes
  - no SWXY migration
  - no new module creation
- 验收标准
  - `M2D` is clearly separated from Data Agent Knowledge RAG
  - current status is recorded as `M2D implementation in progress`

### M2D-1 SWXY RAG Integration Review

- 目标
  - classify SWXY assets into reusable, adapter-required, and forbidden migration sets
- 输入
  - SWXY repository structure and known asset list
- 输出
  - `docs/reviews/m2d-existing-rag-integration-review.md`
- 禁止事项
  - no vendor import
  - no dependency addition
- 验收标准
  - direct reuse, adapter required, and do not migrate assets are explicit
  - coupling risks are documented

### M2D-2 Risk Domain RAG Contract

- 目标
  - define the future retrieval, evidence, routing, refusal, and trace contracts
- 输入
  - `M2D-0` and `M2D-1` review outputs
- 输出
  - `docs/specs/m2d-risk-domain-knowledge-rag-contract.md`
- 禁止事项
  - no consumer implementation
  - no ES access implementation
- 验收标准
  - metadata and evidence schemas are explicit
  - routing and refusal boundaries are explicit

### M2D-3 Knowledge Base Module Design

- 目标
  - define the management-side module boundary for long-term document knowledge
- 输入
  - `M2D-0` scope boundary
  - `M2D-1` engine-asset review
  - `M2D-2` service contract
- 输出
  - `docs/specs/m2d-knowledge-base-module-design.md`
- 禁止事项
  - no API implementation
  - no DB migration
- 验收标准
  - KB/document/version/chunk/job entities are explicit
  - lifecycle and API draft are explicit

### M2D-4 Third-party SWXY RAG Vendor Import

- 目标
  - isolate SWXY engine assets under a CHORD-owned third-party boundary
- 输入
  - `M2D-1` asset classification
- 输出
  - vendor-imported engine assets under a dedicated boundary
- 禁止事项
  - no old SWXY application shell migration
- 验收标准
  - imported assets are isolated
  - old app coupling is not imported

### M2D-5 Knowledge Base Module Skeleton

- 目标
  - create the runtime skeleton for knowledge-base management
- 输入
  - `M2D-3` design
- 输出
  - initial module, contracts, and storage boundary
- 禁止事项
  - no consumer integration yet
- 验收标准
  - KB/document/version/job ownership is represented in code

### M2D-6 SWXY Ingestion Adapter

- 目标
  - adapt SWXY parsing/chunking pipeline to CHORD document/version semantics
- 输入
  - imported engine assets
  - `M2D-3` lifecycle design
- 输出
  - CHORD-owned ingestion adapter
- 禁止事项
  - no legacy `user_id/session_id` semantics
- 验收标准
  - `kb_id/doc_id/version_id/index_name` semantics are explicit

### M2D-7 Metadata & Evidence Builder

- 目标
  - build CHORD-owned metadata and evidence shaping logic
- 输入
  - chunk outputs from ingestion adapter
  - `M2D-2` evidence contract
- 输出
  - document metadata builder
  - chunk metadata builder
  - evidence builder
- 禁止事项
  - no bare chunk exposure to consumers
  - no repository lookup or service calls inside builders
  - no embedding, ES indexing, retrieval, rerank, persistence, or Agent-facing service work
- 验收标准
  - evidence payloads conform to contract
  - builders accept only `ParsedDocument + KnowledgeDocument + KnowledgeDocumentVersion`
  - `KnowledgeDocumentVersion.status == parsed` is enforced
  - `RiskEvidence` remains draft evidence with `score = None`

### M2D-8 ES Hybrid Index Adapter

- 目标
  - implement CHORD-owned ES index and alias integration
- 输入
  - metadata/enrichment outputs
  - ES naming contract
- 输出
  - ES hybrid index adapter
- 禁止事项
  - no direct consumer ES access
- 验收标准
  - versioned physical index and active alias behavior are explicit

### M2D-9 RiskKnowledgeService

- 目标
  - expose a single consumer-facing risk knowledge service boundary
- 输入
  - retrieval engine
  - evidence builder
  - refusal rules
- 输出
  - `RiskKnowledgeService`
- 禁止事项
  - no direct ES access from consumers
- 验收标准
  - NL Chat and Profile Explanation can consume service outputs without infrastructure coupling

### M2D-10 Upload / Reindex / Status API

- 目标
  - implement KB management APIs
- 输入
  - knowledge-base module
  - ingest-job model
- 输出
  - upload/reindex/status management APIs
- 禁止事项
  - no consumer retrieval bypass through management routes
- 验收标准
  - management APIs expose explicit document and ingest state

### M2D-11 NL Chat / Profile Explanation Integration

- 目标
  - integrate `RiskKnowledgeService` into conversation and profile-explanation paths
- 输入
  - service boundary
  - routing contract
- 输出
  - routed consumer integrations
- 禁止事项
  - no direct ES or chunk access in consumer code
- 验收标准
  - only in-scope requests route to `M2D`

### M2D-12 Refusal / Eval / Acceptance Review

- 目标
  - complete refusal, evaluation, and acceptance closure for the first runtime release
- 输入
  - implemented retrieval and consumer integrations
- 输出
  - evaluation artifacts
  - acceptance review
- 禁止事项
  - no informal closure without evidence
- 验收标准
  - routing, refusal, groundedness, and citation behavior are verified

## Non-Goals

This plan does not make `M2D` responsible for:

- SQL generation
- schema grounding
- SQL validator governance
- Data Agent table selection
- runtime memory
- temporary session document QA

## Risks

Primary integration risks are:

- importing SWXY app-shell coupling instead of engine assets
- preserving `user_id/session_id -> index_name` semantics
- confusing `quick_parse` with long-term KB ingestion
- letting consumers bypass `RiskKnowledgeService`
- treating raw engine import as if it were a complete CHORD module

## Acceptance Gate

The current pass is accepted only if:

- `PLANNING.md` and `TASK.md` use the exact status string `M2D implementation in progress`
- subphase wording stays at `M2D-7 metadata and evidence builder landed; no embedding/retrieval/ES runtime started`
- `M2D` does not use any completion-state label
- no runtime dependencies, routes, migrations, persistence, ES runtime, or retrieval services are added
- existing `M2C/M3` closure wording remains untouched
