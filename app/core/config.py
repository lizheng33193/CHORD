"""Application configuration module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseModel):
    """Centralize project settings with simple env-based overrides."""

    app_name: str = os.getenv("APP_NAME", "User Profile Multi-Agent API")
    app_version: str = os.getenv("APP_VERSION", "0.2.0")
    model_mode: str = os.getenv("MODEL_MODE", "gemini").lower()
    model_name: str = os.getenv("MODEL_NAME", "gemini-2.5-flash")
    model_timeout_seconds: int = int(os.getenv("MODEL_TIMEOUT_SECONDS", "90"))
    model_max_output_tokens: int = int(os.getenv("MODEL_MAX_OUTPUT_TOKENS", "8192"))
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str | None = os.getenv("GEMINI_MODEL")
    vertex_project_id: str | None = os.getenv("VERTEX_PROJECT_ID")
    vertex_location: str = os.getenv("VERTEX_LOCATION", "global")
    google_application_credentials: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    app_profile_prompt_max_apps: int = int(os.getenv("APP_PROFILE_PROMPT_MAX_APPS", "80"))
    app_profile_prompt_max_detail_apps: int = int(
        os.getenv("APP_PROFILE_PROMPT_MAX_DETAIL_APPS", "6")
    )
    app_profile_short_report: bool = os.getenv("APP_PROFILE_SHORT_REPORT", "0").strip() in {
        "1",
        "true",
        "True",
        "yes",
        "YES",
    }
    default_country_code: str = os.getenv("DEFAULT_COUNTRY_CODE", "mx").lower()
    data_source: str = os.getenv("DATA_SOURCE", "local").lower()
    prompt_dir: str = os.getenv("PROMPT_DIR", "app/prompts")
    data_dir: str = os.getenv("DATA_DIR", "data")
    app_source_dir: str = os.getenv("APP_SOURCE_DIR", "data/app/source")
    app_by_uid_dir: str = os.getenv("APP_BY_UID_DIR", "data/app/by_uid")
    behavior_source_dir: str = os.getenv("BEHAVIOR_SOURCE_DIR", "data/behavior/source")
    behavior_by_uid_dir: str = os.getenv("BEHAVIOR_BY_UID_DIR", "data/behavior/by_uid")
    credit_source_dir: str = os.getenv("CREDIT_SOURCE_DIR", "data/credit/source")
    credit_by_uid_dir: str = os.getenv("CREDIT_BY_UID_DIR", "data/credit/by_uid")
    output_dir: str = os.getenv("OUTPUT_DIR", "outputs")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    # data_acquisition_agent V2 — 非敏感配置（凭据 DA_DB_* 不入 Settings，见 v2 §6.1）
    da_max_result_rows: int = int(os.getenv("DA_MAX_RESULT_ROWS", "100000"))
    da_query_timeout_seconds: int = int(os.getenv("DA_QUERY_TIMEOUT_SECONDS", "60"))
    da_connection_profile: str = os.getenv("DA_CONNECTION_PROFILE", "default")
    uid_transition_duration_ms: int = int(os.getenv("UID_TRANSITION_DURATION_MS", "20000"))
    auth_enabled: bool = os.getenv("AUTH_ENABLED", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }
    auth_database_url: str | None = os.getenv("AUTH_DATABASE_URL")
    auth_jwt_secret: str = os.getenv("AUTH_JWT_SECRET", "change-me-in-env")
    auth_jwt_expire_minutes: int = int(os.getenv("AUTH_JWT_EXPIRE_MINUTES", "1440"))
    auth_seed_on_startup: bool = os.getenv("AUTH_SEED_ON_STARTUP", "1").strip().lower() in {
        "1", "true", "yes", "on",
    }
    auth_default_register_role: str = os.getenv("AUTH_DEFAULT_REGISTER_ROLE", "analyst").strip().lower() or "analyst"
    default_admin_username: str = os.getenv("DEFAULT_ADMIN_USERNAME", "admin").strip() or "admin"
    default_admin_email: str = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com").strip() or "admin@example.com"
    default_admin_password: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123456").strip() or "admin123456"
    auth_demo_user_id: str = os.getenv("AUTH_DEMO_USER_ID", "local-default-user").strip() or "local-default-user"
    auth_demo_username: str = os.getenv("AUTH_DEMO_USERNAME", "demo-user").strip() or "demo-user"
    auth_demo_display_name: str = os.getenv("AUTH_DEMO_DISPLAY_NAME", "Demo User").strip() or "Demo User"
    auth_demo_project_id: str = os.getenv("AUTH_DEMO_PROJECT_ID", "agent-user-profile-fork").strip() or "agent-user-profile-fork"
    auth_demo_project_code: str = os.getenv("AUTH_DEMO_PROJECT_CODE", "maps_lz").strip() or "maps_lz"
    auth_demo_country: str = os.getenv("AUTH_DEMO_COUNTRY", "mx").strip().lower() or "mx"
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "maps_lz").strip() or "maps_lz"
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "maps_lz").strip()
    mysql_database: str = os.getenv("MYSQL_DATABASE", "maps_lz").strip() or "maps_lz"
    dashscope_api_key: str | None = os.getenv("DASHSCOPE_API_KEY")
    risk_knowledge_embedding_provider: str = os.getenv(
        "RISK_KNOWLEDGE_EMBEDDING_PROVIDER",
        "openai_compatible",
    ).strip() or "openai_compatible"
    risk_knowledge_embedding_api_key: str | None = (
        os.getenv("RISK_KNOWLEDGE_EMBEDDING_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    )
    risk_knowledge_embedding_base_url: str | None = os.getenv("RISK_KNOWLEDGE_EMBEDDING_BASE_URL")
    risk_knowledge_embedding_model: str = os.getenv(
        "RISK_KNOWLEDGE_EMBEDDING_MODEL",
        "text-embedding-v3",
    ).strip() or "text-embedding-v3"
    risk_knowledge_embedding_dimension: int = int(
        os.getenv("RISK_KNOWLEDGE_EMBEDDING_DIMENSION", "1024")
    )
    risk_knowledge_embedding_output_type: str = os.getenv(
        "RISK_KNOWLEDGE_EMBEDDING_OUTPUT_TYPE",
        "dense",
    ).strip() or "dense"
    risk_knowledge_embedding_text_type: str = os.getenv(
        "RISK_KNOWLEDGE_EMBEDDING_TEXT_TYPE",
        "document",
    ).strip() or "document"
    risk_knowledge_embedding_max_batch_size: int = int(
        os.getenv("RISK_KNOWLEDGE_EMBEDDING_MAX_BATCH_SIZE", "10")
    )
    risk_knowledge_faiss_artifact_dir: str = os.getenv(
        "RISK_KNOWLEDGE_FAISS_ARTIFACT_DIR",
        "outputs/risk_knowledge/faiss",
    )
    risk_knowledge_upload_dir: str = os.getenv(
        "RISK_KNOWLEDGE_UPLOAD_DIR",
        "storage/risk_knowledge/uploads",
    )
    risk_knowledge_max_upload_mb: int = int(
        os.getenv("RISK_KNOWLEDGE_MAX_UPLOAD_MB", "50")
    )
    risk_knowledge_allowed_upload_extensions: str = os.getenv(
        "RISK_KNOWLEDGE_ALLOWED_UPLOAD_EXTENSIONS",
        "pdf,docx,md,txt",
    ).strip() or "pdf,docx,md,txt"
    risk_knowledge_redis_url: str = os.getenv(
        "RISK_KNOWLEDGE_REDIS_URL",
        "redis://127.0.0.1:6379/15",
    ).strip() or "redis://127.0.0.1:6379/15"
    risk_knowledge_redis_key_prefix: str = os.getenv(
        "RISK_KNOWLEDGE_REDIS_KEY_PREFIX",
        "chord:risk_knowledge",
    ).strip() or "chord:risk_knowledge"
    risk_knowledge_indexing_lock_ttl_seconds: int = int(
        os.getenv("RISK_KNOWLEDGE_INDEXING_LOCK_TTL_SECONDS", "120")
    )
    risk_knowledge_indexing_state_ttl_seconds: int = int(
        os.getenv("RISK_KNOWLEDGE_INDEXING_STATE_TTL_SECONDS", "3600")
    )
    risk_knowledge_indexing_heartbeat_seconds: int = int(
        os.getenv("RISK_KNOWLEDGE_INDEXING_HEARTBEAT_SECONDS", "30")
    )
    risk_knowledge_indexing_max_retries: int = int(
        os.getenv("RISK_KNOWLEDGE_INDEXING_MAX_RETRIES", "3")
    )
    risk_knowledge_retrieval_vector_top_k: int = int(
        os.getenv("RISK_KNOWLEDGE_RETRIEVAL_VECTOR_TOP_K", "50")
    )
    risk_knowledge_retrieval_keyword_top_k: int = int(
        os.getenv("RISK_KNOWLEDGE_RETRIEVAL_KEYWORD_TOP_K", "50")
    )
    risk_knowledge_retrieval_fused_top_k: int = int(
        os.getenv("RISK_KNOWLEDGE_RETRIEVAL_FUSED_TOP_K", "10")
    )
    risk_knowledge_retrieval_rrf_k: int = int(
        os.getenv("RISK_KNOWLEDGE_RETRIEVAL_RRF_K", "60")
    )
    risk_knowledge_retrieval_max_query_chars: int = int(
        os.getenv("RISK_KNOWLEDGE_RETRIEVAL_MAX_QUERY_CHARS", "512")
    )
    risk_knowledge_bm25_k1: float = float(os.getenv("RISK_KNOWLEDGE_BM25_K1", "1.5"))
    risk_knowledge_bm25_b: float = float(os.getenv("RISK_KNOWLEDGE_BM25_B", "0.75"))
    risk_knowledge_bm25_tokenizer: str = os.getenv(
        "RISK_KNOWLEDGE_BM25_TOKENIZER",
        "char_bigram",
    ).strip() or "char_bigram"
    risk_knowledge_query_embedding_text_type: str = os.getenv(
        "RISK_KNOWLEDGE_QUERY_EMBEDDING_TEXT_TYPE",
        "query",
    ).strip() or "query"
    risk_knowledge_reranker_provider: str = os.getenv(
        "RISK_KNOWLEDGE_RERANKER_PROVIDER",
        "dashscope",
    ).strip() or "dashscope"
    risk_knowledge_reranker_model: str = os.getenv(
        "RISK_KNOWLEDGE_RERANKER_MODEL",
        "qwen3-rerank",
    ).strip() or "qwen3-rerank"
    risk_knowledge_reranker_top_n: int = int(
        os.getenv("RISK_KNOWLEDGE_RERANKER_TOP_N", "10")
    )
    risk_knowledge_reranker_timeout_seconds: int = int(
        os.getenv("RISK_KNOWLEDGE_RERANKER_TIMEOUT_SECONDS", "30")
    )
    risk_knowledge_reranker_max_candidates: int = int(
        os.getenv("RISK_KNOWLEDGE_RERANKER_MAX_CANDIDATES", "50")
    )
    risk_knowledge_reranker_http_base_url: str | None = os.getenv(
        "RISK_KNOWLEDGE_RERANKER_HTTP_BASE_URL"
    )
    risk_knowledge_evidence_max_count: int = int(
        os.getenv("RISK_KNOWLEDGE_EVIDENCE_MAX_COUNT", "6")
    )
    risk_knowledge_evidence_min_count: int = int(
        os.getenv("RISK_KNOWLEDGE_EVIDENCE_MIN_COUNT", "1")
    )
    risk_knowledge_evidence_min_rerank_score: float = float(
        os.getenv("RISK_KNOWLEDGE_EVIDENCE_MIN_RERANK_SCORE", "0.2")
    )
    risk_knowledge_evidence_max_total_chars: int = int(
        os.getenv("RISK_KNOWLEDGE_EVIDENCE_MAX_TOTAL_CHARS", "6000")
    )
    risk_knowledge_evidence_dedup_by_content_hash: bool = os.getenv(
        "RISK_KNOWLEDGE_EVIDENCE_DEDUP_BY_CONTENT_HASH",
        "1",
    ).strip().lower() in {"1", "true", "yes", "on"}
    risk_knowledge_answer_provider: str = os.getenv(
        "RISK_KNOWLEDGE_ANSWER_PROVIDER",
        "deterministic",
    ).strip() or "deterministic"
    risk_knowledge_answer_model: str = os.getenv(
        "RISK_KNOWLEDGE_ANSWER_MODEL",
        "",
    ).strip()
    risk_knowledge_answer_timeout_seconds: int = int(
        os.getenv("RISK_KNOWLEDGE_ANSWER_TIMEOUT_SECONDS", "60")
    )
    risk_knowledge_answer_max_context_chars: int = int(
        os.getenv("RISK_KNOWLEDGE_ANSWER_MAX_CONTEXT_CHARS", "6000")
    )
    risk_knowledge_bm25_cache_size: int = int(
        os.getenv("RISK_KNOWLEDGE_BM25_CACHE_SIZE", "16")
    )
    risk_knowledge_bm25_max_scope_chunks: int = int(
        os.getenv("RISK_KNOWLEDGE_BM25_MAX_SCOPE_CHUNKS", "5000")
    )
    hybrid_retrieval_enabled_raw: str = os.getenv("HYBRID_RETRIEVAL_ENABLED", "0")
    hybrid_retrieval_mode_raw: str = os.getenv("HYBRID_RETRIEVAL_MODE", "deterministic_only")
    hybrid_retrieval_source_namespace_raw: str = os.getenv("HYBRID_RETRIEVAL_SOURCE_NAMESPACE", "m2b_legacy_v3")
    hybrid_retrieval_vector_index_path_raw: str = os.getenv("HYBRID_RETRIEVAL_VECTOR_INDEX_PATH", "")
    hybrid_retrieval_allow_countries_raw: str = os.getenv("HYBRID_RETRIEVAL_ALLOW_COUNTRIES", "")
    hybrid_retrieval_allow_project_ids_raw: str = os.getenv("HYBRID_RETRIEVAL_ALLOW_PROJECT_IDS", "")
    hybrid_retrieval_vector_rank_limit_raw: str = os.getenv("HYBRID_RETRIEVAL_VECTOR_RANK_LIMIT", "8")
    hybrid_retrieval_family_score_thresholds_json_raw: str = os.getenv(
        "HYBRID_RETRIEVAL_FAMILY_SCORE_THRESHOLDS_JSON",
        '{"catalog_table": 0.18, "catalog_field": 0.16, "glossary_term": 0.17, "sql_example": 0.15}',
    )
    hybrid_retrieval_family_caps_json_raw: str = os.getenv(
        "HYBRID_RETRIEVAL_FAMILY_CAPS_JSON",
        '{"catalog_table": 1, "catalog_field": 2, "glossary_term": 1, "sql_example": 1}',
    )
    hybrid_retrieval_total_vector_supplement_cap_raw: str = os.getenv(
        "HYBRID_RETRIEVAL_TOTAL_VECTOR_SUPPLEMENT_CAP",
        "3",
    )
    hybrid_retrieval_deterministic_pass_guard_raw: str = os.getenv(
        "HYBRID_RETRIEVAL_DETERMINISTIC_PASS_GUARD",
        "1",
    )
    hybrid_retrieval_hybrid_enabled_projects_raw: str = os.getenv(
        "HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS",
        "",
    )
    hybrid_retrieval_hybrid_enabled_eval_gate_raw: str = os.getenv(
        "HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE",
        "0",
    )
    hybrid_retrieval_hybrid_enabled_kill_switch_raw: str = os.getenv(
        "HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH",
        "0",
    )
    hybrid_retrieval_shadow_sample_rate_raw: str = os.getenv(
        "HYBRID_RETRIEVAL_SHADOW_SAMPLE_RATE",
        "0.0",
    )

    @property
    def project_root(self) -> Path:
        """Return repository root path based on this file location."""
        return Path(__file__).resolve().parents[2]

    def resolve_path(self, path_value: str) -> Path:
        """Resolve a relative path against project root."""
        path = Path(path_value)
        if path.is_absolute():
            return path
        return self.project_root / path

    @property
    def resolved_gemini_api_key(self) -> str | None:
        """Resolve Gemini API key from env-backed settings."""
        return str(self.gemini_api_key).strip() if self.gemini_api_key else None

    @property
    def resolved_model_name(self) -> str:
        """Allow GEMINI_MODEL to override MODEL_NAME for compatibility."""
        return str((self.gemini_model or self.model_name) or "").strip()

    @property
    def resolved_google_application_credentials(self) -> str | None:
        """Resolve GOOGLE_APPLICATION_CREDENTIALS to an absolute path if provided."""
        if not self.google_application_credentials:
            return None
        resolved = self.resolve_path(self.google_application_credentials)
        return str(resolved)

    @property
    def resolved_auth_database_url(self) -> str:
        if self.auth_database_url:
            return self.auth_database_url
        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+pymysql://{user}:{password}@{self.mysql_host}:{self.mysql_port}/"
            f"{self.mysql_database}?charset=utf8mb4"
        )


settings = Settings()


# ---------------------------------------------------------------
# llm.providers / llm.routes loading (Plan #02 Task 1.2)
# ---------------------------------------------------------------

_LLM_CONFIG_CACHE: dict[str, Any] | None = None


def get_llm_config() -> dict[str, Any]:
    global _LLM_CONFIG_CACHE
    if _LLM_CONFIG_CACHE is None:
        path = settings.project_root / "config.yaml"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _LLM_CONFIG_CACHE = data.get("llm", {})
        else:
            _LLM_CONFIG_CACHE = {}
    return _LLM_CONFIG_CACHE


def llm_provider_for(route_key: str) -> str:
    cfg = get_llm_config()
    routes = cfg.get("routes", {})
    return routes.get(route_key, cfg.get("default_provider", "gemini"))


def validate_llm_routes() -> None:
    """Startup-time check: every route's provider must exist; placeholder
    endpoints emit warnings without aborting startup."""
    from app.core.logger import get_logger  # lazy import: avoid logger->config circular
    logger = get_logger(__name__)

    cfg = get_llm_config()
    providers = set(cfg.get("providers", {}).keys())
    known_skill_prefixes = {
        "app_profile", "behavior_profile", "credit_profile",
        "comprehensive", "product_advice", "ops_advice",
        "trace_analyzer", "data_acquisition", "orchestrator",
    }
    for route_key, provider_name in cfg.get("routes", {}).items():
        if "." not in route_key:
            raise ValueError(f"Invalid route_key shape: {route_key}")
        prefix = route_key.split(".", 1)[0]
        if prefix not in known_skill_prefixes:
            logger.warning(f"Unknown skill prefix: {prefix}")
        if provider_name not in providers:
            raise ValueError(
                f"route {route_key} -> {provider_name} not in providers"
            )

    # R8 P0-A bug 修复：区分"未声明 endpoint 字段"和"声明了但是 placeholder"
    # 未声明 → 该 provider 不依赖 endpoint（如 gemini 走 SDK / mock 不走网络）→ 跳过
    # 声明了但是 placeholder → 真的还没准备好 → warning
    PLACEHOLDER_ENDPOINTS = {"", "[Spike Pending]", "TBD", "TODO"}
    for name, p_cfg in cfg.get("providers", {}).items():
        ep = p_cfg.get("endpoint")
        if ep is None:
            continue  # 该 provider 不依赖 endpoint，跳过
        if ep.strip() in PLACEHOLDER_ENDPOINTS:
            logger.warning(
                "provider %s has placeholder endpoint=%r; will raise ProviderUnavailable on first call "
                "(Plan #03 Maestro Spike pending)", name, ep
            )
