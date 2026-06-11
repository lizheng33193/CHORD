# Data Agent Empty / Too-Large Cohort UX Audit

## Scope

This review documents the current `empty cohort` and `too-large cohort` user experience for D1.3. It is a UX-focused audit and records the contract boundaries that must remain unchanged.

Reviewed surfaces:

- `app/services/orchestrator_agent/flows/query_data_then_profile.py`
- `app/services/orchestrator_agent/flows/general_chat.py`
- `app/services/orchestrator_agent/finalization/final_answer_builder.py`
- `app/services/orchestrator_agent/finalization/query_data_messages.py`
- `tests/orchestrator_agent/test_refactor_baseline.py`
- `tests/test_orchestrator_visible_execution.py`

## Current Semantic Boundaries

The following semantics are intentionally preserved:

- `QueryDataThenProfileFlow` still owns the query-profile and clarification query-only terminal branches.
- `GeneralChatFlow -> query_data` still remains a query-only single-tool path.
- `GeneralChatFlow` still uses:
  - `tool_completed(query_data)`
  - tool observation
  - one LLM continuation final
- no new SSE event types were introduced
- no `awaiting_user_ack` payload keys changed
- no `execution_plan`, `plan_step_status`, `review_result`, or `tool_completed` public shapes changed
- the too-large threshold remains `200`

## QueryDataThenProfileFlow Current Behavior

### Query-only empty cohort

Path:

- clarification resume
- `query_data` completes successfully
- no `run_profile`
- no `repair_profile_data`
- `review_result.status == "pass"`
- terminal `final_status == "completed"`

D1.3 change:

- final guidance is now clearer about:
  - query success
  - zero matched users
  - `UID 数量：0`
  - relaxing the filter conditions

### Query-only too-large cohort

Path:

- clarification resume
- `query_data` completes successfully
- no `run_profile`
- no `repair_profile_data`
- `review_result.status == "fail"`
- issues keep `cohort_too_large`
- terminal `final_status == "blocked"`

D1.3 change:

- final guidance now clearly says:
  - the cohort exceeds the current safe limit
  - processing stopped safely
  - the user should narrow the query scope

### Query-profile empty cohort

Path:

- first-turn or clarification auto-profile path
- `query_data` completes successfully
- no `check_data`
- no `run_profile`
- no `repair_profile_data`
- `review_result.status == "fail"`
- issues keep `empty_cohort`
- terminal `final_status == "blocked"`

D1.3 change:

- final guidance now clearly says:
  - the query succeeded
  - no UID matched
  - profiling will not start
  - the user should relax the filters

### Query-profile too-large cohort

Path:

- first-turn or clarification auto-profile path
- `query_data` completes successfully
- no `check_data`
- no `run_profile`
- no `repair_profile_data`
- `review_result.status == "fail"`
- issues keep `cohort_too_large`
- terminal `final_status == "blocked"`

D1.3 change:

- final guidance now clearly says:
  - the cohort is too large for safe handling
  - profiling will not continue
  - the user should narrow the scope

## GeneralChatFlow Current Behavior

`GeneralChatFlow` still does **not** get a dedicated empty / too-large terminal branch.

The path remains:

- `tool_started(query_data)`
- `tool_completed(query_data)`
- append tool observation to `session.messages`
- one continuation LLM pass
- one final assistant message

D1.3 change:

- for empty results, the tool observation is now prose guidance instead of raw JSON
- for too-large results, the tool observation is now prose guidance instead of raw JSON
- all other query-data outputs still use the existing JSON observation path

This keeps `GeneralChatFlow` in the existing observation-only architecture and avoids introducing new blocked/fail flow semantics.

## Threshold

The current too-large threshold is still `200`.

D1.3 does not:

- change the threshold
- make it configurable
- move it into the Data Agent executor

## Visible Execution Order

Current visible execution order remains unchanged:

- `query_data` completion still happens before `review_result` / `final`
- `run_profile` does not start for empty / too-large outcomes
- `repair_profile_data` does not start for empty / too-large outcomes
- `final` still appears exactly once

## Contract Boundaries Preserved

D1.3 does not change:

- `QueryDataInput`
- `NormalizedRequest`
- `awaiting_user_ack`
- `tool_started.input`
- `tool_completed` public payload
- `review_result` schema
- frontend reducer input shape
- `DataQueryRunner` execution lifecycle
- `data_acquisition_agent/` runtime behavior

## Tests Added or Updated

D1.3 coverage now includes:

- helper-level message tests in `tests/orchestrator_agent/test_query_data_messages.py`
- baseline tests for:
  - query-profile empty
  - query-profile too-large
  - query-only empty
  - query-only too-large
  - general-chat empty observation
  - general-chat too-large observation
- visible execution assertions that final messages are clearer while public event shapes remain unchanged

## Follow-up Work Not Included

D1.3 intentionally does not include:

- SQL preview explainability
- SQL safety hardening
- threshold changes
- Data Agent executor changes
- Vanna integration
- LangGraph work
