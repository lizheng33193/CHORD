"""Deterministic SQL semantic validation service for PR-C."""

from __future__ import annotations

import re

from app.data_agent.semantic_validation.schemas import (
    SqlSemanticValidationRequest,
    SqlSemanticValidationResult,
    SqlSemanticViolation,
)

_RISKY_SQL_OPERATION_RE = re.compile(
    r"^\s*(update|delete|truncate|drop|alter|insert|create|replace|merge)\b",
    re.IGNORECASE,
)
_CROSS_JOIN_RE = re.compile(r"\bcross\s+join\b", re.IGNORECASE)
_JOIN_ON_UID_RE = re.compile(r"\bjoin\b[\s\S]+?\bon\b[\s\S]*?\buid\b", re.IGNORECASE)
_WHERE_UID_RE = re.compile(r"\bwhere\b[\s\S]*?\buid\b", re.IGNORECASE)
_BEHAVIOR_TABLE_RE = re.compile(r"\bdwb_b1_data_burying_point\b", re.IGNORECASE)
_DATE_TOKEN_RE = re.compile(r"\b(dt|date|time|timestamp_|apply_time)\b", re.IGNORECASE)


def validate_sql_semantics(request: SqlSemanticValidationRequest) -> SqlSemanticValidationResult:
    sql = request.sql.strip()
    structured_plan = dict(request.structured_sql_plan or {})
    violations: list[SqlSemanticViolation] = []

    expected_country = str(request.expected_country or "").strip().lower()
    plan_country = str(structured_plan.get("country") or "").strip().lower()
    if expected_country and plan_country and expected_country != plan_country:
        violations.append(
            SqlSemanticViolation(
                code="COUNTRY_SCOPE_MISMATCH",
                severity="critical",
                message=f"Structured plan country `{plan_country}` does not match expected country `{expected_country}`.",
                suggestion="Align the structured_sql_plan country with the runtime request country before approval.",
                blocking=True,
            )
        )

    if _RISKY_SQL_OPERATION_RE.search(sql) or _CROSS_JOIN_RE.search(sql):
        violations.append(
            SqlSemanticViolation(
                code="RISKY_SQL_OPERATION",
                severity="critical",
                message="SQL contains a risky write or expansion operation that is outside the allowed query-only boundary.",
                suggestion="Restrict the candidate to safe read-only SQL or keep it in a controlled writeback-only review path.",
                blocking=True,
            )
        )

    uid_boundary_required = bool(structured_plan.get("uid_boundary_required"))
    if uid_boundary_required and not (_JOIN_ON_UID_RE.search(sql) or _WHERE_UID_RE.search(sql)):
        violations.append(
            SqlSemanticViolation(
                code="UID_BOUNDARY_MISSING",
                severity="error",
                message="SQL requires an explicit uid boundary but no uid join or uid filter was detected.",
                field="uid",
                suggestion="Add a uid join, uid filter, or target cohort CTE before approval.",
                blocking=True,
            )
        )

    if _BEHAVIOR_TABLE_RE.search(sql) and "join" not in sql.lower() and "where" not in sql.lower():
        violations.append(
            SqlSemanticViolation(
                code="BROAD_SCAN_RISK",
                severity="warning",
                message="Behavior-table SQL appears to scan broadly without cohort or filter constraints.",
                table="dwb_b1_data_burying_point",
                suggestion="Constrain behavior-table queries with cohort joins, uid boundaries, or scoped filters.",
                blocking=False,
            )
        )

    if request.expected_time_window and not _DATE_TOKEN_RE.search(sql):
        violations.append(
            SqlSemanticViolation(
                code="TIME_WINDOW_UNSPECIFIED",
                severity="warning",
                message="Expected time-window semantics were provided but no time field was detected in SQL.",
                suggestion="Add a business-time or partition-time constraint that matches the request intent.",
                blocking=False,
            )
        )

    if not violations:
        return SqlSemanticValidationResult(
            validation_status="passed",
            violations=[],
            requires_human_review=False,
        )

    if any(item.blocking for item in violations):
        return SqlSemanticValidationResult(
            validation_status="blocked",
            violations=violations,
            requires_human_review=True,
        )

    return SqlSemanticValidationResult(
        validation_status="needs_human_review",
        violations=violations,
        requires_human_review=True,
    )
