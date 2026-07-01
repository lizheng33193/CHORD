from __future__ import annotations


class StubRetriever:
    def retrieve(self, query):
        from app.risk_knowledge.retrieval.schemas import HybridRetrievalCandidate, HybridRetrievalResult, RetrievalScopeType

        self.last_query = query
        return HybridRetrievalResult(
            query=query.query,
            normalized_query=query.query,
            kb_id=query.kb_id,
            scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
            document_id=query.document_id,
            version_id=query.version_id,
            active_manifest_index_ids=["idx_manifest_active"],
            embedding_provider="deterministic_test",
            embedding_model="deterministic-v1",
            embedding_dimension=2,
            candidates=[
                HybridRetrievalCandidate(
                    retrieval_key="risk_guide_v1_chunk_000001",
                    chunk_id="risk_guide_v1_chunk_000001",
                    document_id="risk_guide",
                    version_id="risk_guide_v1",
                    manifest_index_id="idx_manifest_active",
                    content_hash="sha256:chunk-1",
                    section_path=["贷前风控", "多头借贷"],
                    page_start=12,
                    page_end=13,
                    text="多头借贷是指用户在多个平台频繁申请或使用信贷产品。" * 20,
                    vector_raw_score=0.83,
                    keyword_score=4.21,
                    fused_score=0.034,
                    fused_rank=1,
                    matched_channels=["vector", "keyword"],
                )
            ],
            diagnostics={
                "vector_hit_count": 5,
                "keyword_hit_count": 4,
                "fused_hit_count": 1,
            },
        )


def test_retrieval_debug_service_returns_retrieval_only_payload() -> None:
    from app.risk_knowledge.admin.retrieval_debug_service import RetrievalDebugService
    from app.risk_knowledge.admin.schemas import DebugRetrieveRequest

    retriever = StubRetriever()
    service = RetrievalDebugService(db=None, retriever=retriever, text_preview_chars=120)

    response = service.debug_retrieve(
        DebugRetrieveRequest(
            kb_id="risk_domain_knowledge",
            query="什么是多头借贷风险？",
            top_k=10,
        )
    )

    assert retriever.last_query.fused_top_k == 10
    assert response.query == "什么是多头借贷风险？"
    assert response.scope.scope_type == "kb_active_documents"
    assert response.candidates[0].rank == 1
    assert response.candidates[0].section_path == "贷前风控 / 多头借贷"
    assert len(response.candidates[0].text_preview) <= 123
    assert response.candidates[0].scores.vector_score == 0.83
    assert response.diagnostics.candidate_count == 1
    assert "answer" not in response.model_dump()
    assert "citations" not in response.model_dump()


def test_retrieval_debug_service_clamps_top_k_to_bounded_candidates() -> None:
    from app.risk_knowledge.admin.retrieval_debug_service import RetrievalDebugService
    from app.risk_knowledge.admin.schemas import DebugRetrieveRequest

    retriever = StubRetriever()
    service = RetrievalDebugService(db=None, retriever=retriever)

    response = service.debug_retrieve(
        DebugRetrieveRequest(
            kb_id="risk_domain_knowledge",
            query="loan risk",
            top_k=1,
        )
    )

    assert len(response.candidates) == 1
