from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment specific
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


ASSET_FILES = (
    "catalog_tables.yaml",
    "catalog_fields.yaml",
    "glossary_terms.yaml",
    "business_rules.yaml",
    "cohort_definitions.yaml",
    "sql_example_patterns.yaml",
    "sql_error_cases.yaml",
    "canonical_field_policies.yaml",
)

RUNTIME_IMPORTABLE_TYPES = {
    "catalog_table",
    "catalog_field",
    "glossary_term",
    "sql_example_pattern",
    "sql_error_case",
}

PROMOTION_DECISIONS = {
    "promote_now",
    "defer_needs_review",
    "eval_only",
    "future_profile_skill_only",
    "rejected",
}

SEED_IMPORT_DECISIONS = {
    "import_now",
    "manifest_only",
    "not_imported",
}

SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\b(password|passwd|pwd)\b"),
    re.compile(r"(?i)pymysql\.connect"),
    re.compile(r"(?i)create_engine"),
    re.compile(r"(?i)\bhost\s*="),
    re.compile(r"(?i)\buser\s*="),
    re.compile(r"(?i)jdbc:"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
)

DIRTY_SQL_PATTERNS = (
    re.compile(r"\bdm_model\.yx_tmp_[a-z0-9_]*", re.IGNORECASE),
    re.compile(r"\buid_str\b", re.IGNORECASE),
    re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b20\d{6}\b"),
)

SUPPORTED_SOURCE_NAMESPACE_PATTERN = re.compile(r"^m2b_legacy_v\d+$")

V2_GLOSSARY_ENRICHMENTS: dict[str, dict[str, Any]] = {
    "glossary.mx.high_risk": {
        "synonyms": ["高风险用户", "high risk", "risk_level", "高风险客群"],
        "mapped_tables": ["dwd_w_apply"],
        "mapped_fields": ["risk_level", "user_uuid", "apply_create_at"],
        "suggested_filters": ["risk_level", "recent_7d"],
        "definition_suffix": "优先映射到风险等级字段与申请时间窗口。",
    },
    "glossary.mx.recent_7d": {
        "synonyms": ["7天内", "last 7 days", "past 7 days", "rolling 7 day window"],
        "mapped_tables": ["dwd_w_apply", "dwb_r_apply"],
        "mapped_fields": ["apply_create_at", "apply_created_at", "dt"],
        "suggested_filters": ["apply_create_at", "apply_created_at", "dt"],
        "definition_suffix": "检索时优先命中业务时间字段，其次才是 dt 分区字段。",
    },
    "glossary.common.first_loan": {
        "synonyms": ["首次借款", "第一笔借款", "first borrowing", "首借"],
        "mapped_tables": ["dwd_w_apply"],
        "mapped_fields": ["user_uuid", "withdraw_uuid", "asset_grant_at"],
        "suggested_filters": ["withdraw_uuid", "first_loan"],
    },
    "glossary.common.never_overdue": {
        "synonyms": ["未逾期", "没有逾期", "0逾期", "never overdue user"],
        "mapped_tables": ["dwd_w_apply", "ph_apply_orders"],
        "mapped_fields": ["asset_overdue_days", "max_overdue_days", "history_overdue_count"],
        "suggested_filters": ["asset_overdue_days", "max_overdue_days"],
    },
    "glossary.common.fully_settled": {
        "synonyms": ["结清", "已结清", "full settlement"],
        "mapped_tables": ["dwd_w_apply"],
        "mapped_fields": ["asset_finish_at", "asset_grant_at"],
        "suggested_filters": ["asset_finish_at"],
    },
    "glossary.common.seven_day_no_reborrow_churn": {
        "synonyms": ["7天内未复借", "未复借", "no reborrow within 7 days", "seven_day_no_reborrow"],
        "mapped_tables": ["dwd_w_apply"],
        "mapped_fields": ["withdraw_uuid", "asset_finish_at", "apply_create_at"],
        "suggested_filters": ["withdraw_uuid", "apply_create_at"],
    },
    "glossary.mx.credit_profile": {
        "synonyms": ["credit profile", "征信申请字段", "审核申请画像"],
        "mapped_tables": ["dwb_r_apply"],
        "mapped_fields": ["apply_id", "apply_user_uuid", "apply_status"],
        "suggested_filters": ["apply_status", "apply_created_at"],
        "definition_suffix": "应优先检索征信审核申请宽表字段。",
    },
    "glossary.mx.no_apply": {
        "synonyms": ["无申请", "未申请", "no application"],
        "mapped_tables": ["dwd_w_user"],
        "mapped_fields": [],
        "suggested_filters": ["user_uuid", "apply_create_at"],
    },
    "glossary.mx.recent_30d": {
        "synonyms": ["30天内", "last 30 days", "past 30 days"],
        "mapped_tables": [],
        "mapped_fields": [],
        "suggested_filters": ["user_create_time", "apply_create_at", "dt"],
    },
    "glossary.mx.app_profile": {
        "synonyms": ["app profile", "安装应用画像", "app安装画像"],
        "mapped_tables": ["ods_f_market_app_categories"],
        "mapped_fields": ["app_package"],
    },
    "glossary.th.risk_apply": {
        "synonyms": ["risk apply", "风控申请", "预审风控"],
        "mapped_tables": ["dwt_rsk_apply_info_base_d"],
    },
    "glossary.th.ask_loan_risk": {
        "synonyms": ["ask loan risk", "正审风控", "ask loan"],
        "mapped_tables": ["dwt_rsk_ask_loan_info_base_d"],
    },
    "glossary.th.third_party_risk": {
        "synonyms": ["third party risk", "三方风控", "供应商风控"],
        "mapped_tables": ["hive_third_party_risk_domain"],
    },
}

