"""BM25 foundation for M2D-10 retrieval."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.risk_knowledge.retrieval.tokenization import tokenize_for_bm25


@dataclass(frozen=True)
class BM25SearchHit:
    chunk_id: str
    doc_id: str
    version_id: str
    score: float
    rank: int
    matched_terms: list[str]


class BM25Index:
    def __init__(self, *, chunks: list[Any], tokenized_corpus: list[list[str]], k1: float, b: float) -> None:
        self._chunks = list(chunks)
        self._tokenized_corpus = tokenized_corpus
        self._bm25 = BM25Okapi(tokenized_corpus, k1=k1, b=b)

    @classmethod
    def build(cls, chunks: list[Any]) -> "BM25Index":
        tokenized_corpus = [tokenize_for_bm25(chunk.content_text) for chunk in chunks]
        return cls(
            chunks=chunks,
            tokenized_corpus=tokenized_corpus,
            k1=settings.risk_knowledge_bm25_k1,
            b=settings.risk_knowledge_bm25_b,
        )

    def search(self, query: str, *, top_k: int) -> list[BM25SearchHit]:
        query_tokens = tokenize_for_bm25(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        ordered = sorted(
            zip(self._chunks, scores, strict=False),
            key=lambda item: (-float(item[1]), item[0].chunk_id),
        )[:top_k]
        hits: list[BM25SearchHit] = []
        matched_terms = sorted(set(query_tokens))
        for rank, (chunk, score) in enumerate(ordered, start=1):
            hits.append(
                BM25SearchHit(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    version_id=chunk.version_id,
                    score=float(score),
                    rank=rank,
                    matched_terms=matched_terms,
                )
            )
        return hits


class BM25IndexCache:
    def __init__(self, *, max_size: int) -> None:
        self._max_size = max_size
        self._items: OrderedDict[str, BM25Index] = OrderedDict()

    def get(self, key: str) -> BM25Index | None:
        item = self._items.get(key)
        if item is None:
            return None
        self._items.move_to_end(key)
        return item

    def set(self, key: str, value: BM25Index) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self._max_size:
            self._items.popitem(last=False)


def build_scope_fingerprint(*, scope_type: str, kb_id: str, manifest_ids: list[str], manifest_fingerprints: list[str], chunks: list[Any]) -> str:
    payload = json.dumps(
        {
            "scope_type": scope_type,
            "kb_id": kb_id,
            "manifest_ids": sorted(manifest_ids),
            "manifest_fingerprints": sorted(manifest_fingerprints),
            "chunk_count": len(chunks),
            "chunk_pairs": sorted((chunk.chunk_id, chunk.content_hash) for chunk in chunks),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
