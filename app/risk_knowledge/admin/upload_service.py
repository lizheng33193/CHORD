"""Document upload handling for M2D-14A."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge_base.id_factory import build_version_id
from app.knowledge_base.errors import KnowledgeDocumentNotFoundError
from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository
from app.knowledge_base.schemas import SourceType
from app.knowledge_base.services.document_service import DocumentService
from app.risk_knowledge.admin.errors import (
    DocumentTooLargeAdminError,
    KnowledgeDocumentMissingAdminError,
    UnsupportedDocumentTypeAdminError,
)
from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService
from app.risk_knowledge.admin.schemas import UploadVersionResult

_NON_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_EXTENSION_TO_SOURCE_TYPE = {
    "pdf": SourceType.PDF,
    "docx": SourceType.DOCX,
    "md": SourceType.MARKDOWN,
    "txt": SourceType.TXT,
}


class KnowledgeDocumentUploadService:
    def __init__(
        self,
        db: Session,
        *,
        indexing_service_factory: Callable[[Session], IndexingAdminService] | None = None,
    ) -> None:
        self._db = db
        self._document_service = DocumentService(SqlAlchemyKnowledgeDocumentRepository(db))
        self._indexing_service_factory = indexing_service_factory or (lambda session: IndexingAdminService(session))

    def upload_document_version(
        self,
        *,
        document_id: str,
        upload,
        version_label: str | None,
        auto_index: bool,
    ) -> UploadVersionResult:
        filename = self._sanitize_filename(upload.filename or "upload.bin")
        extension = self._get_extension(filename)
        source_type = self._resolve_source_type(extension)
        if source_type is None:
            raise UnsupportedDocumentTypeAdminError(
                "unsupported document type",
                resource_id=filename,
            )

        try:
            document = self._document_service._get_document(document_id)  # noqa: SLF001 - localized admin seam
        except KnowledgeDocumentNotFoundError as exc:
            raise KnowledgeDocumentMissingAdminError(
                "knowledge document not found",
                resource_id=document_id,
            ) from exc
        upload_root = self._resolve_upload_root()
        doc_dir = (upload_root / document_id).resolve()
        doc_dir.mkdir(parents=True, exist_ok=True)
        if upload_root not in doc_dir.parents and doc_dir != upload_root:
            raise ValueError("resolved upload path escaped upload dir")

        stored_filename = f"{uuid4().hex}_{filename}"
        final_path = (doc_dir / stored_filename).resolve()
        if upload_root not in final_path.parents:
            raise ValueError("resolved file path escaped upload dir")

        file_hash, file_size = self._write_upload(upload.file, final_path)
        self._document_service._repository.update_document(  # noqa: SLF001 - localized admin seam
            document.model_copy(
                update={
                    "doc_name": filename,
                    "source_type": source_type,
                    "source_uri": str(final_path),
                }
            )
        )
        version = self._document_service.create_document_version(
            version_id=build_version_id(document_id, version_label or "v1"),
            doc_id=document_id,
            kb_id=document.kb_id,
            version=version_label or "v1",
            file_hash=file_hash,
            file_uri=str(final_path),
            parser_version=None,
            chunker_version=None,
            embedding_model=None,
            embedding_dim=None,
            index_name=None,
        )
        self._db.commit()
        indexing_job_id = None
        if auto_index:
            launch = self._indexing_service_factory(self._db).start_index(version.version_id)
            indexing_job_id = launch.job_id

        return UploadVersionResult(
            document_id=document_id,
            version_id=version.version_id,
            filename=filename,
            file_size_bytes=file_size,
            file_hash=file_hash,
            stored_path=str(final_path),
            indexing_job_id=indexing_job_id,
        )

    def _resolve_upload_root(self) -> Path:
        path_value = getattr(settings, "risk_knowledge_upload_dir", "storage/risk_knowledge/uploads")
        return settings.resolve_path(path_value).resolve()

    def _max_upload_bytes(self) -> int:
        mb = int(getattr(settings, "risk_knowledge_max_upload_mb", 50))
        return max(mb, 0) * 1024 * 1024

    def _resolve_source_type(self, extension: str) -> SourceType | None:
        allowed = {
            item.strip().lower()
            for item in str(getattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt")).split(",")
            if item.strip()
        }
        if extension not in allowed:
            return None
        return _EXTENSION_TO_SOURCE_TYPE.get(extension)

    def _write_upload(self, file_obj, final_path: Path) -> tuple[str, int]:
        max_bytes = self._max_upload_bytes()
        hasher = hashlib.sha256()
        bytes_written = 0
        fd, temp_path_raw = tempfile.mkstemp(prefix=".upload_", dir=str(final_path.parent))
        temp_path = Path(temp_path_raw)
        try:
            with os.fdopen(fd, "wb") as handle:
                while True:
                    chunk = file_obj.read(64 * 1024)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise DocumentTooLargeAdminError(
                            "document exceeds upload size limit",
                            resource_id=final_path.name,
                        )
                    hasher.update(chunk)
                    handle.write(chunk)
            os.replace(temp_path, final_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            try:
                file_obj.seek(0)
            except Exception:
                pass

        return f"sha256:{hasher.hexdigest()}", bytes_written

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        cleaned = _NON_FILENAME_CHARS.sub("_", Path(filename).name).strip("._")
        return cleaned or "upload.bin"

    @staticmethod
    def _get_extension(filename: str) -> str:
        return Path(filename).suffix.lower().lstrip(".")
