# Pre-M3 Risk QA Production Gate Plan

## Goal

Upgrade the existing `risk_knowledge_answer` path from retrieval-oriented answer shaping into a production-gated Risk QA flow with context isolation, evidence sufficiency, citation validation, and additive artifact metadata.

## Public Compatibility

- keep intent: `risk_knowledge_answer`
- keep facade: `RiskKnowledgeService.answer()`
- keep orchestrator flow: `RiskKnowledgeAnswerFlow`
- keep additive-only external schema evolution

## Internal Structure

Implement the new logic behind the public facade using:

- `app/risk_knowledge/qa/`
- `app/risk_knowledge/context/`
- `app/risk_knowledge/evidence/manager.py`

The facade translates legacy input and maps the internal pipeline result back to the extended public answer contract.

## Runtime Gates

The runtime sequence is:

`context isolation -> retrieval normalization -> evidence selection -> sufficiency -> answer generation -> citation validation -> artifact shaping`

Mandatory production rules:

- insufficient evidence is a pre-generation hard stop
- citation validation is a public-answer gate
- grounded answers may cite only selected `risk_domain_knowledge` evidence
- Risk QA must not create DataAgentRun or touch SQL HITL
- Data routes must not use Risk Domain Knowledge as field grounding

## Documentation And Status Sync

This phase requires:

- `docs/specs/risk-qa-production-gate-contract.md`
- this plan document
- `docs/reviews/pre-m3-risk-qa-production-gate-acceptance-review.md`
- `PLANNING.md` update
- `TASK.md` update

## Verification

Required verification includes:

- routing tests
- context isolation tests
- evidence and sufficiency tests
- citation validation tests
- facade compatibility tests
- orchestrator E2E tests
- relevant Data Agent non-regression tests
