"""Narrow bridge tool for creating Data Agent SQL HITL runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.auth.database import AuthSessionLocal
from app.core.audit import record_runtime_audit_event
from app.core.request_context import RequestContext
from app.core.user_context import UserContext
from app.data_agent.schemas import DataAgentRunCreateRequest
from app.data_agent.service import DataAgentService


class CreateDataAgentRunToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    natural_language_request: str = Field(..., min_length=1, max_length=2000)
    target_country: str = Field(..., min_length=2, max_length=32)
    run_type: Literal["cohort_query", "bucket_writeback"]
    output_bucket: Literal["app", "behavior", "credit"] | None = None
    output_format: Literal["csv", "json"] | None = None


class CreateDataAgentRunToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["data_agent_run"] = "data_agent_run"
    run_id: str
    status: str


async def create_data_agent_run_tool(
    *,
    user_context: UserContext,
    request_context: RequestContext | None,
    payload: dict[str, object],
) -> dict[str, object]:
    input_data = CreateDataAgentRunToolInput.model_validate(payload)
    db = AuthSessionLocal()
    try:
        service = DataAgentService(db)
        body = DataAgentRunCreateRequest(
            natural_language_request=input_data.natural_language_request,
            target_country=input_data.target_country,
            run_type=input_data.run_type,
            output_bucket=input_data.output_bucket,
            output_format=input_data.output_format,
        )
        detail = service.create_run(ctx=user_context, body=body)
        sql_hash = detail.current_sql.sql_hash if detail.current_sql is not None else None
        record_runtime_audit_event(
            user=user_context,
            request_context=request_context,
            event_type="orchestrator.data_agent_run.created",
            action="create",
            resource_type="data_agent_run",
            resource_id=detail.run_id,
            metadata={
                "user_id": user_context.user_id,
                "project_id": user_context.project_id,
                "country": detail.target_country,
                "run_id": detail.run_id,
                "run_type": detail.run_type,
                "sql_hash": sql_hash,
            },
        )
        return CreateDataAgentRunToolOutput(
            run_id=detail.run_id,
            status=detail.status,
        ).model_dump(mode="json")
    finally:
        db.close()
