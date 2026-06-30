# M2D Current State and Scope Review

## 1. Review Purpose

This review is a status-calibration and scope-closure document only.

Current `M2D` status must be recorded as:

> `planned; contract/review/design in progress`

This review does not migrate SWXY code, does not add runtime modules, does not add APIs, and does not start implementation.

## 2. Current CHORD Knowledge/RAG Landscape

Current knowledge and retrieval capabilities in CHORD already include:

- `07 Knowledge Base` design and plan artifacts for Data Acquisition knowledge routing
- `M2A Data Agent Knowledge RAG` for SQL-generation grounding
- `M2B Hybrid Retrieval / Governance` for Data Agent retrieval evolution, fallback, provenance, and rollout control
- `M2C` status reconciliation for SQL governance ownership and boundary cleanup
- `M3 Profile DAG Runtime` for profile execution orchestration

These artifacts show that CHORD already has multiple knowledge-related layers, but they were built around Data Agent grounding and profile runtime execution rather than risk-domain document answering.

## 3. Existing Capability Boundary

The current CHORD knowledge and retrieval stack primarily serves the Data Agent path. Existing capability boundaries include:

- schema grounding
- field grounding
- SQL example retrieval
- hybrid candidate grounding
- SQL validator governance
- SQL planning and repair support

This means the current system already supports knowledge-assisted SQL generation and retrieval governance, but it does not yet provide a dedicated document knowledge layer for risk-domain conversation and evidence support.

## 4. Missing Capability

What is still missing is a separate risk-domain document knowledge layer that can support:

- natural-language risk knowledge Q&A
- risk concept explanation
- policy and strategy interpretation
- profile explanation evidence support
- document-governed evidence retrieval for conversation

The missing capability is not another Data Agent retrieval pass. It is a new evidence-grounded document knowledge capability for non-SQL consumers.

## 5. M2D Scope

`M2D` is defined as `Risk Domain Knowledge RAG`.

It is intended to support:

- natural conversation about risk-domain knowledge
- profile explanation evidence enhancement
- risk concept explanation
- policy and strategy wording explanation
- evidence-grounded answers based on curated risk documents

In long-term shape, `M2D` will become:

- a `Knowledge Base Module`
- a `Risk Domain RAG Engine`
- an `Agent Evidence Service`

## 6. M2D Non-Scope

`M2D` is explicitly not responsible for:

- SQL generation
- schema grounding
- SQL example retrieval
- Data Agent table selection
- SQL validator logic
- runtime memory
- temporary session file Q&A
- Data Agent retrieval fusion for SQL generation

`M2D` is not a replacement for `M2A/M2B` Data Agent Knowledge RAG.

## 7. Relationship with SWXY RAG

SWXY is a reusable RAG engineering asset for `M2D`, not a business subsystem to be copied whole into CHORD.

SWXY is useful because it already contains engineering assets for:

- PDF / Word parsing
- OCR and layout analysis
- table recognition
- chunking and tokenization
- embeddings
- Elasticsearch hybrid retrieval
- rerank support

But CHORD still must define its own:

- `kb_id`
- `doc_id`
- `version_id`
- `chunk_id`
- evidence schema
- document lifecycle
- routing rules
- refusal policy
- evaluation contract
- service integration boundary

## 8. Current Status Calibration

Current `M2D` project status is:

> `planned; contract/review/design in progress`

This wording must be kept exactly across `PLANNING.md`, `TASK.md`, and the `M2D` review/spec/plan documents.

## 9. Implementation Not Started

Implementation has not started. The following are still explicitly not started:

- SWXY code migration
- `app/third_party/swxy_rag`
- `app/risk_knowledge`
- `app/knowledge_base`
- NL Chat integration
- Profile Explanation integration
- knowledge-base management API implementation
- ES runtime implementation for `M2D`

## 10. Review Conclusion

CHORD already has Data Agent knowledge grounding and retrieval governance, but it does not yet have an independent risk-domain document knowledge layer.

The correct next step is therefore:

- define the `M2D` contract
- define the knowledge-base module boundary
- define the integration plan

`M2D` should proceed through contract/review/design closure first, with implementation still clearly marked as not started.
