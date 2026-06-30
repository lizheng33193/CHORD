from __future__ import annotations

import pytest


def test_redis_lock_acquire_and_release(fake_redis_client) -> None:
    from app.risk_knowledge.runtime.redis_lock import RedisVersionLock

    lock = RedisVersionLock(
        client=fake_redis_client,
        key_prefix="chord:test",
        ttl_seconds=30,
    )

    token = lock.acquire("risk_guide_202607")
    assert token
    lock.release("risk_guide_202607", token)


def test_redis_lock_rejects_duplicate_acquire(fake_redis_client) -> None:
    from app.risk_knowledge.runtime.errors import IndexingLockConflictError
    from app.risk_knowledge.runtime.redis_lock import RedisVersionLock

    lock = RedisVersionLock(
        client=fake_redis_client,
        key_prefix="chord:test",
        ttl_seconds=30,
    )

    lock.acquire("risk_guide_202607")
    with pytest.raises(IndexingLockConflictError):
        lock.acquire("risk_guide_202607")


def test_redis_lock_lost_raises_explicit_error(fake_redis_client) -> None:
    from app.risk_knowledge.runtime.errors import IndexingLockLostError
    from app.risk_knowledge.runtime.redis_lock import RedisVersionLock

    lock = RedisVersionLock(
        client=fake_redis_client,
        key_prefix="chord:test",
        ttl_seconds=30,
    )

    token = lock.acquire("risk_guide_202607")
    fake_redis_client.delete("chord:test:indexing:lock:risk_guide_202607")

    with pytest.raises(IndexingLockLostError):
        lock.renew("risk_guide_202607", token)
