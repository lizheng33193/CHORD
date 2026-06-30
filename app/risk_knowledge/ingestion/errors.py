"""Domain errors for the M2D-6 ingestion adapter."""


class RiskKnowledgeIngestionError(Exception):
    """Base error for risk-knowledge ingestion failures."""


class SwxyParserUnavailableError(RiskKnowledgeIngestionError):
    """Raised when the vendored SWXY parser/chunker is unavailable."""


class SwxyParserExecutionError(RiskKnowledgeIngestionError):
    """Raised when the SWXY parser/chunker raises at execution time."""


class UnsupportedSourceTypeError(RiskKnowledgeIngestionError):
    """Raised when the source type is unsupported in M2D-6."""


class EmptyParsedDocumentError(RiskKnowledgeIngestionError):
    """Raised when parsing yields no usable chunk content."""