V2_FIELD_ENRICHMENTS: dict[str, dict[str, Any]] = {
    "field.mx.dwd_w_apply.withdraw_uuid": {
        "aliases": ["loan_uuid", "借款单号", "提现订单号"],
        "description": "提现流水号，真实借款/首贷判定和复借检测的核心借款单号字段。",
        "business_meaning_text": "借款单号，用于识别真实提现、首贷借款链路和 7 天内是否复借。",
    },
    "field.mx.dwd_w_apply.apply_create_at": {
        "aliases": ["申请创建时间", "申请时间", "apply business time"],
        "description": "申请创建时间，可作为申请业务时间窗口；优先于 dt 用于最近7天等自然语言时间过滤。",
        "business_meaning_text": "申请创建时间，对应 apply_time / recent_7d / 风险申请时间窗口。",
    },
    "field.mx.dwd_w_apply.asset_grant_at": {
        "aliases": ["放款时间", "到账时间", "grant time"],
        "description": "放款时间，用于真实借款成立、首贷成立和生命周期观察窗口。",
        "business_meaning_text": "放款时间，用于 true withdraw 和 first loan 生命周期分析。",
    },
    "field.mx.dwd_w_apply.asset_finish_at": {
        "aliases": ["结清时间", "完全结清时间", "settlement time"],
        "description": "资产或分期结清时间，用于 fully_settled 和 7 天未复借流失观察。",
        "business_meaning_text": "结清时间，用于 full settlement 与 7 天 churn 观察窗口。",
    },
    "field.mx.dwd_w_apply.user_uuid": {
        "aliases": ["用户ID", "用户id", "借款用户", "borrower_uuid"],
        "description": "借款链路用户 ID，适用于 cohort join、用户级聚合和跨表关联。",
        "business_meaning_text": "用户主键，可对应 uid / borrower / cohort join。",
    },
    "field.mx.dwb_r_apply.apply_id": {
        "aliases": ["申请ID", "审核申请ID", "credit_apply_id"],
        "description": "征信审核申请记录 ID，用于 credit profile / 审核字段查询。",
        "business_meaning_text": "审核申请主键，用于 credit profile 与申请状态查询。",
    },
    "field.mx.dwb_r_apply.apply_user_uuid": {
        "aliases": ["user_uuid", "申请用户", "credit_user_uuid"],
        "description": "审核申请记录上的用户 uuid，可映射通用 user_uuid 问法。",
        "business_meaning_text": "审核申请用户 ID，对应 user_uuid / user identifier / credit profile user。",
    },
    "field.mx.dwb_r_apply.apply_status": {
        "aliases": ["审核状态", "申请状态", "credit_status"],
        "description": "审核申请状态字段，可回答征信申请状态、审核状态相关查询。",
        "business_meaning_text": "申请状态 / 审核状态，用于 credit profile 状态查询。",
    },
    "field.mx.dwb_r_apply.apply_created_at": {
        "aliases": ["apply_time", "审核申请时间", "credit apply time"],
        "description": "审核申请创建时间，对应 credit profile 的业务时间窗口。",
        "business_meaning_text": "审核申请时间，可作为 recent_7d 等 credit profile 时间过滤字段。",
    },
}


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to promote M2B extracted assets. Install project dependencies before running this script."
        ) from YAML_IMPORT_ERROR


