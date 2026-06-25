from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SOURCE_TYPES = {
    "business_logic",
    "old_prompt",
    "schema_doc",
    "table_dictionary",
    "domain_definition",
    "sql_pattern_doc",
    "feature_logic_doc",
    "error_case_doc",
    "sensitive_raw_doc",
    "mixed_legacy_doc",
}

USEFUL_ASSET_TYPES = {
    "catalog_table",
    "catalog_field",
    "glossary_term",
    "business_rule",
    "cohort_definition",
    "sql_example_pattern",
    "sql_error_case",
    "canonical_field_policy",
    "feature_definition",
    "domain_definition",
    "table_lineage_hint",
    "retrieval_eval_case",
}

RUNTIME_ALLOWED = {
    "no_raw_runtime",
    "sanitized_only",
    "eval_only",
    "future_profile_skill_only",
}

SENSITIVE_PATTERNS = (
    ("host", re.compile(r"(?i)\bhost\s*=\s*['\"][^'\"]+['\"]")),
    ("password", re.compile(r"(?i)\b(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]")),
    ("user", re.compile(r"(?i)\buser\s*=\s*['\"][^'\"]+['\"]")),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("jdbc", re.compile(r"(?i)jdbc:")),
    (
        "connection_string",
        re.compile(r"(?i)(pymysql\.connect|create_engine|postgresql://|mysql://|jdbc:)"),
    ),
)

IGNORED_FILE_PATTERNS = (
    ".DS_Store",
    "__MACOSX",
)


@dataclass(frozen=True)
class InventoryEntry:
    source_file: str
    source_type: str
    country: str
    domain: str
    contains_sensitive_info: bool
    sensitive_categories: list[str]
    useful_asset_types: list[str]
    risks: str
    recommended_action: str
    runtime_allowed: str


def should_ignore_file(path: Path) -> bool:
    name = path.name
    if name == "README.md":
        return True
    if name in IGNORED_FILE_PATTERNS:
        return True
    if name.startswith(".") or name.startswith("._") or name.startswith("~$"):
        return True
    if name.endswith((".tmp", ".temp", ".swp", ".swo", "~")):
        return True
    return False


def detect_sensitive_categories(text: str) -> list[str]:
    categories: list[str] = []
    for label, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            categories.append(label)
    return categories


def infer_source_type(path: Path, text: str) -> str:
    name = path.name.lower()
    content = text.lower()
    if "多国业务逻辑" in path.name:
        return "business_logic"
    if "gem prompt" in name:
        return "old_prompt"
    if path.name in {"few.md", "all_examples .md"}:
        return "mixed_legacy_doc"
    if name.startswith("schema_") and path.suffix == ".csv":
        return "schema_doc"
    if any(token in path.name for token in ("征信所需表格结构", "app所需表结构", "scheme.md")):
        return "schema_doc"
    if any(token in path.name for token in ("数据字典目录", "dws_user_renewal_loan_seg_d", "dws_fox_boc_behavior_log_d", "dwt_")):
        return "table_dictionary"
    if any(token in path.name for token in ("域定义", "三方域", "用户域与风控域")):
        return "domain_definition"
    if "error" in name or "报错" in path.name:
        return "error_case_doc"
    if "sql" in content or "select " in content or "create table" in content:
        return "sql_pattern_doc"
    return "sensitive_raw_doc"


