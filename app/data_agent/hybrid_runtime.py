from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from app.data_knowledge.canonical_fields import normalize_field_name, normalize_table_name


DEFAULT_VECTOR_DIM = 512
DEFAULT_TRACE_SCHEMA_VERSION = "hybrid_retrieval_audit_trace_v1"
DEFAULT_VECTOR_INDEX_SCHEMA_VERSION = "m2b_vector_index_v1"
DEFAULT_VECTOR_FORMAT = "sparse_hash_weight_map"
DEFAULT_ALLOWED_RUNTIME_MODE = "hybrid_shadow"
DEFAULT_MAX_DETERMINISTIC_CANDIDATES = 20
DEFAULT_MAX_VECTOR_CANDIDATES = 10
DEFAULT_MAX_ACCEPTED_SUPPLEMENTS = 3
DEFAULT_MAX_REJECTED_CANDIDATES = 20
DEFAULT_MAX_SUPPLEMENTAL_SECTION_CHARS = 3000
MAX_TITLE_LENGTH = 200
MAX_SOURCE_KEY_LENGTH = 300
MAX_DETAIL_LENGTH = 240
DEFAULT_FAMILY_THRESHOLDS = {
    "catalog_table": 0.18,
    "catalog_field": 0.16,
    "glossary_term": 0.17,
    "sql_example": 0.15,
}
DEFAULT_FAMILY_CAPS = {
    "catalog_table": 1,
    "catalog_field": 2,
    "glossary_term": 1,
    "sql_example": 1,
}
_BOOL_TRUE = {"1", "true", "yes", "on"}
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
WORD_TOKEN = re.compile(r"[a-z0-9_]+")
CJK_CHAR = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
FIELD_EQUIVALENCE_TOKENS = {
    "uid": {"uid"},
    "useruuid": {"useruuid"},
}
_VECTOR_INDEX_CACHE: dict[str, tuple[int, dict[str, Any]]] = {}
PROMPT_INJECTION_NONE = "none"
PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1 = "supplemental_candidates_v1"
FINAL_GENERATION_PASS_DETERMINISTIC = "deterministic"
FINAL_GENERATION_PASS_HYBRID_CANDIDATE = "hybrid_candidate"
FINAL_GENERATION_PASS_DETERMINISTIC_RERUN = "deterministic_rerun"
DISCARD_REASON_POST_SQL_KIND_MISMATCH = "post_sql_kind_mismatch"
DISCARD_REASON_CANDIDATE_GENERATION_FAILED = "candidate_generation_failed"
DISCARD_REASON_CANDIDATE_PLAN_INVALID = "candidate_plan_invalid"
_SUPPLEMENTAL_FAMILY_ORDER = {
    "catalog_table": 0,
    "catalog_field": 1,
    "glossary_term": 2,
    "sql_example": 3,
}
_NON_QUERY_ONLY_INTENT_PATTERN = re.compile(
    r"(create\s+(a\s+)?table|build\s+(a\s+)?(result\s+)?table|persist|materiali[sz]e"
    r"|save\s+.*\b(table|cohort)\b|writeback|bucket_writeback|建表|物化|落表|写回|沉淀.*表)",
    re.IGNORECASE,
)


class HybridRetrievalMode(str, Enum):
    DETERMINISTIC_ONLY = "deterministic_only"
    HYBRID_SHADOW = "hybrid_shadow"
    HYBRID_CANDIDATE = "hybrid_candidate"
    HYBRID_ENABLED = "hybrid_enabled"


class HybridFallbackReason(str, Enum):
    HYBRID_DISABLED = "hybrid_disabled"
    MODE_FORCED_DETERMINISTIC = "mode_forced_deterministic"
    COUNTRY_NOT_ALLOWLISTED = "country_not_allowlisted"
    PROJECT_NOT_ALLOWLISTED = "project_not_allowlisted"
    UNSUPPORTED_SQL_KIND = "unsupported_sql_kind"
    UNSUPPORTED_RUN_TYPE = "unsupported_run_type"
    VECTOR_BACKEND_UNAVAILABLE = "vector_backend_unavailable"
    VECTOR_QUERY_FAILED = "vector_query_failed"
    FUSION_GUARD_FAILED = "fusion_guard_failed"
    AUDIT_TRACE_UNAVAILABLE = "audit_trace_unavailable"
    CONFIG_INVALID = "config_invalid"


@dataclass(slots=True)
class HybridRetrievalConfigV1:
    enabled: bool
    retrieval_mode: HybridRetrievalMode
    source_namespace: str
    vector_index_path: str | None
    allow_countries: list[str]
    allow_project_ids: list[str]
    vector_rank_limit: int
    family_score_thresholds: dict[str, float]
    family_caps: dict[str, int]
    total_vector_supplement_cap: int
    deterministic_pass_guard: bool
    shadow_sample_rate: float
    errors: list[str]


@dataclass(slots=True)
class EffectiveModeDecision:
    configured_mode: HybridRetrievalMode
    effective_mode: HybridRetrievalMode
    fallback_reason: HybridFallbackReason | None
    fallback_applied: bool
    sample_hit: bool
    should_attempt_shadow: bool


@dataclass(slots=True)
class ShadowTraceBuildResult:
    trace: dict[str, Any] | None
    audit_summary: dict[str, Any]
    supplemental_prompt_section: str = ""


