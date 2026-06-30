# M2D-11 Reranker + Evidence Gate Spec

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-11 reranker and evidence gate landed; no RiskKnowledgeService/API/NL Chat/Profile Explanation runtime started`

## 1. Goal

`M2D-11` converts `HybridRetrievalCandidate[]` into a structured `RiskEvidenceBundle` through:

- reranker provider execution
- deterministic evidence selection
- deterministic evidence gate
- stable citation building

This phase still does not implement `RiskKnowledgeService`, NL Chat integration, Profile Explanation integration, answer generation, API routes, frontend work, Elasticsearch, or SWXY runtime imports.

## 2. Reranker Boundary

`app/risk_knowledge/reranking` owns:

- typed rerank request/result contracts
- stable content-derived `candidate_id`
- deterministic offline provider
- DashScope HTTP provider
- provider factory
- provider-output validation and rank rebuilding

Only `dashscope_provider.py` may access DashScope transport details or `DASHSCOPE_API_KEY`.

## 3. Empty Candidate Policy

The empty-candidate policy is split by layer:

- provider boundary: empty candidates are invalid input
- bundle/pipeline boundary: empty retrieval candidates are a valid business result and must return `should_answer=false` with `reason=no_candidates`

The bundle path must not call the provider when retrieval returns no candidates.

## 4. Evidence Selection Boundary

`EvidenceSelector` uses rerank output plus retrieval metadata and applies fixed rules:

- sort by `rerank_rank`
- filter by `min_rerank_score`
- keep at most `max_evidence_count`
- deduplicate by `chunk_id`
- optionally deduplicate by `content_hash`
- enforce `max_total_chars` by skipping oversized additions rather than truncating text

Diagnostics preserve:

- `skipped_by_total_chars`
- `skipped_by_duplicate`
- `selected_total_chars`

## 5. Evidence Gate Boundary

`EvidenceGate` is deterministic and does not call an LLM judge.

It must refuse or degrade when:

- no retrieval candidates exist
- no rerank hits exist
- selected evidence count is below threshold
- top rerank score is below threshold
- selected evidence text is empty

Gate diagnostics must preserve:

- `rerank_provider`
- `rerank_model`
- `top_rerank_score`
- `min_rerank_score`
- `selected_count`
- `threshold_source`

If gate fails after evidence has been selected, the bundle still preserves `selected_evidence` and `citations`.

## 6. Citation Contract

`CitationBuilder` creates stable citations using:

- `document_id`
- `version_id`
- `chunk_id`
- `content_hash`

`citation_id` is hash-derived from those stable fields and must not depend on rerank order.

Each citation must preserve:

- `chunk_id`
- `version_id`
- `manifest_index_id`
- `content_hash`
- page metadata when present
- section metadata when present

`len(citations) == len(selected_evidence)` is an invariant.

## 7. Bundle Contract

`RiskEvidenceBundle` must preserve:

- query and normalized query
- scope metadata
- retrieval diagnostics
- rerank provider/model
- `selected_evidence`
- `citations`
- `gate_decision`
- `should_answer`
- `refusal_reason`

It must not contain:

- answer text
- generated text
- chat message payloads

## 8. Acceptance Conditions

`M2D-11` is accepted only if:

- rerank requests use stable content-derived candidate ids
- provider results are validated before evidence shaping
- empty retrieval candidates bypass provider execution and return `no_candidates`
- evidence selection, evidence gate, and citation building remain deterministic
- citations are stable across rerank-rank changes
- real reranker smoke remains opt-in
- no `RiskKnowledgeService`, API runtime, NL Chat, or Profile Explanation integration starts in this phase
