from __future__ import annotations

import os
import sys
from pathlib import Path


def test_build_default_env_contains_local_mysql_defaults(tmp_path):
    from scripts.local_mysql.local_stack import build_default_env

    env = build_default_env(
        project_root=tmp_path,
        sandbox_root=Path("/Users/zhengli/Desktop/docker-data"),
    )

    assert env["MODEL_MODE"] == "mock"
    assert env["DATA_ACQUISITION_ENABLED"] == "true"
    assert env["DA_LOCAL_DEV"] == "1"
    assert env["DA_DB_HOST"] == "127.0.0.1"
    assert env["DA_DB_PORT"] == "3307"
    assert env["DA_DB_DATABASE"] == "user_profile"
    assert env["APP_BY_UID_DIR"] == "data/local_mysql_test/app/by_uid"
    assert env["BEHAVIOR_BY_UID_DIR"] == "data/local_mysql_test/behavior/by_uid"
    assert env["CREDIT_BY_UID_DIR"] == "data/local_mysql_test/credit/by_uid"
    assert env["LOCAL_MYSQL_APP_PORT"] == "8000"


def test_render_env_text_contains_expected_lines(tmp_path):
    from scripts.local_mysql.local_stack import build_default_env, render_env_text

    env = build_default_env(
        project_root=tmp_path,
        sandbox_root=Path("/Users/zhengli/Desktop/docker-data"),
    )

    text = render_env_text(env)

    assert "DA_LOCAL_DEV=1" in text
    assert "DATA_ACQUISITION_ENABLED=true" in text
    assert "APP_BY_UID_DIR=data/local_mysql_test/app/by_uid" in text
    assert "LOCAL_MYSQL_APP_PORT=8000" in text


def test_build_uvicorn_command_respects_reload_flag():
    from scripts.local_mysql.local_stack import build_uvicorn_command

    command = build_uvicorn_command(host="127.0.0.1", port=8013, reload=False)

    assert command[:4] == [sys.executable, "-m", "uvicorn", "app.main:app"]
    assert "--host" in command
    assert "127.0.0.1" in command
    assert "--port" in command
    assert "8013" in command
    assert "--reload" not in command


def test_build_execute_smoke_requests_cover_three_buckets():
    from scripts.local_mysql.local_stack import build_execute_smoke_requests

    requests = build_execute_smoke_requests("824812551379353600")

    assert [request["output_bucket"] for request in requests] == ["app", "behavior", "credit"]
    assert "ai_category_level_2_CN" in requests[0]["approved_sql"]
    assert "eventname" in requests[1]["approved_sql"]
    assert "valor" in requests[2]["approved_sql"]


def test_should_run_live_generate_only_when_model_is_not_mock():
    from scripts.local_mysql.local_stack import should_run_live_generate

    assert should_run_live_generate(model_mode="gemini", api_key="abc") is True
    assert should_run_live_generate(model_mode="mock", api_key="abc") is False
    assert should_run_live_generate(model_mode="gemini", api_key="") is False


def test_apply_stack_env_exports_values(monkeypatch, tmp_path):
    from scripts.local_mysql.local_stack import apply_stack_env, build_default_env

    env = build_default_env(
        project_root=tmp_path,
        sandbox_root=Path("/Users/zhengli/Desktop/docker-data"),
    )
    original_values = {key: os.environ.get(key) for key in env}
    monkeypatch.delenv("DA_LOCAL_DEV", raising=False)

    try:
        apply_stack_env(env)

        assert os.environ["DA_LOCAL_DEV"] == "1"
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_load_stack_env_prefers_env_file_over_ambient_shell(monkeypatch, tmp_path):
    from scripts.local_mysql.local_stack import load_stack_env

    env_file = tmp_path / ".env.local-mysql"
    env_file.write_text("MODEL_MODE=mock\nDA_LOCAL_DEV=1\n", encoding="utf-8")
    monkeypatch.setenv("MODEL_MODE", "vertex")

    env = load_stack_env(env_file)

    assert env["MODEL_MODE"] == "mock"