def _build_audit_summary(
    *,
    configured_mode: HybridRetrievalMode,
    effective_mode: HybridRetrievalMode,
    fallback_reason: str | None,
    trace_present: bool,
    attempted_mode: str | None = None,
    final_generation_pass: str = FINAL_GENERATION_PASS_DETERMINISTIC,
    prompt_injection_mode: str = PROMPT_INJECTION_NONE,
    prompt_candidate_count: int = 0,
    candidate_attempted: bool = False,
    candidate_discarded: bool = False,
    candidate_discard_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "hybrid_configured_mode": configured_mode.value,
        "hybrid_attempted_mode": attempted_mode,
        "hybrid_effective_mode": effective_mode.value,
        "hybrid_fallback_reason": fallback_reason,
        "hybrid_final_generation_pass": final_generation_pass,
        "hybrid_prompt_injection_mode": prompt_injection_mode,
        "hybrid_prompt_candidate_count": prompt_candidate_count,
        "hybrid_candidate_attempted": candidate_attempted,
        "hybrid_candidate_discarded": candidate_discarded,
        "hybrid_candidate_discard_reason": candidate_discard_reason,
        "hybrid_trace_present": trace_present,
    }


def _as_bool(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in _BOOL_TRUE


def _parse_csv(raw: str | None) -> list[str]:
    return [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]


def _parse_mode(raw: str | None) -> tuple[HybridRetrievalMode, list[str]]:
    value = str(raw or "").strip().lower() or HybridRetrievalMode.DETERMINISTIC_ONLY.value
    try:
        return HybridRetrievalMode(value), []
    except ValueError:
        return HybridRetrievalMode.DETERMINISTIC_ONLY, [f"invalid retrieval mode: {value}"]


def _parse_int(raw: str | None, *, label: str, minimum: int = 0) -> tuple[int, list[str]]:
    try:
        value = int(str(raw or "").strip())
        if value < minimum:
            raise ValueError
        return value, []
    except Exception:
        return minimum, [f"invalid {label}: {raw!r}"]


def _parse_float(raw: str | None, *, label: str, minimum: float = 0.0, maximum: float = 1.0) -> tuple[float, list[str]]:
    try:
        value = float(str(raw or "").strip())
        if value < minimum or value > maximum:
            raise ValueError
        return value, []
    except Exception:
        return minimum, [f"invalid {label}: {raw!r}"]


def _parse_json_mapping(raw: str | None, *, label: str) -> tuple[dict[str, Any], list[str]]:
    try:
        value = json.loads(str(raw or "").strip())
        if not isinstance(value, dict):
            raise ValueError
        return value, []
    except Exception:
        return {}, [f"invalid {label}: {raw!r}"]


def _normalize_thresholds(raw: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    normalized: dict[str, float] = {}
    errors: list[str] = []
    for family, default_value in DEFAULT_FAMILY_THRESHOLDS.items():
        value = raw.get(family, default_value)
        try:
            converted = float(value)
            if converted < 0:
                raise ValueError
        except Exception:
            normalized[family] = default_value
            errors.append(f"invalid family_score_threshold for {family}: {value!r}")
            continue
        normalized[family] = converted
    return normalized, errors


def _normalize_caps(raw: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    normalized: dict[str, int] = {}
    errors: list[str] = []
    for family, default_value in DEFAULT_FAMILY_CAPS.items():
        value = raw.get(family, default_value)
        try:
            if isinstance(value, bool):
                raise ValueError
            converted = int(value)
            if converted < 0:
                raise ValueError
        except Exception:
            normalized[family] = default_value
            errors.append(f"invalid family_cap for {family}: {value!r}")
            continue
        normalized[family] = converted
    return normalized, errors


def load_hybrid_config(settings: Any) -> HybridRetrievalConfigV1:
    mode, mode_errors = _parse_mode(getattr(settings, "hybrid_retrieval_mode_raw", None))
    rank_limit, rank_errors = _parse_int(
        getattr(settings, "hybrid_retrieval_vector_rank_limit_raw", None),
        label="vector_rank_limit",
        minimum=1,
    )
    total_cap, total_cap_errors = _parse_int(
        getattr(settings, "hybrid_retrieval_total_vector_supplement_cap_raw", None),
        label="total_vector_supplement_cap",
        minimum=0,
    )
    sample_rate, sample_rate_errors = _parse_float(
        getattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", None),
        label="shadow_sample_rate",
    )
    thresholds, threshold_errors = _parse_json_mapping(
        getattr(settings, "hybrid_retrieval_family_score_thresholds_json_raw", None),
        label="family_score_thresholds_json",
    )
    caps, cap_errors = _parse_json_mapping(
        getattr(settings, "hybrid_retrieval_family_caps_json_raw", None),
        label="family_caps_json",
    )
    normalized_thresholds, threshold_value_errors = _normalize_thresholds(thresholds)
    normalized_caps, cap_value_errors = _normalize_caps(caps)
    return HybridRetrievalConfigV1(
        enabled=_as_bool(getattr(settings, "hybrid_retrieval_enabled_raw", None)),
        retrieval_mode=mode,
        source_namespace=str(
            getattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3")
        ).strip()
        or "m2b_legacy_v3",
        vector_index_path=str(getattr(settings, "hybrid_retrieval_vector_index_path_raw", "") or "").strip() or None,
        allow_countries=_parse_csv(getattr(settings, "hybrid_retrieval_allow_countries_raw", None)),
        allow_project_ids=[item.strip() for item in str(getattr(settings, "hybrid_retrieval_allow_project_ids_raw", "") or "").split(",") if item.strip()],
        vector_rank_limit=rank_limit or 1,
        family_score_thresholds=normalized_thresholds,
        family_caps=normalized_caps,
        total_vector_supplement_cap=total_cap,
        deterministic_pass_guard=_as_bool(getattr(settings, "hybrid_retrieval_deterministic_pass_guard_raw", None)),
        shadow_sample_rate=sample_rate,
        errors=(
            mode_errors
            + rank_errors
            + total_cap_errors
            + sample_rate_errors
            + threshold_errors
            + cap_errors
            + threshold_value_errors
            + cap_value_errors
        ),
    )


def _stable_sample_hit(*, request_key: str, sample_rate: float) -> bool:
    if sample_rate <= 0:
        return False
    if sample_rate >= 1:
        return True
    digest = hashlib.sha256(request_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket < sample_rate


def evaluate_effective_mode(
    *,
    config: HybridRetrievalConfigV1,
    country: str | None,
    project_id: str | None,
    run_type: str | None,
    request_key: str,
) -> EffectiveModeDecision:
    configured_mode = config.retrieval_mode
    normalized_country = str(country or "").strip().lower()
    normalized_project_id = str(project_id or "").strip()
    normalized_run_type = str(run_type or "").strip().lower()

    if not config.enabled:
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.HYBRID_DISABLED,
            fallback_applied=True,
            sample_hit=False,
            should_attempt_shadow=False,
        )
    if config.errors:
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.CONFIG_INVALID,
            fallback_applied=True,
            sample_hit=False,
            should_attempt_shadow=False,
        )
    if configured_mode in {
        HybridRetrievalMode.HYBRID_ENABLED,
    }:
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.MODE_FORCED_DETERMINISTIC,
            fallback_applied=True,
            sample_hit=False,
            should_attempt_shadow=False,
        )
    if configured_mode is HybridRetrievalMode.DETERMINISTIC_ONLY:
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.MODE_FORCED_DETERMINISTIC,
            fallback_applied=True,
            sample_hit=False,
            should_attempt_shadow=False,
        )
    if normalized_run_type != "cohort_query":
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.UNSUPPORTED_RUN_TYPE,
            fallback_applied=True,
            sample_hit=False,
            should_attempt_shadow=False,
        )
    if normalized_country not in set(config.allow_countries):
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.COUNTRY_NOT_ALLOWLISTED,
            fallback_applied=True,
            sample_hit=False,
            should_attempt_shadow=False,
        )
    if normalized_project_id not in set(config.allow_project_ids):
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.PROJECT_NOT_ALLOWLISTED,
            fallback_applied=True,
            sample_hit=False,
            should_attempt_shadow=False,
        )
    if configured_mode is HybridRetrievalMode.HYBRID_CANDIDATE:
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.HYBRID_CANDIDATE,
            fallback_reason=None,
            fallback_applied=False,
            sample_hit=True,
            should_attempt_shadow=True,
        )
    sample_hit = _stable_sample_hit(request_key=request_key, sample_rate=config.shadow_sample_rate)
    if not sample_hit:
        return EffectiveModeDecision(
            configured_mode=configured_mode,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.MODE_FORCED_DETERMINISTIC,
            fallback_applied=True,
            sample_hit=False,
            should_attempt_shadow=False,
        )
    return EffectiveModeDecision(
        configured_mode=configured_mode,
        effective_mode=HybridRetrievalMode.HYBRID_SHADOW,
        fallback_reason=None,
        fallback_applied=False,
        sample_hit=True,
        should_attempt_shadow=True,
    )


