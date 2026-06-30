"""Repository interfaces and in-memory implementations for M2D knowledge-base skeleton."""

from app.knowledge_base.repositories.interfaces import (
    KnowledgeBaseRepository,
    KnowledgeDocumentRepository,
    KnowledgeIngestJobRepository,
)
from app.knowledge_base.repositories.memory import (
    InMemoryKnowledgeBaseRepository,
    InMemoryKnowledgeDocumentRepository,
    InMemoryKnowledgeIngestJobRepository,
)
from app.knowledge_base.repositories.sqlalchemy import (
    SqlAlchemyKnowledgeDocumentRepository,
    SqlAlchemyKnowledgeIngestJobRepository,
)

__all__ = [
    "InMemoryKnowledgeBaseRepository",
    "InMemoryKnowledgeDocumentRepository",
    "InMemoryKnowledgeIngestJobRepository",
    "SqlAlchemyKnowledgeDocumentRepository",
    "SqlAlchemyKnowledgeIngestJobRepository",
    "KnowledgeBaseRepository",
    "KnowledgeDocumentRepository",
    "KnowledgeIngestJobRepository",
]
