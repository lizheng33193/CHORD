# Data Agent / Text-to-SQL Current State Audit

## Scope

This audit documents the current `query_data` lifecycle and ownership after orchestrator decomposition. It is a D1-0 review artifact, not a runtime behavior change.

Reviewed surfaces:

- `app/services/orchestrator_agent/execution/data_query_runner.py`
- `app/services/orchestrator_agent/flows/query_data_then_profile.py`
- `app/services/orchestrator_agent/flows/general_chat.py`
- `app/services/orchestrator_agent/tools/query_data.py`
- `app/services/orchestrator_agent/agent_loop.py`
- `data_acquisition_agent/executor.py`
- `data_acquisition_agent/output_scanner.py`
- `tests/orchestrator_agent/test_data_query_runner.py`
- `tests/orchestrator_agent/test_refactor_baseline.py`
- `tests/test_orchestrator_visible_execution.py`
- `tests/frontend/test_chat_reducer.py`

## Current QueryDataInput Contract

`QueryDataInput` in `app/services/orchestrator_agent/schemas.py` currently has exactly two public fields:

- `request: str`
- `country: CountryCode`

This is still the public tool-input contract used by `GeneralChatFlow` and test fixtures. No structured `time_window`, `auto_profile`, `query_mode`, or filter fields exist on the public schema.

Related public request facts:

- `NormalizedRequest.query_request` is currently free text.
- `NormalizedRequest` does not expose a structured query-specific sub-schema.
- `request_router.normalize_request()` already performs the first deterministic routing layer and may set:
  - `intent="query_data_then_profile"`
  - `query_request=<free-text cohort request>`
  - `request_understanding` for clarification-ready cases

## Current query_data Lifecycle

The current `query_data` runtime lifecycle is implemented by `DataQueryRunner` in `app/services/orchestrator_agent/execution/data_query_runner.py`.

Observed lifecycle:

1. `tool_started(query_data)`
2. preview phase
3. one of:
   - preview returns immediate completed output
   - preview returns `awaiting_user_ack`
4. if ACK is approved, complete phase runs
5. `tool_completed(query_data)` on completed paths

Current ACK payload shape emitted by `awaiting_user_ack`:

- `ack_id`
- `tool_call_id`
- `sql_text`
- `rows_estimated`

This shape is frontend-visible and already consumed by reducer tests in `tests/frontend/test_chat_reducer.py`.

Current non-approved outcomes:

- `rejected`
- `expired`
- `cancelled`

Current failure surfaces:

- preview exception
- complete exception
- runner result missing
- cancellation before or after ACK

## QueryDataThenProfileFlow Ownership

`QueryDataThenProfileFlow` currently owns the main cohort orchestration path:

- unsupported-country guard
- capability-disabled / unavailable guard
- clarification resume with `auto_profile=false`
- clarification resume with `auto_profile=true`
- first-turn full `query_data_then_profile`
- query-only terminal final
- query -> profile success / partial / blocked
- single-bucket repair bridge

Key ownership facts:

- query execution goes through `_run_query_data_phase(...)`
- post-query continuation stays inside the flow
- first-turn full query no longer falls back to `_run_known_request()`
- multi-bucket repair remains conservative / blocked rather than expanded into a broader live repair matrix

## GeneralChatFlow query_data Ownership

`GeneralChatFlow` owns the query-like single-tool path in `_run_query_data_tool_loop(...)`.

Current guarantees:

- validates `QueryDataInput(**arguments)`
- uses `DataQueryRunner`
- does not call `get_tool_registry()`
- remains query-only single-tool
- does not auto-enter profile
- does not auto-enter repair
- allows only one continuation final after the observation

This means D1 normalization must not upgrade the general-chat `query_data` path into query->profile orchestration.

## ACK Semantics

ACK semantics are currently stable at the runner layer:

- preview opens ACK
- `awaiting_user_ack` is emitted before wait
- approved continues to completion
- rejected / expired / cancelled terminate without a normal final answer on cancellation paths

The D1 first slice must preserve:

- ACK event type
- ACK payload keys
- event order
- tool lifecycle order

