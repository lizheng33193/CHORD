"""Isolated M4 retrieval service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.memory.candidates import MemoryCandidate
from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUseDecision,
    MemoryUsePurpose,
)
from app.services.memory.isolation import validate_memory_use
from app.services.memory.retrieval_adapter import MemoryReadableStoreAdapter, MemoryStoredRecord
from app.services.memory.retrieval_policy import (
    MemoryRetrievalPolicy,
    MemoryRetrievalTaskType,
    resolve_retrieval_policies,
)


@dataclass(frozen=True)
class MemoryRetrievalRequest:
    query: str
    task_type: MemoryRetrievalTaskType
    user_id: str
    project_id: str | None = None
    country: str | None = None
    session_id: str | None = None
    max_items: int = 8
    include_legacy_memory: bool = False
    production_context: bool = False

    def __post_init__(self) -> None:
        user_id = str(self.user_id or "").strip()
        if not user_id:
            raise ValueError("MemoryRetrievalRequest.user_id is required")
        object.__setattr__(self, "query", str(self.query or "").strip())
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "project_id", _optional_text(self.project_id))
        object.__setattr__(self, "country", _optional_text(self.country))
        object.__setattr__(self, "session_id", _optional_text(self.session_id))
        object.__setattr__(self, "max_items", max(1, int(self.max_items or 1)))


@dataclass(frozen=True)
class MemoryRetrievedItem:
    memory_id: str
    content: str
    memory_source_type: MemorySourceType
    authority_level: MemoryAuthorityLevel
    allowed_memory_use: tuple[MemoryUsePurpose, ...]
    forbidden_memory_use: tuple[MemoryUsePurpose, ...]
    requested_use: MemoryUsePurpose
    use_decision: MemoryUseDecision
    evidence_status: str | None
    source_run_id: str | None
    source_artifact_id: str | None
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRejectedRetrievalItem:
    memory_id: str
    requested_use: MemoryUsePurpose
    reason: str
    blocked_by: str | None
    memory_source_type: MemorySourceType | None = None
    authority_level: MemoryAuthorityLevel | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRetrievalResult:
    request: MemoryRetrievalRequest
    items: tuple[MemoryRetrievedItem, ...]
    rejected_items: tuple[MemoryRejectedRetrievalItem, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryRetrievalService:
    def __init__(self, store: MemoryReadableStoreAdapter) -> None:
        self.store = store

    def retrieve(self, request: MemoryRetrievalRequest) -> MemoryRetrievalResult:
        warnings: list[str] = []
        metadata: dict[str, Any] = {}
        if not request.project_id:
            warnings.append("missing_project_id")
        if not request.country:
            warnings.append("missing_country")
        metadata["policy_count"] = 0

        accepted: list[MemoryRetrievedItem] = []
        rejected: list[MemoryRejectedRetrievalItem] = []
        seen_item_ids: set[str] = set()
        seen_rejected_ids: set[str] = set()

        policies = resolve_retrieval_policies(request.task_type)
        metadata["policy_count"] = len(policies)
        for policy in policies:
            candidates = self.store.search_records(
                query=request.query,
                user_id=request.user_id,
                project_id=request.project_id,
                country=request.country,
                allowed_source_types=policy.allowed_source_types,
                limit=policy.max_items,
                include_legacy_memory=request.include_legacy_memory or policy.include_legacy_memory,
            )
            for record in candidates:
                item, rejection = self._evaluate_record(record, request, policy)
                if item is not None:
                    if item.memory_id in seen_item_ids:
                        continue
                    accepted.append(item)
                    seen_item_ids.add(item.memory_id)
                    continue
                if rejection is not None:
                    if rejection.memory_id in seen_rejected_ids:
                        continue
                    rejected.append(rejection)
                    seen_rejected_ids.add(rejection.memory_id)

        accepted.sort(key=_sort_key, reverse=True)
        truncated_items = accepted[: request.max_items]
        metadata["returned_item_count"] = len(truncated_items)
        metadata["rejected_item_count"] = len(rejected)
        return MemoryRetrievalResult(
            request=request,
            items=tuple(truncated_items),
            rejected_items=tuple(rejected),
            warnings=tuple(warnings),
            metadata=metadata,
        )

    def _evaluate_record(
        self,
        record: MemoryStoredRecord,
        request: MemoryRetrievalRequest,
        policy: MemoryRetrievalPolicy,
    ) -> tuple[MemoryRetrievedItem | None, MemoryRejectedRetrievalItem | None]:
        metadata = dict(record.metadata_json or {})
        if not _is_valid_m4_envelope(metadata):
            return None, MemoryRejectedRetrievalItem(
                memory_id=record.memory_id,
                requested_use=policy.requested_use,
                reason="malformed_m4_metadata",
                blocked_by="malformed_m4_metadata",
                metadata={"metadata_keys": sorted(metadata)},
            )
        if str(record.status or "").strip().lower() != "active":
            return None, MemoryRejectedRetrievalItem(
                memory_id=record.memory_id,
                requested_use=policy.requested_use,
                reason="inactive_memory_status",
                blocked_by="inactive_memory_status",
            )
        if request.project_id is not None and record.project_id != request.project_id:
            return None, MemoryRejectedRetrievalItem(
                memory_id=record.memory_id,
                requested_use=policy.requested_use,
                reason="project_id_mismatch",
                blocked_by="project_id_mismatch",
            )
        if request.country is not None and (record.country or "").lower() != request.country.lower():
            return None, MemoryRejectedRetrievalItem(
                memory_id=record.memory_id,
                requested_use=policy.requested_use,
                reason="country_mismatch",
                blocked_by="country_mismatch",
            )

        try:
            source_type = MemorySourceType(str(metadata["memory_source_type"]))
            authority_level = MemoryAuthorityLevel(str(metadata["authority_level"]))
            allowed_uses = tuple(MemoryUsePurpose(value) for value in metadata["allowed_memory_use"])
            forbidden_uses = tuple(MemoryUsePurpose(value) for value in metadata["forbidden_memory_use"])
        except (KeyError, TypeError, ValueError):
            return None, MemoryRejectedRetrievalItem(
                memory_id=record.memory_id,
                requested_use=policy.requested_use,
                reason="malformed_m4_metadata",
                blocked_by="malformed_m4_metadata",
                metadata={"metadata_keys": sorted(metadata)},
            )

        if authority_level not in policy.min_authority_levels:
            return None, MemoryRejectedRetrievalItem(
                memory_id=record.memory_id,
                requested_use=policy.requested_use,
                reason="authority_level_insufficient",
                blocked_by="authority_level_insufficient",
                memory_source_type=source_type,
                authority_level=authority_level,
            )

        candidate = MemoryCandidate(
            content=record.content,
            memory_source_type=source_type,
            authority_level=authority_level,
            allowed_memory_use=allowed_uses,
            forbidden_memory_use=forbidden_uses,
            user_id=record.user_id,
            project_id=record.project_id,
            country=record.country,
            session_id=request.session_id,
            source_run_id=_optional_text(metadata.get("source_run_id")),
            source_artifact_id=_optional_text(metadata.get("source_artifact_id")),
            evidence_status=_optional_text(metadata.get("evidence_status")),
            importance=float(record.importance),
            confidence=float(record.confidence),
            metadata=dict(metadata.get("candidate_metadata") or {}),
        )
        use_decision = validate_memory_use(
            candidate,
            policy.requested_use,
            production_context=request.production_context or policy.production_context,
        )
        if not use_decision.allowed:
            return None, MemoryRejectedRetrievalItem(
                memory_id=record.memory_id,
                requested_use=policy.requested_use,
                reason=use_decision.reason,
                blocked_by=use_decision.blocked_by,
                memory_source_type=source_type,
                authority_level=authority_level,
                metadata=dict(candidate.metadata),
            )

        return (
            MemoryRetrievedItem(
                memory_id=record.memory_id,
                content=record.content,
                memory_source_type=source_type,
                authority_level=authority_level,
                allowed_memory_use=allowed_uses,
                forbidden_memory_use=forbidden_uses,
                requested_use=policy.requested_use,
                use_decision=use_decision,
                evidence_status=_optional_text(metadata.get("evidence_status")),
                source_run_id=_optional_text(metadata.get("source_run_id")),
                source_artifact_id=_optional_text(metadata.get("source_artifact_id")),
                score=_score(record),
                metadata={
                    **dict(candidate.metadata),
                    "importance": float(record.importance),
                    "confidence": float(record.confidence),
                    "created_at": record.created_at,
                },
            ),
            None,
        )


def _is_valid_m4_envelope(metadata: dict[str, Any]) -> bool:
    required = {
        "m4_contract_version",
        "memory_source_type",
        "authority_level",
        "allowed_memory_use",
        "forbidden_memory_use",
        "write_gate",
    }
    return required.issubset(metadata)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _score(record: MemoryStoredRecord) -> float:
    return round((float(record.importance) * 0.6) + (float(record.confidence) * 0.4), 6)


def _sort_key(item: MemoryRetrievedItem) -> tuple[float, float, float]:
    return (
        float(item.metadata.get("importance", item.score)),
        float(item.metadata.get("confidence", item.score)),
        _created_at_rank(item.metadata.get("created_at")),
    )


def _created_at_rank(value: Any) -> float:
    text = _optional_text(value)
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
