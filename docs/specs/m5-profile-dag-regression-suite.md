# M5 Profile DAG Regression Suite

## Summary
- `M5-5` adds deterministic Profile DAG regression coverage on top of `app/eval/`.
- It introduces two runnable suites:
  - `profile_dag_contract`
  - `profile_memory_snapshot`
- `pr_acceptance` now runs `release_gate_smoke`, `memory_governance`, `data_agent_sql_safety`, `data_agent_sql_grounding`, `risk_qa_groundedness`, `profile_dag_contract`, and `profile_memory_snapshot`.
- `production_release` remains smoke-only until `M5-6`.

## Boundary
- Reuse existing deterministic Profile DAG seams as the source of truth:
  - fixed node registry and dependency closure
  - `ProfileDagExecutor`
  - profile event builders and legacy adapters
  - `build_profile_memory_snapshot(...)`
  - M4 memory candidate and isolation policy seams
- Do not mutate `ProfileDagExecutor`, node registry behavior, or real runtime skill behavior.
- Do not call real LLMs, real databases, or full production profile flows in `M5-5` eval.

## Suite Shape
- `profile_dag_contract`
  - node registry contract
  - dependency closure
  - deterministic fake DAG execution
  - skip / degraded semantics
  - event contract
  - structured output contract
- `profile_memory_snapshot`
  - snapshot module-output contract
  - legacy adapter compatibility
  - profile-result memory/source boundary validation
  - degraded snapshot evidence-status coverage

## Evaluator Contract
- `ProfileEvaluator` routes by `input.check_kind`.
- It uses deterministic fake skills for DAG execution while still exercising real runtime executor / adapter seams.
- It preserves raw runtime statuses and raw memory policy reason codes in `EvalResult.artifacts`.
- It emits stable normalized eval codes for suite metrics and regression reports.

## Non-Goals
- No Profile DAG runtime rewrite.
- No business-correctness re-evaluation of real `app/behavior/credit` skill internals.
- No `production_release` expansion before `M5-6`.
