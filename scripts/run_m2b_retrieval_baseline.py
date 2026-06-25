from __future__ import annotations

import argparse
import json
from pathlib import Path

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


def load_golden_cases(path: Path) -> list[dict]:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to load golden_set.yaml. Install project dependencies before running this script."
        ) from YAML_IMPORT_ERROR

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a template-only M2B retrieval baseline result set.")
    parser.add_argument("--golden-set", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--generated-at", default="template")
    args = parser.parse_args()

    if args.mode != "template":
        raise SystemExit("Real retrieval baseline is out of M2B-0 scope.")

    cases = load_golden_cases(args.golden_set)
    payload = build_template_results(cases, generated_at=args.generated_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
