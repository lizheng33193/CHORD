"""Known flow for M2D-12 risk knowledge answers."""

from __future__ import annotations

import hashlib
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

        update_internal_trace_metadata(
            trace,
            {
                "context_hash": _resolve_context_hash(answer),
                "retrieval_snapshot_id": _resolve_retrieval_snapshot_id(answer),
                "selected_evidence_ids": _resolve_selected_evidence_ids(answer),
                "selected_chunk_ids": _resolve_selected_chunk_ids(answer),
                "blocked_context_sources": list(answer.blocked_context_sources),
                "grounding_status": answer.grounding_status,
                "warning_codes": [warning.code for warning in answer.warnings],
                "citation_count": len(answer.citations),
                "evidence_count": len(_resolve_selected_evidence_ids(answer)),
            },
        )
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
            artifacts=[_build_risk_knowledge_artifact(answer)],
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )


def _build_risk_knowledge_artifact(answer) -> dict[str, object]:
    return {
        "type": answer.type,
        "schema_version": answer.schema_version,
        "query": answer.query,
        "answer": answer.answer,
        "answer_type": answer.answer_type,
        "grounding_status": answer.grounding_status,
        "citations": [citation.model_dump(mode="json") for citation in answer.citations],
        "evidence_trace": [item.model_dump(mode="json") for item in answer.evidence_trace],
        "retrieval_snapshot_id": _resolve_retrieval_snapshot_id(answer),
        "blocked_context_sources": list(answer.blocked_context_sources),
        "context_hash": _resolve_context_hash(answer),
        "warnings": [warning.model_dump(mode="json") for warning in answer.warnings],
    }


def _resolve_selected_evidence_ids(answer) -> list[str]:
    if answer.evidence_trace:
        return [item.evidence_id for item in answer.evidence_trace]
    return [item.evidence_id for item in answer.evidence_bundle.selected_evidence]


def _resolve_selected_chunk_ids(answer) -> list[str]:
    if answer.evidence_trace:
        return [item.chunk_id for item in answer.evidence_trace if item.chunk_id]
    return [item.chunk_id for item in answer.evidence_bundle.selected_evidence if item.chunk_id]


def _resolve_context_hash(answer) -> str:
    if answer.context_hash:
        return answer.context_hash
    payload = "::".join(
        [
            answer.query,
            ",".join(sorted(_resolve_selected_evidence_ids(answer))),
            ",".join(sorted(answer.blocked_context_sources)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_retrieval_snapshot_id(answer) -> str:
    if answer.retrieval_snapshot_id:
        return answer.retrieval_snapshot_id
    payload = "::".join([answer.query, ",".join(_resolve_selected_chunk_ids(answer))])
    return f"rqs_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"
