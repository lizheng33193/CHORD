# SWXY RAG Vendor Import

This directory contains vendored SWXY RAG engine assets for `M2D`.

## Provenance

- Source repo: `https://github.com/lizheng33193/SWXY`
- Source branch: `main`
- Source commit: `81ac2812c152e20012c88e80cd4736909c6c1ebe`
- Vendor date: `2026-06-30`
- Vendor strategy: `Hybrid mirror`
- Import boundary: `app.third_party.swxy_rag`

## Scope

This vendor import preserves the SWXY engine subtrees needed for later `M2D` phases:

- `deepdoc/`
- `rag/`
- `core/api/utils/file_utils.py`
- `conf/mapping.json`
- `file_parse_core.py`
- `retrieval_core.py`

The following renames were applied to make the vendored-engine role explicit:

- `file_parse.py -> file_parse_core.py`
- `retrieval.py -> retrieval_core.py`

## Phase Boundary

This directory does not mean the stage is runtime-usable yet.

`M2D-4` only vendors source/resources and performs the minimum import-path normalization needed to establish the `app.third_party.swxy_rag` package boundary.

This phase does not:

- install dependencies
- run ingestion
- run retrieval
- connect Elasticsearch
- implement `app/knowledge_base`
- implement `app/risk_knowledge`
- implement `RiskKnowledgeService`
- add routes or migrations
- integrate with NL Chat or Profile Explanation