def write_yaml(path: Path, payload: Any) -> None:
    _require_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read_yaml(path: Path) -> Any:
    _require_yaml()
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_candidate_assets(assets_dir: Path) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for name in ASSET_FILES:
        payload = _read_yaml(assets_dir / name) or []
        if not isinstance(payload, list):
            raise ValueError(f"{name} must contain a top-level list")
        assets.extend(payload)
    return assets


def _normalize_country(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"", "common"}:
        return None
    return normalized


def _short_table_name(table_name: str | None) -> str | None:
    if not table_name:
        return None
    normalized = str(table_name).strip()
    if not normalized:
        return None
    return normalized.split(".")[-1]


def _normalize_field_hint(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip()


def _stable_hash(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(data.encode('utf-8')).hexdigest()}"


def _seed_status_for_country(country: str | None) -> str:
    return "active"


def _promotion_for_asset(asset: dict[str, Any], *, source_namespace: str) -> tuple[str, str]:
    runtime_allowed = str(asset.get("runtime_allowed") or "").strip()
    confidence = str(asset.get("confidence") or "").strip().lower()
    asset_type = str(asset.get("asset_type") or "").strip()
    review_status = str(asset.get("review_status") or "").strip().lower()

    if runtime_allowed == "eval_only" or asset_type == "sql_error_case":
        return "eval_only", "not_imported"
    if runtime_allowed == "future_profile_skill_only":
        return "future_profile_skill_only", "not_imported"
    if asset_type == "canonical_field_policy" or review_status == "needs_human_review":
        return "defer_needs_review", "not_imported"
    if asset_type in {"business_rule", "cohort_definition"}:
        if confidence in {"high", "medium"}:
            return "promote_now", "manifest_only"
        return "defer_needs_review", "not_imported"
    if (
        source_namespace == "m2b_legacy_v2"
        and asset_type == "glossary_term"
        and runtime_allowed == "sanitized_only"
        and confidence in {"high", "medium"}
    ):
        return "promote_now", "import_now"
    if asset_type in {"catalog_table", "catalog_field", "glossary_term", "sql_example_pattern"}:
        if runtime_allowed == "sanitized_only" and confidence == "high":
            return "promote_now", "import_now"
        return "defer_needs_review", "not_imported"
    return "rejected", "not_imported"


def build_promotion_manifest(assets: list[dict[str, Any]], *, source_namespace: str) -> dict[str, Any]:
    manifest_assets: list[dict[str, Any]] = []
    for asset in sorted(assets, key=lambda item: str(item["asset_id"])):
        promotion_decision, seed_import_decision = _promotion_for_asset(
            asset,
            source_namespace=source_namespace,
        )
        manifest_assets.append(
            {
                "asset_id": asset["asset_id"],
                "asset_type": asset["asset_type"],
                "country": asset.get("country"),
                "domain": asset.get("domain"),
                "confidence": asset.get("confidence"),
                "runtime_allowed": asset.get("runtime_allowed"),
                "promotion_decision": promotion_decision,
                "seed_import_decision": seed_import_decision,
                "source_namespace": source_namespace,
                "source_key": asset["asset_id"],
                "review_status": asset.get("review_status"),
                "source_files": asset.get("source_files") or [],
            }
        )
    return {
        "schema_version": "m2b_seed_promotion_manifest_v1",
        "source_namespace": source_namespace,
        "assets": manifest_assets,
    }


def _build_catalog_table_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    full_table_name = str(asset["table_name"])
    short_table_name = _short_table_name(full_table_name)
    time_fields = list(asset.get("time_fields") or [])
    partition_fields = list(asset.get("partition_fields") or [])
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": _seed_status_for_country(asset.get("country")),
        "table_name": short_table_name,
        "domain": asset.get("domain"),
        "description": asset.get("description"),
        "purpose": "Promoted from M2B structured extraction candidate asset.",
        "grain": asset.get("grain"),
        "time_field": _normalize_field_hint(time_fields[0] if time_fields else None),
        "partition_field": _normalize_field_hint(partition_fields[0] if partition_fields else None),
        "join_keys": list(asset.get("join_keys") or []),
        "common_filters": [],
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "runtime_allowed": asset.get("runtime_allowed"),
            "physical_table_names": [full_table_name],
            "primary_entities": list(asset.get("primary_entities") or []),
            "notes": list(asset.get("notes") or []),
        },
    }


