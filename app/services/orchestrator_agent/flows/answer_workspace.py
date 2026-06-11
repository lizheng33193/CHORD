"""Migrated known flow for workspace-evidence answers."""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

from app.services.orchestrator_agent.finalization.final_answer_builder import build_known_final_message
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.review_rules import build_no_workspace_review, review_step_summary
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.trace_store import (
    build_execution_plan_event,
    create_execution_trace,
    finalize_trace,
    set_trace_review,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import NormalizedRequest, PlanStep, ReviewResult
from app.services.orchestrator_agent.visible_execution import (
    answer_from_workspace_with_evidence,
    build_workspace_evidence_bundle,
)


class AnswerWorkspaceFlow:
    intent = "answer_from_workspace"

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        if request.intent != self.intent:
            return False
        if self._build_evidence(ctx, request) is not None:
            return True
        return not bool(request.uids)

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[dict[str, Any]]:
        evidence_bundle = self._build_evidence(ctx, request)
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
                    step_id="reuse_workspace",
                    title="复用现有画像结果",
                    kind="answer_from_workspace",
                    user_visible_reason="当前问题是只读追问，优先复用已有画像结果。",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="确认已有结果是否足以回答当前问题。",
                ),
            ],
        )
        update_internal_trace_metadata(
            trace,
            {
                "flow_name": "AnswerWorkspaceFlow",
                "flow_mode": "workspace_answer",
            },
        )
        yield build_execution_plan_event(trace)

        if evidence_bundle is not None:
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="reuse_workspace",
                status="done",
                result_summary="已复用 session/tool_calls/workspace snapshot 中的画像结果，并装载证据回答上下文。",
            )
            final_message, confidence = answer_from_workspace_with_evidence(
                ctx.client,
                prompt=ctx.prompt,
                normalized_request=request,
                evidence_bundle=evidence_bundle,
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
            finalize_trace(ctx.session, trace, final_status="completed", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=ctx.prompt,
                final_message=final_message,
                confidence=confidence,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        yield update_trace_step(
            ctx.session,
            trace,
            step_id="reuse_workspace",
            status="blocked",
            result_summary="当前会话没有可复用的画像结果。",
        )
        review = build_no_workspace_review()
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
            extra_note="请先分析 UID 或恢复历史 workspace 后再继续追问。",
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

    def _build_evidence(self, ctx, request: NormalizedRequest) -> dict[str, Any] | None:
        return build_workspace_evidence_bundle(
            ctx.session,
            request,
            ctx.prompt,
            ctx.detected_country,
        )
