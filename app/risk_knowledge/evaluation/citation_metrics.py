"""Citation metrics for M2D-13."""

from __future__ import annotations

from app.risk_knowledge.evaluation.matchers import expected_citation_matches_rendered
from app.risk_knowledge.evaluation.schemas import CitationMetrics, GoldenEvaluationCase
from app.risk_knowledge.evidence.schemas import Citation, SelectedEvidence
from app.risk_knowledge.service.schemas import RenderedCitation


def calculate_citation_metrics(
    *,
    case: GoldenEvaluationCase,
    rendered_citations: list[RenderedCitation],
    bundle_citations: list[Citation],
    selected_evidence: list[SelectedEvidence],
    should_answer: bool,
) -> CitationMetrics:
    citation_present = len(rendered_citations) > 0
    invalid_citation_count = 0
    bundle_by_id = {citation.citation_id: citation for citation in bundle_citations}
    evidence_ids = {evidence.evidence_id for evidence in selected_evidence}

    for rendered in rendered_citations:
        bundle_citation = bundle_by_id.get(rendered.citation_id)
        if bundle_citation is None or bundle_citation.evidence_id not in evidence_ids:
            invalid_citation_count += 1
            continue
        if case.expected_citation_refs and not any(
            expected_citation_matches_rendered(expected, rendered) for expected in case.expected_citation_refs
        ):
            invalid_citation_count += 1

    missing_expected_citation = bool(case.expected_citation_refs) and not all(
        any(expected_citation_matches_rendered(expected, rendered) for rendered in rendered_citations)
        for expected in case.expected_citation_refs
    )
    citation_correct = (
        (citation_present if should_answer else True)
        and invalid_citation_count == 0
        and not missing_expected_citation
    )
    return CitationMetrics(
        citation_present=citation_present,
        citation_correct=citation_correct,
        citation_count=len(rendered_citations),
        missing_expected_citation=missing_expected_citation,
        invalid_citation_count=invalid_citation_count,
    )
