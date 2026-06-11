"""Migrated known flow for clarification shell handling."""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator

from app.services.orchestrator_agent.finalization.final_answer_builder import build_known_final_message
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.flows.base import FlowControlSignal, FlowOutput
from app.services.orchestrator_agent.review_rules import review_step_summary
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


class ClarifyScopeFlow:
    intent = "need_clarification"

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        del ctx
        return request.intent == self.intent

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[FlowOutput]:
        execution_id = uuid.uuid4().hex
        clarification_prompt = (
            request.request_understanding.clarification_prompt
            if request.request_understanding
            else "请补充国家和时间范围。"
        )
        required_slots = list((request.request_understanding.missing_slots if request.request_understanding else []) or [])
        candidate_defaults = dict((request.request_understanding.candidate_defaults if request.request_understanding else {}) or {})
        resolution_id = f"{execution_id}:clarify_scope"
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
                    step_id="clarify_scope",
                    title="补充 cohort 查询条件",
                    kind="clarification",
                    user_visible_reason="当前请求明显是在筛选一批用户，但还缺少国家或时间范围。",
                    resolution_type="clarification",
                    resolution_prompt=clarification_prompt,
                    resolution_required_slots=required_slots,
                    resolution_candidate_defaults=candidate_defaults,
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="等待补充关键条件后再继续执行。",
                ),
            ],
        )
        update_internal_trace_metadata(
            trace,
            {
                "flow_name": "ClarifyScopeFlow",
                "flow_mode": "clarification_prompt",
            },
        )
        try:
            yield build_execution_plan_event(trace)
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="clarify_scope",
                status="awaiting_resolution",
                result_summary="等待用户补充国家和时间范围。",
            )
            await ctx.human_input.request_resolution(
                session_id=ctx.session.session_id,
                resolution_id=resolution_id,
                run_id=ctx.run_id,
            )
            ctx.lifecycle.set_pending_resolution(
                run_id=ctx.run_id,
                resolution_id=resolution_id,
                step_id="clarify_scope",
                resolution_type="clarification",
                message=clarification_prompt,
                options=[],
                title="请先补充执行条件",
            )
            ctx.lifecycle.set_run_status(run_id=ctx.run_id, status="awaiting_resolution")
            yield build_awaiting_resolution_event(
                trace,
                step_id="clarify_scope",
                resolution_id=resolution_id,
                resolution_type="clarification",
                prompt=clarification_prompt,
                required_slots=required_slots,
                candidate_defaults=candidate_defaults,
            )
            resolution = await ctx.human_input.wait_for_resolution(session_id=ctx.session.session_id, timeout_seconds=600.0)
        except asyncio.CancelledError:
            self._cleanup_resolution_state(ctx)
            raise

        answers = dict(getattr(resolution, "payload", {}) or {})
        country_answer = str(answers.get("country") or "").strip()
        time_window_answer = str(answers.get("time_window") or "").strip()
        self._cleanup_resolution_state(ctx)
        if getattr(resolution, "status", None) == "resolved" and country_answer and time_window_answer:
            yield FlowControlSignal(
                kind="clarification_resume",
                payload={
                    "answers": answers,
                    "trace": trace,
                },
            )
            return

        review = ReviewResult(
            status="fail",
            issues=[{"type": "clarification_required", "message": "缺少国家或时间范围，无法继续 cohort 执行。"}],
            can_answer=False,
            confidence_impact="缺少 cohort 关键条件，已阻断执行",
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="clarify_scope",
            status="blocked",
            result_summary="未补充完整的国家和时间范围。",
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
            extra_note="请补充国家和时间范围后重试，例如：墨西哥、最近 7 天。",
        )
        update_internal_trace_metadata(trace, {"terminal_reason": "blocked_unavailable"})
        finalize_trace(ctx.session, trace, final_status="blocked", final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )

    def _cleanup_resolution_state(self, ctx) -> None:
        ctx.lifecycle.clear_pending_resolution(run_id=ctx.run_id)
        ctx.lifecycle.set_run_status(run_id=ctx.run_id, status="running")
