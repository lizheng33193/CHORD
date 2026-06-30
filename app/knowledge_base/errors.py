"""Domain errors for the M2D knowledge-base skeleton."""


class KnowledgeBaseError(Exception):
    """Base error for knowledge-base domain failures."""


class KnowledgeBaseNotFoundError(KnowledgeBaseError):
    """Raised when a knowledge base cannot be found."""


class KnowledgeDocumentNotFoundError(KnowledgeBaseError):
    """Raised when a document cannot be found."""


class KnowledgeDocumentVersionNotFoundError(KnowledgeBaseError):
    """Raised when a document version cannot be found."""


class KnowledgeIngestJobNotFoundError(KnowledgeBaseError):
    """Raised when an ingest job cannot be found."""


class InvalidKnowledgeBaseStateTransition(KnowledgeBaseError):
    """Raised when a lifecycle transition is invalid."""


class DuplicateKnowledgeBaseError(KnowledgeBaseError):
    """Raised when a knowledge base already exists."""


class DuplicateKnowledgeDocumentError(KnowledgeBaseError):
    """Raised when a document already exists."""


class DuplicateKnowledgeDocumentVersionError(KnowledgeBaseError):
    """Raised when a document version already exists."""


class DuplicateKnowledgeIngestJobError(KnowledgeBaseError):
    """Raised when an ingest job already exists."""
