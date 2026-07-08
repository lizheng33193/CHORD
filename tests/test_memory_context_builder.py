from __future__ import annotations

from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUseDecision,
    MemoryUsePurpose,
)


def _retrieved_item(
    *,
    memory_id: str,
    content: str,
    source_type: MemorySourceType = MemorySourceType.USER_PREFERENCE,
    authority: MemoryAuthorityLevel = MemoryAuthorityLevel.USER_PROVIDED,
    requested_use: MemoryUsePurpose = MemoryUsePurpose.RESPONSE_STYLE,
    evidence_status: str | None = None,
    retrieval_method: str = "fts",
    raw_distance: float | None = None,
):
    from app.services.memory.retrieval import MemoryRetrievedItem

    return MemoryRetrievedItem(
        memory_id=memory_id,
        content=content,
        memory_source_type=source_type,
        authority_level=authority,
        allowed_memory_use=(requested_use,),
        forbidden_memory_use=(),
        requested_use=requested_use,
        use_decision=MemoryUseDecision(
            allowed=True,
            requested_use=requested_use,
            memory_source_type=source_type,
            authority_level=authority,
            reason="memory use allowed",
            blocked_by=None,
        ),
        evidence_status=evidence_status,
        source_run_id=f"run-{memory_id}",
        source_artifact_id=f"artifact-{memory_id}",
        score=0.8,
        retrieval_method=retrieval_method,
        raw_distance=raw_distance,
        normalized_score=0.8,
        metadata={"forbidden_memory_use": ["should_not_render"]},
    )


def _result(*items, warnings: tuple[str, ...] = ()):
    from app.services.memory.retrieval import MemoryRetrievalRequest, MemoryRetrievalResult
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    return MemoryRetrievalResult(
        request=MemoryRetrievalRequest(
            query="reply in Chinese",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="u1",
            project_id="p1",
            country="mx",
        ),
        items=tuple(items),
        rejected_items=(),
        warnings=warnings,
        metadata={},
    )


def test_context_builder_renders_required_provenance_fields() -> None:
    from app.services.memory.context_builder import build_memory_context_bundle

    bundle = build_memory_context_bundle(
        _result(
            _retrieved_item(
                memory_id="pref-1",
                content="User prefers concise Chinese output.",
                evidence_status="grounded",
            )
        )
    )

    assert "source_type=user_preference" in bundle.rendered_text
    assert "authority=user_provided" in bundle.rendered_text
    assert "use=response_style" in bundle.rendered_text
    assert "evidence=grounded" in bundle.rendered_text
    assert "retrieval=fts" in bundle.rendered_text
    assert "forbidden_memory_use" not in bundle.rendered_text


def test_context_builder_truncates_at_item_boundaries() -> None:
    from app.services.memory.context_builder import build_memory_context_bundle

    first = _retrieved_item(memory_id="pref-1", content="A" * 120)
    second = _retrieved_item(memory_id="pref-2", content="B" * 120)

    bundle = build_memory_context_bundle(_result(first, second), max_chars=280)

    assert len(bundle.items) == 1
    assert bundle.items[0].memory_id == "pref-1"
    assert "pref-2" not in bundle.rendered_text
    assert "context_truncated" in bundle.warnings
    assert bundle.metadata["omitted_item_count"] == 1


def test_context_builder_preserves_existing_warnings() -> None:
    from app.services.memory.context_builder import build_memory_context_bundle

    bundle = build_memory_context_bundle(
        _result(
            _retrieved_item(memory_id="pref-1", content="User prefers concise Chinese output."),
            warnings=("missing_country",),
        )
    )

    assert "missing_country" in bundle.warnings


def test_context_builder_renders_vector_method_without_raw_distance() -> None:
    from app.services.memory.context_builder import build_memory_context_bundle

    bundle = build_memory_context_bundle(
        _result(
            _retrieved_item(
                memory_id="pref-2",
                content="User prefers tabular output for profile follow-ups.",
                retrieval_method="vector",
                raw_distance=0.1234,
            )
        )
    )

    assert "retrieval=vector" in bundle.rendered_text
    assert "0.1234" not in bundle.rendered_text
