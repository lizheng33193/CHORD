# M2D-13 Golden Set Evaluation Review

## Summary

`M2D-13` landed a CHORD-owned golden-set evaluation framework for the current M2D runtime chain, including offline-safe fixture evaluation, advisory regression decisions, JSON / Markdown reporting, and read-only trace seams over retrieval, rerank, evidence, citation, and answer outputs.

## Scope

This phase adds:

- `app/risk_knowledge/evaluation`
- canonical sample golden-set fixture
- read-only trace seams for bundle / pipeline / service
- advisory regression decision logic
- fixture CLI and runtime opt-in CLI

It does not add:

- admin API/UI
- document upload / reindex / status runtime
- frontend work
- Data Agent RAG mixing
- ES / SWXY runtime coupling
- production hardening

## Validation

Validated with:

- `pytest -q tests/risk_knowledge/evaluation tests/risk_knowledge/service tests/risk_knowledge/reranking tests/risk_knowledge/evidence tests/risk_knowledge/retrieval tests/risk_knowledge/embedding tests/knowledge_base`
- `python -m app.risk_knowledge.evaluation.cli --golden-set tests/fixtures/golden/risk_knowledge/eval_set.sample.jsonl --output-dir /tmp/m2d_eval_report --mode fixture`

Fixture validation remained offline-safe and did not access MySQL, Redis, DashScope, or real LLM providers.

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-13 golden-set evaluation landed; no admin API/UI/production-hardening runtime started`

Acceptance posture:

> `M2D-13 accepted at stage level after targeted golden-set evaluation and regression validation; runtime evaluation, full repository regression, and runtime baseline remain optional/pending validation items.`

Additional posture:

- v1 regression remains report-only / advisory
- runtime evaluation remains opt-in / pending
- full repository regression remains pending / optional
- runtime baseline remains intentionally uncommitted in v1

Explicitly not started:

- no admin API/UI
- no document upload / reindex / status API
- no frontend
- no Data Agent RAG mixing
- no ES / SWXY coupling
- no production hardening

## Next Step

`M2D-14A` remains:

- Knowledge Base Admin API
- upload / reindex / status runtime surfaces
