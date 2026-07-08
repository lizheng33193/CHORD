# M5-5 Profile DAG Regression Suite Plan

## Goal
- Land deterministic Profile DAG contract and snapshot regression suites on the shared eval platform.

## Deliverables
- `app/eval/evaluators/profile.py`
- `profile_dag_contract` suite registration
- `profile_memory_snapshot` suite registration
- deterministic `tests/eval_cases/profile_dag_contract.yaml`
- deterministic `tests/eval_cases/profile_memory_snapshot.yaml`
- `pr_acceptance` profile expansion only
- targeted `tests/eval/` coverage plus Profile DAG and memory-boundary non-regression verification

## Explicit Constraints
- Reuse deterministic Profile DAG runtime seams first, thin adapters second, eval-only last resort.
- Use fake skills only to feed deterministic payloads into the real executor path.
- Use `build_profile_memory_snapshot(...)` as snapshot source of truth.
- Reuse `profile_snapshot_to_memory_candidate(...) + validate_memory_use(...)` for boundary checks.
- Keep `production_release` smoke-only in `M5-5`.
