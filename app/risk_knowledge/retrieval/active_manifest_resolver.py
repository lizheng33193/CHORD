"""Active retrieval scope resolution for M2D-10."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository
from app.knowledge_base.schemas import DocumentVersionStatus
from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository
from app.risk_knowledge.retrieval.errors import (
    InactiveManifestError,
    InvalidRetrievalScopeError,
    NoActiveManifestError,
    NoActiveRetrievalScopeError,
    RetrievalDocumentVersionMismatchError,
    RetrievalScopeEmbeddingMismatchError,
)
from app.risk_knowledge.retrieval.schemas import (
    ActiveRetrievalManifest,
    ActiveRetrievalScope,
    RetrievalQuery,
    RetrievalScopeType,
)


class ActiveManifestResolver:
    def __init__(self, db: Session) -> None:
        self._documents = SqlAlchemyKnowledgeDocumentRepository(db)
        self._manifests = SqlAlchemyFaissIndexRepository(db)

    def resolve_scope(self, query: RetrievalQuery) -> ActiveRetrievalScope:
        if query.version_id:
            version = self._require_active_version(query.version_id, kb_id=query.kb_id)
            if query.document_id and version.doc_id != query.document_id:
                raise RetrievalDocumentVersionMismatchError(
                    f"version_id={query.version_id} does not belong to document_id={query.document_id}"
                )
            manifest = self._require_active_manifest(version.active_manifest_index_id, version.doc_id, version.version_id)
            return self._build_scope(
                scope_type=RetrievalScopeType.EXPLICIT_VERSION,
                kb_id=query.kb_id,
                document_id=version.doc_id,
                version_id=version.version_id,
                manifests=[manifest],
            )

        if query.document_id:
            document = self._documents.get_document(query.document_id)
            if document is None or document.kb_id != query.kb_id:
                raise InvalidRetrievalScopeError(f"document_id={query.document_id} not found in kb_id={query.kb_id}")
            if not document.current_version_id:
                raise NoActiveRetrievalScopeError(
                    f"document_id={query.document_id} does not have a current active version"
                )
            version = self._require_active_version(document.current_version_id, kb_id=query.kb_id)
            manifest = self._require_active_manifest(version.active_manifest_index_id, version.doc_id, version.version_id)
            return self._build_scope(
                scope_type=RetrievalScopeType.ACTIVE_DOCUMENT_VERSION,
                kb_id=query.kb_id,
                document_id=document.doc_id,
                version_id=version.version_id,
                manifests=[manifest],
            )

        manifests: list[ActiveRetrievalManifest] = []
        for document in self._documents.list_documents(query.kb_id):
            if not document.current_version_id:
                continue
            try:
                version = self._require_active_version(document.current_version_id, kb_id=query.kb_id)
            except NoActiveRetrievalScopeError:
                continue
            manifests.append(
                self._require_active_manifest(version.active_manifest_index_id, version.doc_id, version.version_id)
            )

        if not manifests:
            raise NoActiveRetrievalScopeError(f"no active retrieval scope found for kb_id={query.kb_id}")
        return self._build_scope(
            scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
            kb_id=query.kb_id,
            document_id=None,
            version_id=None,
            manifests=manifests,
        )

    def _require_active_version(self, version_id: str, *, kb_id: str):
        version = self._documents.get_version(version_id)
        if version is None or version.kb_id != kb_id:
            raise InvalidRetrievalScopeError(f"version_id={version_id} not found in kb_id={kb_id}")
        if version.status != DocumentVersionStatus.ACTIVE:
            raise NoActiveRetrievalScopeError(f"version_id={version_id} is not active")
        if not version.active_manifest_index_id:
            raise NoActiveManifestError(f"version_id={version_id} has no active manifest")
        return version

    def _require_active_manifest(self, manifest_index_id: str | None, document_id: str, version_id: str) -> ActiveRetrievalManifest:
        if not manifest_index_id:
            raise NoActiveManifestError(f"version_id={version_id} has no active manifest")
        manifest = self._manifests.get(manifest_index_id)
        if manifest is None:
            raise NoActiveManifestError(f"active manifest not found: {manifest_index_id}")
        if not manifest.is_active:
            raise InactiveManifestError(f"manifest is not active: {manifest_index_id}")
        return ActiveRetrievalManifest(
            manifest_index_id=manifest.index_id,
            kb_id=manifest.kb_id,
            document_id=document_id,
            version_id=manifest.version_id,
            embedding_provider=manifest.embedding_provider,
            embedding_model=manifest.embedding_model,
            embedding_dimension=manifest.embedding_dimension,
            distance_metric=manifest.distance_metric,
            artifact_path=manifest.artifact_path,
            mapping_path=manifest.mapping_path,
            checksum=manifest.checksum,
            build_fingerprint=manifest.build_fingerprint,
        )

    def _build_scope(
        self,
        *,
        scope_type: RetrievalScopeType,
        kb_id: str,
        document_id: str | None,
        version_id: str | None,
        manifests: list[ActiveRetrievalManifest],
    ) -> ActiveRetrievalScope:
        providers = {item.embedding_provider for item in manifests}
        models = {item.embedding_model for item in manifests}
        dimensions = {item.embedding_dimension for item in manifests}
        metrics = {item.distance_metric for item in manifests}
        if len(providers) != 1 or len(models) != 1 or len(dimensions) != 1 or len(metrics) != 1:
            raise RetrievalScopeEmbeddingMismatchError("active retrieval scope mixes incompatible manifest configs")
        return ActiveRetrievalScope(
            scope_type=scope_type,
            kb_id=kb_id,
            document_id=document_id,
            version_id=version_id,
            active_manifest_index_ids=[item.manifest_index_id for item in manifests],
            manifests=manifests,
        )
