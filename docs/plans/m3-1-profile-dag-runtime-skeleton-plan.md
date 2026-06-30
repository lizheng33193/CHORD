# M3-1 Profile DAG Runtime Skeleton Plan

## Status
- Updated: 2026-06-30
- Outcome: implemented

## Objective
- Replace mixed profile runtime views with one module-level DAG executor.
- Preserve public API shape and old progress contracts while introducing explicit node runtime contracts.

## Delivered

### New runtime package
- `app/services/profile_dag/contracts.py`
- `app/services/profile_dag/node_registry.py`
- `app/services/profile_dag/events.py`
- `app/services/profile_dag/adapters.py`
- `app/services/profile_dag/executor.py`

### Orchestrator integration
- `AnalysisOrchestrator.analyze()` now runs through `ProfileDagExecutor`.
- `AnalysisOrchestrator.analyze_module()` now runs through the same executor with a single requested module.
- `AnalysisOrchestrator.run_profile_request()` provides chat `run_profile` output assembly through the same executor.

### Compatibility bridges
- Raw node/run events are emitted from the executor.
- Analyze path keeps legacy `skill_started / skill_completed / skill_failed`.
- Chat `run_profile` keeps legacy `profile_module_started / profile_module_completed / profile_module_error`.
- Final results still map back to `UserAnalysisResult` and `RunProfileOutput`.

### State machine
- Added explicit node states:
  - `pending`
  - `running`
  - `completed`
  - `failed`
  - `skipped`
  - `degraded`
- Added explicit run states:
  - `pending`
  - `running`
  - `completed`
  - `completed_with_degradation`
  - `failed`
  - `cancelled`

### Failure semantics
- Non-requested nodes are marked `skipped`.
- Stage siblings remain independent.
- `comprehensive` is soft-required on `app/behavior/credit` in `M3-1`.
- `product/ops` are skipped when `comprehensive` fails.

## Tests Added / Updated
- `tests/test_profile_dag_runtime.py`
  - fixed graph contract
  - degraded comprehensive path
  - `comprehensive failed -> product/ops skipped`
  - event contract fields
  - `analyze()` legacy + new event bridge
  - `run_profile()` legacy + new event bridge
  - `analyze_module()` response compatibility

## Verification
- `pytest tests/test_profile_dag_runtime.py tests/test_orchestrator_progress.py tests/orchestrator_agent/test_profile_runner.py -q`
- `AUTH_ENABLED=0 pytest tests/test_analyze_stream_endpoint.py tests/test_analyze_module_endpoint.py -q`

## Risks Kept Deliberately Out
- no DB persistence
- no retry scheduler
- no resume/checkpoint
- no dynamic graph expansion
- no LangGraph migration
- no frontend DAG visualization rewrite

## Follow-up
- `M3-2`: frontend profile progress alignment on top of `profile_node_*`
- `M3-3`: persistence / audit / cache provenance hardening
- Re-evaluate LangGraph only after node truth, adapters, and audit semantics are stable
