"""Policy-gated semantic retrieval for M6B."""

from __future__ import annotations

from dataclasses import replace

from app.core.config import settings
from app.services.memory.retrieval import (
    MemoryRejectedRetrievalItem,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    evaluate_retrieved_record,
)
from app.services.memory.retrieval_adapter import stored_record_from_memory_row
from app.services.memory.retrieval_policy import (
    MemoryRetrievalPolicy,
    MemoryRetrievalTaskType,
    resolve_retrieval_policies,
)
from app.services.memory.vector_index_adapter import (
    MemoryVectorIndex,
    OrchestratorMemoryVectorIndexAdapter,
)
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore


_ALLOWED_VECTOR_TASK_TYPES = {
    MemoryRetrievalTaskType.GENERAL_CHAT,
    MemoryRetrievalTaskType.PROFILE_FOLLOWUP,
    MemoryRetrievalTaskType.RISK_QA_FOLLOWUP,
}


class SemanticMemoryRetrievalService:
    def __init__(
        self,
        *,
        relational_store: SQLiteMemoryStore,
        vector_index: MemoryVectorIndex | None = None,
    ) -> None:
        self.relational_store = relational_store
        self.vector_index = vector_index or OrchestratorMemoryVectorIndexAdapter(
            relational_store=relational_store
        )

    def retrieve(self, request: MemoryRetrievalRequest) -> MemoryRetrievalResult:
        if not request.allow_vector:
            return self._empty_result(request, reason="vector_disabled")
        if request.task_type not in _ALLOWED_VECTOR_TASK_TYPES:
            return self._empty_result(request, reason="task_type_not_allowlisted")

        try:
            hits = self.vector_index.search(query=request.query, top_k=request.max_vector_items)
        except Exception as exc:
            warnings = ("vector_search_failed",)
            return MemoryRetrievalResult(
                request=request,
                items=(),
                rejected_items=(),
                warnings=warnings,
                metadata={
                    "used_fallback": bool(settings.memory_vector_fallback_to_fts),
                    "vector_error": str(exc),
                    "vector_health": self._safe_health_check(),
                },
            )

        policies = resolve_retrieval_policies(request.task_type)
        accepted = []
        rejected: list[MemoryRejectedRetrievalItem] = []
        seen_memory_ids: set[str] = set()
        score_threshold = settings.memory_vector_min_score

        for hit in hits:
            if score_threshold is not None and hit.normalized_score < float(score_threshold):
                continue
            if hit.memory_id in seen_memory_ids:
                continue
            row = self.relational_store.get(
                hit.memory_id,
                user_id=request.user_id,
                project_id=request.project_id or "",
                country=request.country or "",
                session_id=request.session_id,
            )
            if row is None:
                rejected.append(
                    MemoryRejectedRetrievalItem(
                        memory_id=hit.memory_id,
                        requested_use=policies[0].requested_use,
                        reason="not visible or missing",
                        blocked_by="not_visible_or_missing",
                    )
                )
                continue

            record = stored_record_from_memory_row(row, include_legacy_memory=request.include_legacy_memory)
            if record is None:
                rejected.append(
                    MemoryRejectedRetrievalItem(
                        memory_id=hit.memory_id,
                        requested_use=policies[0].requested_use,
                        reason="memory row lacks supported retrieval metadata",
                        blocked_by="unsupported_memory_metadata",
                    )
                )
                continue

            item, rejection = _evaluate_vector_record(
                record=record,
                request=request,
                policies=policies,
                raw_distance=hit.raw_distance,
                normalized_score=hit.normalized_score,
            )
            if item is not None:
                accepted.append(item)
                seen_memory_ids.add(item.memory_id)
                continue
            if rejection is not None:
                rejected.append(rejection)

        return MemoryRetrievalResult(
            request=request,
            items=tuple(accepted[: request.max_vector_items]),
            rejected_items=tuple(rejected),
            warnings=(),
            metadata={
                "used_fallback": False,
                "vector_health": self._safe_health_check(),
                "returned_item_count": len(accepted[: request.max_vector_items]),
                "rejected_item_count": len(rejected),
            },
        )

    def _empty_result(self, request: MemoryRetrievalRequest, *, reason: str) -> MemoryRetrievalResult:
        return MemoryRetrievalResult(
            request=request,
            items=(),
            rejected_items=(),
            warnings=(),
            metadata={"used_fallback": False, "reason": reason, "vector_health": self._safe_health_check()},
        )

    def _safe_health_check(self) -> dict[str, object]:
        try:
            return self.vector_index.health_check()
        except Exception as exc:  # pragma: no cover - defensive fallback
            return {"ok": False, "error": str(exc)}


def _evaluate_vector_record(
    *,
    record,
    request: MemoryRetrievalRequest,
    policies: tuple[MemoryRetrievalPolicy, ...],
    raw_distance: float,
    normalized_score: float,
):
    source_type = str(record.metadata_json.get("memory_source_type") or "").strip()
    matching_policies = [
        policy
        for policy in policies
        if any(allowed_source_type.value == source_type for allowed_source_type in policy.allowed_source_types)
    ]
    if not matching_policies:
        return None, MemoryRejectedRetrievalItem(
            memory_id=record.memory_id,
            requested_use=policies[0].requested_use,
            reason="source type is not allowed for this retrieval task",
            blocked_by="source_type_not_allowed",
        )

    request_with_legacy = replace(request, include_legacy_memory=True)
    first_rejection = None
    for policy in matching_policies:
        item, rejection = evaluate_retrieved_record(
            record,
            request_with_legacy,
            policy,
            score=normalized_score,
            retrieval_method="vector",
            raw_distance=raw_distance,
            normalized_score=normalized_score,
        )
        if item is not None:
            return item, None
        if first_rejection is None:
            first_rejection = rejection
    return None, first_rejection
