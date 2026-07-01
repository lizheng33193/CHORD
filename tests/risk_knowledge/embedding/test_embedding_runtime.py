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
    max_batch_size = None

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


class TrackingBatchEmbeddingProvider:
    provider_name = "tracking_batch_test"
    max_batch_size = 2

    def __init__(self, *, dimension: int = 2) -> None:
        self.dimension = dimension
        self.batch_sizes: list[int] = []

    def embed(self, inputs: list[EmbeddingInput]) -> list[EmbeddingVectorResult]:
        self.batch_sizes.append(len(inputs))
        results: list[EmbeddingVectorResult] = []
        for item in inputs:
            vector = [float(len(item.text)), float(len(item.chunk_id))][: self.dimension]
            if self.dimension > 2:
                vector.extend([1.0] * (self.dimension - 2))
            results.append(
                EmbeddingVectorResult(
                    chunk_id=item.chunk_id,
                    content_hash=item.content_hash,
                    provider=self.provider_name,
                    model="tracking-batch-v1",
                    dimension=self.dimension,
                    vector=vector,
                    vector_checksum=f"sha256:{item.chunk_id}:{self.dimension}",
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


def test_embedding_batch_service_batches_embed_inputs() -> None:
    from app.risk_knowledge.embedding.batch_service import EmbeddingBatchService

    provider = TrackingBatchEmbeddingProvider()
    service = EmbeddingBatchService(provider=provider, expected_dimension=2)

    result = service.embed_inputs(
        [
            EmbeddingInput(
                chunk_id=f"risk_guide_202607_chunk_{index:06d}",
                content_hash=f"sha256:content:{index}",
                text=f"风险知识内容 {index}",
            )
            for index in range(5)
        ]
    )

    assert provider.batch_sizes == [2, 2, 1]
    assert len(result.records) == 5


def test_embedding_batch_service_batches_persisted_chunks(auth_db) -> None:
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
    chunks = [
        KnowledgeChunk(
            chunk_id=f"risk_guide_202607_chunk_{index:06d}",
            kb_id="risk_domain_knowledge",
            doc_id="risk_guide",
            version_id="risk_guide_202607",
            chunk_order=index,
            chunk_type="paragraph",
            section_title="贷后风险识别",
            section_path=["智能风控指南", "贷后风险识别"],
            page_start=12,
            page_end=12,
            content=f"贷后风险识别是指...{index}",
            content_hash=f"sha256:content:{index}",
            status=ChunkStatus.PENDING,
            permission_scope=PermissionScope.INTERNAL,
            source_type=SourceType.PDF,
            source_uri="knowledge/risk/risk_guide.pdf",
            source_metadata={"doc_name": "risk_guide.pdf"},
        )
        for index in range(1, 6)
    ]

    with AuthSessionLocal() as db:
        KnowledgeChunkPersistenceService(db).persist_chunks(version, chunks)
        provider = TrackingBatchEmbeddingProvider()
        service = EmbeddingBatchService(provider=provider, expected_dimension=2, db=db)

        result = service.embed_persisted_chunks(
            version_id=version.version_id,
            chunk_ids=[chunk.chunk_id for chunk in chunks],
        )

        assert provider.batch_sizes == [2, 2, 1]
        assert len(result.records) == 5


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


def test_dashscope_settings_fields_support_local_configuration(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "dashscope_api_key", "dashscope-test-key", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_provider", "dashscope", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_model", "text-embedding-v4", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_dimension", 1024, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_output_type", "dense", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_text_type", "document", raising=False)

    assert settings.dashscope_api_key == "dashscope-test-key"
    assert settings.risk_knowledge_embedding_provider == "dashscope"
    assert settings.risk_knowledge_embedding_model == "text-embedding-v4"
    assert settings.risk_knowledge_embedding_dimension == 1024
    assert settings.risk_knowledge_embedding_output_type == "dense"
    assert settings.risk_knowledge_embedding_text_type == "document"


def test_embedding_factory_selects_dashscope_provider(monkeypatch) -> None:
    from app.core.config import settings
    from app.risk_knowledge.embedding.factory import build_embedding_provider_from_settings

    monkeypatch.setattr(settings, "dashscope_api_key", "dashscope-test-key", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_provider", "dashscope", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_model", "text-embedding-v4", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_dimension", 1024, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_output_type", "dense", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_text_type", "document", raising=False)

    provider = build_embedding_provider_from_settings()

    assert provider.provider_name == "dashscope"


def test_dashscope_provider_requires_dashscope_api_key(monkeypatch) -> None:
    from app.core.config import settings
    from app.risk_knowledge.embedding.dashscope_provider import DashScopeEmbeddingProvider

    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(settings, "dashscope_api_key", None, raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_embedding_api_key", None, raising=False)
    provider = DashScopeEmbeddingProvider(
        api_key=None,
        model="text-embedding-v4",
        dimension=1024,
        output_type="dense",
        text_type="document",
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


def test_dashscope_provider_declares_max_batch_size() -> None:
    from app.risk_knowledge.embedding.dashscope_provider import DashScopeEmbeddingProvider

    provider = DashScopeEmbeddingProvider(
        api_key="dashscope-test-key",
        model="text-embedding-v4",
        dimension=1024,
        output_type="dense",
        text_type="document",
    )

    assert provider.max_batch_size == 10


def test_dashscope_provider_error_does_not_leak_api_key(monkeypatch) -> None:
    from app.risk_knowledge.embedding.dashscope_provider import DashScopeEmbeddingProvider
    from app.risk_knowledge.embedding.errors import EmbeddingProviderError

    provider = DashScopeEmbeddingProvider(
        api_key="secret-dashscope-key",
        model="text-embedding-v4",
        dimension=1024,
        output_type="dense",
        text_type="document",
    )

    def _raise_failure(_payload):
        raise RuntimeError("provider failed with secret-dashscope-key")

    monkeypatch.setattr(provider, "_post_embeddings_request", _raise_failure)

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider.embed(
            [
                EmbeddingInput(
                    chunk_id="risk_guide_202607_chunk_000001",
                    content_hash="sha256:content",
                    text="贷后风险识别是指...",
                )
            ]
        )

    assert "secret-dashscope-key" not in str(exc_info.value)


def test_real_dashscope_smoke_skips_without_required_env(monkeypatch) -> None:
    monkeypatch.delenv("CHORD_RUN_REAL_EMBEDDING_TESTS", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("RISK_KNOWLEDGE_EMBEDDING_PROVIDER", "openai_compatible")

    with pytest.raises(pytest.skip.Exception):
        _require_real_dashscope_smoke()


def test_openai_compatible_provider_real_smoke() -> None:
    if os.getenv("CHORD_RUN_REAL_EMBEDDING_TESTS") != "1":
        pytest.skip("set CHORD_RUN_REAL_EMBEDDING_TESTS=1 to run real embedding smoke")
    if os.getenv("RISK_KNOWLEDGE_EMBEDDING_PROVIDER") != "openai_compatible":
        pytest.skip("set RISK_KNOWLEDGE_EMBEDDING_PROVIDER=openai_compatible to run this smoke test")
    if not os.getenv("RISK_KNOWLEDGE_EMBEDDING_API_KEY"):
        pytest.skip("set RISK_KNOWLEDGE_EMBEDDING_API_KEY to run OpenAI-compatible embedding smoke")

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


def _require_real_dashscope_smoke() -> None:
    if os.getenv("CHORD_RUN_REAL_EMBEDDING_TESTS") != "1":
        pytest.skip("set CHORD_RUN_REAL_EMBEDDING_TESTS=1 to run real embedding smoke")
    if not os.getenv("DASHSCOPE_API_KEY"):
        pytest.skip("set DASHSCOPE_API_KEY to run DashScope embedding smoke")
    if os.getenv("RISK_KNOWLEDGE_EMBEDDING_PROVIDER") != "dashscope":
        pytest.skip("set RISK_KNOWLEDGE_EMBEDDING_PROVIDER=dashscope to run DashScope embedding smoke")


def test_dashscope_provider_real_smoke() -> None:
    _require_real_dashscope_smoke()

    from app.core.config import settings
    from app.risk_knowledge.embedding.dashscope_provider import DashScopeEmbeddingProvider

    provider = DashScopeEmbeddingProvider(
        api_key=settings.dashscope_api_key,
        model=settings.risk_knowledge_embedding_model,
        dimension=settings.risk_knowledge_embedding_dimension,
        output_type=settings.risk_knowledge_embedding_output_type,
        text_type=settings.risk_knowledge_embedding_text_type,
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

    assert provider.provider_name == "dashscope"
    assert provider.model == "text-embedding-v4"
    assert len(result) == 1
    assert result[0].provider == "dashscope"
    assert result[0].model == "text-embedding-v4"
    assert result[0].dimension == 1024


def test_embedding_batch_service_real_smoke_dashscope_single_persisted_chunk(auth_db) -> None:
    _require_real_dashscope_smoke()

    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.knowledge_base.schemas import (
        ChunkStatus,
        DocumentVersionStatus,
        KnowledgeChunk,
        KnowledgeDocumentVersion,
        PermissionScope,
        SourceType,
    )
    from app.risk_knowledge.embedding.batch_service import EmbeddingBatchService
    from app.risk_knowledge.embedding.dashscope_provider import DashScopeEmbeddingProvider
    from app.risk_knowledge.persistence.repositories import SqlAlchemyKnowledgeChunkEmbeddingRepository
    from app.risk_knowledge.persistence.service import KnowledgeChunkPersistenceService

    version = KnowledgeDocumentVersion(
        version_id="risk_guide_202607_real_smoke",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-07-real-smoke",
        file_hash="sha256:file-real-smoke",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy-parser-v1",
        chunker_version="chunker-v1",
        embedding_model="text-embedding-v4",
        embedding_dim=1024,
        index_name=None,
        status=DocumentVersionStatus.PARSED,
    )
    chunk = KnowledgeChunk(
        chunk_id="risk_guide_202607_real_smoke_chunk_000001",
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id=version.version_id,
        chunk_order=1,
        chunk_type="paragraph",
        section_title="贷后风险识别",
        section_path=["智能风控指南", "贷后风险识别"],
        page_start=12,
        page_end=12,
        content="贷后风险识别是指借款发放后的风险信号跟踪。",
        content_hash="sha256:real-smoke-content",
        status=ChunkStatus.PENDING,
        permission_scope=PermissionScope.INTERNAL,
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        source_metadata={"doc_name": "risk_guide.pdf"},
    )

    with AuthSessionLocal() as db:
        KnowledgeChunkPersistenceService(db).persist_chunks(version, [chunk])
        service = EmbeddingBatchService(
            provider=DashScopeEmbeddingProvider(
                api_key=settings.dashscope_api_key,
                model=settings.risk_knowledge_embedding_model,
                dimension=settings.risk_knowledge_embedding_dimension,
                output_type=settings.risk_knowledge_embedding_output_type,
                text_type=settings.risk_knowledge_embedding_text_type,
            ),
            expected_dimension=1024,
            db=db,
        )

        result = service.embed_persisted_chunks(version_id=version.version_id, chunk_ids=[chunk.chunk_id])
        persisted = SqlAlchemyKnowledgeChunkEmbeddingRepository(db).list_by_version(version.version_id)

    assert len(result.records) == 1
    assert result.records[0].provider == "dashscope"
    assert result.records[0].model == "text-embedding-v4"
    assert result.records[0].dimension == 1024
    assert result.records[0].chunk_id == chunk.chunk_id
    assert result.records[0].content_hash == chunk.content_hash
    assert len(persisted) == 1
    assert persisted[0].provider == "dashscope"
    assert persisted[0].model == "text-embedding-v4"
    assert persisted[0].dimension == 1024
    assert persisted[0].chunk_id == chunk.chunk_id
    assert persisted[0].content_hash == chunk.content_hash
    assert len(persisted[0].vector_json) == 1024
