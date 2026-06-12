"""Known flow for ambiguous data-request clarification."""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator

from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.flows.base import FlowOutput
from app.services.orchestrator_agent.flows.data_agent_run import DataAgentRunFlow
from app.services.orchestrator_agent.request_understanding import build_request_understanding
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.trace_store import (
    build_awaiting_resolution_event,
    build_execution_plan_event,
    create_execution_trace,
    finalize_trace,
    set_trace_review,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import NormalizedRequest, PlanStep, ReviewResult


class ClarifyDataRequestFlow:
    intent = "clarify_data_request"

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        del ctx
        return request.intent == self.intent

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[FlowOutput]:
        execution_id = uuid.uuid4().hex
        original_prompt = (request.query_request or ctx.prompt).strip()
        clarification_prompt = (
            request.request_understanding.clarification_prompt
            if request.request_understanding and request.request_understanding.clarification_prompt
            else "你是想继续普通画像/对话，还是创建一个需要人工审核的 SQL 任务？"
        )
        options = ["profile_chat", "create_sql_review_task"]
        resolution_id = f"{execution_id}:clarify_data_request"
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
                    step_id="clarify_data_request",
                    title="澄清数据任务类型",
                    kind="clarification",
                    user_visible_reason="当前请求只说要查数据，还未明确是普通画像还是创建 SQL 审核任务。",
                    resolution_type="clarify_data_request",
                    resolution_prompt=clarification_prompt,
                    resolution_options=options,
                ),
                PlanStep(
                    step_id="create_data_agent_run",
                    title="创建 Data Agent SQL 审核任务",
                    kind="tool",
                    tool_name="create_data_agent_run_tool",
                    user_visible_reason="只有在用户明确选择 SQL 审核任务后才会创建 run。",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="确认后续路径保持在受控范围内。",
                ),
            ],
        )
        update_internal_trace_metadata(
            trace,
            {
                "flow_name": "ClarifyDataRequestFlow",
                "flow_mode": "resolution_prompt",
                "original_prompt": original_prompt,
            },
        )
        try:
            yield build_execution_plan_event(trace)
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="clarify_data_request",
                status="awaiting_resolution",
                result_summary="等待用户确认是普通画像对话还是 SQL 审核任务。",
            )
            await ctx.human_input.request_resolution(
                session_id=ctx.session.session_id,
                resolution_id=resolution_id,
                run_id=ctx.run_id,
            )
            ctx.lifecycle.set_pending_resolution(
                run_id=ctx.run_id,
                resolution_id=resolution_id,
                step_id="clarify_data_request",
                resolution_type="clarify_data_request",
                message=clarification_prompt,
                options=options,
                title="请选择数据请求处理方式",
                payload={"original_prompt": original_prompt},
            )
            ctx.lifecycle.set_run_status(run_id=ctx.run_id, status="awaiting_resolution")
            yield build_awaiting_resolution_event(
                trace,
                step_id="clarify_data_request",
                resolution_id=resolution_id,
                resolution_type="clarify_data_request",
                prompt=clarification_prompt,
                options=options,
            )
            resolution = await ctx.human_input.wait_for_resolution(
                session_id=ctx.session.session_id,
                timeout_seconds=600.0,
            )
        except asyncio.CancelledError:
            self._cleanup_resolution_state(ctx)
            raise

        payload = dict(getattr(resolution, "payload", {}) or {})
        selected_option = str(payload.get("selected_option") or "").strip() or "profile_chat"
        self._cleanup_resolution_state(ctx)

        if getattr(resolution, "status", None) == "resolved" and selected_option == "create_sql_review_task":
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="clarify_data_request",
                status="done",
                result_summary="用户已选择创建 SQL 审核任务。",
            )
            data_agent_flow = DataAgentRunFlow()
            create_request = request.model_copy(
                update={
                    "intent": "create_data_agent_run",
                    "query_request": original_prompt,
                    "request_summary": "创建 Data Agent SQL 审核任务",
                    "data_agent_run_type": "cohort_query",
                    "data_agent_output_bucket": None,
                    "data_agent_output_format": None,
                    "request_understanding": build_request_understanding(
                        prompt=original_prompt,
                        intent="create_data_agent_run",
                        uids=[],
                        focus=["data_agent"],
                    ),
                }
            )
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="create_data_agent_run",
                status="running",
                result_summary="正在根据用户选择创建 SQL 审核任务。",
            )
            _, result = await data_agent_flow.create_run_result(
                ctx,
                create_request,
                request_text=original_prompt,
            )
            artifact = {"type": "data_agent_run", "run_id": str(result.get("run_id") or "")}
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
                confidence_impact="已进入受控 SQL HITL 审核路径，等待人工确认。",
            )
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="review_final",
                status="done",
                result_summary="已确认只有用户明确选择后才会创建 SQL 审核任务。",
            )
            yield set_trace_review(ctx.session, trace, review)
            final_message = "我已为你创建一个 Data Agent SQL 审核任务，请在下方卡片中确认 SQL。"
            finalize_trace(ctx.session, trace, final_status="completed", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=ctx.prompt,
                final_message=final_message,
                confidence=1.0,
                detected_country=data_agent_flow.resolve_target_country(ctx, create_request),
                artifacts=[artifact],
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        yield update_trace_step(
            ctx.session,
            trace,
            step_id="clarify_data_request",
            status="done",
            result_summary="用户选择继续普通画像/对话，不创建 SQL 审核任务。",
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="create_data_agent_run",
            status="skipped",
            result_summary="未创建 SQL 审核任务。",
        )
        review = ReviewResult(
            status="pass",
            issues=[],
            can_answer=True,
            confidence_impact="未进入 SQL 路径，保持普通画像/对话流程。",
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="review_final",
            status="done",
            result_summary="已确认本轮不创建 SQL 审核任务。",
        )
        yield set_trace_review(ctx.session, trace, review)
        final_message = "这次我先不创建 SQL 审核任务。你可以继续直接问普通画像问题，或明确说“用 Data Agent 生成 SQL …”。"
        finalize_trace(ctx.session, trace, final_status="completed", final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=final_message,
            confidence=0.9,
            detected_country=request.country or ctx.detected_country,
            artifacts=[],
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )

    def _cleanup_resolution_state(self, ctx) -> None:
        ctx.lifecycle.clear_pending_resolution(run_id=ctx.run_id)
        ctx.lifecycle.set_run_status(run_id=ctx.run_id, status="running")
