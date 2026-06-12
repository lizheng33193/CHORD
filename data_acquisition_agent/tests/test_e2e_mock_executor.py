import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data_acquisition_agent.api import router

def _client(): app = FastAPI(); app.include_router(router); return TestClient(app)

def _req_ddl(): return {"approved_sql":"CREATE TABLE dm_model.yyp_tmp_x AS SELECT 1",
    "sql_kind":"build_table_script","target_country":"mexico","approved_by":"t",
    "output_bucket":"app","output_format":"csv","uid_column":"uid"}

def test_t1_build_table_script_422_no_connect():
    from data_acquisition_agent import executor as ex

    called = {"n": 0}

    class _NeverEnter:
        def __enter__(self_):
            called["n"] += 1
            raise AssertionError("must not connect")

        def __exit__(self_, *a):
            return False

    with patch.object(ex, "open_starrocks_connection", return_value=_NeverEnter()):
        r = _client().post("/api/data-acquisition/execute", json=_req_ddl())
    assert r.status_code == 422
    assert r.json()["error_type"] == "ddl_not_supported_in_v2"
    assert r.json()["message"] == "DDL is not executable by V2"
    assert called["n"] == 0


@pytest.mark.parametrize("sql", [
    "CREATE TABLE x AS SELECT 1", "DROP TABLE x", "ALTER TABLE x ADD c INT",
    "TRUNCATE TABLE x", "INSERT INTO x VALUES (1)",
    "UPDATE x SET a=1", "DELETE FROM x WHERE 1=1",
    "CALL read_only_proc()", "EXEC read_only_proc()",
    "LOAD DATA INFILE '/tmp/users.csv' INTO TABLE users",
    "SELECT uid FROM users INTO OUTFILE '/tmp/users.csv'",
])
def test_t2_query_only_rejects_ddl_dml(sql, monkeypatch):
    from data_acquisition_agent import executor as ex
    monkeypatch.setattr(ex, "open_starrocks_connection",
        lambda **kw: pytest.fail("must not connect"))
    r = _client().post("/api/data-acquisition/execute",
        json={**_req_ddl(), "sql_kind":"query_only", "approved_sql": sql})
    assert r.status_code == 422
    assert r.json()["error_type"] == "ddl_policy_violation"


SECRET = "FAKE_PW_DO_NOT_LEAK_42"

def test_t3_db_unreachable_no_secret_in_log_or_response(monkeypatch, caplog):
    monkeypatch.setenv("DA_DB_HOST", "10.0.0.1")
    monkeypatch.setenv("DA_DB_PORT", "9030")
    monkeypatch.setenv("DA_DB_USER", "ro_user")
    monkeypatch.setenv("DA_DB_PASSWORD", SECRET)
    monkeypatch.setenv("DA_DB_DATABASE", "dm_fake")
    with patch("data_acquisition_agent.connection.pymysql.connect",
               side_effect=Exception(f"Access denied (password={SECRET})")):
        import logging
        with caplog.at_level(logging.DEBUG):
            r = _client().post("/api/data-acquisition/execute",
                json={"approved_sql":"SELECT uid FROM dm_model.yyp_tmp_x",
                      "sql_kind":"query_only","target_country":"mexico",
                      "approved_by":"t","output_bucket":"app",
                      "output_format":"csv","uid_column":"uid"})
    assert r.status_code == 502
    assert SECRET not in r.text
    for record in caplog.records:
        assert SECRET not in record.getMessage()
        assert SECRET not in str(record.args or "")
    assert SECRET not in r.json().get("message", "")


from data_acquisition_agent import api as api_mod
from data_acquisition_agent.executor import ExecutorError
from data_acquisition_agent.connection import DbUnreachableError
from data_acquisition_agent.schemas import ErrorType

V2_ERRORS = [
    (ErrorType.DDL_NOT_SUPPORTED_IN_V2, "DDL is not executable by V2"),
    (ErrorType.QUERY_FAILED,            "query execution failed"),
    (ErrorType.RESULT_VALIDATION_FAILED,"result validation failed"),
    (ErrorType.RESULT_TOO_LARGE,        "result exceeds row limit"),
    (ErrorType.OUTPUT_WRITE_FAILED,     "output write failed"),
]

@pytest.mark.parametrize("etype,fixed_msg", V2_ERRORS)
def test_t4_response_has_fixed_message_no_payload(monkeypatch, etype, fixed_msg):
    LEAK_HINT = "uid app_name SELECT FROM dm_model.yyp_tmp_x"
    def boom(req, request_id):
        raise ExecutorError(etype, fixed_msg, request_id=request_id)
    monkeypatch.setattr(api_mod, "_run_execute_pipeline", boom)
    r = _client().post("/api/data-acquisition/execute",
        json={"approved_sql": LEAK_HINT,"sql_kind":"query_only",
            "target_country":"mexico","approved_by":"t",
            "output_bucket":"app","output_format":"csv","uid_column":"uid"})
    body = r.json()
    assert body["message"] == fixed_msg
    assert "SELECT" not in body["message"]
    assert "dm_model" not in body["message"]
    assert "app_name" not in body["message"]

def test_t4_db_unreachable_fixed_message(monkeypatch):
    def boom(req, request_id):
        raise DbUnreachableError(request_id=request_id)
    monkeypatch.setattr(api_mod, "_run_execute_pipeline", boom)
    r = _client().post("/api/data-acquisition/execute",
        json={"approved_sql":"SELECT 1","sql_kind":"query_only",
            "target_country":"mexico","approved_by":"t",
            "output_bucket":"app","output_format":"csv","uid_column":"uid"})
    assert r.json()["message"] == "database connection failed"


def test_e2e_happy_path_app_bucket_mexico(monkeypatch, tmp_path):
    from data_acquisition_agent import executor as ex
    from data_acquisition_agent import output_writer as ow
    bucket = tmp_path / "app_by_uid"; bucket.mkdir()
    monkeypatch.setattr(ow, "resolve_bucket_dir", lambda b: bucket)

    def fake_open(**kw):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = (3,)
        cur.description = [(c,) for c in
            ["uid","app_name","app_package","first_install_time",
             "last_update_time","gp_category","ai_category_level_2_CN"]]
        cur.fetchall.return_value = [
            ("u1","WA","p","t","t","g","c"),
            ("u1","FB","p","t","t","g","c"),
            ("u2","TG","p","t","t","g","c")]
        conn.cursor.return_value.__enter__.return_value = cur
        class CM:
            def __enter__(self_): return conn
            def __exit__(self_, *a): return False
        return CM()
    monkeypatch.setattr(ex, "open_starrocks_connection", fake_open)

    r = _client().post("/api/data-acquisition/execute",
        json={"approved_sql":("SELECT uid, app_name, app_package, first_install_time, "
                              "last_update_time, gp_category, ai_category_level_2_CN "
                              "FROM dm_model.yyp_tmp_x"),
              "sql_kind":"query_only","target_country":"mexico",
              "approved_by":"alice","output_bucket":"app",
              "output_format":"csv","uid_column":"uid"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written_file_count"] == 2
    assert body["total_uids"] == 2
    assert sorted(body["filenames"]) == ["u1.csv", "u2.csv"]
    assert body["metadata"]["row_count_total"] == 3
    assert body["metadata"]["approved_by"] == "alice"
    assert (bucket / "u1.csv").exists()
    assert (bucket / "u2.csv").exists()
