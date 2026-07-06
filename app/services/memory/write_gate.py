"""M4-2 write gate implementation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.services.memory.dedupe import build_memory_dedupe_key
from app.services.memory.records import (
    MemoryRecordDraft,
    MemoryWriteDecision,
    MemoryWriteRejectReason,
    MemoryWriteStatus,
)
from app.services.memory.redaction import redact_memory_content
from app.services.memory.store_adapter import MemoryStoreAdapter


class MemoryWriteGate:
    def __init__(
        self,
        *,
        store: MemoryStoreAdapter | None = None,
        require_scope: bool = True,
        min_importance: float = 0.0,
        min_confidence: float = 0.0,
        allow_store_write: bool = False,
    ) -> None:
        self._store = store
        self._require_scope = require_scope
        self._min_importance = float(min_importance)
        self._min_confidence = float(min_confidence)
        self._allow_store_write = allow_store_write

    def evaluate(self, candidate: Any) -> MemoryWriteDecision:
        required_fields = (
            "content",
            "memory_source_type",
            "authority_level",
            "allowed_memory_use",
            "forbidden_memory_use",
            "user_id",
            "project_id",
            "country",
            "session_id",
            "source_run_id",
            "source_artifact_id",
            "evidence_status",
            "importance",
            "confidence",
            "metadata",
        )
        missing = [field for field in required_fields if not hasattr(candidate, field)]
        if missing:
            return self._reject(
                "candidate missing required fields",
                MemoryWriteRejectReason.INVALID_CANDIDATE,
                metadata={"missing_fields": missing},
            )

        content = str(getattr(candidate, "content", "") or "").strip()
        if not content:
            return self._reject("memory content is empty", MemoryWriteRejectReason.EMPTY_CONTENT)

        allowed_uses = _string_values(getattr(candidate, "allowed_memory_use"))
        if not allowed_uses:
            return self._reject("allowed memory use is required", MemoryWriteRejectReason.MISSING_ALLOWED_USE)

        forbidden_uses = _string_values(getattr(candidate, "forbidden_memory_use"))
        if not forbidden_uses:
            return self._reject(
                "forbidden memory use is required",
                MemoryWriteRejectReason.MISSING_FORBIDDEN_USE,
            )

        user_id = _optional_text(getattr(candidate, "user_id", None))
        project_id = _optional_text(getattr(candidate, "project_id", None))
        country = _optional_text(getattr(candidate, "country", None))
        if self._require_scope and not user_id:
            return self._reject("user_id is required for memory writes", MemoryWriteRejectReason.MISSING_SCOPE)

        redaction = redact_memory_content(content)
        if redaction.rejected:
            return self._reject(
                redaction.reason or "secret-like content detected",
                MemoryWriteRejectReason.SECRET_DETECTED,
                metadata={"findings": list(redaction.findings)},
            )

        importance = _float_value(getattr(candidate, "importance", 0.0))
        if importance < self._min_importance:
            return self._reject("importance below write threshold", MemoryWriteRejectReason.LOW_IMPORTANCE)

        confidence = _float_value(getattr(candidate, "confidence", 0.0))
        if confidence < self._min_confidence:
            return self._reject("confidence below write threshold", MemoryWriteRejectReason.LOW_CONFIDENCE)

        dedupe_key = build_memory_dedupe_key(candidate)
        if self._store is not None and self._store.exists_by_dedupe_key(dedupe_key):
            return MemoryWriteDecision(
                status=MemoryWriteStatus.SKIPPED_DUPLICATE,
                accepted=False,
                persisted=False,
                reason="duplicate memory candidate skipped",
                reject_reason=MemoryWriteRejectReason.DUPLICATE,
                dedupe_key=dedupe_key,
                metadata={"write_gate": {"status": MemoryWriteStatus.SKIPPED_DUPLICATE.value}},
            )

        source_type = _value(getattr(candidate, "memory_source_type"))
        authority_level = _value(getattr(candidate, "authority_level"))
        scope_warnings: list[str] = []
        if not project_id:
            scope_warnings.append("missing_project_id")
        if not country:
            scope_warnings.append("missing_country")
        if not user_id and not self._require_scope:
            scope_warnings.append("missing_user_id")

        metadata_json = {
            "m4_contract_version": "m4-2",
            "memory_source_type": source_type,
            "authority_level": authority_level,
            "allowed_memory_use": allowed_uses,
            "forbidden_memory_use": forbidden_uses,
            "source_run_id": _optional_text(getattr(candidate, "source_run_id", None)),
            "source_artifact_id": _optional_text(getattr(candidate, "source_artifact_id", None)),
            "evidence_status": _optional_text(getattr(candidate, "evidence_status", None)),
            "candidate_metadata": dict(getattr(candidate, "metadata", {}) or {}),
            "scope_warnings": scope_warnings,
            "write_gate": {
                "status": MemoryWriteStatus.ACCEPTED.value,
                "reject_reason": None,
                "redacted": redaction.redacted,
                "dedupe_key": dedupe_key,
                "decision_reason": "accepted",
            },
        }
        draft = MemoryRecordDraft(
            content=content,
            memory_source_type=source_type,
            authority_level=authority_level,
            allowed_memory_use=allowed_uses,
            forbidden_memory_use=forbidden_uses,
            user_id=user_id,
            project_id=project_id,
            country=country,
            session_id=_optional_text(getattr(candidate, "session_id", None)),
            source_run_id=_optional_text(getattr(candidate, "source_run_id", None)),
            source_artifact_id=_optional_text(getattr(candidate, "source_artifact_id", None)),
            evidence_status=_optional_text(getattr(candidate, "evidence_status", None)),
            importance=importance,
            confidence=confidence,
            status="active",
            dedupe_key=dedupe_key,
            metadata_json=metadata_json,
        )
        return MemoryWriteDecision(
            status=MemoryWriteStatus.ACCEPTED,
            accepted=True,
            persisted=False,
            reason="memory candidate accepted by write gate",
            dedupe_key=dedupe_key,
            redacted=redaction.redacted,
            record_draft=draft,
            metadata={"write_gate": metadata_json["write_gate"]},
        )

    def write(self, candidate: Any) -> MemoryWriteDecision:
        decision = self.evaluate(candidate)
        if not decision.accepted or decision.record_draft is None:
            return decision
        if not self._allow_store_write or self._store is None:
            deferred_draft = _with_gate_status(decision.record_draft, MemoryWriteStatus.DEFERRED, "store write deferred")
            return MemoryWriteDecision(
                status=MemoryWriteStatus.DEFERRED,
                accepted=True,
                persisted=False,
                reason="gate passed but store write deferred",
                dedupe_key=decision.dedupe_key,
                redacted=decision.redacted,
                record_draft=deferred_draft,
                metadata={"write_gate": deferred_draft.metadata_json["write_gate"]},
            )
        try:
            memory_id = self._store.add_record(decision.record_draft)
        except Exception as exc:
            return self._reject(
                f"store write failed: {exc}",
                MemoryWriteRejectReason.STORE_UNAVAILABLE,
                dedupe_key=decision.dedupe_key,
            )

        accepted_status = (
            MemoryWriteStatus.REDACTED_AND_ACCEPTED if decision.redacted else MemoryWriteStatus.ACCEPTED
        )
        persisted_draft = _with_gate_status(decision.record_draft, accepted_status, "accepted")
        return MemoryWriteDecision(
            status=accepted_status,
            accepted=True,
            persisted=True,
            reason="memory record persisted",
            memory_id=memory_id,
            dedupe_key=decision.dedupe_key,
            redacted=decision.redacted,
            record_draft=persisted_draft,
            metadata={"write_gate": persisted_draft.metadata_json["write_gate"]},
        )

    def _reject(
        self,
        reason: str,
        reject_reason: MemoryWriteRejectReason,
        *,
        dedupe_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryWriteDecision:
        details = dict(metadata or {})
        details["write_gate"] = {
            "status": MemoryWriteStatus.REJECTED.value,
            "reject_reason": reject_reason.value,
            "redacted": False,
            "dedupe_key": dedupe_key,
            "decision_reason": reason,
        }
        return MemoryWriteDecision(
            status=MemoryWriteStatus.REJECTED,
            accepted=False,
            persisted=False,
            reason=reason,
            reject_reason=reject_reason,
            dedupe_key=dedupe_key,
            metadata=details,
        )


def _string_values(values: Any) -> list[str]:
    try:
        items = list(values)
    except TypeError:
        return []
    normalized = [_value(item) for item in items if _value(item)]
    return normalized


def _value(item: Any) -> str:
    value = getattr(item, "value", item)
    text = str(value or "").strip()
    return text


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _with_gate_status(
    draft: MemoryRecordDraft,
    status: MemoryWriteStatus,
    decision_reason: str,
) -> MemoryRecordDraft:
    metadata_json = dict(draft.metadata_json)
    write_gate = dict(metadata_json.get("write_gate") or {})
    write_gate["status"] = status.value
    write_gate["decision_reason"] = decision_reason
    metadata_json["write_gate"] = write_gate
    return replace(draft, metadata_json=metadata_json)
