"""Known flow for M2D-12 risk knowledge answers."""

from __future__ import annotations

import uuid
from typing import AsyncIterator

from app.knowledge_base.config import DEFAULT_RISK_KB_ID
from app.risk_knowledge.service import build_risk_knowledge_service_from_settings
from app.risk_knowledge.service.errors import RiskKnowledgeServiceError
from app.risk_knowledge.service.schemas import RiskKnowledgeQuery
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.trace_store import (
    build_execution_plan_event,
    create_execution_trace,
    finalize_trace,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import NormalizedRequest, PlanStep


class RiskKnowledgeAnswerFlow:
    intent = "risk_knowledge_answer"

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        return request.intent == self.intent and not request.uids and request.query_request is None

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[dict[str, object]]:
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
                    step_id="answer_risk_knowledge",
                    title="回答风控知识问题",
                    kind="risk_knowledge_answer",
                    user_visible_reason="当前问题是明确的风控知识解释请求，进入风险知识服务回答。",
                ),
            ],
        )
        update_internal_trace_metadata(
            trace,
            {
                "flow_name": "RiskKnowledgeAnswerFlow",
                "flow_mode": "risk_knowledge_answer",
            },
        )
        yield build_execution_plan_event(trace)

        service = build_risk_knowledge_service_from_settings()
        service_query = RiskKnowledgeQuery(
            query=ctx.prompt,
            kb_id=DEFAULT_RISK_KB_ID,
            user_id=(ctx.user_context.user_id if ctx.user_context else None),
            session_id=ctx.session.session_id,
            intent="risk_knowledge_qa",
            source="nl_chat",
        )
        try:
            answer = service.answer(service_query)
        except RiskKnowledgeServiceError:
            final_message = "风险知识服务暂时不可用，请稍后重试。"
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="answer_risk_knowledge",
                status="failed",
                result_summary="风险知识服务执行失败。",
            )
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
            return

        result_summary = (
            "已基于风控知识证据生成回答。"
            if answer.should_answer
            else "当前证据不足，已返回风控知识拒答结果。"
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="answer_risk_knowledge",
            status="done",
            result_summary=result_summary,
        )
        finalize_trace(ctx.session, trace, final_status="completed", final_message=answer.answer)
        confidence = float(answer.evidence_bundle.gate_decision.confidence if answer.should_answer else 0.0)
        yield persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=answer.answer,
            confidence=confidence,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )
