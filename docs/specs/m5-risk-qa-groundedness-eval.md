# M5 Risk QA Groundedness Eval

## Summary
- `M5-4` adds deterministic Risk QA groundedness regression coverage on top of `app/eval/`.
- It introduces one runnable suite:
  - `risk_qa_groundedness`
- `pr_acceptance` now runs `release_gate_smoke`, `memory_governance`, `data_agent_sql_safety`, `data_agent_sql_grounding`, and `risk_qa_groundedness`.
- `production_release` remains smoke-only until `M5-6`.

## Boundary
- Reuse existing deterministic Risk QA seams as the source of truth:
  - context isolation
  - citation validation
  - evidence sufficiency
  - risk evidence / citation / answer-facing schemas
  - deterministic evaluation matcher helpers where useful
- Do not mutate Risk Knowledge runtime behavior.
- Do not call real LLMs, embedding providers, FAISS, Redis workers, indexing, rebuild, activate, or rollback flows in M5-4 eval.

## Suite Shape
- `risk_qa_groundedness`
  - deterministic retrieval/evidence grounding validation
  - evidence sufficiency and refusal checks
  - citation presence / validity / metadata checks
  - grounded answer token coverage
  - unsupported-claim blocking
  - source-boundary isolation

## Evaluator Contract
- `RiskQAEvaluator` routes by `input.check_kind`.
- It uses deterministic record adapters instead of real retrieval/runtime infrastructure.
- It preserves raw runtime warning / failure codes and mapped source labels in `EvalResult.artifacts`.
- It emits stable normalized eval codes for reports and suite metrics.

## Non-Goals
- No Risk Knowledge runtime rewrite.
- No vector retrieval quality benchmark, no LLM-as-judge, and no release-gate expansion beyond `pr_acceptance`.
- No Profile DAG shared suite in this phase.
