"""Deterministic review builders for visible execution."""

from __future__ import annotations

from app.services.orchestrator_agent.schemas import DataAvailability, NormalizedRequest, ReviewResult

_FULL_MODULE_CHAIN = ["app", "behavior", "credit", "comprehensive", "product", "ops"]


def build_no_workspace_review() -> ReviewResult:
    return ReviewResult(
        status="fail",
        issues=[{
            "type": "no_workspace_context",
            "message": "当前会话没有可复用的画像结果，无法直接回答只读追问。",
        }],
        can_answer=False,
        confidence_impact="缺少可复用画像上下文，已阻断只读追问",
    )


def build_profile_review(
    availability: DataAvailability,
    uid_modules_run: dict[str, list[str]],
    profile_output: dict | None = None,
    normalized_request: NormalizedRequest | None = None,
) -> ReviewResult:
    if not any(uid_modules_run.values()):
        if normalized_request and normalized_request.modules:
            return ReviewResult(
                status="fail",
                issues=[{
                    "type": "requested_modules_unavailable",
                    "message": "本次请求没有任何可运行模块。",
                }],
                can_answer=False,
                confidence_impact="用户请求的必要数据当前不可用，无法生成可信画像",
            )
        return ReviewResult(
            status="fail",
            issues=[{"type": "no_basic_bucket", "message": "没有任何基础 bucket 可用于画像"}],
            can_answer=False,
            confidence_impact="无法生成可信画像",
        )

    issues: list[dict] = []
    requested_modules = list((normalized_request.modules if normalized_request else []) or [])
    requested_set = set(requested_modules)
    fatal_types = {"module_error", "no_basic_bucket"}
    expect_full_profile = not requested_modules
    required_buckets = _required_buckets_for_modules(requested_modules)
    all_expected_met = True
    for row in availability.per_uid:
        modules_run = list(uid_modules_run.get(row.uid) or [])
        expected_modules = _expected_modules_for_review(requested_modules)
        expected_set = set(expected_modules)
        if expect_full_profile and modules_run != _FULL_MODULE_CHAIN:
            all_expected_met = False
            issues.append({
                "type": "partial_profile",
                "uid": row.uid,
                "modules_run": modules_run,
            })
        missing_required_buckets = [
            bucket
            for bucket in row.missing_buckets
            if expect_full_profile or bucket in _required_buckets_for_modules(requested_modules)
        ]
        for bucket in missing_required_buckets:
            issues.append({
                "type": "missing_data",
                "uid": row.uid,
                "bucket": bucket,
                "reason": "bucket_missing",
            })
        for bucket_name in row.available_buckets:
            if not expect_full_profile and bucket_name not in required_buckets:
                continue
            bucket_status = getattr(row, bucket_name)
            if bucket_status.status != "available":
                issues.append({
                    "type": "weak_bucket_data",
                    "uid": row.uid,
                    "bucket": bucket_name,
                    "reason": bucket_status.detail or bucket_status.status,
                })
            elif bucket_status.weak_reasons:
                issues.append({
                    "type": "weak_prepared_data",
                    "uid": row.uid,
                    "bucket": bucket_name,
                    "reason": ",".join(bucket_status.weak_reasons),
                })
        for module_name in expected_set:
            if module_name not in modules_run:
                all_expected_met = False
                issues.append({
                    "type": "requested_module_skipped",
                    "uid": row.uid,
                    "module": module_name,
                    "reason": (
                        "dependent_data_missing"
                        if module_name in {"comprehensive", "product", "ops"}
                        else "requested_bucket_unavailable"
                    ),
                })

    if profile_output:
        for row in profile_output.get("results") or []:
            uid = row.get("uid")
            module_name = row.get("module")
            result = row.get("result") or {}
            status = result.get("status")
            error = result.get("error")
            data = result.get("data") or {}
            if status != "ok" or error:
                issues.append({
                    "type": "module_error",
                    "uid": uid,
                    "module": module_name,
                    "message": error or status or "module_execution_failed",
                })
                continue
            if not str(data.get("summary") or "").strip():
                issues.append({
                    "type": "empty_summary",
                    "uid": uid,
                    "module": module_name,
                })
            structured_result = data.get("structured_result")
            if structured_result in (None, "", [], {}):
                issues.append({
                    "type": "missing_structured_result",
                    "uid": uid,
                    "module": module_name,
                })
            model_trace = data.get("model_trace") or {}
            if model_trace.get("fallback_reason") or model_trace.get("degraded") or model_trace.get("model_unavailable"):
                issues.append({
                    "type": "degraded_model_output",
                    "uid": uid,
                    "module": module_name,
                    "reason": model_trace.get("fallback_reason") or "degraded",
                })

    if all_expected_met and not issues:
        return ReviewResult(status="pass", issues=[], can_answer=True, confidence_impact=None)

    if not issues:
        issues.append({
            "type": "partial_profile",
            "message": "仅输出有真实数据支撑的基础模块。",
        })

    if requested_set & {"product", "ops", "comprehensive"}:
        confidence_impact = "部分基础数据缺失，综合/策略结论已降级"
    elif expect_full_profile:
        confidence_impact = "部分用户仅输出有真实数据支撑的模块"
    else:
        confidence_impact = "请求模块已满足，但其余非请求模块未纳入本次审核"

    status = "fail" if any(issue.get("type") in fatal_types for issue in issues) else "warning"
    if status == "fail":
        can_answer = False
    else:
        can_answer = True

    return ReviewResult(
        status=status,
        issues=issues,
        can_answer=can_answer,
        confidence_impact=confidence_impact,
    )


