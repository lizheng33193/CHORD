from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment specific
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


REQUIRED_CASE_KEYS = (
    "case_id",
    "country",
    "domain",
    "run_type",
    "output_bucket",
    "request",
    "expected_tables",
    "expected_fields",
    "expected_glossary_terms",
    "expected_sql_examples",
    "forbidden_examples",
    "notes",
)

DEFAULT_SEED_PATCH = Path("data_knowledge_seed/m2b/m2b_legacy_v1.yaml")
DEFAULT_PROMOTION_MANIFEST = Path("data_knowledge_eval/m2b/seed_promotion_manifest.yaml")
DEFAULT_COVERAGE_YAML = Path("data_knowledge_eval/m2b/deterministic_coverage.yaml")
DEFAULT_RESULTS_REVIEW = Path("docs/reviews/m2b-2-deterministic-baseline-results.md")
DEFAULT_COVERAGE_REVIEW = Path("docs/reviews/m2b-2-golden-set-deterministic-coverage.md")
DEFAULT_V21_RESULTS_REVIEW = Path("docs/reviews/m2b-2-1-deterministic-grounding-results.md")
DEFAULT_V21_COMPARISON_REVIEW = Path("docs/reviews/m2b-2-1-v1-v2-baseline-comparison.md")
DEFAULT_V22_RESULTS_REVIEW = Path("docs/reviews/m2b-2-2-targeted-grounding-results.md")
DEFAULT_V22_COMPARISON_REVIEW = Path("docs/reviews/m2b-2-2-v2-v3-baseline-comparison.md")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CASE_MANIFEST_ONLY_HINTS = {
    "mx-mob1-settled-7d-churn": [
        "rule.common.full_settlement",
        "rule.common.seven_day_no_reborrow",
        "cohort.mx.mob1_settled_7d_churn",
    ],
    "mx-high-risk-cohort": [
        "cohort.mx.high_risk_recent_7d",
        "canonical.mx.apply_business_time",
    ],
    "mx-first-loan-never-overdue": [
        "cohort.mx.first_loan_never_overdue",
    ],
}

FIELD_EQUIVALENCE_TOKENS: dict[str, set[str]] = {
    "overdue_days": {
        "overdue_days",
        "asset_overdue_days",
        "real_overdue_days",
        "max_overdue_days",
        "history_overdue_count",
    },
}


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to load M2B golden set and promotion assets. Install project dependencies before running this script."
        ) from YAML_IMPORT_ERROR


def load_golden_cases(path: Path) -> list[dict]:
    _require_yaml()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("golden_set.yaml must contain a top-level 'cases' list")

    seen_case_ids: set[str] = set()
    validated: list[dict] = []
    list_fields = {
        "expected_tables",
        "expected_fields",
        "expected_glossary_terms",
        "expected_sql_examples",
        "forbidden_examples",
    }

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Case #{index} must be a mapping")
        missing = [key for key in REQUIRED_CASE_KEYS if key not in case]
        if missing:
            raise ValueError(f"Case #{index} is missing required keys: {', '.join(missing)}")
        case_id = str(case["case_id"]).strip()
        if not case_id:
            raise ValueError(f"Case #{index} has empty case_id")
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)
        for key in ("country", "domain", "run_type", "request"):
            if not str(case[key]).strip():
                raise ValueError(f"Case '{case_id}' has empty required field: {key}")
        for key in list_fields:
            if not isinstance(case[key], list):
                raise ValueError(f"Case '{case_id}' field '{key}' must be a list")
        notes = case["notes"]
        if not isinstance(notes, (list, str)):
            raise ValueError(f"Case '{case_id}' field 'notes' must be a string or list")
        validated.append(case)
    return validated


def _read_yaml(path: Path) -> Any:
    _require_yaml()
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _normalize_table_name(name: str) -> str:
    return str(name or "").strip().lower().split(".")[-1]


def _normalize_token(value: str) -> str:
    return str(value or "").strip().lower()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        result.append(value)
        seen.add(key)
    return result


def _extract_field_aliases(row) -> list[str]:
    metadata = dict(getattr(row, "metadata_json", None) or {})
    aliases = metadata.get("aliases") or []
    return [str(item).strip() for item in aliases if str(item).strip()]


def _extract_glossary_tokens(row) -> set[str]:
    tokens = {_normalize_token(row.term)}
    tokens.update(_normalize_token(alias) for alias in (row.synonyms_json or []))
    tokens.add(_normalize_token(getattr(row, "source_key", "")))
    return {token for token in tokens if token}


