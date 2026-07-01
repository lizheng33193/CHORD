# M2D Risk Domain RAG Integration Plan

## Summary

This plan defines the full staged path for `M2D`, with the current implementation having progressed through `M2D-14A`.

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-14A Knowledge Base Admin API landed; no UI/production-hardening runtime started`

## Current Status

Current project reading for `M2D`:

- scope clarified
- SWXY identified as reusable engine asset source
- contract/review/design closure landed
- M2D-4 to M2D-13 code has landed
- `M2D-14A` starts from the accepted `M2D-13` baseline (`origin/codex/m2d-13-golden-evaluation`, closure `fd26319`)
- minimal NL Chat seam has landed
- minimal Profile Explanation adapter seam has landed
- golden-set evaluation harness has landed
- admin API has landed
- no UI or frontend work has started

## Key Decisions

- `M2D` is `Risk Domain Knowledge RAG`, not `Data Agent Knowledge RAG`
- SWXY is a reusable RAG engine asset, not an application subsystem to import whole
- `M2D` requires a `Knowledge Base Module`
- `M2D v1` keeps `MySQL + real embedding + FAISS` as the mainline indexing foundation
- Elasticsearch may exist only as a future optional adapter, not as `M2D-8` mainline
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

### M2D-8 FAISS Foundation

- 目标
  - implement CHORD-owned MySQL metadata persistence, real embedding runtime, and FAISS index foundation
- 输入
  - metadata/enrichment outputs
  - `KnowledgeChunk` canonical contract
- 输出
  - chunk persistence
  - embedding runtime boundary
  - FAISS build/save/load foundation
- 禁止事项
  - no ES adapter
  - no retrieval, rerank, or consumer-facing service work
- 验收标准
  - chunk persistence is idempotent for the same `version_id + chunk_id + content_hash`
  - embedding/model/dimension metadata are explicit
  - FAISS manifest and vector mapping behavior are explicit

### M2D-9 Indexing Job Runtime / Redis Task State

- 目标
  - add runtime orchestration for indexing, rebuild, and retry flows
- 输入
  - `ParsedDocument / RawParsedChunk`
  - M2D-7 materializers
  - M2D-8 persistence / embedding / FAISS foundation
- 输出
  - indexing job runner / orchestrator
  - durable job lineage and document-version activation flow
  - Redis-backed runtime state / heartbeat / locking seams
- 禁止事项
  - no retrieval, rerank, `RiskKnowledgeService`, NL Chat, Profile Explanation, API routes, ES, or SWXY runtime imports
- 验收标准
  - MySQL durable state remains the source of truth
  - Redis lock blocks same-version concurrent indexing
  - lock loss blocks manifest activation
  - retry lineage, rebuild flow, and active-manifest supersede behavior are explicit

### M2D-10 Retrieval Foundation

- 目标
  - add CHORD-owned hybrid retrieval primitives on top of active manifests and persisted chunk artifacts
- 输入
  - M2D-9 active manifest governance
  - FAISS artifact foundation
  - persisted chunk metadata
- 输出
  - query normalizer
  - query embedding service
  - active manifest resolver
  - FAISS vector retriever
  - BM25 keyword retriever
  - RRF fusion
  - hydrated retrieval candidates
- 禁止事项
  - no reranker
  - no evidence gate
  - no `RiskKnowledgeService`
  - no NL Chat or Profile Explanation integration
  - no API routes
  - no ES or SWXY runtime coupling
- 验收标准
  - retrieval scope resolves only active versions and active manifests
  - `kb_id`-only retrieval spans all active manifests in the KB
  - query embedding is executed once per request and reused across the scope
  - vector ranking is metric-aware and currently explicit for `l2`
  - RRF fusion is rank-based
  - hydrated candidates preserve manifest/version/document/chunk identity and `content_hash`

### M2D-11 Reranker / Evidence Gate

- 目标
  - add rerank and evidence-selection controls before consumer integration
- 输入
  - retrieval outputs
  - evidence contract
- 输出
  - rerank and evidence gate
- 禁止事项
  - no NL Chat or Profile Explanation integration yet
- 验收标准
  - citation/evidence boundaries are explicit
  - empty retrieval candidates return `no_candidates` without provider execution
  - provider result mismatch is rejected before evidence shaping
  - `RiskEvidenceBundle` excludes answer-generation fields

### M2D-12 RiskKnowledgeService / Consumer Integration

- 目标
  - expose a single consumer-facing risk knowledge service boundary
- 输入
  - retrieval engine
  - evidence builder
  - refusal rules
- 输出
  - `RiskKnowledgeService`
  - deterministic grounded answer / refusal contract
  - minimal NL Chat seam
  - minimal Profile Explanation adapter seam
- 禁止事项
  - no admin API/UI
  - no frontend changes
  - no document upload
  - no golden-set evaluation
  - no Data Agent RAG mixing
  - no ES or SWXY runtime coupling
- 验收标准
  - `RiskKnowledgeService` depends on a thin `RiskEvidencePipeline`
  - refusal path does not call answer synthesis
  - grounded answers only use selected evidence and rendered citations
  - NL Chat and Profile Explanation can consume service outputs without infrastructure coupling
  - route policy remains conservative and does not steal SQL / UID / cohort / trace / workspace follow-up queries

### M2D-13 Golden Set Evaluation + Regression

- 目标
  - build a repeatable golden-set evaluation and regression framework for the existing M2D runtime chain
- 输入
  - retrieval engine
  - rerank and evidence outputs
  - `RiskKnowledgeService` answer / refusal outputs
- 输出
  - golden-set case schema
  - loader and matchers
  - retrieval / rerank / evidence / gate / citation / answer metrics
  - evaluator and report builder
  - advisory regression decision
  - fixture CLI and runtime opt-in CLI
- 禁止事项
  - no admin API/UI
  - no upload / reindex / status runtime
  - no frontend changes
  - no Data Agent RAG mixing
  - no ES or SWXY runtime coupling
- 验收标准
  - evaluation logic lives under `app/risk_knowledge/evaluation`
  - app code does not import `tests.golden`
  - trace seams remain read-only
  - fixture mode remains offline-safe
  - runtime mode remains opt-in
  - advisory regression decision is report-only in v1

### M2D-14A Knowledge Base Admin API

- 目标
  - expose management-side upload / reindex / status APIs for the knowledge-base runtime
- 输入
  - knowledge-base module
  - ingest-job model
- 输出
  - upload / reindex / status management APIs
  - durable knowledge-base CRUD
  - retrieval-only debug API
- 禁止事项
  - no consumer retrieval bypass through management routes
  - no UI console or worker queue
- 验收标准
  - management APIs expose explicit KB / document / version / ingest state
  - uploads stay local-only with bounded file handling
  - `debug/retrieve` remains retrieval-only and does not call `RiskKnowledgeService`

### M2D-14B Knowledge Base UI Console

- 目标
  - add a management-side UI console on top of the admin API surface
- 输入
  - `M2D-14A` API runtime
- 输出
  - knowledge-base admin UI console
- 禁止事项
  - no production-hardening expansion yet
- 验收标准
  - upload / status / reindex flows are operable from UI without changing M2D runtime semantics

### M2D-15 Production Hardening

- 目标
  - harden the full M2D runtime after evaluation and admin surfaces exist
- 输入
  - evaluation framework
  - admin API and UI console
- 输出
  - production hardening artifacts
  - final acceptance closure
- 禁止事项
  - no informal closure without evidence
- 验收标准
  - routing, refusal, groundedness, citation behavior, and operational readiness are verified

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
- expanding admin runtime before measuring M2D quality

## Acceptance Gate

The current pass is accepted only if:

- `PLANNING.md` and `TASK.md` use the exact status string `M2D implementation in progress`
- subphase wording stays at `M2D-14A Knowledge Base Admin API landed; no UI/production-hardening runtime started`
- `M2D` does not use any completion-state label
- no runtime dependencies, routes, migrations, persistence, retrieval services, or consumer integrations are added in planning-only phases
- existing `M2C/M3` closure wording remains untouched
