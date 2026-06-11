from __future__ import annotations

import csv
import os
from pathlib import Path

import pymysql
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from data_acquisition_agent import api as api_mod
from data_acquisition_agent.api import router
from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
from scripts.local_mysql.load_mexico_local_dev import (
    APP_TABLE,
    BEHAVIOR_TABLE,
    CREDIT_TABLE,
    LABEL_TABLE,
    run_import,
)


RUN_MYSQL_INTEGRATION = os.getenv("RUN_MYSQL_INTEGRATION") == "1"
DEFAULT_SANDBOX_ROOT = "/Users/zhengli/Desktop/docker-data"

pytestmark = [
    pytest.mark.mysql_integration,
    pytest.mark.skipif(
        not RUN_MYSQL_INTEGRATION,
        reason="set RUN_MYSQL_INTEGRATION=1 to run local Docker MySQL sandbox integration tests",
    ),
]


class StubModelClient:
    mode = "mock"
    model_name = "stub-local-dev"

    def generate_structured(self, **kwargs):
        del kwargs
        return {
            "status": "ok",
            "model_name": self.model_name,
            "prompt_preview": "",
            "structured_result": {
                "reasoning_summary": "local dev app cohort",
                "sql": "SELECT DISTINCT uid FROM app_install_list LIMIT 5",
                "sql_kind": "query_only",
                "python": None,
                "audit_report": {
                    "high_risk_ddl": False,
                    "final_verdict": "ok",
                },
            },
        }


def _sandbox_root() -> Path:
    return Path(os.getenv("MYSQL_SANDBOX_ROOT", DEFAULT_SANDBOX_ROOT))


def _import_root() -> Path:
    return _sandbox_root() / "mysql-import"


def _configure_db_env() -> None:
    os.environ.setdefault("DA_LOCAL_DEV", "1")
    os.environ.setdefault("DA_DB_HOST", "127.0.0.1")
    os.environ.setdefault("DA_DB_PORT", "3307")
    os.environ.setdefault("DA_DB_USER", "maps_user")
    os.environ.setdefault("DA_DB_PASSWORD", "maps_password")
    os.environ.setdefault("DA_DB_DATABASE", "user_profile")


def _connect():
    _configure_db_env()
    return pymysql.connect(
        host=os.environ["DA_DB_HOST"],
        port=int(os.environ["DA_DB_PORT"]),
        user=os.environ["DA_DB_USER"],
        password=os.environ["DA_DB_PASSWORD"],
        database=os.environ["DA_DB_DATABASE"],
        charset="utf8mb4",
        autocommit=True,
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fetch_one_uid(table: str) -> str:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT uid FROM `{table}` ORDER BY uid LIMIT 1")
            row = cur.fetchone()
    assert row and row[0]
    return str(row[0])


def _read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        return next(reader)


@pytest.fixture(scope="module")
def imported_data():
    _configure_db_env()
    import_root = _import_root()
    assert import_root.exists(), f"missing import root: {import_root}"
    result = run_import(
        import_root=import_root,
        chunksize=int(os.getenv("MYSQL_IMPORT_CHUNKSIZE", "20000")),
        reset=True,
    )
    return result


@pytest.fixture()
def isolated_output_dirs(tmp_path, monkeypatch):
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"
    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir))
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir))
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir))
    return {
        "app": app_dir,
        "behavior": behavior_dir,
        "credit": credit_dir,
    }


def test_mysql_loader_imports_expected_counts(imported_data):
    rows = imported_data["rows"]
    assert rows[APP_TABLE] > 100_000
    assert rows[BEHAVIOR_TABLE] > 400_000
    assert rows[CREDIT_TABLE] == 1_000
    assert rows[LABEL_TABLE] == 3_670
    assert imported_data["app_raw_rows"] == 112_559
    assert imported_data["app_joined_rows"] == imported_data["app_raw_rows"]
    assert imported_data["uid_intersection"] == {
        "app": 1_000,
        "behavior": 1_000,
        "credit": 1_000,
        "all": 1_000,
    }


