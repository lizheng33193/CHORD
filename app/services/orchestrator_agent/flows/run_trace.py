"""Migrated known flow for run_trace execution."""

from __future__ import annotations

import uuid
from typing import AsyncIterator

from app.services.orchestrator_agent.execution.tool_runner import ToolRunSpec
from app.services.orchestrator_agent.finalization.final_answer_builder import build_known_final_message
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.flows.base import FlowOutput
from app.services.orchestrator_agent.review_rules import review_step_summary
from app.services.orchestrator_agent.runtime.cancellation import cancel_requested
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.trace_store import (
    build_execution_plan_event,
    create_execution_trace,
    finalize_trace,
    set_trace_review,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import NormalizedRequest, PlanStep, ReviewResult, RunTraceInput


class RunTraceFlow:
    intent = "run_trace"

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        del ctx
        return request.intent == self.intent and bool(request.uids)

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[FlowOutput]:
        from app.services.orchestrator_agent import tools as tools_mod

        uid = request.uids[0]
        trace = create_execution_trace(
            ctx.session,
            execution_id=uuid.uuid4().hex,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
            prompt=ctx.prompt,
            normalized_request=request,
            availability=None,
            steps=[
                PlanStep(
                    step_id="run_trace",
                    title="执行轨迹分析",
                    kind="run_trace",
                    user_visible_reason="用户显式请求深度行为轨迹分析。",
                    tool_name="run_trace",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="确认轨迹分析结果可回答当前问题。",
                ),
            ],
        )
        update_internal_trace_metadata(
            trace,
            {
                "flow_name": "RunTraceFlow",
                "flow_mode": "run_trace",
                "trace_days": request.trace_days,
            },
        )
        yield build_execution_plan_event(trace)
        yield update_trace_step(ctx.session, trace, step_id="run_trace", status="running")

        handle = await ctx.tools.start(
            ToolRunSpec(
                name="run_trace",
                func=tools_mod.run_trace,
                input_payload={"uid": uid, "days": request.trace_days},
                call_args=(RunTraceInput(uid=uid, days=request.trace_days),),
                trace_id=trace.trace_id or trace.execution_id,
            )
        )
        tool_call_id = handle.record.tool_call_id
        if handle.started_event is not None:
            yield handle.started_event
        result = await handle.execute()
        if result.completed_event is not None:
            yield result.completed_event

        if result.status == "completed":
            output = result.output
            cancel_events = cancel_requested(
                ctx.session,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
                trace=trace,
            ) or []
            if cancel_events:
                for evt in cancel_events:
                    yield evt
                return
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="run_trace",
                status="done",
                result_summary="已完成轨迹分析。",
                tool_call_id=tool_call_id,
            )
            review = ReviewResult(status="pass", issues=[], can_answer=True, confidence_impact=None)
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="review_final",
                status="done",
                result_summary=review_step_summary(review),
            )
            yield set_trace_review(ctx.session, trace, review)
            final_message = build_known_final_message(
                request,
                trace_output=output,
                review=review,
                extra_note="可继续结合左侧画像模块核对关键风险信号。",
            )
            finalize_trace(ctx.session, trace, final_status="completed", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=ctx.prompt,
                final_message=final_message,
                confidence=0.88,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        error_message = result.error or "run_trace failed"
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="run_trace",
            status="failed",
            result_summary=error_message,
            tool_call_id=tool_call_id,
        )
        review = ReviewResult(
            status="fail",
            issues=[{"type": "tool_error", "message": error_message}],
            can_answer=False,
            confidence_impact="轨迹分析执行失败",
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="review_final",
            status="done",
            result_summary=review_step_summary(review),
        )
        yield set_trace_review(ctx.session, trace, review)
        final_message = build_known_final_message(
            request,
            review=review,
            extra_note="请稍后重试或改为查看已有画像模块。",
        )
        update_internal_trace_metadata(trace, {"terminal_reason": "tool_error"})
        finalize_trace(ctx.session, trace, final_status="error", final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )
