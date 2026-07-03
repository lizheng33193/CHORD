from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def _seed_version_and_manifest(tmp_path: Path, *, active_manifest_id: str) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository
    from app.knowledge_base.schemas import (
        DocumentStatus,
        DocumentVersionStatus,
        KnowledgeDocument,
        KnowledgeDocumentVersion,
        PermissionScope,
        SourceType,
    )
    from app.risk_knowledge.indexing.schemas import FaissIndexManifest
    from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository

    upload_path = tmp_path / "uploads" / "risk_guide" / "risk_guide.txt"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_text("risk knowledge body", encoding="utf-8")

    active_faiss = tmp_path / "faiss" / f"{active_manifest_id}.faiss"
    active_mapping = tmp_path / "faiss" / f"{active_manifest_id}.mapping.json"
    active_faiss.parent.mkdir(parents=True, exist_ok=True)
    active_faiss.write_text("active", encoding="utf-8")
    active_mapping.write_text("{}", encoding="utf-8")

    inactive_faiss = tmp_path / "faiss" / "idx_manifest_old.faiss"
    inactive_mapping = tmp_path / "faiss" / "idx_manifest_old.mapping.json"
    inactive_faiss.write_text("old", encoding="utf-8")
    inactive_mapping.write_text("{}", encoding="utf-8")

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        manifest_repo = SqlAlchemyFaissIndexRepository(db)
        doc_repo.create_document(
            KnowledgeDocument(
                doc_id="risk_guide",
                kb_id="risk_domain_knowledge",
                doc_title="智能风控指南",
                doc_name="risk_guide.txt",
                source_type=SourceType.TXT,
                source_uri=str(upload_path),
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
                file_hash="sha256:file",
                file_uri=str(upload_path),
                parser_version="swxy-parser-v1",
                chunker_version="chunker-v1",
                embedding_model="deterministic-v1",
                embedding_dim=2,
                index_name=None,
                status=DocumentVersionStatus.ACTIVE,
                latest_manifest_index_id=active_manifest_id,
                active_manifest_index_id=active_manifest_id,
                last_job_id="idxjob_active",
            )
        )
        manifest_repo.save_manifest(
            FaissIndexManifest(
                index_id=active_manifest_id,
                kb_id="risk_domain_knowledge",
                version_id="risk_guide_v1",
                embedding_provider="deterministic_test",
                embedding_model="deterministic-v1",
                embedding_dimension=2,
                job_id="idxjob_active",
                index_type="flat_l2",
                distance_metric="l2",
                record_count=1,
                artifact_path=str(active_faiss),
                mapping_path=str(active_mapping),
                checksum="sha256:active",
                build_fingerprint="sha256:active",
                build_status="active",
                is_active=True,
                superseded_by_index_id=None,
                superseded_at=None,
                built_at=datetime.now(UTC).replace(tzinfo=None),
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
                artifact_path=str(inactive_faiss),
                mapping_path=str(inactive_mapping),
                checksum="sha256:old",
                build_fingerprint="sha256:old",
                build_status="superseded",
                is_active=False,
                superseded_by_index_id=active_manifest_id,
                superseded_at=datetime.now(UTC).replace(tzinfo=None),
                built_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.commit()


def test_artifact_cleanup_dry_run_protects_active_manifest_and_version_upload(auth_db, tmp_path, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.artifact_cleanup_service import ArtifactCleanupService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_faiss_artifact_dir", str(tmp_path / "faiss"), raising=False)

    _seed_version_and_manifest(tmp_path, active_manifest_id="idx_manifest_active")

    with AuthSessionLocal() as db:
        report = ArtifactCleanupService(db).cleanup(dry_run=True)

    candidate_paths = {item.path for item in report.candidates}
    protected_paths = {item.path: item.reason for item in report.protected}

    assert str(tmp_path / "faiss" / "idx_manifest_old.faiss") in candidate_paths
    assert str(tmp_path / "faiss" / "idx_manifest_old.mapping.json") in candidate_paths
    assert protected_paths[str(tmp_path / "faiss" / "idx_manifest_active.faiss")] == "active_manifest"
    assert protected_paths[str(tmp_path / "uploads" / "risk_guide" / "risk_guide.txt")] == "version_upload"


def test_artifact_cleanup_dry_run_lists_temporary_artifacts(auth_db, tmp_path, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.artifact_cleanup_service import ArtifactCleanupService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_faiss_artifact_dir", str(tmp_path / "faiss"), raising=False)

    _seed_version_and_manifest(tmp_path, active_manifest_id="idx_manifest_active")
    temp_path = tmp_path / "faiss" / "idx_manifest_building.faiss.tmp"
    temp_path.write_text("tmp", encoding="utf-8")

    with AuthSessionLocal() as db:
        report = ArtifactCleanupService(db).cleanup(dry_run=True)

    reasons_by_path = {item.path: item.reason for item in report.candidates}
    assert reasons_by_path[str(temp_path)] == "temporary_artifact"


def test_artifact_cleanup_rejects_unmanaged_root(auth_db, tmp_path, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.artifact_cleanup_service import ArtifactCleanupService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"), raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_faiss_artifact_dir", str(tmp_path / "faiss"), raising=False)

    with AuthSessionLocal() as db:
        service = ArtifactCleanupService(db)
        try:
            service.cleanup(dry_run=True, root=str(tmp_path / "elsewhere"))
        except ValueError as exc:
            assert "unmanaged cleanup root" in str(exc)
        else:
            raise AssertionError("expected unmanaged cleanup root to be rejected")
