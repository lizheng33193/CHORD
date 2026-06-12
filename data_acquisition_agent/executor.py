"""V2 Execution Layer. See docs/specs/data_acquisition_agent_v2.md §7.

守门 → 连库 → COUNT 预检 → 执行 → 委托 output_writer → 组装 metadata。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .schemas import ErrorType, ExecuteRequest
from .output_scanner import (scan_credentials, scan_python_dangerous,
    check_sql_policy, _split_statements, _strip_sql_comments)
from .connection import open_starrocks_connection


class ExecutorError(Exception):
    """执行层错误；沿用 V1 OrchestratorError 风格（error_type + 固定 message + request_id）。"""

    def __init__(self, error_type: ErrorType, message: str, request_id: str = ""):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.request_id = request_id


def enforce_pre_execution_gates(
    *,
    approved_sql: str,
    sql_kind: str,
    analyst_private_prefix: str,
    request_id: str,
) -> None:
    """§7.1 守门：sql_kind / V1 三层 scanner / multi-statement。失败 raise ExecutorError。"""
    if sql_kind == "build_table_script":
        raise ExecutorError(ErrorType.DDL_NOT_SUPPORTED_IN_V2,
            "DDL is not executable by V2", request_id=request_id)
    if scan_credentials(approved_sql):
        raise ExecutorError(ErrorType.CREDENTIAL_LEAK,
            "credential pattern in artifact", request_id=request_id)
    if scan_python_dangerous(approved_sql):
        raise ExecutorError(ErrorType.DANGEROUS_CODE,
            "dangerous code pattern in artifact", request_id=request_id)
    try:
        check_sql_policy(approved_sql, "query_only", analyst_private_prefix)
    except ValueError:
        raise ExecutorError(ErrorType.DDL_POLICY_VIOLATION,
            "artifact failed SQL policy", request_id=request_id)
    stripped = _strip_sql_comments(approved_sql)
    tokens = _split_statements(stripped)
    if len(tokens) > 1:
        raise ExecutorError(ErrorType.DDL_POLICY_VIOLATION,
            "artifact failed SQL policy", request_id=request_id)


def precheck_row_count(*, conn, approved_sql, max_rows, timeout_s, request_id):
    sql_stripped = approved_sql.rstrip().rstrip(";").rstrip()
    count_sql = f"SELECT COUNT(*) FROM ({sql_stripped}) AS da_v2_count"
    try:
        with conn.cursor() as cur:
            cur.execute(count_sql)
            row = cur.fetchone()
            n = int(row[0]) if row else 0
    except ExecutorError:
        raise
    except Exception:
        raise ExecutorError(ErrorType.QUERY_FAILED,
            "query execution failed", request_id=request_id) from None
    if n > max_rows:
        raise ExecutorError(ErrorType.RESULT_TOO_LARGE,
            "result exceeds row limit", request_id=request_id)
    return n


def execute_query(
    *,
    conn: Any,
    approved_sql: str,
    timeout_s: int,
    request_id: str,
) -> pd.DataFrame:
    """§7.3 真正执行；失败 → query_failed；空集 → result_validation_failed。"""
    try:
        with conn.cursor() as cur:
            cur.execute(approved_sql)
            rows = cur.fetchall()
            cols = [d[0] for d in (cur.description or [])]
    except ExecutorError:
        raise
    except Exception:
        raise ExecutorError(ErrorType.QUERY_FAILED,
            "query execution failed", request_id=request_id) from None
    if not rows:
        raise ExecutorError(ErrorType.RESULT_VALIDATION_FAILED,
            "result validation failed", request_id=request_id)
    return pd.DataFrame(list(rows), columns=cols)


def run_execute_pipeline(request: ExecuteRequest, *, request_id: str) -> dict:
    """端到端编排：守门 → connect → COUNT → 执行 → 委托 output_writer → 组装 metadata。"""
    import time
    from datetime import datetime, timezone
    from app.core.config import settings
    from .manifest import load_manifest
    from .output_writer import (validate_bucket_schema, build_per_uid_payloads,
        write_per_uid_atomic, resolve_bucket_dir)

    manifest = load_manifest(request.target_country.value)
    enforce_pre_execution_gates(approved_sql=request.approved_sql,
        sql_kind=request.sql_kind,
        analyst_private_prefix=manifest.analyst_private_prefix,
        request_id=request_id)
    t0 = time.monotonic()
    executed_at = datetime.now(timezone.utc).isoformat()
    with open_starrocks_connection(request_id=request_id) as conn:
        precheck_row_count(conn=conn, approved_sql=request.approved_sql,
            max_rows=settings.da_max_result_rows,
            timeout_s=settings.da_query_timeout_seconds,
            request_id=request_id)
        df = execute_query(conn=conn, approved_sql=request.approved_sql,
            timeout_s=settings.da_query_timeout_seconds,
            request_id=request_id)
    actual_uid_column = validate_bucket_schema(df, output_bucket=request.output_bucket,
        output_format=request.output_format, uid_column=request.uid_column,
        request_id=request_id)
    items = build_per_uid_payloads(df, output_bucket=request.output_bucket,
        output_format=request.output_format, uid_column=actual_uid_column,
        approved_by=request.approved_by,
        source_request_id=request.source_request_id,
        executed_at=executed_at, request_id=request_id)
    bucket_dir = resolve_bucket_dir(request.output_bucket)
    bucket_dir.mkdir(parents=True, exist_ok=True)
    filenames = write_per_uid_atomic(items, bucket_dir=bucket_dir,
        output_format=request.output_format, overwrite=request.overwrite,
        request_id=request_id)
    duration_ms = int((time.monotonic() - t0) * 1000)
    uid_series = df[actual_uid_column].fillna("").astype(str).str.strip()
    rows_per_uid = {uid: int((uid_series == str(uid).strip()).sum())
                     for uid, _ in items}
    return {
        "request_id": request_id,
        "output_bucket": request.output_bucket,
        "output_format": request.output_format,
        "target_dir": str(bucket_dir),
        "filenames": filenames,
        "written_file_count": len(filenames),
        "total_uids": len(items),
        "rows_per_uid": rows_per_uid,
        "metadata": {
            "executed_at": executed_at,
            "approved_by": request.approved_by,
            "source_request_id": request.source_request_id,
            "duration_ms": duration_ms,
            "row_count_total": int(len(df)),
        },
    }
