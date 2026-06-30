"""Redis-backed ephemeral task state for M2D-9 indexing jobs."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.risk_knowledge.runtime.errors import IndexingRedisStateError
from app.risk_knowledge.runtime.schemas import RedisIndexingJobState


class RedisIndexingTaskStateStore:
    def __init__(self, *, client, key_prefix: str, state_ttl_seconds: int) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._state_ttl_seconds = state_ttl_seconds

    def put(self, state: RedisIndexingJobState) -> RedisIndexingJobState:
        now = datetime.now(UTC).replace(tzinfo=None)
        payload = state.model_copy(update={"updated_at": now})
        try:
            self._client.set(self._job_key(state.job_id), payload.model_dump_json(), ex=self._state_ttl_seconds)
            self._client.set(self._latest_job_key(state.version_id), state.job_id, ex=self._state_ttl_seconds)
        except Exception as exc:  # pylint: disable=broad-except
            raise IndexingRedisStateError(f"failed to write Redis task state for job_id={state.job_id}") from exc
        return payload

    def get(self, job_id: str) -> RedisIndexingJobState | None:
        try:
            payload = self._client.get(self._job_key(job_id))
        except Exception as exc:  # pylint: disable=broad-except
            raise IndexingRedisStateError(f"failed to read Redis task state for job_id={job_id}") from exc
        if not payload:
            return None
        return RedisIndexingJobState.model_validate(json.loads(payload))

    def touch_heartbeat(self, job_id: str) -> RedisIndexingJobState:
        state = self.get(job_id)
        if state is None:
            raise IndexingRedisStateError(f"missing Redis task state for job_id={job_id}")
        now = datetime.now(UTC).replace(tzinfo=None)
        return self.put(
            state.model_copy(
                update={
                    "last_heartbeat_at": now,
                    "updated_at": now,
                }
            )
        )

    def get_latest_job_id(self, version_id: str) -> str | None:
        try:
            return self._client.get(self._latest_job_key(version_id))
        except Exception as exc:  # pylint: disable=broad-except
            raise IndexingRedisStateError(f"failed to read latest job pointer for version_id={version_id}") from exc

    def _job_key(self, job_id: str) -> str:
        return f"{self._key_prefix}:indexing:job:{job_id}"

    def _latest_job_key(self, version_id: str) -> str:
        return f"{self._key_prefix}:indexing:version:{version_id}:latest_job"