def _build_catalog_field_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    aliases = list(asset.get("aliases") or [])
    semantic = str(asset.get("semantic") or "").strip()
    usage = list(asset.get("usage") or [])
    description = str(asset.get("description") or "").strip()
    business_meaning_parts = []
    if semantic:
        business_meaning_parts.append(f"semantic={semantic}")
    if aliases:
        business_meaning_parts.append(f"aliases={', '.join(aliases)}")
    if usage:
        business_meaning_parts.append(f"usage={', '.join(usage)}")
    if asset.get("is_join_key"):
        business_meaning_parts.append("join_key=true")
    if asset.get("is_partition_field"):
        business_meaning_parts.append("partition_field=true")
    if asset.get("is_business_time"):
        business_meaning_parts.append("business_time=true")
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": _seed_status_for_country(asset.get("country")),
        "table_name": _short_table_name(asset.get("table_name")),
        "field_name": asset.get("field_name"),
        "field_type": asset.get("field_type"),
        "description": description,
        "business_meaning": "; ".join(business_meaning_parts) or None,
        "is_sensitive": False,
        "join_hint": "primary join key" if asset.get("is_join_key") else None,
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "runtime_allowed": asset.get("runtime_allowed"),
            "aliases": aliases,
            "semantic": semantic or None,
            "usage": usage,
            "table_name_full": asset.get("table_name"),
            "is_join_key": bool(asset.get("is_join_key")),
            "is_partition_field": bool(asset.get("is_partition_field")),
            "is_business_time": bool(asset.get("is_business_time")),
        },
    }


def _build_glossary_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": _seed_status_for_country(asset.get("country")),
        "term": asset.get("term"),
        "synonyms": list(asset.get("aliases") or []),
        "definition": asset.get("definition"),
        "mapped_tables": [_short_table_name(name) for name in asset.get("mapped_tables", []) if _short_table_name(name)],
        "mapped_fields": [str(name).strip() for name in asset.get("mapped_fields", []) if str(name).strip()],
        "suggested_filters": list(asset.get("suggested_filters") or []),
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "runtime_allowed": asset.get("runtime_allowed"),
            "aliases": list(asset.get("aliases") or []),
            "related_rules": list(asset.get("related_rules") or []),
            "domain": asset.get("domain"),
        },
    }


