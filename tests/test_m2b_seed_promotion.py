from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTRACTED_ASSETS_DIR = REPO_ROOT / "data_knowledge_eval" / "m2b" / "extracted_assets"


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-m2b-seed", raising=False)
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


def test_promotion_manifest_and_seed_patch_follow_m2b2_rules() -> None:
    from scripts.promote_m2b_extracted_assets import (
        build_promotion_manifest,
        build_seed_patch_payload,
        load_candidate_assets,
        validate_seed_patch_payload,
    )

    assets = load_candidate_assets(EXTRACTED_ASSETS_DIR)
    assert len(assets) == 128

    manifest = build_promotion_manifest(assets, source_namespace="m2b_legacy_v1")
    manifest_assets = manifest["assets"]
    assert len(manifest_assets) == len(assets)

    by_asset_id = {entry["asset_id"]: entry for entry in manifest_assets}
    assert by_asset_id["table.mx.dwd_w_apply"]["promotion_decision"] == "promote_now"
    assert by_asset_id["table.mx.dwd_w_apply"]["seed_import_decision"] == "import_now"
    assert by_asset_id["rule.common.full_settlement"]["promotion_decision"] == "promote_now"
    assert by_asset_id["rule.common.full_settlement"]["seed_import_decision"] == "manifest_only"
    assert by_asset_id["error_case.common.fixed_historical_date_copy"]["promotion_decision"] == "eval_only"
    assert by_asset_id["error_case.common.fixed_historical_date_copy"]["seed_import_decision"] == "not_imported"
    assert by_asset_id["canonical.mx.apply_business_time"]["promotion_decision"] == "defer_needs_review"
    assert by_asset_id["canonical.mx.apply_business_time"]["seed_import_decision"] == "not_imported"

    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace="m2b_legacy_v1",
        generated_from_manifest="data_knowledge_eval/m2b/seed_promotion_manifest.yaml",
    )
    validate_seed_patch_payload(seed_payload)

    assert seed_payload["schema_version"] == "m2b_seed_patch_v1"
    assert seed_payload["source_namespace"] == "m2b_legacy_v1"
    assert seed_payload["generated_from_manifest"] == "data_knowledge_eval/m2b/seed_promotion_manifest.yaml"
    assert seed_payload["catalog_tables"]
    assert seed_payload["catalog_fields"]
    assert seed_payload["glossary_terms"]
    assert seed_payload["sql_examples"]
    source_keys = set()
    for family_name in ("catalog_tables", "catalog_fields", "glossary_terms", "sql_examples", "sql_error_cases"):
        for entry in seed_payload[family_name]:
            assert entry["source_key"] not in source_keys
            source_keys.add(entry["source_key"])
    pattern_example = next(item for item in seed_payload["sql_examples"] if item["source_key"] == "sql_pattern.mx.behavior_writeback_target_cohort")
    assert pattern_example["sql_text"] is None
    assert pattern_example["metadata"]["kind"] == "sql_example_pattern"
    assert pattern_example["metadata"]["executable"] is False


