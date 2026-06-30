from __future__ import annotations


def test_hybrid_retriever_returns_hydrated_candidates(auth_db, retrieval_scope_data) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.retrieval.hybrid_retriever import HybridRiskKnowledgeRetriever
    from app.risk_knowledge.retrieval.schemas import RetrievalQuery
    from tests.risk_knowledge.retrieval.conftest import DeterministicRetrievalEmbeddingProvider

    with AuthSessionLocal() as db:
        result = HybridRiskKnowledgeRetriever(
            db=db,
            provider=DeterministicRetrievalEmbeddingProvider(dimension=2),
        ).retrieve(
            RetrievalQuery(
                query="loan warning",
                kb_id=retrieval_scope_data["kb_id"],
            )
        )

    assert result.scope_type == "kb_active_documents"
    assert result.active_manifest_index_ids
    assert result.candidates
    assert result.candidates[0].document_id
    assert result.candidates[0].version_id
    assert result.candidates[0].manifest_index_id
    assert result.candidates[0].content_hash
