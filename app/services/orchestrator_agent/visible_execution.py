"""Helpers for visible execution fast paths."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.orchestrator_agent.schemas import NormalizedRequest, OrchestratorSession


_UID_RE = re.compile(r"(?<!\d)\d{18}(?!\d)")

_EVIDENCE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "final_message": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["final_message", "confidence"],
}


def build_workspace_evidence_bundle(
    session: OrchestratorSession,
    normalized_request: NormalizedRequest,
    prompt: str,
    detected_country: str | None,
) -> dict[str, Any] | None:
    reusable_results = extract_reusable_profile_results(session)
    if not reusable_results:
        return None

    uid = _pick_snapshot_uid(prompt, normalized_request.uids, reusable_results)
    if not uid:
        return None
    entries = reusable_results.get(uid) or {}
    required_modules = list(normalized_request.modules or ["comprehensive"])
    if any(module_name not in entries for module_name in required_modules):
        return None

    if detected_country:
        for module_name in required_modules:
            entry_country = str(entries[module_name].get("country") or "").strip().lower()
            if entry_country and entry_country != detected_country.lower():
                return None

    evidence_rows = []
    for module_name in required_modules:
        entry = entries[module_name]
        evidence_rows.append({
            "uid": uid,
            "module": module_name,
            "summary": entry.get("summary") or "",
            "structured_result": entry.get("structured_result") or {},
        })

    return {
        "uid": uid,
        "modules": required_modules,
        "entries": entries,
        "evidence_rows": evidence_rows,
        "fallback_message": build_snapshot_final_message(uid=uid, modules=required_modules, entries=entries),
    }


def answer_from_workspace_with_evidence(
    client,
    *,
    prompt: str,
    normalized_request: NormalizedRequest,
    evidence_bundle: dict[str, Any],
) -> tuple[str, float]:
    fallback_message = str(evidence_bundle["fallback_message"])
    fallback_result = {
        "final_message": fallback_message,
        "confidence": 0.72,
    }
    request_understanding = normalized_request.request_understanding
    route_reason = request_understanding.route_reason if request_understanding else "仅基于已有画像结果回答。"
    llm_prompt = (
        "你是用户画像分析助手。请仅基于下方提供的已有画像证据回答当前问题。\n"
        "不要调用工具，不要要求重新分析，不要编造不存在的数据。\n"
        "如果用户要求改写成客服话术，可以在证据范围内做表达转换，但不能新增事实。\n\n"
        f"## 用户问题\n{prompt}\n\n"
        f"## 路由说明\n{route_reason}\n\n"
        f"## 已有画像证据(JSON)\n{json.dumps(evidence_bundle['evidence_rows'], ensure_ascii=False)}\n"
    )
    generated = client.generate_structured(
        skill_name="orchestrator_workspace_followup",
        prompt=llm_prompt,
        fallback_result=fallback_result,
        response_schema=_EVIDENCE_RESPONSE_SCHEMA,
        route_key="orchestrator_agent.workspace_followup",
    )
    structured = generated.get("structured_result", fallback_result) or fallback_result
    final_message = str(structured.get("final_message") or fallback_message)
    try:
        confidence = float(structured.get("confidence", fallback_result["confidence"]))
    except (TypeError, ValueError):
        confidence = float(fallback_result["confidence"])
    return final_message, confidence


def extract_reusable_profile_results(session: OrchestratorSession) -> dict[str, dict[str, dict[str, Any]]]:
    reusable: dict[str, dict[str, dict[str, Any]]] = {}
    run_status_by_id = {
        run.run_id: run.status
        for turn in session.turns
        for run in turn.runs
        if run.run_id
    }

    def _put(entry: dict[str, Any], *, overwrite: bool) -> None:
        uid = entry["uid"]
        module = entry["module"]
        reusable.setdefault(uid, {})
        if overwrite or module not in reusable[uid]:
            reusable[uid][module] = entry

    for record in session.tool_calls:
        if record.tool_name != "run_profile" or record.status != "done" or not isinstance(record.output, dict):
            continue
        if record.run_id and run_status_by_id.get(record.run_id) == "cancelled":
            continue
        default_app_time = record.input.get("app_time") if isinstance(record.input, dict) else None
        rows = record.output.get("results")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            result = row.get("result")
            data = result.get("data") if isinstance(result, dict) else None
            if not (isinstance(result, dict) and result.get("status") == "ok" and isinstance(data, dict)):
                continue
            normalized = _normalize_snapshot_row(
                {
                    "uid": row.get("uid"),
                    "module": row.get("module"),
                    "summary": data.get("summary"),
                    "structured_result": data.get("structured_result"),
                },
                default_country=session.country,
                default_app_time=default_app_time,
            )
            if normalized:
                _put(normalized, overwrite=True)

    session_snapshot = session.active_entities.get("workspace_snapshot")
    if isinstance(session_snapshot, dict):
        default_country = session_snapshot.get("country") or session.country
        default_app_time = session_snapshot.get("applicationTime")
        rows = session_snapshot.get("results")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                normalized = _normalize_snapshot_row(
                    row,
                    default_country=default_country,
                    default_app_time=default_app_time,
                )
                if normalized:
                    _put(normalized, overwrite=False)

    return reusable


def build_snapshot_final_message(*, uid: str, modules: list[str], entries: dict[str, dict[str, Any]]) -> str:
    profile_module_labels = {
        "app": "App画像",
        "behavior": "行为画像",
        "credit": "征信画像",
        "comprehensive": "综合画像",
        "product": "产品策略",
        "ops": "运营策略",
    }

    if modules == ["behavior"] and entries.get("behavior"):
        behavior = entries["behavior"]
        return (
            f"## 行为画像分析报告：UID {uid}\n\n"
            f"{behavior.get('summary') or '暂无行为画像摘要。'}"
        )

    if modules == ["app"] and entries.get("app"):
        app_result = entries["app"]
        return (
            f"## App画像分析报告：UID {uid}\n\n"
            f"{app_result.get('summary') or '暂无 App 画像摘要。'}"
        )

    if modules == ["credit"] and entries.get("credit"):
        credit = entries["credit"]
        return (
            f"## 征信画像分析报告：UID {uid}\n\n"
            f"{credit.get('summary') or '暂无征信画像摘要。'}"
        )

    if modules == ["product"] and entries.get("product"):
        product = entries["product"]
        return (
            f"## 产品策略建议：UID {uid}\n\n"
            f"{product.get('summary') or '暂无产品策略摘要。'}"
        )

    if modules == ["ops"] and entries.get("ops"):
        ops = entries["ops"]
        return (
            f"## 运营策略建议：UID {uid}\n\n"
            f"{ops.get('summary') or '暂无运营策略摘要。'}"
        )

    comprehensive = entries.get("comprehensive")
    lines = [f"## 综合画像分析报告：UID {uid}", ""]
    if comprehensive:
        lines.append(comprehensive.get("summary") or "暂无综合画像摘要。")
    else:
        lines.append("暂无综合画像摘要。")

    detail_modules = ["app", "behavior", "credit", "product", "ops"]
    detail_lines = []
    for module_name in detail_modules:
        entry = entries.get(module_name)
        if not entry:
            continue
        detail_lines.append(
            f"- **{profile_module_labels[module_name]}**：{entry.get('summary') or '暂无摘要。'}"
        )
    if detail_lines:
        lines.extend(["", "### 已有模块结论", *detail_lines])
    return "\n".join(lines)


def _pick_snapshot_uid(
    prompt: str,
    requested_uids: list[str],
    reusable_results: dict[str, dict[str, dict[str, Any]]],
) -> str | None:
    if requested_uids:
        for requested_uid in requested_uids:
            if requested_uid in reusable_results:
                return requested_uid
    requested_uid = _extract_requested_uid(prompt)
    if requested_uid and requested_uid in reusable_results:
        return requested_uid
    if len(reusable_results) == 1:
        return next(iter(reusable_results.keys()))
    if reusable_results:
        return next(iter(reusable_results.keys()))
    return None


def _extract_requested_uid(prompt: str) -> str | None:
    matched = _UID_RE.search(prompt or "")
    return matched.group(0) if matched else None


def _normalize_snapshot_row(
    row: dict[str, Any],
    *,
    default_country: str | None,
    default_app_time: str | None,
) -> dict[str, Any] | None:
    uid = str(row.get("uid") or "").strip()
    module = str(row.get("module") or "").strip()
    if not uid or not module:
        return None
    structured_result = row.get("structured_result")
    if not isinstance(structured_result, dict):
        structured_result = {}
    return {
        "uid": uid,
        "module": module,
        "summary": str(row.get("summary") or "").strip(),
        "structured_result": structured_result,
        "country": row.get("country") or default_country,
        "applicationTime": row.get("applicationTime") or default_app_time,
    }
