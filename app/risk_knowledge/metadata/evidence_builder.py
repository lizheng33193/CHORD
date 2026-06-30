"""Pure builder that materializes draft `RiskEvidence` from knowledge chunks."""

from __future__ import annotations

from app.knowledge_base.schemas import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion
from app.risk_knowledge.metadata.errors import EmptyMetadataBuildInputError, MetadataInputMismatchError
from app.risk_knowledge.schemas import EvidenceBuildResult, EvidenceUsage, RiskEvidence


class RiskEvidenceBuilder:
    def build(
        self,
        chunks: list[KnowledgeChunk],
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
    ) -> EvidenceBuildResult:
        self._validate_inputs(chunks, document, version)
        evidence = [
            RiskEvidence(
                evidence_id=f"ev_{chunk.chunk_id}",
                kb_id=chunk.kb_id,
                doc_id=chunk.doc_id,
                doc_title=document.doc_title,
                version_id=chunk.version_id,
                chunk_id=chunk.chunk_id,
                section_title=chunk.section_title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                score=None,
                text=chunk.content,
                usage=EvidenceUsage.SUPPORTING_EVIDENCE,
            )
            for chunk in chunks
        ]
        return EvidenceBuildResult(evidence=evidence)

    def _validate_inputs(
        self,
        chunks: list[KnowledgeChunk],
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
    ) -> None:
        if not chunks:
            raise EmptyMetadataBuildInputError("chunks must not be empty")
        if not document.doc_title.strip():
            raise MetadataInputMismatchError("document.doc_title must not be empty")
        for chunk in chunks:
            if chunk.kb_id != document.kb_id or document.kb_id != version.kb_id:
                raise MetadataInputMismatchError("kb_id mismatch between chunk, document, and version")
            if chunk.doc_id != document.doc_id or document.doc_id != version.doc_id:
                raise MetadataInputMismatchError("doc_id mismatch between chunk, document, and version")
            if chunk.version_id != version.version_id:
                raise MetadataInputMismatchError("version_id mismatch between chunk and version")
