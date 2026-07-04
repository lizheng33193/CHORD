"""Controlled answer generation for PR-A Risk QA."""

from __future__ import annotations

from app.risk_knowledge.service.answer_synthesizer import AnswerSynthesizer, DeterministicAnswerSynthesizer
from app.risk_knowledge.service.schemas import EvidenceContext, GroundedAnswerRequest, GroundedAnswerResult


class RiskQaAnswerGenerator:
    def __init__(self, *, synthesizer: AnswerSynthesizer | None = None) -> None:
        self._synthesizer = synthesizer or DeterministicAnswerSynthesizer()

    def generate(
        self,
        *,
        query: str,
        evidence_context: EvidenceContext,
        answer_style: str,
        grounding_status: str,
    ) -> GroundedAnswerResult:
        result = self._synthesizer.synthesize(
            GroundedAnswerRequest(
                query=query,
                evidence_context=evidence_context,
                answer_style=answer_style,  # type: ignore[arg-type]
                language="zh",
            )
        )
        if grounding_status == "partial":
            result = result.model_copy(
                update={
                    "answer": f"当前知识库只支持部分解释，以下内容仅基于已召回证据：{result.answer}",
                }
            )
        return result
