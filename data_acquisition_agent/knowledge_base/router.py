"""Knowledge router — INDEX -> BM25 -> full fallback (Plan 07 Phase 2).

三级路由：
1. always_inject 文件强制注入（不进 budget trim 候选名单）
2. INDEX 关键词命中 + BM25 top_k 兜底（这两类才进 budget trim）
3. 全量回退（USE_FULL_KNOWLEDGE_INJECTION=1 或 INDEX 解析为空时）
"""

from __future__ import annotations

import os
from pathlib import Path

from data_acquisition_agent.prompt_assembler import TOKEN_LIMIT

from .bm25_indexer import get_indexer
from .index_parser import parse_index_md


_DEFAULT_TOKEN_BUDGET = int(TOKEN_LIMIT * 0.03)


def route_knowledge(
    query: str,
    country: str,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
) -> list[str]:
    """返回应该加载的 md 文件**绝对路径字符串**（POSIX 形式）列表。"""
    if os.getenv("USE_FULL_KNOWLEDGE_INJECTION") == "1":
        return _full_inject_from_manifest(country)

    entries = parse_index_md(country)
    if not entries:
        return _full_inject_from_manifest(country)

    must_inject: list[str] = [e["file"] for e in entries if e["always_inject"]]

    optional: list[str] = []
    query_lower = query.lower()
    for e in entries:
        if e["always_inject"]:
            continue
        if any(kw.lower() in query_lower for kw in e["keywords"]):
            optional.append(e["file"])

    if len(optional) < 3:
        bm25_results = get_indexer(country).search(query, top_k=3)
        for path in bm25_results:
            if path not in must_inject and path not in optional:
                optional.append(path)

    file_to_estimate = {e["file"]: e["token_estimate"] for e in entries}
    used = sum(file_to_estimate.get(p, 5000) for p in must_inject)
    result = list(must_inject)
    for path in optional:
        est = file_to_estimate.get(path, 5000)
        if used + est <= token_budget:
            result.append(path)
            used += est

    if not result:
        return _full_inject_from_manifest(country)

    from data_acquisition_agent.manifest import REPO_ROOT

    return [
        (REPO_ROOT / p if not Path(p).is_absolute() else Path(p)).resolve().as_posix()
        for p in result
    ]


def _full_inject_from_manifest(country: str) -> list[str]:
    """从 manifest 读 5 个 md key —— 不 glob 目录（避免漏 system_prompt 跨国共享 + 防止误吃 INDEX.md）"""
    try:
        from data_acquisition_agent.manifest import load_manifest
    except ImportError:
        return []
    try:
        manifest = load_manifest(country)
    except Exception:
        return []
    paths = [
        manifest.system_prompt_md,
        manifest.business_logic_md,
        manifest.all_examples_md,
        manifest.schema_md,
        manifest.few_md,
    ]
    return [Path(p).resolve().as_posix() for p in paths if p.exists()]
