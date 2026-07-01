"""Grounded answer synthesizer abstractions for risk knowledge service."""

from __future__ import annotations

from typing import Protocol

from app.risk_knowledge.service.errors import GroundedAnswerSynthesisError
from app.risk_knowledge.service.schemas import GroundedAnswerRequest, GroundedAnswerResult


class AnswerSynthesizer(Protocol):
    def synthesize(self, request: GroundedAnswerRequest) -> GroundedAnswerResult:
        ...


class DeterministicAnswerSynthesizer:
    """Offline-safe synthesizer used by default in tests and deterministic runtime."""

    provider = "deterministic"
    model = "deterministic-answer-v1"

    def synthesize(self, request: GroundedAnswerRequest) -> GroundedAnswerResult:
        if not request.evidence_context.evidence_items:
            raise GroundedAnswerSynthesisError("evidence context must not be empty")
        lines = []
        used_citation_ids: list[str] = []
        for item in request.evidence_context.evidence_items:
            used_citation_ids.append(item.citation_id)
            lines.append(f"{item.text}[{item.citation_id}]")
        prefix = "根据已检索到的风控资料，" if request.answer_style == "concise" else "基于当前知识库证据，可以整理出以下结论："
        answer = prefix + " ".join(lines)
        return GroundedAnswerResult(
            answer=answer,
            used_citation_ids=used_citation_ids,
            provider=self.provider,
            model=self.model,
        )
