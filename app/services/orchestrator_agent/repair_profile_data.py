"""Internal repair flow for missing profile buckets."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.core.data_acquisition_capability import (
    data_acquisition_unavailable_message,
    get_data_acquisition_capability,
)
from app.services.orchestrator_agent.schemas import RepairProfileDataInput, RepairProfileDataOutput
from app.services.orchestrator_agent.session import is_query_cancelled, mark_query_cancelled


_COUNTRY_MAP = {
    "mx": "mexico",
}
_BUCKET_REQUIRED_COLUMNS = {
    "app": [
        "uid",
        "app_name",
        "app_package",
        "first_install_time",
        "last_update_time",
        "gp_category",
        "ai_category_level_2_CN",
    ],
    "behavior": ["uid", "event_name", "event_time"],
    "credit": [
        "uid",
        "user_uuid",
        "valor",
        "nombrescore",
        "razones",
        "consultas_detail_json",
        "creditos_detail_json",
        "timestamp_",
    ],
}


class _RepairChildAgent:
    """Per-call repair facade around data_acquisition_agent."""

    def __init__(self, country: str, bucket: str) -> None:
        if country not in _COUNTRY_MAP:
            raise ValueError(f"repair_profile_data only supports country={country!r} in v1")
        from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator

        self.country = country
        self.bucket = bucket
        self._target_country = _COUNTRY_MAP[country]
        self._orch = DataAcquisitionOrchestrator()

    def run_query(self, request_text: str):
        from data_acquisition_agent.schemas import GenerateRequest, TargetAction, TargetCountry

        response = self._orch.generate(GenerateRequest(
            natural_language_request=request_text,
            target_country=TargetCountry(self._target_country),
            target_action=TargetAction.EXTRACT,
        ))
        return type("RepairQueryResult", (), {
            "sql_text": response.sql or "",
            "rows_estimated": -1,
            "reasoning_summary": response.reasoning_summary,
        })()

    def execute(self, sql_text: str):
        from data_acquisition_agent.executor import run_execute_pipeline
        from data_acquisition_agent.schemas import ExecuteRequest, TargetCountry

        request_id = uuid.uuid4().hex
        response = run_execute_pipeline(
            ExecuteRequest(
                approved_sql=sql_text,
                sql_kind="query_only",
                target_country=TargetCountry(self._target_country),
                approved_by="orchestrator_repair",
                output_bucket=self.bucket,
                output_format="csv",
                uid_column="uid",
                overwrite=True,
            ),
            request_id=request_id,
        )
        metadata = response.get("metadata", {}) or {}
        return {
            "uids": sorted((response.get("rows_per_uid") or {}).keys()),
            "rows_actual": int(metadata.get("row_count_total", 0)),
            "filenames": list(response.get("filenames") or []),
            "written_file_count": int(response.get("written_file_count", 0)),
        }


@dataclass
class PreparedRepairQuery:
    input_data: RepairProfileDataInput
    child: _RepairChildAgent
    sql_text: str
    rows_estimated: int


def build_repair_request(input_data: RepairProfileDataInput) -> str:
    quoted_uids = ", ".join(input_data.uids)
    bucket_hint = {
        "app": "应用安装明细",
        "behavior": "行为事件明细",
        "credit": "征信/信用明细",
    }[input_data.bucket]
    required_columns = ", ".join(_BUCKET_REQUIRED_COLUMNS[input_data.bucket])
    extra_uid_hint = ""
    if input_data.bucket == "credit":
        extra_uid_hint = (
            "请优先返回原始 Buró 明细字段，不要在 SQL 中派生信用画像摘要等级字段。"
            "如果上游原始字段只有 user_uuid，请在最终结果中同时输出 uid（可由 user_uuid 重命名得到）。"
        )
    return (
        f"请为以下 UID 补齐可用于用户画像的 {bucket_hint} 数据，只返回明细结果，不要汇总，不要建表。"
        f"目标 UID: {quoted_uids}。"
        f"必须至少包含这些字段: {required_columns}。"
        f"{extra_uid_hint}"
        f"补数原因：{input_data.reason}。"
        f"结果需要按 uid 可落到 {input_data.bucket} bucket。"
    )


def _await_user_ack(
    session_id: str,
    tool_call_id: str,
    sql_text: str,
    rows_estimated: int,
) -> bool:
    from app.services.orchestrator_agent import ack_bus

    confirm = ack_bus.wait_ack(session_id, timeout_sec=600.0)
    if not confirm:
        mark_query_cancelled(session_id)
        return False
    return True


def _write_repair_csv(bucket: str, rows: list[dict], target_uids: list[str]) -> list[str]:
    """Fallback writer for tests / future raw-row execution paths."""
    fieldnames = list(rows[0].keys()) if rows else ["uid"]
    bucket_dir = _bucket_dir(bucket)
    bucket_dir.mkdir(parents=True, exist_ok=True)
    filenames: list[str] = []
    for uid in target_uids:
        matching_rows = [row for row in rows if str(row.get("uid", "")).strip() == uid]
        if not matching_rows:
            continue
        file_path = bucket_dir / f"{uid}.csv"
        import csv
        with file_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(matching_rows)
        filenames.append(file_path.name)
    return filenames


def _bucket_dir(bucket: str) -> Path:
    attr = {
        "app": "app_by_uid_dir",
        "behavior": "behavior_by_uid_dir",
        "credit": "credit_by_uid_dir",
    }[bucket]
    return settings.resolve_path(getattr(settings, attr))


def prepare_repair_query(input_data: RepairProfileDataInput) -> PreparedRepairQuery:
    capability = get_data_acquisition_capability()
    if not capability.enabled:
        raise RuntimeError(data_acquisition_unavailable_message(capability))
    child = _RepairChildAgent(input_data.country, input_data.bucket)
    query_result = child.run_query(build_repair_request(input_data))
    return PreparedRepairQuery(
        input_data=input_data,
        child=child,
        sql_text=query_result.sql_text,
        rows_estimated=int(getattr(query_result, "rows_estimated", -1) or -1),
    )


def execute_repair_query(prepared: PreparedRepairQuery) -> RepairProfileDataOutput:
    execute_out = prepared.child.execute(prepared.sql_text)
    written_uids = list(execute_out.get("uids") or [])
    filenames = list(execute_out.get("filenames") or [])

    from app.services.orchestrator_agent.data_availability import check_data_availability

    availability = check_data_availability(written_uids, country=prepared.input_data.country)
    for row in availability.per_uid:
        bucket_status = getattr(row, prepared.input_data.bucket)
        if not bucket_status.usable_for_profile:
            raise ValueError(f"repair_unusable_after_write:{prepared.input_data.bucket}:{row.uid}")

    return RepairProfileDataOutput(
        bucket=prepared.input_data.bucket,
        requested_uids=prepared.input_data.uids,
        written_uids=written_uids,
        filenames=filenames,
        sql_text=prepared.sql_text,
        rows_estimated=prepared.rows_estimated,
        rows_actual=int(execute_out.get("rows_actual") or 0),
    )


def repair_profile_data(
    input_data: RepairProfileDataInput,
    *,
    session_id: str,
    tool_call_id: str,
    before_ack: Callable[[str, int], None] | None = None,
) -> RepairProfileDataOutput:
    from app.services.orchestrator_agent import ack_bus

    if is_query_cancelled(session_id):
        raise PermissionError("user cancelled in this session")

    prepared = prepare_repair_query(input_data)
    ack_bus.open_ack(session_id)
    if before_ack is not None:
        before_ack(prepared.sql_text, prepared.rows_estimated)
    if not _await_user_ack(session_id, tool_call_id, prepared.sql_text, prepared.rows_estimated):
        raise PermissionError("User rejected SQL execution")
    return execute_repair_query(prepared)
