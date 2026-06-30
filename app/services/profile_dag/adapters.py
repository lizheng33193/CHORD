"""Compatibility adapters for Profile DAG runtime outputs and events."""

from __future__ import annotations

from typing import Any

from app.schemas.final_response import UserAnalysisResult
from app.services.profile_dag.contracts import ProfileNodeRun, ProfileRunResultSnapshot
from app.services.profile_dag.node_registry import NODE_KEY_TO_SPEC


def empty_agent_output(summary: str, *, status: str = "error", message: str = "") -> dict[str, Any]:
    return {
        "summary": summary,
        "structured_result": {
            "status": status,
            "message": message or summary,
        },
        "charts": [],
        "report_markdown": summary,
    }


def profile_event_to_legacy_skill_events(event: dict[str, Any]) -> list[dict[str, Any]]:
    event_type = event.get("type")
    if event_type == "profile_node_started":
        return [{
            "type": "skill_started",
            "uid": event.get("uid"),
            "skill": event.get("skill_name"),
            "stage": event.get("stage"),
        }]
    if event_type == "profile_node_completed":
        return [{
            "type": "skill_completed",
            "uid": event.get("uid"),
            "skill": event.get("skill_name"),
            "stage": event.get("stage"),
            "duration_ms": int(event.get("duration_ms") or 0),
        }]
    if event_type == "profile_node_failed":
        return [{
            "type": "skill_failed",
            "uid": event.get("uid"),
            "skill": event.get("skill_name"),
            "stage": event.get("stage"),
            "duration_ms": int(event.get("duration_ms") or 0),
            "error_message": ((event.get("error") or {}).get("message") or "profile node failed"),
        }]
    return []


def profile_event_to_legacy_module_event(
    event: dict[str, Any],
    *,
    requested_modules: list[str],
    completed: int,
    total: int,
) -> tuple[dict[str, Any] | None, int]:
    node_key = str(event.get("node_key") or "")
    if node_key not in requested_modules:
        return None, completed

    event_type = event.get("type")
    uid = event.get("uid")
    if event_type == "profile_node_started":
        return ({
            "progress_type": "profile_module_started",
            "uid": uid,
            "module": node_key,
            "status": "running",
            "completed": completed,
            "total": total,
        }, completed)

    if event_type not in {"profile_node_completed", "profile_node_failed", "profile_node_skipped"}:
        return None, completed

    next_completed = completed + 1
    result = profile_node_event_to_module_result(event)
    if event_type == "profile_node_completed":
        return ({
            "progress_type": "profile_module_completed",
            "uid": uid,
            "module": node_key,
            "result": result,
            "status": "ok" if result.get("status") == "ok" else "error",
            "completed": next_completed,
            "total": total,
            "elapsed_ms": int(event.get("duration_ms") or 0),
        }, next_completed)

    error_message = ((event.get("error") or {}).get("message") or result.get("error", {}).get("message"))
    return ({
        "progress_type": "profile_module_error",
        "uid": uid,
        "module": node_key,
        "status": "error",
        "completed": next_completed,
        "total": total,
        "elapsed_ms": int(event.get("duration_ms") or 0),
        "error": error_message,
        "result": result,
    }, next_completed)


def classify_module_payload(payload: dict[str, Any] | None) -> tuple[str, str | None]:
    if not isinstance(payload, dict):
        return "failed", None
    structured = payload.get("structured_result") if isinstance(payload.get("structured_result"), dict) else {}
    result_status = str(structured.get("status") or "ok")
    if result_status in {"error", "failed"}:
        return "failed", result_status
    if result_status in {"data_missing", "degraded", "partial", "warning", "skipped"}:
        return "degraded", result_status
    model_trace = structured.get("model_trace") if isinstance(structured.get("model_trace"), dict) else {}
    if model_trace.get("fallback_reason") or model_trace.get("degraded") or model_trace.get("model_unavailable"):
        return "degraded", result_status
    return "completed", result_status


def node_run_to_module_result(node_run: ProfileNodeRun) -> dict[str, Any]:
    if node_run.status in {"completed", "degraded"} and isinstance(node_run.output_ref, dict):
        return {
            "uid": node_run.uid,
            "module": node_run.node_key,
            "status": "ok",
            "data": node_run.output_ref,
            "error": None,
        }
    message = ((node_run.error or {}).get("message") or node_run.skip_reason or f"{node_run.node_key} unavailable")
    details = dict(node_run.error or {})
    if node_run.skip_reason and "skip_reason" not in details:
        details["skip_reason"] = node_run.skip_reason
    return {
        "uid": node_run.uid,
        "module": node_run.node_key,
        "status": "error",
        "data": None,
        "error": {
            "code": "dependency_module_failed" if node_run.status == "skipped" else "module_runtime_error",
            "message": message,
            "details": details,
        },
    }


def profile_node_event_to_module_result(event: dict[str, Any]) -> dict[str, Any]:
    status = str(event.get("status") or "")
    if status in {"completed", "degraded"} and isinstance(event.get("output"), dict):
        return {
            "uid": event.get("uid"),
            "module": event.get("node_key"),
            "status": "ok",
            "data": event.get("output"),
            "error": None,
        }
    error = event.get("error") or {}
    message = error.get("message") or f"{event.get('node_key')} unavailable"
    code = "dependency_module_failed" if status == "skipped" else "module_runtime_error"
    details = dict(error)
    return {
        "uid": event.get("uid"),
        "module": event.get("node_key"),
        "status": "error",
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


def snapshot_to_user_analysis_result(
    snapshot: ProfileRunResultSnapshot,
    *,
    standardized_labels: dict[str, Any] | None,
) -> UserAnalysisResult:
    outputs = snapshot.module_outputs
    app_output = outputs.get("app") or empty_agent_output("App profile unavailable.")
    behavior_output = outputs.get("behavior") or empty_agent_output("Behavior profile unavailable.")
    credit_output = outputs.get("credit") or empty_agent_output("Credit profile unavailable.")
    comprehensive_output = outputs.get("comprehensive") or empty_agent_output("Comprehensive profile unavailable.")

    product_output = outputs.get("product")
    ops_output = outputs.get("ops")
    return UserAnalysisResult(
        uid=snapshot.uid,
        app_profile=app_output,
        behavior_profile=behavior_output,
        credit_profile=credit_output,
        comprehensive_profile=comprehensive_output,
        product_advice=product_output,
        ops_advice=ops_output,
        standardized_labels=standardized_labels,
    )


def snapshot_to_run_profile_rows(snapshot: ProfileRunResultSnapshot) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    node_run_by_key = {node_run.node_key: node_run for node_run in snapshot.node_runs}
    for module in snapshot.requested_modules:
        node_run = node_run_by_key[module]
        rows.append(
            {
                "uid": snapshot.uid,
                "module": module,
                "result": node_run_to_module_result(node_run),
            }
        )
    return rows


def snapshot_to_module_response(snapshot: ProfileRunResultSnapshot, module: str) -> dict[str, Any]:
    node_run_by_key = {node_run.node_key: node_run for node_run in snapshot.node_runs}
    return node_run_to_module_result(node_run_by_key[module])


def canonical_node_order() -> list[str]:
    return list(NODE_KEY_TO_SPEC.keys())
