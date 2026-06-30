"""Redis-backed version-level lock for M2D-9 indexing jobs."""

from __future__ import annotations

import uuid

from app.risk_knowledge.runtime.errors import IndexingLockConflictError, IndexingLockLostError


class RedisVersionLock:
    def __init__(self, *, client, key_prefix: str, ttl_seconds: int) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    def acquire(self, version_id: str) -> str:
        token = uuid.uuid4().hex
        acquired = self._client.set(self._key(version_id), token, nx=True, ex=self._ttl_seconds)
        if not acquired:
            raise IndexingLockConflictError(f"indexing lock already held for version_id={version_id}")
        return token

    def renew(self, version_id: str, token: str) -> None:
        key = self._key(version_id)
        with self._client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    current = pipe.get(key)
                    if current != token:
                        pipe.reset()
                        raise IndexingLockLostError(f"indexing lock lost for version_id={version_id}")
                    pipe.multi()
                    pipe.expire(key, self._ttl_seconds)
                    pipe.execute()
                    return
                except IndexingLockLostError:
                    raise
                except Exception:
                    pipe.reset()
                    continue

    def release(self, version_id: str, token: str) -> None:
        key = self._key(version_id)
        with self._client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    current = pipe.get(key)
                    if current != token:
                        pipe.reset()
                        raise IndexingLockLostError(f"indexing lock lost for version_id={version_id}")
                    pipe.multi()
                    pipe.delete(key)
                    pipe.execute()
                    return
                except IndexingLockLostError:
                    raise
                except Exception:
                    pipe.reset()
                    continue

    def _key(self, version_id: str) -> str:
        return f"{self._key_prefix}:indexing:lock:{version_id}"