def test_v2_seed_patch_enriches_grounding_text_without_changing_runtime_scope() -> None:
    from scripts.promote_m2b_extracted_assets import (
        build_promotion_manifest,
        build_seed_patch_payload,
        load_candidate_assets,
        validate_seed_patch_payload,
    )

    assets = load_candidate_assets(EXTRACTED_ASSETS_DIR)
    manifest = build_promotion_manifest(assets, source_namespace="m2b_legacy_v2")
    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace="m2b_legacy_v2",
        generated_from_manifest="data_knowledge_eval/m2b/seed_promotion_manifest.v2.yaml",
    )
    validate_seed_patch_payload(seed_payload)

    assert seed_payload["source_namespace"] == "m2b_legacy_v2"
    assert seed_payload["generated_from_manifest"] == "data_knowledge_eval/m2b/seed_promotion_manifest.v2.yaml"

    glossary_by_key = {item["source_key"]: item for item in seed_payload["glossary_terms"]}
    field_by_key = {item["source_key"]: item for item in seed_payload["catalog_fields"]}

    high_risk = glossary_by_key["glossary.mx.high_risk"]
    assert "high risk" in {item.lower() for item in high_risk["synonyms"]}
    assert "risk_level" in {item.lower() for item in high_risk["synonyms"]}
    assert "dwd_w_apply" in high_risk["mapped_tables"]
    assert "risk_level" in high_risk["mapped_fields"]

    recent_7d = glossary_by_key["glossary.mx.recent_7d"]
    assert "last 7 days" in {item.lower() for item in recent_7d["synonyms"]}
    assert "7天内" in recent_7d["synonyms"]

    credit_profile = glossary_by_key["glossary.mx.credit_profile"]
    assert "credit profile" in {item.lower() for item in credit_profile["synonyms"]}
    assert "dwb_r_apply" in credit_profile["mapped_tables"]
    assert "apply_status" in credit_profile["mapped_fields"]

    apply_create_at = field_by_key["field.mx.dwd_w_apply.apply_create_at"]
    assert "申请创建时间" in apply_create_at["description"]
    assert "apply_time" in (apply_create_at["business_meaning"] or "")

    withdraw_uuid = field_by_key["field.mx.dwd_w_apply.withdraw_uuid"]
    assert "借款单号" in (withdraw_uuid["business_meaning"] or "")
    assert withdraw_uuid["metadata"]["table_name_full"] == "hive.dwd.dwd_w_apply"


def test_import_seed_patch_is_idempotent_and_uses_m2b_namespace(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.models import DataCatalogTable, DataGlossaryTerm
    from app.data_knowledge.service import DataKnowledgeService
    from scripts.promote_m2b_extracted_assets import (
        build_promotion_manifest,
        build_seed_patch_payload,
        load_candidate_assets,
        write_yaml,
    )

    assets = load_candidate_assets(EXTRACTED_ASSETS_DIR)
    manifest = build_promotion_manifest(assets, source_namespace="m2b_legacy_v1")
    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace="m2b_legacy_v1",
        generated_from_manifest="data_knowledge_eval/m2b/seed_promotion_manifest.yaml",
    )
    seed_path = auth_db / "m2b_legacy_v1.yaml"
    write_yaml(seed_path, seed_payload)

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        service = DataKnowledgeService(db)

        first = service.import_seed_patch(
            path=seed_path,
            project_id=project.id,
            actor_username="admin",
        )
        second = service.import_seed_patch(
            path=seed_path,
            project_id=project.id,
            actor_username="admin",
        )

        assert first["source_namespace"] == "m2b_legacy_v1"
        assert first["upserted"] > 0
        assert first["deprecated"] == 0
        assert second["upserted"] == 0
        assert second["deprecated"] == 0

        table_rows = list(
            db.scalars(
                select(DataCatalogTable).where(DataCatalogTable.source_namespace == "m2b_legacy_v1")
            ).all()
        )
        glossary_rows = list(
            db.scalars(
                select(DataGlossaryTerm).where(DataGlossaryTerm.source_namespace == "m2b_legacy_v1")
            ).all()
        )
        assert table_rows
        assert glossary_rows
        assert all(row.status == "active" for row in table_rows)
        assert all(row.status == "active" for row in glossary_rows)


def test_import_seed_patch_accepts_v2_namespace(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.models import DataGlossaryTerm
    from app.data_knowledge.service import DataKnowledgeService
    from scripts.promote_m2b_extracted_assets import (
        build_promotion_manifest,
        build_seed_patch_payload,
        load_candidate_assets,
        write_yaml,
    )

    assets = load_candidate_assets(EXTRACTED_ASSETS_DIR)
    manifest = build_promotion_manifest(assets, source_namespace="m2b_legacy_v2")
    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace="m2b_legacy_v2",
        generated_from_manifest="data_knowledge_eval/m2b/seed_promotion_manifest.v2.yaml",
    )
    seed_path = auth_db / "m2b_legacy_v2.yaml"
    write_yaml(seed_path, seed_payload)

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        service = DataKnowledgeService(db)
        result = service.import_seed_patch(
            path=seed_path,
            project_id=project.id,
            actor_username="admin",
        )
        assert result["source_namespace"] == "m2b_legacy_v2"
        glossary_rows = list(
            db.scalars(
                select(DataGlossaryTerm).where(DataGlossaryTerm.source_namespace == "m2b_legacy_v2")
            ).all()
        )
        assert glossary_rows
