"""query_data — Parent-Child facade with lazy Data Agent execution imports.

`query_data` is used for cohort discovery, not profile-bucket repair. The
execute phase therefore returns UID lists and SQL metadata only, and does not
write anything into `data/*/by_uid`.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.data_acquisition_capability import (
    data_acquisition_unavailable_message,
    get_data_acquisition_capability,
)
from app.services.orchestrator_agent.schemas import QueryDataInput, QueryDataOutput


_PROHIBITED_SQL = re.compile(
    r"(?is)\b(?:DELETE|DROP|TRUNCATE|UPDATE|INSERT|CALL|EXEC)\b|"
    r"\bLOAD\s+DATA\b|"
    r"\bINTO\s+OUTFILE\b",
)
_COUNTRY_MAP: dict[str, str] = {
    "mx": "mexico",
    "th": "thailand",
}
_UID_FIELD_CANDIDATES = {
    "uid",
    "userid",
    "useruuid",
    "customerid",
}


def _normalize_column_name(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())


def _mask_sql_string_literals(sql: str) -> str:
    chars: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote is None:
            if ch in {"'", '"'}:
                quote = ch
            chars.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < len(sql):
            chars.append(" ")
            chars.append(" ")
            i += 2
            continue
        if ch == quote:
            if quote == "'" and i + 1 < len(sql) and sql[i + 1] == quote:
                chars.append(" ")
                chars.append(" ")
                i += 2
                continue
            quote = None
            chars.append(ch)
            i += 1
            continue
        chars.append(" ")
        i += 1
    return "".join(chars)


def _load_settings():
    from app.core.config import settings

    return settings


def _load_manifest(country: str):
    from data_acquisition_agent.manifest import load_manifest

    return load_manifest(country)


def enforce_pre_execution_gates(**kwargs):
    from data_acquisition_agent.executor import enforce_pre_execution_gates as _impl

    return _impl(**kwargs)


def open_starrocks_connection(*args, **kwargs):
    from data_acquisition_agent.connection import open_starrocks_connection as _impl

    return _impl(*args, **kwargs)


def precheck_row_count(**kwargs):
    from data_acquisition_agent.executor import precheck_row_count as _impl

    return _impl(**kwargs)


def execute_query(**kwargs):
    from data_acquisition_agent.executor import execute_query as _impl

    return _impl(**kwargs)


@dataclass
class _ChildResult:
    sql_text: str
    rows_estimated: int


class _ChildAgent:
    """Per-call facade with lazy Data Agent imports."""

    def __init__(self, country: str) -> None:
        capability = get_data_acquisition_capability()
        if not capability.enabled:
            raise RuntimeError(data_acquisition_unavailable_message(capability))
        if country not in _COUNTRY_MAP:
            raise ValueError(
                f"V1 query_data does not support country={country!r}; "
                f"only mx (and stub th) supported. See Plan #03 Scope."
            )
        from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
        from data_acquisition_agent.schemas import TargetCountry

        self._country_code = country
        self._country_name = _COUNTRY_MAP[country]
        self._target_country = TargetCountry(self._country_name)
        self._orch = DataAcquisitionOrchestrator()

    def run_query(self, request_text: str) -> _ChildResult:
        from data_acquisition_agent.schemas import GenerateRequest, TargetAction

        gen_req = GenerateRequest(
            natural_language_request=request_text,
            target_country=self._target_country,
            target_action=TargetAction.EXTRACT,
        )
        gen_resp = self._orch.generate(gen_req)
        return _ChildResult(sql_text=gen_resp.sql or "", rows_estimated=-1)

    def execute(
        self,
        sql_text: str,
        *,
        approved_by: str = "orchestrator_agent",
        output_bucket: str = "behavior",
        output_format: str = "json",
    ) -> dict[str, Any]:
        del approved_by, output_bucket, output_format
        request_id = uuid.uuid4().hex
        manifest = _load_manifest(self._country_name)
        settings = _load_settings()

        enforce_pre_execution_gates(
            approved_sql=sql_text,
            sql_kind="query_only",
            analyst_private_prefix=manifest.analyst_private_prefix,
            request_id=request_id,
        )
        with open_starrocks_connection(request_id=request_id) as conn:
            rows_estimated = precheck_row_count(
                conn=conn,
                approved_sql=sql_text,
                max_rows=settings.da_max_result_rows,
                timeout_s=settings.da_query_timeout_seconds,
                request_id=request_id,
            )
            df = execute_query(
                conn=conn,
                approved_sql=sql_text,
                timeout_s=settings.da_query_timeout_seconds,
                request_id=request_id,
            )

        uid_column = next(
            (
                col
                for col in df.columns
                if _normalize_column_name(col) in _UID_FIELD_CANDIDATES
            ),
            None,
        )
        if uid_column is None:
            raise ValueError("query_data result missing uid column")

        uids = sorted({
            text
            for value in df[uid_column].tolist()
            if value is not None
            for text in [str(value).strip()]
            if text
        })
        return {
            "uids": uids,
            "rows_actual": int(len(df)),
            "rows_estimated": int(rows_estimated),
        }


def query_data(input_data: QueryDataInput) -> QueryDataOutput:
    """Single-shot query path for tests and non-streaming callers."""
    child = _ChildAgent(country=input_data.country)
    try:
        gen = child.run_query(input_data.request)
        sql_text = gen.sql_text
        if _PROHIBITED_SQL.search(_mask_sql_string_literals(sql_text)):
            raise ValueError("Prohibited SQL keyword detected in generated SQL")
        execute_out = child.execute(sql_text)
        return QueryDataOutput(
            uids=execute_out["uids"],
            rows_actual=execute_out["rows_actual"],
            sql_text=sql_text,
            rows_estimated=int(execute_out.get("rows_estimated", gen.rows_estimated) or -1),
        )
    finally:
        del child
