"""Stable M4-facing snapshot helpers for profile DAG results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from app.services.label_builder import build_standardized_labels
from app.services.profile_dag.contracts import ProfileRun, ProfileRunResultSnapshot


ALLOWED_MEMORY_USE = [
    "profile_result_recall",
    "profile_followup_context",
    "user_profile_history",
]

FORBIDDEN_MEMORY_USE = [
    "data_agent_field_grounding",
    "data_knowledge_authority",
    "risk_knowledge_document_evidence",
    "approved_strategy_policy",
    "sql_generation_grounding",
]


class ProfileMemorySnapshot(TypedDict):
    uid: str
    country: str | None
    project_id: str | None
    profile_run_id: str | None
    completed_modules: list[str]
    degraded_modules: list[str]
    failed_modules: list[str]
    summary: str | None
    standardized_labels: dict[str, Any] | None
    segment: str | None
    risk_level: str | None
    value_level: str | None
    confidence: str | None
    source: Literal["profile_dag"]
    memory_source_type: Literal["profile_result"]
    authority_level: Literal["system_generated"]
    profile_runtime_version: str
    evidence_status: Literal["risk_domain_not_integrated", "unknown"]
    allowed_memory_use: list[str]
    forbidden_memory_use: list[str]
    created_at: str


def build_profile_memory_snapshot(
    run: ProfileRun,
    snapshot: ProfileRunResultSnapshot,
) -> ProfileMemorySnapshot:
    comprehensive = _structured(snapshot.module_outputs.get("comprehensive"))
    standardized_labels = build_standardized_labels(
        app_profile=snapshot.module_outputs.get("app"),
        behavior_profile=snapshot.module_outputs.get("behavior"),
        credit_profile=snapshot.module_outputs.get("credit"),
        comprehensive_profile=snapshot.module_outputs.get("comprehensive"),
        product_advice=snapshot.module_outputs.get("product"),
        ops_advice=snapshot.module_outputs.get("ops"),
    )
    completed_modules, degraded_modules, failed_modules = _module_status_lists(snapshot)
    meaningful = _is_meaningful_profile_result(comprehensive)

    return {
        "uid": snapshot.uid,
        "country": run.country_code,
        "project_id": None,
        "profile_run_id": run.run_id,
        "completed_modules": completed_modules,
        "degraded_modules": degraded_modules,
        "failed_modules": failed_modules,
        "summary": _nullable_text(comprehensive.get("summary")) if meaningful else None,
        "standardized_labels": standardized_labels,
        "segment": _nullable_text(_top_or_metrics(comprehensive, "segment")) if meaningful else None,
        "risk_level": _nullable_text(_top_or_metrics(comprehensive, "overall_risk")) if meaningful else None,
        "value_level": _nullable_text(_top_or_metrics(comprehensive, "overall_value")) if meaningful else None,
        "confidence": _nullable_text(_top_or_metrics(comprehensive, "confidence")) if meaningful else None,
        "source": "profile_dag",
        "memory_source_type": "profile_result",
        "authority_level": "system_generated",
        "profile_runtime_version": "profile_dag_v1",
        "evidence_status": "risk_domain_not_integrated" if meaningful else "unknown",
        "allowed_memory_use": list(ALLOWED_MEMORY_USE),
        "forbidden_memory_use": list(FORBIDDEN_MEMORY_USE),
        "created_at": _created_at(run),
    }


def _structured(agent_output: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(agent_output, dict):
        return {}
    structured = agent_output.get("structured_result")
    return structured if isinstance(structured, dict) else {}


def _top_or_metrics(structured: dict[str, Any], key: str) -> Any:
    if key in structured:
        return structured.get(key)
    metrics = structured.get("metrics")
    if isinstance(metrics, dict):
        return metrics.get(key)
    return None


def _module_status_lists(snapshot: ProfileRunResultSnapshot) -> tuple[list[str], list[str], list[str]]:
    completed: list[str] = []
    degraded: list[str] = []
    failed: list[str] = []
    for node_run in snapshot.node_runs:
        if node_run.status == "completed":
            completed.append(node_run.node_key)
        elif node_run.status == "degraded":
            degraded.append(node_run.node_key)
        elif node_run.status == "failed":
            failed.append(node_run.node_key)
    return completed, degraded, failed


def _is_meaningful_profile_result(structured: dict[str, Any]) -> bool:
    if str(structured.get("status") or "") != "ok":
        return False
    return any(
        _nullable_text(value)
        for value in (
            structured.get("summary"),
            _top_or_metrics(structured, "segment"),
            _top_or_metrics(structured, "overall_risk"),
            _top_or_metrics(structured, "overall_value"),
            _top_or_metrics(structured, "confidence"),
        )
    )


def _nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _created_at(run: ProfileRun) -> str:
    for value in (run.finished_at, run.started_at, run.created_at):
        if value is not None:
            return value.isoformat()
    return datetime.now(timezone.utc).isoformat()
