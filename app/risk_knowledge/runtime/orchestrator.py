"""Composition root for M2D-9 indexing runtime."""

from __future__ import annotations

from pathlib import Path

from app.auth.database import AuthSessionLocal
from app.core.config import settings
from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRepository
from app.risk_knowledge.runtime.redis_lock import RedisVersionLock
from app.risk_knowledge.runtime.redis_state import RedisIndexingTaskStateStore
from app.risk_knowledge.runtime.runner import IndexingJobRunner, RunnerDependencies


class IndexingOrchestrator:
    def __init__(
        self,
        *,
        redis_client,
        embedding_provider,
        artifact_root: Path | None = None,
        lose_lock_before_activation: bool = False,
    ) -> None:
        dependencies = RunnerDependencies(
            redis_state_store=RedisIndexingTaskStateStore(
                client=redis_client,
                key_prefix=settings.risk_knowledge_redis_key_prefix,
                state_ttl_seconds=settings.risk_knowledge_indexing_state_ttl_seconds,
            ),
            version_lock=RedisVersionLock(
                client=redis_client,
                key_prefix=settings.risk_knowledge_redis_key_prefix,
                ttl_seconds=settings.risk_knowledge_indexing_lock_ttl_seconds,
            ),
            embedding_provider=embedding_provider,
            artifact_root=artifact_root or settings.resolve_path(settings.risk_knowledge_faiss_artifact_dir),
            session_factory=AuthSessionLocal,
        )
        self._runner = IndexingJobRunner(
            dependencies=dependencies,
            lose_lock_before_activation=lose_lock_before_activation,
        )

    def start_initial_index(self, *, parsed_document, document, version):
        return self._runner.run_initial_index(
            parsed_document=parsed_document,
            document=document,
            version=version,
        )

    def start_retry(self, *, parsed_document, document, version, failed_job_id: str):
        with AuthSessionLocal() as db:
            failed_job = SqlAlchemyKnowledgeIngestJobRepository(db).get(failed_job_id)
        if failed_job is None:
            raise ValueError(f"failed job not found: {failed_job_id}")
        return self._runner.run_retry(
            parsed_document=parsed_document,
            document=document,
            version=version,
            failed_job=failed_job,
        )

    def start_rebuild_from_parsed(self, *, parsed_document, document, version):
        return self._runner.run_rebuild_from_parsed(
            parsed_document=parsed_document,
            document=document,
            version=version,
        )

    def start_rebuild_from_persisted_chunks(self, *, document, version, force: bool = False):
        return self._runner.run_rebuild_from_persisted_chunks(
            document=document,
            version=version,
            force=force,
        )
