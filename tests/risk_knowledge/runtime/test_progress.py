from __future__ import annotations


def test_progress_updater_invokes_heartbeat_callback(
    fake_redis_client,
    sample_document,
    sample_version,
    sample_job,
) -> None:
    from app.risk_knowledge.runtime.progress import IndexingProgressUpdater, ProgressUpdate
    from app.risk_knowledge.runtime.redis_state import RedisIndexingTaskStateStore

    heartbeat_calls: list[str] = []

    updater = IndexingProgressUpdater(
        job=sample_job,
        document=sample_document,
        version=sample_version,
        redis_state_store=RedisIndexingTaskStateStore(
            client=fake_redis_client,
            key_prefix="test:risk",
            state_ttl_seconds=60,
        ),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("durable session should not be used")),
        heartbeat_callback=lambda: heartbeat_calls.append("heartbeat"),
    )
    updater._last_durable_flush_at = updater._now()  # pylint: disable=protected-access

    updater.update(
        ProgressUpdate(
            runtime_status="running",
            current_step="parsing_pdf",
            progress_message="parsing document",
        ),
        force=False,
    )

    assert heartbeat_calls == ["heartbeat"]
