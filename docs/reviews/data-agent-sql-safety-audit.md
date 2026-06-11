# Data Agent SQL Safety Audit

## Scope

This document records the current SQL safety guard locations, coverage, minimal hardening results, and follow-up gaps for D1.4. It is an audit artifact, not a schema or runtime contract change.

Reviewed files:

- `app/services/orchestrator_agent/tools/query_data.py`
- `data_acquisition_agent/output_scanner.py`
- `data_acquisition_agent/executor.py`
- `data_acquisition_agent/tests/test_output_scanner.py`
- `data_acquisition_agent/tests/test_executor.py`

## Guard Boundary Summary

Current guard layers:

1. orchestrator-side shallow guard
   - `app/services/orchestrator_agent/tools/query_data.py::_PROHIBITED_SQL`
2. authoritative SQL / artifact scanner
   - `data_acquisition_agent/output_scanner.py`
3. authoritative execution gate
   - `data_acquisition_agent/executor.py::enforce_pre_execution_gates(...)`

Assessment:

- `_PROHIBITED_SQL` is only an early, shallow rejection layer.
- the authoritative guard boundary belongs to the executor/scanner layer
- D1 safety hardening should prefer executor/scanner changes over flow-layer logic

## Current Guard Coverage

### Read-only / DDL-DML rejection

Current state:

- `output_scanner.check_sql_policy(..., "query_only", ...)` now treats `query_only` as a narrow `SELECT / WITH ... SELECT` lane
- query-only rejects:
  - `CREATE`
  - `DROP`
  - `ALTER`
  - `TRUNCATE`
  - `INSERT`
  - `UPDATE`
  - `DELETE`
  - `CALL`
  - `EXEC`
  - `LOAD DATA`
  - `SELECT ... INTO OUTFILE`
- `executor.enforce_pre_execution_gates(...)` wraps policy failures into `ExecutorError(ErrorType.DDL_POLICY_VIOLATION, "artifact failed SQL policy", ...)`
- `tools/query_data.py::_PROHIBITED_SQL` was kept as a shallow guard and aligned with newly covered dangerous classes

Coverage:

- `data_acquisition_agent/tests/test_output_scanner.py::test_query_only_rejects_ddl`
- `test_query_only_rejects_non_select_statement_classes`
- `test_query_only_allows_safe_select_and_cte_shapes`
- `data_acquisition_agent/tests/test_executor.py::test_gate_rejects_ddl_dml_in_query_only`
- `test_gate_allows_safe_cte_and_string_literals_with_keywords`

Notes:

- string literals are now masked before keyword scanning, so safe queries such as `WHERE note = 'drop candidate'` no longer false-reject
- this slice does not introduce broader table policy; it only narrows the allowed statement class

### Multi-statement rejection

Current state:

- `executor.enforce_pre_execution_gates(...)` strips comments, splits on `;` outside string literals, and rejects more than one statement

Coverage:

- `data_acquisition_agent/tests/test_executor.py::test_gate_rejects_multi_statement`
- `test_gate_rejects_multi_statement_with_comment_and_newline_evasion`
- comments are explicitly stripped before split in `test_gate_strips_comments_before_split`
- semicolons inside string literals are explicitly allowed in `test_gate_does_not_treat_semicolon_in_string_literal_as_multi_statement`

### Credential leak scan

Current state:

- `output_scanner.scan_credentials(...)` detects host / port / user / password / database / token / api_key / access_token / secret / bearer patterns
- `executor.enforce_pre_execution_gates(...)` rejects if any credential pattern is found

Coverage:

- `data_acquisition_agent/tests/test_output_scanner.py::test_scan_finds_ip_and_password`
- `test_scan_finds_token_and_bearer`
- `data_acquisition_agent/tests/test_executor.py::test_gate_rejects_credential_leak`

### Dangerous code scan

Current state:

- `output_scanner.scan_python_dangerous(...)` rejects patterns such as:
  - `os.system(...)`
  - `subprocess(..., shell=True)`
  - `eval(...)`
  - `exec(...)`
  - destructive filesystem calls
- `executor.enforce_pre_execution_gates(...)` blocks these in approved artifacts

Coverage:

- `data_acquisition_agent/tests/test_output_scanner.py::test_blacklist_hits`
- `test_clean_python`
- `data_acquisition_agent/tests/test_executor.py::test_gate_rejects_dangerous_python`

### Row-count precheck / result-too-large

Current state:

- `executor.precheck_row_count(...)` wraps the approved SQL in a `SELECT COUNT(*) FROM (...)`
- if row count exceeds `settings.da_max_result_rows`, executor raises `RESULT_TOO_LARGE`
- this is the current hard gate; there is no SQL rewrite to inject `LIMIT`

Coverage:

- `data_acquisition_agent/tests/test_executor.py::test_precheck_returns_count`
- `test_precheck_raises_when_over_limit`
- `test_precheck_wraps_sql_in_count`

### Query failure and fixed error messages

Current state:

- DB execution failures are translated to fixed `query execution failed`
- empty results are translated to `result validation failed`
- executor does not echo raw DB errors back into the public message field

Coverage:

- `data_acquisition_agent/tests/test_executor.py::test_precheck_db_failure_to_query_failed`
- `test_execute_empty_result_raises_validation`
- `test_execute_db_failure_to_query_failed`

### UID column validation

Current state:

- query-only UID-column validation is currently not in executor/scanner
- it lives in `app/services/orchestrator_agent/tools/query_data.py::_ChildAgent.execute(...)`
- accepted normalized candidates are:
  - `uid`
  - `userid`
  - `useruuid`
  - `customerid`
- blank strings are filtered
- `None` values are now filtered before string normalization
- numeric UID values are normalized to strings
- missing UID columns raise `ValueError("query_data result missing uid column")`

Coverage:

- direct cohort-output behavior is now covered by:
  - `tests/test_orchestrator_visible_execution.py::test_query_data_execute_accepts_user_uuid_alias`
  - `test_query_data_execute_accepts_customer_id_alias_and_normalizes_numeric_uids`
  - `test_query_data_execute_filters_blank_and_none_uids`
  - `test_query_data_execute_missing_uid_column_raises_value_error`
- error propagation is covered by:
  - `tests/orchestrator_agent/test_data_query_runner.py::test_data_query_runner_missing_uid_output_marks_error_without_tool_completed_ok`
- flow compatibility is covered by:
  - `tests/test_orchestrator_visible_execution.py::test_run_agent_loop_query_data_then_profile_missing_uid_output_never_starts_run_profile`

Assessment:

- UID validation ownership remains unchanged in this slice
- invalid cohort output is now explicitly covered so it does not silently continue into `run_profile`

## Current Gaps

### Table allowlist / denylist

Current state:

- no explicit query-only table allowlist
- no explicit sensitive-table denylist
- no dedicated `information_schema` block in the current query-only scanner

Assessment:

- this is a real audit gap, but not yet a confirmed runtime vulnerability because executor still enforces read-only semantics and row-count gating
- follow-up hardening candidate for later D1.4 work

### Approved SQL audit trace

Current state:

- `awaiting_user_ack` exposes `sql_text` to the user for approval
- query-only execution does not currently produce a dedicated structured audit record containing:
  - approved SQL
  - approver identity
  - safety decision
  - rows estimated
  - execution timestamp

Assessment:

- this is a traceability gap rather than an immediate blocker
- good follow-up candidate after first-slice normalization settles

### Result-size semantics remain contract-based

Current state:

- executor blocks over-limit result sets
- `QueryDataThenProfileFlow` separately treats cohort sizes over `200` as blocked on the orchestrator side

Assessment:

- the two limits live at different layers and serve different purposes
- no contract change is needed in D1 first slice, but the distinction should stay documented

## Recommended D1.4 Handling

For the first D1 slice:

1. keep D1.4 in audit mode by default
2. add or confirm coverage first
3. only patch runtime guards if a real uncovered safety defect is demonstrated

Preferred repair order if a defect is found:

1. `data_acquisition_agent/executor.py`
2. `data_acquisition_agent/output_scanner.py`
3. `app/services/orchestrator_agent/tools/query_data.py`

Explicit constraint:

- do not move SQL safety into `QueryDataThenProfileFlow`
- do not rely on prompt wording as the primary guard
- do not change ACK contract while hardening safety

## Current Conclusion

The current query-only SQL safety boundary remains centered in `executor.py` and `output_scanner.py`, and D1.4-1 added minimal hardening plus focused coverage for:

- DDL/DML rejection
- `CALL / EXEC / LOAD DATA / INTO OUTFILE` rejection
- multi-statement rejection
- safe `SELECT / CTE` acceptance without false positives from string literals
- credential leak rejection
- dangerous-code rejection
- result-too-large precheck
- fixed error messages
- query-data UID output contract behavior
- invalid cohort output blocking before `run_profile`

The most important known follow-up gaps are:

- explicit table allowlist / denylist
- explicit `information_schema` policy
- structured approved-SQL audit trace
- UID validation ownership centralization (explicitly deferred)
