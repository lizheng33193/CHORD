"""Upstream skill-result aggregation for the comprehensive pipeline."""
from __future__ import annotations

from typing import Any

from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


class ComprehensiveUpstreamProvider:
    """Thin shell that normalises three upstream skill results."""

    _MODULE_KEYS: tuple[tuple[str, str], ...] = (
        ("app_result", "app_profile"),
        ("behavior_result", "behavior_profile"),
        ("credit_result", "credit_profile"),
    )

    def fetch(
        self,
        uid: str,
        context: ComprehensiveRunContext,
        *,
        app_result: dict[str, Any],
        behavior_result: dict[str, Any],
        credit_result: dict[str, Any],
    ) -> ComprehensiveUpstreamBundle:
        results = {
            "app_result": app_result or {},
            "behavior_result": behavior_result or {},
            "credit_result": credit_result or {},
        }
        statuses: dict[str, str] = {}
        missing: list[str] = []
        errors: list[str] = []
        ok_count = 0

        for result_key, module_name in self._MODULE_KEYS:
            res = results[result_key]
            structured = res.get("structured_result") if isinstance(res, dict) else None
            # status lives inside structured_result in real pipeline output,
            # but some callers pass it at the top level — check both.
            status_raw = (
                (structured.get("status") if isinstance(structured, dict) else None)
                or (res.get("status") if isinstance(res, dict) else None)
            )
            if status_raw == "ok" and isinstance(structured, dict) and structured:
                statuses[module_name] = "ok"
                ok_count += 1
            else:
                statuses[module_name] = "missing" if status_raw != "ok" else "degraded"
                missing.append(module_name)
                if status_raw and status_raw != "ok":
                    errors.append(f"{module_name}:{status_raw}")

        data_status = "ok" if ok_count >= 1 else "data_missing"

        return ComprehensiveUpstreamBundle(
            uid=uid,
            country_code=context["country_code"],
            app_result=results["app_result"],
            behavior_result=results["behavior_result"],
            credit_result=results["credit_result"],
            app_status=statuses["app_profile"],
            behavior_status=statuses["behavior_profile"],
            credit_status=statuses["credit_profile"],
            ok_count=ok_count,
            missing_modules=missing,
            data_status=data_status,
            errors=errors,
        )
