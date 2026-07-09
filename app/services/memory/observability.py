"""Shared semantic-memory observability contracts for M6C."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any, Mapping
from uuid import uuid4

from app.core.config import settings

if TYPE_CHECKING:
    from app.services.memory.retrieval import MemoryRejectedRetrievalItem, MemoryRetrievalRequest


SEMANTIC_MEMORY_TRACE_METADATA_KEY = "semantic_memory_trace"
SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY = "semantic_memory_trace_summary"
SEMANTIC_MEMORY_TRACE_HANDOFF_KEY = "_internal_semantic_memory_trace_summary"
EXECUTION_TRACE_SEMANTIC_MEMORY_KEY = "semantic_memory"


@dataclass(frozen=True)
class SemanticMemoryRetrievalTrace:
    trace_id: str
    run_id: str | None
    request_id: str | None
    task_type: str | None
    requested_use: str | None
    retrieval_mode: str
    feature_enabled: bool
    vector_context_injection_enabled: bool
    fts_candidate_count: int
    vector_candidate_count: int
    relational_loaded_count: int
    policy_allowed_count: int
    policy_blocked_count: int
    fused_candidate_count: int
    injected_count: int
    fallback_used: bool
    fallback_reason: str | None
    policy_block_reasons: dict[str, int]
    context_budget_used: int
    context_budget_limit: int
    vector_budget_limit: int | None
    dropped_due_to_budget: int
    latency_ms: float | None
    warnings: list[str]


@dataclass(frozen=True)
class SemanticMemoryTraceSummary:
    enabled: bool
    retrieval_mode: str
    requested_use: str | None
    fts_candidates: int
    vector_candidates: int
    relational_loaded: int
    policy_allowed: int
    policy_blocked: int
    injected: int
    fallback_used: bool
    fallback_reason: str | None
    context_budget_used: int
    context_budget_limit: int
    latency_ms: float | None
    warnings_count: int


def trace_timer() -> float:
    return perf_counter()


def elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000.0, 3)


def build_semantic_memory_trace(request: "MemoryRetrievalRequest") -> dict[str, Any]:
    return asdict(
        SemanticMemoryRetrievalTrace(
            trace_id=str(getattr(request, "trace_id", None) or uuid4().hex),
            run_id=getattr(request, "run_id", None),
            request_id=getattr(request, "request_id", None),
            task_type=_task_type_value(getattr(request, "task_type", None)),
            requested_use=_resolve_requested_use(getattr(request, "task_type", None)),
            retrieval_mode=str(getattr(request, "retrieval_mode", "fts_only") or "fts_only"),
            feature_enabled=bool(settings.memory_vector_enabled),
            vector_context_injection_enabled=bool(settings.memory_vector_context_injection_enabled),
            fts_candidate_count=0,
            vector_candidate_count=0,
            relational_loaded_count=0,
            policy_allowed_count=0,
            policy_blocked_count=0,
            fused_candidate_count=0,
            injected_count=0,
            fallback_used=False,
            fallback_reason=None,
            policy_block_reasons={},
            context_budget_used=0,
            context_budget_limit=int(getattr(request, "max_items", 0) or 0),
            vector_budget_limit=int(getattr(request, "max_vector_items", 0) or 0),
            dropped_due_to_budget=0,
            latency_ms=None,
            warnings=[],
        )
    )


def ensure_semantic_memory_trace(
    metadata: Mapping[str, Any] | None,
    request: "MemoryRetrievalRequest",
) -> dict[str, Any]:
    trace = build_semantic_memory_trace(request)
    current = (metadata or {}).get(SEMANTIC_MEMORY_TRACE_METADATA_KEY)
    if isinstance(current, Mapping):
        trace.update(dict(current))
        trace["trace_id"] = str(current.get("trace_id") or trace["trace_id"])
        trace["run_id"] = current.get("run_id", trace["run_id"])
        trace["request_id"] = current.get("request_id", trace["request_id"])
    return trace


def build_semantic_memory_trace_summary(trace: Mapping[str, Any]) -> dict[str, Any]:
    return asdict(
        SemanticMemoryTraceSummary(
            enabled=bool(
                trace.get("vector_context_injection_enabled")
                or trace.get("feature_enabled")
                or trace.get("vector_candidate_count")
            ),
            retrieval_mode=str(trace.get("retrieval_mode") or "fts_only"),
            requested_use=_optional_text(trace.get("requested_use")),
            fts_candidates=int(trace.get("fts_candidate_count") or 0),
            vector_candidates=int(trace.get("vector_candidate_count") or 0),
            relational_loaded=int(trace.get("relational_loaded_count") or 0),
            policy_allowed=int(trace.get("policy_allowed_count") or 0),
            policy_blocked=int(trace.get("policy_blocked_count") or 0),
            injected=int(trace.get("injected_count") or 0),
            fallback_used=bool(trace.get("fallback_used", False)),
            fallback_reason=_optional_text(trace.get("fallback_reason")),
            context_budget_used=int(trace.get("context_budget_used") or 0),
            context_budget_limit=int(trace.get("context_budget_limit") or 0),
            latency_ms=_optional_float(trace.get("latency_ms")),
            warnings_count=len(list(trace.get("warnings") or [])),
        )
    )


def canonical_policy_block_reason(blocked_by: str | None) -> str:
    mapping = {
        "inactive_memory_status": "status_not_active",
        "project_id_mismatch": "project_mismatch",
        "country_mismatch": "country_mismatch",
        "explicit_forbidden_use": "forbidden_use",
        "not_in_allowed_use": "allowed_use_missing",
        "authority_level_insufficient": "authority_insufficient",
        "not_visible_or_missing": "scope_mismatch",
    }
    text = _optional_text(blocked_by)
    return mapping.get(text or "", text or "unknown")


def aggregate_policy_block_reasons(rejected_items: tuple["MemoryRejectedRetrievalItem", ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in rejected_items:
        reason = canonical_policy_block_reason(getattr(item, "blocked_by", None))
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def canonical_fallback_reason(reason: str | None) -> str | None:
    mapping = {
        "task_type_not_allowlisted": "task_type_not_allowed",
        "vector_search_failed": "vector_search_error",
    }
    text = _optional_text(reason)
    if not text:
        return None
    return mapping.get(text, text)


def trace_warnings(value: Any) -> list[str]:
    warnings = []
    for item in list(value or []):
        text = _optional_text(item)
        if text:
            warnings.append(text)
    return warnings


def _resolve_requested_use(task_type: Any) -> str | None:
    if task_type is None:
        return None
    try:
        from app.services.memory.retrieval_policy import resolve_retrieval_policies

        policies = resolve_retrieval_policies(task_type)
    except Exception:  # pragma: no cover - defensive fallback
        return None
    if not policies:
        return None
    return _optional_text(policies[0].requested_use.value)


def _task_type_value(task_type: Any) -> str | None:
    if task_type is None:
        return None
    return _optional_text(getattr(task_type, "value", task_type))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)
