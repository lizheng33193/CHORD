"""Adapters that map runtime artifacts into M4 memory candidates."""

from __future__ import annotations

from typing import Any

from app.services.memory.candidates import MemoryCandidate
from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUsePurpose,
)
from app.services.memory.policy import (
    get_allowed_memory_use,
    get_forbidden_memory_use,
)
from app.services.profile_dag.memory_snapshot import ProfileMemorySnapshot


def profile_snapshot_to_memory_candidate(
    snapshot: ProfileMemorySnapshot,
    *,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
) -> MemoryCandidate:
    uid = str(snapshot["uid"])
    segment = _string_or_none(snapshot.get("segment"))
    risk_level = _string_or_none(snapshot.get("risk_level"))
    value_level = _string_or_none(snapshot.get("value_level"))
    confidence = _string_or_none(snapshot.get("confidence"))
    allowed = _memory_uses(snapshot["allowed_memory_use"])
    forbidden = _memory_uses(snapshot["forbidden_memory_use"])

    return MemoryCandidate(
        content=(
            f"Profile result for uid={uid}: segment={segment or 'unknown'}, "
            f"risk={risk_level or 'unknown'}, value={value_level or 'unknown'}, "
            f"confidence={confidence or 'unknown'}."
        ),
        memory_source_type=MemorySourceType.PROFILE_RESULT,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=allowed,
        forbidden_memory_use=forbidden,
        user_id=user_id,
        project_id=project_id or _string_or_none(snapshot.get("project_id")),
        country=country or _string_or_none(snapshot.get("country")),
        source_run_id=_string_or_none(snapshot.get("profile_run_id")),
        evidence_status=_string_or_none(snapshot.get("evidence_status")),
        confidence=_float_or_default(snapshot.get("confidence"), 0.5),
        metadata={
            "uid": uid,
            "summary": _string_or_none(snapshot.get("summary")),
            "segment": segment,
            "risk_level": risk_level,
            "value_level": value_level,
            "confidence": confidence,
            "completed_modules": list(snapshot.get("completed_modules") or []),
            "degraded_modules": list(snapshot.get("degraded_modules") or []),
            "failed_modules": list(snapshot.get("failed_modules") or []),
            "standardized_labels": snapshot.get("standardized_labels"),
            "created_at": _string_or_none(snapshot.get("created_at")),
        },
    )


def risk_qa_answer_to_memory_candidate(
    *,
    answer: str,
    question: str,
    citations: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
    source_run_id: str | None = None,
) -> MemoryCandidate:
    authority_level = (
        MemoryAuthorityLevel.EVIDENCE_GROUNDED if citations else MemoryAuthorityLevel.UNVERIFIED
    )
    return MemoryCandidate(
        content=f"Risk QA answer for question='{question}': {answer}",
        memory_source_type=MemorySourceType.RISK_QA_ANSWER,
        authority_level=authority_level,
        allowed_memory_use=get_allowed_memory_use(MemorySourceType.RISK_QA_ANSWER),
        forbidden_memory_use=get_forbidden_memory_use(MemorySourceType.RISK_QA_ANSWER),
        user_id=user_id,
        project_id=project_id,
        country=country,
        source_run_id=source_run_id,
        evidence_status="grounded" if citations else "unverified",
        metadata={
            "question": question,
            "answer": answer,
            "citations": list(citations or []),
        },
    )


def approved_sql_to_memory_candidate(
    *,
    sql: str,
    question: str,
    approved_sql_hash: str,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
    source_run_id: str | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        content=f"Approved SQL case for question='{question}' with hash={approved_sql_hash}.",
        memory_source_type=MemorySourceType.DATA_AGENT_SQL_CASE,
        authority_level=MemoryAuthorityLevel.HUMAN_APPROVED,
        allowed_memory_use=get_allowed_memory_use(MemorySourceType.DATA_AGENT_SQL_CASE),
        forbidden_memory_use=get_forbidden_memory_use(MemorySourceType.DATA_AGENT_SQL_CASE),
        user_id=user_id,
        project_id=project_id,
        country=country,
        source_run_id=source_run_id,
        source_artifact_id=approved_sql_hash,
        metadata={
            "question": question,
            "sql": sql,
            "approved_sql_hash": approved_sql_hash,
        },
    )


def failed_sql_to_memory_candidate(
    *,
    sql: str,
    error: str,
    question: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
    source_run_id: str | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        content=f"Failed SQL case: error='{error}'.",
        memory_source_type=MemorySourceType.DATA_AGENT_SQL_ERROR,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=get_allowed_memory_use(MemorySourceType.DATA_AGENT_SQL_ERROR),
        forbidden_memory_use=get_forbidden_memory_use(MemorySourceType.DATA_AGENT_SQL_ERROR),
        user_id=user_id,
        project_id=project_id,
        country=country,
        source_run_id=source_run_id,
        metadata={
            "question": question,
            "sql": sql,
            "error": error,
        },
    )


def _memory_uses(values: list[str]) -> tuple[MemoryUsePurpose, ...]:
    return tuple(MemoryUsePurpose(value) for value in values)


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