def test_generate_uses_local_dev_knowledge_files_via_api(monkeypatch):
    monkeypatch.setenv("DA_LOCAL_DEV", "1")
    monkeypatch.setattr(
        api_mod,
        "_get_orchestrator",
        lambda: DataAcquisitionOrchestrator(model_client=StubModelClient()),
    )
    response = _client().post(
        "/api/data-acquisition/generate",
        json={
            "natural_language_request": "帮我查 5 个有 App 数据的墨西哥用户",
            "target_country": "mexico",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "app_install_list" in body["sql"]
    assert any(
        "data_acquisition_agent/configs/local_dev/scheme.md" in path
        for path in body["metadata"]["knowledge_files_loaded"]
    )
    assert any(
        "data_acquisition_agent/configs/local_dev/few.md" in path
        for path in body["metadata"]["knowledge_files_loaded"]
    )
    assert not any(
        "各国数据知识库汇总/墨西哥/scheme.md" in path
        for path in body["metadata"]["knowledge_files_loaded"]
    )
    assert not any(
        "各国数据知识库汇总/墨西哥/few.md" in path
        for path in body["metadata"]["knowledge_files_loaded"]
    )


def test_execute_app_bucket_with_real_mysql(imported_data, isolated_output_dirs):
    del imported_data
    uid = _fetch_one_uid(APP_TABLE)
    response = _client().post(
        "/api/data-acquisition/execute",
        json={
            "approved_sql": (
                "SELECT uid, app_name, app_package, first_install_time, "
                "last_update_time, gp_category, ai_category_level_2_CN "
                f"FROM {APP_TABLE} WHERE uid = '{uid}' LIMIT 20"
            ),
            "sql_kind": "query_only",
            "target_country": "mexico",
            "approved_by": "mysql_integration_test",
            "output_bucket": "app",
            "output_format": "csv",
            "uid_column": "uid",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["written_file_count"] == 1
    output_path = isolated_output_dirs["app"] / f"{uid}.csv"
    assert output_path.exists()
    assert _read_csv_header(output_path) == [
        "uid",
        "app_name",
        "app_package",
        "first_install_time",
        "last_update_time",
        "gp_category",
        "ai_category_level_2_CN",
    ]


def test_execute_behavior_bucket_with_real_mysql(imported_data, isolated_output_dirs):
    del imported_data
    uid = _fetch_one_uid(BEHAVIOR_TABLE)
    response = _client().post(
        "/api/data-acquisition/execute",
        json={
            "approved_sql": (
                "SELECT uid, servertimestamp, timestamp_, scenetype, processtype, "
                "eventname, extend, clientmodel, clientosversion, url, refer, ip "
                f"FROM {BEHAVIOR_TABLE} WHERE uid = '{uid}' LIMIT 20"
            ),
            "sql_kind": "query_only",
            "target_country": "mexico",
            "approved_by": "mysql_integration_test",
            "output_bucket": "behavior",
            "output_format": "csv",
            "uid_column": "uid",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["written_file_count"] == 1
    output_path = isolated_output_dirs["behavior"] / f"{uid}.csv"
    assert output_path.exists()
    header = _read_csv_header(output_path)
    assert "uid" in header
    assert "timestamp_" in header or "servertimestamp" in header
    assert "eventname" in header


def test_execute_credit_bucket_with_real_mysql(imported_data, isolated_output_dirs):
    del imported_data
    uid = _fetch_one_uid(CREDIT_TABLE)
    response = _client().post(
        "/api/data-acquisition/execute",
        json={
            "approved_sql": (
                "SELECT uid, valor, nombrescore, razones, consultas_detail_json, "
                f"creditos_detail_json FROM {CREDIT_TABLE} WHERE uid = '{uid}' LIMIT 5"
            ),
            "sql_kind": "query_only",
            "target_country": "mexico",
            "approved_by": "mysql_integration_test",
            "output_bucket": "credit",
            "output_format": "csv",
            "uid_column": "uid",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["written_file_count"] == 1
    output_path = isolated_output_dirs["credit"] / f"{uid}.csv"
    assert output_path.exists()
    header = _read_csv_header(output_path)
    assert "uid" in header
    assert "valor" in header
    assert "nombrescore" in header
