from __future__ import annotations

from pathlib import Path


def _seed_version(tmp_path: Path) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import (
        SqlAlchemyKnowledgeBaseRepository,
        SqlAlchemyKnowledgeDocumentRepository,
    )
    from app.knowledge_base.schemas import (
        DocumentStatus,
        DocumentVersionStatus,
        KnowledgeBase,
        KnowledgeBaseStatus,
        KnowledgeBaseType,
        KnowledgeDocument,
        KnowledgeDocumentVersion,
        PermissionScope,
        SourceType,
    )

    file_path = tmp_path / "risk-guide.txt"
    file_path.write_text("risk knowledge body", encoding="utf-8")

    with AuthSessionLocal() as db:
        kb_repo = SqlAlchemyKnowledgeBaseRepository(db)
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        kb_repo.create(
            KnowledgeBase(
                kb_id="risk_domain_knowledge",
                kb_name="风控领域知识库",
                kb_type=KnowledgeBaseType.RISK_DOMAIN,
                description="用于画像解释的风控知识资料",
                status=KnowledgeBaseStatus.ACTIVE,
                index_alias="risk_domain_knowledge_active",
            )
        )
        doc_repo.create_document(
            KnowledgeDocument(
                doc_id="risk_guide",
                kb_id="risk_domain_knowledge",
                doc_title="智能风控指南",
                doc_name="risk-guide.txt",
                source_type=SourceType.TXT,
                source_uri=str(file_path),
                current_version_id=None,
                status=DocumentStatus.INACTIVE,
                permission_scope=PermissionScope.INTERNAL,
            )
        )
        doc_repo.create_version(
            KnowledgeDocumentVersion(
                version_id="risk_guide_v1",
                doc_id="risk_guide",
                kb_id="risk_domain_knowledge",
                version="v1",
                file_hash="sha256:test",
                file_uri=str(file_path),
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
        )
        db.commit()


def test_submit_job_reuses_existing_job_for_same_idempotency_key(auth_db, tmp_path) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRepository
    from app.knowledge_base.services.ingest_job_service import IngestJobService
    from app.risk_knowledge.indexing.facade import RiskKnowledgeIndexingFacade

    _seed_version(tmp_path)

    with AuthSessionLocal() as db:
        service = RiskKnowledgeIndexingFacade(db)
        first = service.submit_job(version_id="risk_guide_v1", idempotency_key="idem-1")
        second = service.submit_job(version_id="risk_guide_v1", idempotency_key="idem-1")

    assert first["job_id"] == second["job_id"]
    assert first["idempotency_key"] == "idem-1"

    with AuthSessionLocal() as db:
        repo = SqlAlchemyKnowledgeIngestJobRepository(db)
        IngestJobService(repo).fail_job(first["job_id"], "boom")
        db.commit()

    with AuthSessionLocal() as db:
        third = RiskKnowledgeIndexingFacade(db).submit_job(version_id="risk_guide_v1", idempotency_key="idem-2")

    assert third["job_id"] != first["job_id"]