def infer_country(path: Path, source_type: str, text: str) -> str:
    name = path.name
    if name in {"scheme.md", "gem prompt.md", "🚀 征信所需表格结构", "🚀 正在提取表上下文 app所需表结构.ods_f_market_app_categories"}:
        return "mx"
    if any(token in name for token in ("泰国", "dwb层数据字典目录（泰国）", "dwd层数据字典目录（泰国）", "dws层数据字典目录（泰国）", "BI数仓_1.", "BI数仓_2.", "BI数仓_3.", "hive_泰国三方域")):
        return "th"
    if name in {"多国业务逻辑.md", "few.md", "all_examples .md", "1.dws.dws_user_renewal_loan_seg_d 介绍.md", "2.dws.dws_fox_boc_behavior_log_d介绍.md", "schema_dws_dws_fox_boc_behavior_log_d.csv", "schema_dws_dws_user_renewal_loan_seg_d.csv"}:
        return "multi"
    if "泰国" in name or "thailand" in text.lower():
        return "th"
    if "菲律宾" in name:
        return "ph"
    return "multi" if source_type in {"old_prompt", "sql_pattern_doc", "mixed_legacy_doc"} else "unknown"


def infer_domain(path: Path, source_type: str, text: str) -> str:
    name = path.name
    content = text.lower()
    if source_type == "business_logic":
        return "lifecycle"
    if source_type == "old_prompt":
        return "retrieval_governance"
    if name in {"few.md", "all_examples .md"}:
        return "risk_behavior_mixed"
    if "资产域定义" in name or "dwt_asset" in name:
        return "asset"
    if "用户域定义" in name or "user_info" in name or "market_tag" in name:
        return "user"
    if "风控域定义" in name or "rsk_" in name:
        return "risk"
    if "三方域" in name:
        return "third_party"
    if "征信所需表格结构" in name or "credit" in name:
        return "credit"
    if "app所需表结构" in name or "app" in name.lower():
        return "app_profile"
    if "fox_boc_behavior" in name or "schema_dws_dws_fox_boc_behavior_log_d" in name:
        return "behavior"
    if "renewal_loan_seg" in name or "mob1" in content or "结清" in text:
        return "lifecycle"
    if "风控" in name or "risk" in content:
        return "risk"
    if "行为" in name or "behavior" in content or "埋点" in text:
        return "behavior"
    if source_type in {"mixed_legacy_doc", "sql_pattern_doc"}:
        return "risk_behavior_mixed"
    return "mixed"


def infer_useful_asset_types(source_type: str, path: Path, text: str) -> list[str]:
    if source_type == "business_logic":
        return ["glossary_term", "business_rule", "cohort_definition"]
    if source_type == "old_prompt":
        return ["canonical_field_policy", "retrieval_eval_case"]
    if source_type in {"schema_doc", "table_dictionary"}:
        return ["catalog_table", "catalog_field", "table_lineage_hint"]
    if source_type == "domain_definition":
        return ["domain_definition", "glossary_term", "table_lineage_hint"]
    if source_type in {"sql_pattern_doc", "mixed_legacy_doc"}:
        assets = ["sql_example_pattern", "sql_error_case"]
        if "analyze_fraud_behavior" in text or "feature" in text.lower():
            assets.append("feature_definition")
        return assets
    if source_type == "error_case_doc":
        return ["sql_error_case", "retrieval_eval_case"]
    if source_type == "feature_logic_doc":
        return ["feature_definition", "canonical_field_policy"]
    return ["retrieval_eval_case"]


def infer_runtime_allowed(source_type: str) -> str:
    if source_type in {"business_logic", "old_prompt"}:
        return "no_raw_runtime"
    if source_type in {"error_case_doc"}:
        return "eval_only"
    if source_type in {"feature_logic_doc"}:
        return "future_profile_skill_only"
    return "sanitized_only"


def infer_risks(source_type: str, sensitive_categories: list[str], path: Path) -> str:
    risks: list[str] = []
    if sensitive_categories:
        risks.append("contains sensitive connection/runtime details")
    if source_type in {"mixed_legacy_doc", "sql_pattern_doc"}:
        risks.append("contains historical SQL patterns that can cause literal-copy drift")
    if source_type == "old_prompt":
        risks.append("legacy prompt guidance should not be used as runtime grounding")
    if path.suffix == ".csv":
        risks.append("schema snapshot may be partial and needs normalization before import")
    if not risks:
        risks.append("raw source requires structured extraction before runtime use")
    return "; ".join(risks)


