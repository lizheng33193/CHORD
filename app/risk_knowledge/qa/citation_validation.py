"""Citation validation gate for PR-A Risk QA."""

from __future__ import annotations

from app.risk_knowledge.qa.schemas import CitationValidationResult
from app.risk_knowledge.service.schemas import EvidenceTraceItem, RenderedCitation, RiskQaWarning


class CitationValidator:
    def validate(
        self,
        *,
        citations: list[RenderedCitation],
        evidence_trace: list[EvidenceTraceItem],
        used_citation_ids: list[str],
    ) -> CitationValidationResult:
        warnings: list[RiskQaWarning] = []
        blockers: list[RiskQaWarning] = []
        citation_by_id = {citation.citation_id: citation for citation in citations}
        evidence_by_id = {item.evidence_id: item for item in evidence_trace}

        if not citations or not used_citation_ids:
            blockers.append(
                RiskQaWarning(
                    code="RISK_QA_CITATION_MISSING",
                    severity="blocker",
                    message="Grounded answers must include at least one valid citation.",
                )
            )

        for citation_id in used_citation_ids:
            citation = citation_by_id.get(citation_id)
            if citation is None:
                blockers.append(
                    RiskQaWarning(
                        code="RISK_QA_CITATION_NOT_IN_SELECTED_EVIDENCE",
                        severity="blocker",
                        message="Answer referenced a citation that was not rendered from selected evidence.",
                        detail={"citation_id": citation_id},
                    )
                )
                continue
            if not citation.chunk_id:
                blockers.append(
                    RiskQaWarning(
                        code="RISK_QA_CITATION_MISSING",
                        severity="blocker",
                        message="Rendered citation is missing chunk provenance.",
                        detail={"citation_id": citation_id},
                    )
                )
            evidence = evidence_by_id.get(citation.evidence_id or "")
            if evidence is None:
                blockers.append(
                    RiskQaWarning(
                        code="RISK_QA_CITATION_NOT_IN_SELECTED_EVIDENCE",
                        severity="blocker",
                        message="Citation does not resolve to selected evidence.",
                        detail={"citation_id": citation_id, "evidence_id": citation.evidence_id},
                    )
                )
                continue
            if evidence.source_type != "risk_domain_knowledge":
                blockers.append(
                    RiskQaWarning(
                        code="RISK_QA_CITATION_INVALID_SOURCE",
                        severity="blocker",
                        message="Citation source must remain within risk domain knowledge evidence.",
                        detail={"source_type": evidence.source_type},
                    )
                )
            if citation.page_start is None or citation.page_end is None:
                warnings.append(
                    RiskQaWarning(
                        code="RISK_QA_CITATION_PAGE_MISSING",
                        severity="warning",
                        message="Citation is missing page metadata.",
                        detail={"citation_id": citation_id},
                    )
                )

        return CitationValidationResult(
            passed=not blockers,
            citations=citations,
            warnings=warnings,
            blockers=blockers,
            used_citation_ids=list(used_citation_ids),
        )