def _extract_example_tokens(row) -> set[str]:
    tokens = {_normalize_token(getattr(row, "source_key", ""))}
    natural_language_request = _normalize_token(getattr(row, "natural_language_request", ""))
    if natural_language_request:
        tokens.add(natural_language_request)
        tokens.add(natural_language_request.replace(" ", "_"))
    pattern_summary = _normalize_token(getattr(row, "pattern_summary", ""))
    if pattern_summary:
        tokens.add(pattern_summary)
        tokens.add(pattern_summary.replace(" ", "_"))
    metadata = dict(getattr(row, "metadata_json", None) or {})
    scenario = metadata.get("scenario")
    if scenario:
        normalized = _normalize_token(scenario)
        tokens.add(normalized)
        tokens.add(normalized.replace(" ", "_"))
    for match_token in metadata.get("match_tokens") or []:
        normalized = _normalize_token(match_token)
        if normalized:
            tokens.add(normalized)
    return {token for token in tokens if token}


def _load_manifest_decisions(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    payload = _read_yaml(path) or {}
    assets = payload.get("assets") or []
    return {
        str(item["asset_id"]): item
        for item in assets
        if isinstance(item, dict) and "asset_id" in item
    }


def _load_seed_namespace(path: Path) -> str:
    payload = _read_yaml(path) or {}
    source_namespace = str(payload.get("source_namespace") or "").strip()
    if not source_namespace:
        raise ValueError(f"seed patch {path} is missing source_namespace")
    return source_namespace


def _build_glossary_alias_index(seed_patch_path: Path) -> dict[str, set[str]]:
    payload = _read_yaml(seed_patch_path) or {}
    index: dict[str, set[str]] = {}
    for item in payload.get("glossary_terms") or []:
        source_key = str(item.get("source_key") or "").strip()
        canonical_candidates = {
            _normalize_token(item.get("term")),
            _normalize_token(source_key.split(".")[-1] if source_key else ""),
        }
        aliases = {
            _normalize_token(item.get("term")),
            *(_normalize_token(alias) for alias in (item.get("synonyms") or [])),
            _normalize_token(source_key),
            _normalize_token(source_key.split(".")[-1] if source_key else ""),
        }
        aliases = {token for token in aliases if token}
        for canonical in canonical_candidates:
            if not canonical:
                continue
            index.setdefault(canonical, set()).update(aliases)
    return index


def _phase_label_for_seed_namespace(source_namespace: str) -> str:
    if source_namespace == "m2b_legacy_v2":
        return "m2b_2_1"
    if source_namespace == "m2b_legacy_v3":
        return "m2b_2_2"
    return "m2b_2"


def _default_manifest_path_for_seed_patch(seed_patch_path: Path) -> Path:
    if seed_patch_path.stem.endswith("v3"):
        return Path("data_knowledge_eval/m2b/seed_promotion_manifest.v3.yaml")
    if seed_patch_path.stem.endswith("v2"):
        return Path("data_knowledge_eval/m2b/seed_promotion_manifest.v2.yaml")
    return DEFAULT_PROMOTION_MANIFEST


def build_template_results(cases: list[dict], *, generated_at: str) -> dict:
    template_cases = []
    for case in cases:
        template_cases.append(
            {
                "case_id": case["case_id"],
                "request": case["request"],
                "retrieved_tables": [],
                "retrieved_fields": [],
                "retrieved_glossary_terms": [],
                "retrieved_examples": [],
                "retrieved_error_cases": [],
                "missing_expected": ["TODO: fill after real retriever baseline"],
                "unexpected": [],
                "judgment": "todo",
                "notes": "Template only. Real retriever adapter is intentionally out of M2B-0 scope.",
            }
        )
    return {
        "schema_version": "m2b_baseline_template_v1",
        "generated_at": generated_at,
        "run_mode": "template",
        "retriever": "not_connected",
        "cases": template_cases,
    }


def _case_manifest_notes(
    case_id: str,
    manifest_decisions: dict[str, dict[str, Any]],
    *,
    phase_label: str,
) -> list[str]:
    notes: list[str] = []
    for asset_id in CASE_MANIFEST_ONLY_HINTS.get(case_id, []):
        decision = manifest_decisions.get(asset_id)
        if decision is None:
            notes.append(f"not_runtime_imported_in_{phase_label}:{asset_id}")
            continue
        if decision.get("seed_import_decision") != "import_now":
            notes.append(f"not_runtime_imported_in_{phase_label}:{asset_id}")
    return notes


def _determine_judgment(*, matched_expected: list[str], missing_expected: list[str]) -> str:
    if matched_expected and not missing_expected:
        return "pass"
    if matched_expected:
        return "partial"
    return "fail"


def _build_case_result(
    case: dict[str, Any],
    context,
    *,
    manifest_decisions: dict[str, dict[str, Any]],
    phase_label: str,
    glossary_alias_index: dict[str, set[str]],
) -> dict[str, Any]:
    retrieved_tables = _dedupe_preserve_order([row.table_name for row in context.catalog_tables])
    retrieved_fields = _dedupe_preserve_order([row.field_name for row in context.catalog_fields])
    retrieved_glossary_terms = _dedupe_preserve_order([row.term for row in context.glossary_terms])
    retrieved_examples = _dedupe_preserve_order([row.source_key for row in context.sql_examples])
    retrieved_error_cases = _dedupe_preserve_order([row.source_key for row in context.error_cases])

    matched_expected: list[str] = []
    missing_expected: list[str] = []
    unexpected: list[str] = []

    table_tokens = {_normalize_table_name(name) for name in retrieved_tables}
    for expected in case["expected_tables"]:
        label = f"table:{expected}"
        if _normalize_table_name(expected) in table_tokens:
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    field_tokens = {_normalize_token(name) for name in retrieved_fields}
    field_alias_tokens = {
        _normalize_token(alias)
        for row in context.catalog_fields
        for alias in _extract_field_aliases(row)
    }
    for expected in case["expected_fields"]:
        label = f"field:{expected}"
        token = _normalize_token(expected)
        equivalent_tokens = FIELD_EQUIVALENCE_TOKENS.get(token, {token})
        if equivalent_tokens.intersection(field_tokens) or equivalent_tokens.intersection(field_alias_tokens):
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    glossary_tokens = set()
    for row in context.glossary_terms:
        glossary_tokens.update(_extract_glossary_tokens(row))
    for expected in case["expected_glossary_terms"]:
        label = f"glossary:{expected}"
        expected_token = _normalize_token(expected)
        alias_tokens = glossary_alias_index.get(expected_token, set())
        if expected_token in glossary_tokens or (alias_tokens and glossary_tokens.intersection(alias_tokens)):
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    example_tokens = set()
    for row in context.sql_examples:
        example_tokens.update(_extract_example_tokens(row))
    for expected in case["expected_sql_examples"]:
        label = f"example:{expected}"
        if _normalize_token(expected) in example_tokens:
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    error_tokens = {_normalize_token(value) for value in retrieved_error_cases}
    for forbidden in case["forbidden_examples"]:
        label = f"forbidden:{forbidden}"
        if _normalize_token(forbidden) in error_tokens:
            unexpected.append(label)

    notes = _case_manifest_notes(str(case["case_id"]), manifest_decisions, phase_label=phase_label)
    if unexpected:
        notes.append("forbidden error-case context surfaced in deterministic retrieval")

    return {
        "case_id": case["case_id"],
        "request": case["request"],
        "retrieved_tables": retrieved_tables,
        "retrieved_fields": retrieved_fields,
        "retrieved_glossary_terms": retrieved_glossary_terms,
        "retrieved_examples": retrieved_examples,
        "retrieved_error_cases": retrieved_error_cases,
        "matched_expected": matched_expected,
        "missing_expected": missing_expected,
        "unexpected": unexpected,
        "judgment": _determine_judgment(matched_expected=matched_expected, missing_expected=missing_expected),
        "notes": notes,
    }


def build_deterministic_results(
    *,
    golden_set_path: Path,
    seed_patch_path: Path,
    generated_at: str,
    promotion_manifest_path: Path | None = None,
) -> dict[str, Any]:
    cases = load_golden_cases(golden_set_path)
    seed_source_namespace = _load_seed_namespace(seed_patch_path)
    phase_label = _phase_label_for_seed_namespace(seed_source_namespace)
    manifest_path = promotion_manifest_path or _default_manifest_path_for_seed_patch(seed_patch_path)
    manifest_decisions = _load_manifest_decisions(manifest_path)
    glossary_alias_index = _build_glossary_alias_index(seed_patch_path)

    from app.core.config import settings

    original_settings = {
        "auth_enabled": getattr(settings, "auth_enabled", None),
        "auth_database_url": getattr(settings, "auth_database_url", None),
        "auth_jwt_secret": getattr(settings, "auth_jwt_secret", None),
        "default_admin_username": getattr(settings, "default_admin_username", None),
        "default_admin_email": getattr(settings, "default_admin_email", None),
        "default_admin_password": getattr(settings, "default_admin_password", None),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        auth_db_path = Path(tmpdir) / "auth.sqlite3"
        settings.auth_enabled = True
        settings.auth_database_url = f"sqlite:///{auth_db_path}"
        settings.auth_jwt_secret = "m2b-deterministic-baseline-secret"
        settings.default_admin_username = "admin"
        settings.default_admin_email = "admin@example.com"
        settings.default_admin_password = "admin123456"

        from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
        from app.auth.models import Project
        from app.auth.seed import seed_auth_data
        from app.data_knowledge.retriever import DataKnowledgeRetriever
        from app.data_knowledge.service import DataKnowledgeService
        from sqlalchemy import select

        try:
            reset_auth_engine()
            create_auth_schema()
            case_results: list[dict[str, Any]] = []
            with AuthSessionLocal() as db:
                seed_auth_data(db)
                project = db.scalar(select(Project).where(Project.code == "maps_lz"))
                if project is None:
                    raise RuntimeError("default project maps_lz is required for deterministic baseline")

                service = DataKnowledgeService(db)
                service.import_seed_bundle(bundle="mx", project_id=project.id, actor_username="admin")
                service.import_seed_bundle(bundle="ph", project_id=project.id, actor_username="admin")
                service.import_seed_bundle(bundle="common", project_id=project.id, actor_username="admin")
                service.import_seed_patch(path=seed_patch_path, project_id=project.id, actor_username="admin")

                retriever = DataKnowledgeRetriever(db)
                for case in cases:
                    context = retriever.retrieve(
                        natural_language_request=str(case["request"]),
                        project_id=project.id,
                        country=str(case["country"]),
                        run_type=str(case["run_type"]),
                        output_bucket=case.get("output_bucket"),
                    )
                    case_results.append(
                        _build_case_result(
                            case,
                            context,
                            manifest_decisions=manifest_decisions,
                            phase_label=phase_label,
                            glossary_alias_index=glossary_alias_index,
                        )
                    )
        finally:
            reset_auth_engine()
            for key, value in original_settings.items():
                setattr(settings, key, value)

    return {
        "schema_version": "m2b_baseline_result_v1",
        "generated_at": generated_at,
        "run_mode": "deterministic",
        "retriever": "DataKnowledgeRetriever",
        "seed_namespaces": ["mx", "ph", "common", seed_source_namespace],
        "seed_patch": str(seed_patch_path),
        "cases": case_results,
    }


def _build_coverage_payload(results_payload: dict[str, Any]) -> dict[str, Any]:
    coverage_cases = []
    for case in results_payload["cases"]:
        coverage_cases.append(
            {
                "case_id": case["case_id"],
                "matched_expected": list(case["matched_expected"]),
                "missing_expected": list(case["missing_expected"]),
                "unexpected": list(case["unexpected"]),
                "coverage_judgment": case["judgment"],
                "notes": list(case["notes"]),
            }
        )
    return {
        "schema_version": "m2b_deterministic_coverage_v1",
        "run_mode": "deterministic",
        "seed_namespaces": list(results_payload["seed_namespaces"]),
        "seed_patch": results_payload["seed_patch"],
        "cases": coverage_cases,
    }


def _build_results_review_markdown(results_payload: dict[str, Any], *, phase_label: str) -> str:
    counter = Counter(case["judgment"] for case in results_payload["cases"])
    missing_counter = Counter()
    for case in results_payload["cases"]:
        for item in case["missing_expected"]:
            missing_counter[item] += 1
    if phase_label == "m2b_2":
        title = "# M2B-2 Deterministic Baseline Results"
        next_step = "M2B-3" if counter["pass"] >= 8 and counter["fail"] == 0 else "M2B-2.1"
        phase_text = "M2B-2"
    elif phase_label == "m2b_2_1":
        title = "# M2B-2.1 Deterministic Grounding Results"
        next_step = "M2B-3" if counter["pass"] >= 8 and counter["fail"] == 0 else "M2B-2.2"
        phase_text = "M2B-2.1"
    else:
        title = "# M2B-2.2 Targeted Grounding Results"
        next_step = "M2B-3" if counter["pass"] >= 5 and counter["fail"] == 0 else "M2B-2.3"
        phase_text = "M2B-2.2"

    lines = [
        title,
        "",
        "This is a diagnostic baseline for deterministic Data Knowledge retrieval only.",
        "",
        "## Summary",
        "",
        f"- run_mode: `{results_payload['run_mode']}`",
        f"- retriever: `{results_payload['retriever']}`",
        f"- seed_patch: `{results_payload['seed_patch']}`",
        f"- pass: `{counter['pass']}`",
        f"- partial: `{counter['partial']}`",
        f"- fail: `{counter['fail']}`",
        "",
        "## Interpretation",
        "",
        "- This baseline does not use embeddings, vector retrieval, hybrid retrieval, SQL generation, or SQL execution.",
        f"- Missing business rules, cohort definitions, or canonical policies may be expected when they are manifest-only in {phase_text}.",
        f"- If deterministic recall remains weak after this seed patch, the next step should be `{next_step}` rather than jumping directly to vector retrieval.",
        f"- Recommended next step: `{next_step}`",
        "",
        "## Top Missing Expectations",
        "",
    ]
    for label, count in missing_counter.most_common(12):
        lines.append(f"- `{label}` missing in `{count}` cases")
    return "\n".join(lines)


def _seed_namespace_from_payload(payload: dict[str, Any]) -> str:
    namespaces = payload.get("seed_namespaces") or []
    if not namespaces:
        return "unknown_seed"
    return str(namespaces[-1])


def _comparison_title(left_namespace: str, right_namespace: str) -> tuple[str, str]:
    if left_namespace == "m2b_legacy_v1" and right_namespace == "m2b_legacy_v2":
        return (
            "# M2B-2.1 V1 vs V2 Deterministic Baseline Comparison",
            "This comparison measures deterministic grounding changes between `m2b_legacy_v1` and `m2b_legacy_v2`.",
        )
    if left_namespace == "m2b_legacy_v2" and right_namespace == "m2b_legacy_v3":
        return (
            "# M2B-2.2 V2 vs V3 Deterministic Baseline Comparison",
            "This comparison measures targeted deterministic grounding changes between `m2b_legacy_v2` and `m2b_legacy_v3`.",
        )
    return (
        "# M2B Deterministic Baseline Comparison",
        f"This comparison measures deterministic grounding changes between `{left_namespace}` and `{right_namespace}`.",
    )


def _comparison_header_labels(left_namespace: str, right_namespace: str) -> tuple[str, str]:
    if left_namespace == "m2b_legacy_v1" and right_namespace == "m2b_legacy_v2":
        return "v1_judgment", "v2_judgment"
    if left_namespace == "m2b_legacy_v2" and right_namespace == "m2b_legacy_v3":
        return "v2_judgment", "v3_judgment"
    return "left_judgment", "right_judgment"


def _judgment_rank(value: str) -> int:
    order = {"fail": 0, "partial": 1, "pass": 2}
    return order.get(str(value), -1)


def build_baseline_comparison_markdown(left_payload: dict[str, Any], right_payload: dict[str, Any]) -> str:
    left_namespace = _seed_namespace_from_payload(left_payload)
    right_namespace = _seed_namespace_from_payload(right_payload)
    title, subtitle = _comparison_title(left_namespace, right_namespace)
    left_header, right_header = _comparison_header_labels(left_namespace, right_namespace)
    left_cases = {case["case_id"]: case for case in left_payload.get("cases", [])}
    right_cases = {case["case_id"]: case for case in right_payload.get("cases", [])}
    shared_ids = sorted(set(left_cases) & set(right_cases))
    lines = [
        title,
        "",
        subtitle,
        "",
        f"- left_seed_namespace: `{left_namespace}`",
        f"- right_seed_namespace: `{right_namespace}`",
        "",
        f"| case_id | {left_header} | {right_header} | matched_expected_delta | missing_expected_delta | unexpected_delta | improvement_summary | regression_risk |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for case_id in shared_ids:
        left_case = left_cases[case_id]
        right_case = right_cases[case_id]
        matched_delta = len(right_case["matched_expected"]) - len(left_case["matched_expected"])
        missing_delta = len(right_case["missing_expected"]) - len(left_case["missing_expected"])
        unexpected_delta = len(right_case["unexpected"]) - len(left_case["unexpected"])
        judgment_delta = _judgment_rank(right_case["judgment"]) - _judgment_rank(left_case["judgment"])
        if judgment_delta > 0 or matched_delta > 0 or missing_delta < 0:
            improvement_summary = "improved"
        elif judgment_delta < 0 or matched_delta < 0 or missing_delta > 0:
            improvement_summary = "regressed"
        elif unexpected_delta > 0:
            improvement_summary = "unexpected_increase"
        else:
            improvement_summary = "no_material_change"
        regression_risk = "yes" if unexpected_delta > 0 or judgment_delta < 0 or matched_delta < 0 or missing_delta > 0 else "no"
        lines.append(
            f"| {case_id} | {left_case['judgment']} | {right_case['judgment']} | {matched_delta} | {missing_delta} | {unexpected_delta} | {improvement_summary} | {regression_risk} |"
        )
    return "\n".join(lines)


def _build_coverage_review_markdown(results_payload: dict[str, Any]) -> str:
    lines = [
        "# M2B-2 Golden Set Deterministic Coverage",
        "",
        "| case_id | judgment | matched_expected | missing_expected | notes |",
        "|---|---|---|---|---|",
    ]
    for case in results_payload["cases"]:
        matched = ", ".join(case["matched_expected"]) or "-"
        missing = ", ".join(case["missing_expected"]) or "-"
        notes = "; ".join(case["notes"]) or "-"
        lines.append(
            f"| {case['case_id']} | {case['judgment']} | {matched} | {missing} | {notes} |"
        )
    return "\n".join(lines)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    _require_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate M2B retrieval baseline results.")
    parser.add_argument("--golden-set", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--generated-at", default="template")
    parser.add_argument("--seed-patch", type=Path, default=DEFAULT_SEED_PATCH)
    parser.add_argument("--promotion-manifest", type=Path)
    parser.add_argument("--coverage-yaml", type=Path)
    args = parser.parse_args()

    if args.mode == "template":
        cases = load_golden_cases(args.golden_set)
        payload = build_template_results(cases, generated_at=args.generated_at)
        _write_json(args.output, payload)
        return 0

    if args.mode != "deterministic":
        raise SystemExit(f"unsupported mode: {args.mode}")

    payload = build_deterministic_results(
        golden_set_path=args.golden_set,
        seed_patch_path=args.seed_patch,
        generated_at=args.generated_at,
        promotion_manifest_path=args.promotion_manifest,
    )
    _write_json(args.output, payload)

    coverage_payload = _build_coverage_payload(payload)
    coverage_output = args.coverage_yaml or DEFAULT_COVERAGE_YAML
    _write_yaml(coverage_output, coverage_payload)

    seed_source_namespace = _load_seed_namespace(args.seed_patch)
    if seed_source_namespace == "m2b_legacy_v2":
        DEFAULT_V21_RESULTS_REVIEW.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_V21_RESULTS_REVIEW.write_text(
            _build_results_review_markdown(payload, phase_label="m2b_2_1") + "\n",
            encoding="utf-8",
        )
        v1_result_path = args.output.parent / "baseline_results.m2b_legacy_v1.deterministic.json"
        if v1_result_path.exists():
            v1_payload = json.loads(v1_result_path.read_text(encoding="utf-8"))
            DEFAULT_V21_COMPARISON_REVIEW.write_text(
                build_baseline_comparison_markdown(v1_payload, payload) + "\n",
                encoding="utf-8",
            )
    elif seed_source_namespace == "m2b_legacy_v3":
        DEFAULT_V22_RESULTS_REVIEW.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_V22_RESULTS_REVIEW.write_text(
            _build_results_review_markdown(payload, phase_label="m2b_2_2") + "\n",
            encoding="utf-8",
        )
        v2_result_path = args.output.parent / "baseline_results.m2b_legacy_v2.deterministic.json"
        if v2_result_path.exists():
            v2_payload = json.loads(v2_result_path.read_text(encoding="utf-8"))
            DEFAULT_V22_COMPARISON_REVIEW.write_text(
                build_baseline_comparison_markdown(v2_payload, payload) + "\n",
                encoding="utf-8",
            )
    else:
        if args.output == Path("data_knowledge_eval/m2b/baseline_results.deterministic.json"):
            DEFAULT_RESULTS_REVIEW.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_RESULTS_REVIEW.write_text(
                _build_results_review_markdown(payload, phase_label="m2b_2") + "\n",
                encoding="utf-8",
            )
            DEFAULT_COVERAGE_REVIEW.write_text(_build_coverage_review_markdown(payload) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
