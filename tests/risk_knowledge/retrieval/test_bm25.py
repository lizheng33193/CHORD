from __future__ import annotations


def test_bm25_ranks_relevant_chunk_first(retrieval_scope_data, auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.persistence.repositories import SqlAlchemyKnowledgeChunkRepository
    from app.risk_knowledge.retrieval.bm25 import BM25Index

    with AuthSessionLocal() as db:
        chunks = SqlAlchemyKnowledgeChunkRepository(db).list_by_version(retrieval_scope_data["guide_version_id"])

    index = BM25Index.build(chunks)
    hits = index.search("loan warning", top_k=2)

    assert hits[0].chunk_id == "risk_guide_v1_chunk_000001"
    assert len(hits) == 2
