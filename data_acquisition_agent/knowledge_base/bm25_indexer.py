"""BM25 keyword indexer (Plan 07 Phase 1) — manifest 驱动，不 glob 目录。"""

from __future__ import annotations

from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from data_acquisition_agent.manifest import load_manifest, resolve_knowledge_namespace


class BM25Indexer:
    """文件级 BM25 索引；索引源 = manifest 的 5 个 md key（不 glob 目录）"""

    def __init__(self, country: str):
        self.country = country
        self.doc_paths: list[str] = []
        self.bm25: BM25Okapi | None = None
        self._build()

    def _build(self) -> None:
        try:
            manifest = load_manifest(self.country)
        except Exception:
            return

        md_paths: list[Path] = [
            manifest.system_prompt_md,
            manifest.business_logic_md,
            manifest.all_examples_md,
            manifest.schema_md,
            manifest.few_md,
        ]

        corpus: list[list[str]] = []
        for p in md_paths:
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8")
            tokens = list(jieba.cut(content))
            corpus.append(tokens)
            self.doc_paths.append(str(p))

        if corpus:
            self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k: int = 3) -> list[str]:
        if self.bm25 is None:
            return []
        query_tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(query_tokens)
        top_indices = scores.argsort()[-top_k:][::-1]
        return [self.doc_paths[i] for i in top_indices if scores[i] > 0]


_INDEXERS: dict[str, BM25Indexer] = {}


def get_indexer(country: str) -> BM25Indexer:
    namespace = resolve_knowledge_namespace(country)
    cache_key = f"{country}::{namespace}"
    if cache_key not in _INDEXERS:
        _INDEXERS[cache_key] = BM25Indexer(country)
    return _INDEXERS[cache_key]
