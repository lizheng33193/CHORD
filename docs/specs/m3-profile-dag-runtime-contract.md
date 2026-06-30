# M3 Profile DAG Runtime Contract

## Status
- Updated: 2026-06-30
- Scope: `M3-1` runtime skeleton for module-level Profile DAG

## Goal
- Establish one runtime truth for profile execution.
- Keep public API shapes unchanged.
- Do not introduce LangGraph, DB persistence, retry, resume, or micro-node decomposition.

## In Scope
- Module-level nodes only:
  - `app`
  - `behavior`
  - `credit`
  - `comprehensive`
  - `product`
  - `ops`
- Runtime truth:
  - node spec
  - node state
  - node event
  - node result
  - compatibility adapters

## Source Of Truth
- `app/services/profile_dag/executor.py::ProfileDagExecutor` is the execution source of truth for profile runtime.
- The following paths must run through the same executor or its direct adapters:
  - `AnalysisOrchestrator.analyze()`
  - `AnalysisOrchestrator.analyze_module()`
  - chat `run_profile`
- `SkillRegistry` remains as skill registration / metadata / concrete skill-instance storage.
- `ExecutionTraceRecord` and frontend progress are consumers, not profile runtime truth.

## Fixed Node Registry

| node_key | module | skill_name | result_key | stage | depends_on |
| --- | --- | --- | --- | --- | --- |
| `app` | `app` | `app_profile` | `app_profile` | `0` | `[]` |
| `behavior` | `behavior` | `behavior_profile` | `behavior_profile` | `0` | `[]` |
| `credit` | `credit` | `credit_profile` | `credit_profile` | `0` | `[]` |
| `comprehensive` | `comprehensive` | `comprehensive_profile` | `comprehensive_profile` | `1` | `["app", "behavior", "credit"]` |
| `product` | `product` | `product_advice` | `product_advice` | `2` | `["comprehensive"]` |
| `ops` | `ops` | `ops_advice` | `ops_advice` | `2` | `["comprehensive"]` |

## Domain Contracts

### `ProfileRun`
- `run_id`
- `source`
- `uids`
- `requested_modules`
- `country_code`
- `application_time`
- `strict_data_mode`
- `status`
- `trace_id`
- `session_id`
- `turn_id`
- `request_id`
- `created_at`
- `started_at`
- `finished_at`
- `error`

### `ProfileNodeRun`
- `node_run_id`
- `profile_run_id`
- `uid`
- `node_key`
- `skill_name`
- `stage`
- `depends_on`
- `upstream_node_run_ids`
- `status`
- `attempt`
- `started_at`
- `finished_at`
- `duration_ms`
- `input_ref`
- `output_ref`
- `result_status`
- `error`
- `skip_reason`
- `cache_status`

### `ProfileRunResultSnapshot`
- `uid`
- `requested_modules`
- `module_outputs`
- `node_runs`
- `cache_hits`
- `cache_misses`

## Node Status
- `pending`
- `running`
- `completed`
- `failed`
- `skipped`
- `degraded`

## Run Status
- `pending`
- `running`
- `completed`
- `completed_with_degradation`
- `failed`
- `cancelled`

## Failure / Skip / Degrade Rules
- Same-stage siblings do not block each other.
- Nodes outside the requested dependency closure are `skipped` with `skip_reason=not_requested`.
- Downstream nodes can run when upstream nodes are `completed` or `degraded`.
- Downstream nodes are `skipped` when required upstream nodes are `failed`, except:
  - `comprehensive` treats `app/behavior/credit` as soft-required in `M3-1`.
  - `comprehensive` may still run with failed upstream inputs and must become `degraded` if any upstream is failed, skipped, or degraded.
- `product` and `ops` require `comprehensive`.
  - `comprehensive failed` -> `product/ops skipped`
- `ProfileRun.status` resolution:
  - all requested nodes `completed` -> `completed`
  - any requested node `degraded` / `skipped` / `failed`, but some result remains displayable -> `completed_with_degradation`
  - all requested nodes `failed` -> `failed`

## Event Contract
- `profile_run_started`
- `profile_node_started`
- `profile_node_completed`
- `profile_node_failed`
- `profile_node_skipped`
- `profile_run_completed`
- `profile_run_failed`

Each node event must carry:
- `profile_run_id`
- `node_run_id`
- `uid`
- `node_key`
- `skill_name`
- `stage`
- `status`
- `duration_ms`
- `cache_status`
- `upstream_node_run_ids`
- `error`

## Compatibility Contract
- Public response shapes remain unchanged:
  - `/api/analyze`
  - `/api/analyze-stream`
  - `/api/analyze-module`
  - `RunProfileOutput.results`
  - `AnalyzeResponse`
  - `UserAnalysisResult`
- `M3-1` adapters preserve legacy progress semantics:
  - `profile_node_started -> skill_started`
  - `profile_node_completed -> skill_completed`
  - `profile_node_failed -> skill_failed`
  - requested-module node events -> `profile_module_started/completed/error`
- New `profile_node_*` events are the future UI truth source.

## Out Of Scope
- LangGraph
- DB persistence
- artifact store
- cross-run cache provenance
- selective retry
- checkpoint / resume
- arbitrary DAG UI
- skill-internal six-step graphization
- `TraceAnalyzer`
- `query_data / repair / data_agent`
