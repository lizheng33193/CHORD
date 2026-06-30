from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge_base.schemas import ChunkStatus, DocumentVersionStatus, KnowledgeChunk, KnowledgeDocumentVersion, PermissionScope, SourceType


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-m2d8", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)

    from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    yield

    reset_auth_engine()


def _build_version() -> KnowledgeDocumentVersion:
    return KnowledgeDocumentVersion(
        version_id="risk_guide_202607",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-07",
        file_hash="sha256:file",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy-parser-v1",
        chunker_version="chunker-v1",
        embedding_model=None,
        embedding_dim=None,
        index_name=None,
        status=DocumentVersionStatus.PARSED,
    )


def _build_chunk(*, content_hash: str = "sha256:content") -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id="risk_guide_202607_chunk_000001",
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        chunk_order=1,
        chunk_type="paragraph",
        section_title="贷后风险识别",
        section_path=["智能风控指南", "贷后风险识别"],
        page_start=12,
        page_end=12,
        content="贷后风险识别是指...",
        content_hash=content_hash,
        status=ChunkStatus.PENDING,
        permission_scope=PermissionScope.INTERNAL,
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        source_metadata={"doc_name": "risk_guide.pdf"},
    )


def test_persist_chunks_is_idempotent_for_same_identity_and_content_hash(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.persistence.service import KnowledgeChunkPersistenceService

    with AuthSessionLocal() as db:
        service = KnowledgeChunkPersistenceService(db)

        first = service.persist_chunks(_build_version(), [_build_chunk()])
        second = service.persist_chunks(_build_version(), [_build_chunk()])

        assert len(first.records) == 1
        assert len(second.records) == 1
        assert first.records[0].chunk_id == second.records[0].chunk_id
        assert first.records[0].id == second.records[0].id


def test_persist_chunks_rejects_same_chunk_id_with_different_content_hash(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.persistence.errors import ChunkContentConflictError
    from app.risk_knowledge.persistence.service import KnowledgeChunkPersistenceService

    with AuthSessionLocal() as db:
        service = KnowledgeChunkPersistenceService(db)
        service.persist_chunks(_build_version(), [_build_chunk(content_hash="sha256:one")])

        with pytest.raises(ChunkContentConflictError):
            service.persist_chunks(_build_version(), [_build_chunk(content_hash="sha256:two")])


def test_persisted_chunk_records_keep_chunk_metadata_without_embedding_fields(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.persistence.models import KnowledgeChunkEmbeddingRecord, KnowledgeChunkRecord
    from app.risk_knowledge.persistence.service import KnowledgeChunkPersistenceService
    from sqlalchemy import select

    with AuthSessionLocal() as db:
        service = KnowledgeChunkPersistenceService(db)
        result = service.persist_chunks(_build_version(), [_build_chunk()])

        stored = db.scalar(select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.chunk_id == result.records[0].chunk_id))
        embedding_rows = list(db.scalars(select(KnowledgeChunkEmbeddingRecord)).all())

        assert stored is not None
        assert stored.chunk_id == "risk_guide_202607_chunk_000001"
        assert stored.content_hash == "sha256:content"
        assert stored.metadata_json["source_metadata"]["doc_name"] == "risk_guide.pdf"
        assert stored.token_count is None
        assert embedding_rows == []
