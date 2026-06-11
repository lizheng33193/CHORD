"""JSON-based session store with atexit flush and resume support."""

from __future__ import annotations

import atexit
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.orchestrator_agent.schemas import OrchestratorSession


_LOCK = threading.Lock()
_DIRTY: set[str] = set()
_CACHE: dict[str, OrchestratorSession] = {}


def _sessions_dir() -> Path:
    p = settings.project_root / "outputs" / "orchestrator_sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_session(sess: OrchestratorSession) -> None:
    path = _sessions_dir() / f"{sess.session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(sess.model_dump_json(indent=2), encoding="utf-8")
    tmp_path.replace(path)


def create_session(
    *,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
) -> OrchestratorSession:
    sid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    sess = OrchestratorSession(
        session_id=sid,
        created_at=now,
        updated_at=now,
        user_id=user_id or "local-default-user",
        project_id=project_id or "agent-user-profile-fork",
        country=country,
    )
    with _LOCK:
        _CACHE[sid] = sess
        _DIRTY.add(sid)
        _write_session(sess)
        _DIRTY.discard(sid)
    return sess


def get_session(session_id: str) -> OrchestratorSession | None:
    with _LOCK:
        if session_id in _CACHE:
            return _CACHE[session_id]
    path = _sessions_dir() / f"{session_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    sess = OrchestratorSession.model_validate(data)
    with _LOCK:
        _CACHE[session_id] = sess
    return sess


def list_sessions(
    *,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
    limit: int = 20,
) -> list[dict]:
    sessions: dict[str, OrchestratorSession] = {}
    with _LOCK:
        sessions.update(_CACHE)
    for path in _sessions_dir().glob("*.json"):
        sid = path.stem
        if sid in sessions:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sessions[sid] = OrchestratorSession.model_validate(data)
        except Exception:
            continue

    normalized_country = country.lower() if country else None
    rows = []
    for sess in sessions.values():
        if user_id and sess.user_id != user_id:
            continue
        if project_id and sess.project_id != project_id:
            continue
        if normalized_country and (sess.country or "").lower() != normalized_country:
            continue
        rows.append(_session_summary(sess))
    rows.sort(key=lambda item: item["updated_at"], reverse=True)
    return rows[: max(1, min(100, int(limit or 20)))]


def save_session(sess: OrchestratorSession) -> None:
    sess.updated_at = datetime.now(timezone.utc)
    with _LOCK:
        _CACHE[sess.session_id] = sess
        _DIRTY.add(sess.session_id)
        _write_session(sess)
        _DIRTY.discard(sess.session_id)


def flush() -> None:
    with _LOCK:
        for sid in list(_DIRTY):
            sess = _CACHE.get(sid)
            if not sess:
                continue
            _write_session(sess)
        _DIRTY.clear()


atexit.register(flush)


def _session_summary(sess: OrchestratorSession) -> dict:
    last_user = ""
    for message in reversed(sess.messages):
        if message.role == "user":
            last_user = message.content or ""
            break
    final_message = sess.final_message or ""
    if not final_message:
        for message in reversed(sess.messages):
            if message.role == "assistant":
                final_message = message.content or ""
                break
    return {
        "session_id": sess.session_id,
        "created_at": sess.created_at.isoformat(),
        "updated_at": sess.updated_at.isoformat(),
        "status": sess.status,
        "user_id": sess.user_id,
        "project_id": sess.project_id,
        "country": sess.country,
        "message_count": len(sess.messages),
        "last_user_message_preview": _preview(last_user),
        "final_message_preview": _preview(final_message),
    }


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit]
