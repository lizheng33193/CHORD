from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

import pymysql
from dotenv import dotenv_values

from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
from data_acquisition_agent.schemas import GenerateRequest

from .load_mexico_local_dev import (
    APP_TABLE,
    BEHAVIOR_TABLE,
    CREDIT_TABLE,
    LABEL_TABLE,
    run_import,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SANDBOX_ROOT = Path("/Users/zhengli/Desktop/docker-data")
DEFAULT_ENV_FILE = REPO_ROOT / ".env.local-mysql"
DEFAULT_ENV_EXAMPLE_FILE = REPO_ROOT / ".env.local-mysql.example"
COMPOSE_FILE = REPO_ROOT / "docker/mysql/docker-compose.yml"
STACK_OUTPUT_DIR = REPO_ROOT / "outputs" / "local_mysql_dev"
PID_FILE = STACK_OUTPUT_DIR / "uvicorn.pid"
LOG_FILE = STACK_OUTPUT_DIR / "uvicorn.log"

TRACKED_ENV_KEYS = [
    "MODEL_MODE",
    "MODEL_NAME",
    "DATA_SOURCE",
    "DATA_ACQUISITION_ENABLED",
    "AUTH_ENABLED",
    "AUTH_SEED_ON_STARTUP",
    "AUTH_JWT_SECRET",
    "AUTH_JWT_EXPIRE_MINUTES",
    "DEFAULT_ADMIN_USERNAME",
    "DEFAULT_ADMIN_EMAIL",
    "DEFAULT_ADMIN_PASSWORD",
    "DA_LOCAL_DEV",
    "DA_DB_HOST",
    "DA_DB_PORT",
    "DA_DB_USER",
    "DA_DB_PASSWORD",
    "DA_DB_DATABASE",
    "DA_MAX_RESULT_ROWS",
    "DA_QUERY_TIMEOUT_SECONDS",
    "APP_BY_UID_DIR",
    "BEHAVIOR_BY_UID_DIR",
    "CREDIT_BY_UID_DIR",
    "LOCAL_MYSQL_APP_HOST",
    "LOCAL_MYSQL_APP_PORT",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_SANDBOX_ROOT",
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "AUTH_DATABASE_URL",
    "RISK_KNOWLEDGE_UPLOAD_DIR",
    "RISK_KNOWLEDGE_MAX_UPLOAD_MB",
    "RISK_KNOWLEDGE_ALLOWED_UPLOAD_EXTENSIONS",
    "RISK_KNOWLEDGE_REDIS_URL",
    "RISK_KNOWLEDGE_REDIS_KEY_PREFIX",
    "RISK_KNOWLEDGE_EMBEDDING_PROVIDER",
    "RISK_KNOWLEDGE_EMBEDDING_MODEL",
    "RISK_KNOWLEDGE_EMBEDDING_DIMENSION",
    "RISK_KNOWLEDGE_EMBEDDING_OUTPUT_TYPE",
    "RISK_KNOWLEDGE_EMBEDDING_TEXT_TYPE",
    "RISK_KNOWLEDGE_RERANKER_PROVIDER",
    "RISK_KNOWLEDGE_RERANKER_MODEL",
    "RISK_KNOWLEDGE_ANSWER_PROVIDER",
    "DASHSCOPE_API_KEY",
    "MYSQL_IMPORT_CHUNKSIZE",
]

TABLE_NAMES = (APP_TABLE, BEHAVIOR_TABLE, CREDIT_TABLE, LABEL_TABLE)


class StubLocalDevModelClient:
    mode = "mock"
    model_name = "stub-local-dev"

    def generate_structured(self, **kwargs):
        del kwargs
        return {
            "status": "ok",
            "model_name": self.model_name,
            "prompt_preview": "",
            "structured_result": {
                "reasoning_summary": "local mysql sandbox smoke",
                "sql": "SELECT DISTINCT uid FROM app_install_list LIMIT 5",
                "sql_kind": "query_only",
                "python": None,
                "audit_report": {
                    "high_risk_ddl": False,
                    "final_verdict": "ok",
                },
            },
        }


def build_default_env(project_root: Path, sandbox_root: Path) -> dict[str, str]:
    del project_root
    return {
        "MODEL_MODE": "mock",
        "MODEL_NAME": "gemini-2.5-flash",
        "DATA_SOURCE": "local",
        "DATA_ACQUISITION_ENABLED": "true",
        "AUTH_ENABLED": "true",
        "AUTH_SEED_ON_STARTUP": "true",
        "AUTH_JWT_SECRET": "dev_secret_change_me",
        "AUTH_JWT_EXPIRE_MINUTES": "1440",
        "DEFAULT_ADMIN_USERNAME": "admin",
        "DEFAULT_ADMIN_EMAIL": "admin@example.com",
        "DEFAULT_ADMIN_PASSWORD": "admin123456",
        "DA_LOCAL_DEV": "1",
        "DA_DB_HOST": "127.0.0.1",
        "DA_DB_PORT": "3307",
        "DA_DB_USER": "maps_user",
        "DA_DB_PASSWORD": "maps_password",
        "DA_DB_DATABASE": "user_profile",
        "DA_MAX_RESULT_ROWS": "100000",
        "DA_QUERY_TIMEOUT_SECONDS": "60",
        "APP_BY_UID_DIR": "data/local_mysql_test/app/by_uid",
        "BEHAVIOR_BY_UID_DIR": "data/local_mysql_test/behavior/by_uid",
        "CREDIT_BY_UID_DIR": "data/local_mysql_test/credit/by_uid",
        "LOCAL_MYSQL_APP_HOST": "127.0.0.1",
        "LOCAL_MYSQL_APP_PORT": "8000",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3307",
        "MYSQL_SANDBOX_ROOT": str(sandbox_root),
        "MYSQL_ROOT_PASSWORD": "root_change_me",
        "MYSQL_DATABASE": "user_profile",
        "MYSQL_USER": "maps_user",
        "MYSQL_PASSWORD": "maps_password",
        "AUTH_DATABASE_URL": "mysql+pymysql://maps_user:maps_password@127.0.0.1:3307/user_profile?charset=utf8mb4",
        "RISK_KNOWLEDGE_UPLOAD_DIR": "storage/risk_knowledge/uploads",
        "RISK_KNOWLEDGE_MAX_UPLOAD_MB": "50",
        "RISK_KNOWLEDGE_ALLOWED_UPLOAD_EXTENSIONS": "pdf,docx,md,txt",
        "RISK_KNOWLEDGE_REDIS_URL": "redis://127.0.0.1:6379/15",
        "RISK_KNOWLEDGE_REDIS_KEY_PREFIX": "chord:risk_knowledge",
        "RISK_KNOWLEDGE_EMBEDDING_PROVIDER": "dashscope",
        "RISK_KNOWLEDGE_EMBEDDING_MODEL": "text-embedding-v4",
        "RISK_KNOWLEDGE_EMBEDDING_DIMENSION": "1024",
        "RISK_KNOWLEDGE_EMBEDDING_OUTPUT_TYPE": "dense",
        "RISK_KNOWLEDGE_EMBEDDING_TEXT_TYPE": "document",
        "RISK_KNOWLEDGE_RERANKER_PROVIDER": "dashscope",
        "RISK_KNOWLEDGE_RERANKER_MODEL": "qwen3-rerank",
        "RISK_KNOWLEDGE_ANSWER_PROVIDER": "deterministic",
        "DASHSCOPE_API_KEY": "",
        "MYSQL_IMPORT_CHUNKSIZE": "20000",
    }


def render_env_text(env: Mapping[str, str]) -> str:
    header = [
        "# Local MySQL sandbox preset for data_acquisition_agent",
        "# Copy to .env.local-mysql and adjust only if needed.",
        "",
    ]
    body = [f"{key}={env[key]}" for key in TRACKED_ENV_KEYS if key in env]
    return "\n".join(header + body) + "\n"


def build_uvicorn_command(host: str, port: int, reload: bool) -> list[str]:
    command = ["python", "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)]
    if reload:
        command.append("--reload")
    return command


def build_execute_smoke_requests(uid: str) -> list[dict[str, Any]]:
    return [
        {
            "approved_sql": (
                "SELECT uid, app_name, app_package, first_install_time, "
                "last_update_time, gp_category, ai_category_level_2_CN "
                f"FROM {APP_TABLE} WHERE uid = '{uid}' LIMIT 20"
            ),
            "sql_kind": "query_only",
            "target_country": "mexico",
            "approved_by": "local_mysql_stack",
            "output_bucket": "app",
            "output_format": "csv",
            "uid_column": "uid",
        },
        {
            "approved_sql": (
                "SELECT uid, servertimestamp, timestamp_, scenetype, processtype, "
                "eventname, extend, clientmodel, clientosversion, url, refer, ip "
                f"FROM {BEHAVIOR_TABLE} WHERE uid = '{uid}' LIMIT 50"
            ),
            "sql_kind": "query_only",
            "target_country": "mexico",
            "approved_by": "local_mysql_stack",
            "output_bucket": "behavior",
            "output_format": "csv",
            "uid_column": "uid",
        },
        {
            "approved_sql": (
                "SELECT uid, valor, nombrescore, razones, consultas_detail_json, "
                f"creditos_detail_json FROM {CREDIT_TABLE} WHERE uid = '{uid}' LIMIT 5"
            ),
            "sql_kind": "query_only",
            "target_country": "mexico",
            "approved_by": "local_mysql_stack",
            "output_bucket": "credit",
            "output_format": "csv",
            "uid_column": "uid",
        },
    ]


def should_run_live_generate(model_mode: str, api_key: str | None) -> bool:
    return model_mode.strip().lower() != "mock" and bool((api_key or "").strip())


def _quote_env_value(value: str) -> str:
    if any(char in value for char in (" ", "#", '"')):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def write_env_file(path: Path, env: Mapping[str, str]) -> None:
    path.write_text(render_env_text({key: _quote_env_value(value) for key, value in env.items()}), encoding="utf-8")


def _load_env_file_values(env_file: Path) -> dict[str, str]:
    raw = dotenv_values(env_file)
    return {str(key): str(value) for key, value in raw.items() if key and value is not None}


def ensure_env_file(env_file: Path) -> Path:
    env_file.parent.mkdir(parents=True, exist_ok=True)
    if env_file.exists():
        return env_file
    defaults = build_default_env(REPO_ROOT, DEFAULT_SANDBOX_ROOT)
    write_env_file(env_file, defaults)
    return env_file


def load_stack_env(env_file: Path) -> dict[str, str]:
    defaults = build_default_env(REPO_ROOT, DEFAULT_SANDBOX_ROOT)
    file_values = _load_env_file_values(env_file) if env_file.exists() else {}
    merged = defaults.copy()
    merged.update(file_values)
    return merged


def _child_env(stack_env: Mapping[str, str]) -> dict[str, str]:
    child = os.environ.copy()
    child.update({key: str(value) for key, value in stack_env.items()})
    return child


def apply_stack_env(stack_env: Mapping[str, str]) -> None:
    for key, value in stack_env.items():
        os.environ[key] = str(value)


def ensure_runtime_dirs(stack_env: Mapping[str, str]) -> None:
    sandbox_root = Path(stack_env["MYSQL_SANDBOX_ROOT"])
    for subdir in ("mysql-data", "mysql-import", "mysql-logs"):
        (sandbox_root / subdir).mkdir(parents=True, exist_ok=True)
    for key in ("APP_BY_UID_DIR", "BEHAVIOR_BY_UID_DIR", "CREDIT_BY_UID_DIR"):
        path = Path(stack_env[key])
        if not path.is_absolute():
            path = REPO_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
    STACK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_command(command: list[str], *, env: Mapping[str, str], cwd: Path = REPO_ROOT) -> None:
    subprocess.run(command, cwd=str(cwd), env=_child_env(env), check=True)


def docker_compose_up(stack_env: Mapping[str, str]) -> None:
    run_command(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"],
        env=stack_env,
    )


def docker_compose_down(stack_env: Mapping[str, str], *, remove_volumes: bool) -> None:
    command = ["docker", "compose", "-f", str(COMPOSE_FILE), "down"]
    if remove_volumes:
        command.append("-v")
    run_command(command, env=stack_env)


def _mysql_connect(stack_env: Mapping[str, str]):
    return pymysql.connect(
        host=stack_env["DA_DB_HOST"],
        port=int(stack_env["DA_DB_PORT"]),
        user=stack_env["DA_DB_USER"],
        password=stack_env["DA_DB_PASSWORD"],
        database=stack_env["DA_DB_DATABASE"],
        charset="utf8mb4",
        autocommit=True,
    )


def wait_for_mysql(stack_env: Mapping[str, str], *, timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with _mysql_connect(stack_env) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(1)
    raise RuntimeError(f"MySQL did not become ready within {timeout_seconds}s: {last_error}")


def get_table_counts(stack_env: Mapping[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with _mysql_connect(stack_env) as conn:
        with conn.cursor() as cur:
            for table in TABLE_NAMES:
                cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                row = cur.fetchone()
                counts[table] = int(row[0]) if row else 0
    return counts


def bootstrap_mysql_data(stack_env: Mapping[str, str], *, reset: bool = False) -> dict[str, Any]:
    counts = get_table_counts(stack_env)
    needs_import = reset or any(counts.get(table, 0) == 0 for table in TABLE_NAMES)
    if not needs_import:
        return {"rows": counts, "skipped": True}
    return run_import(
        import_root=Path(stack_env["MYSQL_SANDBOX_ROOT"]) / "mysql-import",
        chunksize=int(stack_env.get("MYSQL_IMPORT_CHUNKSIZE", "20000")),
        reset=True,
    )


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return None


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url, data=data, method=method, headers=headers)
    with urllib_request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_text(method: str, url: str, payload: dict[str, Any] | None = None) -> str:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url, data=data, method=method, headers=headers)
    with urllib_request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8")


def wait_for_http(base_url: str, *, timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            body = _http_json("GET", f"{base_url}/health")
            if body.get("status") == "ok":
                return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise RuntimeError(f"HTTP server did not become healthy within {timeout_seconds}s: {base_url}")


def start_app_server(stack_env: Mapping[str, str], *, reload: bool) -> dict[str, Any]:
    host = stack_env["LOCAL_MYSQL_APP_HOST"]
    port = int(stack_env["LOCAL_MYSQL_APP_PORT"])
    base_url = f"http://{host}:{port}"
    existing_pid = _read_pid()
    if existing_pid and _pid_is_running(existing_pid):
        wait_for_http(base_url, timeout_seconds=15)
        return {"status": "already_running", "pid": existing_pid, "base_url": base_url, "log_file": str(LOG_FILE)}
    if PID_FILE.exists():
        PID_FILE.unlink()
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("a", encoding="utf-8")
    process = subprocess.Popen(
        build_uvicorn_command(host=host, port=port, reload=reload),
        cwd=str(REPO_ROOT),
        env=_child_env(stack_env),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    wait_for_http(base_url)
    return {"status": "started", "pid": process.pid, "base_url": base_url, "log_file": str(LOG_FILE)}


def stop_app_server() -> dict[str, Any]:
    pid = _read_pid()
    if not pid:
        return {"status": "not_running"}
    if not _pid_is_running(pid):
        PID_FILE.unlink(missing_ok=True)
        return {"status": "stale_pid_removed", "pid": pid}
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 15
    while time.time() < deadline:
        if not _pid_is_running(pid):
            PID_FILE.unlink(missing_ok=True)
            return {"status": "stopped", "pid": pid}
        time.sleep(0.5)
    os.kill(pid, signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    return {"status": "killed", "pid": pid}


def pick_smoke_uid(stack_env: Mapping[str, str]) -> str:
    with _mysql_connect(stack_env) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT uid FROM `{CREDIT_TABLE}` ORDER BY uid LIMIT 1")
            row = cur.fetchone()
    if not row or not row[0]:
        raise RuntimeError("No UID found in credit_report_raw for smoke test")
    return str(row[0])


def run_generate_contract_check() -> dict[str, Any]:
    orchestrator = DataAcquisitionOrchestrator(model_client=StubLocalDevModelClient())
    response = orchestrator.generate(
        GenerateRequest(
            natural_language_request="帮我查 5 个有 App 数据的墨西哥用户",
            target_country="mexico",
        )
    )
    return {
        "sql": response.sql,
        "knowledge_files_loaded": response.metadata.knowledge_files_loaded,
    }


def run_smoke(stack_env: Mapping[str, str], *, base_url: str | None = None) -> dict[str, Any]:
    host = stack_env["LOCAL_MYSQL_APP_HOST"]
    port = int(stack_env["LOCAL_MYSQL_APP_PORT"])
    resolved_base_url = base_url or f"http://{host}:{port}"
    generate_contract = run_generate_contract_check()
    uid = pick_smoke_uid(stack_env)
    execute_results = []
    for payload in build_execute_smoke_requests(uid):
        execute_results.append(
            {
                "bucket": payload["output_bucket"],
                "body": _http_json("POST", f"{resolved_base_url}/api/data-acquisition/execute", payload),
            }
        )
    analyze_text = _http_text(
        "POST",
        f"{resolved_base_url}/api/analyze-stream",
        {
            "uid": uid,
            "application_time": "2026-04-15T12:00:00",
            "country": "mx",
        },
    )
    file_paths = {
        "app": (REPO_ROOT / stack_env["APP_BY_UID_DIR"] / f"{uid}.csv").exists(),
        "behavior": (REPO_ROOT / stack_env["BEHAVIOR_BY_UID_DIR"] / f"{uid}.csv").exists(),
        "credit": (REPO_ROOT / stack_env["CREDIT_BY_UID_DIR"] / f"{uid}.csv").exists(),
    }
    return {
        "uid": uid,
        "generate_contract": generate_contract,
        "execute_results": execute_results,
        "analysis_started": "analysis_started" in analyze_text,
        "analysis_completed": "analysis_completed" in analyze_text,
        "stream_error": "stream_error" in analyze_text,
        "by_uid_files": file_paths,
    }


def _cmd_write_env(args) -> int:
    env_file = Path(args.env_file)
    env = build_default_env(REPO_ROOT, Path(args.sandbox_root))
    write_env_file(env_file, env)
    print(json.dumps({"env_file": str(env_file), "written": True}, ensure_ascii=False, indent=2))
    return 0


def _cmd_up(args) -> int:
    env_file = ensure_env_file(Path(args.env_file))
    stack_env = load_stack_env(env_file)
    apply_stack_env(stack_env)
    ensure_runtime_dirs(stack_env)
    docker_compose_up(stack_env)
    wait_for_mysql(stack_env)
    import_summary = bootstrap_mysql_data(stack_env, reset=args.reset_db)
    server_summary = start_app_server(stack_env, reload=not args.no_reload)
    result = {
        "env_file": str(env_file),
        "mysql": import_summary,
        "server": server_summary,
    }
    if not args.no_smoke:
        result["smoke"] = run_smoke(stack_env, base_url=server_summary["base_url"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_smoke(args) -> int:
    env_file = ensure_env_file(Path(args.env_file))
    stack_env = load_stack_env(env_file)
    apply_stack_env(stack_env)
    host = stack_env["LOCAL_MYSQL_APP_HOST"]
    port = int(stack_env["LOCAL_MYSQL_APP_PORT"])
    wait_for_mysql(stack_env)
    wait_for_http(f"http://{host}:{port}")
    result = run_smoke(stack_env)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_down(args) -> int:
    env_file = ensure_env_file(Path(args.env_file))
    stack_env = load_stack_env(env_file)
    stop_summary = stop_app_server()
    docker_compose_down(stack_env, remove_volumes=args.volumes)
    result = {"server": stop_summary, "docker_down": True, "volumes_removed": args.volumes}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local MySQL sandbox bootstrap for data_acquisition_agent.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Path to the local sandbox env file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_env_parser = subparsers.add_parser("write-env", help="Write a local sandbox env file preset.")
    write_env_parser.add_argument(
        "--env-file",
        dest="env_file",
        default=str(DEFAULT_ENV_FILE),
        help="Path to the local sandbox env file.",
    )
    write_env_parser.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))
    write_env_parser.set_defaults(func=_cmd_write_env)

    up_parser = subparsers.add_parser("up", help="Start Docker MySQL, import data if needed, start app, and smoke test.")
    up_parser.add_argument("--reset-db", action="store_true", help="Force re-import of the four local-dev tables.")
    up_parser.add_argument("--no-smoke", action="store_true", help="Skip the post-start smoke validation.")
    up_parser.add_argument("--no-reload", action="store_true", help="Start uvicorn without --reload.")
    up_parser.set_defaults(func=_cmd_up)

    smoke_parser = subparsers.add_parser("smoke", help="Run smoke validation against the running local sandbox.")
    smoke_parser.set_defaults(func=_cmd_smoke)

    down_parser = subparsers.add_parser("down", help="Stop uvicorn and tear down Docker MySQL.")
    down_parser.add_argument("--volumes", action="store_true", help="Also remove Docker volumes via compose down -v.")
    down_parser.set_defaults(func=_cmd_down)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
