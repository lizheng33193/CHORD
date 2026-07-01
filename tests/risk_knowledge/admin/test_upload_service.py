from __future__ import annotations

from io import BytesIO

import pytest
from starlette.datastructures import UploadFile


def _seed_kb_and_document() -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import (
        SqlAlchemyKnowledgeBaseRepository,
        SqlAlchemyKnowledgeDocumentRepository,
    )
    from app.knowledge_base.schemas import (
        DocumentStatus,
        KnowledgeBase,
        KnowledgeBaseStatus,
        KnowledgeBaseType,
        KnowledgeDocument,
        PermissionScope,
        SourceType,
    )

    with AuthSessionLocal() as db:
        kb_repo = SqlAlchemyKnowledgeBaseRepository(db)
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        kb_repo.create(
            KnowledgeBase(
                kb_id="risk_domain_knowledge",
                kb_name="风控领域知识库",
                kb_type=KnowledgeBaseType.RISK_DOMAIN,
                description="Risk-domain document knowledge base for M2D.",
                status=KnowledgeBaseStatus.ACTIVE,
                index_alias="chord_m2d_risk_knowledge_active",
            )
        )
        doc_repo.create_document(
            KnowledgeDocument(
                doc_id="risk_guide",
                kb_id="risk_domain_knowledge",
                doc_title="智能风控指南",
                doc_name="risk_guide.txt",
                source_type=SourceType.TXT,
                source_uri="storage/risk/risk_guide.txt",
                current_version_id=None,
                status=DocumentStatus.INACTIVE,
                permission_scope=PermissionScope.INTERNAL,
            )
        )
        db.commit()


def test_upload_service_writes_file_and_registers_version_without_auto_index(auth_db, tmp_path, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.upload_service import KnowledgeDocumentUploadService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 1, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt", raising=False)
    _seed_kb_and_document()

    with AuthSessionLocal() as db:
        service = KnowledgeDocumentUploadService(db)
        result = service.upload_document_version(
            document_id="risk_guide",
            upload=UploadFile(filename="guide.txt", file=BytesIO(b"risk content")),
            version_label="v1",
            auto_index=False,
        )

        assert result.document_id == "risk_guide"
        assert result.filename == "guide.txt"
        assert result.indexing_job_id is None
        assert result.file_size_bytes == len(b"risk content")
        assert result.file_hash.startswith("sha256:")
        assert result.stored_path.startswith(str(tmp_path / "uploads"))


def test_upload_service_rejects_unsupported_extension(auth_db, tmp_path, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.errors import UnsupportedDocumentTypeAdminError
    from app.risk_knowledge.admin.upload_service import KnowledgeDocumentUploadService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 1, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt", raising=False)
    _seed_kb_and_document()

    with AuthSessionLocal() as db:
        service = KnowledgeDocumentUploadService(db)
        with pytest.raises(UnsupportedDocumentTypeAdminError):
            service.upload_document_version(
                document_id="risk_guide",
                upload=UploadFile(filename="guide.exe", file=BytesIO(b"risk content")),
                version_label="v1",
                auto_index=False,
            )


def test_upload_service_rejects_oversized_payload(auth_db, tmp_path, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.errors import DocumentTooLargeAdminError
    from app.risk_knowledge.admin.upload_service import KnowledgeDocumentUploadService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 0, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt", raising=False)
    _seed_kb_and_document()

    with AuthSessionLocal() as db:
        service = KnowledgeDocumentUploadService(db)
        with pytest.raises(DocumentTooLargeAdminError):
            service.upload_document_version(
                document_id="risk_guide",
                upload=UploadFile(filename="guide.txt", file=BytesIO(b"risk content")),
                version_label="v1",
                auto_index=False,
            )


def test_upload_service_auto_index_returns_job_id(auth_db, tmp_path, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.schemas import IndexingJobLaunchResponse
    from app.risk_knowledge.admin.upload_service import KnowledgeDocumentUploadService

    class StubIndexingService:
        def start_index(self, _version_id: str) -> IndexingJobLaunchResponse:
            return IndexingJobLaunchResponse(
                result="accepted",
                job_id="idxjob_auto",
                version_id="risk_guide_v1",
                status="pending",
                trigger="initial_index",
                latest_manifest_index_id=None,
                active_manifest_index_id=None,
            )

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 1, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt", raising=False)
    _seed_kb_and_document()

    with AuthSessionLocal() as db:
        service = KnowledgeDocumentUploadService(
            db,
            indexing_service_factory=lambda _db: StubIndexingService(),
        )
        result = service.upload_document_version(
            document_id="risk_guide",
            upload=UploadFile(filename="guide.txt", file=BytesIO(b"risk content")),
            version_label="v1",
            auto_index=True,
        )

        assert result.indexing_job_id == "idxjob_auto"


def test_upload_service_sanitizes_filename_and_confines_path(auth_db, tmp_path, monkeypatch) -> None:
    from pathlib import Path

    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.upload_service import KnowledgeDocumentUploadService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 1, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt", raising=False)
    _seed_kb_and_document()

    with AuthSessionLocal() as db:
        service = KnowledgeDocumentUploadService(db)
        result = service.upload_document_version(
            document_id="risk_guide",
            upload=UploadFile(filename="../guide?.txt", file=BytesIO(b"risk content")),
            version_label="v1",
            auto_index=False,
        )

        stored_path = Path(result.stored_path)
        assert stored_path.exists()
        assert stored_path.parent == (tmp_path / "uploads" / "risk_guide")
        assert stored_path.name.endswith("guide_.txt")
        assert all(not item.name.startswith(".upload_") for item in stored_path.parent.iterdir())
