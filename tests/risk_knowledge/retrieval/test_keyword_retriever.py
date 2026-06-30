from __future__ import annotations


def test_keyword_retriever_searches_scope_chunks(auth_db, retrieval_scope_data) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.retrieval.active_manifest_resolver import ActiveManifestResolver
    from app.risk_knowledge.retrieval.keyword_retriever import BM25KeywordRetriever
    from app.risk_knowledge.retrieval.schemas import RetrievalQuery

    with AuthSessionLocal() as db:
        scope = ActiveManifestResolver(db).resolve_scope(
            RetrievalQuery(query="collection", kb_id=retrieval_scope_data["kb_id"])
        )
        hits = BM25KeywordRetriever(db).search("collection", scope, top_k=2)

    assert hits
    assert hits[0].retrieval_key
