from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.risk_knowledge.embedding.base import EmbeddingProvider
from app.risk_knowledge.embedding.errors import (
    EmbeddingDimensionMismatchError,
    EmbeddingInputError,
    EmbeddingProviderUnavailableError,
)
from app.risk_knowledge.embedding.schemas import EmbeddingInput, EmbeddingVectorResult


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-m2d8", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)

    from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    yield

    reset_auth_engine()


class DeterministicTestEmbeddingProvider:
    provider_name = "deterministic_test"

    def embed(self, inputs: list[EmbeddingInput]) -> list[EmbeddingVectorResult]:
        results: list[EmbeddingVectorResult] = []
        for item in inputs:
            vector = [float(len(item.text)), float(len(item.chunk_id))]
            results.append(
                EmbeddingVectorResult(
                    chunk_id=item.chunk_id,
                    content_hash=item.content_hash,
                    provider=self.provider_name,
                    model="deterministic-v1",
                    dimension=2,
                    vector=vector,
                    vector_checksum=f"sha256:{len(item.text)}",
                )
            )
        return results


def test_embedding_provider_protocol_and_batch_service_contract() -> None:
    from app.risk_knowledge.embedding.batch_service import EmbeddingBatchService

    provider = DeterministicTestEmbeddingProvider()
    assert isinstance(provider, EmbeddingProvider)

    service = EmbeddingBatchService(provider=provider, expected_dimension=2)
    result = service.embed_inputs(
        [
            EmbeddingInput(
                chunk_id="risk_guide_202607_chunk_000001",
                content_hash="sha256:content",
                text="贷后风险识别是指...",
            )
        ]
    )

    assert result.records[0].provider == "deterministic_test"
    assert result.records[0].dimension == 2


def test_embedding_batch_service_persists_embedding_records_for_chunks(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.schemas import ChunkStatus, DocumentVersionStatus, KnowledgeChunk, KnowledgeDocumentVersion, PermissionScope, SourceType
    from app.risk_knowledge.embedding.batch_service import EmbeddingBatchService
    from app.risk_knowledge.persistence.service import KnowledgeChunkPersistenceService

    version = KnowledgeDocumentVersion(
        version_id="risk_guide_202607",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-07",
        file_hash="sha256:file",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy-parser-v1",
        chunker_version="chunker-v1",
        embedding_model=None,
        embedding_dim=None,
        index_name=None,
        status=DocumentVersionStatus.PARSED,
    )
    chunk = KnowledgeChunk(
        chunk_id="risk_guide_202607_chunk_000001",
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        chunk_order=1,
        chunk_type="paragraph",
        section_title="贷后风险识别",
        section_path=["智能风控指南", "贷后风险识别"],
        page_start=12,
        page_end=12,
        content="贷后风险识别是指...",
        content_hash="sha256:content",
        status=ChunkStatus.PENDING,
        permission_scope=PermissionScope.INTERNAL,
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        source_metadata={"doc_name": "risk_guide.pdf"},
    )

    with AuthSessionLocal() as db:
        KnowledgeChunkPersistenceService(db).persist_chunks(version, [chunk])
        service = EmbeddingBatchService(provider=DeterministicTestEmbeddingProvider(), expected_dimension=2, db=db)

        first = service.embed_persisted_chunks(version_id=version.version_id, chunk_ids=[chunk.chunk_id])
        second = service.embed_persisted_chunks(version_id=version.version_id, chunk_ids=[chunk.chunk_id])

        assert len(first.records) == 1
        assert len(second.records) == 1
        assert first.records[0].embedding_id == second.records[0].embedding_id


def test_embedding_batch_service_rejects_empty_input() -> None:
    from app.risk_knowledge.embedding.batch_service import EmbeddingBatchService

    service = EmbeddingBatchService(provider=DeterministicTestEmbeddingProvider(), expected_dimension=2)

    with pytest.raises(EmbeddingInputError):
        service.embed_inputs([])


def test_embedding_batch_service_rejects_dimension_mismatch() -> None:
    from app.risk_knowledge.embedding.batch_service import EmbeddingBatchService

    service = EmbeddingBatchService(provider=DeterministicTestEmbeddingProvider(), expected_dimension=3)

    with pytest.raises(EmbeddingDimensionMismatchError):
        service.embed_inputs(
            [
                EmbeddingInput(
                    chunk_id="risk_guide_202607_chunk_000001",
                    content_hash="sha256:content",
                    text="贷后风险识别是指...",
                )
            ]
        )


def test_openai_compatible_provider_requires_runtime_dependency(monkeypatch) -> None:
    from app.risk_knowledge.embedding import openai_compatible_provider as provider_module
    from app.risk_knowledge.embedding.openai_compatible_provider import OpenAICompatibleEmbeddingProvider

    def _raise_missing_openai(name: str):
        if name == "openai":
            raise ModuleNotFoundError("No module named 'openai'")
        raise AssertionError(f"unexpected import request: {name}")

    monkeypatch.delenv("RISK_KNOWLEDGE_EMBEDDING_API_KEY", raising=False)
    monkeypatch.setattr(provider_module, "import_module", _raise_missing_openai)
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="text-embedding-v3",
        dimension=1024,
        max_batch_size=8,
    )

    with pytest.raises(EmbeddingProviderUnavailableError):
        provider.embed(
            [
                EmbeddingInput(
                    chunk_id="risk_guide_202607_chunk_000001",
                    content_hash="sha256:content",
                    text="贷后风险识别是指...",
                )
            ]
        )


@pytest.mark.skipif(os.getenv("CHORD_RUN_REAL_EMBEDDING_TESTS") != "1", reason="set CHORD_RUN_REAL_EMBEDDING_TESTS=1")
def test_openai_compatible_provider_real_smoke() -> None:
    from app.core.config import settings
    from app.risk_knowledge.embedding.openai_compatible_provider import OpenAICompatibleEmbeddingProvider

    provider = OpenAICompatibleEmbeddingProvider(
        api_key=settings.risk_knowledge_embedding_api_key or "",
        base_url=settings.risk_knowledge_embedding_base_url,
        model=settings.risk_knowledge_embedding_model,
        dimension=settings.risk_knowledge_embedding_dimension,
        max_batch_size=settings.risk_knowledge_embedding_max_batch_size,
    )
    result = provider.embed(
        [
            EmbeddingInput(
                chunk_id="risk_guide_202607_chunk_000001",
                content_hash="sha256:content",
                text="贷后风险识别是指...",
            )
        ]
    )

    assert len(result) == 1
    assert result[0].dimension == settings.risk_knowledge_embedding_dimension
