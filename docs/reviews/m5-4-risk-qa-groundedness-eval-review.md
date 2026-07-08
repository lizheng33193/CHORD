# M5-4 Risk QA Groundedness Eval Review

## Outcome
- `risk_qa_groundedness` is runnable from `python -m app.eval.runner --suite risk_qa_groundedness`.
- `pr_acceptance` now executes five suites in order:
  - `release_gate_smoke`
  - `memory_governance`
  - `data_agent_sql_safety`
  - `data_agent_sql_grounding`
  - `risk_qa_groundedness`
- `production_release` remains smoke-only.

## Runtime Seams Exercised
- `RiskQaContextBuilder`
- `CitationValidator`
- `EvidenceSufficiencyChecker`
- Risk evidence / citation / answer-facing schemas
- thin deterministic adapters over in-memory records, evidence traces, and rendered citations

## Shared Eval Integration
- Added a single `RiskQAEvaluator` with `check_kind` routing.
- Registered one new Risk QA suite on the shared platform.
- Expanded `pr_acceptance` only; `production_release` was left unchanged.

## Raw vs Normalized Codes
- Eval reports preserve raw runtime warning / failure codes in artifacts.
- Source-boundary cases preserve raw source labels plus mapped runtime source types.
- Normalized report codes remain stable for suite metrics and regression reporting.

## Eval-Only Fallback Audit
- `eval_only` fallback cases used: `0`
- `policy_source` values in this phase are limited to `runtime` and `adapter`.

## Deferred Work
- Risk QA integration into `production_release` remains deferred to `M5-6`.
- Full retrieval-quality benchmarking and Profile DAG shared eval remain out of scope for `M5-4`.
