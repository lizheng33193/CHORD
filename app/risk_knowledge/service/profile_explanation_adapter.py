"""Adapter that turns profile facts into risk knowledge explanation queries."""

from __future__ import annotations

from app.risk_knowledge.service.errors import ProfileExplanationAdapterError
from app.risk_knowledge.service.schemas import (
    ProfileExplanationRequest,
    RiskKnowledgeAnswer,
    RiskKnowledgeQuery,
)


class ProfileExplanationAdapter:
    def __init__(self, *, service) -> None:
        self._service = service

    def explain(self, request: ProfileExplanationRequest) -> RiskKnowledgeAnswer:
        facts = [str(item).strip() for item in request.profile_facts if str(item).strip()]
        if not facts:
            raise ProfileExplanationAdapterError("profile_facts must not be empty")
        query = RiskKnowledgeQuery(
            query="请基于风控领域知识解释以下画像事实为什么可能表示风险：" + "；".join(facts),
            kb_id=request.kb_id,
            user_id=request.user_id,
            intent="profile_explanation",
            source=request.source,
            answer_style=request.answer_style,
        )
        return self._service.answer(query)
