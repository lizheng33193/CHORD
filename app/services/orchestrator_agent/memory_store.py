"""SQLite-backed long-term memory store for the Orchestrator Agent."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


DEFAULT_USER_ID = "local-default-user"
DEFAULT_PROJECT_ID = "agent-user-profile-fork"
DEFAULT_COUNTRY = "mx"
DEFAULT_TOP_K = 8

VALID_SCOPES = {"session", "user", "project", "global"}
VALID_CATEGORIES = {"preference", "feedback", "project", "reference", "task", "insight"}
VALID_MEMORY_TYPES = {"episodic", "semantic", "procedural"}
VALID_STATUSES = {"active", "superseded", "archived", "deleted"}
CJK_MEMORY_KEYWORDS = (
    "偏好",
    "输出",
    "中文",
    "简洁",
    "纠正",
    "项目",
    "事实",
    "参考",
    "入口",
    "画像",
    "查询",
    "记住",
)


def _project_root() -> Path:
    return settings.project_root


def memory_enabled() -> bool:
    return os.getenv("MEMORY_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def long_term_memory_enabled() -> bool:
    return os.getenv("LONG_TERM_MEMORY_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def memory_write_enabled() -> bool:
    return os.getenv("MEMORY_WRITE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def memory_backend() -> str:
    return os.getenv("MEMORY_BACKEND", "sqlite").strip().lower() or "sqlite"


def memory_retrieval_top_k() -> int:
    raw = os.getenv("MEMORY_RETRIEVAL_TOP_K", str(DEFAULT_TOP_K))
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return DEFAULT_TOP_K


def default_db_path() -> Path:
    env_path = os.getenv("MEMORY_DB_PATH")
    if env_path:
        p = Path(env_path)
        return p if p.is_absolute() else _project_root() / p
    return _project_root() / "outputs" / "memory" / "memory.sqlite3"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_memory_id() -> str:
    return hashlib.sha256(f"{now_iso()}:{os.urandom(8).hex()}".encode("utf-8")).hexdigest()[:32]


def make_dedupe_key(*parts: str) -> str:
    normalized = "|".join(_normalize_for_hash(p) for p in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def build_scope_dedupe_key(
    *,
    scope: str,
    user_id: str,
    project_id: str,
    country: str,
    session_id: str | None,
    category: str,
    content: str,
) -> str:
    normalized_scope = scope if scope in VALID_SCOPES else "user"
    parts = [normalized_scope]
    if normalized_scope in {"session", "user"}:
        parts.append(user_id)
    parts.append(project_id)
    if normalized_scope != "global":
        parts.append(country)
    if normalized_scope == "session":
        parts.append(session_id or "")
    parts.extend([category, content])
    return make_dedupe_key(*parts)


@dataclass
class MemoryRecord:
    memory_id: str
    scope: str
    user_id: str
    project_id: str
    session_id: str | None
    country: str
    category: str
    memory_type: str
    content: str
    importance: float = 0.6
    confidence: float = 0.8
    status: str = "active"
    tags: list[str] = field(default_factory=list)
    source: str = "memory_policy"
    dedupe_key: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "scope": self.scope,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "country": self.country,
            "category": self.category,
            "memory_type": self.memory_type,
            "content": self.content,
            "importance": float(self.importance),
            "confidence": float(self.confidence),
            "status": self.status,
            "tags": json.dumps(self.tags, ensure_ascii=False),
            "source": self.source,
            "dedupe_key": self.dedupe_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "metadata_json": json.dumps(self.metadata, ensure_ascii=False, sort_keys=True),
        }


class MemoryStoreConflict(ValueError):
    """Raised when an update would duplicate another memory under one identity."""


class MemoryStoreNotFound(KeyError):
    """Raised when a memory id is not visible under the requested identity."""


class SQLiteMemoryStore:
    """Small local memory store with FTS5 retrieval and scope-aware visibility."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_db_path()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    memory_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    session_id TEXT,
                    country TEXT NOT NULL,
                    category TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    source TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(user_id, project_id, country, dedupe_key)
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(memory_id UNINDEXED, content, tags)
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_identity "
                "ON memory_records(user_id, project_id, country, status, category)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_vector_sync (
                    memory_id TEXT PRIMARY KEY,
                    vector_namespace TEXT NOT NULL,
                    embedding_provider TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding_text_hash TEXT,
                    vector_status TEXT NOT NULL,
                    indexed_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def add(self, record: MemoryRecord) -> MemoryRecord:
        self.initialize()
        record = self._validated(record)
        row = record.to_row()
        with self._connect() as conn:
            where_sql, where_params = self._dedupe_lookup_clause(record, alias="")
            existing = conn.execute(
                f"SELECT memory_id, created_at FROM memory_records WHERE {where_sql}",
                where_params,
            ).fetchone()
            if existing:
                record.memory_id = str(existing["memory_id"])
                record.created_at = str(existing["created_at"])
                record.updated_at = now_iso()
                existing_row = conn.execute(
                    "SELECT * FROM memory_records WHERE memory_id = ?",
                    (record.memory_id,),
                ).fetchone()
                if existing_row is not None:
                    record.user_id = str(existing_row["user_id"])
                    record.session_id = existing_row["session_id"]
                    if record.scope in {"project", "global"}:
                        record.country = str(existing_row["country"])
                row = record.to_row()
                conn.execute(
                    """
                    UPDATE memory_records SET
                        scope=:scope, session_id=:session_id, category=:category,
                        memory_type=:memory_type, content=:content, importance=:importance,
                        confidence=:confidence, status=:status, tags=:tags, source=:source,
                        updated_at=:updated_at, expires_at=:expires_at, metadata_json=:metadata_json
                    WHERE memory_id=:memory_id
                    """,
                    row,
                )
            else:
                conn.execute(
                    """
                    INSERT INTO memory_records (
                        memory_id, scope, user_id, project_id, session_id, country,
                        category, memory_type, content, importance, confidence, status,
                        tags, source, dedupe_key, created_at, updated_at, expires_at,
                        metadata_json
                    ) VALUES (
                        :memory_id, :scope, :user_id, :project_id, :session_id, :country,
                        :category, :memory_type, :content, :importance, :confidence, :status,
                        :tags, :source, :dedupe_key, :created_at, :updated_at, :expires_at,
                        :metadata_json
                    )
                    """,
                    row,
                )
            self._refresh_fts(conn, row)
        self._best_effort_update_vector_sync_for_memory(
            self.get_record_by_id(record.memory_id),
            action="write",
        )
        return record

    def search(
        self,
        query: str,
        *,
        user_id: str = DEFAULT_USER_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        country: str = DEFAULT_COUNTRY,
        top_k: int = DEFAULT_TOP_K,
        category: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        query = str(query or "").strip()
        top_k = max(1, min(50, int(top_k or DEFAULT_TOP_K)))
        visibility_sql, visibility_params = self._visibility_clause(
            user_id=user_id,
            project_id=project_id,
            country=country,
            session_id=session_id,
            alias="r",
        )
        filters = [*visibility_params, now_iso()]
        where = [
            visibility_sql,
            "r.status = 'active'",
            "(r.expires_at IS NULL OR r.expires_at > ?)",
        ]
        if category:
            where.append("r.category = ?")
            filters.append(_normalize_category(category))

        rows = self._search_fts(query, where, filters, top_k * 3)
        if not rows:
            rows = self._search_like(query, where, filters, top_k * 3)
        if not rows and not query:
            rows = self._list_recent(where, filters, top_k * 3)

        ranked = [self._score_row(row, query) for row in rows]
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]

    def get(
        self,
        memory_id: str,
        *,
        user_id: str = DEFAULT_USER_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        country: str = DEFAULT_COUNTRY,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        self.initialize()
        visibility_sql, visibility_params = self._visibility_clause(
            user_id=user_id,
            project_id=project_id,
            country=country,
            session_id=session_id,
            alias="memory_records",
        )
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT *, NULL AS fts_rank FROM memory_records WHERE memory_id = ? AND {visibility_sql}",
                (memory_id, *visibility_params),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def update(self, record: MemoryRecord) -> MemoryRecord:
        self.initialize()
        record = self._validated(record)
        with self._connect() as conn:
            visibility_sql, visibility_params = self._visibility_clause(
                user_id=record.user_id,
                project_id=record.project_id,
                country=record.country,
                session_id=record.session_id,
                alias="memory_records",
            )
            existing = conn.execute(
                f"SELECT * FROM memory_records WHERE memory_id = ? AND {visibility_sql}",
                (record.memory_id, *visibility_params),
            ).fetchone()
            if existing is None:
                raise MemoryStoreNotFound(record.memory_id)

            record.user_id = str(existing["user_id"])
            record.session_id = existing["session_id"]
            if record.scope in {"project", "global"}:
                record.country = str(existing["country"])
            conflict_sql, conflict_params = self._dedupe_lookup_clause(record, alias="")
            conflict = conn.execute(
                f"SELECT memory_id FROM memory_records WHERE {conflict_sql} AND memory_id != ?",
                (*conflict_params, record.memory_id),
            ).fetchone()
            if conflict is not None:
                raise MemoryStoreConflict(str(conflict["memory_id"]))

            record.created_at = str(existing["created_at"])
            record.updated_at = now_iso()
            row = record.to_row()
            conn.execute(
                """
                UPDATE memory_records SET
                    scope=:scope, session_id=:session_id, category=:category,
                    memory_type=:memory_type, content=:content, importance=:importance,
                    confidence=:confidence, status=:status, tags=:tags, source=:source,
                    dedupe_key=:dedupe_key, updated_at=:updated_at, expires_at=:expires_at,
                    metadata_json=:metadata_json
                WHERE memory_id=:memory_id
                """,
                row,
            )
            self._refresh_fts(conn, row)
        self._best_effort_update_vector_sync_for_memory(
            self.get_record_by_id(record.memory_id),
            action="update",
        )
        return record

    def set_status(
        self,
        memory_id: str,
        *,
        status: str,
        user_id: str = DEFAULT_USER_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        country: str = DEFAULT_COUNTRY,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in VALID_STATUSES:
            raise ValueError(f"unsupported status: {status}")
        normalized_country = (country or DEFAULT_COUNTRY).lower()
        visibility_sql, visibility_params = self._visibility_clause(
            user_id=user_id,
            project_id=project_id,
            country=normalized_country,
            session_id=session_id,
            alias="memory_records",
        )
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM memory_records WHERE memory_id = ? AND {visibility_sql}",
                (memory_id, *visibility_params),
            ).fetchone()
            if row is None:
                raise MemoryStoreNotFound(memory_id)
            conn.execute(
                "UPDATE memory_records SET status = ?, updated_at = ? WHERE memory_id = ?",
                (normalized_status, now_iso(), memory_id),
            )
        self._best_effort_update_vector_sync_for_memory(
            self.get_record_by_id(memory_id),
            action="restore" if normalized_status == "active" else normalized_status,
        )
        updated = self.get(
            memory_id,
            user_id=user_id,
            project_id=project_id,
            country=normalized_country,
            session_id=session_id,
        )
        if updated is None:
            raise MemoryStoreNotFound(memory_id)
        return updated

    def list_records(
        self,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        country: str | None = None,
        status: str | None = "active",
        category: str | None = None,
        limit: int = 100,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        where: list[str] = []
        params: list[Any] = []
        if status:
            normalized_status = str(status).strip().lower()
            if normalized_status not in VALID_STATUSES:
                normalized_status = "active"
            where.append("status = ?")
            params.append(normalized_status)
        if user_id:
            if project_id and country:
                visibility_sql, visibility_params = self._visibility_clause(
                    user_id=user_id,
                    project_id=project_id,
                    country=country,
                    session_id=session_id,
                    alias="memory_records",
                )
                where.append(visibility_sql)
                params.extend(visibility_params)
            else:
                where.append("user_id = ?")
                params.append(user_id)
        elif project_id:
            where.append("project_id = ?")
            params.append(project_id)
            if country:
                where.append("(scope = 'global' OR country = ?)")
                params.append(country.lower())
        elif country:
            where.append("country = ?")
            params.append(country.lower())
        if category:
            where.append("category = ?")
            params.append(_normalize_category(category))
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT *, NULL AS fts_rank FROM memory_records {where_sql} "
                "ORDER BY updated_at DESC LIMIT ?",
                (*params, max(1, min(1000, limit))),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def status(self) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM memory_records").fetchone()["n"]
            by_category = {
                row["category"]: row["n"]
                for row in conn.execute(
                    "SELECT category, COUNT(*) AS n FROM memory_records GROUP BY category"
                ).fetchall()
            }
            by_status = {
                row["status"]: row["n"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM memory_records GROUP BY status"
                ).fetchall()
            }
        return {
            "backend": "sqlite",
            "db_path": str(self.db_path),
            "total": int(total),
            "by_category": by_category,
            "by_status": by_status,
        }

    def get_record_by_id(self, memory_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT *, NULL AS fts_rank FROM memory_records WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_vector_sync_state(
        self,
        memory_id: str,
        *,
        vector_namespace: str | None = None,
    ):
        from app.services.orchestrator_agent.memory_vector.schemas import MemoryVectorSyncState

        self.initialize()
        namespace = vector_namespace or settings.memory_vector_namespace
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM memory_vector_sync
                WHERE memory_id = ? AND vector_namespace = ?
                """,
                (memory_id, namespace),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        return MemoryVectorSyncState(
            memory_id=str(data["memory_id"]),
            vector_namespace=str(data["vector_namespace"]),
            embedding_provider=str(data["embedding_provider"]),
            embedding_model=str(data["embedding_model"]),
            embedding_dim=int(data["embedding_dim"]),
            content_hash=str(data["content_hash"]),
            embedding_text_hash=str(data["embedding_text_hash"]) if data["embedding_text_hash"] else None,
            vector_status=str(data["vector_status"]),
            indexed_at=data["indexed_at"],
            last_error=data["last_error"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def list_vector_sync_states(
        self,
        *,
        vector_namespace: str | None = None,
        vector_status: str | None = None,
        limit: int = 1000,
    ) -> list:
        from app.services.orchestrator_agent.memory_vector.schemas import MemoryVectorSyncState

        self.initialize()
        namespace = vector_namespace or settings.memory_vector_namespace
        where = ["vector_namespace = ?"]
        params: list[Any] = [namespace]
        if vector_status:
            where.append("vector_status = ?")
            params.append(vector_status)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_vector_sync WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT ?",
                (*params, max(1, min(5000, int(limit or 1000)))),
            ).fetchall()
        return [
            MemoryVectorSyncState(
                memory_id=str(dict(row)["memory_id"]),
                vector_namespace=str(dict(row)["vector_namespace"]),
                embedding_provider=str(dict(row)["embedding_provider"]),
                embedding_model=str(dict(row)["embedding_model"]),
                embedding_dim=int(dict(row)["embedding_dim"]),
                content_hash=str(dict(row)["content_hash"]),
                embedding_text_hash=str(dict(row)["embedding_text_hash"]) if dict(row)["embedding_text_hash"] else None,
                vector_status=str(dict(row)["vector_status"]),
                indexed_at=dict(row)["indexed_at"],
                last_error=dict(row)["last_error"],
                created_at=dict(row)["created_at"],
                updated_at=dict(row)["updated_at"],
            )
            for row in rows
        ]

    def upsert_vector_sync_state(self, state) -> None:
        self.initialize()
        created_at = state.created_at or now_iso()
        updated_at = state.updated_at or now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_vector_sync (
                    memory_id, vector_namespace, embedding_provider, embedding_model,
                    embedding_dim, content_hash, embedding_text_hash, vector_status,
                    indexed_at, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    vector_namespace=excluded.vector_namespace,
                    embedding_provider=excluded.embedding_provider,
                    embedding_model=excluded.embedding_model,
                    embedding_dim=excluded.embedding_dim,
                    content_hash=excluded.content_hash,
                    embedding_text_hash=excluded.embedding_text_hash,
                    vector_status=excluded.vector_status,
                    indexed_at=excluded.indexed_at,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (
                    state.memory_id,
                    state.vector_namespace,
                    state.embedding_provider,
                    state.embedding_model,
                    int(state.embedding_dim),
                    state.content_hash,
                    state.embedding_text_hash,
                    state.vector_status,
                    state.indexed_at,
                    state.last_error,
                    created_at,
                    updated_at,
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _refresh_fts(self, conn: sqlite3.Connection, row: dict[str, Any]) -> None:
        conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (row["memory_id"],))
        conn.execute(
            "INSERT INTO memory_fts(memory_id, content, tags) VALUES (?, ?, ?)",
            (row["memory_id"], row["content"], row["tags"]),
        )

    def _search_fts(
        self,
        query: str,
        where: list[str],
        params: list[Any],
        limit: int,
    ) -> list[sqlite3.Row]:
        fts_query = _to_fts_query(query)
        if not fts_query:
            return []
        sql = (
            "SELECT r.*, bm25(memory_fts) AS fts_rank "
            "FROM memory_fts JOIN memory_records r ON r.memory_id = memory_fts.memory_id "
            f"WHERE memory_fts MATCH ? AND {' AND '.join(where)} "
            "ORDER BY fts_rank LIMIT ?"
        )
        try:
            with self._connect() as conn:
                return conn.execute(sql, (fts_query, *params, limit)).fetchall()
        except sqlite3.OperationalError:
            return []

    def _search_like(
        self,
        query: str,
        where: list[str],
        params: list[Any],
        limit: int,
    ) -> list[sqlite3.Row]:
        tokens = _query_tokens(query)
        like_where = list(where)
        like_params = list(params)
        if tokens:
            like_where.append("(" + " OR ".join(["content LIKE ?" for _ in tokens]) + ")")
            like_params.extend([f"%{token}%" for token in tokens])
        with self._connect() as conn:
            return conn.execute(
                f"SELECT *, NULL AS fts_rank FROM memory_records r "
                f"WHERE {' AND '.join(like_where)} ORDER BY updated_at DESC LIMIT ?",
                (*like_params, limit),
            ).fetchall()

    def _list_recent(self, where: list[str], params: list[Any], limit: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                f"SELECT *, NULL AS fts_rank FROM memory_records r "
                f"WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()

    def _score_row(self, row: sqlite3.Row, query: str) -> dict[str, Any]:
        item = self._row_to_dict(row)
        relevance = _keyword_relevance(query, item["content"])
        if row["fts_rank"] is not None:
            relevance = max(relevance, min(1.0, 1.0 / (1.0 + abs(float(row["fts_rank"])))))
        importance = float(item.get("importance", 0.0))
        confidence = float(item.get("confidence", 0.0))
        recency = _recency_score(str(item.get("updated_at") or item.get("created_at") or ""))
        score = relevance * 0.55 + importance * 0.3 + confidence * 0.1 + recency * 0.05
        item["score"] = round(score, 6)
        item["score_parts"] = {
            "relevance": round(relevance, 6),
            "importance": round(importance, 6),
            "confidence": round(confidence, 6),
            "recency": round(recency, 6),
        }
        return item

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["tags"] = _loads(data.get("tags"), [])
        data["metadata"] = _loads(data.pop("metadata_json", "{}"), {})
        data.pop("fts_rank", None)
        return data

    def _visibility_clause(
        self,
        *,
        user_id: str,
        project_id: str,
        country: str,
        session_id: str | None,
        alias: str,
    ) -> tuple[str, list[Any]]:
        q = f"{alias}." if alias else ""
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append(
                f"({q}scope = 'session' AND {q}user_id = ? AND {q}project_id = ? AND {q}country = ? AND {q}session_id = ?)"
            )
            params.extend([user_id, project_id, country.lower(), session_id])
        clauses.append(f"({q}scope = 'user' AND {q}user_id = ? AND {q}project_id = ? AND {q}country = ?)")
        params.extend([user_id, project_id, country.lower()])
        clauses.append(f"({q}scope = 'project' AND {q}project_id = ? AND {q}country = ?)")
        params.extend([project_id, country.lower()])
        clauses.append(f"({q}scope = 'global' AND {q}project_id = ?)")
        params.append(project_id)
        return "(" + " OR ".join(clauses) + ")", params

    def _dedupe_lookup_clause(self, record: MemoryRecord, *, alias: str) -> tuple[str, list[Any]]:
        q = f"{alias}." if alias else ""
        if record.scope == "session":
            return (
                f"{q}scope = ? AND {q}user_id = ? AND {q}project_id = ? AND {q}country = ? AND {q}session_id = ? AND {q}dedupe_key = ?",
                [record.scope, record.user_id, record.project_id, record.country, record.session_id, record.dedupe_key],
            )
        if record.scope == "project":
            return (
                f"{q}scope = ? AND {q}project_id = ? AND {q}country = ? AND {q}dedupe_key = ?",
                [record.scope, record.project_id, record.country, record.dedupe_key],
            )
        if record.scope == "global":
            return (
                f"{q}scope = ? AND {q}project_id = ? AND {q}dedupe_key = ?",
                [record.scope, record.project_id, record.dedupe_key],
            )
        return (
            f"{q}scope = ? AND {q}user_id = ? AND {q}project_id = ? AND {q}country = ? AND {q}dedupe_key = ?",
            [record.scope, record.user_id, record.project_id, record.country, record.dedupe_key],
        )

    def _validated(self, record: MemoryRecord) -> MemoryRecord:
        record.scope = record.scope if record.scope in VALID_SCOPES else "user"
        record.category = _normalize_category(record.category)
        record.memory_type = (
            record.memory_type if record.memory_type in VALID_MEMORY_TYPES else "semantic"
        )
        record.status = record.status if record.status in VALID_STATUSES else "active"
        record.user_id = record.user_id or DEFAULT_USER_ID
        record.project_id = record.project_id or DEFAULT_PROJECT_ID
        record.country = (record.country or DEFAULT_COUNTRY).lower()
        if not record.dedupe_key:
            record.dedupe_key = build_scope_dedupe_key(
                scope=record.scope,
                user_id=record.user_id,
                project_id=record.project_id,
                country=record.country,
                session_id=record.session_id,
                category=record.category,
                content=record.content,
            )
        return record

    def _best_effort_update_vector_sync_for_memory(
        self,
        memory: dict[str, Any] | None,
        *,
        action: str,
    ) -> None:
        if memory is None:
            return
        try:
            from app.services.orchestrator_agent.memory_vector.embedding_text import (
                build_memory_embedding_text,
            )
            from app.services.orchestrator_agent.memory_vector.schemas import (
                MemoryVectorSyncState,
            )
            from app.services.orchestrator_agent.memory_vector.sync import (
                build_default_memory_vector_sync_service,
            )

            namespace = settings.memory_vector_namespace
            existing = self.get_vector_sync_state(memory["memory_id"], vector_namespace=namespace)
            status = str(memory.get("status") or "").strip().lower()
            content_hash = _sha256_text(str(memory.get("content") or ""))
            text_result = build_memory_embedding_text(
                memory,
                max_chars=settings.memory_vector_text_max_chars,
            )

            if status != "active":
                next_status = "deleted"
                embedding_text_hash = existing.embedding_text_hash if existing else None
            elif text_result.skipped:
                next_status = "skipped"
                embedding_text_hash = None
            else:
                embedding_text_hash = text_result.embedding_text_hash
                next_status = _next_vector_status(
                    existing=existing.vector_status if existing else None,
                    previous_hash=existing.embedding_text_hash if existing else None,
                    current_hash=embedding_text_hash,
                    action=action,
                )

            state = MemoryVectorSyncState(
                memory_id=str(memory["memory_id"]),
                vector_namespace=namespace,
                embedding_provider=settings.memory_vector_embedding_provider,
                embedding_model=settings.memory_vector_embedding_model,
                embedding_dim=int(settings.memory_vector_embedding_dim),
                content_hash=content_hash,
                embedding_text_hash=embedding_text_hash,
                vector_status=next_status,
                indexed_at=existing.indexed_at if existing and next_status == "indexed" else None,
                last_error=None,
                created_at=existing.created_at if existing else now_iso(),
                updated_at=now_iso(),
            )
            self.upsert_vector_sync_state(state)

            if not settings.memory_vector_enabled:
                return
            service = build_default_memory_vector_sync_service(relational_store=self)
            if status != "active":
                service.mark_deleted(str(memory["memory_id"]))
            else:
                service.sync_memory(str(memory["memory_id"]))
        except Exception:
            return


def _next_vector_status(
    *,
    existing: str | None,
    previous_hash: str | None,
    current_hash: str | None,
    action: str,
) -> str:
    if action == "restore":
        if previous_hash and current_hash and previous_hash != current_hash:
            return "stale"
        return "pending"
    if existing == "indexed" and previous_hash and current_hash and previous_hash == current_hash:
        return "indexed"
    if previous_hash and current_hash and previous_hash != current_hash:
        return "stale"
    return "pending"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _normalize_category(category: str) -> str:
    category = str(category or "").strip().lower()
    if category == "user":
        return "preference"
    return category if category in VALID_CATEGORIES else "reference"


def _loads(raw: Any, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return default


def _query_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", str(query or "").lower()):
        if not token:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            for keyword in CJK_MEMORY_KEYWORDS:
                if keyword in token:
                    _append_token(tokens, seen, keyword)
            _append_token(tokens, seen, token)
            for idx in range(max(0, len(token) - 1)):
                _append_token(tokens, seen, token[idx : idx + 2])
        else:
            _append_token(tokens, seen, token)
    return tokens


def _to_fts_query(query: str) -> str:
    tokens = _query_tokens(query)
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens[:24])


def _append_token(tokens: list[str], seen: set[str], token: str) -> None:
    if token and token not in seen:
        tokens.append(token)
        seen.add(token)


def _keyword_relevance(query: str, content: str) -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return 0.2
    text = str(content or "").lower()
    hits = sum(1 for token in tokens if token in text)
    return min(1.0, hits / max(1, len(tokens)))


def _recency_score(ts: str) -> float:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
        return 1.0 / (1.0 + age_days / 30.0)
    except ValueError:
        return 0.0
