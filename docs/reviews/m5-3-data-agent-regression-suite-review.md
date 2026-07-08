# M5-3 Data Agent Regression Suite Review

## Outcome
- `data_agent_sql_safety` is runnable from `python -m app.eval.runner --suite data_agent_sql_safety`.
- `data_agent_sql_grounding` is runnable from `python -m app.eval.runner --suite data_agent_sql_grounding`.
- `pr_acceptance` now executes four suites in order:
  - `release_gate_smoke`
  - `memory_governance`
  - `data_agent_sql_safety`
  - `data_agent_sql_grounding`
- `production_release` remains smoke-only.

## Runtime Seams Exercised
- `run_sql_safety_gate(...)`
- `validate_structured_sql_plan(...)`
- `review_sql_against_intent_plan(...)`
- `validate_sql_semantics(...)`
- `select_repairable_plan_warnings(...)`
- thin adapters over approval / execute eligibility and SQL example / error-case classification semantics

## Shared Eval Integration
- Added a single `DataAgentEvaluator` with `check_kind` routing.
- Registered two new suites on the shared platform.
- Expanded `pr_acceptance` only; `production_release` was left unchanged.

## Raw vs Normalized Codes
- Eval reports preserve raw runtime warning / failure codes in artifacts.
- Normalized report codes remain stable for suite metrics and regression reporting.

## Eval-Only Fallback Audit
- `eval_only` fallback cases used: `0`
- `policy_source` values in this phase are limited to `runtime` and `adapter`.

## Deferred Work
- Data Agent integration into `production_release` remains deferred to `M5-6`.
- Full Risk QA and Profile DAG shared eval suites remain out of scope for `M5-3`.
