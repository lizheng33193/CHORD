# M2D-12 RiskKnowledgeService Review

## Summary

`M2D-12` landed a CHORD-owned `RiskKnowledgeService` that consumes `RiskEvidenceBundle` and returns deterministic grounded answers or deterministic refusals, plus the smallest viable NL Chat and Profile Explanation consumer seams.

## Scope

This phase adds:

- `app/risk_knowledge/service`
- deterministic grounded answer synthesis
- deterministic refusal assembly
- rendered citation output
- conservative risk-knowledge route policy
- minimal `risk_knowledge_answer` orchestrator flow
- minimal `ProfileExplanationAdapter`

It does not add admin API/UI, document upload, golden-set evaluation, frontend work, Data Agent RAG mixing, Elasticsearch, or SWXY runtime imports.

## Service Boundary

The service layer now owns:

- query validation
- conservative route decisions
- `RiskEvidencePipeline` composition
- grounded answer vs refusal branching
- evidence-context shaping
- citation rendering

`RiskKnowledgeService` does not directly orchestrate FAISS, BM25, reranker providers, or evidence-selection internals.

## Consumer Seams

NL Chat integration is limited to:

- `KnownIntent="risk_knowledge_answer"`
- deterministic router hinting
- classifier enum extension
- one dedicated flow that calls `RiskKnowledgeService`

Profile Explanation integration is limited to an adapter that converts `profile_facts` into a fixed query template and delegates to the service.

Neither seam calls Data Agent, loads tool registry, or starts frontend/API runtime work.

## Validation

Validated with:

- `pytest -q tests/risk_knowledge/service tests/risk_knowledge/reranking tests/risk_knowledge/evidence tests/risk_knowledge/retrieval tests/risk_knowledge/embedding tests/knowledge_base`
- `pytest -q tests/orchestrator_agent tests/test_orchestrator_visible_execution.py -k risk_knowledge`
- `python -m compileall -q app/risk_knowledge app/knowledge_base app/services/orchestrator_agent tests/risk_knowledge tests/knowledge_base tests/orchestrator_agent`
- service citation-integrity tests
- refusal path synthesizer-bypass tests
- conservative route-policy tests
- coupling guards over `app/risk_knowledge/service`, its tests, and the orchestrator flow

Default validation remains offline. Real LLM answer smoke is not required for this stage.

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-12 RiskKnowledgeService integration landed; no admin API/UI/golden-set evaluation runtime started`

Acceptance posture:

> `M2D-12 accepted at stage level after targeted RiskKnowledgeService, NL Chat seam, and Profile Explanation adapter validation;`
> `admin API/UI, golden-set evaluation, and production hardening remain future stages.`

Explicitly not started:

- no admin API/UI
- no document upload or reindex/status API
- no golden-set evaluation
- no frontend changes
- no Data Agent RAG mixing
- no ES / SWXY coupling

## Next Step

`M2D-13` remains:

- upload / reindex / status APIs
- management-side runtime surface
- non-consumer operational controls
