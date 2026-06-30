# M2D-4 SWXY Vendor Import Review

## 1. Review Purpose

This review records the `M2D-4` vendor import outcome only.

Current top-level project reading for `M2D` is:

> `M2D implementation in progress`

Current subphase reading is:

> `M2D-4 vendor import landed; no runtime integration started`

This review does not promote `M2D` to any finished-state label.

## 2. Vendor Provenance

- Source repo: `https://github.com/lizheng33193/SWXY`
- Source branch: `main`
- Source commit: `81ac2812c152e20012c88e80cd4736909c6c1ebe`
- Vendor date: `2026-06-30`
- Vendor strategy: `Hybrid mirror`
- Import boundary: `app.third_party.swxy_rag`

## 3. Vendored Files and Directories

The vendored subtree landed under:

- `app/third_party/__init__.py`
- `app/third_party/swxy_rag/__init__.py`
- `app/third_party/swxy_rag/README.md`
- `app/third_party/swxy_rag/core/__init__.py`
- `app/third_party/swxy_rag/core/api/__init__.py`
- `app/third_party/swxy_rag/core/api/utils/__init__.py`
- `app/third_party/swxy_rag/core/api/utils/file_utils.py`
- `app/third_party/swxy_rag/conf/mapping.json`
- `app/third_party/swxy_rag/deepdoc/...`
- `app/third_party/swxy_rag/rag/...`
- `app/third_party/swxy_rag/file_parse_core.py`
- `app/third_party/swxy_rag/retrieval_core.py`

## 4. Renamed Files

The following SWXY entry files were renamed during vendor import:

- `file_parse.py -> file_parse_core.py`
- `retrieval.py -> retrieval_core.py`

These renames make it explicit that the files are vendored engine entrypoints rather than CHORD-owned runtime services.

## 5. Import Path Normalization

This phase only performed the minimum import-path normalization needed to remove old `service.core` coupling and establish the vendored package boundary.

Normalization rule:

- old `service.core.deepdoc...` -> `app.third_party.swxy_rag.deepdoc...`
- old `service.core.rag...` -> `app.third_party.swxy_rag.rag...`
- old `service.core.api.utils...` -> `app.third_party.swxy_rag.core.api.utils...`

No parser, chunking, embedding, search, rerank, or business logic was intentionally changed in this phase.

## 6. Resource Inventory

Preserved resources:

- `rag/res/`
- `rag/res/deepdoc/`
- `conf/mapping.json`

Resource-path handling was minimally adjusted by moving `get_project_base_directory()` to resolve from the vendored package root rather than the old SWXY `service/core` root.

## 7. Large File Guard

Large-file check results:

- files over `50 MB`: present
- files over `100 MB`: none found

Notable large vendored resources include:

- `rag/res/deepdoc/layout.onnx`
- `rag/res/deepdoc/layout.laws.onnx`
- `rag/res/deepdoc/layout.manual.onnx`
- `rag/res/deepdoc/layout.paper.onnx`
- `rag/res/huqie.txt.trie`

No vendored file exceeded the GitHub 100 MB hard limit in this pass.

## 8. Dependency Inventory

Dependencies required later by the vendored engine include:

- `openai`
- `dashscope`
- `llama-index-core`
- `llama-index-postprocessor-dashscope-rerank-custom`
- `elasticsearch`
- `elasticsearch-dsl`
- `onnxruntime`
- `opencv-python`
- `shapely`
- `pyclipper`
- `xgboost`
- `pdfplumber`
- `pypdf`
- `python-docx`
- `openpyxl`
- `python-pptx`
- `tika`
- `datrie`
- `hanziconv`
- `nltk`
- `jieba`
- `tiktoken`
- `chardet`
- `huggingface_hub`
- `xxhash`

This phase does not install or activate these dependencies and does not add `requirements-rag.txt`.

## 9. Non-Migrated Files

This phase intentionally does not migrate:

- old SWXY application shell layout
- frontend
- auth / user / history routes
- database models
- init SQL
- `quick_parse_service.py`
- old chat prompt/session/history/Redis logic

## 10. Runtime Integration State

Still not started:

- `app/risk_knowledge`
- `app/knowledge_base`
- ingestion adapter
- retrieval adapter
- `RiskKnowledgeService`
- ES runtime integration
- NL Chat integration
- Profile Explanation integration

`M2D-4` only establishes the vendored engine boundary and leaves runtime integration for later `M2D` phases.
