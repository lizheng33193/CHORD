"""Metadata-only document and version management services for M2D."""

from __future__ import annotations

from app.knowledge_base.errors import (
    InvalidKnowledgeBaseStateTransition,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentVersionNotFoundError,
)
from app.knowledge_base.lifecycle import assert_version_transition
from app.knowledge_base.repositories.interfaces import KnowledgeDocumentRepository
from app.knowledge_base.schemas import (
    DocumentStatus,
    DocumentVersionStatus,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    PermissionScope,
    SourceType,
)


class DocumentService:
    def __init__(self, repository: KnowledgeDocumentRepository) -> None:
        self._repository = repository

    def register_document(
        self,
        *,
        kb_id: str,
        doc_id: str,
        doc_title: str,
        doc_name: str,
        source_type: SourceType,
        source_uri: str,
        permission_scope: PermissionScope,
    ) -> KnowledgeDocument:
        return self._repository.create_document(
            KnowledgeDocument(
                doc_id=doc_id,
                kb_id=kb_id,
                doc_title=doc_title,
                doc_name=doc_name,
                source_type=source_type,
                source_uri=source_uri,
                current_version_id=None,
                status=DocumentStatus.INACTIVE,
                permission_scope=permission_scope,
            )
        )

    def create_document_version(
        self,
        *,
        version_id: str,
        doc_id: str,
        kb_id: str,
        version: str,
        file_hash: str,
        file_uri: str,
        parser_version: str | None,
        chunker_version: str | None,
        embedding_model: str | None,
        embedding_dim: int | None,
        index_name: str | None,
    ) -> KnowledgeDocumentVersion:
        if self._repository.get_document(doc_id) is None:
            raise KnowledgeDocumentNotFoundError(f"document not found: {doc_id}")
        return self._repository.create_version(
            KnowledgeDocumentVersion(
                version_id=version_id,
                doc_id=doc_id,
                kb_id=kb_id,
                version=version,
                file_hash=file_hash,
                file_uri=file_uri,
                parser_version=parser_version,
                chunker_version=chunker_version,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                index_name=index_name,
                status=DocumentVersionStatus.UPLOADED,
            )
        )

    def activate_version(self, version_id: str) -> KnowledgeDocumentVersion:
        version = self._get_version(version_id)
        if version.status not in {DocumentVersionStatus.INDEXED, DocumentVersionStatus.ACTIVE}:
            raise InvalidKnowledgeBaseStateTransition(
                f"document version must be indexed before activation: {version.status.value}"
            )
        document = self._get_document(version.doc_id)
        sibling_versions = self._repository.list_versions(version.doc_id)

        for sibling in sibling_versions:
            if sibling.version_id == version.version_id:
                continue
            if sibling.status == DocumentVersionStatus.ACTIVE:
                self._repository.update_version(
                    sibling.model_copy(update={"status": DocumentVersionStatus.DEPRECATED})
                )

        if version.status != DocumentVersionStatus.ACTIVE:
            assert_version_transition(version.status, DocumentVersionStatus.ACTIVE)
            version = self._repository.update_version(
                version.model_copy(update={"status": DocumentVersionStatus.ACTIVE})
            )

        document = self._repository.update_document(
            document.model_copy(
                update={
                    "current_version_id": version.version_id,
                    "status": DocumentStatus.ACTIVE,
                }
            )
        )
        return version

    def deprecate_version(self, version_id: str) -> KnowledgeDocumentVersion:
        version = self._get_version(version_id)
        if version.status != DocumentVersionStatus.DEPRECATED:
            assert_version_transition(version.status, DocumentVersionStatus.DEPRECATED)
            version = self._repository.update_version(
                version.model_copy(update={"status": DocumentVersionStatus.DEPRECATED})
            )
        document = self._get_document(version.doc_id)
        if document.current_version_id == version.version_id:
            self._repository.update_document(
                document.model_copy(
                    update={
                        "current_version_id": None,
                        "status": DocumentStatus.DEPRECATED,
                    }
                )
            )
        return version

    def list_documents(self, kb_id: str) -> list[KnowledgeDocument]:
        return self._repository.list_documents(kb_id)

    def list_versions(self, doc_id: str) -> list[KnowledgeDocumentVersion]:
        return self._repository.list_versions(doc_id)

    def transition_version(
        self,
        version_id: str,
        next_status: DocumentVersionStatus,
    ) -> KnowledgeDocumentVersion:
        version = self._get_version(version_id)
        if version.status == next_status:
            return version
        if next_status == DocumentVersionStatus.ACTIVE:
            return self.activate_version(version_id)
        assert_version_transition(version.status, next_status)
        return self._repository.update_version(
            version.model_copy(update={"status": next_status})
        )

    def _get_document(self, doc_id: str) -> KnowledgeDocument:
        document = self._repository.get_document(doc_id)
        if document is None:
            raise KnowledgeDocumentNotFoundError(f"document not found: {doc_id}")
        return document

    def _get_version(self, version_id: str) -> KnowledgeDocumentVersion:
        version = self._repository.get_version(version_id)
        if version is None:
            raise KnowledgeDocumentVersionNotFoundError(f"document version not found: {version_id}")
        return version
