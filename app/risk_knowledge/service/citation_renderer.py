"""Render answer-facing citation labels from structured evidence citations."""

from __future__ import annotations

from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.service.schemas import RenderedCitation


class CitationRenderer:
    def render(self, bundle: RiskEvidenceBundle) -> list[RenderedCitation]:
        evidence_by_id = {item.evidence_id: item for item in bundle.selected_evidence}
        rendered: list[RenderedCitation] = []
        for position, citation in enumerate(bundle.citations, start=1):
            evidence = evidence_by_id.get(citation.evidence_id)
            section_bits = list(citation.section_path)
            document_title = section_bits[0] if section_bits else citation.document_id
            section_path = " / ".join(section_bits) if section_bits else None
            page_suffix = ""
            if citation.page_start is not None and citation.page_end is not None:
                if citation.page_start == citation.page_end:
                    page_suffix = f" / p.{citation.page_start}"
                else:
                    page_suffix = f" / p.{citation.page_start}-{citation.page_end}"
            label = f"[{position}] {document_title}"
            if section_path:
                label = f"{label} / {' / '.join(section_bits[1:])}" if len(section_bits) > 1 else label
            label = f"{label}{page_suffix}"
            rendered.append(
                RenderedCitation(
                    citation_id=citation.citation_id,
                    label=label,
                    document_id=citation.document_id,
                    document_title=document_title,
                    version_id=citation.version_id,
                    chunk_id=citation.chunk_id,
                    evidence_id=citation.evidence_id,
                    section_path=section_path,
                    page_start=evidence.page_start if evidence else citation.page_start,
                    page_end=evidence.page_end if evidence else citation.page_end,
                    quote=(evidence.text[:160] if evidence is not None else None),
                )
            )
        return rendered
