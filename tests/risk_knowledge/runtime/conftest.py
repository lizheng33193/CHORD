from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge_base.schemas import (
    DocumentStatus,
    DocumentVersionStatus,
    IndexingJobStatus,
    PermissionScope,
    SourceType,
)
from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-m2d9", raising=False)
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


@pytest.fixture()
def fake_redis_client():
    import fakeredis

    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def sample_document():
    from app.knowledge_base.schemas import KnowledgeDocument

    return KnowledgeDocument(
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        current_version_id=None,
        status=DocumentStatus.INACTIVE,
        permission_scope=PermissionScope.INTERNAL,
    )


@pytest.fixture()
def sample_version():
    from app.knowledge_base.schemas import KnowledgeDocumentVersion

    return KnowledgeDocumentVersion(
        version_id="risk_guide_202607",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-07",
        file_hash="sha256:file",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy-parser-v1",
        chunker_version="chunker-v1",
        embedding_model="deterministic-v1",
        embedding_dim=2,
        index_name=None,
        status=DocumentVersionStatus.PARSED,
        latest_manifest_index_id=None,
        active_manifest_index_id=None,
        last_job_id=None,
    )


@pytest.fixture()
def sample_parsed_document():
    return ParsedDocument(
        source=SourceDocumentRef(
            kb_id="risk_domain_knowledge",
            doc_id="risk_guide",
            version_id="risk_guide_202607",
            file_path="/tmp/risk_guide.pdf",
            doc_name="risk_guide.pdf",
            source_type=SourceType.PDF,
        ),
        parser_name="swxy-compatible",
        parser_version="swxy-parser-v1",
        raw_chunks=[
            RawParsedChunk(
                chunk_order=1,
                raw_content="贷后风险识别是指...",
                chunk_type="paragraph",
                title="贷后风险识别",
                section_title="贷后风险识别",
                section_path=["智能风控指南", "贷后风险识别"],
                page_start=12,
                page_end=12,
                position={"page": 12},
                source_metadata={"raw_chunk_type": "raw_paragraph"},
            ),
            RawParsedChunk(
                chunk_order=2,
                raw_content="风险预警需要结合行为信号。",
                chunk_type="paragraph",
                title="风险预警",
                section_title="风险预警",
                section_path=["智能风控指南", "风险预警"],
                page_start=13,
                page_end=13,
                position={"page": 13},
                source_metadata={"raw_chunk_type": "raw_paragraph"},
            ),
        ],
        document_metadata={"language": "zh"},
    )


@pytest.fixture()
def sample_job():
    from app.knowledge_base.schemas import IndexingJobTrigger, KnowledgeIngestJob

    return KnowledgeIngestJob(
        job_id="idxjob_sample",
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        status=IndexingJobStatus.PENDING,
        current_step="queued",
        error_message=None,
        trigger=IndexingJobTrigger.INITIAL_INDEX,
        attempt=1,
        max_attempts=3,
        root_job_id="idxjob_sample",
        retry_of_job_id=None,
        started_at=None,
        completed_at=None,
        last_heartbeat_at=None,
        latest_manifest_index_id=None,
        active_manifest_index_id=None,
    )
