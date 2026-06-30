"""Build stable citations from selected evidence."""

from __future__ import annotations

import hashlib

from app.risk_knowledge.evidence.errors import CitationMetadataMissingError
from app.risk_knowledge.evidence.schemas import Citation, SelectedEvidence


class CitationBuilder:
    def build(self, selected_evidence: list[SelectedEvidence]) -> list[Citation]:
        citations: list[Citation] = []
        for evidence in selected_evidence:
            self._validate_required_fields(evidence)
            payload = "::".join(
                [
                    evidence.document_id,
                    evidence.version_id,
                    evidence.chunk_id,
                    evidence.content_hash,
                ]
            )
            citations.append(
                Citation(
                    citation_id=f"cite_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}",
                    evidence_id=evidence.evidence_id,
                    document_id=evidence.document_id,
                    version_id=evidence.version_id,
                    chunk_id=evidence.chunk_id,
                    content_hash=evidence.content_hash,
                    section_path=list(evidence.section_path),
                    page_start=evidence.page_start,
                    page_end=evidence.page_end,
                    manifest_index_id=evidence.manifest_index_id,
                    evidence_rank=evidence.selected_rank,
                )
            )
        return citations

    def _validate_required_fields(self, evidence: SelectedEvidence) -> None:
        for field_name in ("document_id", "version_id", "chunk_id", "content_hash", "manifest_index_id"):
            if not getattr(evidence, field_name):
                raise CitationMetadataMissingError(f"selected evidence missing required field: {field_name}")
