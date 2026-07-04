from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def _seed_manifest_baseline(tmp_path: Path) -> None:
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
    from app.risk_knowledge.indexing.schemas import FaissIndexManifest
    from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository

    file_path = tmp_path / "risk-guide.txt"
    file_path.write_text("risk knowledge body", encoding="utf-8")

    with AuthSessionLocal() as db:
        kb_repo = SqlAlchemyKnowledgeBaseRepository(db)
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        manifest_repo = SqlAlchemyFaissIndexRepository(db)

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
                current_version_id="risk_guide_v1",
                status=DocumentStatus.ACTIVE,
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
                status=DocumentVersionStatus.ACTIVE,
                latest_manifest_index_id="idx_manifest_new",
                active_manifest_index_id="idx_manifest_new",
                last_job_id="idxjob_new",
            )
        )
        manifest_repo.save_manifest(
            FaissIndexManifest(
                index_id="idx_manifest_old",
                kb_id="risk_domain_knowledge",
                version_id="risk_guide_v1",
                embedding_provider="deterministic_test",
                embedding_model="deterministic-v1",
                embedding_dimension=2,
                job_id="idxjob_old",
                index_type="flat_l2",
                distance_metric="l2",
                record_count=1,
                artifact_path="/tmp/old.index",
                mapping_path="/tmp/old.mapping.json",
                checksum="sha256:old",
                build_fingerprint="sha256:fingerprint-old",
                build_status="superseded",
                is_active=False,
                superseded_by_index_id="idx_manifest_new",
                superseded_at=datetime.now(UTC).replace(tzinfo=None),
                built_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        manifest_repo.save_manifest(
            FaissIndexManifest(
                index_id="idx_manifest_new",
                kb_id="risk_domain_knowledge",
                version_id="risk_guide_v1",
                embedding_provider="deterministic_test",
                embedding_model="deterministic-v1",
                embedding_dimension=2,
                job_id="idxjob_new",
                index_type="flat_l2",
                distance_metric="l2",
                record_count=1,
                artifact_path="/tmp/new.index",
                mapping_path="/tmp/new.mapping.json",
                checksum="sha256:new",
                build_fingerprint="sha256:fingerprint-new",
                build_status="active",
                is_active=True,
                superseded_by_index_id=None,
                superseded_at=None,
                built_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        manifest_repo.save_manifest(
            FaissIndexManifest(
                index_id="idx_manifest_failed",
                kb_id="risk_domain_knowledge",
                version_id="risk_guide_v1",
                embedding_provider="deterministic_test",
                embedding_model="deterministic-v1",
                embedding_dimension=2,
                job_id="idxjob_failed",
                index_type="flat_l2",
                distance_metric="l2",
                record_count=1,
                artifact_path="/tmp/failed.index",
                mapping_path="/tmp/failed.mapping.json",
                checksum="sha256:failed",
                build_fingerprint="sha256:fingerprint-failed",
                build_status="failed",
                is_active=False,
                superseded_by_index_id=None,
                superseded_at=None,
                built_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.commit()


def test_manifest_service_rolls_back_to_previous_active_manifest(auth_db, tmp_path) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.indexing.facade import RiskKnowledgeManifestFacade
    from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository

    _seed_manifest_baseline(tmp_path)

    with AuthSessionLocal() as db:
        service = RiskKnowledgeManifestFacade(db)
        rolled_back = service.rollback_manifest("idx_manifest_new")

        manifest_repo = SqlAlchemyFaissIndexRepository(db)
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        old_manifest = manifest_repo.get("idx_manifest_old")
        new_manifest = manifest_repo.get("idx_manifest_new")
        version = doc_repo.get_version("risk_guide_v1")

    assert rolled_back["manifest_id"] == "idx_manifest_old"
    assert old_manifest is not None and old_manifest.is_active is True
    assert new_manifest is not None and new_manifest.build_status == "rolled_back"
    assert version is not None and version.active_manifest_index_id == "idx_manifest_old"


def test_manifest_service_rejects_activation_of_failed_manifest(auth_db, tmp_path) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.indexing.facade import RiskKnowledgeManifestFacade

    _seed_manifest_baseline(tmp_path)

    with AuthSessionLocal() as db:
        service = RiskKnowledgeManifestFacade(db)
        try:
            service.activate_manifest("idx_manifest_failed")
        except ValueError as exc:
            assert "failed" in str(exc)
        else:
            raise AssertionError("expected activate_manifest to reject failed manifest")

