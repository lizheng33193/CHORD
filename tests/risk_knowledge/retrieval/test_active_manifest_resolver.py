from __future__ import annotations

import pytest


def test_active_manifest_resolver_supports_explicit_version(auth_db, retrieval_scope_data) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.retrieval.active_manifest_resolver import ActiveManifestResolver
    from app.risk_knowledge.retrieval.schemas import RetrievalQuery

    with AuthSessionLocal() as db:
        scope = ActiveManifestResolver(db).resolve_scope(
            RetrievalQuery(
                query="loan warning",
                kb_id=retrieval_scope_data["kb_id"],
                version_id=retrieval_scope_data["guide_version_id"],
            )
        )

    assert scope.scope_type == "explicit_version"
    assert scope.active_manifest_index_ids
    assert len(scope.manifests) == 1


def test_active_manifest_resolver_supports_kb_wide_scope(auth_db, retrieval_scope_data) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.retrieval.active_manifest_resolver import ActiveManifestResolver
    from app.risk_knowledge.retrieval.schemas import RetrievalQuery

    with AuthSessionLocal() as db:
        scope = ActiveManifestResolver(db).resolve_scope(
            RetrievalQuery(
                query="warning",
                kb_id=retrieval_scope_data["kb_id"],
            )
        )

    assert scope.scope_type == "kb_active_documents"
    assert len(scope.manifests) == 2


def test_active_manifest_resolver_rejects_document_version_mismatch(auth_db, retrieval_scope_data) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.retrieval.active_manifest_resolver import ActiveManifestResolver
    from app.risk_knowledge.retrieval.errors import RetrievalDocumentVersionMismatchError
    from app.risk_knowledge.retrieval.schemas import RetrievalQuery

    with AuthSessionLocal() as db, pytest.raises(RetrievalDocumentVersionMismatchError):
        ActiveManifestResolver(db).resolve_scope(
            RetrievalQuery(
                query="warning",
                kb_id=retrieval_scope_data["kb_id"],
                document_id=retrieval_scope_data["guide_doc_id"],
                version_id=retrieval_scope_data["ops_version_id"],
            )
        )
