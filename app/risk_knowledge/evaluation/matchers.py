"""Matching helpers for M2D-13 evaluation."""

from __future__ import annotations

from app.risk_knowledge.evaluation.schemas import ExpectedCitationRef, ExpectedEvidence


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower()


def _joined_section_path(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " / ".join(str(item) for item in value)
    return ""


def _matches_text_contains(expected: list[str], actual_text: str) -> bool:
    normalized_text = _normalize(actual_text)
    return all(_normalize(token) in normalized_text for token in expected)


def expected_evidence_matches_candidate(expected: ExpectedEvidence, candidate: object) -> bool:
    actual_chunk_id = _normalize(getattr(candidate, "chunk_id", None))
    actual_content_hash = _normalize(getattr(candidate, "content_hash", None))
    actual_section = _normalize(_joined_section_path(getattr(candidate, "section_path", None)))
    actual_text = str(getattr(candidate, "text", "") or "")

    if expected.chunk_id:
        return _normalize(expected.chunk_id) == actual_chunk_id
    if expected.content_hash:
        return _normalize(expected.content_hash) == actual_content_hash
    if expected.section_path_contains and _normalize(expected.section_path_contains) in actual_section:
        return True
    if expected.text_contains:
        return _matches_text_contains(expected.text_contains, actual_text)
    return False


def expected_citation_matches_rendered(expected: ExpectedCitationRef, citation: object) -> bool:
    actual_chunk_id = _normalize(getattr(citation, "chunk_id", None))
    actual_version_id = _normalize(getattr(citation, "version_id", None))
    actual_document_id = _normalize(getattr(citation, "document_id", None))
    actual_section = _normalize(_joined_section_path(getattr(citation, "section_path", None)))

    if expected.chunk_id:
        return _normalize(expected.chunk_id) == actual_chunk_id
    if expected.version_id:
        return _normalize(expected.version_id) == actual_version_id
    if expected.document_id:
        return _normalize(expected.document_id) == actual_document_id
    if expected.section_path_contains:
        return _normalize(expected.section_path_contains) in actual_section
    return False
