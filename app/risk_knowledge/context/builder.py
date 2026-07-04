"""Task-based context isolation for Risk QA."""

from __future__ import annotations

import hashlib

from app.risk_knowledge.context.schemas import ContextBuildRequest, ContextBuildResult
from app.risk_knowledge.service.schemas import RiskQaWarning


_POLICY: dict[str, dict[str, list[str]]] = {
    "risk_knowledge_answer": {
        "allow": ["risk_domain_knowledge"],
        "block": [
            "data_knowledge",
            "sql_examples",
            "sql_error_cases",
            "catalog_grounding",
            "memory_as_authority",
        ],
    },
    "data_agent": {
        "allow": ["data_knowledge"],
        "block": ["risk_domain_knowledge_as_field_grounding"],
    },
}


class RiskQaContextBuilder:
    def build(self, request: ContextBuildRequest) -> ContextBuildResult:
        policy = _POLICY.get(request.task_type, {"allow": [], "block": []})
        blocked = list(policy["block"])
        warnings = [
            RiskQaWarning(
                code="RISK_QA_CONTEXT_SOURCE_BLOCKED",
                severity="info",
                message="Context isolation policy blocked non-authoritative sources.",
                detail={"blocked_context_sources": blocked},
            )
        ] if blocked else []
        return ContextBuildResult(
            task_type=request.task_type,
            allowed_context_sources=list(policy["allow"]),
            blocked_context_sources=blocked,
            context_hash=self.compute_hash(
                task_type=request.task_type,
                query=request.query,
                selected_evidence_ids=request.selected_evidence_ids,
                blocked_context_sources=blocked,
            ),
            isolation_warnings=warnings,
        )

    @staticmethod
    def compute_hash(
        *,
        task_type: str,
        query: str,
        selected_evidence_ids: list[str],
        blocked_context_sources: list[str],
    ) -> str:
        payload = "::".join(
            [
                task_type.strip(),
                query.strip(),
                ",".join(sorted(selected_evidence_ids)),
                ",".join(sorted(blocked_context_sources)),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