def _build_sql_example_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    tables_used = [_short_table_name(asset.get("table_name"))] if asset.get("table_name") else []
    scenario = str(asset.get("scenario") or asset.get("asset_id")).strip()
    required_fields = [str(name).strip() for name in asset.get("required_output_fields", []) if str(name).strip()]
    hash_payload = {
        "asset_id": asset["asset_id"],
        "scenario": scenario,
        "pattern_summary": list(asset.get("pattern_summary") or []),
        "required_output_fields": required_fields,
    }
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": _seed_status_for_country(asset.get("country")),
        "natural_language_request": scenario.replace("_", " "),
        "run_type": "bucket_writeback" if asset.get("domain") == "behavior" else "cohort_query",
        "output_bucket": "behavior" if asset.get("domain") == "behavior" else None,
        "sql_hash": _stable_hash(hash_payload),
        "sql_text": None,
        "tables_used": tables_used,
        "fields_used": required_fields,
        "pattern_summary": " | ".join(asset.get("pattern_summary") or []),
        "reviewer_username": "m2b_seed_promotion",
        "execution_status": "pattern_only",
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "kind": "sql_example_pattern",
            "scenario": scenario,
            "pattern_summary": list(asset.get("pattern_summary") or []),
            "required_output_fields": required_fields,
            "forbidden_copy": list(asset.get("forbidden_copy") or []),
            "executable": False,
            "raw_sql_available": False,
        },
    }


def _merge_unique_strs(values: list[str], additions: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for raw in [*(values or []), *(additions or [])]:
        value = str(raw).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        merged.append(value)
        seen.add(key)
    return merged


def _append_sentence(base: str | None, addition: str | None) -> str | None:
    base_text = str(base or "").strip()
    addition_text = str(addition or "").strip()
    if not addition_text:
        return base_text or None
    if not base_text:
        return addition_text
    if addition_text in base_text:
        return base_text
    return f"{base_text} {addition_text}".strip()


def _apply_v2_glossary_enrichments(item: dict[str, Any]) -> None:
    enrichment = V2_GLOSSARY_ENRICHMENTS.get(str(item.get("source_key")))
    if not enrichment:
        return
    item["synonyms"] = _merge_unique_strs(list(item.get("synonyms") or []), list(enrichment.get("synonyms") or []))
    item["mapped_tables"] = _merge_unique_strs(list(item.get("mapped_tables") or []), list(enrichment.get("mapped_tables") or []))
    item["mapped_fields"] = _merge_unique_strs(list(item.get("mapped_fields") or []), list(enrichment.get("mapped_fields") or []))
    item["suggested_filters"] = _merge_unique_strs(
        list(item.get("suggested_filters") or []),
        list(enrichment.get("suggested_filters") or []),
    )
    item["definition"] = _append_sentence(item.get("definition"), enrichment.get("definition_suffix"))
    metadata = dict(item.get("metadata") or {})
    metadata["aliases"] = item["synonyms"]
    item["metadata"] = metadata


def _apply_v2_field_enrichments(item: dict[str, Any]) -> None:
    enrichment = V2_FIELD_ENRICHMENTS.get(str(item.get("source_key")))
    if not enrichment:
        return
    metadata = dict(item.get("metadata") or {})
    aliases = _merge_unique_strs(list(metadata.get("aliases") or []), list(enrichment.get("aliases") or []))
    metadata["aliases"] = aliases
    item["metadata"] = metadata
    item["description"] = _append_sentence(item.get("description"), enrichment.get("description"))
    item["business_meaning"] = _append_sentence(item.get("business_meaning"), enrichment.get("business_meaning_text"))


def _apply_seed_enrichments(payload: dict[str, Any], *, source_namespace: str) -> None:
    if source_namespace != "m2b_legacy_v2":
        return
    for item in payload.get("glossary_terms") or []:
        _apply_v2_glossary_enrichments(item)
    for item in payload.get("catalog_fields") or []:
        _apply_v2_field_enrichments(item)


def _build_sql_error_case_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": "open",
        "natural_language_request": asset.get("scenario"),
        "run_type": "cohort_query",
        "output_bucket": None,
        "error_type": asset.get("bad_pattern_category") or asset.get("scenario"),
        "error_message": asset.get("risk"),
        "failed_sql_hash": _stable_hash({"asset_id": asset["asset_id"], "risk": asset.get("risk")}),
        "failed_sql_text": None,
        "fixed_sql_hash": None,
        "fixed_sql_text": None,
        "fix_summary": asset.get("expected_fix"),
        "detected_tables": [],
        "detected_fields": [],
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "kind": "sql_error_case",
            "warning_categories": list(asset.get("warning_categories") or []),
            "executable": False,
            "raw_sql_available": False,
        },
    }


