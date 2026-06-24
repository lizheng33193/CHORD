from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-prompt-context", raising=False)
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


def test_prompt_context_adds_current_request_and_anti_copy_guidance(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.prompt_context import PromptContextAssembler
    from app.data_knowledge.retriever import DataKnowledgeRetriever
    from app.data_knowledge.service import DataKnowledgeService

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        service = DataKnowledgeService(db)
        service.import_seed_bundle(bundle="mx", project_id=project.id, actor_username="admin")
        service.import_seed_bundle(bundle="common", project_id=project.id, actor_username="admin")

        context = DataKnowledgeRetriever(db).retrieve(
            natural_language_request="找出墨西哥首贷且从未逾期的用户，并写回 behavior",
            project_id=project.id,
            country="mx",
            run_type="bucket_writeback",
            output_bucket="behavior",
        )
        assembled = PromptContextAssembler().assemble(
            natural_language_request="找出墨西哥首贷且从未逾期的用户，并写回 behavior",
            country="mx",
            run_type="bucket_writeback",
            output_bucket="behavior",
            context=context,
        )

    assert "current request is the source of truth" in assembled.rendered_text
    assert "do not copy literal dates" in assembled.rendered_text.lower()
    assert "do not copy uid placeholders" in assembled.rendered_text.lower()
    assert "prefer field names explicitly present in the retrieved catalog" in assembled.rendered_text.lower()
    assert "do not substitute to a historical alias family" in assembled.rendered_text.lower()
    assert "if the current request does not mention a source or channel filter, do not add one from examples" in assembled.rendered_text.lower()
    assert "if the current request uses a relative time window, keep it relative" in assembled.rendered_text.lower()


def test_prompt_context_adds_under_specified_writeback_safe_refusal_guidance(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.prompt_context import PromptContextAssembler
    from app.data_knowledge.retriever import DataKnowledgeRetriever
    from app.data_knowledge.service import DataKnowledgeService

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        service = DataKnowledgeService(db)
        service.import_seed_bundle(bundle="mx", project_id=project.id, actor_username="admin")
        service.import_seed_bundle(bundle="common", project_id=project.id, actor_username="admin")

        context = DataKnowledgeRetriever(db).retrieve(
            natural_language_request="用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior",
            project_id=project.id,
            country="mx",
            run_type="bucket_writeback",
            output_bucket="behavior",
        )
        assembled = PromptContextAssembler().assemble(
            natural_language_request="用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior",
            country="mx",
            run_type="bucket_writeback",
            output_bucket="behavior",
            context=context,
        )

    assert "do not broad-scan the behavior table" in assembled.rendered_text.lower()
    lowered = assembled.rendered_text.lower()
    assert "return sql=null" in lowered
    assert "sql_kind=query_only" in lowered
