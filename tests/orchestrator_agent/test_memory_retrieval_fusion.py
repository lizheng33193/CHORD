from __future__ import annotations

from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUseDecision,
    MemoryUsePurpose,
)


def _item(memory_id: str, *, retrieval_method: str, score: float = 0.8):
    from app.services.memory.retrieval import MemoryRetrievedItem

    requested_use = MemoryUsePurpose.CONVERSATION_CONTEXT
    return MemoryRetrievedItem(
        memory_id=memory_id,
        content=f"content for {memory_id}",
        memory_source_type=MemorySourceType.CONVERSATION,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=(requested_use,),
        forbidden_memory_use=(MemoryUsePurpose.PERMISSION_OVERRIDE,),
        requested_use=requested_use,
        use_decision=MemoryUseDecision(
            allowed=True,
            requested_use=requested_use,
            memory_source_type=MemorySourceType.CONVERSATION,
            authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
            reason="memory use allowed",
            blocked_by=None,
        ),
        evidence_status=None,
        source_run_id=f"run-{memory_id}",
        source_artifact_id=f"artifact-{memory_id}",
        score=score,
        retrieval_method=retrieval_method,
        raw_distance=0.2 if retrieval_method == "vector" else None,
        normalized_score=score,
        metadata={},
    )


def test_fusion_preserves_fts_order_dedupes_and_limits_vector_items() -> None:
    from app.services.memory.fusion import fuse_memory_items

    fused = fuse_memory_items(
        fts_items=(
            _item("fts-1", retrieval_method="fts", score=0.9),
            _item("dup-1", retrieval_method="fts", score=0.85),
        ),
        vector_items=(
            _item("dup-1", retrieval_method="vector", score=0.99),
            _item("vec-1", retrieval_method="vector", score=0.8),
            _item("vec-2", retrieval_method="vector", score=0.7),
        ),
        max_total_items=3,
        max_vector_items=1,
    )

    assert [item.memory_id for item in fused] == ["fts-1", "dup-1", "vec-1"]
    assert [item.retrieval_method for item in fused] == ["fts", "fts", "vector"]
