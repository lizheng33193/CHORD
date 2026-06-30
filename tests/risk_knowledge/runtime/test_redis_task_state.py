from __future__ import annotations

from app.knowledge_base.schemas import IndexingJobTrigger


def test_redis_task_state_tracks_status_and_latest_pointer(fake_redis_client) -> None:
    from app.risk_knowledge.runtime.redis_state import RedisIndexingTaskStateStore
    from app.risk_knowledge.runtime.schemas import RedisIndexingJobState

    store = RedisIndexingTaskStateStore(
        client=fake_redis_client,
        key_prefix="chord:test",
        state_ttl_seconds=300,
    )
    state = RedisIndexingJobState(
        job_id="idxjob_root",
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        trigger=IndexingJobTrigger.INITIAL_INDEX,
        runtime_status="queued",
        current_step="queued",
        attempt=1,
        max_attempts=3,
        progress_completed_steps=0,
        progress_total_steps=7,
        progress_message="queued",
        lock_token="token-1",
        error_code=None,
        error_message=None,
        active_manifest_index_id=None,
        latest_manifest_index_id=None,
        started_at=None,
        updated_at=None,
        completed_at=None,
        last_heartbeat_at=None,
    )

    store.put(state)
    stored = store.get("idxjob_root")

    assert stored is not None
    assert stored.runtime_status == "queued"
    assert store.get_latest_job_id("risk_guide_202607") == "idxjob_root"


def test_redis_task_state_updates_heartbeat(fake_redis_client) -> None:
    from app.risk_knowledge.runtime.redis_state import RedisIndexingTaskStateStore
    from app.risk_knowledge.runtime.schemas import RedisIndexingJobState

    store = RedisIndexingTaskStateStore(
        client=fake_redis_client,
        key_prefix="chord:test",
        state_ttl_seconds=300,
    )
    state = RedisIndexingJobState(
        job_id="idxjob_root",
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        trigger=IndexingJobTrigger.INITIAL_INDEX,
        runtime_status="running",
        current_step="embedding",
        attempt=1,
        max_attempts=3,
        progress_completed_steps=3,
        progress_total_steps=7,
        progress_message="embedding",
        lock_token="token-1",
        error_code=None,
        error_message=None,
        active_manifest_index_id=None,
        latest_manifest_index_id=None,
        started_at=None,
        updated_at=None,
        completed_at=None,
        last_heartbeat_at=None,
    )

    store.put(state)
    updated = store.touch_heartbeat("idxjob_root")

    assert updated.last_heartbeat_at is not None
