import pytest
from data_acquisition_agent.executor import (enforce_pre_execution_gates,
    ExecutorError)
from data_acquisition_agent.schemas import ErrorType

PFX = "dm_model.yyp_tmp_"

def test_gate_rejects_build_table_script():
    with pytest.raises(ExecutorError) as ei:
        enforce_pre_execution_gates(approved_sql="CREATE TABLE x AS SELECT 1",
            sql_kind="build_table_script", analyst_private_prefix=PFX,
            request_id="rid")
    assert ei.value.error_type == ErrorType.DDL_NOT_SUPPORTED_IN_V2
    assert ei.value.message == "DDL is not executable by V2"

@pytest.mark.parametrize("sql", [
    "DROP TABLE x", "INSERT INTO x VALUES (1)",
    "UPDATE x SET a=1", "DELETE FROM x WHERE 1=1",
    "TRUNCATE TABLE x", "ALTER TABLE x ADD COLUMN c INT",
    "CREATE TABLE x AS SELECT 1",
    "CALL read_only_proc()",
    "EXEC read_only_proc()",
    "LOAD DATA INFILE '/tmp/users.csv' INTO TABLE users",
    "SELECT uid FROM users INTO OUTFILE '/tmp/users.csv'",
])
def test_gate_rejects_ddl_dml_in_query_only(sql):
    with pytest.raises(ExecutorError) as ei:
        enforce_pre_execution_gates(approved_sql=sql, sql_kind="query_only",
            analyst_private_prefix=PFX, request_id="rid")
    assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION


def test_gate_rejects_multi_statement():
    with pytest.raises(ExecutorError) as ei:
        enforce_pre_execution_gates(
            approved_sql="SELECT 1; SELECT 2",
            sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")
    assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION


def test_gate_rejects_multi_statement_with_comment_and_newline_evasion():
    with pytest.raises(ExecutorError) as ei:
        enforce_pre_execution_gates(
            approved_sql="SELECT uid FROM t /* harmless */ ;\nDELETE FROM t",
            sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")
    assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION

def test_gate_rejects_credential_leak():
    with pytest.raises(ExecutorError) as ei:
        enforce_pre_execution_gates(
            approved_sql="SELECT 1 -- password='leak_xyz'",
            sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")
    assert ei.value.error_type == ErrorType.CREDENTIAL_LEAK

def test_gate_rejects_dangerous_python():
    """§7.1 Step 2: scan_python_dangerous defensive guard。"""
    with pytest.raises(ExecutorError) as ei:
        enforce_pre_execution_gates(
            approved_sql="SELECT uid FROM t WHERE x=eval('1+1')",
            sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")
    assert ei.value.error_type == ErrorType.DANGEROUS_CODE

def test_gate_allows_clean_select():
    enforce_pre_execution_gates(approved_sql="SELECT uid FROM t WHERE x=1",
        sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")


def test_gate_allows_safe_cte_and_string_literals_with_keywords():
    enforce_pre_execution_gates(
        approved_sql=(
            "WITH cohort AS (SELECT uid FROM t WHERE note = 'drop candidate') "
            "SELECT uid FROM cohort WHERE note = 'exec me later' LIMIT 10"
        ),
        sql_kind="query_only",
        analyst_private_prefix=PFX,
        request_id="rid",
    )


def test_gate_strips_comments_before_split():
    """; 在注释里不应触发 multi-statement。"""
    enforce_pre_execution_gates(
        approved_sql="SELECT uid FROM t -- foo; bar\n WHERE x=1",
        sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")


def test_gate_does_not_treat_semicolon_in_string_literal_as_multi_statement():
    enforce_pre_execution_gates(
        approved_sql="SELECT uid FROM t WHERE note = 'a;b'",
        sql_kind="query_only",
        analyst_private_prefix=PFX,
        request_id="rid",
    )


from unittest.mock import MagicMock
from data_acquisition_agent.executor import precheck_row_count

def _mock_conn_returning(value):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (value,) if value is not None else None
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur

def test_precheck_returns_count():
    conn, cur = _mock_conn_returning(42)
    n = precheck_row_count(conn=conn, approved_sql="SELECT 1",
        max_rows=100, timeout_s=60, request_id="rid")
    assert n == 42

def test_precheck_raises_when_over_limit():
    conn, cur = _mock_conn_returning(101)
    with pytest.raises(ExecutorError) as ei:
        precheck_row_count(conn=conn, approved_sql="SELECT 1",
            max_rows=100, timeout_s=60, request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_TOO_LARGE

def test_precheck_db_failure_to_query_failed():
    conn = MagicMock()
    conn.cursor.side_effect = Exception("syntax error near foo")
    with pytest.raises(ExecutorError) as ei:
        precheck_row_count(conn=conn, approved_sql="SELECT 1",
            max_rows=100, timeout_s=60, request_id="rid")
    assert ei.value.error_type == ErrorType.QUERY_FAILED
    assert ei.value.message == "query execution failed"
    assert "syntax" not in ei.value.message

def test_precheck_wraps_sql_in_count():
    conn, cur = _mock_conn_returning(5)
    precheck_row_count(conn=conn, approved_sql="SELECT uid FROM t LIMIT 10",
        max_rows=100, timeout_s=60, request_id="rid")
    executed = cur.execute.call_args.args[0]
    assert "SELECT COUNT(*)" in executed.upper()
    assert "FROM (" in executed.upper()
    assert "AS DA_V2_COUNT" in executed.upper()


import pandas as pd
from data_acquisition_agent.executor import execute_query

def _mock_conn_returning_rows(rows, columns):
    conn = MagicMock()
    cur = MagicMock()
    cur.description = [(c,) for c in columns]
    cur.fetchall.return_value = rows
    conn.cursor.return_value.__enter__.return_value = cur
    return conn

def test_execute_returns_dataframe():
    conn = _mock_conn_returning_rows([("u1", "WhatsApp"), ("u2", "FB")],
        ["uid", "app_name"])
    df = execute_query(conn=conn, approved_sql="SELECT uid, app_name FROM t",
        timeout_s=60, request_id="rid")
    assert list(df.columns) == ["uid", "app_name"]
    assert len(df) == 2

def test_execute_empty_result_raises_validation():
    conn = _mock_conn_returning_rows([], ["uid", "app_name"])
    with pytest.raises(ExecutorError) as ei:
        execute_query(conn=conn, approved_sql="SELECT uid FROM t",
            timeout_s=60, request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

def test_execute_db_failure_to_query_failed():
    conn = MagicMock()
    conn.cursor.side_effect = Exception("table 'x' doesn't exist")
    with pytest.raises(ExecutorError) as ei:
        execute_query(conn=conn, approved_sql="SELECT 1",
            timeout_s=60, request_id="rid")
    assert ei.value.error_type == ErrorType.QUERY_FAILED
    assert "doesn" not in ei.value.message


from data_acquisition_agent.executor import run_execute_pipeline
from data_acquisition_agent.schemas import ExecuteRequest

def _exec_req(**kw):
    defaults = dict(
        approved_sql=("SELECT uid, app_name, app_package, first_install_time, "
                      "last_update_time, gp_category, ai_category_level_2_CN "
                      "FROM dm_model.yyp_tmp_x"),
        sql_kind="query_only", target_country="mexico", approved_by="t",
        output_bucket="app", output_format="csv", uid_column="uid")
    defaults.update(kw)
    return ExecuteRequest(**defaults)

def _mock_conn_pipeline(rows_count: int):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (rows_count,)
    cur.description = [(c,) for c in
        ["uid","app_name","app_package","first_install_time",
         "last_update_time","gp_category","ai_category_level_2_CN"]]
    cur.fetchall.return_value = [
        ("u1","WA","p","t","t","g","c"),
        ("u2","FB","p","t","t","g","c")]
    conn.cursor.return_value.__enter__.return_value = cur
    return conn

def test_pipeline_happy_path(monkeypatch, tmp_path):
    from data_acquisition_agent import output_writer as ow
    bucket = tmp_path / "app"; bucket.mkdir()
    monkeypatch.setattr(ow, "resolve_bucket_dir", lambda b: bucket)
    class CM:
        def __enter__(self_): return _mock_conn_pipeline(2)
        def __exit__(self_, *a): return False
    monkeypatch.setitem(run_execute_pipeline.__globals__, "open_starrocks_connection", lambda **kw: CM())

    result = run_execute_pipeline(_exec_req(), request_id="rid-happy")
    assert result["output_bucket"] == "app"
    assert result["written_file_count"] == 2
    assert sorted(result["filenames"]) == ["u1.csv", "u2.csv"]
    assert result["total_uids"] == 2
    assert result["metadata"]["row_count_total"] == 2


def test_pipeline_rows_per_uid_counts_numeric_uid_values(monkeypatch, tmp_path):
    from data_acquisition_agent import output_writer as ow

    bucket = tmp_path / "app"
    bucket.mkdir()
    monkeypatch.setattr(ow, "resolve_bucket_dir", lambda b: bucket)

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (3,)
    cur.description = [(c,) for c in
        ["uid","app_name","app_package","first_install_time",
         "last_update_time","gp_category","ai_category_level_2_CN"]]
    cur.fetchall.return_value = [
        (123, "WA", "p", "t", "t", "g", "c"),
        (123, "FB", "p", "t", "t", "g", "c"),
        (456, "TG", "p", "t", "t", "g", "c"),
    ]
    conn.cursor.return_value.__enter__.return_value = cur

    class CM:
        def __enter__(self_):
            return conn

        def __exit__(self_, *a):
            return False

    monkeypatch.setitem(run_execute_pipeline.__globals__, "open_starrocks_connection", lambda **kw: CM())

    result = run_execute_pipeline(_exec_req(), request_id="rid-numeric")

    assert result["rows_per_uid"] == {"123": 2, "456": 1}


def test_pipeline_build_table_script_rejected_no_connect(monkeypatch):
    from data_acquisition_agent import executor as ex
    called = {"connect": 0}
    class _NeverEnter:
        def __enter__(self_): called["connect"] += 1; return MagicMock()
        def __exit__(self_, *a): return False
    monkeypatch.setattr(ex, "open_starrocks_connection",
        lambda **kw: _NeverEnter())
    req = _exec_req(sql_kind="build_table_script",
        approved_sql="CREATE TABLE dm_model.yyp_tmp_x AS SELECT 1")
    with pytest.raises(ExecutorError) as ei:
        run_execute_pipeline(req, request_id="rid-no")
    assert ei.value.error_type == ErrorType.DDL_NOT_SUPPORTED_IN_V2
    assert called["connect"] == 0  # T1：守门在前，不连库