def build_seed_patch_payload(
    *,
    assets: list[dict[str, Any]],
    manifest: dict[str, Any],
    source_namespace: str,
    generated_from_manifest: str,
) -> dict[str, Any]:
    by_asset_id = {asset["asset_id"]: asset for asset in assets}
    payload = {
        "schema_version": "m2b_seed_patch_v1",
        "source_namespace": source_namespace,
        "generated_from_manifest": generated_from_manifest,
        "catalog_tables": [],
        "catalog_fields": [],
        "glossary_terms": [],
        "sql_examples": [],
        "sql_error_cases": [],
    }
    for decision in manifest["assets"]:
        if decision["seed_import_decision"] != "import_now":
            continue
        asset = by_asset_id[decision["asset_id"]]
        source_key = decision["source_key"]
        asset_type = asset["asset_type"]
        if asset_type == "catalog_table":
            payload["catalog_tables"].append(_build_catalog_table_seed(asset, source_key=source_key))
        elif asset_type == "catalog_field":
            payload["catalog_fields"].append(_build_catalog_field_seed(asset, source_key=source_key))
        elif asset_type == "glossary_term":
            payload["glossary_terms"].append(_build_glossary_seed(asset, source_key=source_key))
        elif asset_type == "sql_example_pattern":
            payload["sql_examples"].append(_build_sql_example_seed(asset, source_key=source_key))
        elif asset_type == "sql_error_case":
            payload["sql_error_cases"].append(_build_sql_error_case_seed(asset, source_key=source_key))
    _apply_seed_enrichments(payload, source_namespace=source_namespace)
    return payload


def validate_seed_patch_payload(payload: dict[str, Any], *, expected_source_namespace: str | None = None) -> None:
    required_top_level = {
        "schema_version",
        "source_namespace",
        "generated_from_manifest",
        "catalog_tables",
        "catalog_fields",
        "glossary_terms",
        "sql_examples",
        "sql_error_cases",
    }
    missing = required_top_level - set(payload)
    if missing:
        raise ValueError(f"seed patch missing top-level keys: {sorted(missing)}")
    source_namespace = str(payload["source_namespace"] or "").strip()
    if not SUPPORTED_SOURCE_NAMESPACE_PATTERN.match(source_namespace):
        raise ValueError("seed patch source_namespace must match m2b_legacy_vN")
    if expected_source_namespace is not None and source_namespace != expected_source_namespace:
        raise ValueError(f"seed patch source_namespace must be {expected_source_namespace}")

    seen_source_keys: set[str] = set()
    for family_name in ("catalog_tables", "catalog_fields", "glossary_terms", "sql_examples", "sql_error_cases"):
        items = payload.get(family_name) or []
        if not isinstance(items, list):
            raise ValueError(f"{family_name} must be a list")
        for item in items:
            source_key = str(item.get("source_key") or "").strip()
            if not source_key:
                raise ValueError(f"{family_name} entry missing source_key")
            if source_key in seen_source_keys:
                raise ValueError(f"duplicate source_key in seed patch: {source_key}")
            seen_source_keys.add(source_key)
            text = json.dumps(item, ensure_ascii=False, sort_keys=True)
            for pattern in SENSITIVE_PATTERNS:
                if pattern.search(text):
                    raise ValueError(f"sensitive content detected in seed patch entry: {source_key}")
            for pattern in DIRTY_SQL_PATTERNS:
                if pattern.search(text):
                    raise ValueError(f"dirty SQL template detected in seed patch entry: {source_key}")
            if family_name == "sql_examples":
                metadata = dict(item.get("metadata") or {})
                if item.get("sql_text") is not None:
                    raise ValueError("sql example pattern seed must keep sql_text as null")
                if metadata.get("kind") != "sql_example_pattern":
                    raise ValueError("sql example pattern seed metadata.kind must be sql_example_pattern")
                if metadata.get("executable") is not False:
                    raise ValueError("sql example pattern seed metadata.executable must be false")
                if metadata.get("raw_sql_available") is not False:
                    raise ValueError("sql example pattern seed metadata.raw_sql_available must be false")


