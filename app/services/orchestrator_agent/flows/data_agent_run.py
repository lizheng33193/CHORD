"""Known flow for orchestrator-created Data Agent SQL HITL runs."""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

from app.auth.permissions import normalize_country_scope_value, require_country_access, require_permissions
from app.data_agent.service import DataAgentService
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.flows.base import FlowOutput
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.trace_store import (
    build_execution_plan_event,
    create_execution_trace,
    finalize_trace,
    set_trace_review,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import NormalizedRequest, PlanStep, ReviewResult
from app.services.orchestrator_agent.tools.create_data_agent_run_tool import create_data_agent_run_tool


class DataAgentRunFlow:
    intent = "create_data_agent_run"

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        del ctx
        return request.intent == self.intent

    def resolve_target_country(self, ctx, request: NormalizedRequest) -> str:
        return normalize_country_scope_value(
            request.country or ctx.detected_country or ctx.session.country or "mx"
        ) or "mx"

    def build_tool_payload(
        self,
        ctx,
        request: NormalizedRequest,
        *,
        request_text: str | None = None,
    ) -> dict[str, object]:
        target_country = self.resolve_target_country(ctx, request)
        return {
            "natural_language_request": (request_text or request.query_request or ctx.prompt).strip(),
            "target_country": target_country,
            "run_type": request.data_agent_run_type or "cohort_query",
            "output_bucket": request.data_agent_output_bucket,
            "output_format": request.data_agent_output_format,
        }

    def require_create_access(self, ctx, request: NormalizedRequest) -> None:
        if ctx.user_context is None:
            raise PermissionError("missing user context")
        require_permissions(ctx.user_context, ("data:query:generate", "data:query:view_sql"))
        require_country_access(ctx.user_context, self.resolve_target_country(ctx, request), project_id=ctx.user_context.project_id)

    async def create_run_result(
        self,
        ctx,
        request: NormalizedRequest,
        *,
        request_text: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        self.require_create_access(ctx, request)
        payload = self.build_tool_payload(ctx, request, request_text=request_text)
        if ctx.user_context is None:
            raise PermissionError("missing user context")
        result = await create_data_agent_run_tool(
            user_context=ctx.user_context,
            request_context=ctx.request_context,
            payload=payload,
        )
        return payload, result

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[FlowOutput]:
        execution_id = uuid.uuid4().hex
        trace = create_execution_trace(
            ctx.session,
            execution_id=execution_id,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
            prompt=ctx.prompt,
            normalized_request=request,
            availability=None,
            steps=[
                PlanStep(
                    step_id="create_data_agent_run",
                    title="创建 Data Agent SQL 审核任务",
                    kind="tool",
                    tool_name="create_data_agent_run_tool",
                    user_visible_reason="当前请求已明确要求创建需要人工审核的 SQL 任务。",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="确认任务已进入 SQLReviewCard，后续审批与执行仍由 M1 API 控制。",
                ),
            ],
        )
        update_internal_trace_metadata(
            trace,
            {
                "flow_name": "DataAgentRunFlow",
                "flow_mode": "deterministic_bridge",
            },
        )
        yield build_execution_plan_event(trace)
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="create_data_agent_run",
            status="running",
            result_summary="正在创建 Data Agent SQL 审核任务。",
        )
        payload, result = await self.create_run_result(ctx, request)
        artifact = {
            "type": "data_agent_run",
            "run_id": str(result.get("run_id") or ""),
        }
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="create_data_agent_run",
            status="done",
            result_summary=f"已创建 SQL 审核任务，run_id={artifact['run_id']}。",
        )
        review = ReviewResult(
            status="pass",
            issues=[],
            can_answer=True,
            confidence_impact="任务已进入人工审核闭环，等待用户在 SQLReviewCard 中继续操作。",
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="review_final",
            status="done",
            result_summary="已确认 Orchestrator 仅创建任务，不会自动 approve 或 execute。",
        )
        yield set_trace_review(ctx.session, trace, review)
        final_message = "我已为你创建一个 Data Agent SQL 审核任务，请在下方卡片中确认 SQL。"
        update_internal_trace_metadata(
            trace,
            {
                "tool_name": "create_data_agent_run_tool",
                "target_country": payload["target_country"],
                "data_agent_run_id": artifact["run_id"],
            },
        )
        finalize_trace(ctx.session, trace, final_status="completed", final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=final_message,
            confidence=1.0,
            detected_country=self.resolve_target_country(ctx, request),
            artifacts=[artifact],
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )
