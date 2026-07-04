from __future__ import annotations


def test_worker_runtime_helper_rejects_in_process_start_when_fallback_is_disabled() -> None:
    from app.risk_knowledge.runtime.worker import should_start_in_process_worker

    assert should_start_in_process_worker(worker_mode="external", fallback_enabled=False) is False


def test_worker_runtime_helper_allows_in_process_start_when_fallback_is_enabled() -> None:
    from app.risk_knowledge.runtime.worker import should_start_in_process_worker

    assert should_start_in_process_worker(worker_mode="external", fallback_enabled=True) is True
