"""Workspace-evidence answer helpers."""

from __future__ import annotations

from typing import Any

from app.services.orchestrator_agent.schemas import OrchestratorSession
from app.services.orchestrator_agent.visible_execution import (
    answer_from_workspace_with_evidence,
    build_snapshot_final_message,
    build_workspace_evidence_bundle,
    extract_reusable_profile_results,
)


_RERUN_HINTS = ("重新分析", "重新跑", "刷新", "最新", "重新生成")
_READ_ONLY_HINTS = (
    "综合画像", "用户画像", "行为画像", "行为摘要", "行为特点", "征信画像", "app画像",
    "产品策略", "运营策略", "挽留方式", "总结", "简单描述", "概括", "特点",
)
_MODULE_PROMPT_HINTS: dict[str, tuple[str, ...]] = {
    "app": ("app画像", "应用画像", "app 使用", "安装应用", "app安装"),
    "behavior": ("行为画像", "行为摘要", "行为特点", "活跃度", "流失风险"),
    "credit": ("征信画像", "信用画像", "征信", "信用分", "负债"),
    "comprehensive": ("综合画像", "用户画像", "总体画像", "整体画像"),
    "product": ("产品策略", "挽留方式", "续贷策略", "产品建议"),
    "ops": ("运营策略", "催收策略", "触达策略", "运营建议"),
}


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _detect_requested_modules(prompt: str) -> list[str]:
    matched: list[str] = []
    for module_name, hints in _MODULE_PROMPT_HINTS.items():
        if _has_any(prompt, hints):
            matched.append(module_name)
    if matched:
        return matched
    if _has_any(prompt, _READ_ONLY_HINTS):
        return ["comprehensive"]
    return []


def maybe_answer_from_reusable_results(
    session: OrchestratorSession,
    prompt: str,
    detected_country: str | None,
) -> str | None:
    if _has_any(prompt, _RERUN_HINTS):
        return None
    required_modules = _detect_requested_modules(prompt)
    if not required_modules:
        return None

    reusable_results = extract_reusable_profile_results(session)
    if not reusable_results:
        return None
    if len(reusable_results) != 1:
        uid = next(iter(reusable_results.keys()), None)
    else:
        uid = next(iter(reusable_results.keys()))
    if not uid:
        return None
    entries = reusable_results.get(uid) or {}
    if any(module_name not in entries for module_name in required_modules):
        return None
    if detected_country:
        for module_name in required_modules:
            entry_country = str(entries[module_name].get("country") or "").strip().lower()
            if entry_country and entry_country != detected_country.lower():
                return None
    return build_snapshot_final_message(uid=uid, modules=required_modules, entries=entries)


__all__ = [
    "answer_from_workspace_with_evidence",
    "build_workspace_evidence_bundle",
    "maybe_answer_from_reusable_results",
]
