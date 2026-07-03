from __future__ import annotations


def test_worker_lifecycle_start_and_stop_manager_once(monkeypatch) -> None:
    from app import main

    events: list[str] = []

    class StubManager:
        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

    monkeypatch.setattr(main, "_risk_knowledge_worker_manager", None, raising=False)
    monkeypatch.setattr(main, "_build_risk_knowledge_worker_manager", lambda: StubManager(), raising=False)

    main._start_risk_knowledge_worker_manager()
    main._start_risk_knowledge_worker_manager()
    main._stop_risk_knowledge_worker_manager()
    main._stop_risk_knowledge_worker_manager()

    assert events == ["start", "stop"]


def test_worker_lifecycle_respects_disabled_setting(monkeypatch) -> None:
    from app import main
    from app.core.config import settings

    events: list[str] = []

    class StubManager:
        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

    monkeypatch.setattr(settings, "risk_knowledge_indexing_worker_enabled", False, raising=False)
    monkeypatch.setattr(main, "_risk_knowledge_worker_manager", None, raising=False)
    monkeypatch.setattr(main, "_build_risk_knowledge_worker_manager", lambda: StubManager(), raising=False)

    main._start_risk_knowledge_worker_manager()
    main._stop_risk_knowledge_worker_manager()

    assert events == []
