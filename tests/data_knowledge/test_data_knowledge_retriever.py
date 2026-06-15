from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-retriever", raising=False)
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


def test_retriever_respects_country_scope_and_common_fallback(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.retriever import DataKnowledgeRetriever
    from app.data_knowledge.service import DataKnowledgeService

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        service = DataKnowledgeService(db)
        service.import_seed_bundle(bundle="mx", project_id=project.id, actor_username="admin")
        service.import_seed_bundle(bundle="ph", project_id=project.id, actor_username="admin")
        service.import_seed_bundle(bundle="common", project_id=project.id, actor_username="admin")

        retriever = DataKnowledgeRetriever(db)
        context = retriever.retrieve(
            natural_language_request="查询墨西哥首贷从未逾期用户",
            project_id=project.id,
            country="mx",
            run_type="cohort_query",
            output_bucket=None,
        )

        glossary_keys = {item.source_key for item in context.glossary_terms}
        table_names = {item.table_name for item in context.catalog_tables}

        assert "term:first_loan" in glossary_keys
        assert "term:never_overdue" in glossary_keys
        assert "dwd_w_apply" in table_names
        assert "ph_apply_orders" not in table_names


def test_retriever_prefers_same_project_records(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.models import DataGlossaryTerm
    from app.data_knowledge.retriever import DataKnowledgeRetriever

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        db.add(
            DataGlossaryTerm(
                project_id=None,
                country="mx",
                status="active",
                source_type="manual",
                source_namespace="manual/global/glossary",
                source_key="term:high_risk_global",
                source_hash="global-hash",
                created_by="admin",
                updated_by="admin",
                term="高风险用户",
                synonyms_json=["high risk"],
                definition="全局规则",
                mapped_tables_json=["global_risk_table"],
                mapped_fields_json=["risk_level"],
                suggested_filters_json=["risk_level = 'high'"],
            )
        )
        db.add(
            DataGlossaryTerm(
                project_id=project.id,
                country="mx",
                status="active",
                source_type="manual",
                source_namespace="manual/project/glossary",
                source_key="term:high_risk_project",
                source_hash="project-hash",
                created_by="admin",
                updated_by="admin",
                term="高风险用户",
                synonyms_json=["high risk"],
                definition="项目内规则",
                mapped_tables_json=["project_risk_table"],
                mapped_fields_json=["risk_level"],
                suggested_filters_json=["risk_level = 'high'"],
            )
        )
        db.commit()

        retriever = DataKnowledgeRetriever(db)
        context = retriever.retrieve(
            natural_language_request="查询高风险用户",
            project_id=project.id,
            country="mx",
            run_type="cohort_query",
            output_bucket=None,
        )

        assert context.glossary_terms
        assert context.glossary_terms[0].source_key == "term:high_risk_project"


def test_prompt_context_assembler_includes_writeback_constraints(auth_db) -> None:
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

        retriever = DataKnowledgeRetriever(db)
        context = retriever.retrieve(
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

        assert "output_bucket=behavior" in assembled.rendered_text
        assert "uid" in assembled.rendered_text
        assert "bucket 写回" in assembled.rendered_text or "写回 behavior" in assembled.rendered_text
        assert assembled.section_counts["glossary_terms"] >= 1


def test_retriever_does_not_recall_draft_examples(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.models import DataSqlExample
    from app.data_knowledge.retriever import DataKnowledgeRetriever

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        db.add(
            DataSqlExample(
                project_id=project.id,
                country="mx",
                status="draft",
                source_type="approved_sql",
                source_namespace="approved_sql/mx",
                source_key="run:r1:sql:h1",
                source_hash="h1",
                created_by="admin",
                updated_by="admin",
                natural_language_request="查询首贷用户",
                run_type="cohort_query",
                output_bucket=None,
                sql_hash="h1",
                sql_text="SELECT uid FROM users LIMIT 1",
                tables_used_json=["users"],
                fields_used_json=["uid"],
                pattern_summary="draft example",
                reviewer_username="admin",
                execution_status="executed",
            )
        )
        db.commit()

        retriever = DataKnowledgeRetriever(db)
        context = retriever.retrieve(
            natural_language_request="查询首贷用户",
            project_id=project.id,
            country="mx",
            run_type="cohort_query",
            output_bucket=None,
        )

        assert context.sql_examples == []
