from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-data-knowledge", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)

    from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    yield tmp_path

    reset_auth_engine()


def _write_yaml(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_seed_import_is_idempotent_and_deprecates_removed_rows_in_same_namespace(auth_db, monkeypatch) -> None:
    seed_root = auth_db / "data_knowledge_seed"
    _write_yaml(
        seed_root / "mx" / "glossary.yaml",
        """
- source_key: term:first_loan
  term: 首贷
  synonyms: ["first loan"]
  definition: 首次成功放款用户
  mapped_tables: ["dwd_w_apply"]
  mapped_fields: ["loan_order_no"]
  suggested_filters: ["loan_count = 1"]
- source_key: term:never_overdue
  term: 从未逾期
  synonyms: ["never overdue"]
  definition: 历史最大逾期天数为 0
  mapped_tables: ["dwd_w_apply"]
  mapped_fields: ["max_overdue_days"]
  suggested_filters: ["max_overdue_days = 0"]
""".strip(),
    )
    _write_yaml(seed_root / "mx" / "catalog.yaml", "[]")
    _write_yaml(seed_root / "mx" / "sql_examples.yaml", "[]")

    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.models import DataGlossaryTerm
    from app.data_knowledge.service import DataKnowledgeService
    from sqlalchemy import select

    monkeypatch.setattr("app.data_knowledge.service.DATA_KNOWLEDGE_SEED_DIR", seed_root)

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        service = DataKnowledgeService(db)

        first = service.import_seed_bundle(
            bundle="mx",
            project_id=project.id,
            actor_username="admin",
        )
        assert first["upserted"] == 2
        assert first["deprecated"] == 0

        second = service.import_seed_bundle(
            bundle="mx",
            project_id=project.id,
            actor_username="admin",
        )
        assert second["upserted"] == 0
        assert second["deprecated"] == 0

        _write_yaml(
            seed_root / "mx" / "glossary.yaml",
            """
- source_key: term:first_loan
  term: 首贷
  synonyms: ["first loan"]
  definition: 首次成功放款用户
  mapped_tables: ["dwd_w_apply"]
  mapped_fields: ["loan_order_no"]
  suggested_filters: ["loan_count = 1"]
""".strip(),
        )

        third = service.import_seed_bundle(
            bundle="mx",
            project_id=project.id,
            actor_username="admin",
        )
        assert third["upserted"] == 0
        assert third["deprecated"] == 1

        rows = list(
            db.scalars(
                select(DataGlossaryTerm).where(DataGlossaryTerm.source_namespace == "seed/mx/glossary")
            ).all()
        )
        assert len(rows) == 2
        by_key = {row.source_key: row for row in rows}
        assert by_key["term:first_loan"].status == "active"
        assert by_key["term:never_overdue"].status == "deprecated"


def test_seed_import_does_not_deprecate_manual_or_other_namespace_rows(auth_db, monkeypatch) -> None:
    seed_root = auth_db / "data_knowledge_seed"
    _write_yaml(
        seed_root / "mx" / "glossary.yaml",
        """
- source_key: term:first_loan
  term: 首贷
  synonyms: ["first loan"]
  definition: 首次成功放款用户
  mapped_tables: ["dwd_w_apply"]
  mapped_fields: ["loan_order_no"]
  suggested_filters: ["loan_count = 1"]
""".strip(),
    )
    _write_yaml(seed_root / "mx" / "catalog.yaml", "[]")
    _write_yaml(seed_root / "mx" / "sql_examples.yaml", "[]")
    _write_yaml(seed_root / "common" / "glossary.yaml", "[]")

    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.models import DataGlossaryTerm
    from app.data_knowledge.service import DataKnowledgeService
    from sqlalchemy import select

    monkeypatch.setattr("app.data_knowledge.service.DATA_KNOWLEDGE_SEED_DIR", seed_root)

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        service = DataKnowledgeService(db)
        service.import_seed_bundle(bundle="mx", project_id=project.id, actor_username="admin")

        manual = DataGlossaryTerm(
            project_id=project.id,
            country="mx",
            status="active",
            source_type="manual",
            source_namespace="manual/mx/glossary",
            source_key="term:manual_rule",
            source_hash="manual-hash",
            created_by="admin",
            updated_by="admin",
            term="人工术语",
            synonyms_json=[],
            definition="manual",
            mapped_tables_json=[],
            mapped_fields_json=[],
            suggested_filters_json=[],
        )
        common = DataGlossaryTerm(
            project_id=project.id,
            country=None,
            status="active",
            source_type="seed",
            source_namespace="seed/common/glossary",
            source_key="term:shared",
            source_hash="shared-hash",
            created_by="admin",
            updated_by="admin",
            term="共享术语",
            synonyms_json=[],
            definition="common",
            mapped_tables_json=[],
            mapped_fields_json=[],
            suggested_filters_json=[],
        )
        db.add(manual)
        db.add(common)
        db.commit()

        _write_yaml(seed_root / "mx" / "glossary.yaml", "[]")
        result = service.import_seed_bundle(bundle="mx", project_id=project.id, actor_username="admin")
        assert result["deprecated"] == 1

        db.refresh(manual)
        db.refresh(common)
        assert manual.status == "active"
        assert common.status == "active"


def test_seed_import_supports_error_case_seed_namespace(auth_db, monkeypatch) -> None:
    seed_root = auth_db / "data_knowledge_seed"
    _write_yaml(seed_root / "ph" / "catalog.yaml", "[]")
    _write_yaml(seed_root / "ph" / "glossary.yaml", "[]")
    _write_yaml(seed_root / "ph" / "sql_examples.yaml", "[]")
    _write_yaml(
        seed_root / "ph" / "error_cases.yaml",
        """
- source_key: case:ph-withdraw-uuid
  status: open
  natural_language_request: 修复菲律宾首贷从未逾期 SQL，避免使用 withdraw_uuid
  run_type: cohort_query
  error_type: invalid_field
  error_message: Philippines tables do not expose withdraw_uuid.
  failed_sql_hash: failed-ph-withdraw-uuid
  failed_sql_text: "SELECT withdraw_uuid FROM ph_apply_orders"
  fix_summary: Use uid instead of withdraw_uuid.
  detected_tables: ["ph_apply_orders"]
  detected_fields: ["withdraw_uuid", "uid"]
""".strip(),
    )

    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.models import DataSqlErrorCase
    from app.data_knowledge.service import DataKnowledgeService
    from sqlalchemy import select

    monkeypatch.setattr("app.data_knowledge.service.DATA_KNOWLEDGE_SEED_DIR", seed_root)

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        service = DataKnowledgeService(db)

        result = service.import_seed_bundle(bundle="ph", project_id=project.id, actor_username="admin")
        assert result["upserted"] == 1

        row = db.scalar(
            select(DataSqlErrorCase).where(DataSqlErrorCase.source_key == "case:ph-withdraw-uuid")
        )
        assert row is not None
        assert row.status == "open"
        assert row.source_namespace == "seed/ph/error_cases"