## Empty / Too-Large Semantics

Current semantics observed from `QueryDataThenProfileFlow` and its tests:

- query-only empty cohort is treated as a success-like final response
- query-profile empty cohort is blocked before profile execution
- too-large cohort is blocked/fail rather than silently downgraded
- the current threshold is still `200` UIDs in `_run_query_data_phase(...)`

This threshold is runtime behavior today, but D1 first slice does not change it.

## Fake vs Real Data Agent Behavior

Current real path:

- `agent_loop.execute_query_data_cohort(...)` creates `tools.query_data._ChildAgent`
- `_ChildAgent.run_query(...)` generates SQL text
- `DataQueryRunner` emits `awaiting_user_ack`
- `agent_loop._complete_query_data_cohort(...)` calls `_ChildAgent.execute(...)`
- `_ChildAgent.execute(...)` enforces gates, prechecks row count, executes SQL, validates a UID-like column, and returns UID list + row counts

Current fake/test path:

- many tests monkeypatch `execute_query_data_cohort(...)` and `_complete_query_data_cohort(...)` directly
- tests simulate:
  - no-ACK completed preview
  - ACK-required preview
  - empty cohort
  - too-large cohort
  - preview failure
  - execute failure

Important parity note:

- the no-ACK completed preview path exists in `DataQueryRunner` but is mostly exercised through tests and mocks
- the real orchestrator facade normally returns `child + sql_text + rows_estimated`, so production behavior is usually ACK-based

## Current SQL Safety Guard Locations

Authoritative guard path:

- `data_acquisition_agent/executor.py::enforce_pre_execution_gates(...)`
- `data_acquisition_agent/output_scanner.py::check_sql_policy(...)`
- `data_acquisition_agent/output_scanner.py::scan_credentials(...)`
- `data_acquisition_agent/output_scanner.py::scan_python_dangerous(...)`

Shallow orchestrator-side guard:

- `app/services/orchestrator_agent/tools/query_data.py::_PROHIBITED_SQL`

The shallow regex guard is not the authoritative boundary. Real enforcement happens in the executor/scanner layer.

## Test Coverage Map

Current useful coverage surfaces:

- `tests/orchestrator_agent/test_data_query_runner.py`
  - ACK ordering
  - completed/no-ACK path
  - rejected / expired / cancelled
  - complete failure handling
- `tests/orchestrator_agent/test_refactor_baseline.py`
  - first-turn query->profile
  - clarification query-only
  - general-chat query_data
  - empty / too-large / failure / repair outcomes
- `tests/test_orchestrator_visible_execution.py`
  - public event order
  - visible `awaiting_user_ack`
  - execution-plan and final behavior
- `tests/frontend/test_chat_reducer.py`
  - frontend contract for `awaiting_user_ack` and `execution_plan`

New D1 first-slice coverage added:

- `tests/orchestrator_agent/test_query_request_normalizer.py`
  - internal country/time/query-mode/auto-profile normalization
  - hint-block idempotency
  - public schema non-regression

## Known Risks

- `effective_request_text` now affects the real Data Agent input, so it must remain additive and conservative.
- `tool_started` emits the public `input` payload, so normalized hint text must not leak into `DataQueryRunSpec.input_payload`.
- unsupported-country guard must not be bypassed by query-text parsing alone.
- general-chat query-like prompts must not silently become query->profile orchestration.

## D1.1 Implementation Targets

The first normalization slice should remain narrow:

- normalize `country`
- normalize common `time_window` phrases
- stabilize `query_mode`
- honor explicit `auto_profile`
- keep original query text intact
- append only a fixed internal canonical hints block to the execution-time request text

## D1.4 Audit Findings

Summary findings for the safety audit crossover:

- authoritative enforcement already exists in executor/scanner
- multi-statement rejection already exists
- result-too-large precheck already exists
- UID-column validation currently lives in `tools/query_data._ChildAgent.execute(...)`
- explicit table allowlist / denylist is not currently present in the query-only path
- explicit approved-SQL structured audit trace for query-only execution is still limited and should be treated as a follow-up gap
