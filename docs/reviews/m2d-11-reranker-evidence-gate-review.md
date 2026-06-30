# M2D-11 Reranker + Evidence Gate Review

## Summary

`M2D-11` landed CHORD-owned reranking, deterministic evidence shaping, deterministic refusal gating, and stable citation bundling on top of `M2D-10` retrieval candidates.

## Scope

This phase adds:

- `app/risk_knowledge/reranking`
- `app/risk_knowledge/evidence`
- DashScope HTTP reranker provider
- deterministic reranker provider
- stable candidate-id generation
- stable citation ids
- `RiskEvidenceBundle`

It does not add `RiskKnowledgeService`, NL Chat integration, Profile Explanation integration, answer generation, API routes, frontend work, Elasticsearch, or SWXY runtime imports.

## Reranking Boundary

The reranking layer now owns:

- content-derived `candidate_id`
- request/result contracts
- provider factory
- provider result normalization
- duplicate / unknown candidate rejection
- rerank rank rebuilding

Provider-specific HTTP transport stays isolated inside `dashscope_provider.py`.

## Evidence Boundary

The evidence layer now owns:

- deterministic evidence selection
- deterministic refusal checks
- stable citation building
- `RiskEvidenceBundle` assembly

Empty retrieval candidates are treated as a normal refusal path and do not trigger provider calls.

## Validation

Validated with:

- reranker contract tests
- rerank service normalization and mismatch tests
- DashScope provider offline tests
- evidence selector tests
- citation stability tests
- bundle builder tests
- coupling guard for `app/risk_knowledge/evidence`
- regression run across reranking, evidence, retrieval, embedding, and knowledge-base suites
- opt-in real reranker smoke gate

Default tests remain offline. Real reranker smoke still requires local opt-in configuration.

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-11 reranker and evidence gate landed; no RiskKnowledgeService/API/NL Chat/Profile Explanation runtime started`

Acceptance posture:

> `M2D-11 accepted at stage level after targeted reranker/evidence gate validation;`
> `real reranker smoke remains opt-in and full repository regression remains optional/pending.`

Explicitly not started:

- no `RiskKnowledgeService`
- no API runtime
- no NL Chat / Profile Explanation integration
- no answer generation
- no ES / SWXY coupling

## Next Step

`M2D-12` remains:

- consumer-facing `RiskKnowledgeService`
- NL Chat / Profile Explanation integration
- grounded answer assembly over `RiskEvidenceBundle`
