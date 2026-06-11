"""Plan 07 Phase 2 — router 单测。"""

from __future__ import annotations

from pathlib import Path

from data_acquisition_agent.knowledge_base.index_parser import parse_index_md
from data_acquisition_agent.knowledge_base.router import (
    _full_inject_from_manifest,
    route_knowledge,
)


def test_index_parses_chinese_keyword_comma():
    entries = parse_index_md("mexico")
    assert len(entries) >= 5
    assert any(len(e["keywords"]) > 0 for e in entries)


def test_index_resolves_real_paths():
    from data_acquisition_agent.manifest import REPO_ROOT

    entries = parse_index_md("mexico")
    for e in entries:
        assert (REPO_ROOT / e["file"]).exists(), f"INDEX entry path does not exist: {e['file']}"


def test_route_returns_existing_files():
    from data_acquisition_agent.manifest import REPO_ROOT

    result = route_knowledge("查询活跃用户", "mexico", token_budget=15000)
    assert isinstance(result, list)
    assert len(result) >= 1
    for p in result:
        path = Path(p)
        if not path.is_absolute():
            path = REPO_ROOT / path
        assert path.exists(), f"Router returned missing file: {p}"


def test_always_inject_preserved_under_tight_budget():
    from data_acquisition_agent.manifest import REPO_ROOT

    entries = parse_index_md("mexico")
    must_inject = {e["file"] for e in entries if e["always_inject"]}
    assert len(must_inject) >= 1, "INDEX must have at least one always_inject=true entry"
    result = route_knowledge("xyz完全不相关的查询", "mexico", token_budget=5000)
    must_inject_norm = {(REPO_ROOT / f).resolve().as_posix() for f in must_inject}
    result_set = set(result)
    missing = must_inject_norm - result_set
    assert not missing, f"always_inject files must survive tight budget: {missing}"


def test_full_fallback_via_env(monkeypatch):
    monkeypatch.setenv("USE_FULL_KNOWLEDGE_INJECTION", "1")
    result = route_knowledge("anything", "mexico")
    assert all(not p.endswith("INDEX.md") for p in result)
    assert len(result) >= 4


def test_full_fallback_uses_manifest_not_glob():
    result = _full_inject_from_manifest("mexico")
    assert any("system_prompt.md" in p for p in result)


def test_parse_index_uses_local_dev_index_when_enabled(monkeypatch):
    monkeypatch.setenv("DA_LOCAL_DEV", "1")
    entries = parse_index_md("mexico")
    assert entries
    assert all("data_acquisition_agent/configs/local_dev/" in e["file"] or e["file"].endswith("system_prompt.md") for e in entries)
    assert not any("各国数据知识库汇总/墨西哥" in e["file"] for e in entries)


def test_route_knowledge_uses_local_dev_paths_when_enabled(monkeypatch):
    monkeypatch.setenv("DA_LOCAL_DEV", "1")
    result = route_knowledge("查高风险征信用户", "mexico", token_budget=15000)
    assert any("data_acquisition_agent/configs/local_dev/scheme.md" in p for p in result)
    assert any("data_acquisition_agent/configs/local_dev/few.md" in p for p in result)
    assert not any("各国数据知识库汇总/墨西哥/scheme.md" in p for p in result)
    assert not any("各国数据知识库汇总/墨西哥/few.md" in p for p in result)
