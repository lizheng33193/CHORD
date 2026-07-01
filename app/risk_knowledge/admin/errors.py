"""Typed admin-facing errors for M2D-14A."""

from __future__ import annotations


class KnowledgeBaseAdminError(Exception):
    code = "KNOWLEDGE_BASE_ADMIN_ERROR"
    status_code = 400

    def __init__(
        self,
        message: str,
        *,
        resource_id: str | None = None,
        state: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.resource_id = resource_id
        self.state = state

    def to_detail(self) -> dict[str, str]:
        detail = {"code": self.code, "message": self.message}
        if self.resource_id:
            detail["resource_id"] = self.resource_id
        if self.state:
            detail["state"] = self.state
        return detail


class KnowledgeBaseAlreadyExistsAdminError(KnowledgeBaseAdminError):
    code = "KNOWLEDGE_BASE_ALREADY_EXISTS"
    status_code = 409


class KnowledgeBaseMissingAdminError(KnowledgeBaseAdminError):
    code = "KNOWLEDGE_BASE_NOT_FOUND"
    status_code = 404


class KnowledgeDocumentAlreadyExistsAdminError(KnowledgeBaseAdminError):
    code = "KNOWLEDGE_DOCUMENT_ALREADY_EXISTS"
    status_code = 409


class KnowledgeDocumentMissingAdminError(KnowledgeBaseAdminError):
    code = "KNOWLEDGE_DOCUMENT_NOT_FOUND"
    status_code = 404


class KnowledgeDocumentVersionMissingAdminError(KnowledgeBaseAdminError):
    code = "KNOWLEDGE_DOCUMENT_VERSION_NOT_FOUND"
    status_code = 404


class IndexingJobMissingAdminError(KnowledgeBaseAdminError):
    code = "INDEXING_JOB_NOT_FOUND"
    status_code = 404


class ManifestMissingAdminError(KnowledgeBaseAdminError):
    code = "MANIFEST_NOT_FOUND"
    status_code = 404


class RunningIndexingJobConflictAdminError(KnowledgeBaseAdminError):
    code = "RUNNING_INDEXING_JOB_CONFLICT"
    status_code = 409


class RetryNotAllowedAdminError(KnowledgeBaseAdminError):
    code = "INDEXING_JOB_RETRY_NOT_ALLOWED"
    status_code = 409


class InvalidActivationStateAdminError(KnowledgeBaseAdminError):
    code = "INVALID_ACTIVATION_STATE"
    status_code = 409


class InvalidAdminRequestError(KnowledgeBaseAdminError):
    code = "INVALID_ADMIN_REQUEST"
    status_code = 400


class UnsupportedDocumentTypeAdminError(KnowledgeBaseAdminError):
    code = "UNSUPPORTED_DOCUMENT_TYPE"
    status_code = 400


class DocumentTooLargeAdminError(KnowledgeBaseAdminError):
    code = "DOCUMENT_TOO_LARGE"
    status_code = 400