def _family_counts(manifest: dict[str, Any]) -> dict[str, Counter]:
    counters: dict[str, Counter] = defaultdict(Counter)
    for item in manifest["assets"]:
        counters[item["asset_type"]][item["promotion_decision"]] += 1
        counters[item["asset_type"]][f"seed::{item['seed_import_decision']}"] += 1
    return counters


def build_review_markdown(*, manifest: dict[str, Any], seed_payload: dict[str, Any]) -> str:
    promotion_counts = Counter(item["promotion_decision"] for item in manifest["assets"])
    import_counts = Counter(item["seed_import_decision"] for item in manifest["assets"])
    family_counts = _family_counts(manifest)
    lines = [
        "# M2B-2 Seed Promotion Review",
        "",
        "This review records the M2B-2 promotion decisions for M2B-1 candidate assets.",
        "",
        "## Summary",
        "",
        f"- source_namespace: `{manifest['source_namespace']}`",
        f"- total candidate assets: `{len(manifest['assets'])}`",
        f"- promote_now: `{promotion_counts['promote_now']}`",
        f"- defer_needs_review: `{promotion_counts['defer_needs_review']}`",
        f"- eval_only: `{promotion_counts['eval_only']}`",
        f"- future_profile_skill_only: `{promotion_counts['future_profile_skill_only']}`",
        f"- rejected: `{promotion_counts['rejected']}`",
        f"- import_now: `{import_counts['import_now']}`",
        f"- manifest_only: `{import_counts['manifest_only']}`",
        f"- not_imported: `{import_counts['not_imported']}`",
        "",
        "## Runtime Seed Families",
        "",
        f"- catalog_tables: `{len(seed_payload['catalog_tables'])}`",
        f"- catalog_fields: `{len(seed_payload['catalog_fields'])}`",
        f"- glossary_terms: `{len(seed_payload['glossary_terms'])}`",
        f"- sql_examples: `{len(seed_payload['sql_examples'])}`",
        f"- sql_error_cases: `{len(seed_payload['sql_error_cases'])}`",
        "",
        "## Asset-Type Decisions",
        "",
    ]
    for asset_type in sorted(family_counts):
        counter = family_counts[asset_type]
        lines.append(
            f"- `{asset_type}`: promote_now={counter['promote_now']}, defer_needs_review={counter['defer_needs_review']}, eval_only={counter['eval_only']}, import_now={counter['seed::import_now']}, manifest_only={counter['seed::manifest_only']}, not_imported={counter['seed::not_imported']}"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Pattern examples are non-executable guidance, not SQL candidates.",
            "- Canonical policies marked `needs_human_review` stay out of runtime seed import.",
            "- Business rules and cohort definitions remain manifest-only in M2B-2 because the current runtime seed schema does not support them directly.",
            "- Eval-only error cases remain outside the runtime deterministic retriever unless a later phase adds a safe import shape.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote M2B extracted candidate assets into an isolated seed patch.")
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--seed-output", required=True, type=Path)
    parser.add_argument("--review-output", required=True, type=Path)
    parser.add_argument("--source-namespace", default="m2b_legacy_v1")
    args = parser.parse_args()

    assets = load_candidate_assets(args.assets_dir)
    manifest = build_promotion_manifest(assets, source_namespace=args.source_namespace)
    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace=args.source_namespace,
        generated_from_manifest=str(args.manifest),
    )
    validate_seed_patch_payload(seed_payload, expected_source_namespace=args.source_namespace)

    write_yaml(args.manifest, manifest)
    write_yaml(args.seed_output, seed_payload)
    args.review_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.write_text(
        build_review_markdown(manifest=manifest, seed_payload=seed_payload) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
