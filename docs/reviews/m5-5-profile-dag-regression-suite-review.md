# M5-5 Profile DAG Regression Suite Review

## Outcome
- `profile_dag_contract` is runnable from `python -m app.eval.runner --suite profile_dag_contract`.
- `profile_memory_snapshot` is runnable from `python -m app.eval.runner --suite profile_memory_snapshot`.
- `pr_acceptance` now executes seven suites in order:
  - `release_gate_smoke`
  - `memory_governance`
  - `data_agent_sql_safety`
  - `data_agent_sql_grounding`
  - `risk_qa_groundedness`
  - `profile_dag_contract`
  - `profile_memory_snapshot`
- `production_release` remains smoke-only.

## Runtime Seams Exercised
- `PROFILE_NODE_SPECS`, `NODE_KEY_TO_SPEC`, and `resolve_execution_closure`
- `ProfileDagExecutor`
- profile event builders and legacy adapters
- `build_profile_memory_snapshot(...)`
- `profile_snapshot_to_memory_candidate(...)`
- `validate_memory_use(...)`

## Shared Eval Integration
- Added a single `ProfileEvaluator` with `check_kind` routing.
- Registered two new Profile DAG suites on the shared platform.
- Expanded `pr_acceptance` only; `production_release` was left unchanged.

## Raw vs Normalized Evidence
- Eval reports preserve raw runtime node statuses and raw memory-policy block codes in artifacts.
- Boundary cases preserve raw `validate_memory_use(...)` outcomes alongside normalized profile-level report codes.
- Normalized report codes remain stable for suite metrics and regression reporting.

## Eval-Only Fallback Audit
- `eval_only` fallback cases used: `0`
- `policy_source` values in this phase are limited to `runtime` and `adapter`.

## Deferred Work
- Profile suites do not join `production_release` until `M5-6`.
- Full release-gate closure remains the next milestone.