def _truncate(value: str, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).lower().strip()


def _split_token_variants(token: str) -> list[str]:
    normalized = _normalize_text(token)
    if not normalized:
        return []
    variants = [normalized]
    camel_split = CAMEL_BOUNDARY.sub(" ", token)
    camel_normalized = _normalize_text(camel_split)
    if camel_normalized and camel_normalized != normalized:
        variants.extend(camel_normalized.split())
    if "_" in normalized:
        variants.extend(part for part in normalized.split("_") if part)
    return variants


def _tokenize_text(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    tokens: list[str] = []
    for raw in WORD_TOKEN.findall(normalized):
        tokens.extend(_split_token_variants(raw))
    compact_cjk = "".join(CJK_CHAR.findall(normalized))
    if compact_cjk:
        if len(compact_cjk) == 1:
            tokens.append(compact_cjk)
        else:
            for idx in range(len(compact_cjk) - 1):
                tokens.append(compact_cjk[idx : idx + 2])
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not token or token in seen:
            continue
        deduped.append(token)
        seen.add(token)
    return deduped


def _hash_token(token: str, *, vector_dim: int) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return str(int.from_bytes(digest[:8], "big") % vector_dim)


def _l2_normalize_sparse(vector: dict[str, float]) -> dict[str, float]:
    if not vector:
        return {}
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm == 0:
        return {}
    return {key: round(value / norm, 6) for key, value in sorted(vector.items(), key=lambda item: int(item[0])) if value}


def _vectorize_query_record(
    *,
    natural_language_request: str,
    country: str,
    run_type: str,
    output_bucket: str | None,
) -> dict[str, float]:
    field_weights = {"title": 2.0, "search_hints": 2.0, "embedding_text": 1.0}
    record = {
        "title": natural_language_request,
        "embedding_text": "\n".join(
            [
                f"Request: {natural_language_request}",
                f"Country: {country}",
                f"Run type: {run_type}",
                f"Output bucket: {output_bucket or ''}",
            ]
        ),
        "search_hints": [country, run_type, output_bucket or ""],
    }
    weighted_counts: dict[str, float] = {}
    for field_name in ("title", "embedding_text", "search_hints"):
        weight = field_weights[field_name]
        raw_value = record[field_name]
        field_text = " ".join(raw_value) if isinstance(raw_value, list) else str(raw_value or "")
        for token in _tokenize_text(field_text):
            bucket = _hash_token(token, vector_dim=DEFAULT_VECTOR_DIM)
            weighted_counts[bucket] = weighted_counts.get(bucket, 0.0) + weight
    return _l2_normalize_sparse(weighted_counts)


def _sparse_dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    score = 0.0
    for key, value in left.items():
        score += value * right.get(key, 0.0)
    return round(score, 6)


def _load_vector_index(*, config: HybridRetrievalConfigV1, project_root: Path) -> tuple[dict[str, Any], Path]:
    if config.vector_index_path:
        path = Path(config.vector_index_path)
    else:
        path = project_root / "data_knowledge_eval" / "m2b" / f"vector_index.{config.source_namespace}.json"
    if not path.exists():
        raise FileNotFoundError(f"vector index not found: {path}")
    stat = path.stat()
    cache_key = str(path.resolve())
    cached = _VECTOR_INDEX_CACHE.get(cache_key)
    if cached and cached[0] == stat.st_mtime_ns:
        return cached[1], path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("vector index must be a JSON object")
    if payload.get("schema_version") != DEFAULT_VECTOR_INDEX_SCHEMA_VERSION:
        raise ValueError("unexpected vector index schema_version")
    if payload.get("source_namespace") != config.source_namespace:
        raise ValueError("vector index source namespace mismatch")
    if payload.get("vector_format") != DEFAULT_VECTOR_FORMAT:
        raise ValueError("unexpected vector index format")
    _VECTOR_INDEX_CACHE[cache_key] = (stat.st_mtime_ns, payload)
    return payload, path


def _safe_reason(reason: HybridFallbackReason | None) -> str | None:
    return reason.value if isinstance(reason, HybridFallbackReason) else None


def _candidate_title(value: str) -> str:
    return _truncate(value, limit=MAX_TITLE_LENGTH)


def _candidate_source_key(value: str) -> str:
    return _truncate(value, limit=MAX_SOURCE_KEY_LENGTH)


def _deterministic_candidate(family: str, canonical_key: str, source_key: str, title: str, rank: int) -> dict[str, Any]:
    return {
        "family": family,
        "canonical_key": canonical_key,
        "source_key": _candidate_source_key(source_key),
        "title": _candidate_title(title),
        "rank": rank,
    }


def _build_deterministic_candidates(retrieved_context: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    rank = 0
    for row in getattr(retrieved_context, "catalog_tables", []) or []:
        rank += 1
        candidates.append(
            _deterministic_candidate(
                "catalog_table",
                normalize_table_name(row.table_name),
                f"table.{row.table_name}",
                row.table_name,
                rank,
            )
        )
    for row in getattr(retrieved_context, "catalog_fields", []) or []:
        rank += 1
        title = f"{row.table_name}.{row.field_name}"
        candidates.append(
            _deterministic_candidate(
                "catalog_field",
                normalize_field_name(row.field_name),
                f"field.{row.table_name}.{row.field_name}",
                title,
                rank,
            )
        )
    for row in getattr(retrieved_context, "glossary_terms", []) or []:
        rank += 1
        candidates.append(
            _deterministic_candidate(
                "glossary_term",
                _normalize_text(row.term),
                f"glossary.{row.term}",
                row.term,
                rank,
            )
        )
    for row in getattr(retrieved_context, "sql_examples", []) or []:
        rank += 1
        source_key = getattr(row, "source_key", None) or f"sql_example.{rank}"
        title = getattr(row, "natural_language_request", None) or source_key
        candidates.append(
            _deterministic_candidate(
                "sql_example",
                _normalize_text(str(source_key)),
                str(source_key),
                str(title),
                rank,
            )
        )
    for row in getattr(retrieved_context, "error_cases", []) or []:
        rank += 1
        source_key = getattr(row, "source_key", None) or f"sql_error_case.{rank}"
        title = getattr(row, "error_type", None) or source_key
        candidates.append(
            _deterministic_candidate(
                "sql_error_case",
                _normalize_text(str(source_key)),
                str(source_key),
                str(title),
                rank,
            )
        )
    return candidates


def _stable_unique(tokens: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = _normalize_text(token)
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def _table_tokens(record: dict[str, Any]) -> list[str]:
    metadata = dict(record.get("metadata") or {})
    candidates = [
        normalize_table_name(metadata.get("table_name") or ""),
        normalize_table_name(record.get("title") or ""),
        _normalize_text(record.get("source_key") or ""),
    ]
    return _stable_unique(candidates)


def _field_tokens(record: dict[str, Any]) -> list[str]:
    metadata = dict(record.get("metadata") or {})
    title = str(record.get("title") or "")
    title_field = title.rsplit(".", 1)[-1] if "." in title else title
    candidates = [normalize_field_name(metadata.get("field_name") or "")]
    candidates.extend(normalize_field_name(item) for item in (metadata.get("aliases") or []))
    candidates.extend(
        [
            normalize_field_name(title_field),
            normalize_field_name(record.get("source_key") or ""),
        ]
    )
    return _stable_unique(candidates)


def _glossary_tokens(record: dict[str, Any]) -> list[str]:
    metadata = dict(record.get("metadata") or {})
    candidates = [
        _normalize_text(metadata.get("term") or ""),
        _normalize_text(record.get("title") or ""),
    ]
    candidates.extend(_normalize_text(item) for item in (metadata.get("synonyms") or []))
    candidates.append(_normalize_text(record.get("source_key") or ""))
    return _stable_unique(candidates)


def _canonical_key_for_record(record: dict[str, Any]) -> tuple[str | None, str | None, str]:
    family = str(record.get("asset_family") or "").strip()
    source_key = str(record.get("source_key") or "")
    title = str(record.get("title") or source_key)
    if family == "catalog_table":
        token = next(iter(_table_tokens(record)), "")
        return family, token, title
    if family == "catalog_field":
        token = next(iter(_field_tokens(record)), "")
        return family, token, title
    if family == "glossary_term":
        token = next(iter(_glossary_tokens(record)), "")
        return family, token, title
    if family == "sql_example":
        return family, _normalize_text(source_key), title
    if family == "sql_error_case":
        return family, _normalize_text(source_key), title
    return None, None, title


def _build_existing_keys(deterministic_candidates: list[dict[str, Any]]) -> dict[str, set[str]]:
    existing: dict[str, set[str]] = {
        "catalog_table": set(),
        "catalog_field": set(),
        "glossary_term": set(),
        "sql_example": set(),
        "sql_error_case": set(),
    }
    for item in deterministic_candidates:
        family = str(item.get("family") or "")
        key = str(item.get("canonical_key") or "")
        if family in existing and key:
            existing[family].add(key)
    return existing


def _rank_vector_candidates(
    *,
    natural_language_request: str,
    country: str,
    run_type: str,
    output_bucket: str | None,
    config: HybridRetrievalConfigV1,
    project_root: Path,
) -> list[dict[str, Any]]:
    payload, _path = _load_vector_index(config=config, project_root=project_root)
    query_vector = _vectorize_query_record(
        natural_language_request=natural_language_request,
        country=country,
        run_type=run_type,
        output_bucket=output_bucket,
    )
    candidates: list[dict[str, Any]] = []
    for entry in payload.get("records", []):
        entry_country = str(entry.get("country") or "").strip().lower()
        if entry_country not in {country, "common", "multi"}:
            continue
        family, canonical_key, title = _canonical_key_for_record(entry)
        if not family or not canonical_key:
            continue
        score = _sparse_dot(query_vector, dict(entry.get("vector") or {}))
        candidates.append(
            {
                "record_id": str(entry.get("record_id") or ""),
                "source_key": _candidate_source_key(str(entry.get("source_key") or "")),
                "asset_family": family,
                "canonical_key": canonical_key,
                "title": _candidate_title(title),
                "score": round(float(score), 6),
                "metadata": dict(entry.get("metadata") or {}),
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["asset_family"], item["source_key"]))
    for rank, item in enumerate(candidates[: DEFAULT_MAX_VECTOR_CANDIDATES], start=1):
        item["rank"] = rank
    return candidates[: DEFAULT_MAX_VECTOR_CANDIDATES]


def _select_vector_supplements(
    *,
    config: HybridRetrievalConfigV1,
    deterministic_candidates: list[dict[str, Any]],
    vector_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    existing = _build_existing_keys(deterministic_candidates)
    accepted_keys: dict[str, set[str]] = {family: set() for family in existing}
    family_counts: dict[str, int] = {family: 0 for family in existing}
    for candidate in vector_candidates:
        family = str(candidate["asset_family"])
        canonical_key = str(candidate["canonical_key"])
        rejection_reason: str | None = None
        if family == "sql_error_case":
            rejection_reason = HybridFallbackReason.FUSION_GUARD_FAILED.value
        elif family not in config.family_score_thresholds:
            rejection_reason = "unsupported_family"
        elif candidate["rank"] > config.vector_rank_limit:
            rejection_reason = "rank_above_limit"
        elif float(candidate["score"]) < float(config.family_score_thresholds.get(family, 0.0)):
            rejection_reason = "below_family_threshold"
        elif canonical_key in existing.get(family, set()):
            rejection_reason = "duplicate_with_deterministic"
        elif canonical_key in accepted_keys.get(family, set()):
            rejection_reason = "duplicate_with_accepted_supplement"
        elif len(accepted) >= config.total_vector_supplement_cap:
            rejection_reason = "case_cap_reached"
        elif family_counts.get(family, 0) >= int(config.family_caps.get(family, 0)):
            rejection_reason = "family_cap_reached"
        if rejection_reason is not None:
            rejected.append(
                {
                    "record_id": candidate["record_id"],
                    "source_key": candidate["source_key"],
                    "asset_family": family,
                    "title": candidate["title"],
                    "score": candidate["score"],
                    "rank": candidate["rank"],
                    "rejected_reason": "sql_error_case_disabled" if family == "sql_error_case" else rejection_reason,
                }
            )
            continue
        accepted_keys[family].add(canonical_key)
        family_counts[family] += 1
        accepted.append(
            {
                "record_id": candidate["record_id"],
                "source_key": candidate["source_key"],
                "asset_family": family,
                "title": candidate["title"],
                "score": candidate["score"],
                "rank": candidate["rank"],
                "accepted_reason": "shadow_candidate_selected",
                "metadata": dict(candidate.get("metadata") or {}),
            }
        )
    return accepted[:DEFAULT_MAX_ACCEPTED_SUPPLEMENTS], rejected[:DEFAULT_MAX_REJECTED_CANDIDATES]


def _serialize_vector_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": candidate["record_id"],
        "source_key": candidate["source_key"],
        "asset_family": candidate["asset_family"],
        "title": candidate["title"],
        "score": candidate["score"],
        "rank": candidate["rank"],
    }


def _serialize_accepted_supplement(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": candidate["record_id"],
        "source_key": candidate["source_key"],
        "asset_family": candidate["asset_family"],
        "title": candidate["title"],
        "score": candidate["score"],
        "rank": candidate["rank"],
        "accepted_reason": candidate["accepted_reason"],
    }


def _default_candidate_attempt(
    *,
    attempted_mode: str | None = None,
    prompt_injection_mode: str = PROMPT_INJECTION_NONE,
    prompt_candidate_count: int = 0,
) -> dict[str, Any]:
    return {
        "attempted": False,
        "attempted_mode": attempted_mode,
        "prompt_injection_mode": prompt_injection_mode,
        "prompt_candidate_count": prompt_candidate_count,
        "output_sql_kind": None,
        "output_sql_hash": None,
        "discarded": False,
        "discard_reason": None,
    }


def _sorted_supplemental_candidates(supplements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        supplements,
        key=lambda item: (
            int(item.get("rank") or 0),
            -float(item.get("score") or 0.0),
            _SUPPLEMENTAL_FAMILY_ORDER.get(str(item.get("asset_family") or ""), 99),
            str(item.get("source_key") or ""),
        ),
    )


def _extract_table_name(candidate: dict[str, Any]) -> str:
    metadata = dict(candidate.get("metadata") or {})
    table_name = normalize_table_name(metadata.get("table_name") or "")
    if table_name:
        return table_name
    title = str(candidate.get("title") or "")
    if "." in title:
        return normalize_table_name(title.rsplit(".", 1)[0])
    source_key = str(candidate.get("source_key") or "")
    parts = source_key.split(".")
    if len(parts) >= 4 and parts[0] in {"field", "table"}:
        return normalize_table_name(parts[2])
    return ""


def _extract_field_name(candidate: dict[str, Any]) -> str:
    metadata = dict(candidate.get("metadata") or {})
    field_name = normalize_field_name(metadata.get("field_name") or "")
    if field_name:
        return field_name
    title = str(candidate.get("title") or "")
    if "." in title:
        return normalize_field_name(title.rsplit(".", 1)[-1])
    source_key = str(candidate.get("source_key") or "")
    return normalize_field_name(source_key.split(".")[-1] if source_key else "")


def _supplemental_lines(candidate: dict[str, Any], index: int) -> list[str]:
    metadata = dict(candidate.get("metadata") or {})
    family = str(candidate.get("asset_family") or "")
    lines = [
        f"{index}. asset_family: {family}",
        f"   source_key: {_candidate_source_key(str(candidate.get('source_key') or ''))}",
        f"   title: {_candidate_title(str(candidate.get('title') or ''))}",
    ]
    if family == "catalog_table":
        table_name = _extract_table_name(candidate)
        detail = _truncate(
            str(metadata.get("purpose") or metadata.get("description") or metadata.get("business_meaning") or ""),
            limit=MAX_DETAIL_LENGTH,
        )
        if table_name:
            lines.append(f"   table: {table_name}")
        if detail:
            lines.append(f"   description: {detail}")
    elif family == "catalog_field":
        table_name = _extract_table_name(candidate)
        field_name = _extract_field_name(candidate)
        detail = _truncate(
            str(metadata.get("business_meaning") or metadata.get("description") or metadata.get("definition") or ""),
            limit=MAX_DETAIL_LENGTH,
        )
        if table_name:
            lines.append(f"   table: {table_name}")
        if field_name:
            lines.append(f"   field: {field_name}")
        if detail:
            lines.append(f"   description: {detail}")
    elif family == "glossary_term":
        definition = _truncate(
            str(metadata.get("definition") or metadata.get("description") or ""),
            limit=MAX_DETAIL_LENGTH,
        )
        if definition:
            lines.append(f"   definition: {definition}")
    elif family == "sql_example":
        summary = _truncate(
            str(metadata.get("pattern_summary") or metadata.get("summary") or metadata.get("description") or ""),
            limit=MAX_DETAIL_LENGTH,
        )
        if summary:
            lines.append(f"   summary: {summary}")
    return lines


def build_supplemental_prompt_section(
    accepted_supplements: list[dict[str, Any]],
) -> tuple[str, int, str]:
    ordered = _sorted_supplemental_candidates(list(accepted_supplements or []))
    if not ordered:
        return "", 0, PROMPT_INJECTION_NONE
    lines = [
        "# === Supplemental Hybrid Knowledge Candidates ===",
        "These candidates are supplemental retrieval hints.",
        "They do not override deterministic knowledge.",
        "Use them only when they are consistent with the primary schema context.",
        "If there is any conflict, prefer the deterministic context.",
        "",
    ]
    added = 0
    for index, candidate in enumerate(ordered, start=1):
        candidate_lines = _supplemental_lines(candidate, index)
        projected = "\n".join(lines + candidate_lines).strip()
        if len(projected) > DEFAULT_MAX_SUPPLEMENTAL_SECTION_CHARS:
            break
        lines.extend(candidate_lines)
        lines.append("")
        added += 1
    if not added:
        return "", 0, PROMPT_INJECTION_NONE
    section = "\n".join(lines).strip()
    return section, added, PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1


def _trace_payload(
    *,
    config: HybridRetrievalConfigV1,
    configured_mode: HybridRetrievalMode,
    effective_mode: HybridRetrievalMode,
    fallback_applied: bool,
    fallback_reason: str | None,
    prompt_injection_mode: str,
    prompt_candidate_count: int,
    final_generation_pass: str,
    deterministic_candidates: list[dict[str, Any]],
    vector_candidates: list[dict[str, Any]],
    accepted_supplements: list[dict[str, Any]],
    rejected_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": DEFAULT_TRACE_SCHEMA_VERSION,
        "configured_mode": configured_mode.value,
        "effective_mode": effective_mode.value,
        "source_namespace": config.source_namespace,
        "fallback_applied": fallback_applied,
        "fallback_reason": fallback_reason,
        "config_snapshot": _config_snapshot(
            config,
            EffectiveModeDecision(
                configured_mode=configured_mode,
                effective_mode=effective_mode,
                fallback_reason=HybridFallbackReason(fallback_reason) if fallback_reason in {reason.value for reason in HybridFallbackReason} else None,
                fallback_applied=fallback_applied,
                sample_hit=(configured_mode is not HybridRetrievalMode.HYBRID_SHADOW) or not fallback_applied,
                should_attempt_shadow=effective_mode is not HybridRetrievalMode.DETERMINISTIC_ONLY,
            ),
        ),
        "prompt_injection_mode": prompt_injection_mode,
        "prompt_candidate_count": prompt_candidate_count,
        "final_generation_pass": final_generation_pass,
        "candidate_counts": {
            "deterministic_total": len(deterministic_candidates),
            "vector_total": len(vector_candidates),
            "accepted_total": len(accepted_supplements),
            "rejected_total": len(rejected_candidates),
        },
        "candidate_attempt": _default_candidate_attempt(
            attempted_mode=(
                configured_mode.value
                if configured_mode is HybridRetrievalMode.HYBRID_CANDIDATE and prompt_injection_mode == PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1
                else None
            ),
            prompt_injection_mode=prompt_injection_mode,
            prompt_candidate_count=prompt_candidate_count,
        ),
        "deterministic_candidates": deterministic_candidates[:DEFAULT_MAX_DETERMINISTIC_CANDIDATES],
        "vector_candidates": [_serialize_vector_candidate(item) for item in vector_candidates[:DEFAULT_MAX_VECTOR_CANDIDATES]],
        "accepted_supplements": [_serialize_accepted_supplement(item) for item in accepted_supplements[:DEFAULT_MAX_ACCEPTED_SUPPLEMENTS]],
        "rejected_candidates": rejected_candidates[:DEFAULT_MAX_REJECTED_CANDIDATES],
    }


def _config_snapshot(config: HybridRetrievalConfigV1, decision: EffectiveModeDecision) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "configured_mode": config.retrieval_mode.value,
        "effective_mode": decision.effective_mode.value,
        "source_namespace": config.source_namespace,
        "allow_countries": list(config.allow_countries),
        "allow_project_ids": list(config.allow_project_ids),
        "vector_rank_limit": config.vector_rank_limit,
        "family_score_thresholds": dict(config.family_score_thresholds),
        "family_caps": dict(config.family_caps),
        "total_vector_supplement_cap": config.total_vector_supplement_cap,
        "deterministic_pass_guard": config.deterministic_pass_guard,
        "shadow_sample_rate": config.shadow_sample_rate,
    }


def _fallback_trace(
    *,
    config: HybridRetrievalConfigV1,
    decision: EffectiveModeDecision,
    deterministic_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    trace = _trace_payload(
        config=config,
        configured_mode=decision.configured_mode,
        effective_mode=decision.effective_mode,
        fallback_applied=True,
        fallback_reason=_safe_reason(decision.fallback_reason),
        prompt_injection_mode=PROMPT_INJECTION_NONE,
        prompt_candidate_count=0,
        final_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC,
        deterministic_candidates=deterministic_candidates,
        vector_candidates=[],
        accepted_supplements=[],
        rejected_candidates=[],
    )
    trace["config_snapshot"] = _config_snapshot(config, decision)
    return trace


def _looks_like_non_query_only_intent(natural_language_request: str) -> bool:
    return bool(_NON_QUERY_ONLY_INTENT_PATTERN.search(str(natural_language_request or "").strip()))


def build_shadow_trace(
    *,
    settings: Any,
    natural_language_request: str,
    country: str,
    project_id: str | None,
    run_type: str,
    output_bucket: str | None,
    retrieved_context: Any,
    request_key: str,
) -> ShadowTraceBuildResult:
    try:
        config = load_hybrid_config(settings)
    except Exception:
        return ShadowTraceBuildResult(
            trace=None,
            audit_summary=_build_audit_summary(
                configured_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
                effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
                fallback_reason=HybridFallbackReason.CONFIG_INVALID.value,
                trace_present=False,
            ),
        )
    decision = evaluate_effective_mode(
        config=config,
        country=country,
        project_id=project_id,
        run_type=run_type,
        request_key=request_key,
    )
    if not config.enabled:
        return ShadowTraceBuildResult(
            trace=None,
            audit_summary=_build_audit_summary(
                configured_mode=decision.configured_mode,
                effective_mode=decision.effective_mode,
                fallback_reason=_safe_reason(decision.fallback_reason),
                trace_present=False,
            ),
        )

    deterministic_candidates = _build_deterministic_candidates(retrieved_context)
    supplemental_prompt_section = ""
    try:
        if not decision.should_attempt_shadow:
            trace = _fallback_trace(
                config=config,
                decision=decision,
                deterministic_candidates=deterministic_candidates,
            )
        else:
            vector_candidates = _rank_vector_candidates(
                natural_language_request=natural_language_request,
                country=country,
                run_type=run_type,
                output_bucket=output_bucket,
                config=config,
                project_root=settings.project_root,
            )
            accepted, rejected = _select_vector_supplements(
                config=config,
                deterministic_candidates=deterministic_candidates,
                vector_candidates=vector_candidates,
            )
            if decision.effective_mode is HybridRetrievalMode.HYBRID_CANDIDATE:
                if _looks_like_non_query_only_intent(natural_language_request):
                    trace = _fallback_trace(
                        config=config,
                        decision=EffectiveModeDecision(
                            configured_mode=decision.configured_mode,
                            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
                            fallback_reason=HybridFallbackReason.UNSUPPORTED_SQL_KIND,
                            fallback_applied=True,
                            sample_hit=decision.sample_hit,
                            should_attempt_shadow=False,
                        ),
                        deterministic_candidates=deterministic_candidates,
                    )
                else:
                    supplemental_prompt_section, prompt_candidate_count, prompt_injection_mode = build_supplemental_prompt_section(accepted)
                    if not supplemental_prompt_section or prompt_candidate_count <= 0:
                        trace = _fallback_trace(
                            config=config,
                            decision=EffectiveModeDecision(
                                configured_mode=decision.configured_mode,
                                effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
                                fallback_reason=HybridFallbackReason.FUSION_GUARD_FAILED,
                                fallback_applied=True,
                                sample_hit=decision.sample_hit,
                                should_attempt_shadow=False,
                            ),
                            deterministic_candidates=deterministic_candidates,
                        )
                    else:
                        trace = _trace_payload(
                            config=config,
                            configured_mode=decision.configured_mode,
                            effective_mode=decision.effective_mode,
                            fallback_applied=False,
                            fallback_reason=None,
                            prompt_injection_mode=prompt_injection_mode,
                            prompt_candidate_count=prompt_candidate_count,
                            final_generation_pass=FINAL_GENERATION_PASS_HYBRID_CANDIDATE,
                            deterministic_candidates=deterministic_candidates,
                            vector_candidates=vector_candidates,
                            accepted_supplements=accepted,
                            rejected_candidates=rejected,
                        )
                        trace["config_snapshot"] = _config_snapshot(config, decision)
            else:
                trace = _trace_payload(
                    config=config,
                    configured_mode=decision.configured_mode,
                    effective_mode=decision.effective_mode,
                    fallback_applied=False,
                    fallback_reason=None,
                    prompt_injection_mode=PROMPT_INJECTION_NONE,
                    prompt_candidate_count=0,
                    final_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC,
                    deterministic_candidates=deterministic_candidates,
                    vector_candidates=vector_candidates,
                    accepted_supplements=accepted,
                    rejected_candidates=rejected,
                )
                trace["config_snapshot"] = _config_snapshot(config, decision)
        json.dumps(trace, ensure_ascii=False)
        return ShadowTraceBuildResult(
            trace=trace,
            audit_summary=extract_hybrid_audit_summary({"hybrid_trace": trace}),
            supplemental_prompt_section=supplemental_prompt_section,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        trace = _fallback_trace(
            config=config,
            decision=EffectiveModeDecision(
                configured_mode=decision.configured_mode,
                effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
                fallback_reason=HybridFallbackReason.VECTOR_BACKEND_UNAVAILABLE,
                fallback_applied=True,
                sample_hit=decision.sample_hit,
                should_attempt_shadow=False,
            ),
            deterministic_candidates=deterministic_candidates,
        )
    except Exception:
        trace = _fallback_trace(
            config=config,
            decision=EffectiveModeDecision(
                configured_mode=decision.configured_mode,
                effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
                fallback_reason=HybridFallbackReason.VECTOR_QUERY_FAILED,
                fallback_applied=True,
                sample_hit=decision.sample_hit,
                should_attempt_shadow=False,
            ),
            deterministic_candidates=deterministic_candidates,
        )
    try:
        json.dumps(trace, ensure_ascii=False)
        return ShadowTraceBuildResult(
            trace=trace,
            audit_summary=extract_hybrid_audit_summary({"hybrid_trace": trace}),
        )
    except Exception:
        return ShadowTraceBuildResult(
            trace=None,
            audit_summary=_build_audit_summary(
                configured_mode=decision.configured_mode,
                effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
                fallback_reason=HybridFallbackReason.AUDIT_TRACE_UNAVAILABLE.value,
                trace_present=False,
            ),
        )


def finalize_shadow_trace_for_sql_kind(
    trace: dict[str, Any] | None,
    *,
    sql_kind: str | None,
) -> dict[str, Any] | None:
    if not trace:
        return None
    normalized = str(sql_kind or "").strip().lower() or "query_only"
    if normalized == "query_only":
        return trace
    finalized = dict(trace)
    finalized["effective_mode"] = HybridRetrievalMode.DETERMINISTIC_ONLY.value
    finalized["fallback_applied"] = True
    finalized["fallback_reason"] = HybridFallbackReason.UNSUPPORTED_SQL_KIND.value
    finalized["prompt_injection_mode"] = PROMPT_INJECTION_NONE
    finalized["prompt_candidate_count"] = 0
    return finalized


def extract_hybrid_audit_summary(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    trace = dict((snapshot or {}).get("hybrid_trace") or {})
    if not trace:
        return _build_audit_summary(
            configured_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            effective_mode=HybridRetrievalMode.DETERMINISTIC_ONLY,
            fallback_reason=HybridFallbackReason.HYBRID_DISABLED.value,
            trace_present=False,
        )
    configured_mode = str(trace.get("configured_mode") or HybridRetrievalMode.DETERMINISTIC_ONLY.value)
    effective_mode = str(trace.get("effective_mode") or HybridRetrievalMode.DETERMINISTIC_ONLY.value)
    return _build_audit_summary(
        configured_mode=HybridRetrievalMode(configured_mode),
        effective_mode=HybridRetrievalMode(effective_mode),
        fallback_reason=trace.get("fallback_reason"),
        attempted_mode=(trace.get("candidate_attempt") or {}).get("attempted_mode"),
        final_generation_pass=str(trace.get("final_generation_pass") or FINAL_GENERATION_PASS_DETERMINISTIC),
        prompt_injection_mode=str(trace.get("prompt_injection_mode") or PROMPT_INJECTION_NONE),
        prompt_candidate_count=int(trace.get("prompt_candidate_count") or 0),
        candidate_attempted=bool((trace.get("candidate_attempt") or {}).get("attempted")),
        candidate_discarded=bool((trace.get("candidate_attempt") or {}).get("discarded")),
        candidate_discard_reason=(trace.get("candidate_attempt") or {}).get("discard_reason"),
        trace_present=True,
    )
