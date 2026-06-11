import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data_acquisition_agent.api import router
from data_acquisition_agent import api as api_mod
from data_acquisition_agent.executor import ExecutorError
from data_acquisition_agent.connection import DbUnreachableError
from data_acquisition_agent.schemas import ErrorType

def _client(): app = FastAPI(); app.include_router(router); return TestClient(app)

def _req(): return {"approved_sql":"SELECT 1","sql_kind":"query_only",
    "target_country":"mexico","approved_by":"t",
    "output_bucket":"app","output_format":"csv","uid_column":"uid"}

def test_execute_happy_path_returns_200(monkeypatch):
    monkeypatch.setattr(api_mod, "_run_execute_pipeline",
        lambda req, request_id: {"request_id": request_id,
            "output_bucket":"app","output_format":"csv",
            "filenames":["u1.csv"], "written_file_count":1, "total_uids":1,
            "rows_per_uid":{"u1":1},
            "metadata":{"executed_at":"t","approved_by":"t",
                "source_request_id":None,"duration_ms":1,"row_count_total":1}})
    r = _client().post("/api/data-acquisition/execute", json=_req())
    assert r.status_code == 200
    assert r.json()["written_file_count"] == 1

@pytest.mark.parametrize("etype,expected_status,expected_msg", [
    (ErrorType.DDL_NOT_SUPPORTED_IN_V2, 422, "DDL is not executable by V2"),
    (ErrorType.QUERY_FAILED,            422, "query execution failed"),
    (ErrorType.RESULT_VALIDATION_FAILED,422, "result validation failed"),
    (ErrorType.RESULT_TOO_LARGE,        413, "result exceeds row limit"),
    (ErrorType.OUTPUT_WRITE_FAILED,     500, "output write failed"),
])
def test_execute_v2_error_mapping(monkeypatch, etype, expected_status,
                                   expected_msg):
    def boom(req, request_id):
        raise ExecutorError(etype, expected_msg, request_id=request_id)
    monkeypatch.setattr(api_mod, "_run_execute_pipeline", boom)
    r = _client().post("/api/data-acquisition/execute", json=_req())
    assert r.status_code == expected_status
    body = r.json()
    assert body["error_type"] == etype.value
    assert body["message"] == expected_msg
    assert body["request_id"]

def test_execute_db_unreachable_mapped(monkeypatch):
    def boom(req, request_id):
        raise DbUnreachableError(request_id=request_id)
    monkeypatch.setattr(api_mod, "_run_execute_pipeline", boom)
    r = _client().post("/api/data-acquisition/execute", json=_req())
    assert r.status_code == 502
    assert r.json()["error_type"] == "db_unreachable"
    assert r.json()["message"] == "database connection failed"

def test_execute_response_no_absolute_path_or_sql_echo(monkeypatch):
    monkeypatch.setattr(api_mod, "_run_execute_pipeline",
        lambda req, request_id: {"request_id": request_id,
            "output_bucket":"app","output_format":"csv",
            "filenames":["u1.csv"], "written_file_count":1, "total_uids":1,
            "rows_per_uid":{"u1":1},
            "metadata":{"executed_at":"t","approved_by":"t",
                "source_request_id":None,"duration_ms":1,"row_count_total":1}})
    r = _client().post("/api/data-acquisition/execute", json=_req())
    body_text = r.text
    assert "SELECT 1" not in body_text
    assert "/data/" not in body_text and "\\data\\" not in body_text

def test_execute_invalid_country_422():
    r = _client().post("/api/data-acquisition/execute",
        json={**_req(), "target_country":"atlantis"})
    assert r.status_code == 422  # Pydantic enum 校验

def test_api_module_imports_without_execute_dependencies(monkeypatch):
    import builtins
    import importlib
    import sys

    original_import = builtins.__import__

    def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"data_acquisition_agent.connection", "data_acquisition_agent.executor"}:
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _patched_import)
    for mod in [
        "data_acquisition_agent.api",
        "data_acquisition_agent.connection",
        "data_acquisition_agent.executor",
    ]:
        sys.modules.pop(mod, None)

    mod = importlib.import_module("data_acquisition_agent.api")

    assert hasattr(mod, "router")
