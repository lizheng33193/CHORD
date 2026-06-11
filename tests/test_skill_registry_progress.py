"""SkillRegistry.run_all progress_callback contract tests."""

from __future__ import annotations

from app.runtime_skills.base import BaseSkill, SkillRegistry


class _FakeSkill(BaseSkill):
    def __init__(self, name: str, stage: int = 0, depends_on=None, raise_exc=False):
        self.name = name
        self.stage = stage
        self.depends_on = depends_on or []
        self._raise = raise_exc

    def analyze(self, uid: str, **kwargs):
        if self._raise:
            raise RuntimeError(f"{self.name} boom")
        return {"summary": f"{self.name} ok"}


def test_run_all_without_callback_unchanged():
    """When callback is None the behavior must equal pre-change semantics."""
    reg = SkillRegistry()
    reg.register(_FakeSkill("a"))
    reg.register(_FakeSkill("b"))
    out = reg.run_all(uid="u1")
    assert set(out.keys()) == {"a", "b"}


def test_run_all_emits_started_and_completed():
    events: list[dict] = []
    reg = SkillRegistry()
    reg.register(_FakeSkill("a"))
    reg.run_all(uid="u1", progress_callback=events.append)

    types = [e["type"] for e in events]
    assert types == ["skill_started", "skill_completed"]
    for evt in events:
        assert evt["uid"] == "u1"
        assert evt["skill"] == "a"
        assert evt["stage"] == 0
    assert "duration_ms" in events[1]
    assert isinstance(events[1]["duration_ms"], int)


def test_run_all_emits_failed_on_exception():
    events: list[dict] = []
    reg = SkillRegistry()
    reg.register(_FakeSkill("a", raise_exc=True))
    reg.register(_FakeSkill("b"))  # downstream stage-0 sibling, must still run

    reg.run_all(uid="u1", progress_callback=events.append)

    types_for_a = [e["type"] for e in events if e["skill"] == "a"]
    assert types_for_a == ["skill_started", "skill_failed"]
    failed = next(e for e in events if e["type"] == "skill_failed")
    assert failed["error_message"] == "a boom"
    assert "duration_ms" in failed

    # b 的事件仍然推送，证明 skill_failed 不级联终止
    types_for_b = [e["type"] for e in events if e["skill"] == "b"]
    assert types_for_b == ["skill_started", "skill_completed"]


def test_run_all_callback_signature_is_dict_only():
    """Callback receives a single dict argument; no kwargs or extras."""
    captured: list[tuple] = []

    def cb(*args, **kwargs):
        captured.append((args, kwargs))

    reg = SkillRegistry()
    reg.register(_FakeSkill("a"))
    reg.run_all(uid="u1", progress_callback=cb)

    for args, kwargs in captured:
        assert len(args) == 1
        assert isinstance(args[0], dict)
        assert kwargs == {}
