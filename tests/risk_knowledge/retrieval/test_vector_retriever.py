from __future__ import annotations


def test_vector_retriever_returns_hits_for_active_scope(auth_db, retrieval_scope_data) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.retrieval.active_manifest_resolver import ActiveManifestResolver
    from app.risk_knowledge.retrieval.query_embedding import QueryEmbeddingService
    from app.risk_knowledge.retrieval.schemas import RetrievalQuery
    from app.risk_knowledge.retrieval.vector_retriever import FaissVectorRetriever
    from tests.risk_knowledge.retrieval.conftest import DeterministicRetrievalEmbeddingProvider

    with AuthSessionLocal() as db:
        scope = ActiveManifestResolver(db).resolve_scope(
            RetrievalQuery(query="loan warning", kb_id=retrieval_scope_data["kb_id"])
        )
    query_vector = QueryEmbeddingService(
        provider=DeterministicRetrievalEmbeddingProvider(dimension=2),
        expected_dimension=2,
    ).embed_query("loan warning")
    hits = FaissVectorRetriever().search(query_vector.vector, scope, top_k=3)

    assert hits
    assert hits[0].retrieval_key
    assert hits[0].distance_metric == "l2"
