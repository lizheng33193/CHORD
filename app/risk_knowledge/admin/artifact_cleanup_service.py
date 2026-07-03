"""Dry-run-first cleanup governance for risk knowledge artifacts."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge_base.models import KnowledgeDocumentVersionModel
from app.risk_knowledge.admin.schemas import ArtifactCleanupEntry, ArtifactCleanupResponse
from app.risk_knowledge.persistence.models import FaissIndexManifestRecord


class ArtifactCleanupService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def cleanup(self, *, dry_run: bool = True, root: str | None = None) -> ArtifactCleanupResponse:
        upload_root = settings.resolve_path(settings.risk_knowledge_upload_dir).resolve()
        faiss_root = settings.resolve_path(settings.risk_knowledge_faiss_artifact_dir).resolve()
        managed_roots = {upload_root, faiss_root}

        if root is not None:
            candidate_root = Path(root).resolve()
            if not any(self._is_within(candidate_root, managed_root) or candidate_root == managed_root for managed_root in managed_roots):
                raise ValueError(f"unmanaged cleanup root: {candidate_root}")
            scan_roots = {candidate_root}
        else:
            scan_roots = managed_roots

        protected: list[ArtifactCleanupEntry] = []
        candidates: list[ArtifactCleanupEntry] = []

        referenced_uploads = {
            str(Path(path).resolve())
            for path in self._db.scalars(select(KnowledgeDocumentVersionModel.file_uri)).all()
            if path
        }
        manifests = list(self._db.scalars(select(FaissIndexManifestRecord)).all())
        active_manifest_paths = set()
        inactive_manifest_paths = set()
        for manifest in manifests:
            artifact_path = str(Path(manifest.artifact_path).resolve())
            mapping_path = str(Path(manifest.mapping_path).resolve())
            if manifest.is_active:
                active_manifest_paths.update({artifact_path, mapping_path})
            else:
                inactive_manifest_paths.update({artifact_path, mapping_path})

        for path in sorted(referenced_uploads):
            if self._matches_scan_roots(path, scan_roots):
                protected.append(ArtifactCleanupEntry(path=path, reason="version_upload"))

        for path in sorted(active_manifest_paths):
            if self._matches_scan_roots(path, scan_roots):
                protected.append(ArtifactCleanupEntry(path=path, reason="active_manifest"))

        for path in sorted(inactive_manifest_paths):
            if self._matches_scan_roots(path, scan_roots):
                candidates.append(ArtifactCleanupEntry(path=path, reason="inactive_manifest"))

        if faiss_root.exists() and any(self._is_within(faiss_root, root_path) or faiss_root == root_path for root_path in scan_roots):
            for path in faiss_root.rglob("*.tmp"):
                if path.is_file():
                    candidates.append(ArtifactCleanupEntry(path=str(path.resolve()), reason="temporary_artifact"))

        if upload_root.exists() and any(self._is_within(upload_root, root_path) or upload_root == root_path for root_path in scan_roots):
            for path in upload_root.rglob("*"):
                if not path.is_file():
                    continue
                resolved = str(path.resolve())
                if resolved in referenced_uploads:
                    continue
                candidates.append(ArtifactCleanupEntry(path=resolved, reason="unreferenced_upload"))

        candidate_entries = self._dedupe_entries(candidates)
        deleted_entries: list[ArtifactCleanupEntry] = []
        if not dry_run:
            for entry in candidate_entries:
                path = Path(entry.path)
                try:
                    if path.exists() and path.is_file():
                        path.unlink()
                        deleted_entries.append(entry)
                except OSError:
                    continue

        return ArtifactCleanupResponse(
            dry_run=dry_run,
            candidates=candidate_entries,
            deleted=[] if dry_run else deleted_entries,
            protected=self._dedupe_entries(protected),
        )

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @classmethod
    def _matches_scan_roots(cls, value: str, scan_roots: set[Path]) -> bool:
        path = Path(value).resolve()
        return any(cls._is_within(path, root) or path == root for root in scan_roots)

    @staticmethod
    def _dedupe_entries(entries: list[ArtifactCleanupEntry]) -> list[ArtifactCleanupEntry]:
        seen: dict[tuple[str, str], ArtifactCleanupEntry] = {}
        for entry in entries:
            seen[(entry.path, entry.reason)] = entry
        return list(seen.values())
