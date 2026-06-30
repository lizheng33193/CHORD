"""Ingestion adapter boundary for M2D-6."""

from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.ingestion_pipeline import SwxyIngestionPipeline
from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef
from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter

__all__ = [
    "IngestionContext",
    "ParsedDocument",
    "RawParsedChunk",
    "SourceDocumentRef",
    "SwxyIngestionPipeline",
    "SwxyParserAdapter",
]
