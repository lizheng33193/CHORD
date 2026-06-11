"""Execution-plan helpers extracted from the monolithic agent loop."""

from __future__ import annotations

from typing import Any

from app.services.orchestrator_agent.schemas import DataAvailability, NormalizedRequest


def apply_clarification_answers(prompt: str, answers: dict[str, Any]) -> str:
    country = str((answers or {}).get("country") or "").strip()
    time_window = str((answers or {}).get("time_window") or "").strip()
    auto_profile = (answers or {}).get("auto_profile")
    extra: list[str] = []
    if country:
        extra.append(f"国家：{country}")
    if time_window:
        extra.append(f"时间范围：{time_window}")
    if auto_profile is not None:
        extra.append(f"自动继续画像：{'是' if bool(auto_profile) else '否'}")
    if not extra:
        return prompt
    return f"{prompt}\n" + "\n".join(extra)


def missing_bucket_counts(availability: DataAvailability, requested_missing: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for bucket in requested_missing:
        counts[bucket] = sum(1 for row in availability.per_uid if bucket in row.missing_buckets)
    return counts


def expand_requested_modules(requested_modules: list[str], available_buckets: list[str]) -> list[str]:
    available_base = [module for module in ["app", "behavior", "credit"] if module in set(available_buckets)]
    if not requested_modules:
        if set(available_base) == {"app", "behavior", "credit"}:
            return ["app", "behavior", "credit", "comprehensive", "product", "ops"]
        return available_base

    requested = set(requested_modules)
    resolved: list[str] = []
    if any(module in requested for module in {"comprehensive", "product", "ops"}):
        if set(available_base) == {"app", "behavior", "credit"}:
            resolved.extend(["app", "behavior", "credit", "comprehensive"])
            if "product" in requested:
                resolved.append("product")
            if "ops" in requested:
                resolved.append("ops")
        else:
            resolved.extend(available_base)
    else:
        for module in ["app", "behavior", "credit"]:
            if module in requested and module in available_base:
                resolved.append(module)

    ordered: list[str] = []
    seen: set[str] = set()
    for module in resolved:
        if module in seen:
            continue
        seen.add(module)
        ordered.append(module)
    return ordered


def build_uid_module_plan(
    availability: DataAvailability,
    normalized_request: NormalizedRequest,
) -> dict[str, list[str]]:
    plan: dict[str, list[str]] = {}
    requested_modules = list(normalized_request.modules or [])
    for row in availability.per_uid:
        plan[row.uid] = expand_requested_modules(requested_modules, row.available_buckets)
    return plan


def group_uid_module_plan(uid_plan: dict[str, list[str]]) -> list[tuple[list[str], list[str]]]:
    grouped: dict[tuple[str, ...], list[str]] = {}
    for uid, modules in uid_plan.items():
        grouped.setdefault(tuple(modules), []).append(uid)
    return [(list(modules), uids) for modules, uids in grouped.items()]


def flatten_planned_modules(uid_plan: dict[str, list[str]]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for module in ["app", "behavior", "credit", "comprehensive", "product", "ops"]:
        if any(module in modules for modules in uid_plan.values()) and module not in seen:
            seen.add(module)
            ordered.append(module)
    return ordered


def required_buckets_for_request(requested_modules: list[str]) -> set[str]:
    if not requested_modules:
        return {"app", "behavior", "credit"}
    requested = set(requested_modules)
    required: set[str] = set()
    for module in {"app", "behavior", "credit"} & requested:
        required.add(module)
    if any(module in requested for module in {"comprehensive", "product", "ops"}):
        required.update({"app", "behavior", "credit"})
    return required
