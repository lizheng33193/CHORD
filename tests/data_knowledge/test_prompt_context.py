from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
    assert "# === retrieved_field_grounding ===" in assembled.rendered_text
    assert "selected table fields must come from retrieved catalog/glossary" in assembled.rendered_text.lower()
    assert "dwd_w_apply" in assembled.rendered_text


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


def test_prompt_context_adds_canonical_field_guidance_and_sql_intent_plan() -> None:
    from app.data_knowledge.prompt_context import PromptContextAssembler
    from app.data_knowledge.retriever import RetrievedKnowledgeContext

    context = RetrievedKnowledgeContext(
        catalog_tables=[
            SimpleNamespace(table_name="dwd_w_apply", purpose="loan applications", grain="uid", time_field="apply_time", join_keys_json=["uid"]),
            SimpleNamespace(table_name="dwb_b1_data_burying_point", purpose="behavior events", grain="event", time_field="timestamp_", join_keys_json=["uid"]),
        ],
        catalog_fields=[
            SimpleNamespace(table_name="dwd_w_apply", field_name="uid", field_type="string", business_meaning="user id", description=""),
            SimpleNamespace(table_name="dwd_w_apply", field_name="user_uuid", field_type="string", business_meaning="historical user id", description=""),
            SimpleNamespace(table_name="dwd_w_apply", field_name="apply_time", field_type="datetime", business_meaning="apply time", description=""),
            SimpleNamespace(table_name="dwd_w_apply", field_name="apply_create_at", field_type="datetime", business_meaning="historical apply time", description=""),
            SimpleNamespace(table_name="dwd_w_apply", field_name="risk_level", field_type="string", business_meaning="risk level", description=""),
            SimpleNamespace(table_name="dwb_b1_data_burying_point", field_name="uid", field_type="string", business_meaning="user id", description=""),
            SimpleNamespace(table_name="dwb_b1_data_burying_point", field_name="timestamp_", field_type="datetime", business_meaning="event time", description=""),
            SimpleNamespace(table_name="dwb_b1_data_burying_point", field_name="eventname", field_type="string", business_meaning="event name", description=""),
        ],
        glossary_terms=[],
        sql_examples=[],
        error_cases=[],
        section_counts={},
        source_ids={"table_ids": [], "field_ids": [], "glossary_ids": [], "example_ids": [], "error_case_ids": []},
        trimmed=False,
    )

    structured_plan = {
        "schema_version": "structured_sql_plan_v1",
        "task_type": "bucket_writeback",
        "output_bucket": "behavior",
        "target_cohort_conditions": ["first_loan", "never_overdue"],
        "source_tables": ["dwd_w_apply", "dwb_b1_data_burying_point"],
        "join_keys": ["uid"],
        "required_fields": ["uid", "timestamp_", "eventname"],
        "forbidden_patterns": [
            "unresolved_uid_placeholder",
            "broad_behavior_scan",
            "historical_date_copy",
            "historical_source_filter",
            "literal_example_copy",
            "unsupported_field_family",
        ],
        "source_filters_allowed": False,
        "fixed_dates_allowed": False,
    }

    assembled = PromptContextAssembler().assemble(
        natural_language_request="找出墨西哥首贷且从未逾期的用户，并写回 behavior",
        country="mx",
        run_type="bucket_writeback",
        output_bucket="behavior",
        context=context,
        structured_plan=structured_plan,
    )

    lowered = assembled.rendered_text.lower()
    assert "# === canonical_field_guidance ===" in assembled.rendered_text
    assert "preferred=uid" in lowered
    assert "alternatives=user_uuid" in lowered
    assert "# === structured_sql_plan_contract ===" in assembled.rendered_text
    assert "schema_version=structured_sql_plan_v1" in lowered
    assert "fixed_dates_allowed=false" in lowered
    assert "source_filters_allowed=false" in lowered
    assert "generated sql must satisfy this structured plan" in lowered
    assert "# === sql_intent_plan ===" in assembled.rendered_text
    assert "task_type=bucket_writeback" in lowered
    assert "target_cohort_conditions=first_loan,never_overdue" in lowered
    assert "join_keys=uid" in lowered
    assert "required_fields=uid,timestamp_,eventname" in lowered


def test_prompt_context_does_not_add_sql_intent_plan_for_under_specified_writeback() -> None:
    from app.data_knowledge.prompt_context import PromptContextAssembler
    from app.data_knowledge.retriever import RetrievedKnowledgeContext

    context = RetrievedKnowledgeContext(
        catalog_tables=[
            SimpleNamespace(table_name="dwb_b1_data_burying_point", purpose="behavior events", grain="event", time_field="timestamp_", join_keys_json=["uid"]),
        ],
        catalog_fields=[
            SimpleNamespace(table_name="dwb_b1_data_burying_point", field_name="uid", field_type="string", business_meaning="user id", description=""),
            SimpleNamespace(table_name="dwb_b1_data_burying_point", field_name="timestamp_", field_type="datetime", business_meaning="event time", description=""),
            SimpleNamespace(table_name="dwb_b1_data_burying_point", field_name="eventname", field_type="string", business_meaning="event name", description=""),
        ],
        glossary_terms=[],
        sql_examples=[],
        error_cases=[],
        section_counts={},
        source_ids={"table_ids": [], "field_ids": [], "glossary_ids": [], "example_ids": [], "error_case_ids": []},
        trimmed=False,
    )

    assembled = PromptContextAssembler().assemble(
        natural_language_request="帮我查询并写回 behavior",
        country="mx",
        run_type="bucket_writeback",
        output_bucket="behavior",
        context=context,
    )

    lowered = assembled.rendered_text.lower()
    assert "return sql=null" in lowered
    assert "# === structured_sql_plan_contract ===" not in assembled.rendered_text
    assert "# === sql_intent_plan ===" not in assembled.rendered_text


def test_prompt_context_does_not_add_writeback_plan_to_query_only_prompt() -> None:
    from app.data_knowledge.prompt_context import PromptContextAssembler
    from app.data_knowledge.retriever import RetrievedKnowledgeContext

    context = RetrievedKnowledgeContext(
        catalog_tables=[
            SimpleNamespace(table_name="dwd_w_apply", purpose="loan applications", grain="uid", time_field="apply_time", join_keys_json=["uid"]),
        ],
        catalog_fields=[
            SimpleNamespace(table_name="dwd_w_apply", field_name="uid", field_type="string", business_meaning="user id", description=""),
            SimpleNamespace(table_name="dwd_w_apply", field_name="apply_time", field_type="datetime", business_meaning="apply time", description=""),
            SimpleNamespace(table_name="dwd_w_apply", field_name="risk_level", field_type="string", business_meaning="risk level", description=""),
        ],
        glossary_terms=[],
        sql_examples=[],
        error_cases=[],
        section_counts={},
        source_ids={"table_ids": [], "field_ids": [], "glossary_ids": [], "example_ids": [], "error_case_ids": []},
        trimmed=False,
    )

    assembled = PromptContextAssembler().assemble(
        natural_language_request="查询最近 7 天高风险用户",
        country="mx",
        run_type="cohort_query",
        output_bucket=None,
        context=context,
    )

    assert "# === structured_sql_plan_contract ===" not in assembled.rendered_text
    assert "# === sql_intent_plan ===" not in assembled.rendered_text
    assert "# === writeback_constraints ===" not in assembled.rendered_text
