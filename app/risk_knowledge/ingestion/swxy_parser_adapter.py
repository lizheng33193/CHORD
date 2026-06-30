"""SWXY-compatible parser/chunker adapter for M2D-6."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.knowledge_base.schemas import SourceType
from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.errors import (
    EmptyParsedDocumentError,
    SwxyParserExecutionError,
    SwxyParserUnavailableError,
    UnsupportedSourceTypeError,
)
from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef


class SwxyParserAdapter:
    def __init__(self, chunker: Callable[..., Any] | None = None) -> None:
        self._chunker = chunker

    def parse(self, context: IngestionContext) -> ParsedDocument:
        self._validate_source_type(context.source_type)
        chunker = self._chunker or self._load_default_chunker()
        try:
            raw_output = chunker(
                filename=context.file_path,
                binary=None,
                from_page=0,
                to_page=100000,
                callback=self._noop_callback,
            )
        except SwxyParserUnavailableError:
            raise
        except Exception as exc:
            raise SwxyParserExecutionError(f"SWXY parser execution failed: {exc}") from exc

        raw_chunks = self._normalize_chunks(raw_output)
        if not raw_chunks:
            raise EmptyParsedDocumentError("SWXY parser returned no usable chunks")

        return ParsedDocument(
            source=SourceDocumentRef(
                kb_id=context.kb_id,
                doc_id=context.doc_id,
                version_id=context.version_id,
                file_path=context.file_path,
                doc_name=context.doc_name,
                source_type=context.source_type,
            ),
            parser_name=context.parser_name,
            parser_version="app.third_party.swxy_rag.rag.app.naive.chunk",
            raw_chunks=raw_chunks,
            document_metadata={"source_type": context.source_type.value, "doc_name": context.doc_name},
        )

    def _load_default_chunker(self) -> Callable[..., Any]:
        try:
            from app.third_party.swxy_rag.rag.app.naive import chunk
        except Exception as exc:
            raise SwxyParserUnavailableError(f"failed to load vendored SWXY chunker: {exc}") from exc
        return chunk

    def _validate_source_type(self, source_type: SourceType) -> None:
        supported_types = {
            SourceType.PDF,
            SourceType.DOCX,
            SourceType.DOC,
            SourceType.MARKDOWN,
            SourceType.TXT,
            SourceType.HTML,
            SourceType.JSON,
            SourceType.XLSX,
            SourceType.XLS,
        }
        if source_type not in supported_types:
            raise UnsupportedSourceTypeError(f"unsupported source type for M2D-6: {source_type.value}")

    def _normalize_chunks(self, raw_output: Any) -> list[RawParsedChunk]:
        if raw_output is None:
            return []
        if not isinstance(raw_output, list):
            raise SwxyParserExecutionError("SWXY parser output must be a list of chunk-like objects")

        chunks: list[RawParsedChunk] = []
        for index, item in enumerate(raw_output, start=1):
            normalized = self._normalize_chunk_item(index, item)
            if normalized is not None:
                chunks.append(normalized)
        return chunks

    def _normalize_chunk_item(self, chunk_order: int, item: Any) -> RawParsedChunk | None:
        if not isinstance(item, dict):
            raise SwxyParserExecutionError("SWXY chunk items must be dict-like for M2D-6")

        raw_content = self._extract_raw_content(item)
        if not raw_content:
            return None

        page_start, page_end = self._extract_page_range(item)
        position = self._extract_position(item)
        source_metadata = self._extract_source_metadata(item)

        return RawParsedChunk(
            chunk_order=chunk_order,
            raw_content=raw_content,
            chunk_type=self._string_or_none(item.get("chunk_type")) or self._string_or_none(item.get("raw_chunk_type")),
            title=self._string_or_none(item.get("title")),
            section_title=self._string_or_none(item.get("section_title")) or self._string_or_none(item.get("title")),
            section_path=self._normalize_section_path(item.get("section_path")),
            page_start=page_start,
            page_end=page_end,
            position=position,
            source_metadata=source_metadata,
        )

    def _extract_raw_content(self, item: dict[str, Any]) -> str | None:
        for key in ("content_with_weight", "content", "text", "page_content"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_page_range(self, item: dict[str, Any]) -> tuple[int | None, int | None]:
        page_start = self._normalize_positive_int(item.get("page_start"))
        page_end = self._normalize_positive_int(item.get("page_end"))
        page_num = self._normalize_positive_int(item.get("page_num_int"))
        if page_num is not None:
            page_start = page_start or page_num
            page_end = page_end or page_num
        if page_start is not None and page_end is not None and page_end < page_start:
            raise SwxyParserExecutionError("invalid page range from SWXY chunk output")
        return page_start, page_end

    def _extract_position(self, item: dict[str, Any]) -> dict[str, Any] | None:
        position: dict[str, Any] = {}
        if item.get("position_int") is not None:
            position["position_int"] = item.get("position_int")
        if item.get("top_int") is not None:
            position["top_int"] = item.get("top_int")
        return position or None

    def _extract_source_metadata(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata_keys = (
            "docnm_kwd",
            "doc_id",
            "title_tks",
            "content_ltks",
            "content_sm_ltks",
            "top_int",
            "position_int",
            "chunk_type",
        )
        metadata = {key: item[key] for key in metadata_keys if key in item}
        metadata["original_keys"] = sorted(item.keys())
        if "chunk_type" in item:
            metadata["raw_chunk_type"] = item["chunk_type"]
        return metadata

    def _normalize_section_path(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return [str(value)] if str(value).strip() else []

    def _normalize_positive_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 1 else None

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _noop_callback(*_args: Any, **_kwargs: Any) -> None:
        return None
