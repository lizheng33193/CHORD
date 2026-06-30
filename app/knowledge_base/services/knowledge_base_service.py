"""Management-side services for knowledge-base metadata."""

from __future__ import annotations

from app.knowledge_base.config import (
    DEFAULT_RISK_INDEX_ALIAS,
    DEFAULT_RISK_KB_ID,
    DEFAULT_RISK_KB_NAME,
)
from app.knowledge_base.errors import KnowledgeBaseNotFoundError
from app.knowledge_base.repositories.interfaces import KnowledgeBaseRepository
from app.knowledge_base.schemas import KnowledgeBase, KnowledgeBaseStatus, KnowledgeBaseType


class KnowledgeBaseService:
    def __init__(self, repository: KnowledgeBaseRepository) -> None:
        self._repository = repository

    def ensure_default_risk_domain_knowledge_base(self) -> KnowledgeBase:
        existing = self._repository.get(DEFAULT_RISK_KB_ID)
        if existing is not None:
            return existing
        return self._repository.create(
            KnowledgeBase(
                kb_id=DEFAULT_RISK_KB_ID,
                kb_name=DEFAULT_RISK_KB_NAME,
                kb_type=KnowledgeBaseType.RISK_DOMAIN,
                description="Risk-domain document knowledge base for M2D.",
                status=KnowledgeBaseStatus.ACTIVE,
                index_alias=DEFAULT_RISK_INDEX_ALIAS,
            )
        )

    def create_knowledge_base(
        self,
        *,
        kb_id: str,
        kb_name: str,
        kb_type: KnowledgeBaseType,
        description: str | None,
        status: KnowledgeBaseStatus,
        index_alias: str,
    ) -> KnowledgeBase:
        return self._repository.create(
            KnowledgeBase(
                kb_id=kb_id,
                kb_name=kb_name,
                kb_type=kb_type,
                description=description,
                status=status,
                index_alias=index_alias,
            )
        )

    def get_knowledge_base(self, kb_id: str) -> KnowledgeBase:
        kb = self._repository.get(kb_id)
        if kb is None:
            raise KnowledgeBaseNotFoundError(f"knowledge base not found: {kb_id}")
        return kb

    def list_knowledge_bases(self) -> list[KnowledgeBase]:
        return self._repository.list()
