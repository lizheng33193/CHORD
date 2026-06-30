# M2D-12 RiskKnowledgeService Spec

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-12 RiskKnowledgeService integration landed; no admin API/UI/golden-set evaluation runtime started`

## 1. Goal

`M2D-12` turns `RiskEvidenceBundle` into a consumer-facing service contract through:

- `RiskKnowledgeService`
- deterministic grounded answer / refusal assembly
- minimal NL Chat seam
- minimal Profile Explanation adapter seam

This phase still does not implement admin API/UI, document upload, reindex/status APIs, golden-set evaluation, frontend work, Data Agent RAG mixing, Elasticsearch, or SWXY runtime coupling.

## 2. Service Boundary

`app/risk_knowledge/service` owns:

- `RiskKnowledgeQuery`
- `RiskKnowledgeAnswer`
- `RenderedCitation`
- `EvidenceContext`
- `GroundedAnswerRequest`
- `GroundedAnswerResult`
- `RouteDecision`
- `ProfileExplanationRequest`
- `RiskEvidencePipeline`
- `RiskKnowledgeService`

`RiskKnowledgeService` depends on `RiskEvidencePipeline` rather than directly orchestrating FAISS, BM25, reranking providers, evidence selectors, or citation builders.

## 3. Evidence Consumption Boundary

`RiskEvidencePipeline` is a thin composition seam over:

- `HybridRiskKnowledgeRetriever`
- `RiskEvidenceBundleBuilder`

`EvidenceContextBuilder` only consumes `selected_evidence` and matching citations from the bundle.

It must preserve:

- `citation_id`
- `document_id`
- `version_id`
- `chunk_id`
- page metadata when present
- section metadata when present

It must not use rejected or unselected retrieval candidates.

## 4. Answer Contract

`RiskKnowledgeAnswer` must preserve:

- `query`
- `normalized_query`
- `kb_id`
- `answer`
- `answer_type`
- `should_answer`
- `refusal_reason`
- `evidence_bundle`
- `citations`
- `used_citation_ids`
- `diagnostics`

`answer_type` is fixed to:

- `grounded_answer`
- `refusal`

If `should_answer=false`, then `answer_type` must be `refusal`.

## 5. Deterministic Answer Synthesis

Default answer synthesis is deterministic and offline.

The default synthesizer must:

- use only `EvidenceContext`
- avoid introducing new facts
- avoid inventing citations
- return only citation ids that exist in rendered citations

Real LLM answer providers may be added later behind a separate seam, but they are not part of `M2D-12` default acceptance.

## 6. Refusal Path

If `RiskEvidenceBundle.should_answer=false`, the service must:

- return a refusal answer
- preserve `evidence_bundle`
- preserve rendered citations for selected evidence when present
- preserve diagnostics

The refusal path must not call the answer synthesizer or an LLM provider.

## 7. Route Policy And Consumer Seams

`RiskKnowledgeRoutePolicy` stays conservative.

It may route:

- risk concept explanation
- risk indicator explanation
- strategy rationale explanation
- explicit profile explanation

It must not capture:

- SQL queries
- UID queries
- cohort queries
- trace requests
- workspace follow-up routing
- Data Agent requests
- ambiguous data/profile requests

The NL Chat seam is limited to a new `risk_knowledge_answer` intent and flow. It must not load tool registry, call Data Agent, or alter existing intent meaning and priority.

## 8. Profile Explanation Adapter

`ProfileExplanationAdapter` only converts profile facts into a `RiskKnowledgeQuery` and delegates to `RiskKnowledgeService`.

The query template is fixed to:

`请基于风控领域知识解释以下画像事实为什么可能表示风险：{profile_facts}`

This adapter must not query user databases, call Data Agent, or recompute profile outputs.

## 9. Acceptance Conditions

`M2D-12` is accepted only if:

- `RiskKnowledgeService` depends on `RiskEvidencePipeline`
- grounded answers and refusals use explicit `answer_type`
- refusal path bypasses answer synthesis
- rendered citations map back to selected evidence
- answer citation ids are validated against rendered citations
- route policy remains conservative
- NL Chat and Profile Explanation seams stay minimal
- default acceptance remains offline and does not require real LLM smoke
- no admin API/UI, frontend, Data Agent RAG mixing, ES, or SWXY runtime coupling starts in this phase