def infer_recommended_action(source_type: str) -> str:
    if source_type == "business_logic":
        return "extract to glossary, business_rules, and cohort_definitions"
    if source_type == "old_prompt":
        return "use as design reference only; do not expose to runtime retrieval"
    if source_type in {"schema_doc", "table_dictionary"}:
        return "extract sanitized catalog tables, fields, and lineage hints"
    if source_type == "domain_definition":
        return "extract domain summaries and semantic table selection hints"
    if source_type in {"sql_pattern_doc", "mixed_legacy_doc"}:
        return "split and sanitize into sql_example_pattern and sql_error_case assets"
    if source_type == "error_case_doc":
        return "convert into eval-only or review anti-pattern cases"
    if source_type == "feature_logic_doc":
        return "defer to future profile-skill extraction"
    return "review manually and decide whether to sanitize or exclude"


def build_inventory(source_dir: Path) -> list[InventoryEntry]:
    entries: list[InventoryEntry] = []
    for path in sorted(source_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or should_ignore_file(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        source_type = infer_source_type(path, text)
        if source_type not in SOURCE_TYPES:
            raise ValueError(f"Unsupported source_type for {path.name}: {source_type}")
        useful_asset_types = infer_useful_asset_types(source_type, path, text)
        if not set(useful_asset_types).issubset(USEFUL_ASSET_TYPES):
            raise ValueError(f"Unsupported useful_asset_types for {path.name}: {useful_asset_types}")
        runtime_allowed = infer_runtime_allowed(source_type)
        if runtime_allowed not in RUNTIME_ALLOWED:
            raise ValueError(f"Unsupported runtime_allowed for {path.name}: {runtime_allowed}")
        sensitive_categories = detect_sensitive_categories(text)
        entries.append(
            InventoryEntry(
                source_file=path.name,
                source_type=source_type,
                country=infer_country(path, source_type, text),
                domain=infer_domain(path, source_type, text),
                contains_sensitive_info=bool(sensitive_categories),
                sensitive_categories=sensitive_categories,
                useful_asset_types=useful_asset_types,
                risks=infer_risks(source_type, sensitive_categories, path),
                recommended_action=infer_recommended_action(source_type),
                runtime_allowed=runtime_allowed,
            )
        )
    return entries


def collect_ignored_files(source_dir: Path) -> list[str]:
    ignored = [path.name for path in sorted(source_dir.iterdir(), key=lambda item: item.name) if path.is_file() and should_ignore_file(path)]
    return ignored


def _join_values(values: Iterable[str]) -> str:
    items = list(values)
    return ", ".join(items) if items else "-"


def render_inventory_markdown(entries: list[InventoryEntry], *, source_dir: Path) -> str:
    ignored_files = collect_ignored_files(source_dir)
    lines = [
        "# M2B Legacy Knowledge Inventory",
        "",
        "This report inventories local raw source documents under `docs/knowledge-base`.",
        "It records only metadata, classification, risk, and recommended handling.",
        "It does not copy raw content, secret values, matched lines, or prompt-ready text.",
        "",
        f"- scanned files: {len(entries)}",
        f"- ignored files: {len(ignored_files)} non-knowledge/system entries",
        "",
        "| source_file | source_type | country | domain | contains_sensitive_info | sensitive_categories | useful_asset_types | risks | recommended_action | runtime_allowed |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            "| "
            + " | ".join(
                [
                    entry.source_file,
                    entry.source_type,
                    entry.country,
                    entry.domain,
                    "true" if entry.contains_sensitive_info else "false",
                    _join_values(entry.sensitive_categories),
                    _join_values(entry.useful_asset_types),
                    entry.risks,
                    entry.recommended_action,
                    entry.runtime_allowed,
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate M2B legacy knowledge inventory metadata.")
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    entries = build_inventory(args.source_dir)
    rendered = render_inventory_markdown(entries, source_dir=args.source_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
