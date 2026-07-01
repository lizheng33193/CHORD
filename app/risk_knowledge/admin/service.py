"""Admin-side knowledge base service for M2D-14A."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.knowledge_base.id_factory import build_doc_id
from app.knowledge_base.errors import (
    DuplicateKnowledgeBaseError,
    KnowledgeBaseNotFoundError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentVersionNotFoundError,
)
from app.knowledge_base.repositories.sqlalchemy import (
    SqlAlchemyKnowledgeBaseRepository,
    SqlAlchemyKnowledgeDocumentRepository,
)
from app.knowledge_base.schemas import (
    DocumentStatus,
    KnowledgeBaseStatus,
    KnowledgeBaseType,
    PermissionScope,
    SourceType,
)
from app.knowledge_base.services.document_service import DocumentService
from app.knowledge_base.services.knowledge_base_service import KnowledgeBaseService
from app.risk_knowledge.admin.errors import (
    KnowledgeBaseAlreadyExistsAdminError,
    KnowledgeBaseMissingAdminError,
    KnowledgeDocumentAlreadyExistsAdminError,
    KnowledgeDocumentMissingAdminError,
    KnowledgeDocumentVersionMissingAdminError,
)
from app.risk_knowledge.admin.schemas import (
    DocumentSummaryResponse,
    KnowledgeBaseSummaryResponse,
    VersionSummaryResponse,
)


class KnowledgeBaseAdminService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._kb_repo = SqlAlchemyKnowledgeBaseRepository(db)
        self._doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        self._kb_service = KnowledgeBaseService(self._kb_repo)
        self._document_service = DocumentService(self._doc_repo)

    def create_kb(
        self,
        *,
        kb_id: str,
        name: str,
        description: str | None,
    ) -> KnowledgeBaseSummaryResponse:
        try:
            kb = self._kb_service.create_knowledge_base(
                kb_id=kb_id,
                kb_name=name,
                kb_type=KnowledgeBaseType.RISK_DOMAIN,
                description=description,
                status=KnowledgeBaseStatus.ACTIVE,
                index_alias=f"{kb_id}_active",
            )
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise KnowledgeBaseAlreadyExistsAdminError(
                "knowledge base already exists",
                resource_id=kb_id,
            ) from exc
        except DuplicateKnowledgeBaseError as exc:
            self._db.rollback()
            raise KnowledgeBaseAlreadyExistsAdminError(
                "knowledge base already exists",
                resource_id=kb_id,
            ) from exc
        return self._build_summary(kb.kb_id)

    def list_kbs(self) -> list[KnowledgeBaseSummaryResponse]:
        return [self._build_summary(item.kb_id) for item in self._kb_service.list_knowledge_bases()]

    def get_kb(self, kb_id: str) -> KnowledgeBaseSummaryResponse:
        try:
            self._kb_service.get_knowledge_base(kb_id)
        except KnowledgeBaseNotFoundError as exc:
            raise KnowledgeBaseMissingAdminError(
                "knowledge base not found",
                resource_id=kb_id,
            ) from exc
        return self._build_summary(kb_id)

    def create_document(
        self,
        *,
        kb_id: str,
        title: str,
        source_type: str,
        source_uri: str | None,
    ) -> DocumentSummaryResponse:
        self.get_kb(kb_id)
        doc_id = self._build_unique_doc_id(title)
        try:
            document = self._document_service.register_document(
                kb_id=kb_id,
                doc_id=doc_id,
                doc_title=title,
                doc_name=title,
                source_type=SourceType.UNKNOWN,
                source_uri=source_uri or f"admin://documents/{doc_id}",
                permission_scope=PermissionScope.INTERNAL,
            )
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise KnowledgeDocumentAlreadyExistsAdminError(
                "knowledge document already exists",
                resource_id=doc_id,
            ) from exc
        return self._build_document_summary(document.doc_id)

    def list_documents(self, kb_id: str) -> list[DocumentSummaryResponse]:
        self.get_kb(kb_id)
        return [self._build_document_summary(item.doc_id) for item in self._document_service.list_documents(kb_id)]

    def get_document(self, document_id: str) -> DocumentSummaryResponse:
        try:
            document = self._document_service._get_document(document_id)  # noqa: SLF001 - localized admin seam
        except KnowledgeDocumentNotFoundError as exc:
            raise KnowledgeDocumentMissingAdminError(
                "knowledge document not found",
                resource_id=document_id,
            ) from exc
        return self._build_document_summary(document.doc_id)

    def list_versions(self, document_id: str) -> list[VersionSummaryResponse]:
        try:
            self._document_service._get_document(document_id)  # noqa: SLF001 - localized admin seam
        except KnowledgeDocumentNotFoundError as exc:
            raise KnowledgeDocumentMissingAdminError(
                "knowledge document not found",
                resource_id=document_id,
            ) from exc
        return [self._build_version_summary(item.version_id) for item in self._document_service.list_versions(document_id)]

    def get_version(self, version_id: str) -> VersionSummaryResponse:
        try:
            version = self._document_service._get_version(version_id)  # noqa: SLF001 - localized admin seam
        except KnowledgeDocumentVersionNotFoundError as exc:
            raise KnowledgeDocumentVersionMissingAdminError(
                "knowledge document version not found",
                resource_id=version_id,
            ) from exc
        return self._build_version_summary(version.version_id)

    def _build_summary(self, kb_id: str) -> KnowledgeBaseSummaryResponse:
        kb = self._kb_service.get_knowledge_base(kb_id)
        documents = self._doc_repo.list_documents(kb_id)
        active_document_count = sum(1 for item in documents if item.status == DocumentStatus.ACTIVE)
        return KnowledgeBaseSummaryResponse(
            kb_id=kb.kb_id,
            name=kb.kb_name,
            description=kb.description,
            status=kb.status.value,
            document_count=len(documents),
            active_document_count=active_document_count,
        )

    def _build_document_summary(self, document_id: str) -> DocumentSummaryResponse:
        document = self._document_service._get_document(document_id)  # noqa: SLF001 - localized admin seam
        versions = self._document_service.list_versions(document_id)
        return DocumentSummaryResponse(
            document_id=document.doc_id,
            kb_id=document.kb_id,
            title=document.doc_title,
            source_type=document.source_type.value,
            status=document.status.value,
            version_count=len(versions),
            active_version_id=document.current_version_id,
        )

    def _build_version_summary(self, version_id: str) -> VersionSummaryResponse:
        version = self._document_service._get_version(version_id)  # noqa: SLF001 - localized admin seam
        return VersionSummaryResponse(
            version_id=version.version_id,
            document_id=version.doc_id,
            version_label=version.version,
            file_hash=version.file_hash,
            file_uri=version.file_uri,
            status=version.status.value,
            last_job_id=version.last_job_id,
            active_manifest_index_id=version.active_manifest_index_id,
            latest_manifest_index_id=version.latest_manifest_index_id,
        )

    def _build_unique_doc_id(self, title: str) -> str:
        candidate = build_doc_id(title)
        existing = self._doc_repo.get_document(candidate)
        if existing is None:
            return candidate
        return f"{candidate}_{uuid4().hex[:8]}"
