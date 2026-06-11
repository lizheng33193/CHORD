"""Plan 07 Phase 1 — BM25 indexer 单测。"""

from __future__ import annotations

from pathlib import Path

import pytest

from data_acquisition_agent.knowledge_base import V1_COUNTRIES
from data_acquisition_agent.knowledge_base import bm25_indexer as _bm25_module
from data_acquisition_agent.knowledge_base.bm25_indexer import get_indexer
from data_acquisition_agent.manifest import REPO_ROOT, load_manifest


@pytest.fixture(autouse=True)
def _reset_indexer_singleton(monkeypatch):
    monkeypatch.delenv("DA_LOCAL_DEV", raising=False)
    _bm25_module._INDEXERS.clear()
    yield
    _bm25_module._INDEXERS.clear()


def _norm(p) -> str:
    return Path(p).resolve().as_posix()


@pytest.mark.parametrize("country", V1_COUNTRIES)
def test_indexer_builds_for_v1_countries(country):
    indexer = get_indexer(country)
    assert indexer.country == country
    assert indexer.bm25 is not None
    assert len(indexer.doc_paths) >= 1


def test_doc_paths_are_real_files():
    indexer = get_indexer("mexico")
    for p in indexer.doc_paths:
        assert Path(p).exists(), f"BM25 indexed missing file: {p}"


def test_chinese_directory_path():
    indexer = get_indexer("mexico")
    chinese_paths = [p for p in indexer.doc_paths if "墨西哥" in p]
    assert len(chinese_paths) >= 1, "Expected at least one path containing 墨西哥"


def test_filename_with_space():
    indexer = get_indexer("mexico")
    space_paths = [p for p in indexer.doc_paths if "all_examples .md" in p]
    assert len(space_paths) == 1, "Expected exactly one path with 'all_examples .md' (with space)"


def test_search_returns_only_existing_paths():
    indexer = get_indexer("mexico")
    results = indexer.search("活跃用户 7 天", top_k=3)
    assert len(results) <= 3
    for p in results:
        assert Path(p).exists(), f"BM25 search returned missing file: {p}"


def test_non_v1_country_falls_back_to_empty_indexer():
    indexer = get_indexer("indonesia")
    assert hasattr(indexer, "doc_paths")


def test_local_dev_indexer_uses_local_manifest_when_enabled(monkeypatch):
    monkeypatch.setenv("DA_LOCAL_DEV", "1")
    indexer = get_indexer("mexico")
    assert indexer.doc_paths
    assert any("data_acquisition_agent/configs/local_dev/scheme.md" in p for p in indexer.doc_paths)
    assert any("data_acquisition_agent/configs/local_dev/few.md" in p for p in indexer.doc_paths)
    assert not any("各国数据知识库汇总/墨西哥/scheme.md" in p for p in indexer.doc_paths)
    assert not any("各国数据知识库汇总/墨西哥/few.md" in p for p in indexer.doc_paths)


@pytest.mark.parametrize("country", V1_COUNTRIES)
def test_index_covers_manifest_5_md(country):
    from data_acquisition_agent.knowledge_base.index_parser import parse_index_md

    manifest = load_manifest(country)
    manifest_paths = {
        _norm(manifest.system_prompt_md),
        _norm(manifest.business_logic_md),
        _norm(manifest.all_examples_md),
        _norm(manifest.schema_md),
        _norm(manifest.few_md),
    }
    entries = parse_index_md(country)
    index_paths = {_norm(REPO_ROOT / e["file"]) for e in entries}
    missing = manifest_paths - index_paths
    assert not missing, f"INDEX.md missing manifest md keys for {country}: {missing}"
