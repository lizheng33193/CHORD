from __future__ import annotations

from io import BytesIO

from starlette.datastructures import UploadFile


def test_admin_service_supports_kb_document_and_version_aggregation(auth_db, tmp_path, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.service import KnowledgeBaseAdminService
    from app.risk_knowledge.admin.upload_service import KnowledgeDocumentUploadService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 1, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt", raising=False)

    with AuthSessionLocal() as db:
        admin_service = KnowledgeBaseAdminService(db)
        upload_service = KnowledgeDocumentUploadService(db)

        created_kb = admin_service.create_kb(
            kb_id="risk_domain_knowledge",
            name="风控领域知识库",
            description="用于画像解释的风控知识资料",
        )
        assert created_kb.document_count == 0

        created_document = admin_service.create_document(
            kb_id=created_kb.kb_id,
            title="智能风控指南",
            source_type="manual",
            source_uri=None,
        )
        assert created_document.kb_id == created_kb.kb_id
        assert created_document.version_count == 0

        uploaded = upload_service.upload_document_version(
            document_id=created_document.document_id,
            upload=UploadFile(filename="risk-guide.txt", file=BytesIO(b"risk knowledge body")),
            version_label="v1",
            auto_index=False,
        )
        assert uploaded.version_id

        kb_detail = admin_service.get_kb(created_kb.kb_id)
        assert kb_detail.document_count == 1

        document_detail = admin_service.get_document(created_document.document_id)
        assert document_detail.version_count == 1
        assert document_detail.active_version_id is None

        version_detail = admin_service.get_version(uploaded.version_id)
        assert version_detail.version_id == uploaded.version_id
        assert version_detail.version_label == "v1"
        assert version_detail.file_hash == uploaded.file_hash
        assert version_detail.file_uri == uploaded.stored_path

        version_items = admin_service.list_versions(created_document.document_id)
        assert [item.version_id for item in version_items] == [uploaded.version_id]
