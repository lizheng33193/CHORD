# M5 Data Agent Regression Suite

## Summary
- `M5-3` adds deterministic Data Agent regression coverage on top of `app/eval/`.
- It introduces two runnable suites:
  - `data_agent_sql_safety`
  - `data_agent_sql_grounding`
- `pr_acceptance` now runs `release_gate_smoke`, `memory_governance`, `data_agent_sql_safety`, and `data_agent_sql_grounding`.
- `production_release` remains smoke-only until `M5-6`.

## Boundary
- Reuse existing deterministic Data Agent seams as the source of truth:
  - SQL safety gate
  - structured plan validation
  - SQL-vs-plan review
  - semantic validation
  - repairable warning selection
  - approval / execute eligibility semantics
  - approved-example vs error-case classification semantics
- Do not mutate Data Agent runtime behavior.
- Do not call LLMs, connect to real DBs, or execute SQL in M5-3 eval.

## Suite Shape
- `data_agent_sql_safety`
  - dangerous SQL blocking
  - writeback boundary blocking
  - semantic uid-boundary blocking
  - review-only SQL handling
  - HITL / execute ineligibility
- `data_agent_sql_grounding`
  - plan contract validation
  - plan validation
  - unsupported-field and non-canonical-field warnings
  - date/source/required-field/broad-scan drift warnings
  - approved-example vs failed-error-case classification

## Evaluator Contract
- `DataAgentEvaluator` routes by `input.check_kind`.
- It emits stable normalized warning / failure codes for reports.
- It preserves raw runtime codes and seam-specific evidence in `EvalResult.artifacts`.
- `eval_only` fallback is exceptional and must be documented if used.

## Non-Goals
- No Data Agent runtime rewrite.
- No SQL execution, no DB persistence, and no release-gate expansion beyond `pr_acceptance`.
- No Risk QA or Profile DAG shared suites in this phase.