def review_step_summary(review: ReviewResult) -> str:
    if review.status == "pass":
        return "规则审核通过，可直接输出结果。"
    if review.status == "warning":
        return review.confidence_impact or "规则审核完成，结果已降级。"
    return review.confidence_impact or "规则审核完成，当前请求已阻断。"


def append_data_acquisition_issue(
    review: ReviewResult,
    *,
    missing_buckets: list[str],
    blocked: bool,
) -> ReviewResult:
    issues = list(review.issues)
    issues.append({
        "type": "data_acquisition_unavailable",
        "severity": "error" if blocked else "warning",
        "missing_buckets": list(missing_buckets),
        "message": (
            "用户请求的必要数据缺失，且当前无法自动补齐。"
            if blocked
            else "缺失 bucket 当前无法自动补齐。"
        ),
    })
    confidence_impact = review.confidence_impact
    if blocked:
        confidence_impact = confidence_impact or "用户请求的必要数据当前不可用，无法生成可信画像"
    else:
        confidence_impact = confidence_impact or "缺失 bucket 当前无法自动补齐，结果基于已有数据降级输出"
    return review.model_copy(update={
        "status": "fail" if blocked else ("warning" if review.status == "pass" else review.status),
        "issues": issues,
        "can_answer": False if blocked else review.can_answer,
        "confidence_impact": confidence_impact,
    })


def append_partial_repair_issue(
    review: ReviewResult,
    *,
    missing_buckets: list[str],
) -> ReviewResult:
    issues = list(review.issues)
    issues.append({
        "type": "partial_repair",
        "severity": "warning",
        "missing_buckets": list(missing_buckets),
        "message": "补数已执行，但仍有部分 bucket 缺失，本次仅基于可用数据继续画像。",
    })
    confidence_impact = review.confidence_impact or "补数后仍有缺失 bucket，结果基于可用数据降级输出"
    return review.model_copy(update={
        "status": "warning" if review.status == "pass" else review.status,
        "issues": issues,
        "confidence_impact": confidence_impact,
    })


def _expected_modules_for_review(requested_modules: list[str]) -> list[str]:
    if not requested_modules:
        return list(_FULL_MODULE_CHAIN)
    requested = set(requested_modules)
    resolved: list[str] = []
    if any(module in requested for module in {"comprehensive", "product", "ops"}):
        resolved.extend(["app", "behavior", "credit", "comprehensive"])
        if "product" in requested:
            resolved.append("product")
        if "ops" in requested:
            resolved.append("ops")
        return resolved
    for module in ["app", "behavior", "credit"]:
        if module in requested:
            resolved.append(module)
    return resolved


def _required_buckets_for_modules(requested_modules: list[str]) -> set[str]:
    if not requested_modules:
        return {"app", "behavior", "credit"}
    requested = set(requested_modules)
    required = {"app", "behavior", "credit"} & requested
    if any(module in requested for module in {"comprehensive", "product", "ops"}):
        required.update({"app", "behavior", "credit"})
    return required
